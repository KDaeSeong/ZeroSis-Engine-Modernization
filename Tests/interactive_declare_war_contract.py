"""Contract tests for the private original DeclareWar popup smoke verifier."""
import hashlib
import json
import sqlite3
import sys
import tempfile
import unittest
from unittest import mock
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from run_interactive_game import _sdk_enum_value, verify_declare_war_smoke


SDK_HEADER = Path(__file__).resolve().parents[1] / 'Source/SDK_BNW_x64/CvGameCoreDLLUtil/include/CvEnums.h'


class DeclareWarSmokeContract(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1] / 'evidence')
        self.root = Path(self.temp.name)
        self.sessions = self.root / 'sessions'
        self.session = self.sessions / 'private-session'
        self.session.mkdir(parents=True)
        self.owner, self.unit = 0, 3
        self.rival_player, self.rival_team, self.target_unit = 1, 1, 4
        self.x, self.y, self.turn, self.plot_index = 5, 5, 10, 17
        self.baseline = (
            'G|10|10|0|144\n'
            'M|17|5|5|0|0|-1|-1|0|-1|-1|1\n'
            'P|0|1|1|1|0|0|1|10|0|-1\n'
            'P|1|1|0|0|1|1|1|0|0|-1\n'
            'U|0|3|1|2|2|2|0|0|1|0|0|\n'
            'U|1|4|1|5|5|2|0|0|1|0|0|\n')

    def tearDown(self):
        self.temp.cleanup()

    def sample(self, mode='move'):
        ranged = int(mode == 'range')
        fixture = (ranged, self.owner, self.unit, self.rival_player, self.rival_team,
                   self.target_unit, self.x, self.y)
        lines = [f'INTERACTIVE_GAME_STARTED={self.turn}|{self.owner}|12|12',
                 'INTERACTIVE_DECLARE_WAR_FIXTURE=' + '|'.join(map(str, fixture))]
        posted, native_inputs, ui_inputs, scenes = [], [], [], []
        world_generations = (300, 301, 302)
        ui_generations = (400, 401, 402)
        world_key = 0x5A57000000000000 | (1 << 32) | self.plot_index
        button_keys = (1101, 1102, 1103)
        for attempt, (world_generation, ui_generation) in enumerate(zip(world_generations, ui_generations)):
            lines.append(f'INTERACTIVE_DECLARE_WAR_WORLD_TARGET={attempt}|{self.unit}|{self.plot_index}|{world_key}|{world_generation}')
            lines.append(f'INTERACTIVE_SMOKE_BUTTON={world_generation}|{world_key}|5|0')
            lines.append(f'INTERACTIVE_SMOKE_POSTED={world_generation}|{world_key}|50|50')
            lines.append(f'INTERACTIVE_WINDOW_INPUT={world_generation}|5|{world_key}|1')
            posted.append(f'{world_generation}|{world_key}|50|50')
            native_inputs.append(f'{world_generation}|5|{world_key}|1')
            world_scene = {'generation': world_generation, 'activePlayer': self.owner,
                           'plots': [[self.plot_index, self.x, self.y, 1, 1]],
                           'hits': [[world_key, 70, 70, 80, 80]],
                           'units': [{'owner': self.owner, 'id': self.unit, 'selected': True,
                                      'x': 2, 'y': 2}],
                           'visibleForeignUnits': [{'owner': self.rival_player, 'id': self.target_unit,
                                                    'x': self.x, 'y': self.y, 'hostile': False}]}
            (self.session / f'play-scene-{world_generation}.json').write_text(
                json.dumps(world_scene), encoding='utf8')
            if attempt == 1:
                virtual_key, control_key = 27, 0
                lines.append(f'INTERACTIVE_DECLARE_WAR_CHOICE={attempt}|27|0|{ui_generation}')
                lines.append(f'INTERACTIVE_DECLARE_WAR_POSTED_ESCAPE=27|{ui_generation}')
                lines.append(f'INTERACTIVE_UI_NATIVE_KEY={ui_generation}|declare-war|27|1|0')
                ui_inputs.append(f'{ui_generation}|0|0|1')
                lines.append(f'INTERACTIVE_UI_NATIVE_INPUT={ui_generation}|0|0|1')
                lines.append(f'INTERACTIVE_DECLARE_WAR_OBSERVATION=1|27|1|0|0|1')
            else:
                virtual_key = 0
                control_key = button_keys[attempt]
                button_id = 'Button2' if attempt == 0 else 'Button1'
                lines.append(f'INTERACTIVE_DECLARE_WAR_CHOICE={attempt}|0|{control_key}|{ui_generation}')
                lines.append(f'INTERACTIVE_SMOKE_BUTTON={ui_generation}|{control_key}|1|0')
                lines.append(f'INTERACTIVE_SMOKE_POSTED={ui_generation}|{control_key}|50|50')
                posted.append(f'{ui_generation}|{control_key}|50|50')
                ui_inputs.append(f'{ui_generation}|1|{control_key}|1')
                lines.append(f'INTERACTIVE_UI_NATIVE_INPUT={ui_generation}|1|{control_key}|1')
                confirmed, unchanged = (0, 1) if attempt == 0 else (1, 0)
                lines.append(f'INTERACTIVE_DECLARE_WAR_OBSERVATION=2|{control_key}|1|0|{confirmed}|{unchanged}')
            lines.append(f'INTERACTIVE_UI_FRAME={attempt + 1}|{ui_generation}|1|ui|0|0|0|0')
            snapshot = {'contextName': 'DeclareWarPopup', 'popupKind': 'DeclareWar', 'active': True,
                        'inputTargets': [
                            {'key': button_keys[0], 'id': 'Button2', 'event': 'LeftClick', 'visible': True,
                             'disabled': False, 'clippedBounds': {'x': 40, 'y': 40, 'width': 80, 'height': 80}},
                            {'key': button_keys[2], 'id': 'Button1', 'event': 'LeftClick', 'visible': True,
                             'disabled': False, 'clippedBounds': {'x': 40, 'y': 40, 'width': 80, 'height': 80}}]}
            snapshot_path = self.session / f'play-ui-{attempt + 1}.json'
            snapshot_path.write_text(json.dumps(snapshot), encoding='utf8')
            scenes.append({'sequence': attempt + 1, 'context': 'declare-war', 'session': str(self.session),
                           'snapshot_before_sha256': hashlib.sha256(snapshot_path.read_bytes()).hexdigest(),
                           'snapshot_state_unchanged': True})
            if attempt == 0:
                lines.append('INTERACTIVE_DECLARE_WAR_REJECTED=0|STATE_UNCHANGED|AT_PEACE')
            elif attempt == 1:
                lines.append('INTERACTIVE_DECLARE_WAR_REJECTED=1|STATE_UNCHANGED|AT_PEACE')
        diplo = _sdk_enum_value(SDK_HEADER, 'FromUIDiploEventTypes', 'FROM_UI_DIPLO_EVENT_HUMAN_DECLARES_WAR')
        commands = [(0, self.rival_team, 1, 0, 0), (1, diplo, self.rival_player, 0, 0)]
        if mode == 'move':
            commands.append((2, self.x, self.y, 0, 0))
        else:
            push = _sdk_enum_value(SDK_HEADER, 'GameMessageTypes', 'GAMEMESSAGE_PUSH_MISSION')
            selection = _sdk_enum_value(SDK_HEADER, 'InterfaceModeTypes', 'INTERFACEMODE_SELECTION')
            commands.extend([(3, push, 50, self.x, self.y), (4, selection, 0, 0, 0)])
            database = sqlite3.connect(self.session / 'rules.db')
            database.execute('CREATE TABLE Missions(ID INTEGER, Type TEXT)')
            database.execute("INSERT INTO Missions VALUES(50, 'MISSION_RANGE_ATTACK')")
            database.commit()
            database.close()
        for command in commands:
            lines.append('INTERACTIVE_DECLARE_WAR_COMMAND=' + '|'.join(map(str, command)))
        lines.extend([
            'INTERACTIVE_DECLARE_WAR_CONFIRMED=' + '|'.join(map(str, (self.owner, self.unit, self.rival_team,
                                                                        self.x, self.y, ranged))),
            'INTERACTIVE_DECLARE_WAR_VERIFIED=' + '|'.join(map(str, fixture))])
        lines.extend(f'INTERACTIVE_DECLARE_WAR_INPUT={self.owner}|{self.unit}|{self.turn}|{self.rival_team}|{self.x}|{self.y}|{ranged}'
                     for _ in range(3))
        for attempt in range(3):
            before = self.session / f'play-declare-war-before-{attempt}-state.txt'
            after = self.session / f'play-declare-war-after-{attempt}-state.txt'
            before.write_text(self.baseline, encoding='utf8')
            after.write_text(self.baseline if attempt < 2 else self.baseline + 'WAR|declared\n', encoding='utf8')
        return '\n'.join(lines) + '\n', posted, native_inputs, ui_inputs, scenes, fixture

    def verify(self, mode='move', mutate=None):
        text, posted, native_inputs, ui_inputs, scenes, fixture = self.sample(mode)
        if mutate:
            text, posted, native_inputs, ui_inputs, scenes = mutate(text, posted, native_inputs, ui_inputs, scenes)
        # The workspace sandbox denies Win32 final-path resolution for newly
        # created fixture paths. These controlled temporary inputs need only
        # exercise the verifier's content, identity, and containment checks.
        with mock.patch.object(Path, 'resolve', lambda path, strict=False: path):
            return verify_declare_war_smoke(text, posted, native_inputs, ui_inputs,
                                            self.sessions, scenes, mode)

    def test_original_move_batch_and_three_native_choices(self):
        result = self.verify('move')
        self.assertTrue(result['validated'], result['failures'])
        self.assertEqual([row['button_id'] for row in result['posted_clicks'] if 'button_id' in row],
                         ['Button2', 'Button1'])
        self.assertEqual([row['button_kind'] for row in result['posted_clicks'] if 'button_kind' in row],
                         ['5', '5', '5'])

    def test_range_mission_comes_from_the_owning_rules_database(self):
        result = self.verify('range')
        self.assertTrue(result['validated'], result['failures'])
        self.assertEqual(result['range_mission']['id'], 50)

    def test_presentation_input_kinds_cannot_replace_host_observations(self):
        def mutate(text, posted, native, ui, scenes):
            text = text.replace('INTERACTIVE_DECLARE_WAR_OBSERVATION=1|27|',
                                'INTERACTIVE_DECLARE_WAR_OBSERVATION=0|27|')
            text = text.replace('INTERACTIVE_DECLARE_WAR_OBSERVATION=2|',
                                'INTERACTIVE_DECLARE_WAR_OBSERVATION=1|')
            return text, posted, native, ui, scenes
        result = self.verify(mutate=mutate)
        self.assertFalse(result['validated'])
        self.assertTrue(any('native input observation' in failure for failure in result['failures']))

    def test_cancellation_state_must_remain_byte_identical(self):
        def mutate(text, posted, native, ui, scenes):
            (self.session / 'play-declare-war-after-0-state.txt').write_text(self.baseline + 'G|changed\n', encoding='utf8')
            return text, posted, native, ui, scenes
        result = self.verify(mutate=mutate)
        self.assertFalse(result['validated'])
        self.assertTrue(any('cancellation attempt 0 changed' in failure for failure in result['failures']))

    def test_yes_key_must_be_the_original_button1_callback(self):
        def mutate(text, posted, native, ui, scenes):
            return text.replace('INTERACTIVE_DECLARE_WAR_CHOICE=2|0|1103|402',
                                'INTERACTIVE_DECLARE_WAR_CHOICE=2|0|1101|402'), posted, native, ui, scenes
        result = self.verify(mutate=mutate)
        self.assertFalse(result['validated'])
        self.assertTrue(any('original Button1' in failure for failure in result['failures']))

    def test_escape_requires_a_posted_vks_escape(self):
        def mutate(text, posted, native, ui, scenes):
            return text.replace('INTERACTIVE_DECLARE_WAR_POSTED_ESCAPE=27|401\n', ''), posted, native, ui, scenes
        result = self.verify(mutate=mutate)
        self.assertFalse(result['validated'])
        self.assertTrue(any('posted VK_ESCAPE' in failure for failure in result['failures']))

    def test_world_target_requires_consumed_right_click(self):
        def mutate(text, posted, native, ui, scenes):
            return text, posted, [row.replace(f'|5|{0x5A57000000000000 | (1 << 32) | self.plot_index}|1',
                                               f'|1|{0x5A57000000000000 | (1 << 32) | self.plot_index}|1')
                                  if row.startswith('300|') else row
                                 for row in native], ui, scenes
        result = self.verify(mutate=mutate)
        self.assertFalse(result['validated'])
        self.assertTrue(any('posted and consumed native map click' in failure for failure in result['failures']))

    def test_command_order_and_raw_diplomacy_args_are_exact(self):
        def mutate(text, posted, native, ui, scenes):
            change = f'INTERACTIVE_DECLARE_WAR_COMMAND=0|{self.rival_team}|1|0|0\n'
            diplo = (f'INTERACTIVE_DECLARE_WAR_COMMAND=1|'
                     f'{_sdk_enum_value(SDK_HEADER, "FromUIDiploEventTypes", "FROM_UI_DIPLO_EVENT_HUMAN_DECLARES_WAR")}'
                     f'|{self.rival_player}|0|0\n')
            return text.replace(change + diplo, diplo + change), posted, native, ui, scenes
        result = self.verify(mutate=mutate)
        self.assertFalse(result['validated'])
        self.assertTrue(any('exact tuples' in failure for failure in result['failures']))

        def bad_args(text, posted, native, ui, scenes):
            old = (f'INTERACTIVE_DECLARE_WAR_COMMAND=1|'
                   f'{_sdk_enum_value(SDK_HEADER, "FromUIDiploEventTypes", "FROM_UI_DIPLO_EVENT_HUMAN_DECLARES_WAR")}'
                   f'|{self.rival_player}|0|0')
            return text.replace(old, old[:-1] + '1'), posted, native, ui, scenes
        result = self.verify(mutate=bad_args)
        self.assertFalse(result['validated'])
        self.assertTrue(any('exact tuples' in failure for failure in result['failures']))


if __name__ == '__main__':
    unittest.main(verbosity=2)
