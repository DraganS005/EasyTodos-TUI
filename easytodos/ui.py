"""Textual interface for the todo app."""

from __future__ import annotations

from rich.text import Text
from textual import events, on
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.reactive import Reactive
from textual.theme import Theme
from textual.widgets import Button, Static, Tab, Tabs

from . import APP_NAME
from .model import (
    DEFAULT_GROUP,
    DEFAULT_THEME,
    MAX_GROUP_LENGTH,
    StoreError,
    TodoStore,
)
from .themes import (
    CUSTOM_THEMES,
    THEME_CHOICES,
    THEME_IDS,
    ThemeSelection,
    get_theme_choice,
)
from .view import build_rows, visible_todo_ids
from .widgets import (
    NEW_GROUP_CHOICE,
    ActionBar,
    ActionButton,
    GroupClicked,
    GroupPickerModal,
    HeaderBar,
    MainScreen,
    TextPromptModal,
    ThemePickerModal,
    TodoClicked,
    TodoList,
    ViewTabs,
    shorten,
)


class TodoApp(App[None]):
    """A compact, mouse-friendly terminal todo list."""

    CSS_PATH = "app.tcss"
    TITLE = APP_NAME
    theme = Reactive(DEFAULT_THEME)

    def register_theme(self, theme: Theme) -> None:
        """Register the custom themes while Textual initializes its built-ins.

        The base ``App`` builds its initial stylesheet before subclass
        ``__init__`` code runs, so registering the custom themes here ensures
        the saved theme is available for that first stylesheet.
        """
        super().register_theme(theme)
        for custom_theme in CUSTOM_THEMES:
            super().register_theme(custom_theme)

    BINDINGS = [
        Binding("n", "add", "New"),
        Binding("a", "add", "New", show=False),
        Binding("space", "toggle", "Check"),
        Binding("enter", "toggle", "Check", show=False),
        Binding("x", "toggle", "Check", show=False),
        Binding("d", "delete", "Delete"),
        Binding("delete", "delete", "Delete", show=False),
        Binding("g", "move", "Group"),
        Binding("G", "new_group", "New group"),
        Binding("h", "toggle_done", "Hide done"),
        Binding("t", "theme", "Theme"),
        Binding("j", "cursor_down", "Down", show=False),
        Binding("down", "cursor_down", "Down", show=False),
        Binding("k", "cursor_up", "Up", show=False),
        Binding("up", "cursor_up", "Up", show=False),
        Binding("left", "previous_view", "Previous view", show=False),
        Binding("right", "next_view", "Next view", show=False),
        Binding("[", "previous_view", "Previous view", show=False),
        Binding("]", "next_view", "Next view", show=False),
        Binding("q", "quit", "Quit"),
    ]

    def __init__(self, store: TodoStore) -> None:
        # Set ANSI handling up front so transparency works in the first frame.
        super().__init__(ansi_color=True if store.transparent else None)
        self.store = store
        self.view: str | None = None
        self.active_group = store.groups[0] if store.groups else DEFAULT_GROUP
        self.selected_id: str | None = None
        self.show_done = True
        self.message = ""
        self.message_is_error = False
        self.main_screen: MainScreen | None = None
        self._tab_views: dict[str, str | None] = {}
        self._syncing_tabs = False
        self.transparent_background = store.transparent
        # Apply the startup appearance before the stylesheet is first parsed.
        self.set_class(store.transparent, "-transparent")

    def get_default_screen(self) -> MainScreen:
        screen = MainScreen()
        screen.set_class(self.transparent_background, "-transparent")
        self.main_screen = screen
        return screen

    def _make_tab_widgets(self) -> list[Tab]:
        """Create the view tabs from the store's current groups."""
        self._tab_views = {}
        entries: list[tuple[str | None, str]] = [(None, "All")]
        entries.extend((group, group) for group in self.store.groups)
        tabs: list[Tab] = []
        for index, (view, name) in enumerate(entries):
            tab_id = "view-all" if view is None else f"view-{index}"
            label = "All" if view is None else shorten(name, 18)
            tab = Tab(Text(label), id=tab_id)
            if view is not None:
                tab.tooltip = f"View {name}"
            tabs.append(tab)
            self._tab_views[tab_id] = view
        return tabs

    def compose(self) -> ComposeResult:
        # Build the complete first frame here. Mounting empty widgets and then
        # filling them from on_mount costs an extra layout pass.
        rows = self._rows()
        ids = visible_todo_ids(rows)
        self.selected_id = ids[0] if ids else None
        yield HeaderBar(id="app-header")
        yield ViewTabs(
            *self._make_tab_widgets(),
            active="view-all",
            id="views",
        )
        yield TodoList(rows, self.selected_id, self._empty_message())
        yield Static("", id="status", markup=False)
        yield ActionBar(id="actions")
        yield Static("", id="help", markup=False)

    _MAIN_ACTIONS = frozenset(
        {
            "add",
            "toggle",
            "delete",
            "move",
            "new_group",
            "toggle_done",
            "theme",
            "cursor_down",
            "cursor_up",
            "previous_view",
            "next_view",
            "quit",
        }
    )

    def check_action(self, action: str, parameters: tuple[object, ...]) -> bool:
        """Keep main-screen shortcuts from firing behind a modal."""
        if (
            self.main_screen is not None
            and self.screen is not self.main_screen
            and action in self._MAIN_ACTIONS
        ):
            return False
        return True

    # -- lifecycle -----------------------------------------------------------

    async def on_mount(self) -> None:
        if self.main_screen is None:
            self.main_screen = self.screen  # type: ignore[assignment]
        saved_theme = (
            self.store.theme if self.store.theme in THEME_IDS else DEFAULT_THEME
        )
        if saved_theme != self.theme:
            self.theme = saved_theme
        self._update_chrome()

    def on_resize(self, event: events.Resize) -> None:
        if self.main_screen is not None and self.main_screen.is_mounted:
            self.call_after_refresh(self._update_chrome)
            self.call_after_refresh(self._scroll_selected)

    # -- state helpers -------------------------------------------------------

    def _rows(self):
        return build_rows(self.store, self.view, self.show_done)

    def _visible_ids(self) -> list[str]:
        return visible_todo_ids(self._rows())

    def _selected_todo(self):
        return self.store.get(self.selected_id)

    def _empty_message(self) -> str:
        if not self.store.todos:
            return "No todos yet. Press n or click New."
        in_view = [
            todo
            for todo in self.store.todos
            if self.view is None or todo.group == self.view
        ]
        if not in_view:
            return f"No todos in {self.view}. Press n or click New."
        if not self.show_done and any(todo.done for todo in in_view):
            where = f" in {self.view}" if self.view is not None else " here"
            return f"Nothing open{where}. Press h to show completed todos."
        return "Nothing to show."

    def _set_message(self, message: str, *, error: bool = False) -> None:
        self.message = message
        self.message_is_error = error
        self._update_chrome()

    def _error(self, message: str) -> None:
        self._set_message(message, error=True)
        self.notify(message, severity="error", timeout=5)

    @staticmethod
    def _nearest_id(
        old_ids: list[str],
        selected_id: str | None,
        new_ids: list[str],
    ) -> str | None:
        """Keep the selection stable when the selected row disappears."""
        if selected_id in new_ids:
            return selected_id
        if not new_ids:
            return None
        try:
            index = old_ids.index(selected_id) if selected_id is not None else 0
        except ValueError:
            index = 0
        return new_ids[min(index, len(new_ids) - 1)]

    def _item_list(self) -> TodoList:
        assert self.main_screen is not None
        return self.main_screen.query_one("#todo-list", TodoList)

    def _apply_selection(self) -> None:
        self._item_list().select(self.selected_id)

    def _scroll_selected(self) -> None:
        self._item_list()._scroll_selected()

    async def _refresh_rows(self) -> None:
        """Rebuild the visible list from the store, then refresh the chrome."""
        rows = self._rows()
        ids = visible_todo_ids(rows)
        if self.selected_id not in ids:
            self.selected_id = ids[0] if ids else None
        await self._item_list().rebuild(
            rows,
            self.selected_id,
            self._empty_message(),
        )
        self._update_chrome()

    # -- chrome --------------------------------------------------------------

    def _update_chrome(self) -> None:
        if self.main_screen is None or not self.main_screen.is_mounted:
            return
        screen = self.main_screen
        width, height = screen.size
        tiny = width < 50 or height < 11
        compact = width < 80 or height < 20

        screen.query_one("#app-stats", Static).update(
            f"{self.store.open_count} open, {self.store.done_count} done"
        )

        if self.message:
            status = self.message
            screen.query_one("#status", Static).set_class(
                self.message_is_error, "-error"
            )
        else:
            status = (
                f"Viewing {self.view}"
                if self.view is not None
                else "Viewing all groups"
            )
            screen.query_one("#status", Static).remove_class("-error")
        screen.query_one("#status", Static).update(status)

        screen.query_one("#help", Static).update(
            self._help_text(width, compact, tiny)
        )

        has_selection = self._selected_todo() is not None
        for button_id in ("btn-toggle", "btn-group", "btn-delete"):
            screen.query_one(f"#{button_id}", ActionButton).disabled = not has_selection

        hide_label = "Hide done" if self.show_done else "Show done"
        if tiny:
            labels = {
                "btn-new": "+",
                "btn-toggle": "ok",
                "btn-group": "g",
                "btn-delete": "x",
                "btn-hide": "hide",
                "btn-theme": "t",
                "btn-quit": "quit",
            }
        elif compact:
            labels = {
                "btn-new": "+ New",
                "btn-toggle": "Check",
                "btn-group": "Group",
                "btn-delete": "Del",
                "btn-hide": "Hide" if self.show_done else "Show",
                "btn-theme": "Theme",
                "btn-quit": "Quit",
            }
        else:
            labels = {
                "btn-new": "New",
                "btn-toggle": "Check",
                "btn-group": "Group",
                "btn-delete": "Delete",
                "btn-hide": hide_label,
                "btn-theme": "Theme",
                "btn-quit": "Quit",
            }
        for button_id, label in labels.items():
            screen.query_one(f"#{button_id}", ActionButton).label = label

    def _help_text(self, width: int, compact: bool, tiny: bool) -> str:
        if tiny or compact:
            return ""
        hide = "hide done" if self.show_done else "show done"
        if width >= 100:
            return (
                "n new   space check   d delete   g group   G new group   "
                f"t theme   tab view   h {hide}   q quit"
            )
        short_hide = "hide" if self.show_done else "show"
        return (
            "n new  space check  d del  g group  G new  t theme  "
            f"tab view  h {short_hide}  q quit"
        )

    # -- tabs ----------------------------------------------------------------

    def _sync_tabs(self) -> None:
        if self.main_screen is None:
            return
        tabs = self.main_screen.query_one("#views", Tabs)
        tab_id = next(
            (key for key, view in self._tab_views.items() if view == self.view),
            None,
        )
        if tab_id is not None and tabs.active != tab_id:
            self._syncing_tabs = True
            try:
                tabs.active = tab_id
            finally:
                self._syncing_tabs = False

    async def _rebuild_tabs(self) -> None:
        if self.main_screen is None:
            return
        tabs = self.main_screen.query_one("#views", ViewTabs)
        self._syncing_tabs = True
        try:
            await tabs.clear()
            for tab in self._make_tab_widgets():
                await tabs.add_tab(tab)
        finally:
            self._syncing_tabs = False
        self._sync_tabs()

    @on(Tabs.TabActivated)
    async def _tab_activated(self, event: Tabs.TabActivated) -> None:
        if self._syncing_tabs or event.tab.id is None:
            return
        if event.tab.id not in self._tab_views:
            return
        view = self._tab_views[event.tab.id]
        if view == self.view:
            return
        await self._set_view(view, sync_tabs=False)

    async def _set_view(self, view: str | None, *, sync_tabs: bool = True) -> None:
        if view is not None and view not in self.store.groups:
            return
        self.view = view
        if view is not None:
            self.active_group = view
        self.selected_id = None
        if sync_tabs:
            self._sync_tabs()
        await self._refresh_rows()
        label = self.view if self.view is not None else "all groups"
        self._set_message(f"Viewing {label}.")

    # -- view navigation -----------------------------------------------------

    async def action_next_view(self) -> None:
        await self._cycle_view(1)

    async def action_previous_view(self) -> None:
        await self._cycle_view(-1)

    async def _cycle_view(self, step: int) -> None:
        views: list[str | None] = [None, *self.store.groups]
        try:
            index = views.index(self.view)
        except ValueError:
            index = 0
        await self._set_view(views[(index + step) % len(views)])

    # -- cursor --------------------------------------------------------------

    def _move_cursor(self, delta: int) -> None:
        ids = self._visible_ids()
        if not ids:
            self.selected_id = None
            self._apply_selection()
            return
        if self.selected_id not in ids:
            self.selected_id = ids[0] if delta >= 0 else ids[-1]
        else:
            index = ids.index(self.selected_id)
            self.selected_id = ids[max(0, min(len(ids) - 1, index + delta))]
        self._apply_selection()

    def action_cursor_down(self) -> None:
        self._move_cursor(1)

    def action_cursor_up(self) -> None:
        self._move_cursor(-1)

    # -- todo actions --------------------------------------------------------

    def action_add(self) -> None:
        selected = self._selected_todo()
        if self.view is not None:
            group = self.view
        elif selected is not None:
            group = selected.group
        else:
            group = self.active_group
        if group not in self.store.groups:
            group = DEFAULT_GROUP
        self.push_screen(
            TextPromptModal(
                f"New todo in {group}",
                placeholder="What needs doing?",
            ),
            callback=lambda text: self._on_add_result(text, group),
        )

    def _on_add_result(self, text: str | None, group: str) -> None:
        if text:
            self.run_worker(self._create_todo(text, group), exclusive=False)

    async def _create_todo(self, text: str, group: str) -> None:
        try:
            todo = self.store.add(text, group)
        except (ValueError, StoreError) as exc:
            self._error(str(exc))
            return
        self.active_group = todo.group
        self.selected_id = todo.id
        await self._refresh_rows()
        self._set_message(f"Added to {todo.group}.")

    async def _toggle(self, todo_id: str) -> None:
        todo = self.store.get(todo_id)
        if todo is None:
            return
        old_ids = self._visible_ids()
        self.selected_id = todo_id
        try:
            updated = self.store.toggle(todo.id)
        except StoreError as exc:
            self._error(str(exc))
            return
        new_ids = self._visible_ids()
        self.selected_id = self._nearest_id(old_ids, todo_id, new_ids)
        await self._refresh_rows()
        if updated is not None:
            self._set_message(
                f"Checked off: {shorten(updated.text)}"
                if updated.done
                else f"Reopened: {shorten(updated.text)}"
            )

    async def action_toggle(self) -> None:
        if self.selected_id is not None:
            await self._toggle(self.selected_id)

    async def action_delete(self) -> None:
        todo = self._selected_todo()
        if todo is not None:
            await self._delete_todo(todo.id)

    async def _delete_todo(self, todo_id: str) -> None:
        todo = self.store.get(todo_id)
        if todo is None:
            return
        old_ids = self._visible_ids()
        try:
            self.store.delete(todo.id)
        except StoreError as exc:
            self._error(str(exc))
            return
        self.selected_id = self._nearest_id(old_ids, todo_id, self._visible_ids())
        await self._refresh_rows()
        self._set_message(f"Deleted: {shorten(todo.text)}")

    def action_move(self) -> None:
        todo = self._selected_todo()
        if todo is None:
            return
        counts = {
            group: (
                sum(not item.done and item.group == group for item in self.store.todos),
                sum(item.group == group for item in self.store.todos),
            )
            for group in self.store.groups
        }
        self.push_screen(
            GroupPickerModal(
                f'Move "{shorten(todo.text, 22)}"',
                list(self.store.groups),
                counts,
                todo.group,
            ),
            callback=lambda choice: self._on_group_choice(todo.id, choice),
        )

    def _on_group_choice(self, todo_id: str, choice: str | object | None) -> None:
        if choice is None:
            return
        if choice is NEW_GROUP_CHOICE:
            self.push_screen(
                TextPromptModal(
                    "New group name",
                    placeholder="e.g. Work, Home, Errands",
                    limit=MAX_GROUP_LENGTH,
                ),
                callback=lambda name: self._on_new_group_for_move(todo_id, name),
            )
            return
        assert isinstance(choice, str)
        self.run_worker(self._move_todo(todo_id, choice), exclusive=False)

    def _on_new_group_for_move(self, todo_id: str, name: str | None) -> None:
        if name:
            self.run_worker(
                self._create_group_and_move(todo_id, name), exclusive=False
            )

    async def _move_todo(self, todo_id: str, group: str) -> None:
        todo = self.store.get(todo_id)
        if todo is None:
            return
        if todo.group == group:
            self._set_message(f"Already in {group}.")
            return
        old_ids = self._visible_ids()
        try:
            moved = self.store.move(todo.id, group)
        except (ValueError, StoreError) as exc:
            self._error(str(exc))
            return
        self.selected_id = self._nearest_id(old_ids, todo_id, self._visible_ids())
        await self._refresh_rows()
        if moved is not None:
            self._set_message(f"Moved to {group}.")

    async def _create_group_and_move(self, todo_id: str, name: str) -> None:
        try:
            group = self.store.add_group(name)
            self.store.move(todo_id, group)
        except (ValueError, StoreError) as exc:
            self._error(str(exc))
            return
        await self._rebuild_tabs()
        await self._refresh_rows()
        self._set_message(f"Moved to {group}.")

    def action_new_group(self) -> None:
        self.push_screen(
            TextPromptModal(
                "New group name",
                placeholder="e.g. Work, Home, Errands",
                limit=MAX_GROUP_LENGTH,
            ),
            callback=self._on_new_group_result,
        )

    def _on_new_group_result(self, name: str | None) -> None:
        if name:
            self.run_worker(self._create_group(name), exclusive=False)

    async def _create_group(self, name: str) -> None:
        try:
            group = self.store.add_group(name)
        except (ValueError, StoreError) as exc:
            self._error(str(exc))
            return
        await self._rebuild_tabs()
        await self._set_view(group)
        self._set_message(f"Viewing {group}. Press n to add a todo.")

    async def action_toggle_done(self) -> None:
        await self._toggle_show_done()

    def action_theme(self) -> None:
        current_theme = self.theme
        current_transparent = self.transparent_background
        self.push_screen(
            ThemePickerModal(
                THEME_CHOICES,
                current_theme,
                current_transparent,
            ),
            callback=lambda result: self._on_theme_result(
                result, current_theme, current_transparent
            ),
        )

    def _apply_transparency(self) -> None:
        enabled = self.transparent_background
        # ``transparent`` is rendered as black by Textual. ANSI default (with
        # native ANSI colors enabled) emits the terminal's own background.
        self.ansi_color = True if enabled else None
        self.set_class(enabled, "-transparent")
        if self.main_screen is not None:
            self.main_screen.set_class(enabled, "-transparent")
        # App class changes do not trigger a stylesheet refresh on their own.
        self.refresh_css(animate=False)

    def _on_theme_result(
        self,
        result: ThemeSelection | None,
        previous_theme: str,
        previous_transparent: bool,
    ) -> None:
        if result is None:
            self.theme = previous_theme
            self.transparent_background = previous_transparent
            self._apply_transparency()
            return
        choice = get_theme_choice(result.theme)
        if choice is None:
            self.theme = previous_theme
            self.transparent_background = previous_transparent
            self._apply_transparency()
            self._error(f"Unknown theme: {result.theme}")
            return
        self.theme = result.theme
        self.transparent_background = result.transparent
        self._apply_transparency()
        try:
            self.store.set_appearance(result.theme, result.transparent)
        except (ValueError, StoreError) as exc:
            self.theme = (
                self.store.theme if self.store.theme in THEME_IDS else previous_theme
            )
            self.transparent_background = self.store.transparent
            self._apply_transparency()
            self._error(str(exc))
            return
        if result.transparent != previous_transparent:
            state = "enabled" if result.transparent else "disabled"
            self._set_message(f"Transparent background {state}.")
        elif result.transparent:
            self._set_message(f"Color theme: {choice.label}, transparent background.")
        else:
            self._set_message(f"Color theme: {choice.label}.")

    async def _toggle_show_done(self) -> None:
        old_ids = self._visible_ids()
        self.show_done = not self.show_done
        self.selected_id = self._nearest_id(
            old_ids, self.selected_id, self._visible_ids()
        )
        await self._refresh_rows()
        self._set_message(
            "Showing completed todos." if self.show_done else "Hiding completed todos."
        )

    # -- widget messages -----------------------------------------------------

    @on(TodoClicked)
    async def _todo_clicked(self, event: TodoClicked) -> None:
        self.selected_id = event.todo_id
        self._apply_selection()
        if event.toggle:
            await self._toggle(event.todo_id)

    @on(GroupClicked)
    async def _group_clicked(self, event: GroupClicked) -> None:
        if event.group in self.store.groups and event.group != self.view:
            await self._set_view(event.group)

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        button_id = event.button.id
        if button_id == "btn-new":
            self.action_add()
        elif button_id == "btn-toggle":
            await self.action_toggle()
        elif button_id == "btn-group":
            self.action_move()
        elif button_id == "btn-delete":
            await self.action_delete()
        elif button_id == "btn-hide":
            await self.action_toggle_done()
        elif button_id == "btn-theme":
            self.action_theme()
        elif button_id == "btn-quit":
            self.exit()
