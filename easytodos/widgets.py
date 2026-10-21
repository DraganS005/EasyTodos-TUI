"""Custom widgets and modal screens for the Textual todo app."""

from __future__ import annotations

import asyncio

from rich.text import Text
from textual import events
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.message import Message
from textual.screen import ModalScreen, Screen
from textual.widgets import Button, Input, OptionList, Static, Tabs
from textual.widgets.option_list import Option

from . import APP_NAME
from .model import MAX_TEXT_LENGTH, Todo
from .themes import ThemeChoice, ThemeSelection
from .view import Row

NEW_GROUP_CHOICE = object()


def shorten(text: str, limit: int = 28) -> str:
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    return text[: max(1, limit - 3)] + "..."


def apply_size_classes(screen: Screen) -> None:
    """Apply responsive classes to the whole screen."""
    width, height = screen.size
    screen.set_class(width < 80 or height < 20, "-compact")
    screen.set_class(width < 50 or height < 11, "-tiny")
    screen.set_class(width < 60, "-narrow")
    screen.set_class(height < 4, "-micro")
    screen.set_class(height < 2, "-nano")


class ResponsiveScreenMixin:
    """Keep responsive CSS classes in sync for main and modal screens."""

    def on_mount(self) -> None:
        apply_size_classes(self)  # type: ignore[arg-type]

    def on_resize(self, event: events.Resize) -> None:
        apply_size_classes(self)  # type: ignore[arg-type]


class TodoClicked(Message):
    """A todo row was clicked."""

    def __init__(self, todo_id: str, toggle: bool) -> None:
        self.todo_id = todo_id
        self.toggle = toggle
        super().__init__()


class GroupClicked(Message):
    """A group header was clicked."""

    def __init__(self, group: str) -> None:
        self.group = group
        super().__init__()


class TodoRow(Static):
    """A single todo line. Click selects; the checkbox or a double-click toggles."""

    ALLOW_SELECT = False

    def __init__(self, todo: Todo, selected: bool = False) -> None:
        super().__init__(classes="todo-row", markup=False)
        self.todo = todo
        self.tooltip = "Click to select | click the box or double-click to check"
        self.set_class(todo.done, "-done")
        self.set_class(selected, "-selected")

    def render(self) -> Text:
        marker = "[x]" if self.todo.done else "[ ]"
        return Text(f"{marker} {self.todo.text}")

    def set_selected(self, selected: bool) -> None:
        self.set_class(selected, "-selected")
        self.refresh()

    def on_click(self, event: events.Click) -> None:
        if event.button != 1:
            return
        toggle = event.chain >= 2 or event.x <= 4
        self.post_message(TodoClicked(self.todo.id, toggle))
        event.stop()


class GroupHeader(Static):
    """A clickable group header."""

    ALLOW_SELECT = False

    def __init__(self, row: Row, first: bool) -> None:
        super().__init__(classes="group-header", markup=False)
        self.row = row
        self.tooltip = f"View {row.group}"
        self.set_class(first, "-first")

    def render(self) -> Text:
        return Text(f"{self.row.group}  ({self.row.done}/{self.row.total} done)")

    def on_click(self, event: events.Click) -> None:
        if event.button == 1:
            self.post_message(GroupClicked(self.row.group))
            event.stop()


class EmptyState(Static):
    """Message shown when the list has no visible rows."""

    def __init__(self, message: str) -> None:
        super().__init__(message, classes="empty-state", markup=False)


class TodoList(VerticalScroll):
    """Scrollable list which rebuilds rows from the current view state."""

    can_focus = False

    def __init__(
        self,
        rows: list[Row] | None = None,
        selected_id: str | None = None,
        empty_message: str = "",
    ) -> None:
        super().__init__(id="todo-list")
        self._selected_id = selected_id
        self._initial_rows = rows or []
        self._initial_empty_message = empty_message
        self._rebuild_lock = asyncio.Lock()

    @staticmethod
    def _row_widgets(
        rows: list[Row],
        selected_id: str | None,
        empty_message: str,
    ) -> list[Static]:
        widgets: list[Static] = []
        first_group = True
        for row in rows:
            if row.kind == "group":
                widgets.append(GroupHeader(row, first=first_group))
                first_group = False
            elif row.todo is not None:
                widgets.append(TodoRow(row.todo, selected=row.todo.id == selected_id))
        if not widgets:
            widgets.append(EmptyState(empty_message))
        return widgets

    def compose(self) -> ComposeResult:
        yield from self._row_widgets(
            self._initial_rows,
            self._selected_id,
            self._initial_empty_message,
        )

    async def rebuild(
        self,
        rows: list[Row],
        selected_id: str | None,
        empty_message: str,
    ) -> None:
        async with self._rebuild_lock:
            self._selected_id = selected_id
            await self.remove_children()

            widgets = self._row_widgets(rows, selected_id, empty_message)
            await self.mount_all(widgets)
            self.refresh(layout=True)
            self.call_after_refresh(self._scroll_selected)

    def select(self, todo_id: str | None) -> None:
        self._selected_id = todo_id
        for row in self.query(TodoRow):
            row.set_selected(row.todo.id == todo_id)
        self.call_after_refresh(self._scroll_selected)

    def _scroll_selected(self) -> None:
        for row in self.query(TodoRow):
            if row.has_class("-selected"):
                row.scroll_visible(animate=False)
                break


class ViewTabs(Tabs):
    """Tabs which never take keyboard focus; arrow keys are handled by the app."""

    can_focus = False


class ActionButton(Button):
    """Mouse action button which keeps keyboard focus off the toolbar."""

    can_focus = False


class HeaderBar(Horizontal):
    def compose(self) -> ComposeResult:
        yield Static(APP_NAME, id="app-title")
        yield Static("", id="app-stats")


class ActionBar(Horizontal):
    def compose(self) -> ComposeResult:
        yield ActionButton("New", id="btn-new", tooltip="Add a todo (n)")
        yield ActionButton("Check", id="btn-toggle", tooltip="Check off (space)")
        yield ActionButton("Group", id="btn-group", tooltip="Move to a group (g)")
        yield ActionButton("Delete", id="btn-delete", tooltip="Delete (d)")
        yield ActionButton("Hide done", id="btn-hide", tooltip="Hide completed (h)")
        yield ActionButton("Theme", id="btn-theme", tooltip="Change color theme (t)")
        yield ActionButton("Quit", id="btn-quit", tooltip="Quit (q)")


class MainScreen(ResponsiveScreenMixin, Screen):
    """Main screen; tab and shift+tab cycle views when nothing has focus."""

    BINDINGS = [
        Binding("tab", "app.next_view", "Next view", show=False),
        Binding("shift+tab", "app.previous_view", "Previous view", show=False),
    ]


class TextPromptModal(ResponsiveScreenMixin, ModalScreen[str | None]):
    """Single-line prompt used for new todos, group names, and edits."""

    BINDINGS = [Binding("escape", "cancel", "Cancel", show=False)]

    def __init__(
        self,
        title: str,
        *,
        placeholder: str = "",
        limit: int = MAX_TEXT_LENGTH,
    ) -> None:
        super().__init__()
        self.title_text = title
        self.placeholder = placeholder
        self.limit = limit

    def compose(self) -> ComposeResult:
        with Vertical(classes="dialog"):
            yield Static(self.title_text, classes="dialog-title", markup=False)
            yield Input(
                placeholder=self.placeholder,
                max_length=self.limit,
                compact=True,
                id="prompt-input",
            )
            with Horizontal(classes="dialog-buttons"):
                yield Button("Save", id="prompt-save", variant="primary")
                yield Button("Cancel", id="prompt-cancel")

    def on_mount(self) -> None:
        super().on_mount()
        self.query_one("#prompt-input", Input).focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        value = event.value.strip()
        self.dismiss(value or None)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "prompt-save":
            value = self.query_one("#prompt-input", Input).value.strip()
            self.dismiss(value or None)
        elif event.button.id == "prompt-cancel":
            self.dismiss(None)

    def action_cancel(self) -> None:
        self.dismiss(None)


class GroupPickerModal(ResponsiveScreenMixin, ModalScreen[str | object | None]):
    """Choose a group from a clickable list."""

    BINDINGS = [Binding("escape", "cancel", "Cancel", show=False)]

    def __init__(
        self,
        title: str,
        groups: list[str],
        counts: dict[str, tuple[int, int]],
        current: str | None,
    ) -> None:
        super().__init__()
        self.title_text = title
        self.groups = groups
        self.counts = counts
        self.current = current
        self._option_values: dict[str, str | object] = {}

    def compose(self) -> ComposeResult:
        options: list[Option] = []
        width = self.app.size.width
        name_limit = max(6, min(28, width - 8)) if width < 60 else 28
        for index, group in enumerate(self.groups):
            option_id = f"group-{index}"
            self._option_values[option_id] = group
            open_count, total = self.counts.get(group, (0, 0))
            label = Text(
                f"{shorten(group, name_limit)}  {open_count}/{total}",
                no_wrap=True,
                overflow="ellipsis",
            )
            options.append(Option(label, id=option_id))
        self._option_values["group-new"] = NEW_GROUP_CHOICE
        options.append(
            Option(
                Text("+ New group...", style="italic", no_wrap=True),
                id="group-new",
            )
        )

        with Vertical(classes="dialog group-dialog"):
            yield Static(self.title_text, classes="dialog-title", markup=False)
            yield OptionList(*options, compact=True, id="group-options")
            with Horizontal(classes="dialog-buttons"):
                yield Button("Cancel", id="group-cancel")

    def on_mount(self) -> None:
        super().on_mount()
        option_list = self.query_one("#group-options", OptionList)
        option_list.focus()
        if self.current in self.groups:
            option_list.highlighted = self.groups.index(self.current)

    def on_option_list_option_selected(
        self, event: OptionList.OptionSelected
    ) -> None:
        if event.option.id is None:
            return
        value = self._option_values.get(event.option.id)
        if value is not None:
            self.dismiss(value)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "group-cancel":
            self.dismiss(None)

    def action_cancel(self) -> None:
        self.dismiss(None)
class ThemePickerModal(ResponsiveScreenMixin, ModalScreen[ThemeSelection | None]):
    """Choose a theme and toggle a transparent background."""

    BINDINGS = [Binding("escape", "cancel", "Cancel", show=False)]

    def __init__(
        self,
        choices: tuple[ThemeChoice, ...],
        current: str,
        transparent: bool = False,
    ) -> None:
        super().__init__()
        self.choices = choices
        self.current = current
        self.transparent = transparent
        self._original_theme = current
        self._option_values: dict[str, str] = {}
        self._preview_ready = False

    def compose(self) -> ComposeResult:
        options: list[Option] = []
        show_swatch = self.app.size.width >= 40
        toggle_label = Text(no_wrap=True, overflow="ellipsis")
        toggle_label.append("[x] " if self.transparent else "[ ] ", style="bold")
        if self.app.size.width >= 36:
            toggle_text = "Transparent background"
        elif self.app.size.width >= 22:
            toggle_text = "Transparent"
        else:
            toggle_text = "Term bg"
        toggle_label.append(toggle_text)
        options.append(Option(toggle_label, id="transparent-background"))

        for index, choice in enumerate(self.choices):
            option_id = f"theme-{index}"
            self._option_values[option_id] = choice.id
            label = Text(no_wrap=True, overflow="ellipsis")
            if show_swatch:
                label.append(
                    "██",
                    style=f"{choice.swatch_primary} on {choice.swatch_background}",
                )
                label.append("  ")
            label.append(choice.label)
            options.append(Option(label, id=option_id))

        with Vertical(classes="dialog theme-dialog"):
            yield Static("Color theme", classes="dialog-title", markup=False)
            yield OptionList(*options, compact=True, id="theme-options")
            with Horizontal(classes="dialog-buttons"):
                yield Button("Cancel", id="theme-cancel")

    def on_mount(self) -> None:
        super().on_mount()
        option_list = self.query_one("#theme-options", OptionList)
        option_list.focus()
        for index, choice in enumerate(self.choices):
            if choice.id == self.current:
                option_list.highlighted = index + 1
                break
        self._preview_ready = True

    def on_option_list_option_highlighted(
        self, event: OptionList.OptionHighlighted
    ) -> None:
        if not self._preview_ready or event.option.id is None:
            return
        theme_id = self._option_values.get(event.option.id)
        if theme_id is not None and theme_id != self.app.theme:
            self.app.theme = theme_id

    def on_option_list_option_selected(
        self, event: OptionList.OptionSelected
    ) -> None:
        if event.option.id is None:
            return
        if event.option.id == "transparent-background":
            self.dismiss(ThemeSelection(self._original_theme, not self.transparent))
            return
        theme_id = self._option_values.get(event.option.id)
        if theme_id is not None:
            self.app.theme = theme_id
            self.dismiss(ThemeSelection(theme_id, self.transparent))

    def _cancel(self) -> None:
        self.app.theme = self._original_theme
        self.dismiss(None)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "theme-cancel":
            self._cancel()

    def action_cancel(self) -> None:
        self._cancel()
