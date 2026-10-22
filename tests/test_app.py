from __future__ import annotations

import asyncio
import tempfile
import time
import unittest
from contextlib import asynccontextmanager
from pathlib import Path

from textual.containers import VerticalScroll
from textual.widgets import Input, OptionList, Tab, TextArea

from easytodos.model import MAX_DESCRIPTION_LENGTH, TodoStore
from easytodos.themes import THEME_CHOICES
from easytodos.ui import TodoApp
from easytodos.widgets import (
    HELP_SECTIONS,
    ActionButton,
    GroupPickerModal,
    HelpModal,
    MainScreen,
    TextPromptModal,
    ThemePickerModal,
    TodoEditorModal,
    TodoRow,
)


class TodoAppTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        # IsolatedAsyncioTestCase enables debug mode, which makes Textual's
        # idle detection extremely slow. Disable it for these UI tests.
        asyncio.get_running_loop().set_debug(False)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "todos.json"
        self.store = TodoStore(self.path)
        self.app: TodoApp
        self.pilot = None

    @asynccontextmanager
    async def running_app(self, size: tuple[int, int] = (80, 24)):
        self.app = TodoApp(self.store)
        async with self.app.run_test(size=size) as pilot:
            self.pilot = pilot
            await pilot.pause()
            yield pilot

    async def wait_until(
        self,
        predicate,
        message: str = "condition",
        timeout: float = 2.0,
    ) -> None:
        deadline = time.monotonic() + timeout
        while not predicate():
            if time.monotonic() >= deadline:
                self.fail(f"Timed out waiting for {message}")
            await self.pilot.pause(0.01)

    def rows(self) -> list[TodoRow]:
        return list(self.app.main_screen.query(TodoRow))

    def row_texts(self) -> list[str]:
        return [row.todo.text for row in self.rows()]

    def assert_inside(self, child, parent) -> None:
        self.assertGreaterEqual(child.region.x, parent.region.x)
        self.assertGreaterEqual(child.region.y, parent.region.y)
        self.assertLessEqual(child.region.right, parent.region.right)
        self.assertLessEqual(child.region.bottom, parent.region.bottom)

    def selected_row(self) -> TodoRow:
        selected = [row for row in self.rows() if row.has_class("-selected")]
        self.assertEqual(len(selected), 1, "exactly one row should be selected")
        return selected[0]

    async def test_initial_state_and_group_order(self) -> None:
        first = self.store.add("first")
        done = self.store.add("second")
        third = self.store.add("third", "Work")
        self.store.toggle(done.id)
        async with self.running_app():
            self.assertEqual(self.row_texts(), ["first", "second", "third"])
            self.assertEqual(self.app.selected_id, first.id)
            self.assertEqual(self.selected_row().todo.id, first.id)
            self.assertEqual(
                self.app.main_screen.query_one("#views").active, "view-all"
            )
            self.assertEqual(self.app.TITLE, "easytodos")
            self.assertEqual(
                str(self.app.main_screen.query_one("#app-title").render()),
                "easytodos",
            )
            self.assertEqual(
                str(self.app.main_screen.query_one("#app-stats").render()),
                "2 open, 1 done",
            )
            self.assertIn(third.id, self.app._visible_ids())

    async def test_footer_shortcuts_are_in_the_action_bar(self) -> None:
        async with self.running_app(size=(120, 24)):
            screen = self.app.main_screen
            self.assertEqual(len(screen.query("#help")), 0)
            self.assertEqual(len(screen.query("#shortcuts")), 0)
            labels = {
                button.id: str(button.label) for button in screen.query(ActionButton)
            }
            self.assertEqual(labels["btn-new"], "n New")
            self.assertEqual(labels["btn-toggle"], "space Check")
            self.assertEqual(labels["btn-edit"], "e Edit")
            self.assertEqual(labels["btn-delete"], "d Delete")
            self.assertEqual(labels["btn-help"], "? Help")
            self.assertTrue(screen.query_one("#btn-edit", ActionButton).disabled)
            for button in screen.query(ActionButton):
                self.assertLessEqual(button.region.right, screen.size.width)

    async def test_footer_edit_button_opens_the_editor(self) -> None:
        todo = self.store.add("edit from footer")
        async with self.running_app(size=(120, 24)) as pilot:
            edit_button = self.app.main_screen.query_one("#btn-edit", ActionButton)
            self.assertFalse(edit_button.disabled)
            await pilot.click("#btn-edit")
            await self.wait_until(
                lambda: isinstance(self.app.screen, TodoEditorModal),
                "edit modal from footer",
            )
            self.assertEqual(
                self.app.screen.query_one("#todo-text", Input).value,
                todo.text,
            )

    async def test_footer_fits_at_every_supported_width(self) -> None:
        self.store.add("keep the footer honest")
        async with self.running_app(size=(120, 24)) as pilot:
            screen = self.app.main_screen
            for width in (20, 24, 30, 40, 50, 60, 79, 80, 91, 92, 96, 97, 101, 102, 120):
                await pilot.resize_terminal(width, 24)
                await pilot.pause(0.05)
                visible = [
                    button for button in screen.query(ActionButton) if button.display
                ]
                self.assertTrue(
                    any(button.id == "btn-edit" for button in visible),
                    f"Edit button missing at width {width}",
                )
                for button in visible:
                    self.assertLessEqual(
                        button.region.right,
                        width,
                        f"{button.id} overflows at width {width}",
                    )

    async def test_help_window_lists_every_shortcut_and_scrolls(self) -> None:
        async with self.running_app(size=(80, 20)) as pilot:
            await pilot.click("#btn-help")
            await self.wait_until(
                lambda: isinstance(self.app.screen, HelpModal), "help modal"
            )

            help_list = self.app.screen.query_one("#help-list", VerticalScroll)
            self.assertTrue(help_list.display)
            self.assertTrue(help_list.can_focus)
            self.assertEqual(self.app.focused, help_list)
            self.assertGreater(help_list.max_scroll_y, 0)

            rendered_keys = "  ".join(
                str(widget.render()) for widget in self.app.screen.query(".help-key")
            )
            help_keys = {
                key
                for _, rows in HELP_SECTIONS
                for keys, _ in rows
                for key in keys
            }
            for _, rows in HELP_SECTIONS:
                for keys, _ in rows:
                    self.assertIn(" / ".join(keys), rendered_keys)
            for binding in (
                *TodoApp.BINDINGS,
                *MainScreen.BINDINGS,
                *HelpModal.BINDINGS,
            ):
                key = {
                    "question_mark": "?",
                    "delete": "Delete",
                    "f1": "F1",
                }.get(binding.key, binding.key)
                self.assertIn(key, help_keys)

            await pilot.press("pagedown")
            await pilot.pause()
            self.assertGreater(help_list.scroll_y, 0)

            await pilot.click("#help-close")
            await self.wait_until(
                lambda: isinstance(self.app.screen, MainScreen), "main after help"
            )

            await pilot.press("question_mark")
            await self.wait_until(
                lambda: isinstance(self.app.screen, HelpModal), "help modal by key"
            )
            await pilot.press("escape")
            await self.wait_until(
                lambda: isinstance(self.app.screen, MainScreen), "main after escape"
            )

    async def test_add_from_keyboard_and_persist(self) -> None:
        async with self.running_app() as pilot:
            await pilot.press("n")
            await self.wait_until(
                lambda: isinstance(self.app.screen, TodoEditorModal), "add modal"
            )
            await pilot.press(*"new item")
            await pilot.press("enter")
            await self.wait_until(
                lambda: isinstance(self.app.screen, MainScreen), "main screen"
            )
            await self.wait_until(lambda: "new item" in self.row_texts(), "new row")

            saved = self.store.todos[-1]
            self.assertEqual(saved.text, "new item")
            self.assertEqual(saved.description, "")
            self.assertEqual(self.app.selected_id, saved.id)
            reloaded = TodoStore(self.path)
            self.assertEqual([todo.text for todo in reloaded.todos], ["new item"])

    async def test_add_with_a_description_from_the_mouse(self) -> None:
        async with self.running_app() as pilot:
            await pilot.click("#btn-new")
            await self.wait_until(
                lambda: isinstance(self.app.screen, TodoEditorModal), "add modal"
            )
            await pilot.press(*"book flights")
            await pilot.press("tab")
            await pilot.press(*"Check the airline site")
            await pilot.click("#todo-save")
            await self.wait_until(
                lambda: isinstance(self.app.screen, MainScreen), "main screen"
            )
            await self.wait_until(
                lambda: self.store.todos
                and self.store.todos[0].description == "Check the airline site",
                "description saved",
            )
            self.assertEqual(self.store.todos[0].text, "book flights")
            self.assertEqual(
                TodoStore(self.path).todos[0].description,
                "Check the airline site",
            )

    async def test_editor_saves_description_with_ctrl_s(self) -> None:
        async with self.running_app() as pilot:
            await pilot.press("n")
            await self.wait_until(
                lambda: isinstance(self.app.screen, TodoEditorModal), "add modal"
            )
            await pilot.press(*"keyboard todo")
            await pilot.press("tab")
            await pilot.press(*"keyboard details")
            await pilot.press("ctrl+s")
            await self.wait_until(
                lambda: isinstance(self.app.screen, MainScreen), "main screen"
            )
            await self.wait_until(
                lambda: self.store.todos
                and self.store.todos[0].description == "keyboard details",
                "description saved",
            )
            self.assertEqual(self.store.todos[0].text, "keyboard todo")

    async def test_add_from_mouse_toolbar_and_save_button(self) -> None:
        async with self.running_app() as pilot:
            await pilot.click("#btn-new")
            await self.wait_until(
                lambda: isinstance(self.app.screen, TodoEditorModal), "add modal"
            )
            await pilot.press(*"clicked add")
            await pilot.click("#todo-save")
            await self.wait_until(
                lambda: isinstance(self.app.screen, MainScreen), "main screen"
            )
            await self.wait_until(lambda: "clicked add" in self.row_texts(), "new row")
            self.assertEqual(self.store.todos[0].text, "clicked add")

    async def test_edit_todo_title_and_description(self) -> None:
        todo = self.store.add("old title", description="old details")
        async with self.running_app() as pilot:
            await pilot.press("e")
            await self.wait_until(
                lambda: isinstance(self.app.screen, TodoEditorModal), "edit modal"
            )
            self.assertEqual(
                self.app.screen.query_one("#todo-text", Input).value,
                "old title",
            )
            self.assertEqual(
                self.app.screen.query_one("#todo-description", TextArea).text,
                "old details",
            )

            self.app.screen.query_one("#todo-text", Input).value = "new title"
            self.app.screen.query_one("#todo-description", TextArea).text = (
                "new details\nsecond line"
            )
            await pilot.click("#todo-save")
            await self.wait_until(
                lambda: isinstance(self.app.screen, MainScreen), "main screen"
            )
            await self.wait_until(
                lambda: self.store.get(todo.id).text == "new title", "todo edited"
            )

            self.assertEqual(
                self.store.get(todo.id).description,
                "new details\nsecond line",
            )
            self.assertEqual(self.row_texts(), ["new title"])
            self.assertEqual(self.app.selected_id, todo.id)
            reloaded = TodoStore(self.path).todos[0]
            self.assertEqual(reloaded.text, "new title")
            self.assertEqual(reloaded.description, "new details\nsecond line")

    async def test_edit_rejects_an_empty_title_without_closing(self) -> None:
        self.store.add("keep me")
        async with self.running_app() as pilot:
            await pilot.press("e")
            await self.wait_until(
                lambda: isinstance(self.app.screen, TodoEditorModal), "edit modal"
            )
            self.app.screen.query_one("#todo-text", Input).value = "   "
            await pilot.click("#todo-save")
            await pilot.pause()
            self.assertIsInstance(self.app.screen, TodoEditorModal)
            self.assertTrue(self.app.screen.query_one("#todo-error").display)
            self.assertEqual(self.store.todos[0].text, "keep me")

    async def test_edit_rejects_an_overlong_description_without_closing(self) -> None:
        todo = self.store.add("keep me")
        async with self.running_app() as pilot:
            await pilot.press("e")
            await self.wait_until(
                lambda: isinstance(self.app.screen, TodoEditorModal), "edit modal"
            )
            description = self.app.screen.query_one("#todo-description", TextArea)
            description.text = "x" * (MAX_DESCRIPTION_LENGTH + 1)
            await pilot.click("#todo-save")
            await pilot.pause()
            self.assertIsInstance(self.app.screen, TodoEditorModal)
            self.assertTrue(self.app.screen.query_one("#todo-error").display)
            self.assertTrue(description.has_class("-invalid"))
            self.assertEqual(self.store.get(todo.id).description, "")

    async def test_toggle_keeps_selection_and_scrolls_it_into_view(self) -> None:
        todos = [self.store.add(f"item {index}") for index in range(36)]
        async with self.running_app() as pilot:
            for _ in range(20):
                await pilot.press("down")
            await pilot.pause()
            target = todos[20]
            self.assertEqual(self.app.selected_id, target.id)
            item_list = self.app.main_screen.query_one("#todo-list")
            self.assertGreater(item_list.scroll_y, 0)

            await pilot.press("space")
            await self.wait_until(
                lambda: self.store.get(target.id).done, "todo checked"
            )
            await pilot.pause()

            self.assertEqual(self.app.selected_id, target.id)
            selected = self.selected_row()
            self.assertEqual(selected.todo.id, target.id)
            self.assertGreaterEqual(selected.region.y, item_list.region.y)
            self.assertLess(
                selected.region.y, item_list.region.y + item_list.region.height
            )
            # Navigation starts from the moved row's new position.
            await pilot.press("k")
            await pilot.pause()
            self.assertNotEqual(self.app.selected_id, target.id)

    async def test_hiding_a_checked_todo_selects_the_next_row(self) -> None:
        todos = [self.store.add(name) for name in ("alpha", "beta", "gamma", "delta")]
        async with self.running_app() as pilot:
            await pilot.press("h")
            await pilot.pause()
            self.assertFalse(self.app.show_done)
            await pilot.press("down")
            await pilot.pause()
            self.assertEqual(self.app.selected_id, todos[1].id)

            await pilot.press("space")
            await self.wait_until(
                lambda: self.store.get(todos[1].id).done, "beta checked"
            )
            await pilot.pause()

            self.assertEqual(self.app.selected_id, todos[2].id)
            self.assertNotIn("beta", self.row_texts())
            self.assertEqual(self.selected_row().todo.id, todos[2].id)

    async def test_delete_selects_the_neighbour(self) -> None:
        todos = [self.store.add(name) for name in ("alpha", "beta", "gamma")]
        async with self.running_app() as pilot:
            await pilot.press("down")
            await pilot.pause()
            self.assertEqual(self.app.selected_id, todos[1].id)

            await pilot.press("d")
            await self.wait_until(lambda: len(self.store.todos) == 2, "todo deleted")
            await pilot.pause()

            self.assertEqual(self.app.selected_id, todos[2].id)
            self.assertEqual(self.row_texts(), ["alpha", "gamma"])

    async def test_mouse_select_checkbox_and_double_click(self) -> None:
        alpha = self.store.add("alpha")
        beta = self.store.add("beta")
        gamma = self.store.add("gamma")
        async with self.running_app() as pilot:
            beta_row = next(row for row in self.rows() if row.todo.id == beta.id)
            await pilot.click(beta_row, offset=(12, 0))
            await pilot.pause()
            self.assertEqual(self.app.selected_id, beta.id)
            self.assertFalse(self.store.get(beta.id).done)

            beta_row = next(row for row in self.rows() if row.todo.id == beta.id)
            await pilot.click(beta_row, offset=(1, 0))
            await self.wait_until(
                lambda: self.store.get(beta.id).done, "beta checked"
            )
            await pilot.pause()
            self.assertEqual(self.app.selected_id, beta.id)

            gamma_row = next(row for row in self.rows() if row.todo.id == gamma.id)
            await pilot.double_click(gamma_row, offset=(12, 0))
            await self.wait_until(
                lambda: self.store.get(gamma.id).done, "gamma checked"
            )
            await pilot.pause()
            self.assertEqual(self.app.selected_id, gamma.id)
            self.assertFalse(self.store.get(alpha.id).done)

    async def test_tabs_switch_views_with_keyboard_and_mouse(self) -> None:
        inbox = self.store.add("inbox item")
        work = self.store.add("work item", "Work")
        async with self.running_app() as pilot:
            self.assertEqual(sorted(self.row_texts()), ["inbox item", "work item"])

            work_tab = self.app.main_screen.query_one("#view-2", Tab)
            await pilot.click(work_tab, offset=(1, 0))
            await self.wait_until(lambda: self.app.view == "Work", "work view")
            self.assertEqual(self.row_texts(), ["work item"])
            self.assertEqual(
                self.app.main_screen.query_one("#views").active, "view-2"
            )

            await pilot.press("tab")
            await self.wait_until(lambda: self.app.view is None, "all view")
            self.assertEqual(sorted(self.row_texts()), ["inbox item", "work item"])
            await pilot.press("shift+tab")
            await self.wait_until(lambda: self.app.view == "Work", "work view again")
            self.assertEqual(self.app.selected_id, work.id)
            self.assertNotEqual(self.app.selected_id, inbox.id)

    async def test_compact_view_bar_when_tabs_do_not_fit(self) -> None:
        self.store.add("inbox item")
        self.store.add("work item", "Work")
        for group in ("Home", "Errands", "Projects", "Someday"):
            self.store.add_group(group)
        async with self.running_app(size=(24, 6)) as pilot:
            screen = self.app.main_screen
            self.assertTrue(screen.has_class("-viewbar"))
            self.assertFalse(screen.query_one("#views").display)
            self.assertTrue(screen.query_one("#view-bar").display)
            self.assertLessEqual(
                screen.query_one("#view-bar").region.right, screen.size.width
            )
            name = screen.query_one("#view-name")
            self.assertIn("All", str(name.render()))

            await pilot.press("right")
            await self.wait_until(lambda: self.app.view == "Inbox", "inbox view")
            self.assertIn("Inbox", str(name.render()))

            await pilot.click("#view-next")
            await self.wait_until(lambda: self.app.view == "Work", "work view")
            self.assertIn("Work", str(name.render()))

            await pilot.click("#view-prev")
            await self.wait_until(lambda: self.app.view == "Inbox", "inbox again")
            self.assertIn("Inbox", str(name.render()))

    async def test_tabs_are_used_when_every_view_fits(self) -> None:
        for group in ("Work", "Home", "Errands", "Projects", "Someday"):
            self.store.add_group(group)
        async with self.running_app(size=(60, 12)):
            screen = self.app.main_screen
            self.assertFalse(screen.has_class("-viewbar"))
            self.assertTrue(screen.query_one("#views").display)
            self.assertFalse(screen.query_one("#view-bar").display)

    async def test_move_todo_with_group_picker(self) -> None:
        todo = self.store.add("move me")
        self.store.add_group("Work")
        async with self.running_app() as pilot:
            await pilot.press("g")
            await self.wait_until(
                lambda: isinstance(self.app.screen, GroupPickerModal), "group modal"
            )
            options = self.app.screen.query_one("#group-options", OptionList)
            self.assertEqual(options.option_count, 3)  # Inbox + Work + new group
            await pilot.press("d")
            await pilot.press("n")
            await pilot.pause()
            self.assertEqual(len(self.store.todos), 1)
            self.assertIsInstance(self.app.screen, GroupPickerModal)
            await pilot.press("down")
            await pilot.press("enter")
            await self.wait_until(
                lambda: isinstance(self.app.screen, MainScreen), "main screen"
            )
            await self.wait_until(
                lambda: self.store.get(todo.id).group == "Work", "todo moved"
            )
            self.assertEqual(self.app.selected_id, todo.id)

    async def test_delete_group_moves_todos_and_switches_view(self) -> None:
        todo = self.store.add("work item", "Work")
        self.store.add_group("Empty")
        async with self.running_app() as pilot:
            work_tab = self.app.main_screen.query_one("#view-2", Tab)
            await pilot.click(work_tab, offset=(1, 0))
            await self.wait_until(lambda: self.app.view == "Work", "work view")

            await pilot.press("D")
            await self.wait_until(
                lambda: isinstance(self.app.screen, GroupPickerModal),
                "delete group modal",
            )
            options = self.app.screen.query_one("#group-options", OptionList)
            self.assertEqual(options.option_count, 2)  # Work + Empty, no Inbox/new
            option_text = " ".join(
                str(options.get_option_at_index(index).prompt)
                for index in range(options.option_count)
            )
            self.assertNotIn("Inbox", option_text)
            self.assertNotIn("New group", option_text)
            self.assertEqual(options.highlighted, 0)

            await pilot.press("enter")
            await self.wait_until(
                lambda: isinstance(self.app.screen, MainScreen), "main screen"
            )
            await self.wait_until(
                lambda: "Work" not in self.store.groups, "group deleted"
            )
            await pilot.pause()

            self.assertEqual(todo.group, "Inbox")
            self.assertIsNone(self.app.view)
            self.assertEqual(self.store.groups, ["Inbox", "Empty"])
            self.assertEqual(self.app.main_screen.query_one("#views").active, "view-all")
            self.assertEqual(self.row_texts(), ["work item"])
            self.assertEqual(self.app.selected_id, todo.id)
            self.assertIn("Moved 1 todo to Inbox", self.app.message)
            self.assertEqual(TodoStore(self.path).groups, ["Inbox", "Empty"])

    async def test_delete_group_is_unavailable_when_only_inbox_remains(self) -> None:
        async with self.running_app() as pilot:
            await pilot.press("D")
            await pilot.pause()
            self.assertIsInstance(self.app.screen, MainScreen)
            self.assertEqual(self.app.message, "No groups to delete.")

    async def test_move_todo_to_a_new_group_from_picker(self) -> None:
        todo = self.store.add("move me")
        async with self.running_app() as pilot:
            await pilot.press("g")
            await self.wait_until(
                lambda: isinstance(self.app.screen, GroupPickerModal), "group modal"
            )
            options = self.app.screen.query_one("#group-options", OptionList)
            options.highlighted = options.option_count - 1
            await pilot.press("enter")
            await self.wait_until(
                lambda: isinstance(self.app.screen, TextPromptModal), "name prompt"
            )
            await pilot.press(*"New Group")
            await pilot.press("enter")
            await self.wait_until(
                lambda: isinstance(self.app.screen, MainScreen), "main screen"
            )
            await self.wait_until(
                lambda: self.store.get(todo.id).group == "New Group", "todo moved"
            )
            self.assertIn("New Group", self.store.groups)
            self.assertEqual(self.app.main_screen.query_one("#views").tab_count, 3)
            self.assertEqual(self.app.selected_id, todo.id)

    async def test_create_group_then_add_a_todo(self) -> None:
        async with self.running_app() as pilot:
            await pilot.press("G")
            await self.wait_until(
                lambda: isinstance(self.app.screen, TextPromptModal), "group prompt"
            )
            self.assertIn(
                "New group",
                str(self.app.screen.query_one(".dialog-title").render()),
            )
            await pilot.press(*"Errands")
            await pilot.press("enter")
            await self.wait_until(lambda: self.app.view == "Errands", "new group view")
            self.assertIn("Errands", self.store.groups)
            self.assertEqual(
                self.app.main_screen.query_one("#views").active, "view-2"
            )

            await pilot.press("n")
            await self.wait_until(
                lambda: isinstance(self.app.screen, TodoEditorModal), "todo prompt"
            )
            self.assertIn(
                "Errands",
                str(self.app.screen.query_one(".dialog-title").render()),
            )
            await pilot.press(*"pick up parcel")
            await pilot.press("enter")
            await self.wait_until(
                lambda: len(self.store.todos) == 1, "todo added to new group"
            )
            self.assertEqual(self.store.todos[0].group, "Errands")
            self.assertEqual(self.app.view, "Errands")
            self.assertEqual(self.row_texts(), ["pick up parcel"])

    async def test_saved_light_theme_is_applied_on_startup(self) -> None:
        self.store.set_theme("github-light")
        async with self.running_app():
            self.assertEqual(self.app.theme, "github-light")
            self.assertIn("-light-mode", self.app.classes)

    async def test_theme_picker_preview_select_and_cancel(self) -> None:
        async with self.running_app() as pilot:
            self.assertEqual(len(THEME_CHOICES), 25)
            self.assertEqual(THEME_CHOICES[0].id, "default")
            self.assertEqual(self.app.theme, "default")
            for choice in THEME_CHOICES:
                self.assertIn(choice.id, self.app.available_themes)

            await pilot.press("t")
            await self.wait_until(
                lambda: isinstance(self.app.screen, ThemePickerModal), "theme modal"
            )
            options = self.app.screen.query_one("#theme-options", OptionList)
            self.assertEqual(options.option_count, 26)  # 25 themes + transparent toggle
            nord_index = next(
                index
                for index, choice in enumerate(THEME_CHOICES)
                if choice.id == "nord"
            )
            options.highlighted = nord_index + 1
            await self.wait_until(lambda: self.app.theme == "nord", "nord preview")
            await pilot.press("enter")
            await self.wait_until(
                lambda: isinstance(self.app.screen, MainScreen), "main screen"
            )
            await self.wait_until(lambda: self.store.theme == "nord", "nord saved")
            self.assertEqual(self.app.theme, "nord")
            self.assertEqual(TodoStore(self.path).theme, "nord")

            # The toolbar button opens the picker, and Cancel restores the
            # previously saved theme after a live preview.
            await pilot.click("#btn-theme")
            await self.wait_until(
                lambda: isinstance(self.app.screen, ThemePickerModal),
                "theme modal from button",
            )
            options = self.app.screen.query_one("#theme-options", OptionList)
            dracula_index = next(
                index
                for index, choice in enumerate(THEME_CHOICES)
                if choice.id == "dracula"
            )
            options.highlighted = dracula_index + 1
            await self.wait_until(
                lambda: self.app.theme == "dracula", "dracula preview"
            )
            await pilot.click("#theme-cancel")
            await self.wait_until(
                lambda: isinstance(self.app.screen, MainScreen), "main after cancel"
            )
            await self.wait_until(lambda: self.app.theme == "nord", "theme restored")
            self.assertEqual(self.store.theme, "nord")

    async def test_transparent_background_toggle_and_persist(self) -> None:
        async with self.running_app() as pilot:
            self.assertFalse(self.store.transparent)
            self.assertFalse(self.app.transparent_background)
            self.assertFalse(self.app.has_class("-transparent"))
            self.assertIsNone(self.app.ansi_color)

            await pilot.press("t")
            await self.wait_until(
                lambda: isinstance(self.app.screen, ThemePickerModal), "theme modal"
            )
            options = self.app.screen.query_one("#theme-options", OptionList)
            self.assertIn("[ ]", str(options.get_option_at_index(0).prompt))
            options.highlighted = 0
            await pilot.press("enter")
            await self.wait_until(
                lambda: isinstance(self.app.screen, MainScreen), "main after enable"
            )
            await self.wait_until(lambda: self.store.transparent, "transparent saved")
            self.assertTrue(self.app.transparent_background)
            self.assertTrue(self.app.has_class("-transparent"))
            self.assertTrue(self.app.main_screen.has_class("-transparent"))
            self.assertTrue(self.app.ansi_color)
            self.assertEqual(self.app.styles.background.ansi, -1)
            self.assertEqual(self.app.main_screen.styles.background.ansi, -1)
            self.assertTrue(TodoStore(self.path).transparent)

            # Switching themes keeps the transparent setting.
            await pilot.press("t")
            await self.wait_until(
                lambda: isinstance(self.app.screen, ThemePickerModal), "theme modal"
            )
            options = self.app.screen.query_one("#theme-options", OptionList)
            nord_index = next(
                index
                for index, choice in enumerate(THEME_CHOICES)
                if choice.id == "nord"
            )
            options.highlighted = nord_index + 1
            await pilot.press("enter")
            await self.wait_until(
                lambda: isinstance(self.app.screen, MainScreen), "main after theme"
            )
            await self.wait_until(lambda: self.store.theme == "nord", "nord saved")
            self.assertTrue(self.store.transparent)
            self.assertTrue(TodoStore(self.path).transparent)
            self.assertEqual(self.app.styles.background.ansi, -1)

            await pilot.resize_terminal(20, 6)
            await pilot.pause(0.05)
            self.assertEqual(self.app.main_screen.styles.background.ansi, -1)
            await pilot.resize_terminal(80, 24)
            await pilot.pause(0.05)

            await pilot.press("t")
            await self.wait_until(
                lambda: isinstance(self.app.screen, ThemePickerModal), "theme modal"
            )
            options = self.app.screen.query_one("#theme-options", OptionList)
            self.assertIn("[x]", str(options.get_option_at_index(0).prompt))
            options.highlighted = 0
            await pilot.press("enter")
            await self.wait_until(
                lambda: isinstance(self.app.screen, MainScreen), "main after disable"
            )
            await self.wait_until(
                lambda: not self.store.transparent, "transparent disabled"
            )
            self.assertFalse(self.app.transparent_background)
            self.assertFalse(self.app.has_class("-transparent"))
            self.assertFalse(self.app.main_screen.has_class("-transparent"))
            self.assertIsNone(self.app.ansi_color)
            self.assertFalse(TodoStore(self.path).transparent)

    async def test_saved_transparency_is_applied_on_startup(self) -> None:
        self.store.set_appearance("textual-dark", True)
        async with self.running_app():
            self.assertTrue(self.app.transparent_background)
            self.assertTrue(self.app.has_class("-transparent"))
            self.assertTrue(self.app.main_screen.has_class("-transparent"))
            self.assertTrue(self.app.ansi_color)
            self.assertEqual(self.app.styles.background.ansi, -1)

    async def test_tiny_layouts_and_modal_fit(self) -> None:
        for index in range(12):
            self.store.add(f"todo {index}")
        self.store.add_group("Work")
        async with self.running_app() as pilot:
            await pilot.resize_terminal(50, 20)
            await pilot.pause(0.05)
            self.assertIn("-narrow", self.app.screen.classes)
            self.assertTrue(self.app.main_screen.query_one("#btn-theme").display)
            self.assertFalse(self.app.main_screen.query_one("#btn-quit").display)

            await pilot.resize_terminal(60, 20)
            await pilot.pause(0.05)
            self.assertNotIn("-narrow", self.app.screen.classes)
            theme_button = self.app.main_screen.query_one("#btn-theme")
            quit_button = self.app.main_screen.query_one("#btn-quit")
            self.assertTrue(theme_button.display)
            self.assertTrue(quit_button.display)
            self.assertLessEqual(quit_button.region.right, self.app.screen.size.width)

            await pilot.resize_terminal(24, 6)
            await pilot.pause(0.05)
            self.assertIn("-tiny", self.app.screen.classes)
            self.assertFalse(self.app.main_screen.query_one("#app-header").display)
            self.assertFalse(self.app.main_screen.query_one("#status").display)
            self.assertGreaterEqual(
                self.app.main_screen.query_one("#todo-list").size.height, 2
            )
            labels = {
                button.id: str(button.label)
                for button in self.app.main_screen.query(ActionButton)
                if button.display
            }
            self.assertEqual(labels["btn-new"], "+")
            self.assertEqual(labels["btn-toggle"], "ok")
            self.assertEqual(labels["btn-edit"], "e")
            self.assertEqual(labels["btn-help"], "?")
            self.assertNotIn("btn-hide", labels)
            self.assertNotIn("btn-theme", labels)

            await pilot.resize_terminal(20, 4)
            await pilot.pause(0.05)
            self.assertNotIn("-micro", self.app.screen.classes)
            self.assertTrue(self.app.main_screen.query_one("#actions").display)
            self.assertGreaterEqual(
                self.app.main_screen.query_one("#todo-list").size.height, 1
            )

            await pilot.press("n")
            await self.wait_until(
                lambda: isinstance(self.app.screen, TodoEditorModal),
                "20x4 todo editor",
            )
            dialog = self.app.screen.query_one(".todo-dialog")
            self.assertTrue(self.app.screen.query_one(".dialog-title").display)
            for widget in (
                self.app.screen.query_one(Input),
                self.app.screen.query_one(TextArea),
                self.app.screen.query_one("#todo-save"),
                self.app.screen.query_one("#todo-cancel"),
            ):
                self.assert_inside(widget, dialog)

            # An inline error must not push the actions outside the dialog.
            self.app.screen.query_one(Input).value = "   "
            await pilot.press("enter")
            await pilot.pause()
            self.assertFalse(self.app.screen.query_one(".dialog-title").display)
            self.assertTrue(self.app.screen.query_one("#todo-error").display)
            self.assertTrue(self.app.screen.query_one(Input).has_class("-invalid"))
            for widget in (
                self.app.screen.query_one(Input),
                self.app.screen.query_one(TextArea),
                self.app.screen.query_one("#todo-error"),
                self.app.screen.query_one("#todo-save"),
                self.app.screen.query_one("#todo-cancel"),
            ):
                self.assert_inside(widget, dialog)

            # Editing the field clears the error and restores the title row.
            await pilot.press("x")
            await pilot.pause()
            self.assertTrue(self.app.screen.query_one(".dialog-title").display)
            self.assertFalse(self.app.screen.query_one("#todo-error").display)
            self.assertFalse(self.app.screen.query_one(Input).has_class("-invalid"))
            await pilot.press("escape")
            await self.wait_until(
                lambda: isinstance(self.app.screen, MainScreen),
                "main after 20x4 editor",
            )

            await pilot.resize_terminal(20, 3)
            await pilot.pause(0.05)
            self.assertIn("-micro", self.app.screen.classes)
            self.assertFalse(self.app.main_screen.query_one("#actions").display)
            self.assertGreaterEqual(
                self.app.main_screen.query_one("#todo-list").size.height, 1
            )

            await pilot.press("n")
            await self.wait_until(
                lambda: isinstance(self.app.screen, TodoEditorModal),
                "20x3 todo editor",
            )
            dialog = self.app.screen.query_one(".todo-dialog")
            self.assertLessEqual(dialog.region.height, 3)
            self.assertFalse(self.app.screen.query_one(".dialog-title").display)
            for widget in (
                self.app.screen.query_one(Input),
                self.app.screen.query_one(TextArea),
                self.app.screen.query_one("#todo-save"),
                self.app.screen.query_one("#todo-cancel"),
            ):
                self.assert_inside(widget, dialog)

            # Micro layouts use a notification instead of an inline error row.
            self.app.screen.query_one(Input).value = "   "
            await pilot.press("enter")
            await pilot.pause()
            self.assertFalse(self.app.screen.query_one("#todo-error").display)
            self.assertTrue(self.app.screen.query_one(Input).has_class("-invalid"))
            for widget in (
                self.app.screen.query_one(Input),
                self.app.screen.query_one(TextArea),
                self.app.screen.query_one("#todo-save"),
                self.app.screen.query_one("#todo-cancel"),
            ):
                self.assert_inside(widget, dialog)
            await pilot.press("escape")
            await self.wait_until(
                lambda: isinstance(self.app.screen, MainScreen),
                "main after 20x3 editor",
            )

            await pilot.press("D")
            await self.wait_until(
                lambda: isinstance(self.app.screen, GroupPickerModal),
                "20x3 delete group modal",
            )
            group_dialog = self.app.screen.query_one(".group-dialog")
            group_options = self.app.screen.query_one("#group-options", OptionList)
            group_cancel = self.app.screen.query_one("#group-cancel")
            for widget in (group_options, group_cancel):
                self.assert_inside(widget, group_dialog)
            await pilot.press("escape")
            await self.wait_until(
                lambda: isinstance(self.app.screen, MainScreen),
                "main after 20x3 group modal",
            )

            await pilot.resize_terminal(20, 2)
            await pilot.pause(0.05)
            self.assertIn("-nano", self.app.screen.classes)
            self.assertFalse(self.app.main_screen.query_one("#views").display)
            self.assertGreaterEqual(
                self.app.main_screen.query_one("#todo-list").size.height, 2
            )

            await pilot.press("n")
            await self.wait_until(
                lambda: isinstance(self.app.screen, TodoEditorModal),
                "20x2 todo editor",
            )
            dialog = self.app.screen.query_one(".todo-dialog")
            self.assertLessEqual(dialog.region.height, 2)
            self.assertFalse(self.app.screen.query_one(TextArea).display)
            for widget in (
                self.app.screen.query_one(Input),
                self.app.screen.query_one("#todo-save"),
                self.app.screen.query_one("#todo-cancel"),
            ):
                self.assert_inside(widget, dialog)
            await pilot.press("escape")
            await self.wait_until(
                lambda: isinstance(self.app.screen, MainScreen),
                "main after 20x2 editor",
            )

            await pilot.press("D")
            await self.wait_until(
                lambda: isinstance(self.app.screen, GroupPickerModal),
                "20x2 delete group modal",
            )
            group_dialog = self.app.screen.query_one(".group-dialog")
            for widget in (
                self.app.screen.query_one("#group-options", OptionList),
                self.app.screen.query_one("#group-cancel"),
            ):
                self.assert_inside(widget, group_dialog)
            await pilot.press("escape")
            await self.wait_until(
                lambda: isinstance(self.app.screen, MainScreen),
                "main after 20x2 group modal",
            )

            await pilot.resize_terminal(20, 6)
            await pilot.pause(0.05)
            await pilot.press("n")
            await self.wait_until(
                lambda: isinstance(self.app.screen, TodoEditorModal), "tiny prompt"
            )
            dialog = self.app.screen.query_one(".todo-dialog")
            self.assertLessEqual(dialog.region.width, 20)
            self.assertLessEqual(dialog.region.height, 6)
            self.assertTrue(self.app.screen.query_one(Input).display)
            self.assertTrue(self.app.screen.query_one(TextArea).display)
            await pilot.press("escape")
            await self.wait_until(
                lambda: isinstance(self.app.screen, MainScreen), "main after escape"
            )

            await pilot.press("t")
            await self.wait_until(
                lambda: isinstance(self.app.screen, ThemePickerModal),
                "tiny theme modal",
            )
            theme_dialog = self.app.screen.query_one(".theme-dialog")
            self.assertLessEqual(theme_dialog.region.width, 20)
            self.assertLessEqual(theme_dialog.region.height, 6)
            theme_options = self.app.screen.query_one("#theme-options", OptionList)
            self.assertEqual(theme_options.option_count, 26)
            self.assertIn("Term bg", str(theme_options.get_option_at_index(0).prompt))

            await pilot.press("escape")
            await self.wait_until(
                lambda: isinstance(self.app.screen, MainScreen),
                "main after tiny theme",
            )
            await pilot.press("f1")
            await self.wait_until(
                lambda: isinstance(self.app.screen, HelpModal), "tiny help modal"
            )
            help_dialog = self.app.screen.query_one(".help-dialog")
            self.assertLessEqual(help_dialog.region.width, 20)
            self.assertLessEqual(help_dialog.region.height, 6)
            help_list = self.app.screen.query_one("#help-list", VerticalScroll)
            self.assertGreater(help_list.max_scroll_y, 0)
            await pilot.press("pagedown")
            await pilot.pause()
            self.assertGreater(help_list.scroll_y, 0)
            await pilot.press("escape")
            await self.wait_until(
                lambda: isinstance(self.app.screen, MainScreen),
                "main after tiny help",
            )


if __name__ == "__main__":
    unittest.main()
