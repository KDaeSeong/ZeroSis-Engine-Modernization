"""Read-only attestation of a current owned-save-delete Host PE.

No image is mapped, imported as native code, or executed. Current source and
the approved source-stage receipt supply the expected bytes; no historical
UiScene digest or fixed catalog-entry count is an acceptance condition.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import stat
import sys
import xml.etree.ElementTree as ET

PROJECT = Path(__file__).absolute().parents[3]
STAGE = Path(__file__).absolute().parent
sys.path.insert(0, str(PROJECT / 'Tests'))

# These helpers only parse bytes and constant data. In particular, do not call
# the legacy verify_build(), whose agreed source freeze is historical.
import verify_load_menu_linked_candidate as base

require = base.require
digest = base.digest
norm = base.norm
Inputs = base.Inputs
PE = base.PE
GAME = base.GAME
TUS = base.TUS

CORE_LAYOUTS = {
    'GameMenuLayout': ('Assets/DLC/Expansion2/UI/InGame/Menus/GameMenu.xml', 'GameMenu', 'gameMenu'),
    'SaveMenuLayout': ('Assets/UI/InGame/Menus/SaveMenu.xml', 'SaveMenu', 'saveMenu'),
    'LoadMenuLayout': ('Assets/UI/FrontEnd/LoadMenu.xml', 'LoadMenu', 'loadMenu'),
}
REQUIRED_FEATURE_SOURCES = (
    'Source/Host/NativeSaveCatalog.h', 'Source/Host/UiSaveMenuContract.h',
    'Source/Host/UiLoadMenuContract.h', 'Source/Host/InteractiveGameSession.h',
    'Source/Host/UiPopupContext.h', 'Source/Host/UiScene.lua',
    'tools/prepare_ui_popup_assets.py', 'tools/ui_pixel_scene.py',
)
ADDENDA = (
    ('host_ui_runtime', 'Host/UiScene.lua', b'', False),
    ('host_ui_input_addendum', 'Presentation/UiPresentationInput.lua', b'\n', False),
    ('host_ui_city_view_addendum', 'Presentation/UiCityView.lua', b'\nif hasRetainedCityUi then\n', True),
    ('host_ui_unit_panel_addendum', 'Presentation/UiUnitPanel.lua', b'\nif hasRetainedUnitUi then\n', True),
    ('host_ui_social_policy_addendum', 'Presentation/UiSocialPolicy.lua', b'\nif hasRetainedSocialPolicyUi then\n', True),
    ('host_ui_economic_overview_addendum', 'Presentation/UiEconomicOverview.lua', b'\nif hasRetainedEconomicUi then\n', True),
    ('host_ui_action_info_addendum', 'Presentation/UiActionInfoPanel.lua', b'\nif hasRetainedActionInfoUi then\n', True),
    ('host_ui_notification_addendum', 'Presentation/UiNotificationPanel.lua', b'\nif hasRetainedNotificationUi then\n', True),
)


def artifact(path, inputs):
    key = str(Path(os.path.abspath(path)))
    require(key in inputs.seals, 'Artifact has not been read and sealed: ' + key)
    return {'path': key, **inputs.seals[key]}


def read_feature_scope(inputs):
    scope_path = STAGE / 'scope.json'
    scope = inputs.document(scope_path)
    require(scope['schema'] == 'zerosis.owned_save_delete_linked_scope.v1' and
            scope['retail_mod_test_hold_active'] is True and
            scope['default_promoted'] is False and scope['host_gamecore_hwnd_executed'] is False,
            'Current linked candidate does not preserve its private scope')
    for row in scope['protected_artifacts'].values():
        inputs.ref(row)
    inputs.ref(scope['header_recovery'])
    source = json.loads(inputs.ref(scope['prior_source_conformance']).decode('utf-8-sig'))
    require(source['status'] == 'PASS_SOURCE_NATIVE_FIXTURE_LUA_AND_FROZEN_CPU_FRONTEND_ONLY',
            'Approved owned-delete source stage is missing')
    approved = {}
    for row in source['changed_sources']:
        current = row['current']
        key = norm(current['path'])
        require(key not in approved, 'Duplicate approved feature source')
        approved[key] = current
    pinned = {}
    for relative in REQUIRED_FEATURE_SOURCES:
        path = PROJECT / relative
        require(norm(path) in approved, 'Source stage did not approve the feature input: ' + relative)
        inputs.ref(approved[norm(path)], path)
        pinned[relative] = approved[norm(path)]
    return scope_path, scope, pinned


def verify_compilation(inputs, report, frozen_root, build_id):
    sources = {}
    for row in report['sources']:
        path = Path(os.path.abspath(row['path']))
        original = Path(os.path.abspath(row['original_source']))
        require(path.is_relative_to(frozen_root) and original.is_relative_to(PROJECT),
                'Owned source escaped the selected frozen build or project')
        require(path.name not in sources, 'Duplicate frozen source basename')
        require(inputs.ref(row) == inputs.read(original),
                'Frozen owned source differs from current source: ' + path.name)
        sources[path.name] = row

    by_original = {}
    for row in report['compiler_inputs']:
        path = Path(os.path.abspath(row['path']))
        require(path.is_relative_to(frozen_root), 'Compiler input escaped the selected frozen build')
        original = inputs.read(row['original_path'])
        require(digest(original) == row['sha256'] and original == inputs.ref(row),
                'Compiler dependency differs from its current input')
        key = norm(row['original_path'])
        require(key not in by_original, 'Duplicate compiler dependency original path')
        by_original[key] = norm(path)

    discoveries, finals = {}, {}
    for output, key in ((discoveries, 'dependency_discovery'), (finals, 'final_compilation')):
        for row in report[key]['translation_units']:
            name = row['translation_unit']
            require(name not in output, 'Duplicate translation unit')
            output[name] = row
    require(set(discoveries) == set(finals) == TUS, 'Compiled translation-unit coverage differs')
    final_sets = {}
    for name in sorted(TUS):
        sets = []
        for row in (discoveries[name], finals[name]):
            require(row['returncode'] == 0, 'Compilation did not succeed')
            log = inputs.ref(row['log']).decode('utf-8', errors='replace')
            require(not re.search(r'\bwarning\s+[A-Z]+\d+', log, re.I), 'Compiler warning remains')
            document = json.loads(inputs.ref(row['dependency_report']).decode('utf-8-sig'))
            data = document.get('Data', document)
            sets.append({norm(path) for path in (data['Source'], *data['Includes'])})
        require(sets[0] <= set(by_original), 'Discovery dependency was not frozen')
        require({by_original[path] for path in sets[0]} == sets[1],
                'Final compiler did not consume the exact frozen dependency closure')
        final_sets[name] = sets[1]

    required = ('UiPopupContext.h', 'UiSaveMenuContract.h', 'UiLoadMenuContract.h',
                'UiPopupAssets.generated.h', 'NativeSaveCatalog.h', 'InteractiveGameSession.h',
                'InteractiveUiSession.h', 'SdkGameRestore.h', 'InteractiveGameLoop.h')
    require(set(name.casefold() for name in required) <=
            {Path(path).name.casefold() for path in final_sets['host_main']},
            'Final Host compilation omitted the owned-delete/save/load contract')
    for relative in (value for value in REQUIRED_FEATURE_SOURCES if value.endswith('.h')):
        require(by_original[norm(PROJECT / relative)] in final_sets['host_main'],
                'Final Host did not consume the exact current feature dependency: ' + relative)

    generated_path = PROJECT / 'Source/Host/UiPopupAssets.generated.h'
    generated = inputs.ref(sources[generated_path.name])
    require(generated == inputs.read(generated_path) and
            by_original[norm(generated_path)] in final_sets['host_main'],
            'Final compiler omitted the exact current generated UI header')

    link_log = inputs.ref(report['link_log']).decode('utf-8', errors='replace')
    require(not re.search(r'\bwarning\s+LNK\d+', link_log, re.I), 'Linker warning remains')
    response = inputs.ref(report['link_response']).decode('utf-8-sig').splitlines()
    actual_objects = {norm(line.strip('"')) for line in response if line.casefold().endswith('.obj"')}
    names = (('host_main', 'HostMain'), ('window', 'BitmapWindow'), ('renderer', 'BitmapRenderer'),
             ('world_renderer', 'WorldViewRenderer'), ('terrain_renderer', 'WorldTerrainRenderer'))
    expected_objects = {norm(PROJECT / 'Build/UiWindowHost' / build_id / 'final' /
                             ('tu_%02d_%s' % (index, name)) / 'obj' / (stem + '.obj'))
                        for index, (name, stem) in enumerate(names)}
    executable = PROJECT / 'Build/UiWindowHost' / build_id / 'final/ZeroSisHost_x64.exe'
    require(actual_objects == expected_objects and
            {'/INCREMENTAL:NO', '/MACHINE:X64', '/Brepro', '/WX', '/OPT:REF', '/OPT:ICF'} <= set(response) and
            f'/OUT:"{executable}"' in response,
            'Link response did not use this candidate\'s exact five final objects')
    inputs.ref(report['map'])
    return sources, generated, final_sets


def assemble_scene(inputs, sources, prepared):
    assembled = b''
    segments, omitted = [], []
    for field, relative, glue, conditional in ADDENDA:
        path = PROJECT / 'Source' / relative
        source = inputs.read(path)
        row = sources[path.name]
        require(norm(row['original_source']) == norm(path) and inputs.ref(row) == source,
                'Scene or addendum lineage differs: ' + relative)
        if field in prepared:
            require(inputs.ref(prepared[field], path) == source, 'Prepared Scene/addendum provenance differs')
        else:
            # The production preparer appends this module but currently omits
            # its report field; frozen source and complete embedded bytes still
            # remain mandatory. No other absent field is accepted.
            require(field == 'host_ui_notification_addendum', 'Required prepared source field is absent: ' + field)
            omitted.append(field)
        assembled += glue
        segments.append({'source': str(path), 'offset': len(assembled), 'bytes': len(source),
                         'sha256': digest(source)})
        assembled += source
        if conditional:
            assembled += b'\nend\n'
    return assembled, segments, omitted


def restore_glyph_keys(tree):
    for name, glyphs in tree.get('fontMetrics', {}).get('glyphSets', {}).items():
        require(all(re.fullmatch(r'0|[1-9][0-9]*', key) and 0 <= int(key) <= 0x10FFFF
                    for key in glyphs), 'Prepared glyph-set codepoint key is invalid')
        tree['fontMetrics']['glyphSets'][name] = {int(key): value for key, value in glyphs.items()}


def prepare_payloads(inputs, sources, prepared):
    scene, segments, omitted = assemble_scene(inputs, sources, prepared)
    payloads = {'ZeroSisUiScene': scene}
    original_rows, original_bytes = {}, {}
    hidden = []
    for row in prepared['inputs']:
        name = row['name']
        require(name not in original_rows, 'Duplicate original UI input name')
        path = Path(os.path.abspath(row['installed']['path']))
        require(path.is_relative_to(GAME / 'Assets') and path.suffix.casefold() in ('.lua', '.xml'),
                'Original UI input escaped static Lua/XML assets')
        raw = inputs.ref(row['installed'])
        require(inputs.ref(row['snapshot']) == raw, 'Original UI snapshot differs: ' + name)
        original_rows[name], original_bytes[name] = row, raw
        if 'runtime_support' in row:
            hidden.append(name)
        elif path.suffix.casefold() == '.lua':
            payloads[name] = raw

    trees = deepcopy(prepared['xml_control_trees'])
    core = {}
    for name, tree in trees.items():
        require(name in original_rows and name not in hidden, 'Prepared layout is not an original catalog input')
        restore_glyph_keys(tree)
        for font in tree.get('fontMetrics', {}).get('fonts', {}).values():
            require(digest(inputs.read(GAME / font['ggxmlPath'])) == font['sha256'],
                    'Prepared font source differs from installed static GGXML')
        if name in CORE_LAYOUTS:
            relative, context, field = CORE_LAYOUTS[name]
            require(norm(original_rows[name]['installed']['path']) == norm(GAME / relative),
                    'Core layout uses a different original file: ' + name)
            require(base.strip_tree(tree) == base.xml_tree(ET.fromstring(original_bytes[name])) and
                    (tree['contextName'], tree['popupKind']) == (context, context),
                    'Core layout rewrote original XML nodes, attributes, or child order: ' + name)
            metadata_key = {'gameMenu': 'game_menu', 'saveMenu': 'save_menu', 'loadMenu': 'load_menu'}[field]
            metadata = prepared[metadata_key]
            require(all(metadata[key] == value for key, value in tree[field].items()),
                    'Prepared core-menu metadata differs from its serialized tree')
            for key, row in tree[field].items():
                if key.startswith('original') and isinstance(row, dict) and 'path' in row:
                    inputs.ref(row)
            style = tree['styleDefaultsSource']
            require(style['path'] == 'Assets/UI/Styles.xml',
                    'Core style reference differs from its game-relative schema')
            require(digest(inputs.read(GAME / style['path'])) == style['sha256'],
                    'Core style reference differs from installed original Styles.xml')
            core[name] = {'original_xml': original_rows[name]['installed'],
                          'node_count': sum(1 for _ in base.walk(tree)),
                          'original_tree_equal': True}
        payloads[name] = ('ZeroSisUiLayout=' + base.lua_value(tree) + '\n').encode('ascii')

    require(set(CORE_LAYOUTS) <= set(core), 'A required core menu layout is missing')
    for metadata_key in ('save_menu', 'load_menu'):
        metadata = prepared[metadata_key]
        require(metadata['deletePolicy'] == 'ORIGINAL_CONFIRMATION_RETAINED; OPTIONAL_OWNED_CATALOG_CAPABILITY; NO_RUNTIME_PROOF' and
                metadata['deleteRuntimeVerified'] is False, 'Prepared menu does not describe the current optional owned-delete capability')
        key = 'requiredDeleteNativeApis' if metadata_key == 'save_menu' else 'requiredNativeApis'
        require('UI.DeleteSavedGame' in metadata[key], 'Prepared menu omitted the owned-delete API dependency')
    checkbox = base.checkbox_contract(inputs, trees['LoadMenuLayout'], prepared['load_menu'])
    for name, field in (('ProductionCommandGuard', 'production_command_guard'),
                        ('ResearchCommandGuard', 'research_command_guard')):
        path = PROJECT / 'Source/Host' / (name + '.lua')
        raw = inputs.read(path)
        require(inputs.ref(sources[path.name]) == raw and inputs.ref(prepared[field], path) == raw,
                'Command guard differs from current/frozen/prepared source')
        payloads[name] = raw
    expected_original = set(original_rows) - set(hidden)
    require(expected_original <= set(payloads), 'An original catalog input has no exact expected payload')
    return payloads, segments, omitted, core, checkbox, hidden


def image_metadata(data, pe):
    offset = pe.number(0x3C, '<I')
    flags = pe.number(offset + 22, '<H')
    require(flags & 0x20, 'Actual PE is not large-address-aware')
    return {'architecture': 'x64', 'is_dll': False, 'large_address_aware': True,
            'machine_hex': '0x8664', 'pe_format': 'PE32+', 'section_count': len(pe.sections)}


def exact_catalog(pe, names, lengths, payloads):
    # EmptyPopup is intentionally a zero-byte stock script. Never seed the
    # address search with NUL or build a candidate list for every image NUL.
    # The complete nonempty current scene uniquely locates one shared table;
    # the legacy parser already validates every row/name/length/RO mapping.
    scene = payloads['ZeroSisUiScene']
    require(scene, 'The UI scene cannot be an empty table-location anchor')
    table = pe.catalog(names, lengths, {'ZeroSisUiScene': scene})
    table_at, _ = pe.mapped(table['table_rva'], len(names) * 24, readonly=True)
    proof = {}
    for index, name in enumerate(names):
        row_at = table_at + index * 24
        name_rva = pe.number(row_at, '<Q') - pe.base
        payload_rva = pe.number(row_at + 8, '<Q') - pe.base
        size = pe.number(row_at + 16, '<Q')
        payload_at, section = pe.mapped(payload_rva, size + 1, readonly=True)
        expected = payloads[name]
        require(size == len(expected) and pe.data[payload_at:payload_at + size] == expected and
                pe.data[payload_at + size] == 0,
                'Actual registered payload differs from exact current input: ' + name)
        proof[name] = {'registry_index': index, 'row_rva': table['table_rva'] + index * 24,
                       'name_rva': name_rva, 'payload_rva': payload_rva, 'file_offset': payload_at,
                       'bytes': size, 'sha256': digest(expected), 'section': section['name']}
    table['exact_payloads'] = proof
    table['location_anchor'] = 'ZeroSisUiScene; NONEMPTY_COMPLETE_CURRENT_BYTES'
    table['zero_length_payload_policy'] = 'DIRECT_REGISTERED_SIZE_ZERO_AND_NUL_CHECK; NO_NUL_SEARCH'
    return table


def verify_historical_negative(inputs, scope, current_scene):
    report = json.loads(inputs.ref(scope['donor_build']).decode('utf-8-sig'))
    sources = {Path(row['path']).name: row for row in report['sources']}
    header = inputs.ref(sources['UiPopupAssets.generated.h'])
    lengths, decoded, names = base.generated_catalog(header, {'ZeroSisUiScene'})
    old_scene = decoded['ZeroSisUiScene']
    old_raw = inputs.ref(sources['UiScene.lua'])
    current_raw = inputs.read(PROJECT / 'Source/Host/UiScene.lua')
    require(old_raw != current_raw and old_scene != current_scene,
            'Historical donor is not a valid different-scene negative control')
    image = inputs.ref(report['executable'])
    pe = PE(image)
    actual = pe.catalog(names, lengths, {'ZeroSisUiScene': old_scene})
    image_metadata(image, pe)
    return {'build_id': report['build_id'], 'executable': report['executable'],
            'actual_historical_catalog_checked': True, 'catalog_entry_count': len(names),
            'table_rva': actual['table_rva'], 'embedded_scene_sha256': digest(old_scene),
            'current_embedded_scene_sha256': digest(current_scene),
            'historical_scene_source_sha256': digest(old_raw),
            'current_scene_source_sha256': digest(current_raw),
            'rejected_as_current_owned_delete': True,
            'rejection': 'Actual historical scene payload and approved current UiScene source bytes differ'}


def verify(build_id):
    require(re.fullmatch(r'\d{8}T\d{6}Z_[0-9a-f]{12}', build_id), 'Invalid immutable build ID')
    inputs = Inputs()
    inputs.read(Path(__file__))
    inputs.read(Path(base.__file__))
    scope_path, scope, approved = read_feature_scope(inputs)
    report_path = PROJECT / 'evidence/ui_window_host' / build_id / 'build_result.json'
    report = inputs.document(report_path)
    require(report['build_id'] == build_id and report['status'] == 'UI_WINDOW_HOST_CANDIDATE_BUILT',
            'Candidate compilation/linking has not completed')
    require(report['source_inputs_unchanged'] is True and report['provider_inputs_unchanged'] is True and
            all(report[key] is False for key in
                ('gamecore_loaded', 'sdk_linked', 'stage_updated', 'mods_updated', 'host_runtime_executed')),
            'Build did not preserve its private compile/link scope')
    require(report['source_hashes_before'] == report['source_hashes_after'], 'Build source accounting differs')
    frozen_root = PROJECT / 'Build/UiWindowHost' / build_id / 'frozen'
    for role, relative in (('builder', 'tools/build_ui_window_host.py'),
                           ('popup_asset_preparer', 'tools/prepare_ui_popup_assets.py'),
                           ('ui_asset_codec', 'tools/civ5_ui_assets.py')):
        raw = inputs.read(PROJECT / relative)
        require(digest(raw) == report['source_hashes_before'][role] and
                inputs.read(frozen_root / 'project' / relative) == raw,
                'Current builder/preparer/codec differs from the build: ' + role)
    sources, generated, final_sets = verify_compilation(inputs, report, frozen_root, build_id)
    prepared = json.loads(inputs.ref(report['ui_assets']).decode('utf-8-sig'))
    require(prepared['status'] == 'INSTALLED_UI_POPUP_ASSETS_PREPARED_NOT_RUNTIME_VERIFIED',
            'UI preparation did not complete')
    require(inputs.ref(prepared['compiled_assets'], PROJECT / 'Source/Host/UiPopupAssets.generated.h') == generated,
            'Prepared generated-header binding differs')
    inputs.ref(prepared['builder'], PROJECT / 'tools/prepare_ui_popup_assets.py')
    payloads, segments, omitted, core, checkbox, hidden = prepare_payloads(inputs, sources, prepared)
    lengths, decoded, names = base.generated_catalog(generated, payloads)
    require(set(names) == set(payloads) and all(decoded[name] == value for name, value in payloads.items()),
            'Generated registry payload coverage or exact bytes differ from current inputs')
    image = inputs.ref(report['executable'], PROJECT / 'Build/UiWindowHost' / build_id / 'final/ZeroSisHost_x64.exe')
    pe = PE(image)
    actual_pe = image_metadata(image, pe)
    require(actual_pe == report['executable']['pe'], 'Reported PE metadata differs from actual bytes')
    imports = pe.imports()
    require(set(imports) == {name.casefold() for name in report['imports']['dependencies']} and
            {'imm32.dll', 'zerosislua51_x64.dll'} <= set(imports) and
            not any('gamecore' in name or 'civilization' in name for name in imports),
            'Actual PE import table differs or imports retail/Core code')
    catalog = exact_catalog(pe, names, lengths, payloads)
    scene_location = catalog['exact_payloads']['ZeroSisUiScene']
    for segment in segments:
        segment['pe_file_offset'] = scene_location['file_offset'] + segment['offset']
        segment['pe_rva'] = scene_location['payload_rva'] + segment['offset']
    historical = verify_historical_negative(inputs, scope, payloads['ZeroSisUiScene'])
    require(historical['build_id'] != build_id, 'Current candidate is the historical donor')
    seals = inputs.finish()
    return {'build_id': build_id, 'build_report': artifact(report_path, inputs),
            'candidate_scope': artifact(scope_path, inputs), 'approved_feature_sources': approved,
            'executable': {**report['executable'], 'pe': actual_pe},
            'prepared_ui': report['ui_assets'], 'generated_header': sources['UiPopupAssets.generated.h'],
            'inputs_unchanged': True, 'read_input_count': len(seals),
            'read_input_seals_sha256': digest(json.dumps(seals, sort_keys=True).encode('utf-8')),
            'translation_units': sorted(TUS), 'exact_final_dependency_closure': True,
            'final_host_dependency_count': len(final_sets['host_main']),
            'actual_pe_imports': imports, 'pe_catalog': catalog, 'scene_source_segments': segments,
            'core_original_layouts': core, 'checkbox_candidate': checkbox,
            'original_hidden_context_assets_not_registered': sorted(hidden),
            'prepared_report_omits_reference_fields': omitted,
            'historical_negative_control': historical,
            'byte_policy': 'RAW_UTF8_BOM_AND_NEWLINES_PRESERVED; EXPLICIT_LF_SCENE_GLUE; XML_ET_ATTRIBUTES_AND_LUA_CONSTANT_SERIALIZATION',
            'catalog_count_policy': 'DERIVED_FROM_CURRENT_GENERATED_REGISTRY_AND_EXPECTED_PAYLOAD_NAMES; NO_FIXED_ENTRY_COUNT',
            'native_binding_execution_verified': False, 'native_delete_verified': False,
            'retail_ui_verified': False, 'retail_save_mod_compatibility_verified': False,
            'acceptance': 'PRIVATE_COMPILE_LINK_AND_EXACT_READ_ONLY_PE_UI_CATALOG_PAYLOAD_ONLY'}


def write_new(filename, document):
    for path in [*STAGE.parents, STAGE]:
        metadata = path.lstat()
        require(not stat.S_ISLNK(metadata.st_mode) and
                not getattr(metadata, 'st_file_attributes', 0) & getattr(stat, 'FILE_ATTRIBUTE_REPARSE_POINT', 0x400),
                'Evidence directory encountered a reparse point')
    path = STAGE / filename
    require(path.parent == STAGE and not path.exists(), 'Refusing to replace an existing attestation')
    with path.open('x', encoding='utf8') as stream:
        json.dump(document, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
    return path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build-id', required=True)
    args = parser.parse_args()
    require(re.fullmatch(r'\d{8}T\d{6}Z_[0-9a-f]{12}', args.build_id), 'Invalid immutable build ID')
    require(not (STAGE / ('attestation_' + args.build_id + '.json')).exists(),
            'A successful attestation already exists for this build')
    boundaries = {'host_executed': False, 'gamecore_loaded': False, 'dll_loaded': False,
                  'hwnd_created': False, 'mods_or_user_saves_accessed': False,
                  'retail_user_settings_accessed': False, 'game_process_queries': 0,
                  'default_promoted': False, 'binary_modified': False}
    try:
        result = verify(args.build_id)
    except Exception as error:
        failure = {'schema': 'zerosis.owned_save_delete_linked_pe_attestation.v1', 'status': 'FAIL',
                   'build_id': args.build_id, 'utc': datetime.now(timezone.utc).isoformat(),
                   'error_type': type(error).__name__, 'error': str(error),
                   'verifier_sha256': digest(Path(__file__).read_bytes()), **boundaries}
        output = write_new('failure_' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ') + '.json', failure)
        print(json.dumps({'status': 'FAIL', 'report': str(output), 'error': str(error)}))
        raise
    result.update(schema='zerosis.owned_save_delete_linked_pe_attestation.v1', status='PASS',
                  utc=datetime.now(timezone.utc).isoformat(),
                  verifier_sha256=digest(Path(__file__).read_bytes()), **boundaries)
    output = write_new('attestation_' + args.build_id + '.json', result)
    print(json.dumps({'status': 'PASS', 'build_id': args.build_id, 'report': str(output),
                      'sha256': digest(output.read_bytes()),
                      'payloads': len(result['pe_catalog']['exact_payloads']),
                      'host_executed': False, 'native_delete_verified': False}))


if __name__ == '__main__':
    main()
