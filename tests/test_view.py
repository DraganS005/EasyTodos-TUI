from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from easytodos.model import TodoStore
from easytodos.view import build_rows, sort_todos, visible_todo_ids


class ViewTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = TodoStore(Path(self.tmp.name) / "todos.json")
        self.work_a = self.store.add("Work A", "Work")
        self.work_b = self.store.add("Work B", "Work")
        self.home = self.store.add("Home A", "Home")

    def kinds(self, rows):
        return [row.kind for row in rows]


class BuildRowsTests(ViewTestCase):
    def test_all_groups_are_shown_with_headers(self) -> None:
        rows = build_rows(self.store)
        self.assertEqual(
            self.kinds(rows),
            ["group", "todo", "todo", "group", "todo"],
        )
        self.assertEqual(rows[0].group, "Work")
        self.assertEqual(rows[3].group, "Home")
        self.assertEqual(rows[0].total, 2)

    def test_open_todos_sort_before_done_ones(self) -> None:
        self.store.toggle(self.work_a.id)
        rows = build_rows(self.store)
        work_todos = [row.todo for row in rows if row.group == "Work" and row.todo]
        self.assertEqual([todo.text for todo in work_todos], ["Work B", "Work A"])

    def test_group_header_counts_include_hidden_done_todos(self) -> None:
        self.store.toggle(self.work_a.id)
        rows = build_rows(self.store, show_done=False)
        header = rows[0]
        self.assertEqual(header.kind, "group")
        self.assertEqual((header.done, header.total), (1, 2))
        todos = [row.todo for row in rows if row.todo]
        self.assertEqual([todo.text for todo in todos], ["Work B", "Home A"])

    def test_empty_groups_are_skipped(self) -> None:
        self.store.add_group("Empty")
        rows = build_rows(self.store)
        self.assertNotIn("Empty", [row.group for row in rows])

    def test_group_view_filters_to_one_group(self) -> None:
        rows = build_rows(self.store, view="Work")
        self.assertEqual([row.group for row in rows], ["Work", "Work", "Work"])
        self.assertEqual(visible_todo_ids(rows), [self.work_a.id, self.work_b.id])

    def test_hiding_done_can_empty_a_group_view(self) -> None:
        self.store.toggle(self.work_a.id)
        rows = build_rows(self.store, view="Work", show_done=False)
        self.assertEqual(self.kinds(rows), ["group", "todo"])

        self.store.toggle(self.work_b.id)
        rows = build_rows(self.store, view="Work", show_done=False)
        self.assertEqual(rows, [])

    def test_unknown_group_view_is_empty(self) -> None:
        self.assertEqual(build_rows(self.store, view="Nope"), [])

    def test_sorting_is_stable_for_same_timestamps(self) -> None:
        self.work_a.created = self.work_b.created = 100.0
        self.assertEqual(
            [todo.id for todo in sort_todos([self.work_b, self.work_a])],
            [self.work_b.id, self.work_a.id],
        )
        self.assertEqual(
            [todo.id for todo in sort_todos([self.work_a, self.work_b])],
            [self.work_a.id, self.work_b.id],
        )


if __name__ == "__main__":
    unittest.main()
