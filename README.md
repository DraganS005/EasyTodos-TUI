# easytodos

A small terminal todo list with groups, built with
[Textual](https://textual.textualize.io/). It has mouse support, a responsive
layout that keeps working in very small terminals, and automatic JSON
persistence.

```text
 easytodos                                                      2 open, 1 done
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

Requires Python 3.10+ and an interactive terminal. Textual is the only runtime
dependency.

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python easytodos.py
```

Or install the project itself, which adds an `easytodos` command:

```sh
.venv/bin/pip install -e .
.venv/bin/easytodos
```

Using a virtual environment avoids changes to the system Python. If Textual is
missing, the app prints the install commands instead of a traceback.

## Run

```sh
.venv/bin/python easytodos.py
# or, from an installed environment
.venv/bin/python -m easytodos
.venv/bin/easytodos
```

Todos, the selected color theme, and the transparent-background setting are
saved automatically to `~/.local/share/easytodos/todos.json` (or
`$XDG_DATA_HOME/easytodos/todos.json`). Choose another file with `--file` or
`EASYTODOS_FILE`:

```sh
.venv/bin/python easytodos.py --file ./my-todos.json
EASYTODOS_FILE=/path/to/todos.json .venv/bin/python easytodos.py
```

Data from the old `~/.local/share/todo-tui/todos.json` location is copied to
`~/.local/share/easytodos/todos.json` on first launch.

## Mouse

| Interaction | Action |
| --- | --- |
| Click a todo | Select it |
| Click the `[ ]` box | Check or reopen it |
| Double-click a todo | Check or reopen it |
| Click a group header | Switch to that group |
| Click a view tab | Switch between All and each group |
| Click a toolbar button | Add, check, group, delete, hide completed, choose a theme, or quit |
| Click a group in the move dialog | Move the selected todo there |
| Wheel / scrollbar | Scroll the list |

The toolbar labels shorten automatically in narrow terminals. Tooltips on rows
and buttons describe their actions.

## Keys

| Key | Action |
| --- | --- |
| `n` / `a` | Add a todo to the current group |
| `space` / `enter` / `x` | Check off or reopen the selected todo |
| `d` / `Delete` | Delete the selected todo immediately |
| `g` | Move the selected todo to another group (or a new group) |
| `G` | Create a new group and switch to it |
| `tab` / `shift+tab` | Cycle between All and each group |
| `left` / `right`, `[` / `]` | Previous / next view |
| `h` | Hide or show completed todos |
| `t` | Change the color theme |
| `j` / `k` / arrows | Move the selection |
| `q` | Quit |

In dialogs, `enter` saves or chooses, and `escape` cancels.

## Color themes

Press `t`, or click **Theme** in the toolbar (hidden only at tiny sizes), to
open the theme picker. Highlighting a theme previews it immediately; press
`enter` or click a theme to apply it, or `escape` / **Cancel** to restore the
previous one. The choice is saved in the todo JSON file and restored on the
next launch.

The first item in the picker, **Transparent background**, lets the terminal's
own background show through the list, tabs, status, help, and toolbar. Theme
colors still apply to text, accents, buttons, and dialogs. This uses the
terminal's default background, so terminal-level transparency, blur, or a
background image also shows through. Reopen the picker and select the item
again to turn it off. Pick a light or dark theme that matches your terminal for
the best text contrast.

There are 25 theme choices (plus the transparent-background toggle):

**Default** is a neutral dark theme designed to sit comfortably beside most
terminal color schemes.

- **Dark:** Default, Textual Dark, Atom One Dark, Ayu Mirage, Catppuccin Frappe,
  Catppuccin Macchiato, Catppuccin Mocha, Dracula, Everforest Dark, Flexoki,
  GitHub Dark, Gruvbox Dark, Kanagawa, Monokai, Nord, Rose Pine,
  Rose Pine Moon, Solarized Dark, Tokyo Night
- **Light:** Textual Light, Atom One Light, Catppuccin Latte, GitHub Light,
  Rose Pine Dawn, Solarized Light

The **Theme** toolbar button is hidden at tiny sizes to keep the four essential
actions, and the **Quit** button is omitted below 60 columns; `t` and `q` work
at every size.

## Small terminals

The interface changes as the terminal shrinks:

| Size | What changes |
| --- | --- |
| 80x20 and larger | Full header, tabs, status, toolbar, and key help |
| Narrower than 80 or shorter than 20 | Key help is hidden and group spacing tightens |
| Narrower than 60 | Quit button is hidden (`q` still works) |
| Narrower than 50 or shorter than 11 | Header, status, and help are hidden; compact toolbar labels; Theme button hidden |
| Shorter than 4 rows | Toolbar is hidden |
| Shorter than 2 rows | Tabs are hidden |

Long todo text is truncated with an ellipsis rather than wrapping and consuming
more rows. At tiny sizes the toolbar keeps the four essential actions: add,
check, group, and delete. Modal dialogs become full-width, remove decorative
borders, and keep their input and buttons visible.

## Groups and selection

The **All** view shows todos under clickable group headers, and every group also
has a tab. Open todos sort first (oldest first), followed by completed todos.
Group headers show done/total counts, including completed todos that are
currently hidden.

Checking a todo off keeps it selected while it reorders, and the list scrolls to
follow it. If the completed todo is hidden by **Hide done**, or it is moved out
of the current view, the selection moves to the next visible row at the same
position (falling back to the previous row at the end) instead of jumping to the
top. Deleting a todo behaves the same way.

When adding a todo, the dialog names the target group: the group you are
viewing, or in the All view the selected todo's group (falling back to the last
group used). Press `G` to create a new group first.

## Tests

```sh
.venv/bin/python -m unittest discover -s tests -v
```

The test suite covers the model, grouping/order logic, and the Textual app
(including mouse clicks, keyboard navigation after completion, groups, modals,
and layouts down to 20x3).

## Layout

```text
easytodos.py             # runnable entry point
easytodos/model.py       # Todo, TodoStore, validation, JSON persistence
easytodos/view.py        # grouping and ordering for the list
easytodos/ui.py          # Textual app, actions, responsive chrome
easytodos/widgets.py     # rows, tabs, toolbar, dialogs
easytodos/themes.py      # 25 theme choices and custom Textual themes
easytodos/app.tcss       # Textual stylesheet and responsive tiers
easytodos/cli.py         # argument parsing and startup
tests/                   # model, view, and Textual app tests
```
