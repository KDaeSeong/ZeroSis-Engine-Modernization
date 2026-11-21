"""Source-bound SaveMenu packets; does not open Host or certify retail pixels."""
import copy
import json
import unittest

from game_menu_ui_assets import small_source_directory
from save_menu_scene import verify_component
from game_menu_renderer import packet_records, packet_hit, walk
from prepare_ui_popup_assets import GAME
from ui_pixel_scene import save_menu_contract
import interactive_ui_driver as driver
import render_ui_popup

_component = None


def component():
    global _component
    if _component is None:
        _component = verify_component(include_snapshot=True)
    return _component


def render(snapshot, directory, *, closed=False):
    directory.mkdir()
    path = directory / 'snapshot.json'
    manifest = directory / 'manifest.json'
    path.write_text(json.dumps(snapshot, ensure_ascii=False), encoding='utf-8')
    (directory / 'inline_colors.json').write_text('{"colors":{}}', encoding='utf-8')
    (directory / 'inline_icons.json').write_text('{"icons":{}}', encoding='utf-8')
    render_ui_popup.prepare(path, directory, manifest, context='save-menu', closed=closed)
    return json.loads(manifest.read_text(encoding='utf-8'))


class SaveMenuRendererTests(unittest.TestCase):
    def test_original_tree_focus_and_input_proof_rejects_forgery(self):
        original = component()['named_snapshot']
        proof = save_menu_contract(original)
        self.assertEqual(proof['catalog_rows'], 2)
        self.assertFalse(proof['retail_pixels_verified'])
        self.assertFalse(proof['native_save_load_verified'])
        for mode in ('source', 'length', 'caret', 'timer', 'cloud', 'target', 'parent', 'name', 'focus_epoch', 'focus_token'):
            changed = copy.deepcopy(original)
            nodes = list(walk(changed['tree']))
            name = next(row for row in nodes if row.get('id') == 'NameBox')
            if mode == 'source': changed['saveMenu']['originalLua']['sha256'] = '0' * 64
            elif mode == 'length': name['maxLength'] = 64
            elif mode == 'caret': name['caretCodepoint'] = 1000
            elif mode == 'timer': changed['timerSemaphore'] = 1
            elif mode == 'cloud': next(row for row in nodes if row.get('id') == 'CloudCheck')['disabled'] = False
            elif mode == 'target': changed['inputTargets'].pop()
            elif mode == 'parent': changed['saveMenu']['parentContext'] = 'Other'
            elif mode == 'focus_epoch': changed['saveMenu']['focusEpoch'] = 0
            elif mode == 'focus_token': changed['saveMenu']['textInputFocusToken'] += 1
            else: changed['saveMenu']['name'] = 'Other'
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                save_menu_contract(changed)

    def test_exact_packet_hit_order_literal_name_and_closed_empty_scene(self):
        with small_source_directory() as temporary:
            snapshot = component()['named_snapshot']
            manifest = render(snapshot, temporary / 'named')
            driver.validate_save_menu_scene_proof(snapshot, manifest)
            records = packet_records(manifest)
            self.assertGreater(len(records['sprites']), 0)
            name = next(node for node in walk(snapshot['tree']) if node.get('id') == 'NameBox')
            self.assertEqual(packet_hit(records['hits'], name['x'] + 2, name['y'] + 2), name['key'])
            label = next(row for row in manifest['labels'] if row['key'] == name['key'])
            self.assertEqual(label['plain_text'], '검증 저장')
            self.assertTrue(label['literal_text'])
            self.assertFalse(label['retail_caret_timing_verified'])
            closed = component()['closed_snapshot']
            closed_manifest = render(closed, temporary / 'closed', closed=True)
            driver.validate_save_menu_scene_proof(closed, closed_manifest, closed=True)
            self.assertEqual(closed_manifest['sprite_count'], 0)
        self.assertFalse(temporary.exists())

    def test_long_korean_name_caret_clips_and_markup_is_literal(self):
        with small_source_directory() as temporary:
            for token, expected, scrolled in (
                    ('long_name_snapshot', '가' * 32, True),
                    ('long_home_snapshot', '가' * 32, False),
                    ('literal_name_snapshot', '[ICON_GOLD]', False)):
                with self.subTest(snapshot=token):
                    snapshot = component()[token]
                    manifest = render(snapshot, temporary / token)
                    driver.validate_save_menu_scene_proof(snapshot, manifest)
                    name = next(row for row in walk(snapshot['tree']) if row.get('id') == 'NameBox')
                    label = next(row for row in manifest['labels'] if row['key'] == name['key'])
                    self.assertEqual(label['plain_text'], expected)
                    self.assertTrue(label['literal_text'])
                    self.assertEqual(label['inline_icons'], [])
                    self.assertEqual(label['horizontal_scroll_pixels'] > 0, scrolled)
                    self.assertFalse(label['retail_text_scroll_verified'])
                    rectangle = (name['x'], name['y'], name['x'] + name['width'], name['y'] + name['height'])
                    sprites = [row for row in packet_records(manifest)['sprites'] if row[1] == name['key']]
                    self.assertGreater(len(sprites), 1)
                    self.assertTrue(all(tuple(row[10:14]) == rectangle for row in sprites))
                    caret = next(row for row in sprites if row[0] == 0xFFFFFFFF)
                    self.assertTrue(rectangle[0] <= caret[6] < caret[8] <= rectangle[2])
                    self.assertTrue(rectangle[1] <= caret[7] < caret[9] <= rectangle[3])
        self.assertFalse(temporary.exists())


if __name__ == '__main__':
    unittest.main()
