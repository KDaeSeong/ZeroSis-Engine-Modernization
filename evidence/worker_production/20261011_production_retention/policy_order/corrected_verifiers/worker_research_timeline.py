"""Strict natural research evidence for the versioned full worker/HUD smoke.

This is a record/ordering verifier, not a game simulator. The caller must also
bind the capability to frozen Host sources and inspect the original UI packets.
"""
from __future__ import annotations

import re


CAPABILITY = "INTERACTIVE_WORKER_RESEARCH_CONTRACT=1"
POLICY_CAPABILITY = "INTERACTIVE_WORKER_POLICY_CONTRACT=1"
PRODUCTION_CAPABILITY = "INTERACTIVE_WORKER_PRODUCTION_CONTRACT=1"
UNSTACK_CAPABILITY = "INTERACTIVE_WORKER_UNSTACK_CONTRACT=1"
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


def verify_worker_policy_inventory(before: dict, after: dict, cycle: dict) -> dict:
    """Only the first paid Tradition branch/opener is covered by this contract."""
    for value in (before, after):
        need(type(value) is dict and value.get('schema') == 'ZEROSIS_SOCIAL_POLICY_SDK_INVENTORY_V1' and
             value.get('source') == 'SDK:Policies/PolicyBranches/JONSCulture', 'policy inventory source/schema differs')
        for name in ('activePlayer', 'turn', 'elapsed', 'culture', 'nextCost', 'freePolicies', 'freeTenets'):
            need(type(value.get(name)) is int and value[name] >= 0, 'invalid policy inventory ' + name)
        need(value['activePlayer'] < 64 and type(value.get('ideology')) is int and value['ideology'] >= -1 and
             value.get('policySaving') is False and value['freePolicies'] == 0, 'policy saving/free awards are not permitted')
        for name, reference, flags in (('policies', 'branch', ('has', 'canAdopt', 'blocked')),
                                        ('branches', 'freePolicy', ('unlocked', 'canUnlock', 'blocked'))):
            entries = value.get(name)
            need(type(entries) is list and 0 < len(entries) <= 2048, 'policy inventory is missing or unbounded')
            need(all(type(row) is dict and type(row.get('id')) is int and row['id'] >= 0 and
                     type(row.get(reference)) is int and row[reference] >= -1 and
                     all(type(row.get(flag)) is bool for flag in flags) for row in entries), 'malformed policy inventory entry')
            ids = [row['id'] for row in entries]
            need(ids == sorted(set(ids)), 'duplicate or unordered policy inventory IDs')
            if name == 'policies':
                need(all(type(row.get('level')) is int and row['level'] >= 0 for row in entries), 'invalid policy level')
    need(all(before[k] == after[k] for k in ('activePlayer', 'turn', 'elapsed', 'freeTenets', 'ideology')) and
         (before['activePlayer'], before['turn']) == (cycle['owner'], cycle['turn']) and
         before['culture'] == cycle['before_culture'] >= before['nextCost'] == cycle['cost'] > 0 and
         after['culture'] == cycle['after_culture'] == before['culture'] - before['nextCost'],
         'paid policy owner/turn/culture debit differs from its SDK inventory')
    old_p, new_p = ({r['id']: r for r in value['policies']} for value in (before, after))
    old_b, new_b = ({r['id']: r for r in value['branches']} for value in (before, after))
    need(old_p.keys() == new_p.keys() and old_b.keys() == new_b.keys() and 0 in old_b and 6 in old_p,
         'policy/branch identity inventory changed')
    need(old_b[0]['freePolicy'] == 6 and old_b[0]['canUnlock'] and not old_b[0]['unlocked'] and
         not old_b[0]['blocked'] and not old_p[6]['has'] and not old_p[6]['blocked'],
         'first paid Tradition opener was not legal and unowned')
    for previous, current, owned, changed, stable in (
            (old_p, new_p, 'has', 6, ('branch', 'blocked', 'level')),
            (old_b, new_b, 'unlocked', 0, ('freePolicy', 'blocked'))):
        need(all(all(row[k] == current[key][k] for k in stable) for key, row in previous.items()),
             'policy identity/blocking changed outside adoption')
        need([key for key in previous if previous[key][owned] != current[key][owned]] == [changed] and
             not previous[changed][owned] and current[changed][owned], 'unrelated or missing policy acquisition')
    return {'branch_added': 0, 'opener_added': 6, 'culture_before': before['culture'],
            'cost': before['nextCost'], 'culture_after': after['culture']}


def verify_worker_policy_timeline(text: str, *, required: bool) -> dict | None:
    """Bind zero/one natural paid adoption to the existing completed worker timeline."""
    need(type(required) is bool, 'policy contract opt-in must be an explicit boolean')
    prefix = 'INTERACTIVE_WORKER_POLICY_'
    if not required:
        need(not any(line.startswith(prefix) for line in text.splitlines()), 'undeclared natural policy records')
        return None

    def records(name, pattern):
        tag = 'INTERACTIVE_' + name + '='
        result = list(re.finditer('^' + tag + pattern + '$', text, re.M))
        need(len(result) == sum(line.startswith(tag) for line in text.splitlines()), 'malformed ' + name)
        return result

    def one(items, reason):
        need(len(items) == 1, reason)
        return items[0]

    def ints(count):
        return r'\|'.join([r'(-?\d+)'] * count)

    def numbers(row):
        return tuple(map(int, row.groups()))

    patterns = {'CONTRACT': ints(1), 'COMPLETE': ints(1), 'BEGIN': ints(8), 'ADOPTED': ints(9),
                'RETURNED': ints(8), 'TARGET': r'(\d+)\|([^|\r\n]+)\|' + ints(7),
                'WORKER_STATE': r'(\d+)\|([^|\r\n]+)\|' + ints(13),
                'INVENTORY': r'(\d+)\|([^|\r\n]+)\|([^|\r\n]+)'}
    data = {name: records('WORKER_POLICY_' + name, pattern) for name, pattern in patterns.items()}
    need(all(line.split('=', 1)[0][len(prefix):] in patterns for line in text.splitlines() if line.startswith(prefix)),
         'unknown natural policy marker')
    capability = one(data['CONTRACT'], 'missing/repeated policy capability')
    complete = one(data['COMPLETE'], 'missing/repeated policy completion')
    need(capability[1] == '1' and complete[1] in ('0', '1') and capability.end() < complete.start(), 'invalid policy version/count/order')
    research = verify_worker_research_timeline(text, required=True)
    finished = one(records('WORKER_BUILD_COMPLETED', ints(5)), 'missing completed worker')
    need(finished.end() < complete.start(), 'policy completion precedes worker completion')
    allowed = ('INTERACTIVE_SOCIAL_POLICY_COMMAND=', 'INTERACTIVE_SOCIAL_POLICY_SHOWN=', 'INTERACTIVE_SOCIAL_POLICY_INPUT=')
    need(not any(line.startswith('INTERACTIVE_SOCIAL_POLICY_') and not line.startswith(allowed) for line in text.splitlines()),
         'forced culture or separate policy fixture mixed into natural adoption')
    commands = records('SOCIAL_POLICY_COMMAND', ints(5))
    shown = records('SOCIAL_POLICY_SHOWN', ints(5))
    queued_policy = [r for r in records('UI_QUEUED', ints(4)) if r[1] == '17']
    opened_policy = [r for r in records('UI_OPENED', r'(\d+)\|([^|\r\n]+)') if r[2] == 'social-policy']
    policy_inputs = records('SOCIAL_POLICY_INPUT', r'(\d+)\|(\d+)\|0\|([01])\|([01])\|([01])\|(\d+)\|([01])')
    hud_targets = records('ACTION_INFO_SMOKE_TARGET', r'([^|\r\n]+)\|' + ints(5))
    policy_hud = [r for r in hud_targets if r[1] == 'policy-continuation']
    count = int(complete[1])
    need(all(len(data[name]) == count * amount for name, amount in
             (('BEGIN', 1), ('ADOPTED', 1), ('RETURNED', 1), ('TARGET', 3), ('WORKER_STATE', 4), ('INVENTORY', 2))) and
         len(commands) == len(shown) == len(policy_hud) == len(queued_policy) == len(opened_policy) == count and
         len(policy_inputs) == 3 * count,
         'policy cycle/command/input/inventory counts differ')
    proof = {'contract_version': 1, 'completed_cycle_count': count, 'cycles': [], 'callback_inputs': []}
    if not count:
        return proof
    begin, adopted, returned = data['BEGIN'][0], data['ADOPTED'][0], data['RETURNED'][0]
    cycle, turn, owner, notification, generation, culture, cost, free = numbers(begin)
    av, rv = numbers(adopted), numbers(returned)
    need(cycle == 1 and owner == research['owner'] and research['initial_turn'] <= turn < research['final_turn'] and
         notification >= 0 and generation > 0 and culture >= cost > 0 and free == 0 and
         av[:5] == (1, turn, owner, 0, 0) and av[5:8] == (culture, cost, culture - cost) and
         rv[:3] == (1, turn, owner) and ((rv[4:7] == (-1, -1, 1) and rv[7] >= 0) or
                                        (rv[4] == 1 and rv[5] >= 0 and rv[6:] == (0, -1))) and
         capability.end() < begin.start() < adopted.start() < returned.start() < finished.start() < complete.start(),
         'policy owner/turn/cost/readiness boundary differs')
    targets, states, inventory = data['TARGET'], data['WORKER_STATE'], data['INVENTORY']
    need([r[2] for r in targets] == ['branch', 'confirm', 'close'] and
         [r[2] for r in states] == ['before', 'selected', 'adopted', 'returned'] and
         [r[2] for r in inventory] == ['before', 'after'] and
         all(r[1] == '1' for r in targets + states + inventory), 'policy phase identity/order differs')
    tv = [tuple(map(int, r.groups()[2:])) for r in targets]
    need(all(t[:2] == (0, 0) and min(t[2:5]) > 0 and t[5:] == (turn, owner) for t in tv) and
         generation < tv[0][3] < tv[1][3] < tv[2][3] == av[8] < rv[3], 'policy target identity/revision/generation differs')
    state_values = [tuple(map(int, r.groups()[2:])) for r in states]
    need(all(v[:2] == (turn, owner) for v in state_values) and
         [v[2] for v in state_values] == [generation, tv[1][3], av[8], rv[3]] and
         all(v[3:] == state_values[0][3:] for v in state_values), 'tracked worker changed across policy phases')
    fixture = one(records('WORKER_BUILD_FIXTURE', ints(6)), 'missing worker fixture')
    target_worker = one(records('WORKER_BUILD_TARGET', ints(6)), 'missing worker build target')
    tracked = state_values[0][3:]
    fv, wt = numbers(fixture), numbers(target_worker)
    need(tracked[:3] == fv[:3] == wt[:3] and tracked[4] == fv[4] > 0 and tracked[6] == fv[5] and
         tracked[7:9] == (wt[3], fv[2]) and min(tracked[3], tracked[9]) >= 0, 'policy observes a different worker/build')
    if turn == research['initial_turn']:
        prior = one(records('WORKER_BUILD_STARTED', ints(5)), 'missing worker start')
        need(numbers(prior) == tracked[:4] + (tracked[5],), 'policy worker differs from its initial SDK start')
    else:
        prior = one([r for r in records('WORKER_BUILD_OBSERVED', ints(9)) if int(r[1]) == turn], 'missing same-turn worker observation')
        need(numbers(prior)[1:] == tracked[:4] + (tracked[5], tracked[9], tracked[7], tracked[8]),
             'policy worker differs from its same-turn SDK observation')
    hud = policy_hud[0]
    key_base = 1 << 52
    blocker, notice, hud_key, hud_generation, hud_turn = map(int, hud.groups()[1:])
    need((blocker, notice, hud_generation, hud_turn) == (0, notification, generation, turn) and
         key_base < hud_key < key_base + (1 << 32) and prior.end() < begin.start() < inventory[0].start() <
         states[0].start() < hud.start(), 'policy blocker/notification/HUD ordering differs')
    worlds = records('WORLD_FRAME', ints(9))
    commits = records('GPU_SCENE_COMMITTED', ints(2))
    hud_frames = records('ACTION_INFO_PANEL_FRAME', ints(6) + r'\|([^|\r\n]+)\|([^|\r\n]+)')
    ui_frames = records('UI_FRAME', ints(3) + r'\|([^|\r\n]+)\|' + ints(2) + r'\|([^|\r\n]+)\|([^|\r\n]+)')
    posts = records('SMOKE_POSTED', ints(4)); buttons = records('SMOKE_BUTTON', ints(4))
    native_inputs = records('UI_NATIVE_INPUT', ints(4))
    panel_inputs = records('ACTION_INFO_PANEL_INPUT', ints(6))
    panel_callbacks = records('ACTION_INFO_INPUT', ints(7))
    timers = list(re.finditer(r'^UI_WINDOW_INPUT=' + ints(10) + '$', text, re.M))
    need(len(timers) == sum(line.startswith('UI_WINDOW_INPUT=') for line in text.splitlines()), 'malformed popup timer dispatch')

    def world(gen, before, after=-1, panel=False):
        frame = one([r for r in worlds if int(r[2]) == gen], 'missing/repeated policy world generation')
        commit = one([r for r in commits if int(r[1]) == gen], 'missing policy GPU commit')
        need(int(frame[3]) == turn and int(frame[6]) == int(commit[2]) > 0 and
             after < commit.start() < frame.start() < before, 'policy world turn/device/order differs')
        if panel:
            h = one([r for r in hud_frames if int(r[2]) == gen], 'missing policy HUD generation')
            need((int(h[3]), int(h[4]), int(h[6])) == (turn, owner, int(frame[6])) and
                 frame.end() < h.start() < before, 'policy HUD owner/turn/device/order differs')
            return h
        return frame

    initial_hud = world(generation, begin.start(), panel=True)
    hp = one([r for r in posts if numbers(r)[:2] == (generation, hud_key)], 'missing policy HUD post')
    hb = one([r for r in buttons if numbers(r)[:2] == (generation, hud_key)], 'missing policy HUD button')
    hi = one([r for r in panel_inputs if numbers(r)[:3] == (generation, 1, hud_key)], 'missing policy HUD consumption')
    callback = one([r for r in panel_callbacks if hp.end() < r.start() < hi.start()],
                   'missing/repeated policy original HUD callback')
    timer = one([r for r in timers if hp.end() < r.start() < hi.start()],
                'missing/repeated policy original HUD timer dispatch')
    ti = numbers(timer)
    need(numbers(callback) == (2, hud_key-key_base, 1, owner, turn, 1, 0) and
         ti[:4] == (0, 2, hud_key-key_base, 1) and
         ti[4] == ti[5] and ti[6:9] == (0, 0, turn) and ti[9] > 0,
         'policy original HUD callback scope/RNG/timer differs')
    need(numbers(hb)[2:] == (1, 0) and numbers(hi)[3:] == (hud_key-key_base, 1, 0) and
         hud.end() < hb.start() < hp.start() < hi.start() < targets[0].start(), 'policy HUD HWND callback differs')
    # ActivateNotification queues and opens the original popup before the
    # action-info callback reports its consumed input to the world loop.
    need(numbers(queued_policy[0]) == (17, owner, -1, -1) and
         numbers(shown[0]) == (owner, owner, -1, turn, 1) and int(opened_policy[0][1]) > 0 and
         hp.end() < callback.start() < timer.start() < queued_policy[0].start() < shown[0].start() < opened_policy[0].start() <
         hi.start() < targets[0].start(), 'policy popup did not follow the original notification')
    callbacks = [{'context': 'action-info-panel', 'phase': 'hud', 'sequence': int(initial_hud[1]),
                  'turn': turn, 'owner': owner, 'generation': generation, 'key': hud_key-key_base,
                  'native_key': hud_key-key_base, 'world_key': hud_key, 'client': [int(hp[3]), int(hp[4])]}]
    consumed = []
    for index, (target, val) in enumerate(zip(targets, tv)):
        key, gen, revision = val[2:5]
        frame = one([r for r in ui_frames if int(r[2]) == gen], 'missing policy original popup frame')
        post = one([r for r in posts if numbers(r)[:2] == (gen, key)], 'missing policy physical coordinate post')
        button = one([r for r in buttons if numbers(r)[:2] == (gen, key)], 'missing policy physical button')
        native = one([r for r in native_inputs if int(r[1]) == gen and int(r[2]) == 1], 'missing policy consumed callback')
        policy_input = policy_inputs[index]
        timer = one([r for r in timers if post.end() < r.start() < native.start() and int(r[3]) == key], 'missing policy timer dispatch')
        after_timer = 0 if index == 2 else 1
        need((int(frame[1]), int(frame[3]), frame[4]) == (revision, turn, 'social-policy') and
             (frame[5], frame[6]) == (initial_hud[5], initial_hud[6]) and
             numbers(button)[2:] == (1, 0) and numbers(native)[1:] == (1, key, 1) and
             numbers(policy_input) == (2, key, 1, after_timer, after_timer, turn, int(index == 1)) and
             numbers(timer)[1:4] == (2, key, 1) and numbers(timer)[6:9] == (1, after_timer, turn) and
             int(timer[1]) > 0 and int(timer[10]) > 0 and (index == 1 or timer[5] == timer[6]) and
             frame.end() < target.start() < button.start() < post.start() < policy_input.start() < timer.start() < native.start(),
             'policy callback/source generation, HWND, payload, timer or dispatch order differs')
        world(gen, target.start(), consumed[-1].end() if consumed else shown[0].end())
        consumed.append(native)
        callbacks.append({'context': 'social-policy', 'phase': target[2], 'sequence': revision, 'turn': turn,
                          'owner': owner, 'generation': gen, 'key': key, 'native_key': key,
                          'client': [int(post[3]), int(post[4])]})
        if index == 1:
            need(numbers(commands[0]) == (owner, 0, 0, 1, turn) and post.end() < commands[0].start() < policy_input.start(),
                 'paid policy SDK command is not exactly within Yes dispatch')
    need(consumed[0].end() < states[1].start() < targets[1].start() and consumed[1].end() < adopted.start() <
         inventory[1].start() < states[2].start() < targets[2].start() and consumed[2].end() < states[3].start() < returned.start(),
         'policy selected/adopted/returned observations are out of order')
    returned_hud = world(rv[3], states[3].start(), consumed[2].end(), panel=True)
    need(returned_hud.groups()[4:6] == initial_hud.groups()[4:6], 'policy return replaced its owned HWND/device')
    next_research = one([r for r in records('WORKER_RESEARCH_BEFORE_TURN', ints(7)) if int(r[1]) == turn],
                        'policy did not continue into its same-turn research/end-turn path')
    need(returned.end() < next_research.start() and int(next_research[4]) >= rv[3] and
         (rv[7] == -1 or int(next_research[3]) == rv[7]), 'policy return did not continue with its selected research')
    cycle_proof = {'cycle': 1, 'turn': turn, 'owner': owner, 'notification': notification,
                   'before_culture': culture, 'cost': cost, 'after_culture': av[7],
                   'hud_generation': generation, 'hud_key': hud_key, 'branch_generation': tv[0][3],
                   'returned_generation': rv[3], 'begin_position': begin.start(), 'hud_position': hud.start(),
                   'return_position': returned.start(), 'worker_state': list(tracked),
                   'inventories': {r[2]: r[3] for r in inventory}}
    proof['cycles'].append(cycle_proof); proof['callback_inputs'] = callbacks
    return proof


def verify_worker_production_timeline(text: str, *, required: bool, unstack_required: bool = False) -> dict | None:
    """Validate one naturally completed unit and the original next-order callback."""
    need(type(required) is bool, 'production contract opt-in must be an explicit boolean')
    need(type(unstack_required) is bool and (not unstack_required or required), 'unstack contract requires explicit production capability')
    prefix = 'INTERACTIVE_WORKER_PRODUCTION_'
    if not required:
        need(not any(line.startswith(prefix) for line in text.splitlines()), 'undeclared natural production records')
        need(not any(line.startswith('INTERACTIVE_WORKER_UNSTACK_') for line in text.splitlines()), 'undeclared unstack records')
        return None

    def ints(count):
        return r'\|'.join([r'(-?\d+)'] * count)

    def records(name, pattern):
        tag = 'INTERACTIVE_' + name + '='
        result = list(re.finditer('^' + tag + pattern + '$', text, re.M))
        need(len(result) == sum(line.startswith(tag) for line in text.splitlines()), 'malformed ' + name)
        return result

    def one(items, reason):
        need(len(items) == 1, reason)
        return items[0]

    def numbers(row):
        return tuple(map(int, row.groups()))

    patterns = {'CONTRACT': ints(1), 'COMPLETE': ints(1), 'BASELINE': ints(8),
                'FINISHED': ints(7), 'BEGIN': ints(7), 'TARGET': ints(8),
                'RETURNED': ints(10), 'COMMAND': ints(11),
                'WORKER_STATE': r'(\d+)\|([^|\r\n]+)\|' + ints(13),
                'QUEUE': r'(\d+)\|([^|\r\n]+)\|' + ints(8),
                'SCENES': r'(\d+)\|([^|\r\n]+)\|([^|\r\n]+)'}
    data = {name: records('WORKER_PRODUCTION_' + name, pattern) for name, pattern in patterns.items()}
    need(all(line.split('=', 1)[0][len(prefix):] in patterns for line in text.splitlines() if line.startswith(prefix)),
         'unknown natural production marker')
    capability = one(data['CONTRACT'], 'missing/repeated production capability')
    complete = one(data['COMPLETE'], 'missing/repeated production completion')
    baseline = one(data['BASELINE'], 'missing/repeated original production baseline')
    need(capability[1] == '1' and complete[1] in ('0', '1'), 'invalid production version/count')
    research = verify_worker_research_timeline(text, required=True)
    verify_worker_policy_timeline(text, required=True)
    finished_worker = one(records('WORKER_BUILD_COMPLETED', ints(5)), 'missing completed worker')
    decision = one(records('DECISION_BEFORE_TURN', r'((?:-?\d+,){11}-?\d+)'), 'missing first decision sample')
    initial_target = one(records('DECISION_PRODUCTION_TARGET', ints(3)), 'missing original initial production target')
    initial = tuple(map(int, decision[1].split(',')))
    bv = numbers(baseline)
    initial_turn, owner, city, initial_unit, length, production, needed, generation = bv
    before_turns = records('WORKER_RESEARCH_BEFORE_TURN', ints(7))
    need((initial_turn, owner) == (research['initial_turn'], research['owner']) and
         (city, initial_unit) == numbers(initial_target)[:2] == initial[3:5] and initial_unit == 0 and
         initial[0] == initial_turn and initial[2] == owner and (length, production, needed) == initial[6:9] and
         length == 1 and 0 <= production < needed and generation > 0 and
         capability.end() < decision.start() < baseline.start() < before_turns[0].start() and
         finished_worker.end() < complete.start(), 'production baseline differs from its original first decision')
    worlds = records('WORLD_FRAME', ints(9))
    commits = records('GPU_SCENE_COMMITTED', ints(2))
    hud_frames = records('ACTION_INFO_PANEL_FRAME', ints(6) + r'\|([^|\r\n]+)\|([^|\r\n]+)')
    ui_frames = records('UI_FRAME', ints(3) + r'\|([^|\r\n]+)\|' + ints(2) + r'\|([^|\r\n]+)\|([^|\r\n]+)')

    def world(gen, turn, before, after=-1, panel=False):
        frame = one([r for r in worlds if int(r[2]) == gen], 'missing/repeated production world generation')
        commit = one([r for r in commits if int(r[1]) == gen], 'missing production GPU commit')
        need(int(frame[3]) == turn and int(frame[6]) == int(commit[2]) > 0 and
             after < commit.start() < frame.start() < before, 'production world turn/device/order differs')
        if panel:
            h = one([r for r in hud_frames if int(r[2]) == gen], 'missing production HUD generation')
            need((int(h[3]), int(h[4]), int(h[6])) == (turn, owner, int(frame[6])) and
                 frame.end() < h.start() < before, 'production HUD owner/turn/device/order differs')
            return h
        return frame

    world(generation, initial_turn, baseline.start(), panel=True)
    hud_targets = records('ACTION_INFO_SMOKE_TARGET', r'([^|\r\n]+)\|' + ints(5))
    production_hud = [r for r in hud_targets if r[1] == 'production-continuation']
    count = int(complete[1])
    need(all(len(data[name]) == count * amount for name, amount in
             (('FINISHED', 1), ('SCENES', 1), ('BEGIN', 1), ('TARGET', 1), ('RETURNED', 1),
              ('COMMAND', 1), ('WORKER_STATE', 3), ('QUEUE', 5))) and len(production_hud) == count,
         'production completion/requeue/worker/queue counts differ')
    proof = {'contract_version': 1, 'completed_cycle_count': count,
             'baseline': dict(zip(('turn', 'owner', 'city', 'unit_type', 'queue_length', 'production', 'needed', 'generation'), bv)),
             'cycles': [], 'callback_inputs': []}
    if not count:
        unstack = verify_worker_unstack_timeline(text, proof, required=unstack_required)
        if unstack is not None: proof['unstack'] = unstack
        return proof
    finished, scene_paths, begin, target, command, returned = (data[name][0] for name in
        ('FINISHED', 'SCENES', 'BEGIN', 'TARGET', 'COMMAND', 'RETURNED'))
    fv, b, t, cv, rv = (numbers(row) for row in (finished, begin, target, command, returned))
    cycle, turn, finish_owner, finish_city, completed_type, produced_unit, finish_generation = fv
    need(cycle == 1 and (finish_owner, finish_city, completed_type) == (owner, city, initial_unit) and
         initial_turn < turn < research['final_turn'] and produced_unit >= 0 and
         b[:4] == (1, turn, owner, city) and b[4] >= 0 and b[5] >= finish_generation > generation and b[6] >= 0 and
         t[:4] == (1, turn, owner, city) and t[4] >= 0 and min(t[5:]) > 0 and t[6] > b[5] and
         rv[:5] == t[:5] and rv[5] > t[6] and rv[6:] == (-1, -1, 1, b[6]) and
         cv[:6] == (1, owner, turn, city, 0, t[4]) and cv[6] == 0 and cv[7] in (0, 1) and cv[8:] == (1, t[6], t[5]) and
         baseline.end() < finished.start() < scene_paths.start() < begin.start() < target.start() < command.start() <
         returned.start() < finished_worker.start() < complete.start() and scene_paths[1] == '1',
         'production identity, natural completion, command tuple or readiness differs')
    queues = data['QUEUE']; states = data['WORKER_STATE']
    need([r[2] for r in queues] == ['last-turn', 'finished', 'before', 'opened', 'returned'] and
         [r[2] for r in states] == ['before', 'opened', 'returned'] and
         all(r[1] == '1' for r in queues + states), 'production queue/worker phase identity differs')
    qv = [tuple(map(int, r.groups()[2:])) for r in queues]
    need(qv[0][:3] == (turn - 1, owner, city) and qv[0][4:6] == (1, initial_unit) and
         generation <= qv[0][3] < finish_generation and 0 <= qv[0][6] < qv[0][7] == needed and
         all(q[:3] == (turn, owner, city) for q in qv[1:]) and
         [q[3] for q in qv[1:]] == [finish_generation, b[5], t[6], rv[5]] and
         all(q[4:6] == (0, -1) for q in qv[1:4]) and qv[1][4:] == qv[2][4:] == qv[3][4:] and
         qv[4][4:6] == (1, t[4]) and all(q[6] >= 0 and q[7] >= 0 for q in qv[1:]) and qv[4][6] < qv[4][7],
         'natural production queue did not go from original order to empty to the selected new order')
    prior_research = one([r for r in before_turns if int(r[1]) == turn - 1], 'missing last production end-turn research')
    research_return = one([r for r in records('WORKER_RESEARCH_TURN_RETURNED', ints(8)) if int(r[1]) == turn],
                          'missing production-turn research return')
    worker = one([r for r in records('WORKER_BUILD_OBSERVED', ints(9)) if int(r[1]) == turn],
                 'missing production-turn worker observation')
    need(int(prior_research[4]) == qv[0][3] and int(research_return[4]) == finish_generation and
         research_return.end() < finished.start() < queues[0].start() < queues[1].start() < worker.start() < begin.start(),
         'production completion is not inside its original consecutive worker turn')
    world(qv[0][3], turn - 1, prior_research.start(), panel=True)
    world(finish_generation, turn, research_return.start(), panel=True)
    state_values = [tuple(map(int, r.groups()[2:])) for r in states]
    need(all(v[:2] == (turn, owner) for v in state_values) and
         [v[2] for v in state_values] == [b[5], t[6], rv[5]] and
         all(v[3:] == state_values[0][3:] for v in state_values), 'tracked worker changed across production popup')
    tracked = state_values[0][3:]
    fixture = numbers(one(records('WORKER_BUILD_FIXTURE', ints(6)), 'missing worker fixture'))
    build_target = numbers(one(records('WORKER_BUILD_TARGET', ints(6)), 'missing worker target'))
    need(tracked[:3] == fixture[:3] == build_target[:3] and tracked[4] == fixture[4] > 0 and tracked[6] == fixture[5] and
         tracked[7:9] == (build_target[3], fixture[2]) and min(tracked[3], tracked[9]) >= 0 and
         numbers(worker)[1:] == tracked[:4] + (tracked[5], tracked[9], tracked[7], tracked[8]),
         'production observes a different worker/build from its actual same-turn SDK state')
    hud = production_hud[0]; key_base = 1 << 52
    blocker, notice, hud_key, hud_generation, hud_turn = map(int, hud.groups()[1:])
    need((blocker, notice, hud_generation, hud_turn) == (2, b[4], b[5], turn) and
         key_base < hud_key < key_base + (1 << 32) and
         begin.end() < queues[2].start() < states[0].start() < hud.start(), 'production blocker/HUD order differs')
    initial_hud = world(b[5], turn, begin.start(), panel=True)
    posts = records('SMOKE_POSTED', ints(4)); buttons = records('SMOKE_BUTTON', ints(4))
    panel_inputs = records('ACTION_INFO_PANEL_INPUT', ints(6)); native_inputs = records('UI_NATIVE_INPUT', ints(4))
    hp = one([r for r in posts if numbers(r)[:2] == (b[5], hud_key)], 'missing production HUD post')
    hb = one([r for r in buttons if numbers(r)[:2] == (b[5], hud_key)], 'missing production HUD button')
    hi = one([r for r in panel_inputs if numbers(r)[:3] == (b[5], 1, hud_key)], 'missing production HUD consumption')
    need(numbers(hb)[2:] == (1, 0) and numbers(hi)[3:] == (hud_key - key_base, 1, 0) and
         hud.end() < hb.start() < hp.start() < hi.start() < queues[3].start() < states[1].start() < target.start(),
         'production popup did not follow its original HUD dispatch')
    frame = one([r for r in ui_frames if int(r[2]) == t[6]], 'missing production original popup frame')
    post = one([r for r in posts if numbers(r)[:2] == (t[6], t[5])], 'missing production callback post')
    button = one([r for r in buttons if numbers(r)[:2] == (t[6], t[5])], 'missing production callback button')
    native = one([r for r in native_inputs if int(r[1]) == t[6] and int(r[2]) == 1], 'missing production consumed callback')
    timers = list(re.finditer(r'^UI_WINDOW_INPUT=' + ints(10) + '$', text, re.M))
    need(len(timers) == sum(line.startswith('UI_WINDOW_INPUT=') for line in text.splitlines()), 'malformed production timer dispatch')
    timer = one([r for r in timers if post.end() < r.start() < native.start() and int(r[3]) == t[5]],
                'missing production timer dispatch')
    gameplay = list(re.finditer(r'^UI_PRODUCTION_WINDOW_GAMEPLAY=(\d+)\|(\d+)\|(\d+)\|([01])\|([01])\|(-?\d+(?:\.\d+)?)$', text, re.M))
    dispatch = one([r for r in gameplay if post.end() < r.start() < native.start()], 'missing production input gameplay observation')
    need((int(frame[1]), int(frame[3]), frame[4]) == (t[7], turn, 'production') and
         frame.groups()[4:6] == initial_hud.groups()[4:6] and numbers(button)[2:] == (1, 0) and
         numbers(native)[1:] == (1, t[5], 1) and numbers(timer)[1:4] == (2, t[5], 1) and
         timer[5] == timer[6] and numbers(timer)[6:9] == (0, 0, turn) and int(timer[1]) > 0 and int(timer[10]) > 0 and
         int(dispatch[1]) == int(timer[1]) and (int(dispatch[2]), int(dispatch[3]), int(dispatch[4]), float(dispatch[6])) == (2, t[5], 0, 0.) and
         frame.end() < queues[3].start() < states[1].start() < target.start() < button.start() < post.start() < timer.start() < dispatch.start() <
         native.start() < command.start() < queues[4].start() < states[2].start() < returned.start(),
         'production original input, timer, owner command or close ordering differs')
    world(t[6], turn, states[1].start(), hi.end())
    returned_hud = world(rv[5], turn, states[2].start(), native.end(), panel=True)
    need(returned_hud.groups()[4:6] == initial_hud.groups()[4:6], 'production return changed its owned HWND/device')
    next_research = one([r for r in before_turns if int(r[1]) == turn], 'production did not continue to end turn')
    need(returned.end() < next_research.start() and int(next_research[4]) >= rv[5] and
         (rv[9] == -1 or int(next_research[3]) == rv[9]), 'production return did not retain its selected research')
    city_orders = list(re.finditer(r'^TURN_CYCLE_EVENT=(\d+)\|local-city-order:(\d+):(-?\d+):(-?\d+):([01]):([01]):([01])$', text, re.M))
    expected_orders = {}
    for event in ((city, 0, initial_unit, 0, 1, 1), (city, 0, t[4], 0, cv[7], 1)):
        expected_orders[event] = expected_orders.get(event, 0) + 1
    actual_orders = {}
    for row in city_orders:
        count, *event = map(int, row.groups()); event = tuple(event)
        need(count > 0 and event not in actual_orders, 'production owner event counts are not uniquely aggregated')
        actual_orders[event] = count
    need(actual_orders == expected_orders,
         'production owner event inventory is not the original first and natural continuation order pair')
    proof['cycles'] = [{'cycle': 1, 'turn': turn, 'owner': owner, 'city': city, 'completed_unit_type': initial_unit,
        'produced_unit': produced_unit, 'unit_type': t[4], 'notification': b[4], 'hud_generation': b[5], 'hud_key': hud_key,
        'finished_generation': finish_generation, 'previous_generation': qv[0][3],
        'selection_generation': t[6], 'returned_generation': rv[5],
        'begin_position': begin.start(), 'hud_position': hud.start(), 'return_position': returned.start(),
        'worker_state': list(tracked), 'queues': {r[2]: list(v) for r, v in zip(queues, qv)},
        'scenes': {'before': scene_paths[2], 'after': scene_paths[3]}, 'command': list(cv)}]
    proof['callback_inputs'] = [
        {'context': 'action-info-panel', 'phase': 'hud', 'sequence': int(initial_hud[1]), 'turn': turn, 'owner': owner,
         'generation': b[5], 'key': hud_key - key_base, 'native_key': hud_key - key_base, 'world_key': hud_key,
         'city': city, 'client': [int(hp[3]), int(hp[4])]},
        {'context': 'production', 'phase': 'selection', 'sequence': t[7], 'turn': turn, 'owner': owner,
         'generation': t[6], 'key': t[5], 'native_key': t[5], 'city': city, 'unit_type': t[4],
         'client': [int(post[3]), int(post[4])]}]
    unstack = verify_worker_unstack_timeline(text, proof, required=unstack_required)
    if unstack is not None: proof['unstack'] = unstack
    return proof


def verify_worker_unstack_timeline(text: str, production: dict, *, required: bool) -> dict | None:
    """Bind the bounded civilian collision recovery to one original world move."""
    prefix = 'INTERACTIVE_WORKER_UNSTACK_'
    if not required:
        need(not any(line.startswith(prefix) for line in text.splitlines()), 'undeclared unstack records')
        return None

    def ints(n): return r'\|'.join([r'(-?\d+)'] * n)
    def records(name, pattern, stem='INTERACTIVE_'):
        tag = stem + name + '='
        result = list(re.finditer('^' + tag + pattern + '$', text, re.M))
        need(len(result) == sum(l.startswith(tag) for l in text.splitlines()), 'malformed ' + name)
        return result
    def one(rows, reason):
        need(len(rows) == 1, reason)
        return rows[0]
    def val(row): return tuple(map(int, row.groups()))
    phase = r'(\d+)\|([^|\r\n]+)\|'
    patterns = {'CONTRACT': ints(1), 'COMPLETE': ints(1), 'BEGIN': ints(16), 'TARGET': ints(12),
                'COMMAND': ints(11), 'RETURNED': ints(11), 'QUEUE': phase + ints(8),
                'RESEARCH': phase + ints(6), 'WORKER_STATE': phase + ints(13),
                'SCENES': r'(\d+)\|([^|\r\n]+)\|([^|\r\n]+)'}
    data = {n: records('WORKER_UNSTACK_' + n, p) for n, p in patterns.items()}
    need(all(l.split('=', 1)[0][len(prefix):] in patterns for l in text.splitlines() if l.startswith(prefix)),
         'unknown unstack marker')
    capability = one(data['CONTRACT'], 'missing/repeated unstack capability')
    complete = one(data['COMPLETE'], 'missing/repeated unstack completion')
    need(capability[1] == '1' and complete[1] in ('0', '1'), 'invalid unstack version/count')
    count = int(complete[1])
    need(all(len(data[n]) == count * amount for n, amount in (('BEGIN', 1), ('TARGET', 1), ('COMMAND', 1),
        ('RETURNED', 1), ('SCENES', 1), ('QUEUE', 2), ('RESEARCH', 2), ('WORKER_STATE', 2))),
        'unstack move/queue/research/worker counts differ')
    worker_finished = one(records('WORKER_BUILD_COMPLETED', ints(5)), 'unstack lacks completed worker')
    need(capability.end() < worker_finished.start() < complete.start(), 'unstack capability/completion order differs')
    proof = {'contract_version': 1, 'completed_cycle_count': count, 'cycles': []}
    if not count: return proof
    cycle = one(production['cycles'], 'unstack is outside its one natural production cycle')
    begin, target, command, returned, scenes = (data[n][0] for n in ('BEGIN', 'TARGET', 'COMMAND', 'RETURNED', 'SCENES'))
    b, t, c, a = (val(r) for r in (begin, target, command, returned))
    turn, owner, city, unit, produced, unit_type, origin_plot, ox, oy, moves, generation, technology = b[1:13]
    need(b[0] == 1 and (turn, owner, city, produced, unit_type) == (cycle['turn'], cycle['owner'], cycle['city'],
         cycle['produced_unit'], cycle['completed_unit_type']) and unit >= 0 and unit != produced and
         origin_plot >= 0 and min(ox, oy) >= 0 and moves > 0 and technology >= 0 and b[13:] == (2, 1, 0) and
         cycle['finished_generation'] <= generation < cycle['hud_generation'] and
         t[:4] == (1, turn, owner, unit) and t[4] >= 0 and min(t[5:7]) >= 0 and t[4] != origin_plot and
         t[7] == (0x5A57000000000000 | (1 << 32) | t[4]) and t[8] == generation and t[9] >= 0 and t[10:] == (1, 1) and
         c == (1, owner, turn, unit, t[9], t[5], t[6], 0, 0, generation, t[7]) and
         a[:5] == (1, turn, owner, unit, produced) and a[5:8] == t[4:7] and 0 <= a[8] < moves and
         generation < a[9] < cycle['hud_generation'] and a[10] == technology and scenes[1] == '1' and
         capability.end() < begin.start() < target.start() < command.start() < scenes.start() < returned.start() < cycle['begin_position'],
         'unstack source, bounded collision, destination, SDK command or return identity differs')
    finished = one(records('WORKER_PRODUCTION_FINISHED', ints(7)), 'unstack lacks its natural completion')
    prior_worker = one([r for r in records('WORKER_BUILD_OBSERVED', ints(9)) if int(r[1]) == turn],
                       'unstack lacks same-turn worker observation')
    need(finished.end() < prior_worker.start() < begin.start(), 'unstack bypassed natural completion or worker observation')
    qrows, rrows, wrows = data['QUEUE'], data['RESEARCH'], data['WORKER_STATE']
    need(all([r[2] for r in rows] == ['before', 'returned'] and all(r[1] == '1' for r in rows)
             for rows in (qrows, rrows, wrows)), 'unstack state phase identity/order differs')
    qs, rs, ws = [[tuple(map(int, r.groups()[2:])) for r in rows] for rows in (qrows, rrows, wrows)]
    need(all(q[:3] == (turn, owner, city) for q in qs) and [q[3] for q in qs] == [generation, a[9]] and
         qs[0][4:] == qs[1][4:] == tuple(cycle['queues']['finished'][4:]) and qs[0][4:6] == (0, -1) and
         all(r[:2] == (turn, owner) for r in rs) and [r[2] for r in rs] == [generation, a[9]] and
         rs[0][3:] == rs[1][3:] and rs[0][3] == technology and min(rs[0][4:]) >= 0 and
         all(w[:2] == (turn, owner) for w in ws) and [w[2] for w in ws] == [generation, a[9]] and
         ws[0][3:] == ws[1][3:] == tuple(cycle['worker_state']), 'unstack changed production, research or tracked worker')
    research = one([r for r in records('WORKER_RESEARCH_TURN_RETURNED', ints(8)) if int(r[1]) == turn],
                   'unstack lacks same-turn research return')
    need((int(research[3]), int(research[5]), int(research[6]), int(research[7]), int(research[8])) ==
         (technology, technology, 0, rs[0][4], rs[0][5]), 'unstack research differs from its natural returned sample')
    need(begin.end() < qrows[0].start() < rrows[0].start() < wrows[0].start() < target.start() and
         command.end() < qrows[1].start() < rrows[1].start() < wrows[1].start() < scenes.start() < returned.start(),
         'unstack queue/research/worker observation ordering differs')
    button = one([r for r in records('SMOKE_BUTTON', ints(4)) if val(r)[:2] == (generation, t[7])], 'unstack missing exact mouse button')
    post = one([r for r in records('SMOKE_POSTED', ints(4)) if val(r)[:2] == (generation, t[7])], 'unstack missing HWND coordinates')
    route = one([r for r in records('WORLD_MOVE_ROUTE', ints(6)) if begin.end() < r.start() < returned.start()],
                'unstack missing unique original world-movement route')
    mission = one([r for r in records('MISSION_ACCEPTED', ints(5)) if begin.end() < r.start() < returned.start()],
                  'unstack missing unique actual SDK accepted mission')
    consumed = one([r for r in records('WINDOW_INPUT', ints(4)) if int(r[1]) == generation], 'unstack missing consumed map input')
    need(val(button)[2:] == (5, 0) and val(route) == (turn, unit, t[5], t[6], 0, 0) and
         val(mission) == (turn, unit, t[9], t[5], t[6]) and val(consumed) == (generation, 5, t[7], 1) and
         target.end() < button.start() < post.start() < route.start() < mission.start() < consumed.start() < command.start(),
         'unstack bypassed original posted right-click or its exact SDK movement route')
    need(not [r for r in records('UNIT_PANEL_INPUT', ints(4)) if begin.end() < r.start() < returned.start()],
         'unstack attempted a unit-panel callback while skip was illegal')
    pushes = list(re.finditer(r'^TURN_CYCLE_EVENT=(\d+)\|local-push-mission:' +
        str(unit) + ':' + str(t[9]) + r':(-?\d+):(-?\d+):([01]):([01])$', text, re.M))
    need(len(pushes) == 1 and int(pushes[0][1]) == 1 and
         tuple(map(int, pushes[0].groups()[1:])) == (t[5], t[6], 0, 0),
         'unstack lacks its unique actual receiver command')
    worlds = records('WORLD_FRAME', ints(9)); commits = records('GPU_SCENE_COMMITTED', ints(2))
    world_rows = []
    for gen, before, after in ((generation, begin.start(), finished.end()), (a[9], qrows[1].start(), command.end())):
        world = one([r for r in worlds if int(r[2]) == gen], 'unstack missing unique world generation')
        commit = one([r for r in commits if int(r[1]) == gen], 'unstack missing GPU commit')
        need(int(world[3]) == turn and int(world[6]) == int(commit[2]) > 0 and
             after < commit.start() < world.start() < before, 'unstack world generation/turn/device/order differs')
        world_rows.append(world)
    need(world_rows[0][6] == world_rows[1][6], 'unstack replaced its original GPU device')
    proof['cycles'] = [{'cycle': 1, 'turn': turn, 'owner': owner, 'city': city, 'unit': unit, 'produced_unit': produced,
        'unit_type': unit_type, 'origin': [origin_plot, ox, oy], 'target': list(t[4:7]), 'moves_before': moves,
        'moves_after': a[8], 'generation': generation, 'returned_generation': a[9], 'technology': technology,
        'key': t[7], 'mission': t[9], 'client': [int(post[3]), int(post[4])], 'begin_position': begin.start(),
        'return_position': returned.start(), 'scenes': {'before': scenes[2], 'after': scenes[3]},
        'worker_state': list(ws[0][3:]), 'queue': list(qs[0][4:]), 'research': list(rs[0][3:])}]
    return proof
