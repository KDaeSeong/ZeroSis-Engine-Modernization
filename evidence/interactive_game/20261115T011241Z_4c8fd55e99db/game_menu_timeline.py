"""Validate the original menu's bounded, native-window input sequence."""
from __future__ import annotations

import re

PHASES = (
    "top-panel-open", "return-button", "world-escape", "main-menu-confirm",
    "confirmation-escape", "unavailable-load", "unavailable-no", "quick-save",
    "unknown-world-key", "world-escape-again", "menu-escape", "returned",
)
TARGETS = {0: "MenuButton", 1: "ReturnButton", 3: "MainMenuButton",
           5: "LoadGameButton", 6: "No", 7: "QuickSaveButton"}
KEYS = {2: 27, 4: 27, 8: 81, 9: 27, 10: 27}
MENU_STEPS = {1, 3, 4, 5, 6, 7, 10}


def verify_game_menu_timeline(text: str) -> tuple[bool, str | None]:
    """Bind the 12 source-defined smoke steps to posted and consumed input.

    This checks native trace ordering and published scene ownership. SDK-state
    files, snapshot contents and save bytes remain separate runner checks; the
    trace does not establish retail UI equivalence or a human playthrough.
    """
    try:
        _verify(text.replace("\r\n", "\n").replace("\r", "\n"))
    except ValueError as error:
        return False, str(error)
    return True, None


def _verify(text: str) -> None:
    def require(condition: bool, reason: str) -> None:
        if not condition:
            raise ValueError(reason)

    def records(marker: str, fields: str) -> list[re.Match]:
        found = list(re.finditer(r"^" + marker + "=" + fields + "$", text, re.M))
        require(len(found) == len(re.findall(r"^" + marker + "=", text, re.M)),
                f"Malformed {marker} record")
        return found

    def one(found: list[re.Match], reason: str) -> re.Match:
        require(len(found) == 1, reason)
        return found[0]

    def ordered(*items: re.Match) -> None:
        require(all(a.end() < b.start() for a, b in zip(items, items[1:])),
                "GameMenu native input evidence is out of callback order")

    specs = {
        "steps": ("INTERACTIVE_GAME_MENU_SMOKE_STEP", r"(\d+)\|([^|\n]+)\|(\d+)\|(\d+)\|STATE_UNCHANGED"),
        "targets": ("INTERACTIVE_GAME_MENU_SMOKE_TARGET", r"(\d+)\|([^|\n]+)\|(\d+)\|(\d+)\|(\d+)"),
        "keys": ("INTERACTIVE_GAME_MENU_SMOKE_KEY", r"(\d+)\|(\d+)\|(\d+)\|(\d+)"),
        "shown": ("INTERACTIVE_GAME_MENU_SHOWN", r"(\d+)\|(\d+)\|(\d+)\|1\|STATE_UNCHANGED"),
        "inner": ("INTERACTIVE_GAME_MENU_INPUT", r"([1-5])\|(\d+)\|([01])\|(\d+)\|(\d+)\|([01])\|([01])\|(\d+)\|STATE_UNCHANGED"),
        "queued": ("INTERACTIVE_GAME_MENU_REQUEST_QUEUED", r"([0-2])\|(\d+)\|(\d+)\|([^|\n]+)"),
        "unavailable_shown": ("INTERACTIVE_GAME_MENU_UNAVAILABLE_SHOWN", r"(\d+)\|(\d+)\|([^|\n]+)\|STATE_UNCHANGED"),
        "unavailable": ("INTERACTIVE_GAME_MENU_UNAVAILABLE", r"(\d+)\|(\d+)\|([^|\n]+)"),
        "quick": ("INTERACTIVE_GAME_MENU_QUICKSAVE", r"(\d+)\|(\d+)\|([^|\n]+)"),
        "complete": ("INTERACTIVE_GAME_MENU_SMOKE_COMPLETE", r"(\d+)\|(\d+)\|STATE_UNCHANGED"),
        "world_key": ("INTERACTIVE_GAME_MENU_WORLD_KEY", r"(\d+)\|(\d+)\|([01])"),
        # Q is rejected by the native window whitelist before QueueKey.
        "ignored": ("UI_WINDOW_KEY_IGNORED", r"(\d+)\|(\d+)"),
        "world_ignored": ("INTERACTIVE_WORLD_KEY_IGNORED", r"(\d+)\|(\d+)"),
        "world_input": ("INTERACTIVE_WINDOW_INPUT", r"(\d+)\|([0-5])\|(\d+)\|([01])"),
        "closed": ("INTERACTIVE_PLAY_CLOSED", r"(\d+)\|NATIVE_CHECKPOINT_WRITTEN"),
        "session_stopped": ("INTERACTIVE_GAME_SESSION_STOPPED", r"(true|false)"),
        "native": ("INTERACTIVE_UI_NATIVE_INPUT", r"(\d+)\|([0-5])\|(\d+)\|([01])"),
        "native_key": ("INTERACTIVE_UI_NATIVE_KEY", r"(\d+)\|([^|\n]+)\|(\d+)\|([01])\|([01])"),
        "top": ("INTERACTIVE_TOP_PANEL_INPUT", r"(\d+)\|([0-5])\|(\d+)\|(\d+)\|([01])"),
        "buttons": ("INTERACTIVE_SMOKE_BUTTON", r"(\d+)\|(\d+)\|([0-5])\|([01])"),
        "posts": ("INTERACTIVE_SMOKE_POSTED", r"(\d+)\|(\d+)\|(-?\d+)\|(-?\d+)"),
        "saves": ("INTERACTIVE_NATIVE_SAVE", r"(\d+)\|([^|\n]+)"),
        "world_commit": ("INTERACTIVE_GPU_WORLD_COMMITTED", r"(\d+)\|(\d+)"),
        "scene_commit": ("INTERACTIVE_GPU_SCENE_COMMITTED", r"(\d+)\|(\d+)"),
        "world_frame": ("INTERACTIVE_WORLD_FRAME", r"(\d+)\|(\d+)\|(\d+)\|\d+\|\d+\|(\d+)\|\d+\|[01]\|\d+"),
        "ui_frame": ("INTERACTIVE_UI_FRAME", r"(\d+)\|(\d+)\|(\d+)\|([^|\n]+)\|(\d+)\|(\d+)\|([^|\n]+)\|([^|\n]+)"),
        "top_frame": ("INTERACTIVE_TOP_PANEL_FRAME", r"(\d+)\|(\d+)\|(\d+)\|(\d+)\|(\d+)\|(\d+)\|([^|\n]+)\|([^|\n]+)"),
    }
    data = {name: records(*spec) for name, spec in specs.items()}
    steps = data["steps"]
    require(len(steps) == len(PHASES), "GameMenu requires all 12 ordered native-input steps")
    rows = [(int(m[1]), m[2], int(m[3]), int(m[4])) for m in steps]
    require([(r[0], r[1]) for r in rows] == list(enumerate(PHASES)), "GameMenu step order or phase changed")
    turn = rows[0][3]
    require(all(0 < r[2] < 2**64 and r[3] == turn for r in rows),
            "GameMenu lost its scene generation or unchanged turn")
    for index in range(1, len(rows)):
        before, after = rows[index-1][2], rows[index][2]
        require(after == before if index == 9 else after > before,
                "GameMenu scene did not advance after input, or advanced after the ignored world key")
    require("INTERACTIVE_GAME_MENU_COMMAND_REJECTED=" not in text,
            "GameMenu command did not reach its settled owner boundary")
    for name, count in (("targets", 6), ("keys", 5), ("shown", 3), ("queued", 3),
                        ("unavailable_shown", 1), ("unavailable", 1), ("quick", 1),
                        ("complete", 1), ("world_key", 2), ("ignored", 1)):
        require(len(data[name]) == count, f"GameMenu has missing or duplicate {name} records")
    shown = data["shown"]
    owner = int(shown[0][1])
    require(all(int(s[1]) == owner and int(s[2]) == turn and int(s[3]) > 0 for s in shown),
            "GameMenu active player, turn or context sequence changed")
    complete = data["complete"][0]
    require(complete.groups() == (str(rows[-1][2]), str(turn)) and complete.start() > steps[-1].end(),
            "GameMenu completion is outside its final returned-world step")
    bounds = (steps[0].start(), complete.end())
    # Other gameplay checkpoints before/after this bounded roundtrip are valid.
    saves = [r for r in data["saves"] if bounds[0] < r.start() < bounds[1]]
    require(len(saves) == 1, "GameMenu native save was missing or repeated during its roundtrip")
    quick = data["quick"][0]
    require(sum(r[2] == quick[3] for r in data["saves"]) == 1,
            "GameMenu quick-save path was written more than once")
    require(len([r for r in data["inner"] if r[1] != "3"]) == len(MENU_STEPS),
            "GameMenu received an extra callback outside its bounded input steps")
    require(len([r for r in data["native_key"] if r[2] == "game-menu"]) == 2,
            "GameMenu received an extra native key outside its bounded input steps")
    hwnd = device = None

    for index, _, generation, _ in rows:
        start = steps[index].end()
        end = steps[index+1].start() if index+1 < len(steps) else complete.end()

        def within(name: str, *, actions_only: bool = False) -> list[re.Match]:
            found = [r for r in data[name] if start < r.start() and r.end() <= end]
            # Hover is allowed, but cannot replace a bounded click/key.
            if actions_only:
                column = 1 if name == "inner" else 2
                found = [r for r in found if int(r[column]) != 3]
            return found

        def expect(name: str, values: tuple[str, ...], *, actions_only: bool = False) -> re.Match:
            row = one(within(name, actions_only=actions_only), f"GameMenu step {index} needs exactly one {name} event")
            require(row.groups() == values, f"GameMenu step {index} has stale or mismatched {name} evidence")
            return row

        # Bind the supplied numeric generation to the latest published scene.
        commits = [r for r in data["scene_commit"] if r.end() < steps[index].start()]
        require(bool(commits) and int(commits[-1][1]) == generation,
                "GameMenu step used a stale or unpublished scene generation")
        scene_commit = one([r for r in data["scene_commit"] if int(r[1]) == generation], "Duplicate scene generation")
        world_commit = one([r for r in data["world_commit"] if int(r[1]) == generation], "Missing/duplicate world commit")
        world_frame = one([r for r in data["world_frame"] if int(r[2]) == generation], "Missing/duplicate world frame")
        menu = index in MENU_STEPS
        frame = one([r for r in data["ui_frame" if menu else "top_frame"] if int(r[2]) == generation],
                    "GameMenu step has no unique original menu/world frame")
        if menu:
            require(frame[4] == "game-menu", "GameMenu input was published for a different modal context")
        else:
            require(int(frame[4]) == owner and not any(int(r[2]) == generation and r[4] == "game-menu" for r in data["ui_frame"]),
                    "GameMenu returned-world step still shows the menu or a different owner")
        if hwnd is None:
            hwnd, device = int(frame[5]), int(frame[6])
        require(hwnd > 0 and device > 0 and int(frame[1]) > 0 and int(world_frame[1]) > 0 and
                int(frame[3]) == turn and int(world_frame[3]) == turn and
                int(frame[5]) == hwnd and int(frame[6]) == device and
                int(scene_commit[2]) == device and int(world_commit[2]) == device and int(world_frame[4]) == device,
                "GameMenu input changed native HWND, GPU device or unchanged turn")
        ordered(world_commit, scene_commit, world_frame, frame, steps[index])

        for inner in within("inner"):
            require(int(inner[4]) == owner and int(inner[5]) == turn,
                    "GameMenu callback lost its owner/turn scope")
            if inner[1] == "3":
                require(inner.groups()[5:8] == ("1", "1", "0"),
                        "GameMenu hover changed modal ownership or queued a command")

        # Reject contradictory extras, not just absence of the expected line.
        for name, allowed in (("targets", index in TARGETS), ("keys", index in KEYS),
                              ("buttons", index in TARGETS), ("posts", index in TARGETS),
                              ("inner", menu), ("native", menu), ("top", index == 0),
                              ("native_key", index in (4, 10)), ("world_key", index in (2, 9)),
                              ("ignored", index == 8), ("world_ignored", False),
                              ("world_input", False), ("closed", False), ("session_stopped", False),
                              ("queued", index in (0, 5, 7)),
                              ("shown", index in (0, 2, 9)), ("unavailable_shown", index == 5),
                              ("unavailable", index == 5), ("quick", index == 7), ("saves", index == 7)):
            relevant = within(name, actions_only=name in ("inner", "native", "top"))
            require(len(relevant) == int(allowed), f"GameMenu step {index} has missing or unexpected {name} action")

        if index == 11:
            ordered(steps[index], complete)
            continue
        if index in TARGETS:
            target = one(within("targets"), "Missing original button target")
            control = int(target[3])
            require(target.groups()[:2] == (str(index), TARGETS[index]) and
                    target.groups()[3:5] == (str(generation), str(turn)) and control > 0,
                    f"GameMenu step {index} target is missing or stale")
            button = expect("buttons", (str(generation), str(control), "1", "0"))
            post = one(within("posts"), "Missing native posted mouse input")
            require(post.groups()[:2] == (str(generation), str(control)), "GameMenu native post used a different scene/control")
            ordered(steps[index], target, button, post)
        else:
            post = expect("keys", (str(index), str(KEYS[index]), str(generation), str(turn)))
            ordered(steps[index], post)

        if index == 0:
            outer = one(within("top", actions_only=True), "Original TopPanel menu click was not consumed")
            local = int(outer[4])
            require(outer.groups()[:3] == (str(generation), "1", str(control)) and outer[5] == "1" and
                    0 < local < 2**32 and control == 2**51 + local,
                    "GameMenu TopPanel input namespace or generation differs")
            queued = expect("queued", ("0", str(owner), str(turn), "GameMenu"))
            opened = within("shown")[0]
            ordered(post, queued, opened, outer)
        elif menu:
            active = "0" if index in (1, 7, 10) else "1"
            pending = "1" if index in (5, 7) else "0"
            inner = expect("inner", ("2" if index in TARGETS else "1", str(control) if index in TARGETS else "27",
                                      "1", str(owner), str(turn), active, active, pending), actions_only=True)
            if index in TARGETS:
                require(control < 2**32, "GameMenu local input identity escaped its namespace")
            outer = expect("native", (str(generation), "1" if index in TARGETS else "0",
                                       str(control) if index in TARGETS else "0", "1"), actions_only=True)
            if index in (5, 7):
                queued = expect("queued", ("2" if index == 5 else "1", str(owner), str(turn),
                                            "LoadMenu" if index == 5 else "QuickSave"))
                ordered(post, queued, inner)
                if index == 5:
                    notice = expect("unavailable_shown", (str(owner), str(turn), "LoadMenu"))
                    unavailable = expect("unavailable", (str(owner), str(turn), "LoadMenu"))
                    ordered(inner, notice, unavailable, outer)
                else:
                    saved = expect("saves", (str(turn), quick[3]))
                    done = expect("quick", (str(owner), str(turn), quick[3]))
                    ordered(inner, saved, done, outer)
            else:
                ordered(post, inner, outer)
            if index in (4, 10):
                key = expect("native_key", (str(generation), "game-menu", "27", "1", active))
                ordered(outer, key)
        elif index in (2, 9):
            opened = within("shown")[0]
            dispatched = expect("world_key", (str(generation), "27", "1"))
            ordered(post, opened, dispatched)
        else:
            # SMOKE_KEY is emitted only after PostMessageW succeeds. The
            # current, non-repeat WM_KEYDOWN must then reach the real window
            # rejection boundary, without being forwarded as a world action.
            ignored = expect("ignored", (str(generation), "81"))
            ordered(post, ignored)
