"""Build the flat, displayable rows for the todo list."""

from __future__ import annotations

from dataclasses import dataclass

from .model import Todo, TodoStore


@dataclass(frozen=True)
class Row:
    """One line in the list: a group header or a todo."""

    kind: str  # "group" or "todo"
    group: str = ""
    todo: Todo | None = None
    done: int = 0
    total: int = 0


def sort_todos(todos: list[Todo]) -> list[Todo]:
    """Open todos first, oldest first; completed ones below."""
    return sorted(todos, key=lambda todo: (todo.done, todo.created))


def build_rows(
    store: TodoStore,
    view: str | None = None,
    show_done: bool = True,
) -> list[Row]:
    """Group todos for display.

    ``view`` is ``None`` for all groups, or a group name. Group headers include
    completed todos in their counts even when completed todos are hidden.
    Empty groups are skipped so the all-groups view stays tidy.
    """
    groups = store.groups if view is None else [view]
    rows: list[Row] = []

    for group in groups:
        todos = [todo for todo in store.todos if todo.group == group]
        if not todos:
            continue
        visible = [todo for todo in todos if show_done or not todo.done]
        if not visible:
            continue
        rows.append(
            Row(
                kind="group",
                group=group,
                done=sum(todo.done for todo in todos),
                total=len(todos),
            )
        )
        rows.extend(Row(kind="todo", group=group, todo=todo) for todo in sort_todos(visible))

    return rows


def visible_todo_ids(rows: list[Row]) -> list[str]:
    return [row.todo.id for row in rows if row.kind == "todo" and row.todo is not None]
