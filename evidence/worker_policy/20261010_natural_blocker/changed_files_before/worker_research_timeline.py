"""Strict natural research evidence for the versioned full worker/HUD smoke.

This is a record/ordering verifier, not a game simulator. The caller must also
bind the capability to frozen Host sources and inspect the original UI packets.
"""
from __future__ import annotations

import re


CAPABILITY = "INTERACTIVE_WORKER_RESEARCH_CONTRACT=1"
REQUEST_FLAGS = ("smoke", "decisions", "research_tree", "unit_actions", "worker_build",
                 "top_panel", "action_info_panel", "notification_panel")
EXCLUDED_FLAGS = ("game_menu_smoke", "trade_route_smoke", "social_policy_smoke",
                  "social_policy_tenets", "economic_overview_smoke", "tech_award",
                  "combat_smoke", "city_capture_smoke", "declare_war_smoke")
VERIFIER_FILES = ("worker_research_timeline.py", "verify_interactive_decisions.py",
                  "action_info_panel_timeline.py")


def exact_worker_research_profile(request: dict) -> bool:
    return all(request.get(name) is True for name in REQUEST_FLAGS) and all(
        request.get(name) is None or request.get(name) is False for name in EXCLUDED_FLAGS)


def need(condition: bool, reason: str) -> None:
    if not condition:
        raise RuntimeError("Worker research: " + reason)


def has_worker_research_records(text: str) -> bool:
    return any(line.startswith(("INTERACTIVE_WORKER_RESEARCH_", "INTERACTIVE_WORKER_TECH_AWARD_"))
               for line in text.splitlines())


def verify_worker_research_timeline(text: str, *, required: bool) -> dict | None:
    """Reject undeclared records; return exact version-1 events for packet checks."""
    need(type(required) is bool, "contract opt-in must be an explicit boolean")
    if not required:
        need(not has_worker_research_records(text), "records appeared outside the declared frozen contract")
        return None

    def records(name: str, pattern: str):
        prefix = "INTERACTIVE_" + name + "="
        found = list(re.finditer(r"^" + re.escape(prefix) + pattern + r"$", text, re.M))
        need(len(found) == sum(line.startswith(prefix) for line in text.splitlines()),
             "malformed " + name)
        return found

    def one(items, reason):
        need(len(items) == 1, reason)
        return items[0]

    def values(row):
        return tuple(map(int, row.groups()))

    specs = {"WORKER_RESEARCH_CONTRACT": 1, "WORKER_RESEARCH_SELECTED": 8,
             "WORKER_RESEARCH_BEFORE_TURN": 7, "WORKER_RESEARCH_TURN_RETURNED": 8,
             "WORKER_TECH_AWARD_TARGET": 6, "WORKER_TECH_AWARD_RETURNED": 7,
             "WORKER_RESEARCH_TARGET": 5}
    data = {name: records(name, r"\|".join([r"(-?\d+)"] * count)) for name, count in specs.items()}
    for line in text.splitlines():
        if line.startswith(("INTERACTIVE_WORKER_RESEARCH_", "INTERACTIVE_WORKER_TECH_AWARD_")):
            need(line.split("=", 1)[0].removeprefix("INTERACTIVE_") in specs,
                 "unknown natural research record")
    capability = one(data["WORKER_RESEARCH_CONTRACT"], "missing or repeated capability")
    need(capability[1] == "1", "unsupported capability version")
    start = one(records("GAME_STARTED", r"(\d+)\|(\d+)\|(\d+)\|(\d+)"), "missing unique game start")
    initial_turn, owner, width, height = values(start)
    finished = one(records("WORKER_BUILD_COMPLETED", r"(\d+)\|(\d+)\|(\d+)\|(\d+)\|(\d+)"),
                   "missing unique worker completion")
    final_turn = int(finished[5])
    need(0 <= owner < 64 and width > 0 and height > 0 and 1 <= final_turn - initial_turn <= 32,
         "invalid owner or finite construction interval")
    before = data["WORKER_RESEARCH_BEFORE_TURN"]
    returned = data["WORKER_RESEARCH_TURN_RETURNED"]
    selected = data["WORKER_RESEARCH_SELECTED"]
    targets = data["WORKER_RESEARCH_TARGET"]
    awards = data["WORKER_TECH_AWARD_TARGET"]
    award_returns = data["WORKER_TECH_AWARD_RETURNED"]
    need([int(row[1]) for row in before] == list(range(initial_turn, final_turn)) and
         [int(row[1]) for row in returned] == list(range(initial_turn + 1, final_turn + 1)),
         "research samples do not cover each consecutive worker turn")
    need(selected and len(selected) == len(targets) + 1, "research selections and continuation targets differ")
    need(len(awards) == len(award_returns) <= final_turn - initial_turn,
         "award targets/returns differ or exceed the turn bound")
    need(len({int(row[3]) for row in awards}) == len(awards) and
         len({int(row[5]) for row in awards}) == len(awards), "technology or award generation repeated")
    need(not records("RESEARCH_COMPLETION_FIXTURE", r".*") and
         not records("TECH_AWARD_TARGET", r".*") and not records("RESEARCH_COMPLETION_VERIFIED", r".*"),
         "forced research fixture was mixed into natural completion")
    accepted = records("END_TURN_ACCEPTED", r"(\d+)")
    next_turns = records("NEXT_HUMAN_TURN", r"(\d+)\|(\d+)")
    observed = records("WORKER_BUILD_OBSERVED", r"(\d+)\|(\d+)\|(\d+)\|(\d+)\|(\d+)\|(-?\d+)\|(\d+)\|(-?\d+)\|(-?\d+)")
    need([int(row[1]) for row in accepted] == list(range(initial_turn, final_turn)) and
         [int(row[1]) for row in next_turns] == [int(row[1]) for row in returned] and
         [int(row[1]) for row in observed] == [int(row[1]) for row in returned],
         "accepted/returned/worker turns do not match research turns")
    world_frames = records("WORLD_FRAME", r"(\d+)\|(\d+)\|(\d+)\|(\d+)\|(\d+)\|(\d+)\|(\d+)\|([01])\|(\d+)")
    commits = records("GPU_SCENE_COMMITTED", r"(\d+)\|(\d+)")
    hud_frames = records("ACTION_INFO_PANEL_FRAME", r"(\d+)\|(\d+)\|(\d+)\|(\d+)\|(\d+)\|(\d+)\|[^\r\n]+")
    hud_targets = records("ACTION_INFO_SMOKE_TARGET", r"([^|\r\n]+)\|(-?\d+)\|(-?\d+)\|(\d+)\|(\d+)\|(\d+)")
    ui_frames = records("UI_FRAME", r"(\d+)\|(\d+)\|(\d+)\|([^|\r\n]+)\|(\d+)\|(\d+)\|([^|\r\n]+)\|([^|\r\n]+)")
    posts = records("SMOKE_POSTED", r"(\d+)\|(\d+)\|(-?\d+)\|(-?\d+)")
    buttons = records("SMOKE_BUTTON", r"(\d+)\|(\d+)\|([0-5])\|([01])")
    inputs = records("UI_NATIVE_INPUT", r"(\d+)\|([0-5])\|(\d+)\|([01])")
    window_inputs = list(re.finditer(r"^UI_WINDOW_INPUT=(\d+)\|(\d+)\|(\d+)\|([01])\|(\d+)\|(\d+)\|([01])\|([01])\|(-?\d+)\|(\d+)$", text, re.M))
    shown = records("TECH_AWARD_SHOWN", r"(\d+)\|(\d+)\|(\d+)\|(\d+)\|([01])")
    closed = records("TECH_AWARD_CLOSED", r"(\d+)\|(\d+)\|0\|STATE_UNCHANGED")
    queued = list(re.finditer(r"^INTERACTIVE_UI_QUEUED=68\|(\d+)\|(\d+)\|(\d+)$", text, re.M))
    need(len(window_inputs) == sum(line.startswith("UI_WINDOW_INPUT=") for line in text.splitlines()) and
         len(queued) == sum(line.startswith("INTERACTIVE_UI_QUEUED=68|") for line in text.splitlines()),
         "malformed original popup dispatch or natural award queue")
    need(len(shown) == len(closed) == len(queued) == len(awards), "natural popup lifecycle count differs")

    def world(generation, turn, position, after=-1):
        frame = one([row for row in world_frames if int(row[2]) == generation], "world generation is missing or repeated")
        commit = one([row for row in commits if int(row[1]) == generation], "GPU generation is missing or repeated")
        hud = one([row for row in hud_frames if int(row[2]) == generation], "return has no unique original HUD frame")
        need(int(frame[3]) == turn and int(hud[3]) == turn and int(hud[4]) == owner and
             int(frame[6]) == int(commit[2]) == int(hud[6]) > 0 and
             after < commit.start() < frame.start() < hud.start() < position,
             "world/HUD return lost generation, owner, turn, device or order")

    def callback(target, generation, key, turn, context, timer_before, timer_after):
        frame = one([row for row in ui_frames if int(row[2]) == generation and row[4] == context],
                    "original callback has no unique native popup frame")
        post = one([row for row in posts if (int(row[1]), int(row[2])) == (generation, key)],
                   "callback has no unique physical coordinate post")
        button = one([row for row in buttons if (int(row[1]), int(row[2])) == (generation, key)],
                     "callback has no unique physical button record")
        native = one([row for row in inputs if int(row[1]) == generation and row[2] == "1"],
                     "callback was not consumed once in its generation")
        timer = one([row for row in window_inputs if post.end() < row.start() < native.start() and
                     row[2] == "2" and row[3] == native[3]], "callback lacks its exact timer/RNG dispatch")
        need(int(frame[3]) == turn and button.groups()[2:] == ("1", "0") and native[4] == "1" and
             frame.end() < target.start() < button.start() < post.start() < timer.start() < native.start() and
             timer[4] == "1" and timer[5] == timer[6] and
             (int(timer[7]), int(timer[8]), int(timer[9])) == (timer_before, timer_after, turn) and int(timer[10]) > 0,
             "callback lost original input, turn, timer, RNG or ordering")
        if context == "tech-award":
            need(int(native[3]) == key, "Continue consumed a different callback")
        return {"context": context, "sequence": int(frame[1]), "turn": turn, "owner": owner,
                "generation": generation, "key": key, "native_key": int(native[3]),
                "client": [int(post[3]), int(post[4])]}, native

    selection_proof, award_proof, continuation_proof, turn_proof, callback_proof = [], [], [], [], []
    initial = values(selected[0])
    need(initial[0] == initial_turn and initial[1] == owner and initial[2] >= 0 and
         initial[3] > 0 and initial[4] == initial[2] and initial[5] == 0 and min(initial[6:]) >= 0 and
         capability.end() < selected[0].start() < before[0].start(), "invalid initial unowned research selection")
    world(initial[3], initial_turn, selected[0].start())
    initial_target = one(records("DECISION_RESEARCH_TARGET", r"(\d+)\|(\d+)"), "missing original initial research choice")
    initial_frames = [row for row in ui_frames if row[4] == "research-tree" and row.end() < initial_target.start()]
    need(initial_frames and int(initial_target[1]) == initial[2], "initial research identity differs from stock tree callback")
    initial_frame = initial_frames[-1]
    initial_callback, initial_native = callback(initial_target, int(initial_frame[2]), int(initial_target[2]), initial_turn, "research-tree", 1, 1)
    initial_callback["technology"] = initial[2]; callback_proof.append(initial_callback)
    escape = one([row for row in re.finditer(r"^INTERACTIVE_UI_NATIVE_KEY=(\d+)\|research-tree\|27\|1\|0$", text, re.M)
                  if initial_native.end() < row.start() < selected[0].start()],
                 "original research tree did not close with Escape")
    need(initial_native.end() < escape.start() < selected[0].start(), "initial selection did not follow original tree close")

    for row in selected:
        val = values(row)
        need(val[1] == owner and val[2] >= 0 and val[3] > 0 and val[4] == val[2] and val[5] == 0 and min(val[6:]) >= 0,
             "selection is not its exact active unowned SDK research")
        selection_proof.append(dict(zip(("turn", "owner", "technology", "generation", "current_research", "has_technology", "progress", "left"), val)))
    for index, (pre, post, accept, next_turn, worker) in enumerate(zip(before, returned, accepted, next_turns, observed)):
        b, a = values(pre), values(post)
        need(b[1] == a[1] == owner and b[2] == a[2] >= 0 and b[4] == 0 and a[5] in (0, 1) and
             b[3] > 0 and a[3] > b[3] and min(b[5:]) >= 0 and min(a[6:]) >= 0 and a[4] >= -1 and
             pre.end() < accept.start() < next_turn.start() < post.start() < worker.start(),
             "pre/returned research identity or turn order differs")
        chosen = [row for row in selected if row.end() < pre.start()]
        need(chosen and int(chosen[-1][3]) == b[2], "end-turn research was never selected through the original UI")
        prior = values(chosen[-1]) if index == 0 or chosen[-1].start() > returned[index - 1].end() else values(returned[index - 1])
        need(prior[4] == b[2] and prior[5] == 0 and (prior[2], prior[6], prior[7]) == (b[2], b[5], b[6]),
             "research changed between observed return/selection and end turn")
        hud = one([row for row in hud_targets if row[1] == "end-turn" and int(row[6]) == b[0]], "missing exact end-turn HUD target")
        need(int(hud[5]) == b[3] and hud.start() < accept.start(), "research before-turn generation differs from its HUD command")
        world(a[3], a[0], post.start(), next_turn.end())
        matching_awards = [row for row in awards if (int(row[1]), int(row[3])) == (a[0], a[2])]
        if a[5] == 0:
            remaining_advanced = a[7] < b[6] if b[6] > 0 else a[7] == 0
            need(a[4] == a[2] and a[6] > b[5] and remaining_advanced and not matching_awards,
                 "incomplete research did not advance with the same selected technology")
        else:
            target = one(matching_awards, "owned technology lacks its unique natural Continue")
            t = values(target)
            ar = one([row for row in award_returns if (int(row[1]), int(row[3])) == (a[0], a[2])], "missing exact award return")
            av = values(ar)
            need(t[1] == owner and t[5] == 1 and av[:3] == a[:3] and av[3] == a[3] and av[4] == a[4] and
                 av[5:] == (1, 0) and a[4] != a[2] and a[6] >= b[5] and a[7] == 0 and
                 next_turn.end() < target.start() < ar.start() < post.start(), "natural completion changed its owner, turn or completed research")
            queued_row = one([row for row in queued if values(row) == (owner, 0, a[2])], "SDK award queue payload differs")
            shown_row = one([row for row in shown if values(row) == (owner, 0, a[2], a[0], 1)], "original award shown payload differs")
            cb, native = callback(target, t[4], t[3], t[0], "tech-award", 1, 0)
            close = one([row for row in closed if values(row) == (t[3], t[0])], "Continue did not close with unchanged SDK state")
            need(accept.end() < queued_row.start() < shown_row.start() < target.start() and
                 target.end() < close.start() < native.start() < ar.start(), "award queue/Continue/return order differs")
            world(av[3], av[0], ar.start(), native.end())
            cb["technology"] = t[2]; callback_proof.append(cb)
            award_proof.append({"turn": t[0], "owner": owner, "technology": t[2], "key": t[3],
                                "generation": t[4], "return_generation": av[3], "current_research": av[4]})
        turn_proof.append({"before": list(b), "returned": list(a)})
    need(len(award_proof) == len(awards), "untracked natural award remains")
    for target, selection in zip(targets, selected[1:]):
        t, chosen = values(target), values(selection)
        need(t[0] == chosen[0] and t[1] == chosen[1] == owner and t[2] == chosen[2] and
             t[0] < final_turn and chosen[3] > t[4] and target.end() < selection.start(),
             "continuation selection changed its identity/turn or did not return")
        completed = one([row for row in returned if int(row[1]) == t[0] and row[6] == "1"], "continuation lacks a same-turn completed research")
        worker = one([row for row in observed if int(row[1]) == t[0]], "continuation has no preceding worker observation")
        hud = one([row for row in hud_targets if row[1] == "research-continuation" and int(row[6]) == t[0]], "continuation has no exact SDK research-blocker HUD target")
        need(hud[2] == "1" and int(hud[3]) >= 0 and completed.end() < worker.start() < hud.start() < target.start() and
             t[2] not in [int(row[3]) for row in awards if row.start() < target.start()],
             "continuation bypassed its research blocker/worker observation or selected owned research")
        cb, native = callback(target, t[4], t[3], t[0], "research", 0, 0)
        cb["technology"] = t[2]; callback_proof.append(cb)
        world(chosen[3], chosen[0], selection.start(), native.end())
        continuation_proof.append({"turn": t[0], "owner": owner, "technology": t[2], "key": t[3],
                                   "generation": t[4], "selected_generation": chosen[3],
                                   "hud_generation": int(hud[5]), "hud_key": int(hud[4])})
    need(len([row for row in hud_targets if row[1] == "research-continuation"]) == len(targets),
         "unpaired research continuation HUD command")
    need(returned[-1].end() < finished.start(), "worker finished before its last research observation")
    decision_before = one(records("DECISION_BEFORE_TURN", r"((?:-?\d+,){11}-?\d+)"), "missing original first decision sample")
    decision_after = one(records("DECISION_AFTER_TURN", r"((?:-?\d+,){11}-?\d+)"), "missing original returned decision sample")
    db, da = tuple(map(int, decision_before[1].split(","))), tuple(map(int, decision_after[1].split(",")))
    b, a = values(before[0]), values(returned[0])
    need(db[0] == initial_turn and da[0] == initial_turn + 1 and db[2:6] == da[2:6] and
         (db[2], db[5], db[9], db[10]) == (owner, b[2], b[5], b[6]) and
         (da[2], da[5], da[9], da[10]) == (owner, a[2], a[6], a[7]) and
         da[1] > db[1] and da[6] == 1 and da[7] > db[7] and da[8] == db[8] and
         decision_before.start() < selected[0].start() and returned[0].end() < decision_after.start() < observed[0].start(),
         "initial/first returned city and research decision samples differ from the verified worker turn")
    return {"contract_version": 1, "owner": owner, "initial_turn": initial_turn, "final_turn": final_turn,
            "selections": selection_proof, "turns": turn_proof, "awards": award_proof,
            "continuations": continuation_proof, "callback_inputs": callback_proof}
