"""Data model and JSON persistence for the todo app."""

from __future__ import annotations

import json
import os
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

DEFAULT_GROUP = "Inbox"
DEFAULT_THEME = "textual-dark"
DATA_VERSION = 1
MAX_TEXT_LENGTH = 500
MAX_GROUP_LENGTH = 40


class StoreError(Exception):
    """Raised when the todo file cannot be read or written."""


def _clean_group(name: str) -> str:
    if not isinstance(name, str):
        raise ValueError("Group name must be text.")
    name = " ".join(name.split())
    if not name:
        raise ValueError("Group name cannot be empty.")
    if len(name) > MAX_GROUP_LENGTH:
        raise ValueError(f"Group names are limited to {MAX_GROUP_LENGTH} characters.")
    if any(not char.isprintable() for char in name):
        raise ValueError("Group name contains unsupported characters.")
    return name


@dataclass
class Todo:
    id: str
    text: str
    group: str = DEFAULT_GROUP
    done: bool = False
    created: float = field(default_factory=time.time)
    completed_at: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "text": self.text,
            "group": self.group,
            "done": self.done,
            "created": self.created,
            "completed_at": self.completed_at,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "Todo":
        if not isinstance(raw, dict):
            raise ValueError("expected an object")
        text = raw.get("text")
        if not isinstance(text, str) or not text.strip():
            raise ValueError("text must be a non-empty string")
        text = text.strip()
        if len(text) > MAX_TEXT_LENGTH:
            raise ValueError(f"text is longer than {MAX_TEXT_LENGTH} characters")

        group = raw.get("group", DEFAULT_GROUP)
        if not isinstance(group, str):
            raise ValueError("group must be a string")

        todo_id = raw.get("id")
        if not isinstance(todo_id, str) or not todo_id:
            todo_id = uuid.uuid4().hex[:12]

        done = raw.get("done", False)
        if not isinstance(done, bool):
            raise ValueError("done must be true or false")

        created = raw.get("created", time.time())
        if isinstance(created, bool) or not isinstance(created, (int, float)):
            raise ValueError("created must be a number")

        completed_at = raw.get("completed_at")
        if completed_at is not None and (
            isinstance(completed_at, bool) or not isinstance(completed_at, (int, float))
        ):
            raise ValueError("completed_at must be a number or null")

        return cls(
            id=todo_id,
            text=text,
            group=group,
            done=done,
            created=float(created),
            completed_at=float(completed_at) if completed_at is not None else None,
        )


class TodoStore:
    """A list of todos, grouped by name and persisted to a JSON file."""

    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path) if path is not None else self.default_path()
        self.groups: list[str] = [DEFAULT_GROUP]
        self.todos: list[Todo] = []
        self.theme: str = DEFAULT_THEME
        self.transparent: bool = False
        self.load()

    @staticmethod
    def default_path() -> Path:
        override = os.environ.get("TODO_TUI_FILE")
        if override:
            return Path(override).expanduser()
        base = os.environ.get("XDG_DATA_HOME")
        root = Path(base).expanduser() if base else Path.home() / ".local" / "share"
        return root / "todo-tui" / "todos.json"

    # -- reading and writing -------------------------------------------------

    def load(self) -> None:
        self.groups = [DEFAULT_GROUP]
        self.todos = []
        self.theme = DEFAULT_THEME
        self.transparent = False

        try:
            raw = self.path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return
        except OSError as exc:
            raise StoreError(f"could not read {self.path}: {exc.strerror or exc}") from exc

        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise StoreError(
                f"{self.path} is not valid JSON "
                f"(line {exc.lineno}, column {exc.colno})"
            ) from exc

        if not isinstance(data, dict):
            raise StoreError(f"{self.path} does not contain a todo list")

        version = data.get("version", DATA_VERSION)
        if version != DATA_VERSION:
            raise StoreError(
                f"{self.path} uses unsupported data version {version!r} "
                f"(expected {DATA_VERSION})"
            )

        theme = data.get("theme", DEFAULT_THEME)
        if not isinstance(theme, str) or not theme.strip():
            raise StoreError(f"{self.path}: 'theme' must be a non-empty string")
        theme = theme.strip()

        transparent = data.get("transparent", False)
        if not isinstance(transparent, bool):
            raise StoreError(f"{self.path}: 'transparent' must be true or false")

        raw_groups = data.get("groups", [])
        if not isinstance(raw_groups, list):
            raise StoreError(f"{self.path}: 'groups' must be a list")

        groups: list[str] = []
        seen: set[str] = set()
        for entry in raw_groups:
            if not isinstance(entry, str):
                raise StoreError(f"{self.path}: every group must be a string")
            try:
                name = _clean_group(entry)
            except ValueError as exc:
                raise StoreError(f"{self.path}: {exc}") from exc
            key = name.casefold()
            if key in seen:
                continue
            seen.add(key)
            groups.append(name)

        # "Inbox" is always the fallback group, spelled consistently.
        inbox_index = next(
            (i for i, name in enumerate(groups) if name.casefold() == DEFAULT_GROUP.casefold()),
            None,
        )
        if inbox_index is None:
            groups.insert(0, DEFAULT_GROUP)
        else:
            groups[inbox_index] = DEFAULT_GROUP

        raw_todos = data.get("todos", [])
        if not isinstance(raw_todos, list):
            raise StoreError(f"{self.path}: 'todos' must be a list")

        todos: list[Todo] = []
        used_ids: set[str] = set()
        for index, entry in enumerate(raw_todos, start=1):
            try:
                todo = Todo.from_dict(entry)
            except ValueError as exc:
                raise StoreError(f"{self.path}: todo #{index}: {exc}") from exc

            group = todo.group.strip() or DEFAULT_GROUP
            canonical = next(
                (name for name in groups if name.casefold() == group.casefold()), None
            )
            if canonical is None:
                try:
                    canonical = _clean_group(group)
                except ValueError as exc:
                    raise StoreError(f"{self.path}: todo #{index}: {exc}") from exc
                groups.append(canonical)

            todo.group = canonical
            if todo.done and todo.completed_at is None:
                todo.completed_at = todo.created
            elif not todo.done:
                todo.completed_at = None

            if todo.id in used_ids:
                todo.id = uuid.uuid4().hex[:12]
            used_ids.add(todo.id)
            todos.append(todo)

        self.groups = groups
        self.todos = todos
        self.theme = theme
        self.transparent = transparent

    def save(self) -> None:
        payload = {
            "version": DATA_VERSION,
            "theme": self.theme,
            "transparent": self.transparent,
            "groups": self.groups,
            "todos": [todo.to_dict() for todo in self.todos],
        }
        tmp = self.path.with_name(self.path.name + ".tmp")
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp.write_text(
                json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            os.replace(tmp, self.path)
        except OSError as exc:
            try:
                tmp.unlink(missing_ok=True)
            except OSError:
                pass
            raise StoreError(f"could not save {self.path}: {exc.strerror or exc}") from exc

    # -- queries -------------------------------------------------------------

    def get(self, todo_id: str | None) -> Todo | None:
        if todo_id is None:
            return None
        return next((todo for todo in self.todos if todo.id == todo_id), None)

    def find_group(self, name: str) -> str | None:
        key = name.casefold()
        return next((group for group in self.groups if group.casefold() == key), None)

    @property
    def open_count(self) -> int:
        return sum(not todo.done for todo in self.todos)

    @property
    def done_count(self) -> int:
        return sum(todo.done for todo in self.todos)

    # -- mutations -----------------------------------------------------------

    def add(self, text: str, group: str | None = None) -> Todo:
        text = text.strip()
        if not text:
            raise ValueError("Todo text cannot be empty.")
        if len(text) > MAX_TEXT_LENGTH:
            raise ValueError(f"Todo text is limited to {MAX_TEXT_LENGTH} characters.")

        todo = Todo(
            id=uuid.uuid4().hex[:12],
            text=text,
            group=self._ensure_group(group or DEFAULT_GROUP),
        )
        self.todos.append(todo)
        self.save()
        return todo

    def add_group(self, name: str) -> str:
        clean = _clean_group(name)
        existing = self.find_group(clean)
        if existing is not None:
            return existing
        self.groups.append(clean)
        self.save()
        return clean

    def set_appearance(self, theme: str, transparent: bool) -> tuple[str, bool]:
        """Persist the selected theme and transparent-background setting."""
        if not isinstance(theme, str) or not theme.strip():
            raise ValueError("Theme name cannot be empty.")
        if not isinstance(transparent, bool):
            raise ValueError("Transparent background must be true or false.")
        clean = theme.strip()
        if clean == self.theme and transparent == self.transparent:
            return self.theme, self.transparent
        previous_theme = self.theme
        previous_transparent = self.transparent
        self.theme = clean
        self.transparent = transparent
        try:
            self.save()
        except StoreError:
            self.theme = previous_theme
            self.transparent = previous_transparent
            raise
        return self.theme, self.transparent

    def set_theme(self, name: str) -> str:
        """Persist the selected color theme name, preserving transparency."""
        theme, _transparent = self.set_appearance(name, self.transparent)
        return theme

    def toggle(self, todo_id: str) -> Todo | None:
        todo = self.get(todo_id)
        if todo is None:
            return None
        todo.done = not todo.done
        todo.completed_at = time.time() if todo.done else None
        self.save()
        return todo

    def delete(self, todo_id: str) -> Todo | None:
        todo = self.get(todo_id)
        if todo is None:
            return None
        self.todos.remove(todo)
        self.save()
        return todo

    def move(self, todo_id: str, group: str) -> Todo | None:
        todo = self.get(todo_id)
        if todo is None:
            return None
        todo.group = self._ensure_group(group)
        self.save()
        return todo

    def _ensure_group(self, name: str) -> str:
        clean = _clean_group(name)
        existing = self.find_group(clean)
        if existing is not None:
            return existing
        self.groups.append(clean)
        return clean
