"""Focused proof tests for the original three-context Economic Overview assets."""
from copy import deepcopy
from pathlib import Path
import sys
import unittest
import xml.etree.ElementTree as ET

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / 'tools'))

import prepare_ui_popup_assets as freezer
from probe_world_builder import artifact


GAME = freezer.GAME
SOURCE_PATHS = {
    'EconomicOverview': 'Assets/UI/InGame/Popups/EconomicOverview.lua',
    'EconomicOverviewLayout': 'Assets/DLC/Expansion2/UI/InGame/Popups/EconomicOverview.xml',
    'EconomicGeneralInfo': 'Assets/DLC/Expansion2/UI/InGame/Popups/EconomicGeneralInfo.lua',
    'EconomicGeneralLayout': 'Assets/DLC/Expansion2/UI/InGame/Popups/EconomicGeneralInfo.xml',
    'HappinessInfo': 'Assets/DLC/Expansion2/UI/InGame/Popups/HappinessInfo.lua',
    'EconomicHappinessLayout': 'Assets/DLC/Expansion2/UI/InGame/Popups/HappinessInfo.xml',
}
LAYOUT_META = {
    'EconomicOverviewLayout': ('EconomicOverview', 'EconomicOverview'),
    'EconomicGeneralLayout': ('EconomicGeneralInfo', 'EconomicGeneral'),
    'EconomicHappinessLayout': ('HappinessInfo', 'EconomicHappiness'),
}


def build_fixture():
    trees, inputs = {}, {}
    source_bytes = {}
    for name, relative in SOURCE_PATHS.items():
        path = GAME / relative
        raw = path.read_bytes()
        source_bytes[name] = raw
        inputs[name] = {'installed': artifact(path)}
        if name not in LAYOUT_META:
            continue
        tree = freezer.control_tree(ET.fromstring(raw))
        tree['contextName'], tree['popupKind'] = LAYOUT_META[name]
        trees[name] = tree
    return trees, inputs, source_bytes


class EconomicOverviewAssetTests(unittest.TestCase):
    def test_exact_original_sources_and_three_context_tree_proof(self):
        trees, inputs, before = build_fixture()
        proof = freezer.economic_overview_proof(trees, inputs)
        self.assertEqual(proof['treeNames'], [
            'EconomicOverviewLayout', 'EconomicGeneralLayout', 'EconomicHappinessLayout'])
        self.assertTrue(proof['sourceBytesPreserved'])
        self.assertEqual(proof['xmlContexts'], [
            {'id': 'EconomicGeneralInfo',
             'fileName': 'Assets/UI/InGame/Popups/EconomicGeneralInfo', 'hidden': '0'},
            {'id': 'HappinessInfo',
             'fileName': 'Assets/UI/InGame/Popups/HappinessInfo', 'hidden': '1'},
        ])
        self.assertEqual(proof['parent']['contextName'], 'EconomicOverview')
        self.assertEqual(proof['parent']['popupKind'], 'EconomicOverview')
        self.assertEqual(proof['parent']['layoutAsset'], 'EconomicOverviewLayout')
        self.assertEqual(proof['parent']['luaAsset'], 'EconomicOverview')
        self.assertEqual(set(proof['children']), {'EconomicGeneralInfo', 'HappinessInfo'})
        self.assertEqual(proof['children']['EconomicGeneralInfo']['popupKind'], 'EconomicGeneral')
        self.assertEqual(proof['children']['HappinessInfo']['popupKind'], 'EconomicHappiness')
        self.assertEqual(proof['children']['EconomicGeneralInfo']['controlId'], 'EconomicGeneralInfo')
        self.assertEqual(proof['children']['HappinessInfo']['controlId'], 'HappinessInfo')
        self.assertTrue(proof['children']['EconomicGeneralInfo']['control_ids'])
        self.assertTrue(proof['children']['HappinessInfo']['control_ids'])
        self.assertEqual([x['name'] for x in proof['children']['EconomicGeneralInfo']['templates']],
                         ['CityInstance', 'TradeEntry'])
        self.assertEqual([x['name'] for x in proof['children']['HappinessInfo']['templates']],
                         ['ResourceEntry', 'TradeEntry'])

        expected_sources = dict(SOURCE_PATHS)
        actual_sources = {name: relative for name, relative in freezer.SCRIPTS +
                          tuple((n, p) for n, p, _ in freezer.LAYOUTS)
                          if name in expected_sources}
        self.assertEqual(actual_sources, expected_sources)
        for name, relative in SOURCE_PATHS.items():
            path = GAME / relative
            self.assertEqual(before[name], path.read_bytes())
            self.assertEqual(inputs[name]['installed'], artifact(path))

    def test_proof_rejects_missing_or_repointed_original_child_context(self):
        trees, inputs, _ = build_fixture()
        for changed in ('missing', 'wrong_file', 'wrong_visibility'):
            candidate = deepcopy(trees)
            nodes = list(freezer._walk_control_tree(candidate['EconomicOverviewLayout']))
            child = next(node for node in nodes if node['kind'] == 'LuaContext' and
                         node['attributes'].get('ID') == 'HappinessInfo')
            if changed == 'missing':
                candidate['EconomicOverviewLayout']['children'].remove(child)
            elif changed == 'wrong_file':
                child['attributes']['FileName'] = 'Assets/UI/InGame/Popups/Other'
            else:
                child['attributes']['Hidden'] = '0'
            with self.subTest(changed=changed), self.assertRaises(ValueError):
                freezer.economic_overview_proof(candidate, inputs)

    def test_template_inventory_matches_complete_original_xml_subtrees(self):
        trees, _, _ = build_fixture()
        for layout_name in ('EconomicGeneralLayout', 'EconomicHappinessLayout'):
            relative = SOURCE_PATHS[layout_name]
            root = ET.parse(GAME / relative).getroot()
            expected = {}
            for instance in root.iter('Instance'):
                nodes = list(instance.iter())
                expected[instance.get('Name')] = {
                    'control_ids': sorted(node.get('ID') for node in nodes if node.get('ID')),
                    'retained_control_count': len(nodes),
                }
            inventory = freezer.economic_overview_tree_inventory(trees[layout_name])
            actual = {row['name']: {key: row[key] for key in
                                    ('control_ids', 'retained_control_count')}
                      for row in inventory['templates']}
            self.assertEqual(actual, expected)


if __name__ == '__main__':
    unittest.main()
