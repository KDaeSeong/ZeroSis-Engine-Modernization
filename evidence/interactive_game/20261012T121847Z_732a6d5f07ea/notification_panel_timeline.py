"""Check the bounded original NotificationPanel native dispatch timeline.

Fresh proof is an actual posted production-notification round trip, forbidden
dismissal, then production selection/removal. Restore proves list presentation
only. This log check does not establish snapshot contents, original assets,
pixels, SDK save bytes, or complete notification-type support.
"""
from __future__ import annotations

import re

KEY_BASE = 1 << 50
KEY_LIMIT = KEY_BASE + (1 << 32)
FRAME = r'(\d+)\|(\d+)\|(\d+)\|(\d+)\|(\d+)\|(\d+)\|([^|\r\n]+)\|([^|\r\n]+)'
MANDATORY_DISMISS_REJECTION = 'INTERACTIVE_INPUT_REJECTED=이 원본 알림은 사용자가 닫을 수 없습니다.'


def unexpected_input_rejection_lines(
        text: str, *, notification_panel_requested: bool = False, restored: bool = False) -> list[str]:
    """Return rejection lines that the runner must continue to treat as failures.

    Only a single exact mandatory-dismiss rejection inside its verified fresh
    callback may be exempted. Empty output is not a replacement for the runner's
    separate timeline/profile checks, and does not certify a run with no rejects.
    """
    text = text.replace('\r\n', '\n')
    rejected = [row for row in re.finditer(r'^[^\n]*$', text, re.M)
                if 'INTERACTIVE_INPUT_REJECTED' in row[0]]
    unexpected = [row[0] for row in rejected]
    if (len(rejected) != 1 or not notification_panel_requested or restored or
            rejected[0][0] != MANDATORY_DISMISS_REJECTION or
            not verify_notification_panel_timeline(text, restored=False)[0]):
        return unexpected
    # The full timeline binds this target's SDK ID to open/dismiss/removal and
    # validates owner, turn, physical post, namespace and generation throughout.
    targets = list(re.finditer(r'^INTERACTIVE_NOTIFICATION_SMOKE_TARGET=dismiss-blocked\|(\d+)\|(\d+)\|(\d+)\|(\d+)$', text, re.M))
    if len(targets) != 1:
        return unexpected
    _, key, generation, turn = map(int, targets[0].groups())
    frames = [row for row in re.finditer('^INTERACTIVE_NOTIFICATION_PANEL_FRAME=' + FRAME + '$', text, re.M)
              if int(row[2]) == generation and int(row[3]) == turn]
    if len(frames) != 1:
        return unexpected
    owner, local = int(frames[0][4]), key - KEY_BASE
    inner = list(re.finditer(rf'^INTERACTIVE_NOTIFICATION_INPUT=5\|{local}\|1\|{owner}\|{turn}\|1\|0$', text, re.M))
    outer = list(re.finditer(rf'^INTERACTIVE_NOTIFICATION_PANEL_INPUT={generation}\|5\|{key}\|{local}\|0$', text, re.M))
    if len(inner) == len(outer) == 1 and inner[0].end() < rejected[0].start() < rejected[0].end() < outer[0].start():
        return []
    return unexpected


def verify_notification_panel_timeline(text: str, *, restored: bool = False) -> tuple[bool, str | None]:
    def need(condition, reason):
        if not condition:
            raise ValueError(reason)

    def rows(marker, fields):
        found = list(re.finditer('^' + marker + '=' + fields + '$', text, re.M))
        need(len(found) == len(re.findall('^' + marker + '=', text, re.M)),
             f'Malformed {marker} record')
        return found

    def one(items, reason):
        need(len(items) == 1, reason)
        return items[0]

    def ints(row, *columns):
        return tuple(int(row[column]) for column in columns)

    try:
        text = text.replace('\r\n', '\n')
        specs = {
            'frames': ('INTERACTIVE_NOTIFICATION_PANEL_FRAME', FRAME),
            'targets': ('INTERACTIVE_NOTIFICATION_SMOKE_TARGET', r'(open|dismiss-blocked)\|(\d+)\|(\d+)\|(\d+)\|(\d+)'),
            'inner': ('INTERACTIVE_NOTIFICATION_INPUT', r'([1-5])\|(\d+)\|([01])\|(\d+)\|(\d+)\|(\d+)\|0'),
            'outer': ('INTERACTIVE_NOTIFICATION_PANEL_INPUT', r'(\d+)\|([0-5])\|(\d+)\|(\d+)\|([01])'),
            'opened': ('INTERACTIVE_NOTIFICATION_POPUP_OPENED', r'(\d+)\|(production|research)\|(\d+)\|(\d+)'),
            'returned': ('INTERACTIVE_NOTIFICATION_OPEN_VERIFIED', r'(\d+)\|(\d+)\|(\d+)\|STATE_UNCHANGED'),
            'denied': ('INTERACTIVE_NOTIFICATION_DISMISS_BLOCKED', r'(\d+)\|(\d+)\|(\d+)\|STATE_UNCHANGED'),
            'removed': ('INTERACTIVE_NOTIFICATION_REMOVED_VERIFIED', r'(\d+)\|(\d+)\|(\d+)'),
            'complete': ('INTERACTIVE_NOTIFICATION_PANEL_SMOKE_COMPLETE', r'([A-Z_]+)'),
            'rejected': ('INTERACTIVE_NOTIFICATION_REQUEST_REJECTED', r'(\d+)\|(\d+)\|(\d+)\|EXPIRED_SDK_NOTIFICATION'),
            'world_commit': ('INTERACTIVE_GPU_WORLD_COMMITTED', r'(\d+)\|(\d+)'),
            'scene_commit': ('INTERACTIVE_GPU_SCENE_COMMITTED', r'(\d+)\|(\d+)'),
            'world': ('INTERACTIVE_WORLD_FRAME', r'(\d+)\|(\d+)\|(\d+)\|\d+\|\d+\|(\d+)\|\d+\|[01]\|\d+'),
            'ui': ('INTERACTIVE_UI_FRAME', r'(\d+)\|(\d+)\|(\d+)\|([^|\r\n]+)\|(\d+)\|(\d+)\|([^|\r\n]+)\|([^|\r\n]+)'),
            'buttons': ('INTERACTIVE_SMOKE_BUTTON', r'(\d+)\|(\d+)\|([0-5])\|([01])'),
            'posts': ('INTERACTIVE_SMOKE_POSTED', r'(\d+)\|(\d+)\|-?\d+\|-?\d+'),
            'native': ('INTERACTIVE_UI_NATIVE_INPUT', r'(\d+)\|([0-5])\|(\d+)\|([01])'),
            'keys': ('INTERACTIVE_UI_NATIVE_KEY', r'(\d+)\|([^|\r\n]+)\|(\d+)\|([01])\|([01])'),
            'production': ('INTERACTIVE_DECISION_PRODUCTION_TARGET', r'(\d+)\|(\d+)\|(\d+)'),
            'city_done': ('INTERACTIVE_OWNED_CITY_SEQUENCE_VERIFIED', r'(\d+)\|(\d+)'),
        }
        data = {name: rows(*spec) for name, spec in specs.items()}
        known = {spec[0] for spec in specs.values()}
        need(all(line.split('=', 1)[0] in known for line in text.splitlines()
                 if line.startswith('INTERACTIVE_NOTIFICATION_')), 'Unknown notification timeline record')
        complete = one(data['complete'], 'Notification sequence needs exactly one completion')
        mode = 'RESTORED_SDK_LIST_PRESENTATION' if restored else 'FRESH_INPUT_AND_SDK_REMOVAL'
        need(complete[1] == mode, 'Fresh input proof and restored list presentation are different scopes')
        frames = data['frames']
        need(bool(frames), 'Original notification list has no published frame')
        owner, hwnd, device = ints(frames[0], 4, 5, 6)
        need(hwnd > 0 and device > 0, 'Notification frame has no native HWND/device identity')

        def committed(frame, device_column=6):
            generation, turn = ints(frame, 2, 3)
            world = one([r for r in data['world_commit'] if int(r[1]) == generation], 'Missing/duplicate world commit')
            scene = one([r for r in data['scene_commit'] if int(r[1]) == generation], 'Missing/duplicate scene commit')
            image = one([r for r in data['world'] if int(r[2]) == generation], 'Missing/duplicate native world frame')
            need(generation > 0 and int(frame[1]) > 0 and int(frame[device_column]) == device and
                 ints(world, 2) == ints(scene, 2) == (device,) and ints(image, 3, 4) == (turn, device) and
                 world.end() < scene.start() < image.start() < frame.start(),
                 'Notification/UI frame is not backed by its ordered same-device GPU commit')

        def current(frame, before):
            preceding = [r for r in data['scene_commit'] if r.end() < before]
            need(frame.end() < before and preceding and int(preceding[-1][1]) == int(frame[2]),
                 'Notification action used a stale or unpublished scene generation')

        def panel(generation, turn, before):
            frame = one([r for r in frames if int(r[2]) == generation], 'No unique notification frame for action')
            need(int(frame[3]) == turn, 'Notification action crossed its published human turn')
            current(frame, before)
            return frame

        for i, frame in enumerate(frames):
            need(ints(frame, 4, 5, 6) == (owner, hwnd, device) and frame.end() < complete.start(),
                 'Notification list changed owner/window/device or appeared after completion')
            if i:
                need(int(frame[1]) > int(frames[i-1][1]) and int(frame[2]) > int(frames[i-1][2]) and
                     int(frame[3]) >= int(frames[i-1][3]), 'Notification frame revision/generation/turn regressed')
            committed(frame)

        # Every dispatched pointer/click gets both records. Passive hover may
        # target a world key and deliberately routes local key zero to this VM.
        need(len(data['inner']) == len(data['outer']), 'Notification callback/outer dispatch count differs')
        previous = -1
        for inner, outer in zip(data['inner'], data['outer']):
            generation, kind, key, local, consumed = ints(outer, 1, 2, 3, 4, 5)
            frame = panel(generation, int(inner[5]), outer.start())
            need(previous < inner.start() < outer.start() < complete.start() and
                 ints(inner, 2, 4, 5) == (local, owner, int(frame[3])), 'Notification callback lost order, local key or owner/turn')
            previous = outer.end()
            need(kind in (1, 3, 5), 'Notification timeline contains an unrequested command kind')
            need((local == 0 and kind == 3) or (KEY_BASE < key < KEY_LIMIT and key == KEY_BASE + local),
                 'Notification input escaped its exact rebased key namespace')
            if kind == 3:
                need(ints(inner, 1, 3, 6) == (3, consumed, 0), 'Pointer motion queued a command or lost its result')
            else:
                need(ints(inner, 1, 3, 6) == (2 if kind == 1 else 5, 1, 1),
                     'Notification click did not complete exactly one deferred original request')
        need(not data['rejected'], 'Expected live notification was already expired')
        clicks = [r for r in data['outer'] if r[2] != '3']
        stages = ('targets', 'opened', 'returned', 'denied', 'removed')
        if restored:
            need(not clicks and all(not data[name] for name in stages) and
                 all(not KEY_BASE < int(r[2]) < KEY_LIMIT for name in ('buttons', 'posts') for r in data[name]),
                 'Restored list presentation must not claim notification input/removal proof')
            return True, None

        targets = data['targets']
        need([r[1] for r in targets] == ['open', 'dismiss-blocked'] and len(clicks) == 2,
             'Fresh notification scenario requires exactly open and forbidden-dismiss clicks')
        identity, turn = ints(targets[0], 2, 5)

        def posted(target, generation, key, kind, dispatch):
            button = one([r for r in data['buttons'] if ints(r, 1, 2) == (generation, key)], 'No unique physical-button post')
            post = one([r for r in data['posts'] if ints(r, 1, 2) == (generation, key)], 'No unique HWND coordinate post')
            need(ints(button, 3, 4) == (kind, 0) and target.end() < button.start() < post.start() < dispatch.start(),
                 'Notification/production command preceded its exact physical button and HWND post')

        for target, click, kind, consumed in zip(targets, clicks, (1, 5), (1, 0)):
            key, generation = ints(target, 3, 4)
            need(ints(target, 2, 5) == (identity, turn) and KEY_BASE < key < KEY_LIMIT,
                 'Notification targets changed SDK ID, turn or private key namespace')
            panel(generation, turn, target.start())
            need(ints(click, 1, 2, 3, 4, 5) == (generation, kind, key, key - KEY_BASE, consumed),
                 'Notification dispatch did not match the requested ID target/key/generation/result')
            inner = data['inner'][data['outer'].index(click)]
            posted(target, generation, key, kind, inner)
        for name in ('buttons', 'posts'):
            need([ints(r, 1, 2) for r in data[name] if KEY_BASE < int(r[2]) < KEY_LIMIT] ==
                 [ints(r, 4, 3) for r in targets], 'Additional/unrequested notification HWND post')

        opened = one(data['opened'], 'Missing/duplicate original notification popup observation')
        returned = one(data['returned'], 'Missing/duplicate state-preserving notification return')
        denied = one(data['denied'], 'Missing/duplicate SDK-forbidden dismissal observation')
        removed = one(data['removed'], 'Missing/duplicate SDK/list-target removal observation')
        need(opened[2] == 'production' and ints(opened, 1, 4) == (identity, turn) and
             all(ints(r, 1, 3) == (identity, turn) for r in (returned, denied, removed)),
             'Notification observations changed SDK ID, original production popup or turn')
        popup_gen = int(opened[3])
        popup = one([r for r in data['ui'] if int(r[2]) == popup_gen], 'Notification has no unique original popup frame')
        need(popup[4] == 'production' and ints(popup, 3, 5, 6) == (turn, hwnd, device),
             'Notification opened a different popup, turn, HWND or device')
        committed(popup)
        current(popup, opened.start())
        escape = one([r for r in data['keys'] if int(r[1]) == popup_gen], 'Original popup lacks one native Escape')
        native_escape = one([r for r in data['native'] if int(r[1]) == popup_gen and r[2] != '3'],
                            'Original notification popup received extra/missing commands')
        need(escape.groups() == (str(popup_gen), 'production', '27', '1', '0') and
             ints(native_escape, 1, 2, 3, 4) == (popup_gen, 0, 0, 1) and
             clicks[0].end() < popup.start() < opened.start() < native_escape.start() < escape.start(),
             'Original popup did not consume Escape once after its observed opening')
        return_frame = panel(int(returned[2]), turn, returned.start())
        panel(int(denied[2]), turn, denied.start())
        panel(int(removed[2]), turn, removed.start())
        need(int(targets[0][4]) < popup_gen < int(returned[2]) == int(targets[1][4]) < int(denied[2]) < int(removed[2]) and
             escape.end() < return_frame.start() < returned.start() < targets[1].start() < clicks[1].start() < denied.start() < removed.start() < complete.start(),
             'Notification open/return/forbidden-dismiss/removal order or generation is invalid')

        # Removal is accepted only after the existing real production-input
        # sequence; the independent evidence verifier must still compare SDK data.
        choice = one(data['production'], 'SDK notification removal lacks one production target')
        done = one(data['city_done'], 'SDK notification removal lacks its completed owned-city sequence')
        need(ints(choice, 1, 2) == ints(done, 1, 2) and denied.end() < choice.start() < done.start() < removed.start(),
             'Notification was removed before its matching city production sequence')
        choices = [r for r in data['ui'] if r.end() < choice.start()]
        need(bool(choices), 'Production choice has no original UI frame')
        choice_frame = choices[-1]
        generation, key = int(choice_frame[2]), int(choice[3])
        need(choice_frame[4] == 'production' and ints(choice_frame, 3, 5, 6) == (turn, hwnd, device) and
             int(denied[2]) < generation < int(removed[2]) and 0 < key < (1 << 32),
             'Removal production choice has a wrong context, generation or key')
        committed(choice_frame)
        current(choice_frame, choice.start())
        dispatch = one([r for r in data['native'] if int(r[1]) == generation and r[2] != '3'],
                       'Production selection has missing/extra native commands')
        need(ints(dispatch, 1, 2, 3, 4) == (generation, 1, key, 1) and dispatch.end() < done.start(),
             'Production selection was not consumed before SDK notification removal')
        posted(choice, generation, key, 1, dispatch)
        return True, None
    except ValueError as error:
        return False, str(error)
