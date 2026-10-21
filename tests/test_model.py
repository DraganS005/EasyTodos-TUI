from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from todo_tui.model import (
    DEFAULT_GROUP,
    DEFAULT_THEME,
    MAX_GROUP_LENGTH,
    StoreError,
    TodoStore,
)


class StoreTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "data" / "todos.json"
        self.store = TodoStore(self.path)

    def reload(self) -> TodoStore:
        return TodoStore(self.path)


class AddTests(StoreTestCase):
    def test_default_group_is_inbox(self) -> None:
        todo = self.store.add("Buy milk")
        self.assertEqual(todo.group, DEFAULT_GROUP)
        self.assertFalse(todo.done)
        self.assertEqual(self.store.todos, [todo])

    def test_text_is_trimmed(self) -> None:
        todo = self.store.add("  Write report  ", "Work")
        self.assertEqual(todo.text, "Write report")
        self.assertIn("Work", self.store.groups)

    def test_empty_text_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            self.store.add("   ")
        self.assertEqual(self.store.todos, [])

    def test_unknown_group_is_created(self) -> None:
        self.store.add("Call plumber", "Errands")
        self.assertEqual(self.store.groups, [DEFAULT_GROUP, "Errands"])
        self.assertEqual(self.reload().groups, [DEFAULT_GROUP, "Errands"])

    def test_persists_across_reload(self) -> None:
        todo = self.store.add("Ship it", "Work")
        loaded = self.reload()
        self.assertEqual(len(loaded.todos), 1)
        self.assertEqual(loaded.todos[0].id, todo.id)
        self.assertEqual(loaded.todos[0].text, "Ship it")
        self.assertEqual(loaded.todos[0].group, "Work")
        self.assertEqual(loaded.groups, ["Inbox", "Work"])

    def test_save_replaces_file_without_leaving_temp_file(self) -> None:
        self.store.add("One")
        self.store.add("Two")
        self.assertFalse(self.path.with_name(self.path.name + ".tmp").exists())
        data = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertEqual(data["version"], 1)
        self.assertEqual(len(data["todos"]), 2)


class GroupTests(StoreTestCase):
    def test_group_names_are_normalized_and_deduplicated(self) -> None:
        first = self.store.add_group("  Deep   Work ")
        second = self.store.add_group("deep work")
        self.assertEqual(first, "Deep Work")
        self.assertEqual(second, "Deep Work")
        self.assertEqual(self.store.groups, [DEFAULT_GROUP, "Deep Work"])

    def test_empty_group_name_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            self.store.add_group("   ")

    def test_overlong_group_name_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            self.store.add_group("x" * (MAX_GROUP_LENGTH + 1))

    def test_move_creates_target_group(self) -> None:
        todo = self.store.add("Fix bike", "Inbox")
        moved = self.store.move(todo.id, "Errands")
        self.assertIsNotNone(moved)
        self.assertEqual(moved.group, "Errands")
        self.assertIn("Errands", self.store.groups)
        self.assertEqual(self.reload().todos[0].group, "Errands")

    def test_inbox_spelling_is_normalized_on_reload(self) -> None:
        self.store.groups = ["Work", "Inbox", "Home"]
        self.store.save()
        self.assertEqual(self.reload().groups, ["Work", "Inbox", "Home"])

    def test_missing_inbox_is_added_on_reload(self) -> None:
        self.path.parent.mkdir(parents=True)
        self.path.write_text(
            json.dumps({"version": 1, "groups": ["Work"], "todos": []}),
            encoding="utf-8",
        )
        self.assertEqual(self.reload().groups, ["Inbox", "Work"])


class ThemeTests(StoreTestCase):
    def test_default_theme_is_saved_and_reloaded(self) -> None:
        self.store.add("One")
        data = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertEqual(data["theme"], DEFAULT_THEME)
        self.assertFalse(data["transparent"])
        self.assertEqual(self.reload().theme, DEFAULT_THEME)
        self.assertFalse(self.reload().transparent)

    def test_set_theme_is_persisted(self) -> None:
        self.store.set_theme("nord")
        self.assertEqual(self.store.theme, "nord")
        self.assertEqual(self.reload().theme, "nord")

    def test_missing_theme_uses_default(self) -> None:
        self.path.parent.mkdir(parents=True)
        self.path.write_text(
            json.dumps({"version": 1, "groups": ["Inbox"], "todos": []}),
            encoding="utf-8",
        )
        self.assertEqual(self.reload().theme, DEFAULT_THEME)
        self.assertFalse(self.reload().transparent)

    def test_transparency_is_persisted(self) -> None:
        self.store.set_appearance("nord", True)
        self.assertEqual((self.store.theme, self.store.transparent), ("nord", True))
        loaded = self.reload()
        self.assertEqual((loaded.theme, loaded.transparent), ("nord", True))

    def test_set_theme_preserves_transparency(self) -> None:
        self.store.set_appearance("nord", True)
        self.store.set_theme("dracula")
        loaded = self.reload()
        self.assertEqual((loaded.theme, loaded.transparent), ("dracula", True))

    def test_invalid_transparency_is_rejected(self) -> None:
        self.path.parent.mkdir(parents=True)
        self.path.write_text(
            json.dumps(
                {
                    "version": 1,
                    "theme": "textual-dark",
                    "transparent": "yes",
                    "groups": ["Inbox"],
                    "todos": [],
                }
            ),
            encoding="utf-8",
        )
        with self.assertRaises(StoreError):
            TodoStore(self.path)

    def test_invalid_theme_is_rejected(self) -> None:
        self.path.parent.mkdir(parents=True)
        self.path.write_text(
            json.dumps(
                {"version": 1, "theme": 42, "groups": ["Inbox"], "todos": []}
            ),
            encoding="utf-8",
        )
        with self.assertRaises(StoreError):
            TodoStore(self.path)

    def test_empty_theme_name_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            self.store.set_theme("   ")

    def test_non_boolean_transparency_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            self.store.set_appearance("nord", "yes")  # type: ignore[arg-type]


class ToggleAndDeleteTests(StoreTestCase):
    def test_toggle_marks_done_and_records_time(self) -> None:
        todo = self.store.add("Water plants")
        updated = self.store.toggle(todo.id)
        self.assertTrue(updated.done)
        self.assertIsNotNone(updated.completed_at)
        self.assertEqual(self.store.open_count, 0)
        self.assertEqual(self.store.done_count, 1)

        reopened = self.store.toggle(todo.id)
        self.assertFalse(reopened.done)
        self.assertIsNone(reopened.completed_at)

    def test_toggle_missing_todo_is_a_noop(self) -> None:
        self.assertIsNone(self.store.toggle("missing"))
        self.assertEqual(self.store.todos, [])

    def test_delete_removes_and_persists(self) -> None:
        todo = self.store.add("Throw away")
        removed = self.store.delete(todo.id)
        self.assertEqual(removed.id, todo.id)
        self.assertEqual(self.store.todos, [])
        self.assertEqual(self.reload().todos, [])

    def test_delete_missing_todo_is_a_noop(self) -> None:
        self.assertIsNone(self.store.delete("missing"))


class LoadTests(StoreTestCase):
    def test_missing_file_starts_empty(self) -> None:
        self.assertFalse(self.path.exists())
        self.assertEqual(self.store.groups, [DEFAULT_GROUP])
        self.assertEqual(self.store.todos, [])
        self.assertFalse(self.path.exists())

    def test_invalid_json_raises_store_error(self) -> None:
        self.path.parent.mkdir(parents=True)
        self.path.write_text("{not json", encoding="utf-8")
        with self.assertRaises(StoreError) as caught:
            TodoStore(self.path)
        self.assertIn("not valid JSON", str(caught.exception))

    def test_unsupported_version_raises_store_error(self) -> None:
        self.path.parent.mkdir(parents=True)
        self.path.write_text(
            json.dumps({"version": 99, "groups": [], "todos": []}),
            encoding="utf-8",
        )
        with self.assertRaises(StoreError):
            TodoStore(self.path)

    def test_invalid_todo_raises_store_error(self) -> None:
        self.path.parent.mkdir(parents=True)
        self.path.write_text(
            json.dumps(
                {
                    "version": 1,
                    "groups": ["Inbox"],
                    "todos": [{"text": ""}],
                }
            ),
            encoding="utf-8",
        )
        with self.assertRaises(StoreError) as caught:
            TodoStore(self.path)
        self.assertIn("todo #1", str(caught.exception))

    def test_todo_referencing_unknown_group_creates_group(self) -> None:
        self.path.parent.mkdir(parents=True)
        self.path.write_text(
            json.dumps(
                {
                    "version": 1,
                    "groups": ["Inbox"],
                    "todos": [
                        {
                            "id": "abc",
                            "text": "Read book",
                            "group": "Learning",
                            "done": False,
                            "created": 123.0,
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        loaded = TodoStore(self.path)
        self.assertIn("Learning", loaded.groups)
        self.assertEqual(loaded.todos[0].group, "Learning")

    def test_groups_are_deduplicated_case_insensitively_on_load(self) -> None:
        self.path.parent.mkdir(parents=True)
        self.path.write_text(
            json.dumps(
                {
                    "version": 1,
                    "groups": ["inbox", "Work", "WORK"],
                    "todos": [],
                }
            ),
            encoding="utf-8",
        )
        loaded = TodoStore(self.path)
        self.assertEqual(loaded.groups, ["Inbox", "Work"])

    def test_duplicate_todo_ids_are_regenerated(self) -> None:
        self.path.parent.mkdir(parents=True)
        todo = {
            "id": "same",
            "text": "One",
            "group": "Inbox",
            "done": False,
            "created": 1.0,
        }
        self.path.write_text(
            json.dumps(
                {"version": 1, "groups": ["Inbox"], "todos": [todo, dict(todo, text="Two")]}
            ),
            encoding="utf-8",
        )
        loaded = TodoStore(self.path)
        self.assertEqual(len({item.id for item in loaded.todos}), 2)

    def test_done_todo_without_completion_time_gets_one(self) -> None:
        self.path.parent.mkdir(parents=True)
        self.path.write_text(
            json.dumps(
                {
                    "version": 1,
                    "groups": ["Inbox"],
                    "todos": [
                        {
                            "id": "abc",
                            "text": "Done thing",
                            "group": "Inbox",
                            "done": True,
                            "created": 50.0,
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        loaded = TodoStore(self.path)
        self.assertEqual(loaded.todos[0].completed_at, 50.0)


class DefaultPathTests(unittest.TestCase):
    def test_env_file_override(self) -> None:
        with mock.patch.dict(
            os.environ, {"TODO_TUI_FILE": "~/todos.json"}, clear=True
        ):
            self.assertEqual(
                TodoStore.default_path(),
                Path.home() / "todos.json",
            )

    def test_xdg_data_home(self) -> None:
        with mock.patch.dict(
            os.environ, {"XDG_DATA_HOME": "/tmp/custom-data"}, clear=True
        ):
            self.assertEqual(
                TodoStore.default_path(),
                Path("/tmp/custom-data/todo-tui/todos.json"),
            )


if __name__ == "__main__":
    unittest.main()
