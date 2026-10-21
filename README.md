# Todo TUI

A small, dependency-free terminal todo list with groups. Built with Python's
standard-library `curses` module.

```
 TODO  grouped todo list
 View [All]  Inbox  Work  Home
 ────────────────────────────────────────────
 Work  (1/3 done)
   [ ] Write the report
   [ ] Reply to email
   [x] Book meeting room
 Home  (0/2 done)
   [ ] Buy milk
   [ ] Water plants
 2 open, 3 done
 n new  space toggle  d del  g group  G new  tab view  h hide done  q quit
```

## Run

Requires Python 3.10+ and an interactive terminal. There is nothing to install.

```sh
python3 todo.py
# or
python3 -m todo_tui
```

Todos are saved automatically to `~/.local/share/todo-tui/todos.json`
(or `$XDG_DATA_HOME/todo-tui/todos.json`). You can choose another file:

```sh
python3 todo.py --file ./my-todos.json
# or set TODO_TUI_FILE=/path/to/todos.json
```

## Keys

| Key | Action |
| --- | --- |
| `n` / `a` | Add a todo to the current group |
| `space` / `enter` / `x` | Check off or reopen the selected todo |
| `d` | Delete the selected todo immediately |
| `g` | Move the selected todo to another group (or a new one) |
| `G` | Create a new group and switch to it |
| `tab` / `shift+tab` | Cycle between All and each group |
| `h` | Hide or show completed todos |
| `j` / `k` / arrows | Move the selection |
| `q` | Quit |

## Groups and sorting

The **All** view shows todos under group headers, and each group also gets a
tab. Within a group, open todos come first (oldest first), followed by completed
todos. Checking a todo off leaves it visible but moves it below the open items;
press `h` if you would rather hide completed items completely. Group headers
show `done/total` counts.

When adding a todo, the prompt shows which group it will go to: the group you
are viewing, or in the All view the selected todo's group (falling back to the
last group you used). To add to a brand-new group, press `G` first.

Creating a group, moving a todo, and adding a todo all update the JSON file
atomically right away.

## Tests

```sh
python3 -m unittest discover -s tests -v
```

## Layout

```
todo.py              # runnable entry point
todo_tui/model.py    # Todo, TodoStore, validation, JSON persistence
todo_tui/view.py     # grouping / ordering logic for the list
todo_tui/ui.py       # curses interface
todo_tui/cli.py      # argument parsing and startup
tests/               # model, persistence, and view logic tests
```
