"""Command-line entry point."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Sequence

from . import __version__
from .model import StoreError, TodoStore


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="todo-tui",
        description="A small terminal todo list with groups, persisted to JSON.",
        epilog=(
            "Data file: $TODO_TUI_FILE, or $XDG_DATA_HOME/todo-tui/todos.json "
            "(defaults to ~/.local/share/todo-tui/todos.json)."
        ),
    )
    parser.add_argument(
        "-f",
        "--file",
        type=Path,
        metavar="PATH",
        help="use a specific data file instead of the default location",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        print(
            "todo-tui: needs an interactive terminal "
            "(stdin and stdout must be a TTY).",
            file=sys.stderr,
        )
        return 1
    path = args.file.expanduser() if args.file is not None else TodoStore.default_path()

    try:
        store = TodoStore(path)
    except StoreError as exc:
        print(f"todo-tui: {exc}", file=sys.stderr)
        return 1

    try:
        from textual.app import App  # noqa: F401
    except ModuleNotFoundError:
        print(
            "todo-tui: Textual is not installed.\n"
            "Install the dependencies with:\n"
            "  python3 -m venv .venv\n"
            "  .venv/bin/pip install -r requirements.txt\n"
            "then run:\n"
            "  .venv/bin/python todo.py",
            file=sys.stderr,
        )
        return 1

    from .ui import TodoApp

    try:
        TodoApp(store).run()
    except KeyboardInterrupt:
        return 130
    return 0
