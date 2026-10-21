# EasyTodos-TUI

A tiny, mouse-friendly todo list that lives in your terminal.

EasyTodos-TUI keeps things simple: groups, fast keyboard shortcuts, a responsive
layout for small terminals, and automatic local persistence. No account, no
sync service, no network.

- **App:** EasyTodos-TUI
- **Command:** `easytodos`
- **Requires:** Python 3.10+ and an interactive terminal

```text
 easytodos                                                    2 open, 1 done
 All  Inbox  Home  Work
 Inbox  (0/1 done)
 [ ] Read a chapter
 Home  (0/2 done)
 [ ] Buy milk and eggs
 [ ] Call the plumber
 Work  (1/1 done)
 [x] Finish the report
 Viewing all groups
   New     Check     Group     Delete     Hide done     Theme     Quit
 n new  space check  d del  g group  G new  t theme  tab view  h hide  q quit
```

## Install

### With uv (recommended)

[uv](https://docs.astral.sh/uv/) installs command-line apps in an isolated
environment:

```sh
uv tool install git+https://github.com/DraganS005/EasyTodos-TUI.git
easytodos
```

If `easytodos` is not found, add the tool directory to your shell path and open
a new terminal:

```sh
uv tool update-shell
```

### With pipx

Prefer [pipx](https://pipx.pypa.io/)?

```sh
pipx install git+https://github.com/DraganS005/EasyTodos-TUI.git
pipx ensurepath
easytodos
```

### From a clone

```sh
git clone https://github.com/DraganS005/EasyTodos-TUI.git
cd EasyTodos-TUI
uv tool install .
easytodos
```

For development, use an editable install so source changes take effect on the
next launch:

```sh
uv tool install --editable .
```

## Use it

Start EasyTodos-TUI with:

```sh
easytodos
```

The basics:

- Press `n`, type a todo, then press `enter`.
- Press `space` to check a todo off.
- Press `g` to move it to another group, or `G` to create a group.
- Press `d` to delete it.
- Press `h` to hide or show completed todos.
- Press `t` to change the color theme.
- Press `q` to quit.

Use `tab` or the left/right arrows to switch between **All** and each group.
Clicking works too: click a row to select it, click its checkbox to check it
off, click a group header or tab to switch views, or use the toolbar buttons.

### Keyboard shortcuts

| Key | Action |
| --- | --- |
| `n` / `a` | Add a todo |
| `space` / `enter` / `x` | Check off or reopen |
| `d` / `Delete` | Delete the selected todo |
| `g` | Move to another group |
| `G` | Create a new group |
| `j` / `k`, `up` / `down` | Move the selection |
| `left` / `right`, `[` / `]` | Previous / next view |
| `tab` / `shift+tab` | Cycle through views |
| `h` | Hide or show completed todos |
| `t` | Open the theme picker |
| `q` | Quit |

In dialogs, `enter` saves or confirms and `escape` cancels.

## Your data

Everything is stored locally in a JSON file:

```text
~/.local/share/easytodos/todos.json
```

Use a different file with `--file` or the `EASYTODOS_FILE` environment variable:

```sh
easytodos --file ./my-todos.json
env EASYTODOS_FILE=/path/to/todos.json easytodos
```

The selected theme and transparent-background setting are saved there too. Data
from the older `todo-tui` location is copied over automatically on first launch.

## Themes

Press `t` to open the theme picker. Highlighting a theme previews it
immediately; press `enter` to keep it or `escape` to go back. EasyTodos-TUI
includes 25 themes, including **Default** (a neutral dark theme), Catppuccin,
Dracula, Nord, Tokyo Night, Solarized, and light options.

The picker also has a **Transparent background** option, which lets your
terminal's own background show through.

## Small terminals

The interface adapts to the available space. In narrow or short terminals, the
key help and non-essential toolbar buttons disappear first, labels get shorter,
and the todo list keeps the full width. Keyboard shortcuts continue to work even
when their buttons are hidden.

## Development

```sh
git clone https://github.com/DraganS005/EasyTodos-TUI.git
cd EasyTodos-TUI
python3 -m venv .venv
.venv/bin/pip install -e .
.venv/bin/easytodos
```

Run the tests with:

```sh
.venv/bin/python -m unittest discover -s tests -v
```

### Project layout

```text
easytodos/model.py    # Todo data, validation, and JSON persistence
easytodos/view.py     # Grouping and ordering
easytodos/ui.py       # Textual app, actions, and startup
easytodos/widgets.py  # Rows, tabs, toolbar, and dialogs
easytodos/themes.py   # Theme catalog
easytodos/app.tcss    # Styles and responsive layout
easytodos/cli.py      # Command-line entry point
tests/                # Model, view, and app tests
```
