"""Source-shaped trace mutations; these are not a game run or pixel evidence.

The fixture follows InteractiveGameLoop's 12 smoke cases, UiPopupContext's
owned callbacks, InteractiveGameSession's deferred save/notice ordering,
and BitmapWindow's actual unregistered-key rejection boundary.
It deliberately does not import the verifier's phase/target constants.
"""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from game_menu_timeline import verify_game_menu_timeline

SAVE = r"C:\fixture\play-save-1-turn-7.zssave"
TOP_KEY = (1 << 51) + 42


def frame(generation, menu=False):
    lines = [f"INTERACTIVE_GPU_WORLD_COMMITTED={generation}|99",
             f"INTERACTIVE_GPU_SCENE_COMMITTED={generation}|99",
             f"INTERACTIVE_WORLD_FRAME={generation}|{generation}|7|2|10|99|4|0|1"]
    marker = "INTERACTIVE_UI_FRAME" if menu else "INTERACTIVE_TOP_PANEL_FRAME"
    context = "game-menu" if menu else "0"
    lines.append(f"{marker}={generation}|{generation}|7|{context}|88|99|C:\\fixture\\s{generation}.json|C:\\fixture\\p{generation}")
    return lines


def fixture():
    # A preceding unrelated checkpoint, and a final checkpoint after the menu,
    # are legitimate parts of the larger gameplay smoke.
    lines = [r"INTERACTIVE_NATIVE_SAVE=6|C:\fixture\earlier.zssave"]
    phases = ["top-panel-open", "return-button", "world-escape", "main-menu-confirm",
              "confirmation-escape", "unavailable-load", "unavailable-no", "quick-save",
              "unknown-world-key", "world-escape-again", "menu-escape", "returned"]
    targets = {0: ("MenuButton", TOP_KEY), 1: ("ReturnButton", 11),
               3: ("MainMenuButton", 13), 5: ("LoadGameButton", 15),
               6: ("No", 16), 7: ("QuickSaveButton", 17)}
    keys = {2: 27, 4: 27, 8: 81, 9: 27, 10: 27}
    for index, phase in enumerate(phases):
        generation = 100 + index - (index >= 9)
        if index != 9:
            lines += frame(generation, menu=index in (1, 3, 4, 5, 6, 7, 10))
        lines.append(f"INTERACTIVE_GAME_MENU_SMOKE_STEP={index}|{phase}|{generation}|7|STATE_UNCHANGED")
        if index in targets:
            name, control = targets[index]
            lines += [f"INTERACTIVE_GAME_MENU_SMOKE_TARGET={index}|{name}|{control}|{generation}|7",
                      f"INTERACTIVE_SMOKE_BUTTON={generation}|{control}|1|0",
                      f"INTERACTIVE_SMOKE_POSTED={generation}|{control}|960|540"]
        elif index in keys:
            lines.append(f"INTERACTIVE_GAME_MENU_SMOKE_KEY={index}|{keys[index]}|{generation}|7")
        if index == 0:
            lines += ["INTERACTIVE_GAME_MENU_REQUEST_QUEUED=0|0|7|GameMenu",
                      "INTERACTIVE_GAME_MENU_SHOWN=0|7|1|1|STATE_UNCHANGED",
                      "INTERACTIVE_UI_OPENED=4|game-menu",
                      f"INTERACTIVE_TOP_PANEL_INPUT={generation}|1|{TOP_KEY}|42|1"]
        elif index in (1, 3, 4, 5, 6, 7, 10):
            active = 0 if index in (1, 7, 10) else 1
            requests = int(index in (5, 7))
            if index == 5:
                lines += ["INTERACTIVE_GAME_MENU_REQUEST_QUEUED=2|0|7|LoadMenu"]
            elif index == 7:
                lines += ["INTERACTIVE_GAME_MENU_REQUEST_QUEUED=1|0|7|QuickSave"]
            kind, control = (2, targets[index][1]) if index in targets else (1, 27)
            lines += [f"INTERACTIVE_GAME_MENU_INPUT={kind}|{control}|1|0|7|{active}|{active}|{requests}|STATE_UNCHANGED"]
            if index == 5:
                lines += ["INTERACTIVE_GAME_MENU_UNAVAILABLE_SHOWN=0|7|LoadMenu|STATE_UNCHANGED",
                          "INTERACTIVE_GAME_MENU_UNAVAILABLE=0|7|LoadMenu"]
            elif index == 7:
                lines += [f"INTERACTIVE_NATIVE_SAVE=7|{SAVE}",
                          f"INTERACTIVE_GAME_MENU_QUICKSAVE=0|7|{SAVE}"]
            native_kind, native_control = (1, control) if index in targets else (0, 0)
            lines += [f"INTERACTIVE_UI_NATIVE_INPUT={generation}|{native_kind}|{native_control}|1"]
            if index in (4, 10):
                lines += [f"INTERACTIVE_UI_NATIVE_KEY={generation}|game-menu|27|1|{active}"]
        elif index in (2, 9):
            lines += ["INTERACTIVE_GAME_MENU_SHOWN=0|7|1|1|STATE_UNCHANGED",
                      f"INTERACTIVE_GAME_MENU_WORLD_KEY={generation}|27|1"]
        elif index == 8:
            lines += [f"UI_WINDOW_KEY_IGNORED={generation}|81"]
        else:
            lines += [f"INTERACTIVE_GAME_MENU_SMOKE_COMPLETE={generation}|7|STATE_UNCHANGED"]
    lines += [r"INTERACTIVE_NATIVE_SAVE=8|C:\fixture\play-save-2-turn-8.zssave",
              "INTERACTIVE_PLAY_CLOSED=8|NATIVE_CHECKPOINT_WRITTEN"]
    return "\n".join(lines) + "\n"


class GameMenuTimelineTests(unittest.TestCase):
    def reject(self, text):
        passed, reason = verify_game_menu_timeline(text)
        self.assertFalse(passed)
        self.assertIsInstance(reason, str)
        self.assertTrue(reason)

    def test_full_original_native_sequence_and_line_endings(self):
        for newline in ("\n", "\r\n", "\r"):
            with self.subTest(newline=repr(newline)):
                self.assertEqual(verify_game_menu_timeline(fixture().replace("\n", newline)), (True, None))

    def test_ordinary_hover_and_ancillary_initialization_are_allowed(self):
        text = fixture().replace(
            "INTERACTIVE_GAME_MENU_SMOKE_TARGET=3|",
            "INTERACTIVE_GAME_MENU_INPUT=3|0|0|0|7|1|1|0|STATE_UNCHANGED\n"
            "INTERACTIVE_UI_NATIVE_INPUT=103|3|0|0\nINTERACTIVE_GAME_MENU_SMOKE_TARGET=3|")
        text = "INTERACTIVE_GAME_MENU_ACTIVATED_MODS=0|SESSION_MANIFEST\n" + text
        # A hover can arrive after the opening callback, before the next step.
        text = text.replace("INTERACTIVE_GPU_WORLD_COMMITTED=101|99",
                            "INTERACTIVE_GAME_MENU_INPUT=3|0|0|0|7|1|1|0|STATE_UNCHANGED\n"
                            "INTERACTIVE_UI_NATIVE_INPUT=100|3|0|0\nINTERACTIVE_GPU_WORLD_COMMITTED=101|99")
        self.assertEqual(verify_game_menu_timeline(text), (True, None))

    def test_each_required_record_is_necessary(self):
        text = fixture()
        for number, line in enumerate(text.splitlines()):
            if line.startswith(("INTERACTIVE_UI_OPENED=", "INTERACTIVE_PLAY_CLOSED=", "INTERACTIVE_NATIVE_SAVE=6|", "INTERACTIVE_NATIVE_SAVE=8|")):
                continue
            with self.subTest(line=number, record=line):
                self.reject(text.replace(line + "\n", "", 1))

    def test_only_completion_or_steps_are_not_execution(self):
        self.reject("INTERACTIVE_GAME_MENU_SMOKE_COMPLETE=110|7|STATE_UNCHANGED\n")
        self.reject("\n".join(line for line in fixture().splitlines()
                              if line.startswith("INTERACTIVE_GAME_MENU_SMOKE_")) + "\n")

    def test_duplicate_and_malformed_records_are_rejected(self):
        text = fixture()
        prefixes = ("INTERACTIVE_GAME_MENU_SMOKE_", "INTERACTIVE_GAME_MENU_REQUEST_QUEUED=",
                    "INTERACTIVE_GAME_MENU_INPUT=", "INTERACTIVE_GAME_MENU_SHOWN=",
                    "INTERACTIVE_GAME_MENU_QUICKSAVE=", "INTERACTIVE_GAME_MENU_UNAVAILABLE",
                    "UI_WINDOW_KEY_IGNORED=")
        for number, line in enumerate(text.splitlines()):
            if not line.startswith(prefixes):
                continue
            for extra in (line, line + "|BAD"):
                with self.subTest(line=number, extra=extra):
                    self.reject(text.replace(line + "\n", line + "\n" + extra + "\n", 1))

    def test_native_post_is_bound_to_control_generation_and_left_button(self):
        text = fixture()
        for before, after in (
            ("INTERACTIVE_SMOKE_BUTTON=101|11|1|0", "INTERACTIVE_SMOKE_BUTTON=100|11|1|0"),
            ("INTERACTIVE_SMOKE_BUTTON=101|11|1|0", "INTERACTIVE_SMOKE_BUTTON=101|11|5|0"),
            ("INTERACTIVE_SMOKE_BUTTON=101|11|1|0", "INTERACTIVE_SMOKE_BUTTON=101|11|1|1"),
            ("INTERACTIVE_SMOKE_POSTED=101|11|", "INTERACTIVE_SMOKE_POSTED=101|12|"),
            ("INTERACTIVE_SMOKE_POSTED=101|11|", "INTERACTIVE_SMOKE_POSTED=100|11|"),
            ("INTERACTIVE_UI_NATIVE_INPUT=101|1|11|1", "INTERACTIVE_UI_NATIVE_INPUT=100|1|11|1"),
            ("INTERACTIVE_UI_NATIVE_INPUT=101|1|11|1", "INTERACTIVE_UI_NATIVE_INPUT=101|1|11|0"),
        ):
            with self.subTest(after=after):
                self.reject(text.replace(before, after, 1))

    def test_input_cannot_be_recorded_before_its_post(self):
        text = fixture()
        before = "INTERACTIVE_GAME_MENU_INPUT=2|11|1|0|7|0|0|0|STATE_UNCHANGED"
        target = "INTERACTIVE_GAME_MENU_SMOKE_TARGET=1|ReturnButton|11|101|7"
        self.reject(text.replace(before + "\n", "").replace(target, before + "\n" + target))

    def test_duplicate_native_input_cannot_hide_beside_a_valid_one(self):
        text = fixture()
        line = "INTERACTIVE_UI_NATIVE_INPUT=103|1|13|1"
        for extra in (line, "INTERACTIVE_UI_NATIVE_INPUT=103|1|99|1", "INTERACTIVE_UI_NATIVE_INPUT=102|1|13|1"):
            with self.subTest(extra=extra):
                self.reject(text.replace(line, line + "\n" + extra))
        self.reject(text + "INTERACTIVE_GAME_MENU_INPUT=2|11|1|0|7|0|0|0|STATE_UNCHANGED\n")
        self.reject(text + "INTERACTIVE_UI_NATIVE_KEY=110|game-menu|27|1|0\n")

    def test_generation_must_advance_and_match_latest_published_scene(self):
        text = fixture()
        self.reject(text.replace("1|return-button|101|7", "1|return-button|100|7"))
        # A target cannot claim a later generation than the ordered roundtrip.
        self.reject(text.replace("3|main-menu-confirm|103|7", "3|main-menu-confirm|999|7"))
        marker = "INTERACTIVE_GAME_MENU_SMOKE_STEP=3|"
        # Keep the entire expected target/callback segment intact but publish
        # another scene first: the superficially matching segment is now stale.
        self.reject(text.replace(marker, "\n".join(frame(999, menu=True)) + "\n" + marker))
        self.reject(text.replace("INTERACTIVE_GPU_SCENE_COMMITTED=103|99\n", ""))

    def test_unknown_world_key_is_ignored_without_replacing_scene(self):
        text = fixture()
        self.reject(text.replace("UI_WINDOW_KEY_IGNORED=108|81", "UI_WINDOW_KEY_IGNORED=108|27"))
        self.reject(text.replace("9|world-escape-again|108|7", "9|world-escape-again|109|7"))
        self.reject(text.replace("UI_WINDOW_KEY_IGNORED=108|81", "UI_WINDOW_KEY_IGNORED=108|81\nINTERACTIVE_UI_NATIVE_KEY=108|game-menu|81|1|0"))

    def test_window_ignore_requires_the_exact_posted_key_and_generation(self):
        text = fixture()
        record = "UI_WINDOW_KEY_IGNORED=108|81"
        for replacement in ("UI_WINDOW_KEY_IGNORED=107|81",
                            "UI_WINDOW_KEY_IGNORED=0|81",
                            "UI_WINDOW_KEY_IGNORED=108|27"):
            with self.subTest(replacement=replacement):
                self.reject(text.replace(record, replacement))
        # Extra acknowledgements outside the bounded roundtrip also fail.
        self.reject(text + record + "\n")
        self.reject(record + "\n" + text)

    def test_window_ignore_must_follow_successful_post_before_the_next_stage(self):
        text = fixture()
        record = "UI_WINDOW_KEY_IGNORED=108|81"
        posted = "INTERACTIVE_GAME_MENU_SMOKE_KEY=8|81|108|7"
        next_step = "INTERACTIVE_GAME_MENU_SMOKE_STEP=9|world-escape-again|108|7|STATE_UNCHANGED"
        without = text.replace(record + "\n", "")
        self.reject(without.replace(posted, record + "\n" + posted))
        self.reject(without.replace(next_step, next_step + "\n" + record))

    def test_world_loop_ignore_cannot_replace_or_follow_window_rejection(self):
        text = fixture()
        record = "UI_WINDOW_KEY_IGNORED=108|81"
        world = "INTERACTIVE_WORLD_KEY_IGNORED=108|81"
        self.reject(text.replace(record, world))
        self.reject(text.replace(record, record + "\n" + world))

    def test_window_ignore_cannot_hide_a_world_action_or_close(self):
        text = fixture()
        record = "UI_WINDOW_KEY_IGNORED=108|81"
        for unexpected in ("INTERACTIVE_WINDOW_INPUT=108|0|900|1",
                           "INTERACTIVE_WINDOW_INPUT=108|0|900|0",
                           "INTERACTIVE_PLAY_CLOSED=7|NATIVE_CHECKPOINT_WRITTEN",
                           "INTERACTIVE_GAME_SESSION_STOPPED=true"):
            with self.subTest(unexpected=unexpected):
                self.reject(text.replace(record, record + "\n" + unexpected))

    def test_confirmation_escape_keeps_menu_and_timer(self):
        text = fixture()
        self.reject(text.replace("INTERACTIVE_UI_NATIVE_KEY=104|game-menu|27|1|1", "INTERACTIVE_UI_NATIVE_KEY=104|game-menu|27|1|0"))
        self.reject(text.replace("INTERACTIVE_GAME_MENU_INPUT=1|27|1|0|7|1|1|0", "INTERACTIVE_GAME_MENU_INPUT=1|27|1|0|7|1|0|0"))
        self.reject(text.replace("INTERACTIVE_UI_NATIVE_KEY=104|game-menu|27|1|1", "INTERACTIVE_UI_NATIVE_KEY=104|production|27|1|1"))
        self.reject(text.replace("INTERACTIVE_UI_NATIVE_KEY=109|game-menu|27|1|0", "INTERACTIVE_UI_NATIVE_KEY=109|game-menu|27|1|1"))

    def test_unavailable_notice_requires_owned_request_and_visible_notice(self):
        text = fixture()
        self.reject(text.replace("INTERACTIVE_GAME_MENU_REQUEST_QUEUED=2|0|7|LoadMenu", "INTERACTIVE_GAME_MENU_REQUEST_QUEUED=2|0|7|SaveMenu"))
        self.reject(text.replace("INTERACTIVE_GAME_MENU_UNAVAILABLE_SHOWN=0|7|LoadMenu|STATE_UNCHANGED\n", ""))
        self.reject(text.replace("INTERACTIVE_GAME_MENU_INPUT=2|16|1|0|7|1|1|0", "INTERACTIVE_GAME_MENU_INPUT=2|16|1|0|7|0|0|0"))

    def test_quick_save_requires_closed_menu_before_one_matching_write(self):
        text = fixture()
        self.reject(text.replace("INTERACTIVE_GAME_MENU_INPUT=2|17|1|0|7|0|0|1", "INTERACTIVE_GAME_MENU_INPUT=2|17|1|0|7|1|1|1"))
        self.reject(text.replace(f"INTERACTIVE_GAME_MENU_QUICKSAVE=0|7|{SAVE}", r"INTERACTIVE_GAME_MENU_QUICKSAVE=0|7|C:\fixture\other.zssave"))
        saved = f"INTERACTIVE_NATIVE_SAVE=7|{SAVE}"
        inner = "INTERACTIVE_GAME_MENU_INPUT=2|17|1|0|7|0|0|1|STATE_UNCHANGED"
        self.reject(text.replace(saved + "\n", "").replace(inner, saved + "\n" + inner))
        self.reject(text + saved + "\n")
        self.reject(text.replace("INTERACTIVE_GAME_MENU_SMOKE_STEP=8|", r"INTERACTIVE_NATIVE_SAVE=7|C:\fixture\unexpected.zssave" + "\nINTERACTIVE_GAME_MENU_SMOKE_STEP=8|"))

    def test_owner_turn_window_and_device_are_stable(self):
        text = fixture()
        for before, after in (
            ("INTERACTIVE_GAME_MENU_SHOWN=0|7|1|1", "INTERACTIVE_GAME_MENU_SHOWN=1|7|1|1"),
            ("INTERACTIVE_GAME_MENU_SHOWN=0|7|1|1", "INTERACTIVE_GAME_MENU_SHOWN=0|7|0|1"),
            ("INTERACTIVE_GAME_MENU_INPUT=2|11|1|0|7|", "INTERACTIVE_GAME_MENU_INPUT=2|11|1|1|7|"),
            ("INTERACTIVE_GAME_MENU_INPUT=2|11|1|0|7|", "INTERACTIVE_GAME_MENU_INPUT=2|11|1|0|8|"),
            ("3|main-menu-confirm|103|7|", "3|main-menu-confirm|103|8|"),
            ("101|101|7|game-menu|88|99|", "101|101|7|game-menu|89|99|"),
            ("101|101|7|game-menu|88|99|", "101|101|7|game-menu|88|100|"),
            ("INTERACTIVE_GPU_SCENE_COMMITTED=101|99", "INTERACTIVE_GPU_SCENE_COMMITTED=101|100"),
        ):
            with self.subTest(after=after):
                self.reject(text.replace(before, after, 1))

    def test_namespaced_top_panel_key_and_local_menu_key_cannot_be_confused(self):
        text = fixture()
        self.reject(text.replace(f"{TOP_KEY}|42|1", f"{TOP_KEY}|43|1"))
        self.reject(text.replace(f"|{TOP_KEY}|", "|42|"))
        self.reject(text.replace("|11|", f"|{1 << 32}|"))

    def test_completion_requires_returned_world_and_all_previous_actions(self):
        text = fixture()
        complete = "INTERACTIVE_GAME_MENU_SMOKE_COMPLETE=110|7|STATE_UNCHANGED"
        self.reject(text.replace(complete + "\n", "").replace("INTERACTIVE_GAME_MENU_SMOKE_STEP=10|", complete + "\nINTERACTIVE_GAME_MENU_SMOKE_STEP=10|"))
        self.reject(text.replace("INTERACTIVE_TOP_PANEL_FRAME=110|110|7|0|", "INTERACTIVE_UI_FRAME=110|110|7|game-menu|"))
        self.reject(text.replace(complete, "INTERACTIVE_GAME_MENU_SMOKE_COMPLETE=109|7|STATE_UNCHANGED"))
        self.reject(text.replace("INTERACTIVE_UI_NATIVE_KEY=109|game-menu|27|1|0\n", ""))
        self.reject(text + "INTERACTIVE_GAME_MENU_COMMAND_REJECTED=0|7|QuickSave\n")


if __name__ == "__main__":
    unittest.main(verbosity=2)
