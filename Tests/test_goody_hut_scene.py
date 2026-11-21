"""Run original GoodyHutPopup in the production retained Lua scene, without SDK.

Only the source-scope-pinned pure Lua 5.1 provider is loaded. Frozen font metrics
are reused in memory; no font copies, windows, game processes or game state are
created. This is component proof, not native pixels or reward/next-turn proof.
"""
from __future__ import annotations

import argparse
import copy
import ctypes
import hashlib
import importlib
import json
import os
from pathlib import Path
import re
import stat
import sys
from unittest.mock import patch
import xml.etree.ElementTree as ET

sys.dont_write_bytecode = True
PROJECT = Path(__file__).absolute().parents[1]
STAGE = PROJECT / 'evidence/goody_hut/source'
SCOPE = STAGE / 'scope.json'
SCOPE_SHA = '7c185ee5a36c38ba9a9b75521e532a16859f21e13b45a8f7554c42e184328f38'
LUA_SHA = '4873cded3ddf52366abc7964e3d3e10546f88e983d966be93bce3465ef85d944'
PATHS = {'scene': 'Source/Host/UiScene.lua', 'input': 'Source/Presentation/UiPresentationInput.lua',
         'preparer': 'tools/prepare_ui_popup_assets.py', 'cases': 'Tests/goody_hut_scene.lua',
         'pixel': 'tools/ui_pixel_scene.py',
         'test': 'Tests/test_goody_hut_scene.py',
         'enums': 'Source/SDK_BNW_x64/CvGameCoreDLLUtil/include/CvEnums.h',
         'styles': 'Source/Assets/UI/Assets/UI/Styles.xml',
         'shared_metrics': 'evidence/ui_popup/assets/prepared.json',
         'font_profile': 'tools/ui_font_profile.py'}


def require(value, message):
    if not value:
        raise RuntimeError(message)


def key(path):
    return os.path.normcase(os.path.abspath(path))


def artifact(path):
    path = Path(os.path.abspath(path))
    for ancestor in (path, *path.parents):
        row = ancestor.lstat()
        require(not stat.S_ISLNK(row.st_mode) and not getattr(row, 'st_file_attributes', 0) & 0x400,
                'Reparse component input: ' + str(ancestor))
    before = path.stat()
    identity = lambda row: (row.st_dev, row.st_ino, row.st_size, row.st_mtime_ns)
    require(stat.S_ISREG(before.st_mode), 'Expected ordinary component input')
    with path.open('rb') as stream:
        require(identity(os.fstat(stream.fileno())) == identity(before), 'Input changed while opening')
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
        require(identity(os.fstat(stream.fileno())) == identity(before), 'Input changed while hashing')
    require(identity(path.stat()) == identity(before), 'Input path changed while hashing')
    return {'path': str(path), 'bytes': before.st_size, 'sha256': digest}


def sealed(row):
    require(artifact(row['path']) == row, 'Sealed component input changed: ' + row['path'])
    return row


def execute_lua(source, provider):
    require(artifact(provider)['sha256'] == LUA_SHA, 'Pure Lua component provider changed')
    lua = ctypes.CDLL(str(provider))
    lua.luaL_newstate.argtypes, lua.luaL_newstate.restype = [], ctypes.c_void_p
    lua.luaL_openlibs.argtypes, lua.luaL_openlibs.restype = [ctypes.c_void_p], None
    lua.luaL_loadbuffer.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_size_t, ctypes.c_char_p]
    lua.luaL_loadbuffer.restype = ctypes.c_int
    lua.lua_pcall.argtypes, lua.lua_pcall.restype = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_int], ctypes.c_int
    lua.lua_tolstring.argtypes, lua.lua_tolstring.restype = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p], ctypes.c_char_p
    lua.lua_close.argtypes, lua.lua_close.restype = [ctypes.c_void_p], None
    state = lua.luaL_newstate()
    require(state, 'Cannot create isolated Lua component state')
    try:
        lua.luaL_openlibs(state)
        data = source.encode('utf-8')
        status = lua.luaL_loadbuffer(state, data, len(data), b'@GoodyHut-original-component.lua')
        if status == 0:
            status = lua.lua_pcall(state, 0, 1, 0)
        message = lua.lua_tolstring(state, -1, None)
        require(status == 0 and message, 'GoodyHut component failed: ' +
                (message.decode('utf-8', errors='replace') if message else 'no returned JSON'))
        require(len(message) < 2 * 1024 * 1024, 'Component report exceeds its bound')
        return json.loads(message.decode('utf-8'))
    finally:
        lua.lua_close(state)


def popup_types(path):
    text = path.read_text(encoding='cp1252')
    match = re.search(r'\benum\s+ButtonPopupTypes\s*\{([^}]+)\}\s*;', text, re.S)
    require(match, 'Original SDK popup enum missing')
    body = re.sub(r'/\*.*?\*/|//[^\r\n]*', '', match.group(1), flags=re.S)
    names = [part.strip() for part in body.split(',') if part.strip()]
    require(names and len(names) == len(set(names)) and
            all(re.fullmatch(r'BUTTONPOPUP_[A-Z0-9_]+|NUM_FIXED_BUTTONPOPUP_TYPES', name) for name in names),
            'Popup enum is no longer a plain sequential declaration')
    result = {name: index for index, name in enumerate(names)}
    require('BUTTONPOPUP_GOODY_HUT_REWARD' in result, 'Original SDK GoodyHut popup enum missing')
    return result


def frozen_metrics_with_integer_keys(metrics):
    """Restore JSON object keys to the integer codepoints Lua glyph lookup uses."""
    glyph_sets, count = {}, 0
    for name, original in metrics['glyphSets'].items():
        restored = {}
        for codepoint, value in original.items():
            require(isinstance(codepoint, str) and re.fullmatch(r'0|[1-9][0-9]*', codepoint) and
                    0 <= int(codepoint) <= 0x10FFFF, 'Noncanonical frozen JSON glyph codepoint')
            restored[int(codepoint)] = value
        require(len(restored) == len(original) and
                all(restored[int(codepoint)] == value for codepoint, value in original.items()),
                'Frozen glyph key restoration changed a metric value or count')
        glyph_sets[name] = restored
        count += len(restored)
    return {**metrics, 'glyphSets': glyph_sets}, count


def validate_exported_snapshots(report, renderer, originals, types):
    snapshots, packet = report['snapshots'], report['snapshot_reward_packet']
    require(set(snapshots) == {'shown', 'closed'} and
            packet['Type'] == types['BUTTONPOPUP_GOODY_HUT_REWARD'], 'Actual reward snapshot pair or packet missing')
    sources = {row['path']: row['sha256'] for row in originals.values()}

    def validate(snapshot, closed=False):
        proof = renderer.goody_hut_reward_contract(snapshot, sources, closed=closed)
        require((proof['reward_id'], proof['special_value']) == (packet['Data1'], packet['Data2']),
                'Reward snapshot differs from its captured original popup packet')
        return proof

    proofs = {name: validate(snapshot, closed=name == 'closed') for name, snapshot in snapshots.items()}
    mutations = []
    changed = copy.deepcopy(snapshots['shown'])
    changed['goodyHutReward']['rewardId'] = packet['Data1'] + 1
    mutations.append(('captured_packet_reward_id_mismatch', changed, False))
    changed = copy.deepcopy(snapshots['shown'])
    changed['goodyHutReward']['originalLayoutLua']['sha256'] = '0' * 64
    mutations.append(('wrong_original_provenance', changed, False))
    changed = copy.deepcopy(snapshots['shown']);changed['timerSemaphore'] = 0
    mutations.append(('shown_timer_released_early', changed, False))
    changed = copy.deepcopy(snapshots['shown'])

    def find_close(node):
        if node.get('id') == 'CloseButton':
            return node
        return next((found for child in node['children'] if (found := find_close(child)) is not None), None)

    close = find_close(changed['tree'])
    require(close is not None, 'Actual outside-grid CloseButton missing')
    close['y'] -= close['height']
    for hit in changed['inputTargets']:
        if hit['key'] == close['key']:
            hit['bounds']['y'] = hit['clippedBounds']['y'] = close['y']
    mutations.append(('close_and_hit_shifted_inside_parent_grid', changed, False))
    changed = copy.deepcopy(snapshots['closed'])
    changed['inputTargets'] = copy.deepcopy(snapshots['shown']['inputTargets'])
    mutations.append(('closed_stale_close_hit', changed, True))
    rejected = []
    for name, snapshot, closed in mutations:
        try:
            validate(snapshot, closed)
        except (RuntimeError, ValueError) as error:
            rejected.append({'case': name, 'rejected': True, 'reason': str(error)})
        else:
            raise RuntimeError('Production contract accepted a malformed actual snapshot: ' + name)
    return proofs, rejected


def verify_component(output=None, scope_path=None):
    selected_scope = Path(os.path.abspath(scope_path or SCOPE))
    require(selected_scope.is_relative_to(PROJECT / 'evidence/goody_hut') and selected_scope.suffix == '.json',
            'Use an explicit engine-owned GoodyHut source scope')
    stage = selected_scope.parent
    if output is not None:
        output = Path(os.path.abspath(output))
        require(output.parent == stage and not os.path.lexists(output), 'Use a fresh report in the scoped stage')
    scope_ref = artifact(selected_scope)
    if selected_scope == SCOPE:
        require(scope_ref['sha256'] == SCOPE_SHA, 'Reviewed GoodyHut source scope changed')
    scope = json.loads(selected_scope.read_text(encoding='utf-8-sig'))
    require(scope['schema'] == 'zerosis.goody_hut.source_scope.v1' and
            scope['retail_mod_test_hold_active'] is True and scope['host_gamecore_hwnd_execution_allowed'] is False and
            scope['retail_user_state_or_game_process_access_allowed'] is False and
            scope['native_acceptance_claim_allowed'] is False, 'Source scope boundary changed')
    originals = {name: sealed(row) for name, row in scope['original_static_assets'].items()}
    require(set(originals) == {'GoodyHutPopup.lua', 'GoodyHutPopup.xml'}, 'Unexpected original asset set')
    provider = Path(scope['lua_provider']['path'])
    require(sealed(scope['lua_provider'])['sha256'] == LUA_SHA and
            key(provider) == key(PROJECT / 'Build/SharedLuaRuntime/Lua/ZeroSisLua51_x64.dll'),
            'Only the reviewed pure Lua provider may be loaded')
    refs = {name: artifact(PROJECT / relative) for name, relative in PATHS.items()}
    denied, dll_loads = [], []
    retail = key(r"C:\Users\home\OneDrive\Documents\My Games\Sid Meier's Civilization 5")
    installed = key(Path(originals['GoodyHutPopup.lua']['path']).parents[6])
    original_keys = {key(row['path']) for row in originals.values()}

    def audit(event, arguments):
        if event in ('open', 'os.listdir', 'os.scandir') and arguments and isinstance(arguments[0], (str, bytes, os.PathLike)):
            target = key(os.fsdecode(arguments[0]))
            if target.startswith('\\\\?\\'):
                target = target[4:]
            if target == retail or target.startswith(retail + os.sep):
                denied.append('retail-user-state');raise RuntimeError('Retail MODS, saves and settings are forbidden')
            if (target == installed or target.startswith(installed + os.sep)) and target not in original_keys:
                denied.append('unscoped-installed-asset');raise RuntimeError('Only scoped static installed GoodyHut assets may be read')
            if event == 'open':
                mode, flags = arguments[1:3]
                writing = (isinstance(mode, str) and any(char in mode for char in 'wax+')) or (
                    type(flags) is int and flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND))
                if writing and (output is None or target != key(output)):
                    denied.append('write');raise RuntimeError('No component copies, scratch files or unrequested artifacts')
        if event in ('os.remove', 'os.rmdir', 'os.rename', 'os.mkdir', 'os.link', 'os.symlink'):
            denied.append(event);raise RuntimeError('Component filesystem mutations are forbidden')
        if event == 'ctypes.dlopen':
            require(arguments and isinstance(arguments[0], (str, bytes, os.PathLike)) and
                    key(os.fsdecode(arguments[0])) == key(provider), 'A non-component DLL load was attempted')
            dll_loads.append(str(provider))
        if event in ('subprocess.Popen', 'os.system', 'os.startfile', 'os.startfile/2', 'os.exec', 'os.spawn', 'os.posix_spawn'):
            denied.append(event);raise RuntimeError('Actual processes, game launches and process queries are forbidden')

    sys.addaudithook(audit)
    with patch.object(sys, 'path', [str(PROJECT / 'tools'), *sys.path]):
        preparation = importlib.import_module('prepare_ui_popup_assets')
        renderer = importlib.import_module('ui_pixel_scene')
        font_profile = importlib.import_module('ui_font_profile')
    require(key(preparation.__file__) == key(refs['preparer']['path']), 'Imported a different production asset preparer')
    require(key(renderer.__file__) == key(refs['pixel']['path']), 'Imported a different production scene contract')
    require(key(font_profile.__file__) == key(refs['font_profile']['path']), 'Imported a different shared-font resolver')
    original_pair = preparation.goody_hut_original_sources()
    require(original_pair == {'lua': originals['GoodyHutPopup.lua'], 'xml': originals['GoodyHutPopup.xml']},
            'Production preparer provenance differs from the sealed originals')
    copied_refs, selected = [], {}
    for name, original in originals.items():
        copied = Path(scope['new_source_assets'][name])
        if copied.exists():
            row = artifact(copied)
            require((row['bytes'], row['sha256']) == (original['bytes'], original['sha256']),
                    'Copied original GoodyHut asset differs from its provenance')
            copied_refs.append(row);selected[name] = copied
        else:
            selected[name] = Path(original['path'])
    tree = preparation.control_tree(ET.parse(selected['GoodyHutPopup.xml']).getroot())
    tree.update(contextName='GoodyHutPopup', popupKind='GoodyHutReward')
    tree['goodyHutReward'] = {'policy': 'ORIGINAL_BNW_GOODY_HUT_REWARD_INFORMATIONAL_V1',
        'originalLayoutLua': original_pair['lua'], 'originalLayoutXml': original_pair['xml'],
        'rewardAlreadyApplied': True, 'nativeAcceptanceVerified': False}
    # Keep the actual production style parser; replace only its copy destination
    # with the existing frozen source, so the component never creates scratch.
    frozen_style = PROJECT / PATHS['styles']
    def existing_style(relative, _destination):
        require(relative == preparation.STYLE_SOURCE == 'Assets/UI/Styles.xml', 'Unexpected style input')
        return frozen_style, frozen_style
    with patch.object(preparation, 'freeze_source', existing_style):
        styles = preparation.production_style_defaults(None, tree)
    require(styles['source']['sha256'] == refs['styles']['sha256'], 'Source style provenance changed')
    tree.update(styleDefaults=styles['controls'], styleDefaultsSource=styles['source'], styleDefaultsPolicy=styles['policy'])
    shared = json.loads((PROJECT / PATHS['shared_metrics']).read_text(encoding='utf-8-sig'))
    bank = shared.get('shared_font_metrics')
    transport = shared['xml_control_trees'].get('GoodyHutRewardLayout')
    shared_mode = isinstance(bank, dict) and isinstance(transport, dict) and \
        transport.get('fontMetrics', {}).get('glyphSetStorage') == 'ZEROSIS_UI_SHARED_GLYPH_SETS_V1'
    if shared_mode:
        # Keep the actual compact layout intact: only the JSON-to-Lua bank keys change type.
        require({name: transport.get(name) for name in ('kind', 'attributes', 'children')} ==
                {name: tree[name] for name in ('kind', 'attributes', 'children')},
                'Actual compact GoodyHut layout differs from its unchanged original XML')
        require((transport.get('contextName'), transport.get('popupKind')) == ('GoodyHutPopup', 'GoodyHutReward') and
                transport.get('goodyHutReward') == tree['goodyHutReward'], 'Compact original source provenance changed')
        metrics = font_profile.resolve_prepared_font_metrics(shared, transport['fontMetrics'])
        profile_path = PROJECT / 'Source/Assets/UI/font_input_profile.json'
        refs['font_input_profile'] = artifact(profile_path)
        profile = json.loads(profile_path.read_text(encoding='utf-8-sig'))
        require(bank['profileId'] == profile['profile_id'] == font_profile.profile_identity(profile),
                'Actual shared bank differs from its sealed original font input profile')
        for font_id, font in metrics['fonts'].items():
            selected_font = profile['fonts'][font_id]
            require(selected_font['ggxml']['sha256'] == font['sha256'] and
                    len(metrics['glyphSets'][font['glyphSet']]) == selected_font['glyph_count'],
                    'Selected shared glyph set lost original profile records: ' + font_id)
        selected_count = sum(len(glyphs) for glyphs in metrics['glyphSets'].values())
        restored_bank, restored_codepoints = frozen_metrics_with_integer_keys({'glyphSets': bank['glyphSets']})
        lua_bank = {**bank, 'glyphSets': restored_bank['glyphSets']}
        tree = copy.deepcopy(transport)
        require('glyphSets' not in tree['fontMetrics'] and tree['fontMetrics']['glyphSetRefs'],
                'Shared-font component must enter the production Lua resolver with compact references')
        metrics_source = 'xml_control_trees.GoodyHutRewardLayout.fontMetrics + shared_font_metrics'
    else:
        require(selected_scope == SCOPE, 'A new source scope must exercise the actual compact GoodyHut layout and bank')
        metrics = font_profile.resolve_prepared_font_metrics(shared, shared['xml_control_trees']['PantheonLayout']['fontMetrics'])
        tree['fontMetrics'] = metrics
        selected_count = restored_codepoints = sum(len(glyphs) for glyphs in metrics['glyphSets'].values())
        lua_bank = {}
        metrics_source = 'xml_control_trees.PantheonLayout.fontMetrics'
    require(metrics['policy'] == 'CIV5_GLYPHGEN_GGXML_LAYOUT_V1' and metrics['retailMetricSemanticsVerified'] is False and
            {'TwCenMT20', 'TwCenMT22', 'TwCenMT24'} <= set(metrics['fonts']), 'Required existing frozen font metrics missing')
    sources = {'scene': (PROJECT / PATHS['scene']).read_text(encoding='utf-8-sig'),
               'input': (PROJECT / PATHS['input']).read_text(encoding='utf-8-sig'),
               'stock': selected['GoodyHutPopup.lua'].read_text(encoding='utf-8-sig')}
    types = popup_types(PROJECT / PATHS['enums'])
    harness = (PROJECT / PATHS['cases']).read_text(encoding='utf-8')
    for marker, value in (('@@SOURCES@@', sources), ('@@LAYOUT@@', tree), ('@@POPUP_TYPES@@', types),
                          ('@@SHARED_FONTS@@', lua_bank), ('@@SELECTED_GLYPH_COUNT@@', selected_count)):
        harness = harness.replace(marker, preparation.lua_value(value))
    require(not re.search(r'@@[A-Z_]+@@', harness), 'Unresolved component fixture input')
    report = execute_lua(harness, provider)
    require(report['checks'] == 485 and len(report['cases']) == len(set(report['cases'])) == 32,
            'Existing 485-check/32-case GoodyHut component coverage was lost')
    require(report['shared_font_transport']['used'] is shared_mode and
            (not shared_mode or report['shared_font_transport']['selected_glyph_count'] == selected_count and
             report['shared_font_transport']['private_layout_resolved'] is True and
             report['shared_font_transport']['input_layout_and_bank_unchanged'] is True),
            'Actual compact GoodyHut layout did not traverse the production Lua shared-font resolver')
    contract_proofs, contract_mutations = validate_exported_snapshots(report, renderer, originals, types)
    require(not denied and dll_loads == [str(provider)] and report['reward_grants'] == report['sdk_commands'] == report['rng_calls'] == 0,
            'Pure Lua component boundary failed')
    for row in [scope_ref, *refs.values(), *originals.values(), *copied_refs, scope['lua_provider']]:
        sealed(row)
    report.update(schema='zerosis.goody_hut.original_popup_headless_component.v1',
        status='PASS_ORIGINAL_GOODY_HUT_POPUP_HEADLESS_COMPONENT', scope=scope_ref, source_inputs=refs,
        original_inputs=originals, copied_original_inputs=copied_refs, sources_unchanged=True,
        pure_lua_provider=scope['lua_provider'], permitted_component_dll_loads=dll_loads,
        forbidden_access_attempts=denied, frozen_metrics_source=metrics_source,
        frozen_metric_key_restoration='CANONICAL_JSON_DECIMAL_STRING_TO_LUA_INTEGER_CODEPOINT',
        frozen_metric_values_and_counts_preserved=True, restored_glyph_codepoint_count=restored_codepoints,
        production_scene_contracts=contract_proofs, production_scene_contract_mutations=contract_mutations,
        generated_layout_name='GoodyHutRewardLayout', sdk_popup_type=types['BUTTONPOPUP_GOODY_HUT_REWARD'],
        sdk_runtime_enum_binding_verified=False, actual_host_processes=0, host_executed=False,
        gamecore_loaded=False, hwnd_created=False, retail_user_state_accessed=False,
        game_process_queries=0, owned_scratch_created=False, native_acceptance=False,
        next_turn_verified=False, full_game_acceptance=False)
    if output is not None:
        with output.open('x', encoding='utf-8') as stream:
            json.dump(report, stream, ensure_ascii=False, indent=2);stream.write('\n');stream.flush();os.fsync(stream.fileno())
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--scope', type=Path, help='Explicit current engine source scope; omitted preserves the reviewed original scope')
    arguments = parser.parse_args()
    result = verify_component(arguments.output, arguments.scope)
    print(json.dumps({'status': result['status'], 'checks': result['checks'], 'cases': len(result['cases']),
                      'contract_mutations': len(result['production_scene_contract_mutations']),
                      'report': artifact(arguments.output) if arguments.output else None}, ensure_ascii=False))
