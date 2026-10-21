"""Command-line entry point."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Sequence

from . import APP_NAME, __version__
from .model import APP_DATA_FILE_ENV, StoreError, TodoStore


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=APP_NAME,
        description="A small terminal todo list with groups, persisted to JSON.",
        epilog=(
            f"Data file: ${APP_DATA_FILE_ENV}, or "
            f"$XDG_DATA_HOME/{APP_NAME}/todos.json "
            f"(defaults to ~/.local/share/{APP_NAME}/todos.json)."
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
            f"{APP_NAME}: needs an interactive terminal "
            "(stdin and stdout must be a TTY).",
            file=sys.stderr,
        )
        return 1
    path = args.file.expanduser() if args.file is not None else TodoStore.default_path()

    try:
        store = TodoStore(path)
    except StoreError as exc:
        print(f"{APP_NAME}: {exc}", file=sys.stderr)
        return 1

    try:
        from textual.app import App  # noqa: F401
    except ModuleNotFoundError:
        print(
            f"{APP_NAME}: Textual is not installed.\n"
            "Install the dependencies with:\n"
            "  python3 -m venv .venv\n"
            "  .venv/bin/pip install -r requirements.txt\n"
            "then run:\n"
            "  .venv/bin/python easytodos.py",
            file=sys.stderr,
        )
        return 1

    from .ui import TodoApp

    try:
        TodoApp(store).run()
    except KeyboardInterrupt:
        return 130
    return 0
