"""Curses interface for the todo app."""

from __future__ import annotations

import curses
import unicodedata

from .model import (
    DEFAULT_GROUP,
    MAX_GROUP_LENGTH,
    MAX_TEXT_LENGTH,
    Todo,
    TodoStore,
    StoreError,
)
from .view import Row, build_rows, visible_todo_ids

_NEW_GROUP = object()
_NEW_GROUP_LABEL = "+ New group..."


def _width(text: str) -> int:
    total = 0
    for char in text:
        if unicodedata.combining(char):
            continue
        total += 2 if unicodedata.east_asian_width(char) in ("W", "F") else 1
    return total


def _clip(text: str, max_width: int) -> str:
    """Clip text to a terminal column width without splitting wide characters."""
    if max_width <= 0:
        return ""
    kept: list[str] = []
    used = 0
    for char in text:
        if not char.isprintable() and not unicodedata.combining(char):
            char = " "
        char_width = _width(char)
        if used + char_width > max_width:
            break
        kept.append(char)
        used += char_width
    return "".join(kept)


def _shorten(text: str, limit: int = 30) -> str:
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


def _win_put(
    win: "curses.window",
    y: int,
    x: int,
    text: str,
    limit: int,
    attr: int = 0,
) -> None:
    clipped = _clip(text, limit)
    if not clipped:
        return
    try:
        win.addstr(y, x, clipped, attr)
    except curses.error:
        pass


class TodoApp:
    def __init__(self, stdscr: "curses.window", store: TodoStore) -> None:
        self.stdscr = stdscr
        self.store = store
        self.view: str | None = None  # None means all groups
        self.active_group = store.groups[0] if store.groups else DEFAULT_GROUP
        self.selected_id: str | None = None
        self.scroll = 0
        self.show_done = True
        self.message = ""
        self.message_error = False

        self.attr_title = curses.A_BOLD
        self.attr_group = curses.A_BOLD
        self.attr_done = curses.A_DIM
        self.attr_status = 0
        self.attr_error = curses.A_BOLD
        self.attr_accent = curses.A_REVERSE | curses.A_BOLD
        self.attr_dim = curses.A_DIM

    # -- setup and main loop -------------------------------------------------

    def _setup(self) -> None:
        try:
            curses.curs_set(0)
        except curses.error:
            pass
        try:
            curses.set_escdelay(25)
        except (AttributeError, curses.error):
            pass
        self.stdscr.keypad(True)

        if not curses.has_colors():
            return
        try:
            curses.start_color()
            try:
                curses.use_default_colors()
            except curses.error:
                pass
            self.attr_title = curses.A_BOLD | self._color(1, curses.COLOR_CYAN)
            self.attr_group = curses.A_BOLD | self._color(2, curses.COLOR_YELLOW)
            self.attr_done = curses.A_DIM | self._color(3, curses.COLOR_GREEN)
            self.attr_status = self._color(4, curses.COLOR_CYAN)
            self.attr_error = curses.A_BOLD | self._color(5, curses.COLOR_RED)
            self.attr_accent = curses.A_BOLD | self._color(6, curses.COLOR_MAGENTA)
        except curses.error:
            pass

    @staticmethod
    def _color(pair: int, foreground: int) -> int:
        try:
            curses.init_pair(pair, foreground, -1)
        except curses.error:
            try:
                curses.init_pair(pair, foreground, curses.COLOR_BLACK)
            except curses.error:
                return 0
        return curses.color_pair(pair)

    def run(self) -> None:
        self._setup()
        try:
            while True:
                self.draw()
                try:
                    key = self.stdscr.get_wch()
                except curses.error:
                    continue
                except KeyboardInterrupt:
                    break
                if not self._handle_key(key):
                    break
        finally:
            try:
                curses.curs_set(1)
            except curses.error:
                pass

    # -- drawing -------------------------------------------------------------

    def _put(
        self,
        y: int,
        x: int,
        text: str,
        attr: int = 0,
        limit: int | None = None,
    ) -> None:
        try:
            height, width = self.stdscr.getmaxyx()
        except curses.error:
            return
        if y < 0 or y >= height or x < 0 or x >= width:
            return
        available = width - x - 1
        if limit is not None:
            available = min(available, limit)
        if available <= 0 or not text:
            return
        clipped = _clip(str(text), available)
        if not clipped:
            return
        try:
            self.stdscr.addstr(y, x, clipped, attr)
        except curses.error:
            pass

    def draw(self) -> None:
        self.stdscr.erase()
        try:
            height, width = self.stdscr.getmaxyx()
        except curses.error:
            return

        if height < 7 or width < 30:
            self._put(0, 0, "Terminal too small.", self.attr_error)
            self._put(1, 0, "Resize the window, or press q to quit.", self.attr_dim)
            self.stdscr.refresh()
            return

        self._put(0, 1, "TODO", self.attr_title)
        self._put(0, 7, "grouped todo list", self.attr_dim)
        self._draw_tabs(width)

        try:
            self.stdscr.hline(2, 0, curses.ACS_HLINE, width - 1, self.attr_dim)
        except curses.error:
            pass

        rows = build_rows(self.store, self.view, self.show_done)
        self._draw_rows(rows, height, width)
        self._draw_status(height, width)
        self._draw_help(height, width)
        self.stdscr.refresh()

    def _draw_tabs(self, width: int) -> None:
        self._put(1, 1, "View", self.attr_dim)
        entries: list[tuple[str | None, str]] = [(None, "All")]
        entries.extend((group, group) for group in self.store.groups)

        tokens: list[str] = []
        attrs: list[int] = []
        for view, name in entries:
            if view == self.view:
                tokens.append(f"[{name}]")
                attrs.append(self.attr_accent)
            else:
                tokens.append(f" {name} ")
                attrs.append(self.attr_dim)

        active_index = next(
            (index for index, (view, _) in enumerate(entries) if view == self.view),
            0,
        )
        available = width - 7
        start = 0
        total = sum(_width(token) + 1 for token in tokens)
        # Scroll the tab strip so the active view stays visible.
        while start < active_index and total > available:
            total -= _width(tokens[start]) + 1
            start += 1
        if start > 0:
            while total + 2 > available and start < active_index:
                total -= _width(tokens[start]) + 1
                start += 1

        x = 6
        if start > 0:
            self._put(1, x, "< ", self.attr_dim)
            x += 2
        for index in range(start, len(tokens)):
            token = tokens[index]
            if x + _width(token) > width - 1:
                break
            self._put(1, x, token, attrs[index])
            x += _width(token) + 1

    def _draw_rows(self, rows: list[Row], height: int, width: int) -> None:
        top = 3
        list_height = height - 5
        if list_height < 1:
            return

        ids = visible_todo_ids(rows)
        if not ids:
            self.selected_id = None
        elif self.selected_id not in ids:
            self.selected_id = ids[0]

        selected_row = 0
        if self.selected_id is not None:
            for index, row in enumerate(rows):
                if row.todo is not None and row.todo.id == self.selected_id:
                    selected_row = index
                    break

        if selected_row < self.scroll:
            self.scroll = selected_row
        elif selected_row >= self.scroll + list_height:
            self.scroll = selected_row - list_height + 1
        self.scroll = max(0, min(self.scroll, max(0, len(rows) - list_height)))

        if not rows:
            if not self.store.todos:
                message = "No todos yet. Press n to add one."
            elif self.view is not None:
                message = f"No todos in {self.view}. Press n to add one."
            elif not self.show_done and self.store.done_count:
                message = "Nothing open here. Press h to show completed todos."
            else:
                message = "Nothing to show."
            x = max(1, (width - len(message)) // 2)
            self._put(top + list_height // 2, x, message, self.attr_dim)
            return

        for line, row in enumerate(rows[self.scroll : self.scroll + list_height]):
            y = top + line
            if row.kind == "group":
                label = f"{row.group}  ({row.done}/{row.total} done)"
                self._put(y, 1, label, self.attr_group)
                continue

            todo = row.todo
            if todo is None:
                continue
            checkbox = "[x]" if todo.done else "[ ]"
            text = todo.text.replace("\n", " ").replace("\r", " ")
            line_text = f"  {checkbox} {text}"

            attr = self.attr_done if todo.done else 0
            if todo.id == self.selected_id:
                attr |= curses.A_REVERSE
                line_text = line_text.ljust(width - 2)
            self._put(y, 0, line_text, attr, width - 1)

    def _draw_status(self, height: int, width: int) -> None:
        y = height - 2
        counts = f"{self.store.open_count} open, {self.store.done_count} done"
        counts_x = max(1, width - len(counts) - 1)

        left = self.message or (
            f"Viewing {self.view}" if self.view is not None else "Viewing all groups"
        )
        if self.message:
            attr = self.attr_error if self.message_error else self.attr_status
        else:
            attr = self.attr_dim
        limit = max(0, counts_x - 3)
        if limit > 0:
            self._put(y, 1, left, attr, limit)
        self._put(y, counts_x, counts, self.attr_dim)

    def _draw_help(self, height: int, width: int) -> None:
        hide = "hide" if self.show_done else "show"
        if width >= 92:
            help_text = (
                f"n new   space toggle   d delete   g group   G new group   "
                f"tab view   h {hide} done   q quit"
            )
        elif width >= 76:
            help_text = (
                f"n new  space toggle  d del  g group  G new  "
                f"tab view  h {hide} done  q quit"
            )
        elif width >= 61:
            help_text = (
                f"n new  spc check  d del  g group  tab view  h {hide}  q quit"
            )
        elif width >= 54:
            help_text = (
                f"n new  spc check  d del  g grp  tab  h {hide}  q quit"
            )
        elif width >= 47:
            help_text = f"n new  spc  d del  g grp  tab  h {hide}  q quit"
        elif width >= 42:
            help_text = f"n new  spc  d del  g grp  h {hide}  q quit"
        else:
            help_text = "n add  spc  d del  q quit"
        self._put(height - 1, 1, help_text, self.attr_dim, width - 2)

    # -- key handling --------------------------------------------------------

    def _handle_key(self, key: str | int) -> bool:
        if isinstance(key, str):
            if key == "q" or key == "\x03":
                return False
            if key == "n" or key == "a":
                self._add_todo()
            elif key in (" ", "\n", "\r", "x"):
                self._toggle_selected()
            elif key == "d":
                self._delete_selected()
            elif key == "g":
                self._move_selected()
            elif key == "G":
                self._new_group()
            elif key == "\t":
                self._cycle_view(1)
            elif key == "h":
                self.show_done = not self.show_done
                self.message = "Showing completed todos." if self.show_done else "Hiding completed todos."
                self.message_error = False
            elif key in ("j", "J"):
                self._move_selection(1)
            elif key in ("k", "K"):
                self._move_selection(-1)
            return True

        if key == curses.KEY_RESIZE:
            return True
        if key == curses.KEY_UP:
            self._move_selection(-1)
        elif key == curses.KEY_DOWN:
            self._move_selection(1)
        elif key == curses.KEY_BTAB:
            self._cycle_view(-1)
        elif key in (curses.KEY_ENTER,):
            self._toggle_selected()
        elif key == curses.KEY_DC:
            self._delete_selected()
        return True

    def _selected_todo(self) -> Todo | None:
        return self.store.get(self.selected_id)

    def _move_selection(self, delta: int) -> None:
        ids = visible_todo_ids(build_rows(self.store, self.view, self.show_done))
        if not ids:
            self.selected_id = None
            return
        if self.selected_id not in ids:
            self.selected_id = ids[0] if delta >= 0 else ids[-1]
            return
        index = ids.index(self.selected_id)
        self.selected_id = ids[max(0, min(len(ids) - 1, index + delta))]

    def _cycle_view(self, step: int) -> None:
        views: list[str | None] = [None, *self.store.groups]
        try:
            index = views.index(self.view)
        except ValueError:
            index = 0
        self.view = views[(index + step) % len(views)]
        if self.view is not None:
            self.active_group = self.view
        self.selected_id = None
        self.scroll = 0
        label = self.view if self.view is not None else "all groups"
        self.message = f"Viewing {label}."
        self.message_error = False

    def _add_todo(self) -> None:
        selected = self._selected_todo()
        if self.view is not None:
            group = self.view
        elif selected is not None:
            group = selected.group
        else:
            group = self.active_group
        if group not in self.store.groups:
            group = DEFAULT_GROUP
        text = self.prompt(f"New todo in {group}")
        if not text:
            return
        try:
            todo = self.store.add(text, group)
        except (ValueError, StoreError) as exc:
            self._error(str(exc))
            return
        self.active_group = todo.group
        self.selected_id = todo.id
        self.message = f"Added to {todo.group}."
        self.message_error = False

    def _toggle_selected(self) -> None:
        todo = self._selected_todo()
        if todo is None:
            return
        try:
            updated = self.store.toggle(todo.id)
        except StoreError as exc:
            self._error(str(exc))
            return
        if updated is not None:
            self.message = (
                f"Checked off: {_shorten(updated.text, 28)}"
                if updated.done
                else f"Reopened: {_shorten(updated.text, 28)}"
            )
            self.message_error = False

    def _delete_selected(self) -> None:
        todo = self._selected_todo()
        if todo is None:
            return
        ids = visible_todo_ids(build_rows(self.store, self.view, self.show_done))
        try:
            index = ids.index(todo.id)
        except ValueError:
            index = 0
        try:
            self.store.delete(todo.id)
        except StoreError as exc:
            self._error(str(exc))
            return

        remaining = visible_todo_ids(build_rows(self.store, self.view, self.show_done))
        if remaining:
            self.selected_id = remaining[min(index, len(remaining) - 1)]
        else:
            self.selected_id = None
        self.message = f"Deleted: {_shorten(todo.text, 28)}"
        self.message_error = False

    def _move_selected(self) -> None:
        todo = self._selected_todo()
        if todo is None:
            return
        target = self._pick_group(f'Move "{_shorten(todo.text, 20)}"', current=todo.group)
        if target is None:
            return
        if target == todo.group:
            self.message = f"Already in {target}."
            self.message_error = False
            return
        try:
            moved = self.store.move(todo.id, target)
        except (ValueError, StoreError) as exc:
            self._error(str(exc))
            return
        if moved is not None:
            self.message = f"Moved to {target}."
            self.message_error = False

    def _new_group(self) -> None:
        name = self.prompt("New group name", limit=MAX_GROUP_LENGTH)
        if not name:
            return
        try:
            group = self.store.add_group(name)
        except (ValueError, StoreError) as exc:
            self._error(str(exc))
            return
        self.view = group
        self.active_group = group
        self.selected_id = None
        self.scroll = 0
        self.message = f"Viewing {group}. Press n to add a todo."
        self.message_error = False

    def _error(self, message: str) -> None:
        self.message = message
        self.message_error = True

    # -- modal helpers -------------------------------------------------------

    def prompt(
        self,
        label: str,
        *,
        initial: str = "",
        limit: int = MAX_TEXT_LENGTH,
    ) -> str | None:
        text = initial
        try:
            curses.curs_set(1)
        except curses.error:
            pass
        try:
            while True:
                self.draw()
                try:
                    height, width = self.stdscr.getmaxyx()
                except curses.error:
                    return None
                if height < 2 or width < 12:
                    return None
                prefix = f"{label}: "
                if _width(prefix) > width - 14:
                    prefix = "> "
                available = max(1, width - 2 - _width(prefix))
                shown = text
                while shown and _width(shown) > available:
                    shown = shown[1:]
                line = prefix + shown
                self._put(height - 1, 0, " " * (width - 1), 0)
                self._put(height - 1, 0, line, curses.A_BOLD)
                try:
                    self.stdscr.move(height - 1, min(width - 2, _width(line)))
                    self.stdscr.refresh()
                    key = self.stdscr.get_wch()
                except curses.error:
                    continue

                if not isinstance(key, str):
                    if key == curses.KEY_RESIZE:
                        continue
                    if key == curses.KEY_BACKSPACE:
                        text = text[:-1]
                    elif key == curses.KEY_ENTER:
                        return text.strip() or None
                    continue

                if key in ("\n", "\r"):
                    return text.strip() or None
                if key in ("\x1b", "\x03"):
                    return None
                if key in ("\x7f", "\b"):
                    text = text[:-1]
                elif key == "\x15":  # Ctrl-U clears the line.
                    text = ""
                elif key.isprintable() and len(text) < limit:
                    text += key
        finally:
            try:
                curses.curs_set(0)
            except curses.error:
                pass

    def _pick_group(self, title: str, current: str | None = None) -> str | None:
        try:
            height, width = self.stdscr.getmaxyx()
        except curses.error:
            return None
        if height < 9 or width < 36:
            self._error("Terminal too small for the group picker.")
            return None

        groups = list(self.store.groups)
        items: list[str | object] = [*groups, _NEW_GROUP]
        labels = [*groups, _NEW_GROUP_LABEL]
        list_height = min(len(items), height - 7)
        win_height = list_height + 4
        win_width = min(
            max(
                36,
                _width(title) + 6,
                *(_width(label) + 8 for label in labels),
            ),
            width - 4,
        )
        top = (height - win_height) // 2
        left = (width - win_width) // 2
        win = curses.newwin(win_height, win_width, top, left)
        win.keypad(True)
        selected = groups.index(current) if current in groups else 0
        offset = max(0, selected - list_height + 1)
        choice: str | object | None = None

        try:
            while True:
                win.erase()
                try:
                    win.box()
                except curses.error:
                    pass
                _win_put(win, 0, 2, f" {title} ", win_width - 4, curses.A_BOLD)
                _win_put(
                    win,
                    win_height - 1,
                    2,
                    " Enter select   Esc cancel ",
                    win_width - 4,
                    curses.A_DIM,
                )

                if selected < offset:
                    offset = selected
                elif selected >= offset + list_height:
                    offset = selected - list_height + 1

                for line, index in enumerate(
                    range(offset, min(len(items), offset + list_height))
                ):
                    label = labels[index]
                    attr = (
                        curses.A_REVERSE | curses.A_BOLD
                        if index == selected
                        else 0
                    )
                    inner = f" {label} "
                    padding = max(0, win_width - 3 - _width(inner))
                    _win_put(
                        win,
                        2 + line,
                        1,
                        inner + " " * padding,
                        win_width - 3,
                        attr,
                    )
                win.refresh()

                try:
                    key = win.get_wch()
                except curses.error:
                    continue

                if isinstance(key, str):
                    if key in ("\n", "\r"):
                        choice = items[selected]
                        break
                    if key in ("\x1b", "\x03"):
                        break
                    if key in ("j", "J"):
                        selected = min(len(items) - 1, selected + 1)
                    elif key in ("k", "K"):
                        selected = max(0, selected - 1)
                    elif key in ("n", "N"):
                        choice = _NEW_GROUP
                        break
                else:
                    if key == curses.KEY_RESIZE:
                        break
                    if key == curses.KEY_UP:
                        selected = max(0, selected - 1)
                    elif key == curses.KEY_DOWN:
                        selected = min(len(items) - 1, selected + 1)
                    elif key == curses.KEY_ENTER:
                        choice = items[selected]
                        break
        finally:
            del win
            self.stdscr.touchwin()

        if choice is _NEW_GROUP:
            name = self.prompt("New group name", limit=MAX_GROUP_LENGTH)
            if not name:
                return None
            try:
                group = self.store.add_group(name)
            except (ValueError, StoreError) as exc:
                self._error(str(exc))
                return None
            return group
        if isinstance(choice, str):
            return choice
        return None
