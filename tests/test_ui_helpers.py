from __future__ import annotations

import unittest

from todo_tui.ui import _clip, _width


class ClipTests(unittest.TestCase):
    def test_ascii_is_clipped_to_columns(self) -> None:
        self.assertEqual(_clip("hello", 3), "hel")
        self.assertEqual(_clip("hello", 0), "")

    def test_a_wide_character_never_straddles_the_edge(self) -> None:
        self.assertEqual(_clip("日本", 3), "日")
        self.assertEqual(_width("日本"), 4)

    def test_combining_characters_stay_with_their_base(self) -> None:
        text = "e\u0301x"
        self.assertEqual(_width(text), 2)
        self.assertEqual(_clip(text, 1), "e\u0301")

    def test_control_characters_are_displayed_as_spaces(self) -> None:
        self.assertEqual(_clip("a\tb", 3), "a b")


if __name__ == "__main__":
    unittest.main()
