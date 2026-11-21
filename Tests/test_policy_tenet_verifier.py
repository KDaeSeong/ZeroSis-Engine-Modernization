from copy import deepcopy
from pathlib import Path
import sys
import tempfile
import unittest

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / 'tools'))
import verify_interactive_policy_tenets as verifier


FREEDOM = 9
BRANCH_NAMES = {0: 'POLICY_BRANCH_TRADITION', FREEDOM: 'POLICY_BRANCH_FREEDOM'}
BRANCH_RULES = [(0, BRANCH_NAMES[0], 0), (FREEDOM, BRANCH_NAMES[FREEDOM], 1)]
POLICY_RULES = [(0, None, 0), (100, BRANCH_NAMES[FREEDOM], 1), (101, BRANCH_NAMES[FREEDOM], 1),
                (102, BRANCH_NAMES[FREEDOM], 1), (103, BRANCH_NAMES[FREEDOM], 2)]


def inventories():
    initial = {'schema': 'ZEROSIS_SOCIAL_POLICY_SDK_INVENTORY_V1', 'source': 'SDK:Policies/PolicyBranches/JONSCulture',
               'activePlayer': 0, 'turn': 0, 'elapsed': 0, 'culture': 0, 'nextCost': 25, 'freePolicies': 0,
               'freeTenets': 0, 'ideology': -1, 'policySaving': False,
               'policies': [{'id': policy_id, 'branch': -1 if branch is None else FREEDOM, 'level': level,
                             'has': False, 'canAdopt': False, 'blocked': False} for policy_id, branch, level in POLICY_RULES],
               'branches': [{'id': 0, 'freePolicy': 0, 'unlocked': False, 'canUnlock': False, 'blocked': False},
                            {'id': FREEDOM, 'freePolicy': -1, 'unlocked': False, 'canUnlock': False, 'blocked': False}]}
    before = deepcopy(initial)
    before.update(ideology=FREEDOM, freeTenets=2)
    before['branches'][1]['unlocked'] = True
    for row in before['policies']:
        row['canAdopt'] = row['level'] == 1
    free1 = deepcopy(before)
    free1['freeTenets'] = 1
    free1['policies'][1].update(has=True, canAdopt=False)
    free2 = deepcopy(free1)
    free2.update(freeTenets=0, nextCost=35)
    free2['policies'][2].update(has=True, canAdopt=False)
    for row in free2['policies']:
        row['canAdopt'] = False
    funded = deepcopy(free2)
    funded['culture'] = free2['nextCost']
    funded['policies'][3]['canAdopt'] = True
    adopted = deepcopy(funded)
    adopted.update(culture=0, nextCost=45)
    adopted['policies'][3].update(has=True, canAdopt=False)
    next_turn = deepcopy(adopted)
    next_turn.update(turn=1, elapsed=1, culture=3)
    return initial, before, free1, free2, funded, adopted, next_turn


def snapshot(inventory, *, tab='Ideologies', choosing=False, confirming=False, selected=-1):
    policies = deepcopy(inventory['policies'])
    branches = deepcopy(inventory['branches'])
    for row in policies:
        row['branch'] = '' if row['branch'] == -1 else BRANCH_NAMES[row['branch']]
        del row['level']
    for row in branches:
        row['type'] = BRANCH_NAMES[row['id']]
        del row['freePolicy']
    meta = {'activePlayer': inventory['activePlayer'], 'currentTab': tab, 'policyInfo': True,
            'ideology': inventory['ideology'], 'freeTenets': inventory['freeTenets'], 'selectedTenet': selected,
            'ideologyPaneVisible': tab == 'Ideologies', 'branchSwitchConfirmationPresent': False,
            'ideologyChangePresent': False, 'policies': policies, 'branches': branches}
    return {'contextName': 'SocialPolicyPopup', 'popupKind': 'SocialPolicy', 'active': True,
            'hasRetainedPopupUi': True, 'timerSemaphore': 1, 'socialPolicy': meta,
            'tree': {'children': [{'id': 'PolicyConfirm', 'hidden': True}, {'id': 'TenetConfirm', 'hidden': not confirming},
                                  {'id': 'ChooseTenet', 'hidden': not choosing}, {'id': 'ChangeIdeologyConfirm', 'hidden': True},
                                  {'id': 'PolicyInfo', 'checked': True}]}}


class TenetInventoryTests(unittest.TestCase):
    def setUp(self):
        self.initial, self.before, self.free1, self.free2, self.funded, self.adopted, self.next_turn = inventories()

    def test_two_actual_free_choices_then_exact_paid_choice(self):
        verifier.verify_prerequisites(self.initial, self.before, FREEDOM)
        first = verifier.verify_tenet_adoption(self.before, self.free1, 100)
        second = verifier.verify_tenet_adoption(self.free1, self.free2, 101)
        verifier.verify_exact_culture_grant(self.free2, self.funded)
        paid = verifier.verify_tenet_adoption(self.funded, self.adopted, 102)
        self.assertEqual([r['payment'] for r in (first, second, paid)], ['free_tenet', 'free_tenet', 'culture'])
        self.assertEqual([r['culture_cost'] for r in (first, second, paid)], [0, 0, 35])
        verifier.verify_next_turn(self.adopted, self.next_turn)

    def test_old_inventory_without_new_native_fields_is_rejected(self):
        for field in ('freeTenets', 'ideology'):
            changed = deepcopy(self.before)
            del changed[field]
            with self.subTest(field=field), self.assertRaises(verifier.VerificationError):
                verifier.validate_inventory(changed)
        del self.before['policies'][1]['level']
        with self.assertRaises(verifier.VerificationError):
            verifier.validate_inventory(self.before)

    def test_bool_integer_and_invalid_level_are_rejected(self):
        for field, value in (('freeTenets', True), ('ideology', False), ('freeTenets', -1), ('ideology', -2)):
            changed = deepcopy(self.before)
            changed[field] = value
            with self.subTest(field=field, value=value), self.assertRaises(verifier.VerificationError):
                verifier.validate_inventory(changed)
        for level in (True, -1, 4, 1.0):
            changed = deepcopy(self.before)
            changed['policies'][1]['level'] = level
            with self.subTest(level=level), self.assertRaises(verifier.VerificationError):
                verifier.validate_inventory(changed)

    def test_duplicate_ids_and_dangling_references_are_rejected(self):
        edits = [lambda x: x['policies'].append(deepcopy(x['policies'][0])),
                 lambda x: x['policies'][1].update(branch=999),
                 lambda x: x['branches'][0].update(freePolicy=999),
                 lambda x: x.update(ideology=999)]
        for edit in edits:
            changed = deepcopy(self.before)
            edit(changed)
            with self.assertRaises(verifier.VerificationError):
                verifier.validate_inventory(changed)

    def test_prerequisite_cannot_pregrant_a_policy_or_second_branch(self):
        for edit in (lambda x: x['policies'][1].update(has=True), lambda x: x['branches'][0].update(unlocked=True),
                     lambda x: x.update(culture=25), lambda x: x.update(freePolicies=1),
                     lambda x: x.update(freeTenets=3), lambda x: x.update(nextCost=30)):
            changed = deepcopy(self.before)
            edit(changed)
            with self.assertRaises(verifier.VerificationError):
                verifier.verify_prerequisites(self.initial, changed, FREEDOM)

    def test_prerequisite_cannot_overwrite_existing_progress(self):
        changed = deepcopy(self.initial)
        changed['policies'][1]['has'] = self.before['policies'][1]['has'] = True
        with self.assertRaises(verifier.VerificationError):
            verifier.verify_prerequisites(changed, self.before, FREEDOM)

    def test_free_choice_must_consume_one_award_without_culture(self):
        for field, value in (('freeTenets', 2), ('freeTenets', 0), ('culture', 1), ('freePolicies', 1)):
            changed = deepcopy(self.free1)
            changed[field] = value
            with self.subTest(field=field, value=value), self.assertRaises(verifier.VerificationError):
                verifier.verify_tenet_adoption(self.before, changed, 100)

    def test_paid_choice_must_consume_actual_cost_and_no_free_award(self):
        for field, value in (('culture', 1), ('culture', 35), ('freeTenets', 1), ('freePolicies', 1)):
            changed = deepcopy(self.adopted)
            changed[field] = value
            with self.subTest(field=field, value=value), self.assertRaises(verifier.VerificationError):
                verifier.verify_tenet_adoption(self.funded, changed, 102)

    def test_adoption_cannot_change_owner_clock_ideology_or_unrelated_rows(self):
        for field, value in (('activePlayer', 1), ('turn', 1), ('elapsed', 1), ('ideology', 0)):
            changed = deepcopy(self.free1)
            changed[field] = value
            with self.subTest(field=field), self.assertRaises(verifier.VerificationError):
                verifier.verify_tenet_adoption(self.before, changed, 100)
        for edit in (lambda x: x['policies'][2].update(has=True), lambda x: x['policies'][2].update(level=2),
                     lambda x: x['policies'][2].update(blocked=True), lambda x: x['branches'][0].update(unlocked=True)):
            changed = deepcopy(self.free1)
            edit(changed)
            with self.assertRaises(verifier.VerificationError):
                verifier.verify_tenet_adoption(self.before, changed, 100)

    def test_wrong_or_unavailable_selected_policy_cannot_pass(self):
        for selected in (101, -1, True):
            with self.subTest(selected=selected), self.assertRaises(verifier.VerificationError):
                verifier.verify_tenet_adoption(self.before, self.free1, selected)
        for field, value in (('canAdopt', False), ('blocked', True), ('has', True), ('branch', 0), ('level', 2)):
            changed = deepcopy(self.before)
            changed['policies'][1][field] = value
            with self.subTest(field=field), self.assertRaises(verifier.VerificationError):
                verifier.verify_tenet_adoption(changed, self.free1, 100)

    def test_existing_owned_policy_must_not_be_removed(self):
        changed = deepcopy(self.free2)
        changed['policies'][1]['has'] = False
        with self.assertRaises(verifier.VerificationError):
            verifier.verify_tenet_adoption(self.free1, changed, 101)

    def test_culture_grant_cannot_pregrant_or_overfund(self):
        for edit in (lambda x: x.update(culture=36), lambda x: x.update(freeTenets=1),
                     lambda x: x.update(ideology=0), lambda x: x['policies'][3].update(has=True),
                     lambda x: x['branches'][0].update(unlocked=True)):
            changed = deepcopy(self.funded)
            edit(changed)
            with self.assertRaises(verifier.VerificationError):
                verifier.verify_exact_culture_grant(self.free2, changed)

    def test_next_turn_preserves_tenets_and_ideology_with_new_culture(self):
        verifier.verify_next_turn(self.adopted, self.next_turn)
        for edit in (lambda x: x.update(turn=0), lambda x: x.update(elapsed=0), lambda x: x.update(freeTenets=1),
                     lambda x: x.update(ideology=0), lambda x: x['policies'][3].update(has=False)):
            changed = deepcopy(self.next_turn)
            edit(changed)
            with self.assertRaises(verifier.VerificationError):
                verifier.verify_next_turn(self.adopted, changed)


class TenetSnapshotTests(unittest.TestCase):
    def setUp(self):
        self.inventory = inventories()[1]
        self.value = snapshot(self.inventory, choosing=True, confirming=True, selected=100)

    def verify(self, selected=100):
        verifier.verify_snapshot(self.value, self.inventory, 'Ideologies', True, True, True, BRANCH_NAMES, selected)

    def test_original_confirmation_matches_sdk_choice_and_payload(self):
        self.verify()

    def test_confirm_button_needs_selected_global_not_void1(self):
        self.value['inputTargets'] = [{'id': 'TenetConfirmYes', 'void1': None}]
        self.verify()
        with self.assertRaisesRegex(verifier.VerificationError, 'g_SelectedTenet'):
            self.verify(101)

    def test_confirmation_selection_cannot_be_missing_wrong_or_already_owned(self):
        for selected in (-1, True, 103, 999):
            self.value['socialPolicy']['selectedTenet'] = selected
            with self.subTest(selected=selected), self.assertRaises(verifier.VerificationError):
                self.verify()
        self.setUp()
        self.inventory['policies'][1].update(has=True, canAdopt=False)
        self.value = snapshot(self.inventory, choosing=True, confirming=True, selected=100)
        with self.assertRaises(verifier.VerificationError):
            self.verify()

    def test_no_confirmation_requires_selected_minus_one(self):
        value = snapshot(self.inventory)
        verifier.verify_snapshot(value, self.inventory, 'Ideologies', True, False, False, BRANCH_NAMES)
        value['socialPolicy']['selectedTenet'] = 100
        with self.assertRaises(verifier.VerificationError):
            verifier.verify_snapshot(value, self.inventory, 'Ideologies', True, False, False, BRANCH_NAMES)

    def test_chooser_and_confirmation_visibility_cannot_be_assumed(self):
        for name in ('ChooseTenet', 'TenetConfirm'):
            self.setUp()
            verifier.nodes(self.value['tree'], name)[0]['hidden'] = True
            with self.subTest(name=name), self.assertRaises(verifier.VerificationError):
                self.verify()

    def test_snapshot_sdk_metadata_flags_and_branch_types_are_exact(self):
        for edit in (lambda x: x['socialPolicy'].update(freeTenets=0), lambda x: x['socialPolicy'].update(ideology=0),
                     lambda x: x['socialPolicy'].update(ideologyPaneVisible=False),
                     lambda x: x['socialPolicy']['policies'][1].update(canAdopt=False),
                     lambda x: x['socialPolicy']['branches'][1].update(type='POLICY_BRANCH_ORDER'),
                     lambda x: x['socialPolicy']['policies'].append(deepcopy(x['socialPolicy']['policies'][1]))):
            self.setUp()
            edit(self.value)
            with self.assertRaises(verifier.VerificationError):
                self.verify()

    def test_option_nested_route_and_modal_identity_are_guarded(self):
        for edit in (lambda x: x.update(active=False), lambda x: x.update(timerSemaphore=0),
                     lambda x: x['socialPolicy'].update(policyInfo=False),
                     lambda x: x['socialPolicy'].update(ideologyChangePresent=True),
                     lambda x: x['socialPolicy'].update(branchSwitchConfirmationPresent=True)):
            self.setUp()
            edit(self.value)
            with self.assertRaises(verifier.VerificationError):
                self.verify()

    def test_boolean_values_cannot_impersonate_native_numeric_metadata(self):
        for edit in (lambda x: x.update(timerSemaphore=True), lambda x: x['socialPolicy'].update(activePlayer=False),
                     lambda x: x['socialPolicy'].update(ideology=True), lambda x: x['socialPolicy'].update(freeTenets=True)):
            self.setUp()
            edit(self.value)
            with self.assertRaises(verifier.VerificationError):
                self.verify()


class TenetRulesAndTargetTests(unittest.TestCase):
    def setUp(self):
        self.scene = {'inputTargets': [{'key': 123, 'id': 'TenetConfirmYes', 'event': 'LeftClick', 'visible': True,
                                      'disabled': False, 'clippedBounds': {'x': 10, 'y': 20, 'width': 40, 'height': 30}}]}
        self.manifest = {'hit_regions': [[123, 10, 20, 50, 50]]}

    def test_target_has_no_fabricated_payload_requirement(self):
        verifier.verify_visible_target(self.scene, self.manifest, 123, 'TenetConfirmYes')

    def test_target_rejects_zero_hidden_disabled_wrong_identity_or_bounds(self):
        for edit in (lambda x: x.update(key=0), lambda x: x.update(visible=False), lambda x: x.update(disabled=True),
                     lambda x: x.update(id='CloseButton'), lambda x: x['clippedBounds'].update(width=0),
                     lambda x: x['clippedBounds'].update(x=float('nan'))):
            self.setUp()
            edit(self.scene['inputTargets'][0])
            with self.assertRaises(verifier.VerificationError):
                verifier.verify_visible_target(self.scene, self.manifest, 123, 'TenetConfirmYes')

    def test_target_rejects_duplicate_missing_shifted_or_nan_native_hits(self):
        for hits in ([], [[123, 10, 20, 50, 50]] * 2, [[123, 11, 20, 50, 50]], [[123, float('nan'), 20, 50, 50]]):
            with self.subTest(hits=hits), self.assertRaises(verifier.VerificationError):
                verifier.verify_visible_target(self.scene, {'hit_regions': hits}, 123, 'TenetConfirmYes')

    def test_actual_rules_own_level_and_ideology_identity(self):
        self.assertEqual(verifier.verify_rule_rows(inventories()[1], BRANCH_RULES, POLICY_RULES), BRANCH_NAMES)
        for change in ('level', 'branch', 'purchase', 'missing'):
            branches, policies = list(BRANCH_RULES), list(POLICY_RULES)
            if change == 'level': policies[1] = (100, BRANCH_NAMES[FREEDOM], 2)
            if change == 'branch': policies[1] = (100, BRANCH_NAMES[0], 1)
            if change == 'purchase': branches[1] = (FREEDOM, BRANCH_NAMES[FREEDOM], 0)
            if change == 'missing': policies.pop()
            with self.subTest(change=change), self.assertRaises(verifier.VerificationError):
                verifier.verify_rule_rows(inventories()[1], branches, policies)

    def test_original_source_contract_rejects_unrelated_lua_or_xml(self):
        with tempfile.TemporaryDirectory(prefix='tenet-verifier-', dir=PROJECT / 'Tests') as directory:
            lua, xml = Path(directory) / 'SocialPolicyPopup.lua', Path(directory) / 'SocialPolicyPopup.xml'
            lua.write_text('function OnTenetConfirmYes() end', encoding='utf8')
            xml.write_text('<Context/>', encoding='utf8')
            with self.assertRaises(verifier.VerificationError):
                verifier.verify_original_sources(lua, xml)


if __name__ == '__main__':
    unittest.main()
