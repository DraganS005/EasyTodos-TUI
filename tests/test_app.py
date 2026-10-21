from __future__ import annotations

import asyncio
import tempfile
import time
import unittest
from contextlib import asynccontextmanager
from pathlib import Path

from textual.widgets import Input, OptionList, Tab

from easytodos.model import TodoStore
from easytodos.themes import THEME_CHOICES
from easytodos.ui import TodoApp
from easytodos.widgets import (
    ActionButton,
    GroupPickerModal,
    MainScreen,
    TextPromptModal,
    ThemePickerModal,
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

    async def test_add_from_keyboard_and_persist(self) -> None:
        async with self.running_app() as pilot:
            await pilot.press("n")
            await self.wait_until(
                lambda: isinstance(self.app.screen, TextPromptModal), "add modal"
            )
            await pilot.press(*"new item")
            await pilot.press("enter")
            await self.wait_until(
                lambda: isinstance(self.app.screen, MainScreen), "main screen"
            )
            await self.wait_until(lambda: "new item" in self.row_texts(), "new row")

            saved = self.store.todos[-1]
            self.assertEqual(saved.text, "new item")
            self.assertEqual(self.app.selected_id, saved.id)
            reloaded = TodoStore(self.path)
            self.assertEqual([todo.text for todo in reloaded.todos], ["new item"])

    async def test_add_from_mouse_toolbar_and_save_button(self) -> None:
        async with self.running_app() as pilot:
            await pilot.click("#btn-new")
            await self.wait_until(
                lambda: isinstance(self.app.screen, TextPromptModal), "add modal"
            )
            await pilot.press(*"clicked add")
            await pilot.click("#prompt-save")
            await self.wait_until(
                lambda: isinstance(self.app.screen, MainScreen), "main screen"
            )
            await self.wait_until(lambda: "clicked add" in self.row_texts(), "new row")
            self.assertEqual(self.store.todos[0].text, "clicked add")

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
                lambda: isinstance(self.app.screen, TextPromptModal), "todo prompt"
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
            self.assertFalse(self.app.main_screen.query_one("#help").display)
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
            self.assertNotIn("btn-hide", labels)
            self.assertNotIn("btn-theme", labels)

            await pilot.resize_terminal(20, 4)
            await pilot.pause(0.05)
            self.assertNotIn("-micro", self.app.screen.classes)
            self.assertTrue(self.app.main_screen.query_one("#actions").display)
            self.assertGreaterEqual(
                self.app.main_screen.query_one("#todo-list").size.height, 1
            )

            await pilot.resize_terminal(20, 3)
            await pilot.pause(0.05)
            self.assertIn("-micro", self.app.screen.classes)
            self.assertFalse(self.app.main_screen.query_one("#actions").display)
            self.assertGreaterEqual(
                self.app.main_screen.query_one("#todo-list").size.height, 1
            )

            await pilot.resize_terminal(20, 6)
            await pilot.pause(0.05)
            await pilot.press("n")
            await self.wait_until(
                lambda: isinstance(self.app.screen, TextPromptModal), "tiny prompt"
            )
            dialog = self.app.screen.query_one(".dialog")
            self.assertLessEqual(dialog.region.width, 20)
            self.assertLessEqual(dialog.region.height, 6)
            self.assertTrue(self.app.screen.query_one(Input).display)
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


if __name__ == "__main__":
    unittest.main()
