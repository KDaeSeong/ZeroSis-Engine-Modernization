from copy import deepcopy
from pathlib import Path
import sys
import unittest

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / 'tools'))
import verify_interactive_social_policy as verifier


def inventories():
    before = {'schema': 'ZEROSIS_SOCIAL_POLICY_SDK_INVENTORY_V1', 'source': 'SDK:Policies/PolicyBranches/JONSCulture',
              'activePlayer': 0, 'turn': 0, 'elapsed': 0, 'culture': 1000, 'nextCost': 25, 'freePolicies': 0, 'policySaving': False,
              'policies': [{'id': 0, 'branch': -1, 'has': False, 'canAdopt': False, 'blocked': False},
                           {'id': 7, 'branch': 0, 'has': False, 'canAdopt': False, 'blocked': False}],
              'branches': [{'id': 0, 'freePolicy': 0, 'unlocked': False, 'canUnlock': True, 'blocked': False}]}
    branch = deepcopy(before)
    branch.update(culture=975, nextCost=30)
    branch['policies'][0]['has'] = True
    branch['policies'][1]['canAdopt'] = True
    branch['branches'][0].update(unlocked=True, canUnlock=False)
    policy = deepcopy(branch)
    policy.update(culture=945, nextCost=40)
    policy['policies'][1].update(has=True, canAdopt=False)
    return before, branch, policy


def snapshot(inventory):
    meta = {'activePlayer': 0, 'currentTab': 'SocialPolicies', 'policyInfo': True,
            'branchSwitchConfirmationPresent': False, 'ideologyChangePresent': False,
            'policies': deepcopy(inventory['policies']), 'branches': deepcopy(inventory['branches'])}
    for policy in meta['policies']:
        policy['branch'] = '' if policy['branch'] == -1 else 'POLICY_BRANCH_TRADITION'
    return {'contextName': 'SocialPolicyPopup', 'popupKind': 'SocialPolicy', 'active': True,
            'hasRetainedPopupUi': True, 'timerSemaphore': 1, 'socialPolicy': meta,
            'tree': {'children': [{'id': name, 'hidden': True} for name in ('PolicyConfirm', 'TenetConfirm', 'ChangeIdeologyConfirm')] +
                     [{'id': 'PolicyInfo', 'checked': True}]}}


class InventoryVerificationTests(unittest.TestCase):
    def setUp(self):
        self.before, self.branch, self.policy = inventories()

    def test_real_paid_branch_then_policy(self):
        self.assertEqual(verifier.verify_adoption(self.before, self.branch, 0, False)['policy_added'], 0)
        self.assertEqual(verifier.verify_adoption(self.branch, self.policy, 7, True)['cost'], 30)

    def test_second_fixture_only_funds_actual_next_cost(self):
        before = deepcopy(self.branch)
        before['culture'] = 0
        after = deepcopy(before)
        after['culture'] = before['nextCost']
        verifier.verify_exact_culture_grant(before, after)
        for field, value in (('culture', before['nextCost'] + 1), ('policySaving', True), ('turn', 1)):
            changed = deepcopy(after)
            changed[field] = value
            with self.subTest(field=field), self.assertRaises(verifier.VerificationError):
                verifier.verify_exact_culture_grant(before, changed)
        after['policies'][1]['has'] = True
        with self.assertRaises(verifier.VerificationError):
            verifier.verify_exact_culture_grant(before, after)

    def test_wrong_cost_free_grant_owner_turn_or_inventory_are_rejected(self):
        for field, value in (('culture', 976), ('freePolicies', 1), ('activePlayer', 1), ('turn', 1), ('elapsed', 1)):
            with self.subTest(field=field):
                altered = deepcopy(self.branch)
                altered[field] = value
                with self.assertRaises(verifier.VerificationError):
                    verifier.verify_adoption(self.before, altered, 0, False)

    def test_no_sdk_mutation_cannot_pass_a_ui_confirmation(self):
        with self.assertRaises(verifier.VerificationError):
            verifier.verify_adoption(self.before, self.before, 0, False)

    def test_wrong_policy_and_policy_removal_rejected(self):
        for field, value in (('has', False), ('blocked', True), ('branch', 2)):
            altered = deepcopy(self.policy)
            altered['policies'][1][field] = value
            with self.subTest(field=field), self.assertRaises(verifier.VerificationError):
                verifier.verify_adoption(self.branch, altered, 7, True)
        altered = deepcopy(self.policy)
        altered['policies'][0]['has'] = False
        with self.assertRaises(verifier.VerificationError):
            verifier.verify_adoption(self.branch, altered, 7, True)

    def test_unavailable_or_blocked_source_policy_rejected(self):
        for field, value in (('canAdopt', False), ('blocked', True), ('has', True)):
            altered = deepcopy(self.branch)
            altered['policies'][1][field] = value
            with self.subTest(field=field), self.assertRaises(verifier.VerificationError):
                verifier.verify_adoption(altered, self.policy, 7, True)

    def test_branch_must_receive_its_exact_free_opener(self):
        altered = deepcopy(self.before)
        altered['branches'][0]['freePolicy'] = 7
        with self.assertRaises(verifier.VerificationError):
            verifier.verify_adoption(altered, self.branch, 0, False)

    def test_duplicate_boolean_integer_missing_or_extra_rows_rejected(self):
        alterations = []
        a = deepcopy(self.before); a['policies'].append(deepcopy(a['policies'][0])); alterations.append(a)
        a = deepcopy(self.before); a['culture'] = True; alterations.append(a)
        a = deepcopy(self.before); a['policies'][0]['has'] = 1; alterations.append(a)
        a = deepcopy(self.before); a['policies'] = []; alterations.append(a)
        a = deepcopy(self.before); a['branches'][0]['freePolicy'] = -2; alterations.append(a)
        for altered in alterations:
            with self.subTest(altered=altered), self.assertRaises(verifier.VerificationError):
                verifier.validate_inventory(altered)


class SnapshotVerificationTests(unittest.TestCase):
    def setUp(self):
        self.inventory = inventories()[1]
        self.value = snapshot(self.inventory)

    def verify(self):
        verifier.verify_snapshot(self.value, self.inventory, 'SocialPolicies', True, False, {0: 'POLICY_BRANCH_TRADITION'})

    def test_snapshot_agrees_with_independent_sdk_inventory(self):
        self.verify()

    def test_snapshot_cannot_invent_policies_or_adoptability(self):
        self.value['socialPolicy']['policies'][1]['has'] = True
        with self.assertRaises(verifier.VerificationError):
            self.verify()
        self.setUp()
        self.value['socialPolicy']['policies'].append(deepcopy(self.value['socialPolicy']['policies'][0]))
        with self.assertRaises(verifier.VerificationError):
            self.verify()

    def test_original_branch_string_maps_to_actual_sdk_id(self):
        self.value['socialPolicy']['policies'][1]['branch'] = 'POLICY_BRANCH_LIBERTY'
        with self.assertRaisesRegex(verifier.VerificationError, 'rules-to-SDK'):
            self.verify()

    def test_confirmation_checkbox_and_tab_cannot_be_assumed(self):
        for control, field, value in (('PolicyConfirm', 'hidden', False), ('PolicyInfo', 'checked', False)):
            self.setUp()
            verifier.nodes(self.value['tree'], control)[0][field] = value
            with self.subTest(control=control), self.assertRaises(verifier.VerificationError):
                self.verify()
        self.setUp()
        self.value['socialPolicy']['currentTab'] = 'Ideologies'
        with self.assertRaises(verifier.VerificationError):
            self.verify()

    def test_unimplemented_nested_routes_are_explicitly_not_covered(self):
        self.value['socialPolicy']['branchSwitchConfirmationPresent'] = True
        with self.assertRaises(verifier.VerificationError):
            self.verify()


class NativeTargetTests(unittest.TestCase):
    def setUp(self):
        self.scene = {'inputTargets': [{'key': 123, 'id': 'BranchButton0', 'void1': 0,
                      'event': 'LeftClick', 'visible': True, 'disabled': False,
                      'clippedBounds': {'x': 10, 'y': 20, 'width': 40, 'height': 30}}]}
        self.manifest = {'hit_regions': [[123, 10, 20, 50, 50]]}

    def verify(self, key=123):
        verifier.verify_visible_target(self.scene, self.manifest, key, 'BranchButton0', 0)

    def test_branch_zero_keeps_its_positive_actual_button_key(self):
        self.verify()

    def test_zero_key_never_means_an_arbitrary_coordinate_click(self):
        self.scene['inputTargets'][0]['key'] = 0
        self.manifest['hit_regions'][0][0] = 0
        with self.assertRaises(verifier.VerificationError):
            self.verify(0)

    def test_wrong_original_button_payload_hidden_or_disabled_rejected(self):
        for field, value in (('id', 'CloseButton'), ('void1', 1), ('void1', False), ('visible', False), ('disabled', True)):
            self.setUp()
            self.scene['inputTargets'][0][field] = value
            with self.subTest(field=field, value=value), self.assertRaises(verifier.VerificationError):
                self.verify()

    def test_native_hit_geometry_must_be_exact_visible_callback_geometry(self):
        for change in ('missing', 'duplicate', 'wrong-bounds'):
            self.setUp()
            if change == 'missing': self.manifest['hit_regions'] = []
            elif change == 'duplicate': self.manifest['hit_regions'] *= 2
            else: self.manifest['hit_regions'][0][1] += 5
            with self.subTest(change=change), self.assertRaises(verifier.VerificationError):
                self.verify()


if __name__ == '__main__':
    unittest.main()
