"""Prepare a bounded current-SDK runtime source overlay, without native tools.

Only thirteen source/header files and one plan are created. Historical recipes
are replayed in RAM as provenance witnesses, never used as the new SDK base.
"""
from __future__ import annotations

import ast
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sys

sys.dont_write_bytecode = True

PROJECT = Path(__file__).resolve().parents[1]
SDK_ROOT = PROJECT / 'Source/SDK_BNW_x64'
SDK = SDK_ROOT / 'CvGameCoreDLL_Expansion2'
ORIGINAL = PROJECT / 'Source/SDK_BNW_Original'
ROOT = PROJECT / 'Build/SDKIncremental/x64/runtime_candidate'
OVERLAY = ROOT / 'source/CvGameCoreDLL_Expansion2'
STAGE = PROJECT / 'evidence/sdk_runtime_current'
PLAN = STAGE / 'overlay_plan.json'
BASE = PROJECT / 'evidence/sdk_current/base_link_result.json'
RECIPE = PROJECT / 'Source/Porting/sdk_x64_patches.json'
MANIFEST = PROJECT / 'evidence/sdk_x64/port_manifest.json'
PREFLIGHT = PROJECT / 'evidence/sdk_incremental/runtime_candidate_preflight.json'
SAVE_SPEC = PROJECT / 'Source/Porting/save_restore_patches.json'
SAVE_REPORT = PROJECT / 'evidence/save_restore_sdk/build_result.json'
NEW_REPORT = PROJECT / 'evidence/new_game_sdk/build_result.json'
EXPLORE_REPORT = PROJECT / 'evidence/explore_sdk/20260930T130230Z_1d2ea0512c6b/build_result.json'
CITY_REPORT = PROJECT / 'evidence/city_site_sdk/20261001T135932Z_86b1d2704654/build_result.json'
FOUND_REPORT = PROJECT / 'evidence/found_value_shared_sdk/build_result.json'
LUA_REPORT = PROJECT / 'evidence/shared_lua_runtime/build_result.json'
SAVE_IDS = (
    'restore_espionage_ai_static_vectors_before_read',
    'initialize_military_player_arrays_with_player_bound',
    'initialize_culture_public_opinion_before_first_save',
    'initialize_optional_trait_combat_improvement',
    'initialize_operation_reinforcement_flag_in_reset',
)
NAMES = ('CvGame', 'CvMapGenerator', 'CvEspionageClasses', 'CvMilitaryAI', 'CvCultureClasses',
         'CvTraitClasses', 'CvAIOperation', 'CvEconomicAI', 'CvCitySpecializationAI', 'CvPlayerAI',
         'CvSiteEvaluationClasses')
BRIDGES = ('ExploreScoreBridge', 'CitySiteScoreBridge', 'CitySiteCpuTrace', 'FoundValueSharedBridge')
PINS = {
    BASE: '5f36ecab69c7b19da42f66d8327c5ddba68b539966ff2c8d5115521a102ef255',
    RECIPE: '871eafa0b4ad8b5a33211b927366349c0ad4b1296561a6893017faf8a16d62e1',
    MANIFEST: 'e1e69ac8c657ebf6a9de16f28182cb54c8f6735c2a3d03243a50d8c4f7b5d6ea',
    PREFLIGHT: 'b6245ded36cef8cdf04b5e9784cc429afa9a4e3629beb6040eb896d5099fb352',
    SAVE_SPEC: 'a06213e3cc305952506c7f6dca41cd238822efaad9f9d6470b79a842bf43de98',
    SAVE_REPORT: 'b4607711f4439bcaf39c35f981dc4452a66c4ada350708af0098000be38181f9',
    NEW_REPORT: '170f4a5760cb1d3dd7dff3e23d4306f00562053156f0a493e219e4c0c5d146ec',
    EXPLORE_REPORT: '640c42c8929df2633dacba0d5c7ef59480293702433e7b76db55ef067632207a',
    CITY_REPORT: '7ca1fb3c18a3520ab55066e1f8688437b6e3c997043d6f9a695611ea573d6ea9',
    FOUND_REPORT: '73dd4ee62acf463441cb1646c19332607ef3d1dce8f5223369c8b5bc44c95f45',
    LUA_REPORT: 'efd352c48d053f1baa71fd1f3058ea6468f99aa90991b7cd9951d36afbe62f6e',
}
INPUTS: dict[str, dict] = {}


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def key(path):
    return os.path.normcase(os.path.abspath(os.fspath(path)))


def within(path, root):
    return key(path) == key(root) or key(path).startswith(key(root) + os.sep)


def check_path(path):
    path = Path(path)
    require(path.is_absolute(), 'Absolute paths are required')
    allowed = (PROJECT, Path(r'C:\Program Files\Microsoft Visual Studio\2022\Community'),
               Path(r'C:\Program Files (x86)\Windows Kits'), Path(r'C:\Windows\System32'),
               Path(r'C:\Windows\Microsoft.NET'))
    require(any(within(path, parent) for parent in allowed) or
            key(path) == key(r'C:\Windows\Globalization\Sorting\SortDefault.nls'),
            'Input escaped copied source/toolchain roots: ' + str(path))
    for parent in (path, *path.parents):
        if parent.exists():
            require(not parent.lstat().st_file_attributes & 0x400, 'Reparse path forbidden: ' + str(parent))
    return path


def sha(data):
    return hashlib.sha256(data).hexdigest()


def artifact(path):
    path = check_path(path)
    before = path.stat()
    require(path.is_file(), 'Input missing: ' + str(path))
    result = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            result.update(block)
    after = path.stat()
    require((before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) ==
            (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns), 'Input changed while hashing')
    return {'path': str(path), 'bytes': before.st_size, 'sha256': result.hexdigest()}


def pin(row):
    require(isinstance(row, dict) and isinstance(row.get('path'), str) and
            re.fullmatch('[0-9a-fA-F]{64}', row.get('sha256', '')), 'Expected path/sha256 artifact')
    actual = artifact(row['path'])
    expected_bytes = row.get('bytes', row.get('size', actual['bytes']))
    require(actual['sha256'] == row['sha256'].lower() and actual['bytes'] == expected_bytes,
            'Pinned input differs: ' + row['path'])
    previous = INPUTS.setdefault(key(actual['path']), actual)
    require(previous['bytes'] == actual['bytes'] and previous['sha256'] == actual['sha256'],
            'Conflicting input identities: ' + actual['path'])
    return previous


def capture(path):
    return pin(artifact(path))


def read_json(path, expected=None):
    pin({'path': str(path), 'sha256': expected}) if expected else capture(path)
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def verify_inputs():
    for row in INPUTS.values():
        require(artifact(row['path']) == row, 'Input changed during preparation: ' + row['path'])


def expected_artifact(path, data):
    return {'path': str(path), 'bytes': len(data), 'sha256': sha(data)}


def historical_witness(data, recorded):
    require(sha(data) == recorded['sha256'], 'Historical generation does not reproduce: ' + recorded['path'])
    exists = Path(recorded['path']).is_file()
    if exists:
        pin(recorded)
    return {'recorded_artifact': recorded, 'currently_present': exists,
            'replayed_bytes': len(data), 'replayed_sha256': sha(data), 'exact_historical_match': True}


def apply_patches(data, rows):
    text = data.decode('latin1')
    for row in rows:
        require(text.count(row['old']) == row['count'], 'Patch context/count differs: ' + row['id'])
        text = text.replace(row['old'], row['new'])
    return text.encode('latin1')


def pure_functions(path, historical_sha, names, constants=()):
    """Compile authenticated Python definitions only, never import a builder."""
    pin({'path': str(path), 'sha256': historical_sha})
    source = Path(path).read_text(encoding='utf-8-sig')
    parsed = ast.parse(source, filename=str(path))
    selected = []
    namespace = {'__builtins__': {name: value for name, value in (
        ('RuntimeError', RuntimeError), ('ValueError', ValueError), ('TypeError', TypeError),
        ('str', str), ('bytes', bytes), ('int', int), ('bool', bool), ('len', len), ('range', range),
        ('enumerate', enumerate), ('tuple', tuple), ('list', list), ('dict', dict), ('min', min), ('max', max))}}
    for name in constants:
        rows = [node for node in parsed.body if isinstance(node, ast.Assign) and
                any(isinstance(target, ast.Name) and target.id == name for target in node.targets)]
        require(len(rows) == 1, 'Ambiguous pure constant: ' + name)
        namespace[name] = ast.literal_eval(rows[0].value)
        require(isinstance(namespace[name], str), 'Helper constant is not a string')
    for name in names:
        rows = [node for node in parsed.body if isinstance(node, ast.FunctionDef) and node.name == name]
        require(len(rows) == 1, 'Ambiguous pure preparation function: ' + name)
        selected.append(rows[0])
    require(not any(isinstance(node, (ast.Import, ast.ImportFrom)) for row in selected for node in ast.walk(row)),
            'Imports are forbidden in pure preparation functions')
    module = ast.Module(body=selected, type_ignores=[])
    exec(compile(ast.fix_missing_locations(module), str(path), 'exec'), namespace)
    return namespace, {'path': str(path), 'sha256': historical_sha, 'functions': list(names),
        'constants': list(constants), 'entire_builder_imported': False, 'native_tools_called': False,
        'function_lines': {node.name: [node.lineno, node.end_lineno] for node in selected}}


def function_region(data, signature):
    marker = signature.encode('ascii')
    require(data.count(marker) == 1, 'Function signature is not unique: ' + signature)
    begin = data.index(marker)
    opening = data.index(b'\n{', begin) + 1
    end = data.index(b'\n}', opening) + 2
    body = data[begin:end]
    require(body.count(b'{') == body.count(b'}'), 'Unsupported function brace shape: ' + signature)
    return begin, end, body


def artifacts_in(value):
    if isinstance(value, dict):
        if isinstance(value.get('path'), str) and isinstance(value.get('sha256'), str):
            yield value
        for child in value.values():
            yield from artifacts_in(child)
    elif isinstance(value, list):
        for child in value:
            yield from artifacts_in(child)


def main():
    require(os.name == 'nt', 'Windows copied-SDK paths required')
    require(not ROOT.exists() and not STAGE.exists(), 'Inspect existing runtime preparation before retrying')
    generated_names = [name + '.cpp' for name in NAMES] + ['CvSiteEvaluationClasses.h', 'CvGameCoreDLLPCH.h']
    allowed_files = {key(OVERLAY / name) for name in generated_names} | {key(PLAN)}
    directories = [ROOT, ROOT / 'source', OVERLAY, STAGE]

    def audit(event, args):
        if event == 'open' and args and isinstance(args[0], (str, bytes, os.PathLike)):
            writing = isinstance(args[1], str) and any(char in args[1] for char in 'wax+') or \
                isinstance(args[2], int) and args[2] & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND)
            if writing:
                require(key(os.fsdecode(args[0])) in allowed_files, 'Write escaped the thirteen files/one plan')
        if event == 'os.mkdir':
            require(key(os.fsdecode(args[0])) in {key(path) for path in directories}, 'Unapproved directory creation')
        if event in ('os.remove', 'os.rmdir', 'os.rename', 'os.chmod', 'os.link', 'os.symlink',
                     'subprocess.Popen', 'os.system', 'os.startfile', 'os.startfile/2') or \
                event.startswith(('ctypes.dlopen', 'socket.', 'urllib.', 'http.client.', 'winreg.')):
            raise RuntimeError('Subprocess, dynamic loading, network, registry or unapproved mutation forbidden')

    sys.addaudithook(audit)
    capture(Path(__file__).resolve())
    values = {path: read_json(path, expected) for path, expected in PINS.items()}
    base, recipe, manifest, preflight = (values[path] for path in (BASE, RECIPE, MANIFEST, PREFLIGHT))
    require(base['status'] == 'PASS_CURRENT_BASE_SDK_LINK_NOT_LOADED' and base['object_count'] == 161 and
            base['gamecore_loaded'] is False and base['overlays_used'] is False, 'Current base proof is not accepted')
    require(len(recipe['patches']) == 714, 'Current SDK recipe is not the authenticated 714-patch plan')
    protected = [pin(row) for row in preflight['protected']]
    for row in base['objects']:
        pin(row)
    pin(base['generated_dll']); pin(base['link_response']); pin(base['compile_report']); pin(base['compile_state'])
    state = read_json(base['compile_state']['path'])
    require(len(state['outputs']) == 162, 'Expected 161 current objects and one current PCH')
    for row in state['outputs']:
        pin(row)
    for row in state['inputs'].values():
        pin(row)
    manifest_by_name = {row['relative_path']: row for row in manifest}
    for row in manifest:
        require(within(row['port'], SDK_ROOT), 'Port manifest escaped current copied SDK')
        pin({'path': row['port'], 'sha256': row['port_sha256']})

    save, new, explore, city, found, lua = (values[path] for path in
        (SAVE_REPORT, NEW_REPORT, EXPLORE_REPORT, CITY_REPORT, FOUND_REPORT, LUA_REPORT))
    require(save['status'] == 'SAVE_RESTORE_SDK_CANDIDATE_LINKED' and
            new['status'] == 'NEW_GAME_SDK_CANDIDATE_LINKED' and
            explore['status'] == 'EXPLORE_SDK_CANDIDATE_LINKED' and
            city['status'] == 'CITY_SITE_SDK_CANDIDATE_LINKED' and
            found['status'] == 'FOUND_VALUE_SHARED_SDK_CANDIDATE_LINKED' and
            lua['status'] == 'SHARED_LUA_RUNTIME_CANDIDATE_BUILT', 'Historical component statuses differ')
    old_spec_row = save['sdk_baseline_patch_specification']
    old_recipe = read_json(old_spec_row['path'], old_spec_row['sha256'])
    require(len(old_recipe['patches']) == 693, 'Historical witness recipe differs')
    base_cache = {}

    def historical_base(relative):
        if relative not in base_cache:
            original = ORIGINAL / relative
            original_row = pin({'path': str(original), 'sha256': manifest_by_name[relative]['original_sha256']})
            data = original.read_bytes()
            rows = [row for row in old_recipe['patches'] if row['file'] == relative]
            require(all(row['source_sha256'] == original_row['sha256'] for row in rows), 'Historical patch origin differs')
            base_cache[relative] = apply_patches(data, rows)
        return base_cache[relative]

    def current(name):
        relative = 'CvGameCoreDLL_Expansion2/' + name
        row = manifest_by_name[relative]
        pin({'path': str(SDK / name), 'sha256': row['port_sha256']})
        return (SDK / name).read_bytes()

    generated, generation, historical = {}, {}, {}
    new_plan = read_json(new['patches']['path'], new['patches']['sha256'])
    pin(new['patch_builder'])
    require(len(new_plan) == 18 and {row['file'] for row in new_plan} ==
            {'CvGameCoreDLL_Expansion2/CvGame.cpp', 'CvGameCoreDLL_Expansion2/CvMapGenerator.cpp'}, 'NewGame patch scope differs')
    for name in ('CvGame', 'CvMapGenerator'):
        relative = 'CvGameCoreDLL_Expansion2/' + name + '.cpp'
        rows = [row for row in new_plan if row['file'] == relative]
        witness = apply_patches(historical_base(relative), rows)
        recorded = next(row for row in new['sources'] if Path(row['path']).name == name + '.cpp')
        historical[name] = historical_witness(witness, recorded)
        require(current(name + '.cpp') == historical_base(relative), 'NewGame current target changed outside accepted overlay')
        generated[name + '.cpp'] = apply_patches(current(name + '.cpp'), rows)
        require(generated[name + '.cpp'] == witness, 'NewGame current generation differs')
        generation[name + '.cpp'] = {'operation': 'all_authenticated_new_game_patches', 'patch_ids': [row['id'] for row in rows],
                            'historical_replay': historical[name]}

    save_spec = values[SAVE_SPEC]
    runtime_rows = [row for row in save_spec['patches'] if row['id'] in SAVE_IDS]
    require(len(runtime_rows) == 5 and {row['id'] for row in runtime_rows} == set(SAVE_IDS), 'Save initializer scope differs')
    for row in runtime_rows:
        relative = row['file']; name = Path(relative).stem
        full_rows = [item for item in save_spec['patches'] if item['file'] == relative]
        witness = apply_patches(historical_base(relative), full_rows)
        recorded = next(item for item in save['source_overlay'] if Path(item['path']).name == Path(relative).name)
        historical[name] = historical_witness(witness, recorded)
        before = current(name + '.cpp')
        require(before.decode('latin1').count(row['new']) == 0, 'Initializer was already applied')
        generated[name + '.cpp'] = apply_patches(before, [row])
        require(generated[name + '.cpp'].decode('latin1').count(row['new']) == row['count'], 'Initializer output count differs')
        generation[name + '.cpp'] = {'operation': 'runtime_initializer_only_on_current_base', 'patch_ids': [row['id']],
            'historical_replay': historical[name], 'old_count_and_include_patches_reapplied': False}

    explore_tool_row = next(row['artifact'] for row in explore['frozen_inputs']
                            if Path(row['original_path']).name == 'build_explore_sdk_candidate.py')
    explore_tool = PROJECT / 'tools/build_explore_sdk_candidate.py'
    ex, ex_trace = pure_functions(explore_tool, explore_tool_row['sha256'],
                                 ('replace_once', 'prepare_economic_source'), ('HELPERS',))
    old_economic = historical_base('CvGameCoreDLL_Expansion2/CvEconomicAI.cpp')
    historical['CvEconomicAI'] = historical_witness(
        ex['prepare_economic_source'](old_economic.decode('latin1')).encode('latin1'), explore['candidate_source'])
    before = current('CvEconomicAI.cpp')
    economic = ex['prepare_economic_source'](before.decode('latin1')).encode('latin1')
    anchor = b'#include "cvStopWatch.h"\r\n'
    helper = ex['HELPERS'].replace('\n', '\r\n').encode('latin1') + b'\r\n'
    require(economic.count(anchor + helper) == 1, 'Explore helper insertion differs')
    stripped = economic.replace(anchor + helper, anchor, 1)
    start = b'/// Go through the plots for the exploration automation to evaluate\r\nvoid CvEconomicAI::UpdatePlots()\r\n{'
    end = b'\r\n#define PATH_PLAN_LAST'
    before_a, before_b = before.index(start), before.index(end, before.index(start))
    after_a, after_b = stripped.index(start), stripped.index(end, stripped.index(start))
    require(before[:before_a] == stripped[:after_a] and before[before_b:] == stripped[after_b:],
            'Explore changed code outside its helper insertion/UpdatePlots body')
    generated['CvEconomicAI.cpp'] = economic
    generation['CvEconomicAI.cpp'] = {'operation': 'helper_insertion_and_UpdatePlots_body_only', 'pure_helper': ex_trace,
        'historical_replay': historical['CvEconomicAI'], 'outside_ai_body_and_helper_unchanged': True}

    city_tool = PROJECT / 'tools/build_city_site_sdk_candidate.py'
    ci, ci_trace = pure_functions(city_tool, city['builder_original']['sha256'],
                                 ('replace_once', 'prepare_source'), ('PATCH_HELPERS',))
    old_city = historical_base('CvGameCoreDLL_Expansion2/CvCitySpecializationAI.cpp')
    historical['CvCitySpecializationAI'] = historical_witness(ci['prepare_source'](old_city), city['candidate_source'])
    require(current('CvCitySpecializationAI.cpp') == old_city, 'CitySite current source changed outside accepted overlay')
    generated['CvCitySpecializationAI.cpp'] = ci['prepare_source'](current('CvCitySpecializationAI.cpp'))
    generation['CvCitySpecializationAI.cpp'] = {'operation': 'authenticated_city_site_prepare_source', 'pure_helper': ci_trace,
                                          'historical_replay': historical['CvCitySpecializationAI']}

    found_tool = PROJECT / 'tools/build_found_value_shared_sdk_candidate.py'
    fv, fv_trace = pure_functions(found_tool, found['builder_original']['original_source_sha256'],
        ('require', 'replace_once', 'function_span', 'prepare_header', 'prepare_player'))
    for name, transform in (('CvPlayerAI.cpp', fv['prepare_player']),
                            ('CvSiteEvaluationClasses.cpp', lambda data: data + b'\n#include "FoundValueSharedSdkCapture.inc"\n'),
                            ('CvSiteEvaluationClasses.h', fv['prepare_header'])):
        before = current(name)
        recorded_original = found['original_sdk_sources'][name]
        require(sha(before) == recorded_original['original_source_sha256'], 'FoundValue current base differs: ' + name)
        data = transform(before)
        recorded = next(row for row in found['candidate_sources'] if Path(row['path']).name == name)
        historical[name] = historical_witness(data, recorded)
        generated[name] = data
        generation[name] = {'operation': 'authenticated_found_value_shared_prepare', 'pure_helper': fv_trace,
                                      'historical_replay': historical[name], 'nonvirtual_member_layout_unchanged': True}
    generated['CvGameCoreDLLPCH.h'] = current('CvGameCoreDLLPCH.h')
    require(b'#include "CvSiteEvaluationClasses.h"' in generated['CvGameCoreDLLPCH.h'], 'PCH routing include missing')
    require(set(generated) == set(generated_names) and len(generated) == 13, 'Generated source/header set differs')

    writer_signatures = {
        'CvTraitClasses': 'void CvPlayerTraits::Write(FDataStream& kStream)',
        'CvCultureClasses': 'FDataStream& operator<<(FDataStream& saveTo, const CvPlayerCulture& readFrom)',
        'CvEspionageClasses': 'FDataStream& operator<<(FDataStream& saveTo, const CvPlayerEspionage& readFrom)',
        'CvEconomicAI': 'void CvEconomicAI::Write(FDataStream& kStream)',
    }
    writer_proofs = []
    for name, signature in writer_signatures.items():
        old_body = function_region(current(name + '.cpp'), signature)[2]
        new_body = function_region(generated[name + '.cpp'], signature)[2]
        require(old_body == new_body, 'Current checked count writer was modified: ' + name)
        writer_proofs.append({'name': name, 'signature': signature, 'bytes': len(old_body),
                              'before_sha256': sha(old_body), 'after_sha256': sha(new_body), 'identical': True})

    helpers = {}

    def current_historical(path, recorded):
        row = pin({'path': str(path), 'sha256': recorded['sha256']})
        if Path(recorded['path']).is_file():
            pin(recorded)
        helpers[key(path)] = {'source': row, 'historical_source': recorded, 'historical_hash_match': True}
        return row

    for row in explore['frozen_inputs']:
        if within(row['original_path'], PROJECT / 'Source/Concurrency'):
            current_historical(Path(row['original_path']), row['artifact'])
    city_source_names = {
        'city_site_bridge_header': PROJECT / 'Source/Concurrency/CitySiteScoreBridge.h',
        'city_site_bridge_source': PROJECT / 'Source/Concurrency/CitySiteScoreBridge.cpp',
        'city_site_kernel': PROJECT / 'Source/Concurrency/CitySiteScores.h',
        'ordered_batch': PROJECT / 'Source/Concurrency/OrderedBatch.h',
        'city_site_trace_header': PROJECT / 'Source/Diagnostics/CitySiteCpuTrace.h',
        'city_site_trace_source': PROJECT / 'Source/Diagnostics/CitySiteCpuTrace.cpp',
    }
    for name, path in city_source_names.items():
        current_historical(path, city['input_sources'][name])
    for row in found['frozen_inputs']:
        if within(row['original_path'], PROJECT / 'Source/Concurrency'):
            current_historical(Path(row['original_path']), row)
    for row in lua['sources']:
        pin(row)
    for row in (lua['source_manifest'], *[lua['native_callback_boundary'][name]
                for name in ('original_ldo', 'patched_ldo', 'bridge')], lua['lua_library'], lua['lua_dll']):
        pin(row)
    historical_headers = []
    for row in found['source_dependency_closure']:
        path = Path(row['original_path'])
        if not within(path, PROJECT):
            actual = pin({'path': str(path), 'sha256': row['sha256']})
            historical_headers.append(actual)
    for row in city['source_dependency_inputs']:
        path = Path(row['path'])
        if not within(path, PROJECT):
            require(row['sha256_after_compile'] == row['sha256_after_link'], 'Historical header changed across link')
            historical_headers.append(pin({'path': str(path), 'sha256': row['sha256_after_link']}))
    include_root = Path(base['compiler']['path']).parents[3] / 'include'
    for name in ('thread', 'condition_variable'):
        require(key(include_root / name) in {key(row['path']) for row in historical_headers},
                'Historical bridge header closure lacks ' + name)

    bridge_units = []
    for name in BRIDGES:
        path = PROJECT / ('Source/Diagnostics' if name == 'CitySiteCpuTrace' else 'Source/Concurrency') / (name + '.cpp')
        require(key(path) in helpers, 'Bridge lacks historical source authentication')
        bridge_units.append({'name': name, 'role': 'bridge', **helpers[key(path)]})
    include_dirs = [OVERLAY, SDK, PROJECT / 'Source/Porting', PROJECT / 'Source/LuaBorrowed',
        PROJECT / 'Source/Concurrency', PROJECT / 'Source/Diagnostics', SDK_ROOT / 'CvWorldBuilderMap/include',
        SDK_ROOT / 'CvGameCoreDLLUtil/include', SDK_ROOT / 'CvLocalization/include', SDK_ROOT / 'CvGameDatabase/include',
        SDK_ROOT / 'FirePlace/include', SDK_ROOT / 'FirePlace/include/FireWorks',
        SDK_ROOT / 'ThirdPartyLibs/Lua51/include']
    require(all(path.is_dir() for path in include_dirs[1:]), 'SDK/source include directory missing')
    verify_inputs()
    for directory in directories:
        directory.mkdir()
    generated_files = []
    for name in generated_names:
        target, data = OVERLAY / name, generated[name]
        with target.open('xb') as stream:
            stream.write(data)
        actual = artifact(target)
        require(actual == expected_artifact(target, data), 'Prepared output identity differs')
        generated_files.append(actual)
    sdk_units = [{'name': name, 'role': 'sdk_overlay',
        'source': next(row for row in generated_files if Path(row['path']).name == name + '.cpp'),
        'base_source': INPUTS[key(SDK / (name + '.cpp'))], 'generation': generation[name + '.cpp']} for name in NAMES]
    require(artifact(OVERLAY / 'CvGameCoreDLLPCH.h') ==
            expected_artifact(OVERLAY / 'CvGameCoreDLLPCH.h', (SDK / 'CvGameCoreDLLPCH.h').read_bytes()),
            'Routing PCH source header differs from current SDK')
    verify_inputs()
    require({path.name for path in OVERLAY.iterdir()} == set(generated_names) and not list(STAGE.iterdir()),
            'Unexpected output appeared during pure preparation')
    plan = {'schema': 'zerosis.sdk.current_runtime_overlay.v1',
        'status': 'CURRENT_RUNTIME_SDK_OVERLAY_PREPARED_NOT_COMPILED',
        'previous_goal_turn_classification': 'progress', 'utc': datetime.now(timezone.utc).isoformat(),
        'preparer': INPUTS[key(Path(__file__).resolve())], 'base_link': INPUTS[key(BASE)],
        'current_recipe': INPUTS[key(RECIPE)], 'current_manifest': INPUTS[key(MANIFEST)],
        'current_recipe_patch_count': 714, 'runtime_root': str(ROOT), 'source_directory': str(OVERLAY),
        'sdk_units': sdk_units, 'bridge_units': bridge_units, 'include_dirs': [str(path) for path in include_dirs],
        'compile_inputs': list(INPUTS.values()), 'generated_files': generated_files, 'generated_file_count': 13,
        'generated_source_bytes': sum(row['bytes'] for row in generated_files), 'base_object_replacements': list(NAMES),
        'base_sdk_object_count': 161, 'base_objects_to_reuse': 150, 'fresh_sdk_units': 11, 'fresh_bridge_units': 4,
        'planned_link_object_count': 165, 'shared_lua_library': INPUTS[key(lua['lua_library']['path'])],
        'shared_lua_dll': INPUTS[key(lua['lua_dll']['path'])], 'shared_lua_build': INPUTS[key(LUA_REPORT)],
        'shared_lua_static_archive_must_be_replaced_exactly_once': True,
        'semantic_proof': {'save_runtime_initializer_ids': list(SAVE_IDS), 'new_game_patch_ids': [row['id'] for row in new_plan],
            'all_historical_generation_replays_match': True, 'historical_recipe_used_only_for_ram_witnesses': True,
            'old_save_count_patches_reapplied': False, 'checked_count_writer_bodies': writer_proofs,
            'current_serialization_helper_unchanged': INPUTS[key(SDK / 'CvInfosSerializationHelper.h')],
            'explore_changes_limited_to_helpers_and_UpdatePlots': True,
            'historical_current_source_matches': list(helpers.values()), 'routing_pch_header_byte_identical': True,
            'binary_pch_used_or_copied': False},
        'historical_bridge_toolchain_header_count': len({key(row['path']) for row in historical_headers}),
        'protected': protected, 'inputs_unchanged': True, 'working_sdk_modified': False,
        'base_cache_modified': False, 'whole_project_or_sdk_copied': False, 'native_tools_called': False,
        'process_or_cdll_calls': 0, 'gamecore_loaded': False, 'host_executed': False, 'hwnd_created': False,
        'retail_accessed': False, 'runtime_updated': False, 'default_promoted': False,
        'compiled': False, 'linked': False, 'retail_save_accepted': False, 'full_engine_goal_complete': False,
        'scope': 'Source-only overlay preparation on authenticated current base; not a compiled/runtime/save acceptance'}
    with PLAN.open('x', encoding='utf-8') as stream:
        stream.write(json.dumps(plan, indent=2, sort_keys=True) + '\n')
    print(json.dumps({'status': plan['status'], 'sdk_units': 11, 'bridge_units': 4, 'generated_files': 13,
        'generated_bytes': plan['generated_source_bytes'], 'compile_inputs': len(INPUTS), 'plan': artifact(PLAN)}))


if __name__ == '__main__':
    main()
