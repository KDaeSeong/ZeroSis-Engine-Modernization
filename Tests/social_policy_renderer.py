"""Focused contract tests for original SocialPolicy scene metadata and callback proof."""
from __future__ import annotations

from pathlib import Path
import sys
import unittest
import xml.etree.ElementTree as ET

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / 'tools'))

from civ5_ui_assets import require
from ui_pixel_scene import (Compiler, validate_social_policy_hover_gate,
                            multiply_opacity,
                            validate_social_policy_metadata,
                            validate_social_policy_zero_area_alpha_anim)
from interactive_ui_driver import CONTEXTS, validate_social_policy_scene_proof


LAYOUT = r'C:\Civ5\Assets\DLC\Expansion2\UI\InGame\Popups\SocialPolicyPopup.xml'
SCRIPT = r'C:\Civ5\Assets\DLC\Expansion2\UI\InGame\Popups\SocialPolicyPopup.lua'
STYLES = r'C:\Civ5\Assets\UI\Styles.xml'


def fixture():
    state = {
        'activePlayer': 0, 'currentTab': 'SocialPolicies', 'policyInfo': False,
        'hasCity': True, 'policyTabBranchIds': [0, 1, 2, 3, 4, 5], 'ideologyPaneVisible': False,
        'policies': [{'id': 13, 'branch': 'POLICY_BRANCH_TRADITION',
                      'has': False, 'canAdopt': True, 'blocked': False}],
        'branches': ([{'id': branch_id, 'type': branch_type,
                       'unlocked': True, 'canUnlock': False, 'blocked': False}
                      for branch_id, branch_type in enumerate((
                          'POLICY_BRANCH_TRADITION', 'POLICY_BRANCH_LIBERTY', 'POLICY_BRANCH_HONOR',
                          'POLICY_BRANCH_PIETY', 'POLICY_BRANCH_PATRONAGE'))] +
                     [{'id': 5, 'type': 'POLICY_BRANCH_COMMERCE',
                       'unlocked': False, 'canUnlock': True, 'blocked': False}]),
        'branchSwitchConfirmationPresent': False, 'ideologyChangePresent': False,
        'originalLayoutXml': {'path': LAYOUT, 'sha256': 'a' * 64},
        'originalLayoutLua': {'path': SCRIPT, 'sha256': 'b' * 64},
    }
    targets = [
        {'key': 10, 'id': 'TabButtonSocialPolicies', 'event': 'LeftClick'},
        {'key': 11, 'id': 'TabButtonIdeologies', 'event': 'LeftClick'},
        {'key': 12, 'id': 'PolicyInfo', 'event': 'LeftClick'},
        {'key': 13, 'id': 'BranchButton5', 'event': 'LeftClick', 'void1': 5},
        {'key': 14, 'id': 'PolicyIcon', 'event': 'LeftClick', 'void1': 13},
        {'key': 15, 'id': 'CloseButton', 'event': 'LeftClick'},
    ]
    snapshot = {'socialPolicy': state, 'inputTargets': targets,
                'tree': {'kind': 'Context', 'children': [
                    {'id': 'PolicyInfo', 'hidden': False, 'checked': False,
                     'defaultSize': {
                         'policy': 'SOCIAL_POLICY_BUTTON_16_DEFAULT_CANDIDATE_V1',
                         'style': 'Button_16', 'width': 32, 'height': 32,
                         'texture': 'Assets/UI/Art/Controls/Checkbox.dds',
                         'source': {'path': STYLES, 'sha256': 'c' * 64},
                     }, 'children': []},
                    {'id': 'PolicyConfirm', 'hidden': True, 'children': []},
                    {'id': 'TenetConfirm', 'hidden': True, 'children': []},
                    {'id': 'ChangeIdeologyConfirm', 'hidden': True, 'children': []},
                ]}}
    proof = {
        'policy': 'ORIGINAL_SOCIAL_POLICY_POPUP_RETAINED_TREE_V1', 'active_player': 0,
        'current_tab': 'SocialPolicies', 'policy_info': False, 'policy_count': 1,
        'has_city': True, 'policy_tab_branch_ids': [0, 1, 2, 3, 4, 5], 'ideology_pane_visible': False,
        'branch_count': 6, 'branch_switch_confirmation_present': False,
        'ideology_change_present': False, 'retail_pixels_verified': False,
        'all_policy_actions_use_stock_callbacks': True, 'full_policy_gameplay_coverage': False,
        'source_contract': {
            'layout_source': {'path': LAYOUT, 'sha256': 'a' * 64},
            'script_source': {'path': SCRIPT, 'sha256': 'b' * 64},
        },
        'original_input_targets': targets,
        'confirmation_states': {'PolicyConfirm': False, 'TenetConfirm': False,
                                'ChangeIdeologyConfirm': False},
    }
    manifest = {
        'social_policy_scene': proof,
        'social_policy_hover_gate_policy': {
            'policy': 'ZEROSIS_RETAINED_SOCIAL_POLICY_INVERSE_HOVER_GATE_V1',
            'gate_count': 0, 'hovered_keys': [],
            'blank_area_hover_verified': False, 'retail_behavior_verified': False,
        },
        'social_policy_check_atlas_policy': {
            'policy': 'CIV5_SOCIAL_POLICY_CHECK_ATLAS_FOUR_STATE_CANDIDATE_V1',
            'retail_widget_state_mapping_verified': False, 'retail_pixels_verified': False,
            'assets': [{'requested_name': 'Assets/UI/Art/Controls/Checkbox.dds',
                        'conversion': {'width': 32, 'height': 128},
                        'source': {'path': 'checkbox.dds', 'sha256': 'd' * 64},
                        'output': {'path': 'textures/checkbox.dds', 'sha256': 'e' * 64}}],
        },
        'original_context_sources': [
            {'path': LAYOUT, 'sha256': 'a' * 64}, {'path': SCRIPT, 'sha256': 'b' * 64},
            {'path': STYLES, 'sha256': 'c' * 64},
        ],
    }
    return snapshot, manifest


class SocialPolicyRendererContractTests(unittest.TestCase):
    def test_context_is_routable_and_valid_snapshot_accepted(self):
        self.assertIn('social-policy', CONTEXTS)
        snapshot, manifest = fixture()
        validate_social_policy_metadata(snapshot['socialPolicy'])
        validate_social_policy_scene_proof(snapshot, manifest, closed=False)

    def test_wrong_tab_key_or_callback_id_is_rejected(self):
        for index, value in ((0, 'TabButtonIdeologies'), (3, 'BranchButton6'), (4, 'NoSuchPolicy')):
            with self.subTest(index=index):
                snapshot, manifest = fixture()
                snapshot['inputTargets'][index]['id'] = value
                manifest['social_policy_scene']['original_input_targets'] = snapshot['inputTargets']
                with self.assertRaises(RuntimeError):
                    validate_social_policy_scene_proof(snapshot, manifest, closed=False)

    def test_culture_exhausted_all_adoption_targets_absent_is_valid(self):
        snapshot, manifest = fixture()
        snapshot['socialPolicy']['branches'][5].update(canUnlock=False, unlocked=True)
        snapshot['socialPolicy']['policies'][0].update(canAdopt=False, has=True)
        snapshot['inputTargets'][:] = [row for row in snapshot['inputTargets']
                                      if row['id'] not in ('BranchButton5', 'PolicyIcon')]
        validate_social_policy_metadata(snapshot['socialPolicy'])
        validate_social_policy_scene_proof(snapshot, manifest, closed=False)

    def test_missing_unlockable_branch_target_still_rejected(self):
        snapshot, manifest = fixture()
        snapshot['inputTargets'][:] = [row for row in snapshot['inputTargets'] if row['id'] != 'BranchButton5']
        with self.assertRaisesRegex(RuntimeError, 'missing an original callback target'):
            validate_social_policy_scene_proof(snapshot, manifest, closed=False)

    def test_no_city_allows_sdk_unlockable_branch_without_original_enabled_target(self):
        snapshot, manifest = fixture()
        snapshot['socialPolicy']['hasCity'] = False
        manifest['social_policy_scene']['has_city'] = False
        snapshot['inputTargets'][:] = [row for row in snapshot['inputTargets'] if row['id'] != 'BranchButton5']
        manifest['social_policy_scene']['original_input_targets'] = snapshot['inputTargets']
        validate_social_policy_metadata(snapshot['socialPolicy'])
        validate_social_policy_scene_proof(snapshot, manifest, closed=False)

    def test_owned_branch_can_unlock_true_does_not_require_button(self):
        snapshot, manifest = fixture()
        snapshot['socialPolicy']['branches'][5].update(unlocked=True, canUnlock=True)
        snapshot['inputTargets'][:] = [row for row in snapshot['inputTargets'] if row['id'] != 'BranchButton5']
        manifest['social_policy_scene']['original_input_targets'] = snapshot['inputTargets']
        validate_social_policy_scene_proof(snapshot, manifest, closed=False)

    def test_missing_one_of_multiple_unlockable_branch_targets_is_rejected(self):
        snapshot, manifest = fixture()
        snapshot['socialPolicy']['branches'][4].update(unlocked=False, canUnlock=True)
        snapshot['inputTargets'].append(
            {'key': 16, 'id': 'BranchButton4', 'event': 'LeftClick', 'void1': 4})
        snapshot['inputTargets'][:] = [row for row in snapshot['inputTargets'] if row['id'] != 'BranchButton5']
        manifest['social_policy_scene']['original_input_targets'] = snapshot['inputTargets']
        with self.assertRaisesRegex(RuntimeError, 'missing an original callback target'):
            validate_social_policy_scene_proof(snapshot, manifest, closed=False)

    def test_purchase_by_level_branch_is_excluded_from_social_policy_buttons(self):
        snapshot, manifest = fixture()
        snapshot['socialPolicy']['branches'].append(
            {'id': 6, 'type': 'POLICY_BRANCH_FREEDOM',
             'unlocked': False, 'canUnlock': True, 'blocked': False})
        manifest['social_policy_scene']['branch_count'] = 7
        # The original loop stops before this SDK row, so it is not in the exact tab prefix.
        validate_social_policy_scene_proof(snapshot, manifest, closed=False)

    @staticmethod
    def add_adoptable_tenet(snapshot, manifest):
        state = snapshot['socialPolicy']
        state['branches'].append({'id': 9, 'type': 'POLICY_BRANCH_FREEDOM',
                                  'unlocked': True, 'canUnlock': False, 'blocked': False})
        state['policies'].append({'id': 63, 'branch': 'POLICY_BRANCH_FREEDOM',
                                  'has': False, 'canAdopt': True, 'blocked': False})
        manifest['social_policy_scene']['branch_count'] = len(state['branches'])
        manifest['social_policy_scene']['policy_count'] = len(state['policies'])

    def test_adoptable_tenet_does_not_require_policy_icon_on_social_policy_tab(self):
        snapshot, manifest = fixture()
        self.add_adoptable_tenet(snapshot, manifest)
        snapshot['socialPolicy']['policies'][0]['canAdopt'] = False
        snapshot['inputTargets'][:] = [row for row in snapshot['inputTargets'] if row['id'] != 'PolicyIcon']
        # Map actual numeric IDs to Type names, not branch-array positions.
        snapshot['socialPolicy']['branches'].reverse()
        validate_social_policy_scene_proof(snapshot, manifest, closed=False)

    def test_adoptable_normal_policy_still_requires_its_target_when_tenet_is_adoptable(self):
        for missing_target in ('absent', 'wrong_tenet_payload'):
            with self.subTest(target=missing_target):
                snapshot, manifest = fixture()
                self.add_adoptable_tenet(snapshot, manifest)
                snapshot['socialPolicy']['branches'].reverse()
                validate_social_policy_scene_proof(snapshot, manifest, closed=False)
                if missing_target == 'absent':
                    snapshot['inputTargets'][:] = [row for row in snapshot['inputTargets']
                                                  if row['id'] != 'PolicyIcon']
                else:
                    snapshot['inputTargets'][4]['void1'] = 63
                with self.assertRaisesRegex(RuntimeError, 'SDK-adoptable policy but no original callback'):
                    validate_social_policy_scene_proof(snapshot, manifest, closed=False)

    def test_branch_opener_without_branch_type_does_not_require_policy_icon(self):
        snapshot, manifest = fixture()
        snapshot['socialPolicy']['policies'][0]['branch'] = ''
        snapshot['inputTargets'][:] = [row for row in snapshot['inputTargets'] if row['id'] != 'PolicyIcon']
        validate_social_policy_scene_proof(snapshot, manifest, closed=False)

    def test_branch_type_mapping_rejects_malformed_or_ambiguous_sdk_metadata(self):
        mutations = (
            lambda state: state['branches'][0].pop('type'),
            lambda state: state['branches'][0].update(type=None),
            lambda state: state['branches'][0].update(type=1),
            lambda state: state['branches'][0].update(type=''),
            lambda state: state['branches'][0].update(type='   '),
            lambda state: state['branches'][0].update(type='X' * 129),
            lambda state: state['branches'][1].update(type=state['branches'][0]['type']),
            lambda state: state['branches'][1].update(id=0),
            lambda state: state['policies'][0].update(branch='POLICY_BRANCH_UNKNOWN'),
        )
        for index, mutate in enumerate(mutations):
            with self.subTest(mutation=index):
                snapshot, manifest = fixture()
                mutate(snapshot['socialPolicy'])
                with self.assertRaises((RuntimeError, ValueError)):
                    validate_social_policy_scene_proof(snapshot, manifest, closed=False)

    def test_city_and_policy_tab_metadata_is_validated_and_reconciled(self):
        for mutate in (
            lambda state: state.update(hasCity=1),
            lambda state: state.update(policyTabBranchIds=[6]),
            lambda state: state.update(policyTabBranchIds=[5, 0]),
        ):
            snapshot, _manifest = fixture()
            mutate(snapshot['socialPolicy'])
            with self.assertRaises((RuntimeError, ValueError)):
                validate_social_policy_metadata(snapshot['socialPolicy'])
        snapshot, manifest = fixture()
        manifest['social_policy_scene']['has_city'] = False
        with self.assertRaises(RuntimeError):
            validate_social_policy_scene_proof(snapshot, manifest, closed=False)
        snapshot, manifest = fixture()
        manifest['social_policy_scene']['policy_tab_branch_ids'] = []
        with self.assertRaises(RuntimeError):
            validate_social_policy_scene_proof(snapshot, manifest, closed=False)

    def test_branch_zero_target_satisfies_actual_sdk_unlockability(self):
        snapshot, manifest = fixture()
        snapshot['socialPolicy']['branches'][0].update(unlocked=False, canUnlock=True)
        snapshot['socialPolicy']['branches'][5].update(unlocked=True, canUnlock=False)
        snapshot['inputTargets'][3].update(id='BranchButton0', void1=0)
        validate_social_policy_scene_proof(snapshot, manifest, closed=False)
        snapshot['inputTargets'][3]['void1'] = 5
        with self.assertRaises(RuntimeError):
            validate_social_policy_scene_proof(snapshot, manifest, closed=False)

    def test_wrong_sdk_callback_payload_and_event_are_rejected(self):
        for field, value in (('void1', 6), ('void1', 14), ('event', 'RightClick')):
            with self.subTest(field=field, value=value):
                snapshot, manifest = fixture()
                target_index = 3 if value == 6 else 4 if value == 14 else 0
                snapshot['inputTargets'][target_index][field] = value
                manifest['social_policy_scene']['original_input_targets'] = snapshot['inputTargets']
                with self.assertRaises(RuntimeError):
                    validate_social_policy_scene_proof(snapshot, manifest, closed=False)

    def test_missing_extra_or_mutated_callback_rejected(self):
        snapshot, manifest = fixture()
        snapshot['inputTargets'].pop()
        with self.assertRaises(RuntimeError):
            validate_social_policy_scene_proof(snapshot, manifest, closed=False)
        snapshot, manifest = fixture()
        snapshot['inputTargets'].append(dict(snapshot['inputTargets'][-1], key=16))
        manifest['social_policy_scene']['original_input_targets'] = snapshot['inputTargets']
        with self.assertRaises(RuntimeError):
            validate_social_policy_scene_proof(snapshot, manifest, closed=False)

    def test_source_mismatch_and_overclaimed_coverage_rejected(self):
        for mutate in ('source', 'coverage'):
            snapshot, manifest = fixture()
            if mutate == 'source':
                snapshot['socialPolicy']['originalLayoutLua']['sha256'] = 'c' * 64
            else:
                manifest['social_policy_scene']['full_policy_gameplay_coverage'] = True
            with self.assertRaises(RuntimeError):
                validate_social_policy_scene_proof(snapshot, manifest, closed=False)

    def test_closed_contract_requires_empty_targets(self):
        snapshot, manifest = fixture()
        snapshot['inputTargets'] = []
        manifest['social_policy_scene']['original_input_targets'] = []
        validate_social_policy_scene_proof(snapshot, manifest, closed=True)
        snapshot['inputTargets'] = fixture()[0]['inputTargets']
        with self.assertRaises(RuntimeError):
            validate_social_policy_scene_proof(snapshot, manifest, closed=True)

    def test_inverse_hover_gate_requires_stock_scope_and_unverified_blank_area(self):
        node = {'kind': 'HideOnMouseOver', 'hovered': False,
                'hoverPolicy': 'ZEROSIS_RETAINED_SOCIAL_POLICY_INVERSE_HOVER_GATE_V1',
                'blankAreaHoverVerified': False,
                'sourceAttributes': {'Anchor': 'C,C'}, 'attributes': {'Anchor': 'C,C'},
                'children': [{'kind': 'Image'}]}
        self.assertIs(validate_social_policy_hover_gate(node), node)
        for field, value in (('hovered', 1), ('hoverPolicy', 'SHOW'),
                             ('blankAreaHoverVerified', True)):
            with self.subTest(field=field):
                bad = dict(node, **{field: value})
                with self.assertRaises(ValueError):
                    validate_social_policy_hover_gate(bad)

    def test_scene_proof_reconciles_inverse_hover_gate_state(self):
        snapshot, manifest = fixture()
        gate = {'key': 30, 'kind': 'HideOnMouseOver', 'id': 'LockedBox', 'hidden': False,
                'hovered': True,
                'hoverPolicy': 'ZEROSIS_RETAINED_SOCIAL_POLICY_INVERSE_HOVER_GATE_V1',
                'blankAreaHoverVerified': False,
                'sourceAttributes': {'Anchor': 'C,C'}, 'attributes': {'Anchor': 'C,C'},
                'children': []}
        snapshot['tree']['children'].append(gate)
        manifest['social_policy_hover_gate_policy'].update(gate_count=1, hovered_keys=[30])
        validate_social_policy_scene_proof(snapshot, manifest, closed=False)
        manifest['social_policy_hover_gate_policy']['hovered_keys'] = []
        with self.assertRaises(RuntimeError):
            validate_social_policy_scene_proof(snapshot, manifest, closed=False)

    @staticmethod
    def zero_area_alpha_anim(label_id='FreePoliciesLabel'):
        original = ET.parse(PROJECT / 'Source/Assets/UI/Assets/DLC/Expansion2/UI/InGame/Popups/SocialPolicyPopup.xml')
        wrapper = next(element for element in original.iter('AlphaAnim')
                       if len(element) == 1 and element[0].get('ID') == label_id)
        attrs, label_attrs = dict(wrapper.attrib), dict(wrapper[0].attrib)
        key, y = (23, 260.5) if label_id == 'FreePoliciesLabel' else (242, 268)
        return {
            'key': key, 'kind': 'AlphaAnim', 'id': '', 'hidden': False,
            'width': 0, 'height': 0, 'x': 485.5, 'y': y,
            'attributes': dict(attrs), 'sourceAttributes': dict(attrs),
            'texture': '', 'textureX': 0, 'textureY': 0,
            'animation': {'clock': 0.1554416, 'alpha': 0.874973216},
            'children': [{
                'key': key + 1, 'kind': wrapper[0].tag, 'id': label_id, 'hidden': True,
                'width': 0, 'height': 19, 'x': 485.5, 'y': y - 9.5,
                'attributes': dict(label_attrs), 'sourceAttributes': dict(label_attrs),
                'children': [], 'text': '', 'texture': '',
            }],
        }

    @staticmethod
    def alpha_compiler(node, context='social-policy'):
        compiler = Compiler.__new__(Compiler)
        compiler.context = context
        compiler.width, compiler.height = 1920, 1080
        compiler.snapshot_clock = node['animation']['clock']
        compiler.styles = {}
        compiler.keys = set()
        compiler.geometry = []
        compiler.sprites = []
        return compiler

    def test_original_textureless_zero_area_alpha_wrappers_preserve_extent_and_inherited_alpha(self):
        for label_id in ('FreePoliciesLabel', 'FreeTenetsLabel'):
            with self.subTest(label=label_id):
                node = self.zero_area_alpha_anim(label_id)
                node['animation']['alpha'] = 0.4
                label = node['children'][0]
                label['hidden'] = False
                label['text'] = 'Free policies or tenets: 1'
                label['textFrame'] = {'x': label['x'], 'y': label['y'], 'width': 142, 'height': 19}
                validate_social_policy_zero_area_alpha_anim(node, node['attributes'])
                compiler = self.alpha_compiler(node)
                label_calls = []

                def capture_label(label_node, attrs, parent, inherited, clip, stack_y, stack_x=0, *, opacity=1.0):
                    label_calls.append({'parent': parent, 'clip': clip, 'opacity': opacity})
                    frame = label_node['textFrame']
                    return tuple(frame[name] for name in ('x', 'y', 'width', 'height'))

                compiler.label = capture_label
                compiler.node(node, (0, 0, 1920, 1080), {}, (0, 0, 1920, 1080), inherited_opacity=0.5)
                wrapper_bounds = (node['x'], node['y'], 0, 0)
                self.assertEqual(compiler.geometry[0]['bounds'], wrapper_bounds)
                self.assertEqual(compiler.geometry[1]['bounds'], (label['x'], label['y'], 142, 19))
                self.assertEqual(label_calls, [{'parent': wrapper_bounds,
                                                'clip': (0, 0, 1920, 1080), 'opacity': 0.2}])
                self.assertEqual(compiler.sprites, [])
                self.assertEqual(multiply_opacity((1, 1, 1, 0.5), label_calls[0]['opacity']),
                                 (1, 1, 1, 0.1))

    def test_hidden_free_policy_and_tenet_labels_produce_no_geometry_or_alpha_draw(self):
        for label_id in ('FreePoliciesLabel', 'FreeTenetsLabel'):
            with self.subTest(label=label_id):
                node = self.zero_area_alpha_anim(label_id)
                compiler = self.alpha_compiler(node)
                compiler.node(node, (0, 0, 1920, 1080), {}, (0, 0, 1920, 1080))
                self.assertEqual(len(compiler.geometry), 1)
                self.assertEqual(compiler.geometry[0]['bounds'], (node['x'], node['y'], 0, 0))
                self.assertEqual(compiler.sprites, [])

    def test_zero_area_alpha_exception_rejects_nonstock_source_or_retained_attributes(self):
        mutations = (
            lambda n: n['attributes'].update(Texture='Unexpected.dds'),
            lambda n: n['attributes'].update(Size='16,16'),
            lambda n: n['sourceAttributes'].update(Size='0,0'),
            lambda n: n.update(texture='Unexpected.dds'),
            lambda n: n.update(width=16),
            lambda n: n['attributes'].update(Anchor='R,C'),
            lambda n: n['sourceAttributes'].update(AlphaStart='.5'),
            lambda n: n['attributes'].update(Speed='2'),
            lambda n: n['children'][0].update(id='OtherLabel'),
            lambda n: n['children'][0].update(kind='Box'),
            lambda n: n['children'][0]['sourceAttributes'].update(FontStyle='Shadow'),
            lambda n: n['children'][0]['attributes'].update(Anchor='L,T'),
            lambda n: n['children'].append(dict(n['children'][0])),
        )
        for label_id in ('FreePoliciesLabel', 'FreeTenetsLabel'):
            for index, mutate in enumerate(mutations):
                with self.subTest(label=label_id, mutation=index):
                    node = self.zero_area_alpha_anim(label_id)
                    mutate(node)
                    with self.assertRaises(ValueError):
                        validate_social_policy_zero_area_alpha_anim(node, node['attributes'])

    def test_zero_area_alpha_exception_rejects_wrong_child_anchor_pairing(self):
        for label_id, other_id in (('FreePoliciesLabel', 'FreeTenetsLabel'),
                                   ('FreeTenetsLabel', 'FreePoliciesLabel')):
            for swap in ('child', 'placement'):
                with self.subTest(label=label_id, swap=swap):
                    node = self.zero_area_alpha_anim(label_id)
                    other = self.zero_area_alpha_anim(other_id)
                    if swap == 'child':
                        node['children'] = other['children']
                    else:
                        for field in ('attributes', 'sourceAttributes'):
                            for name in ('Anchor', 'Offset'):
                                node[field][name] = other[field][name]
                    with self.assertRaises(ValueError):
                        validate_social_policy_zero_area_alpha_anim(node, node['attributes'])

    def test_zero_area_alpha_wrappers_keep_clock_and_context_restrictions(self):
        for label_id in ('FreePoliciesLabel', 'FreeTenetsLabel'):
            for invalid in ('clock', 'alpha', 'context'):
                with self.subTest(label=label_id, invalid=invalid):
                    node = self.zero_area_alpha_anim(label_id)
                    compiler = self.alpha_compiler(node, 'production' if invalid == 'context' else 'social-policy')
                    if invalid == 'clock':
                        node['animation']['clock'] = -1
                    elif invalid == 'alpha':
                        node['animation']['alpha'] = float('nan')
                    with self.assertRaises(ValueError):
                        compiler.node(node, (0, 0, 1920, 1080), {}, (0, 0, 1920, 1080))


if __name__ == '__main__':
    unittest.main()
