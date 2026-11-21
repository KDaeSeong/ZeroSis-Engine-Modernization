"""Plan and compile one current menu Host; never run a Host, SDK or UI.

Planning is file-only. Applying the sealed plan runs one toolchain environment
command, five /Zs dependency discoveries, five frozen compilations and one link.
The old five-TU response recipes supply flags, not dependency counts. Actual
discovery reports establish the closure, including newly added headers.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import struct
import subprocess
import sys
import types

import build_exit_confirm_host as common
import retained_menu_suite_host_input as menu


PROJECT = Path(__file__).absolute().parents[1]
STAGE = PROJECT / 'evidence/world_terrain_original/phase12/host_build'
PARENT_ID = '20261116T114748Z_014dd63ad3bc'
PARENT_ROOT = PROJECT / 'Build/UiWindowHost' / PARENT_ID
PARENT_REPORT = PROJECT / 'evidence/ui_window_host' / PARENT_ID / 'build_result.json'
PARENT_SHA = '3d5d63304d2076c2f309344e9103eb520875a5893282ed5abfff4104ef196b8d'
COMMON_SHA = '69133de112bd30e088626379adce382912f26086aae701c8a2683fbbe0e8fd94'
MENU_GATE_SHA = '587d564e7df4e59fca5356e6f94b15b4bc3aba4a36fed11ba150ac355af08067'
PARSER_PATH = PROJECT / 'evidence/goody_hut/owned_fonts/verify_candidate.py'
PARSER_SHA = '723e8d4594ce148336149f34c2ee535512c14ad283165b4fd729473eb302123f'
PURE_HELPER_PATH = PROJECT / 'tools/build_native_restore_host.py'
PURE_HELPER_SHA = '07f50b1ab7482591792b44cc8767f27c709884f5f487b0eada7459f28c8da558'
HEADER = PROJECT / 'Source/Host/UiPopupAssets.generated.h'
PROTECTED_ROOTS = ('20261012T121847Z_732a6d5f07ea', '20261024T070230Z_cbbd79f1cbb6',
                   '20261024T091253Z_713037fbac49', '20261104T132911Z_4f194ae38472',
                   '20261105T114739Z_01dfa4cf86d8', '20261105T123201Z_9a1a8fa8c1a2',
                   '20261106T135115Z_e38cb351eca4', '20261106T230144Z_48d9fd363237',
                   '20261107T121011Z_527ea94501fb', '20261108T003146Z_40a8030edf08',
                   '20261115T011241Z_4c8fd55e99db',
                   '20261115T101941Z_99b3c393ee9a',
                   '20261115T134603Z_aa8853762399',
                   '20261116T123457Z_90b98a574efc')
# Prepared runtimes retired by an explicit user decision; their inherited protection rows are dropped.
RETIRED_ROOTS = ('20261105T133817Z_1fba743abc09',)


def require(value, message):
    if not value:
        raise RuntimeError(message)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode('ascii')


def read_document(path, digest=None):
    return common.document(path, digest)


def select_system_tool(parent, parent_ref, path=None, digest=None):
    """Read an explicit cmd-only selection; historical rows are never live inputs."""
    if path is None:
        require(digest is None, 'System-tool SHA256 requires an explicit selection file')
        return None
    require(re.fullmatch('[0-9a-f]{64}', digest or '') and
            Path(path).absolute() == STAGE / 'system_tool_selection.json',
            'System-tool selection needs its exact owned path and reviewed SHA256')
    selection, selection_ref = read_document(Path(path).absolute(), digest)
    require(selection.get('schema') == 'zerosis.cmd_system_tool_selection.v1' and
            selection.get('scope') == 'EXACT_PARENT_CMD_EXE_ONLY' and
            selection.get('parent_report') == parent_ref,
            'System-tool selection is not bound to this exact historical parent')
    previous_tools = [row for row in parent['toolchain_inputs'] if Path(row['path']).name.casefold() == 'cmd.exe']
    require(len(previous_tools) == 1, 'Parent must identify exactly one command interpreter')
    previous = previous_tools[0]
    previous_protected = [row for row in parent['protected_artifacts']
                          if common.key(row['path']) == common.key(previous['path'])]
    require(len(previous_protected) == 1 and
            selection.get('previous_toolchain_input') == previous and
            selection.get('previous_protected_artifact') == previous_protected[0],
            'Historical cmd rows differ from the pinned parent inventories')
    selected = common.sealed(selection['selected_cmd'])
    require(common.key(selected['path']) == common.key(previous['path']) and
            selected['sha256'] != previous['sha256'] and
            all(common.key(row['path']) != common.key(previous['path']) for row in parent['current_source_inputs']),
            'System-tool selection may replace only the parent cmd provider, never source inputs')
    signature_ref = common.sealed(selection['signature_receipt'])
    require(Path(signature_ref['path']) == STAGE / 'system_tool_signature.json',
            'Command-interpreter signature receipt escaped its exact evidence path')
    signature, _ = read_document(signature_ref['path'], signature_ref['sha256'])
    require(signature.get('schema') == 'zerosis.cmd_signature_observation.v1' and
            signature.get('tool') == selected and signature.get('signature_status') == 'Valid' and
            signature.get('signature_type') == 'Catalog' and signature.get('is_os_binary') is True and
            signature.get('signer_subject') == 'CN=Microsoft Windows, O=Microsoft Corporation, L=Redmond, S=Washington, C=US' and
            re.fullmatch('[0-9A-F]{40}', signature.get('signer_thumbprint', '')) and
            signature.get('company_name') == 'Microsoft Corporation' and
            signature.get('verification_method') == 'Get-AuthenticodeSignature' and
            signature.get('selected_tool_executed') is False,
            'Selected cmd lacks its exact sealed valid Microsoft catalog-signature observation')
    return dict(manifest=selection_ref, parent_report=parent_ref,
                previous_toolchain_input=previous, previous_protected_artifact=previous_protected[0],
                selected_cmd=selected, signature_receipt=signature_ref)


def selected_toolchain(parent, selection):
    selected = selection['selected_cmd'] if selection else None
    return [common.sealed(selected if selected and common.key(row['path']) == common.key(selected['path']) else row)
            for row in parent['toolchain_inputs']]


def load_helpers():
    """Respect the authenticated loader's (module, artifact) return contract."""
    parser, parser_ref = common.load_pure(PARSER_PATH, PARSER_SHA, '_menu_suite_coff_parser')
    pure, pure_ref = common.load_pure(PURE_HELPER_PATH, PURE_HELPER_SHA, '_menu_suite_object_helpers')
    require(isinstance(parser, types.ModuleType) and isinstance(pure, types.ModuleType) and
            callable(getattr(parser, 'coff', None)) and callable(getattr(parser, 'PE', None)) and
            callable(getattr(pure, 'object_defaults', None)) and callable(getattr(pure, 'catalog_summary', None)) and
            parser_ref['sha256'] == PARSER_SHA and pure_ref['sha256'] == PURE_HELPER_SHA,
            'Authenticated pure build helpers do not expose their exact expected API contract')
    return parser, pure, dict(parser=parser_ref, object_helpers=pure_ref)


def input_root_map(build):
    """Derive each frozen include root from real compiler manifest coordinates."""
    result = {}
    for row in build['compiler_inputs']:
        name, relative = row['root_name'], Path(row['relative_path'])
        require(not relative.is_absolute() and '..' not in relative.parts and relative.parts,
                'Compiler dependency has a noncanonical relative path')
        old = Path(row['path'])
        original = Path(row['original_path'])
        for _ in relative.parts:
            old, original = old.parent, original.parent
        pair = (str(old), str(original))
        require(name not in result or result[name] == pair, 'Conflicting compiler include-root provenance')
        result[name] = pair
    # The response also carries valid include search roots that the old source
    # never visited. They must point to actual originals during new discovery;
    # otherwise a newly included SDK header could be silently missed.
    for index, original in enumerate(build.get('system_include_roots', [])):
        name = 'system_%02d' % index
        pair = (str(PARENT_ROOT / 'frozen/include_roots' / name), str(original))
        require(name not in result or tuple(map(common.key, result[name])) == tuple(map(common.key, pair)),
                'Sealed system include root conflicts with compiler provenance')
        result[name] = pair
    require('project' in result and common.key(result['project'][1]) == common.key(PROJECT),
            'Compiler project include root differs from the workspace')
    return result


def replace_paths(text, pairs):
    # Include both Windows and response-file slash forms; longest roots first.
    substitutions = {}
    for source, target in pairs:
        substitutions[str(source)] = str(target)
        substitutions[Path(source).as_posix()] = Path(target).as_posix()
    if not substitutions:
        return text
    # Targets intentionally live below PROJECT. A sequence of str.replace calls
    # would therefore rewrite an already relocated SDK/system target when the
    # PROJECT prefix is processed later. Match only the original string once.
    pattern = re.compile('(?:' + '|'.join(re.escape(source) for source in
                         sorted(substitutions, key=len, reverse=True)) + r')(?=$|[\\/";\r\n])')
    return pattern.sub(lambda match: substitutions[match.group(0)], text)


def discovery_response(raw, root_map, dependency_path):
    """Use current original includes and syntax-only compilation, without /Fo."""
    text = replace_paths(raw.decode('utf-8-sig').replace('\r\n', '\n'), root_map.values())
    lines = [line for line in text.splitlines() if line.casefold() != '/c' and
             not line.casefold().startswith(('/fo', '/sourcedependencies'))]
    require(not any(line.casefold() in ('/zs', '/p', '/e', '/ep') for line in lines),
            'Unexpected existing discovery/preprocessor response mode')
    lines += ['/Zs', '/sourceDependencies "' + str(dependency_path) + '"']
    require(str(PARENT_ROOT) not in '\n'.join(lines) and PARENT_ROOT.as_posix() not in '\n'.join(lines),
            'Dependency discovery still refers to an old frozen build')
    return ('\n'.join(lines) + '\n').encode('utf-8')


def compiler_dependencies(path):
    document, _ = read_document(path)
    fields = document.get('Data', {})
    require(document.get('Version') == '1.2' and type(fields.get('Source')) is str and
            type(fields.get('Includes')) is list and all(type(path) is str for path in fields['Includes']) and
            not any(fields.get(name) for name in ('ProvidedModule', 'ImportedModules', 'ImportedHeaderUnits')),
            'Unexpected actual compiler dependency schema')
    values = [fields['Source'], *fields['Includes']]
    return {common.key(path): str(Path(path).absolute()) for path in values}, len(values)


def source_inventory(parent, additional):
    """Refresh project sources; require unchanged external compiler/provider inputs."""
    current = {}
    for old in parent['current_source_inputs']:
        actual = common.artifact(old['path'])
        if not Path(old['path']).is_relative_to(PROJECT):
            require((actual['bytes'], actual['sha256']) == (old['bytes'], old['sha256']),
                    'External compiler/SDK input changed; select a new toolchain explicitly')
        current[common.key(actual['path'])] = actual
    for path in [Path(__file__).absolute(), PROJECT / 'tools/retained_menu_suite_host_input.py', *additional]:
        path = Path(path).absolute()
        require(path.is_relative_to(PROJECT) and '..' not in path.parts and
                path.suffix.casefold() in ('.h', '.hpp', '.inc', '.cpp', '.c', '.lua', '.xml', '.py', '.json', '.dds'),
                'Additional source is outside the bounded project source types')
        current[common.key(path)] = common.artifact(path)
    return list(current.values())


def protected_inventory(parent, selection=None):
    """Keep exact current/default/previous/prepared runs and every retained save."""
    retired = [PROJECT / 'Build/InteractiveGameRuntime' / identifier for identifier in RETIRED_ROOTS]
    selected = selection['selected_cmd'] if selection else None
    rows = {common.key(row['path']): common.sealed(
                selected if selected and common.key(row['path']) == common.key(selected['path']) else row)
            for row in parent['protected_artifacts']
            if not any(Path(row['path']).is_relative_to(root) for root in retired)}
    for relative in ('tools/Start-Engine.ps1', 'Play/EarlyAccess/release.json'):
        row = common.artifact(PROJECT / relative)
        rows[common.key(row['path'])] = row
    # Include newer owned saves or diagnostics without following reparse points.
    for identifier in PROTECTED_ROOTS:
        root = PROJECT / 'Build/InteractiveGameRuntime' / identifier
        require(root.is_dir(), 'A protected actual/default/prepared runtime is absent')
        for directory, names, files in os.walk(root, followlinks=False):
            for name in names:
                require(not (Path(directory) / name).lstat().st_file_attributes & 0x400,
                        'Protected runtime has a reparse directory')
            for name in files:
                row = common.artifact(Path(directory) / name)
                rows[common.key(row['path'])] = row
    return list(rows.values())


def prepare_plan(additional, catalog_count, source_manifest=None, system_tool_selection=None, system_tool_sha256=None):
    """Read and hash a reviewable plan; no environment/compiler is executed."""
    require(os.name == 'nt' and sys.dont_write_bytecode and __debug__, 'Use Windows Python -B without optimization')
    require(not any(value for name, value in os.environ.items() if name.upper() in ('CL', '_CL_', 'LINK')),
            'Ambient compiler/linker injection options are forbidden')
    common.pin(PROJECT / 'tools/build_exit_confirm_host.py', COMMON_SHA)
    common.pin(PROJECT / 'tools/retained_menu_suite_host_input.py', MENU_GATE_SHA)
    _, _, helper_contract = load_helpers()
    parent, parent_ref = read_document(PARENT_REPORT, PARENT_SHA)
    require(parent['build_id'] == PARENT_ID and parent['status'] == 'UI_WINDOW_HOST_CANDIDATE_BUILT',
            'Current base Host report differs')
    selection = select_system_tool(parent, parent_ref, system_tool_selection, system_tool_sha256)
    frozen = menu.frozen_rows(parent)
    for row in frozen.values():
        common.sealed(row)
    for group in ('provider_inputs', 'system_libraries', 'implicit_libraries'):
        for row in parent[group]:
            origin = row.get('original_path')
            if origin and os.path.lexists(origin):
                actual = common.artifact(origin)
                require((actual['bytes'], actual['sha256']) == (row['bytes'], row['sha256']),
                        'Constant provider/system library changed; select a new provider explicitly')
    manifest_ref = None
    if source_manifest:
        manifest, manifest_ref = read_document(source_manifest)
        require(type(manifest.get('sources')) is list, 'Menu source manifest must contain explicit sources')
        for row in manifest['sources']:
            verified = common.sealed(row)
            additional.append(Path(verified['path']))
    roots = input_root_map(parent)
    responses = {}
    for unit in parent['final_compilation']['translation_units']:
        responses[unit['translation_unit']] = common.sealed(unit['response'])
    require(set(responses) == set(menu.TUS), 'Expected exactly the five known Host translation units')
    header_ref = common.artifact(HEADER)
    arrays, order = menu.parse_catalog(common.read_bytes(header_ref), catalog_count,
                                       ('ZeroSisUiScene', 'ExitConfirm', 'ExitConfirmLayout'))
    catalog_payloads = [dict(name=name, index=index, bytes=len(arrays[name]), sha256=hashlib.sha256(arrays[name]).hexdigest())
                        for index, name in enumerate(order)]
    tools = {name: common.sealed(parent[name]) for name in ('compiler', 'linker', 'dumpbin')}
    toolchain = selected_toolchain(parent, selection)
    vcvars = common.sealed(parent['vcvars'])
    require({Path(row['path']).name.casefold() for row in toolchain} == {'cmd.exe', 'c1xx.dll', 'c2.dll'},
            'Expected exact retained compiler backend and environment toolchain')
    plan = dict(schema='zerosis.menu_suite_host.plan.v1', status='FILE_ONLY_PLAN_REQUIRES_ACTUAL_DEPENDENCY_DISCOVERY',
        parent=parent_ref, builder=common.artifact(Path(__file__).absolute()), common_helper=common.artifact(PROJECT / 'tools/build_exit_confirm_host.py'),
        menu_gate=common.artifact(PROJECT / 'tools/retained_menu_suite_host_input.py'), pure_parser=common.pin(PARSER_PATH, PARSER_SHA),
        pure_build_helper=common.pin(PURE_HELPER_PATH, PURE_HELPER_SHA), source_manifest=manifest_ref,
        authenticated_helper_contract=helper_contract,
        include_roots=roots, prior_responses=responses, prior_link_response=common.sealed(parent['link_response']),
        tools=tools, toolchain_inputs=toolchain, vcvars=vcvars, system_tool_selection=selection,
        current_source_inputs=source_inventory(parent, additional), protected_artifacts=protected_inventory(parent, selection),
        catalog_count=len(order), catalog_payloads=catalog_payloads, header=header_ref,
        dependency_count_policy='ACTUAL_FIVE_ZS_REPORTS_NO_PREASSUMED_COUNTS',
        additional_sources=[str(Path(path).absolute()) for path in additional],
        direct_child_phases=['environment', *('discover_' + name for name in menu.TUS),
                             *('compile_' + name for name in menu.TUS), 'link'],
        allowed_native_children='EXACT_ENVIRONMENT_AND_COMPILER_LINKER_ONLY',
        host_sdk_clr_hwnd_gpu_or_game_execution_allowed=False, full_ui_preparer_main_allowed=False,
        default_promotion_allowed=False, automatic_retry_allowed=False, full_engine_goal_complete=False)
    return plan


class BuildGuard(common.BuildGuard):
    def audit(self, event, values):
        if event.startswith(('sqlite3.', 'winreg.')) or event in ('os.replace', 'os.posix_spawnp'):
            self.denied.append(dict(event=event, target=str(values[0])[:240] if values else ''))
            raise PermissionError('Menu Host build forbids native state access: ' + event)
        return super().audit(event, values)


def build(plan, plan_ref):
    """Apply one sealed plan. Call only after the user-authorized source work ends."""
    parent, parent_ref = read_document(plan['parent']['path'], plan['parent']['sha256'])
    require(common.key(parent_ref['path']) == common.key(PARENT_REPORT) and parent_ref['sha256'] == PARENT_SHA,
            'Build plan does not use this exact historical parent')
    selection = plan.get('system_tool_selection')
    if selection is not None:
        verified = select_system_tool(parent, parent_ref, selection['manifest']['path'], selection['manifest']['sha256'])
        require(canonical(selection) == canonical(verified), 'System-tool selection changed after planning')
        protected_cmd = [row for row in plan['protected_artifacts']
                         if common.key(row['path']) == common.key(selection['selected_cmd']['path'])]
        require(protected_cmd == [selection['selected_cmd']], 'Selected cmd protection differs from its reviewed selection')
    require(canonical(plan['toolchain_inputs']) == canonical(selected_toolchain(parent, selection)),
            'Plan toolchain changes more than its exact selected command interpreter')
    for row in [plan_ref, plan['builder'], plan['common_helper'], plan['menu_gate'], plan['parent'],
                plan['pure_parser'], plan['pure_build_helper'], plan['vcvars'], *plan['tools'].values(),
                *plan['toolchain_inputs'], *plan['current_source_inputs'], *plan['protected_artifacts'],
                *plan['prior_responses'].values(), plan['prior_link_response']]:
        common.sealed(row)
    signature = hashlib.sha256(canonical(plan)).hexdigest()
    identifier = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ_') + signature[:12]
    root = PROJECT / 'Build/UiWindowHost' / identifier
    output = PROJECT / 'evidence/ui_window_host' / identifier
    attempt = STAGE / 'attempts' / signature[:20]
    roots = (root, output, attempt)
    require(not any(os.path.lexists(path) for path in roots), 'Single-use plan already has outputs; inspect rather than replay')
    for path in roots:
        for ancestor in path.parents:
            if ancestor.exists():
                require(not ancestor.lstat().st_file_attributes & 0x400, 'Output ancestor is a reparse point')
        path.mkdir(parents=True, exist_ok=False)
    environment_script = root / 'read_build_environment.cmd'
    cmd = next(row['path'] for row in plan['toolchain_inputs'] if Path(row['path']).name.casefold() == 'cmd.exe')
    commands_allowed = [([cmd, '/d', '/c', str(environment_script)], root)]
    for phase in ('discovery', 'final'):
        for index, name in enumerate(menu.TUS):
            cwd = root / phase / f'tu_{index:02d}_{name}'
            commands_allowed.append(([plan['tools']['compiler']['path'], '@' + str(cwd / (name + '.compile.rsp'))], cwd))
    link_path = root / 'final/ZeroSisHost_x64.link.rsp'
    commands_allowed.append(([plan['tools']['linker']['path'], '@' + str(link_path)], link_path.parent))
    b''.decode('mbcs')
    parser, pure, _ = load_helpers()
    guard = BuildGuard(roots, commands_allowed)
    commands, discoveries, completed, materialized, donors = [], [], [], {}, {}

    def write_raw(path, raw):
        path = Path(path)
        require(guard.owns(path) and not os.path.lexists(path), 'Output is not fresh and private')
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open('xb') as stream:
            stream.write(raw)

    def write(path, value):
        write_raw(path, json.dumps(value, indent=2, ensure_ascii=True).encode('ascii') + b'\n')

    def execute(command, cwd, log, phase, env=None):
        record = dict(command=list(command), cwd=str(cwd), phase=phase)
        commands.append(record)
        require(guard.pending is None, 'Overlapping direct-child execution')
        guard.pending = (list(command), str(cwd))
        try:
            result = subprocess.run(command, cwd=cwd, env=env, capture_output=True, timeout=300,
                creationflags=subprocess.CREATE_NO_WINDOW | subprocess.BELOW_NORMAL_PRIORITY_CLASS)
        except BaseException as error:
            record.update(error_type=type(error).__name__, timed_out=isinstance(error, subprocess.TimeoutExpired))
            raise
        finally:
            guard.pending = None
        write_raw(log, result.stderr if phase == 'environment' else result.stdout + result.stderr)
        record.update(returncode=result.returncode, log=common.artifact(log))
        require(result.returncode == 0 and (phase == 'environment' or not re.search(
            rb'\bwarning\s+(?:C|LNK)\d+', result.stdout + result.stderr, re.I)), 'Compiler/toolchain phase failed: ' + phase)
        return result

    try:
        started = attempt / 'started.json'
        write(started, dict(schema='zerosis.menu_suite_host.started.v1', build_id=identifier, signature=signature,
            reviewed_preflight=plan_ref, no_automatic_retry=True, host_sdk_clr_window_gpu_or_dll_execution_allowed=False))
        write_raw(environment_script, ('@echo off\ncall "' + plan['vcvars']['path'] + '" >nul\n'
                                      'if errorlevel 1 exit /b %errorlevel%\nset\n').encode('ascii'))
        if selection is not None:
            for row in (selection['manifest'], selection['signature_receipt'], selection['selected_cmd']):
                common.sealed(row)
        result = execute(commands_allowed[0][0], root, attempt / 'environment.stderr.log', 'environment')
        env = os.environ.copy()
        for line in result.stdout.decode('mbcs').splitlines():
            if '=' in line and not line.startswith('='):
                name, value = line.split('=', 1)
                env[name] = value
        (root / 'tmp').mkdir()
        env.update(TMP=str(root / 'tmp'), TEMP=str(root / 'tmp'), VSLANG='1033', CL='', _CL_='', LINK='')
        actual_dependencies = {}
        for index, name in enumerate(menu.TUS):
            cwd = root / 'discovery' / f'tu_{index:02d}_{name}'
            response, dependency = cwd / (name + '.compile.rsp'), cwd / (name + '.sourceDependencies.json')
            write_raw(response, discovery_response(common.read_bytes(plan['prior_responses'][name]), plan['include_roots'], dependency))
            execute(commands_allowed[1 + index][0], cwd, attempt / ('discover_' + name + '.log'), 'discover_' + name, env)
            paths, visits = compiler_dependencies(dependency)
            actual_dependencies.update(paths)
            discoveries.append(dict(translation_unit=name, response=common.artifact(response),
                dependency_report=common.artifact(dependency), actual_paths=list(paths.values()),
                actual_dependency_count=len(paths), dependency_visits=visits, returncode=0, objects=[]))
        current = {common.key(row['path']): row for row in plan['current_source_inputs']}
        for path in actual_dependencies.values():
            current[common.key(path)] = common.artifact(path)
        old_frozen = menu.frozen_rows(parent)
        old_by_origin = {common.key(row['origin']): row for row in old_frozen.values()}
        include_roots = [(name, Path(pair[1])) for name, pair in plan['include_roots'].items()]

        def freeze(source, target, origin, role=None):
            source = common.sealed(source)
            path = common.key(target)
            if path in materialized:
                require((materialized[path]['bytes'], materialized[path]['sha256'], common.key(materialized[path]['original_path'])) ==
                        (source['bytes'], source['sha256'], common.key(origin)), 'Conflicting frozen materialization')
                return materialized[path]
            donor = old_by_origin.get(common.key(origin))
            same_donor = donor is not None and (donor['bytes'], donor['sha256']) == (source['bytes'], source['sha256'])
            target.parent.mkdir(parents=True, exist_ok=True)
            require(not os.path.lexists(target), 'Frozen target already exists')
            if same_donor:
                donor = common.sealed(donor)
                guard.links[path] = common.key(donor['path'])
                os.link(donor['path'], target)
                donors[common.key(donor['path'])] = donor
                method = 'attested_snapshot_hardlink'
            else:
                guard.copies.add(path)
                write_raw(target, common.read_bytes(source))
                os.chmod(target, stat.S_IREAD)
                method = 'owned_changed_source_copy' if donor is not None else 'owned_added_source_copy'
            row = dict(**common.artifact(target), original_path=str(origin), materialization=method)
            if same_donor:
                row['reused_from_path'] = donor['path']
            if role is not None:
                row['role'] = role
            materialized[path] = row
            return row

        compiler_inputs, compiler_by_origin = [], {}
        for path in actual_dependencies.values():
            matches = [(name, original) for name, original in include_roots if Path(path).is_relative_to(original)]
            require(matches, 'Discovered compiler input lies outside the sealed include roots: ' + path)
            name, original = max(matches, key=lambda item: len(item[1].parts))
            relative = Path(path).relative_to(original)
            target = root / 'frozen/include_roots' / name / relative
            row = dict(freeze(current[common.key(path)], target, path), root_name=name, relative_path=str(relative))
            compiler_inputs.append(row)
            compiler_by_origin[common.key(path)] = row
        sources, source_origins = [], set()
        source_paths = [row.get('original_source', row.get('original_path')) for row in parent['sources']]
        source_paths += [str(path) for path in plan['additional_sources'] if Path(path).suffix.casefold() != '.py']
        source_paths += [path for path in actual_dependencies.values() if any(Path(path).is_relative_to(PROJECT / relative)
                         for relative in ('Source/Host', 'Source/Presentation', 'Source/Porting'))]
        for path in source_paths:
            original = common.key(path)
            if original in source_origins:
                continue
            require(original in current and Path(path).is_relative_to(PROJECT), 'Source manifest is not part of the actual current closure')
            source_origins.add(original)
            row = compiler_by_origin.get(original)
            if row is None:
                row = freeze(current[original], root / 'frozen/project' / Path(path).relative_to(PROJECT), path)
            sources.append(dict(row, original_source=str(path), relative_path=str(Path(path).relative_to(PROJECT))))

        def inherited(row, refresh=False):
            origin = row.get('original_source', row.get('original_path'))
            source = current.get(common.key(origin)) if refresh else common.sealed(row)
            require(source is not None, 'A refreshed producer/asset is absent from the current closure')
            target = root / Path(row['path']).relative_to(PARENT_ROOT)
            result = {**row, **freeze(source, target, origin, row.get('role'))}
            result.pop('reused_from_path', None)
            if materialized[common.key(target)]['materialization'] == 'attested_snapshot_hardlink':
                result['reused_from_path'] = materialized[common.key(target)]['reused_from_path']
            return result

        providers, systems, implicit = ([inherited(row) for row in parent[name]] for name in
                                        ('provider_inputs', 'system_libraries', 'implicit_libraries'))
        reports = {name: inherited(row) for name, row in parent['provider_reports'].items()}
        lua_build, assets = inherited(parent['shared_lua_build']), inherited(parent['ui_assets'], refresh=True)
        build_tools = [inherited(row, refresh=True) for row in parent['build_tools']]
        producer_paths = [PROJECT / 'tools/build_menu_suite_host.py', PROJECT / 'tools/retained_menu_suite_host_input.py']
        producer_paths += [Path(path) for path in plan['additional_sources'] if Path(path).suffix.casefold() == '.py']
        producer_origins = {common.key(row['original_path']) for row in build_tools}
        for origin in producer_paths:
            if common.key(origin) in producer_origins:
                continue
            relative = origin.relative_to(PROJECT)
            build_tools.append(freeze(current[common.key(origin)], root / 'frozen/project' / relative, origin, origin.stem))
            producer_origins.add(common.key(origin))
        expected_union = {common.key(row['path']) for row in compiler_inputs}
        final_union = set()
        for index, (name, stem, discovery) in enumerate(zip(menu.TUS, menu.STEMS, discoveries)):
            cwd = root / 'final' / f'tu_{index:02d}_{name}'
            response, dependency = cwd / (name + '.compile.rsp'), cwd / (name + '.sourceDependencies.json')
            source_text = Path(discovery['response']['path']).read_text(encoding='utf-8-sig')
            lines = [line for line in source_text.splitlines() if line.casefold() != '/zs' and
                     not line.casefold().startswith('/sourcedependencies')]
            pairs = [(original, root / 'frozen/include_roots' / root_name) for root_name, original in include_roots]
            final_text = replace_paths('\n'.join(lines), pairs)
            final_text += '\n/c\n/Fo"' + (cwd / 'obj').as_posix() + '/"\n/sourceDependencies "' + str(dependency) + '"\n'
            write_raw(response, final_text.encode('utf-8'))
            (cwd / 'obj').mkdir()
            execute(commands_allowed[6 + index][0], cwd, attempt / ('compile_' + name + '.log'), 'compile_' + name, env)
            actual, visits = compiler_dependencies(dependency)
            expected = {common.key(compiler_by_origin[common.key(path)]['path']) for path in discovery['actual_paths']}
            require(set(actual) == expected and expected <= expected_union, 'Final frozen dependency set differs from actual /Zs discovery')
            final_union.update(actual)
            object_ref = common.artifact(cwd / 'obj' / (stem + '.obj'))
            object_raw = common.read_bytes(object_ref)
            machine = parser.coff(object_raw)
            defaults = pure.object_defaults(object_raw)
            allowed_libraries = {Path(row['path']).name.casefold() for row in providers + systems + implicit}
            require(machine['machine_hex'] == '0x8664' and set(defaults) <= allowed_libraries,
                    'Final COFF object used an unattested default library')
            completed.append(dict(translation_unit=name, command=commands_allowed[6 + index][0], response=common.artifact(response),
                dependency_report=common.artifact(dependency), object=object_ref, log=common.artifact(attempt / ('compile_' + name + '.log')),
                returncode=0, actual_dependency_count=len(actual), expected_dependency_count=len(expected), dependency_visits=visits,
                default_libraries=defaults, coff_machine=machine['machine_hex']))
        require(final_union == expected_union, 'Frozen final compiler union differs from discovery')
        link = replace_paths(common.read_bytes(plan['prior_link_response']).decode('utf-8-sig'), [(PARENT_ROOT, root)])
        # The parent's object response filenames stay in the same five-TU layout;
        # output/map/library paths relocate as a group, without new link options.
        linked = re.findall(r'^"([^"\r\n]+\.obj)"$', link.replace('\r\n', '\n'), re.M | re.I)
        require([common.key(path) for path in linked] == [common.key(row['object']['path']) for row in completed],
                'Link recipe does not consume exactly the five current objects')
        write_raw(link_path, link.encode('utf-8'))
        execute(commands_allowed[-1][0], link_path.parent, attempt / 'link.log', 'link', env)
        image_path = root / Path(parent['executable']['path']).relative_to(PARENT_ROOT)
        map_path = root / Path(parent['map']['path']).relative_to(PARENT_ROOT)
        image_ref, map_ref = common.artifact(image_path), common.artifact(map_path)
        pe = menu.PE(common.read_bytes(image_ref))
        arrays, order = menu.parse_catalog(common.read_bytes(plan['header']), plan['catalog_count'], ('ZeroSisUiScene', 'ExitConfirm', 'ExitConfirmLayout'))
        catalog, imports, markers = pe.catalog(arrays, order), pe.imports(), pe.occurrences(menu.MARKER)
        require(set(imports) == set(parent['imports']['dependencies']) and len(imports) == len(set(imports)) and len(markers) == 1,
                'Linked menu Host import set or readonly restore marker differs')
        optional = struct.unpack_from('<I', pe.data, 0x3c)[0] + 24
        require(struct.unpack_from('<I', pe.data, optional + 108)[0] >= 16 and all(
            struct.unpack_from('<II', pe.data, optional + 112 + 8 * index) == (0, 0) for index in (13, 14)),
            'Linked menu Host acquired delay imports or CLR')
        static = attempt / 'static_pe.json'
        write(static, dict(schema='zerosis.menu_suite_host.static_pe.v1', source='PURE_FILE_BACKED_PE_AND_COFF',
            image=image_ref, catalog=catalog, dependencies=imports, clr_directory_empty=True, delay_import_directory_empty=True,
            restore_contract_marker=dict(ascii=menu.MARKER.decode('ascii'), rva=markers[0], read_only=True), executable_or_dll_loaded=False))
        for row in [*plan['current_source_inputs'], *plan['protected_artifacts'], *donors.values(), plan_ref]:
            common.sealed(row)
        for row in materialized.values():
            common.sealed(row)
        require(len(commands) == 12 and not guard.allowed and not guard.denied and
                [row['phase'] for row in commands] == plan['direct_child_phases'], 'Direct toolchain child sequence differs')
        counts = dict(compiler_inputs=len(compiler_inputs), source_manifest=len(sources), current_source_inputs=len(current),
            unique_frozen_files=len(materialized), planned_hardlinks=sum(row['materialization'] == 'attested_snapshot_hardlink' for row in materialized.values()),
            planned_private_copies=sum(row['materialization'] != 'attested_snapshot_hardlink' for row in materialized.values()),
            private_copy_bytes=sum(row['bytes'] for row in materialized.values() if row['materialization'] != 'attested_snapshot_hardlink'),
            build_tools=len(build_tools), tu_dependencies=[row['actual_dependency_count'] for row in completed])
        revisions, added = [], []
        for origin, row in current.items():
            before = old_by_origin.get(origin)
            if before is not None and (before['bytes'], before['sha256']) != (row['bytes'], row['sha256']):
                revisions.append(dict(before=dict(original_path=row['path'], bytes=before['bytes'], sha256=before['sha256']),
                    backup=common.sealed(before), after=row, preservation='EXISTING_IMMUTABLE_PARENT_FROZEN_INPUT'))
            elif before is None and any(common.key(item['original_path']) == origin for item in materialized.values()):
                added.append(row)
        map_text = common.read_bytes(map_ref).decode('mbcs')
        mapped = {name.casefold().removesuffix('.lib') + '.lib' for name in re.findall(
            r'\s([\w.-]+):\S+\.(?:obj|dll)\s*$', map_text, re.I | re.M)}
        allowed_libraries = {Path(row['path']).name.casefold() for row in providers + systems + implicit}
        require(mapped <= allowed_libraries, 'Link map consumed an unattested library')
        # Explicit context inputs are preserved but are not compiler dependencies.
        by_original = {common.key(row['original_source']): row for row in sources}
        report = dict(parent, build_id=identifier, baseline_build=plan['parent'], profile=plan_ref,
            menu_suite_builder=plan['builder'], menu_suite_component=plan['source_manifest'] or plan_ref,
            toolchain_inputs=plan['toolchain_inputs'],
            system_tool_selection=selection['manifest'] if selection else None,
            system_tool_signature=selection['signature_receipt'] if selection else None,
            compiler_inputs=compiler_inputs, compiler_dependency_count=len(compiler_inputs), sources=sources,
            window_sources=[by_original[common.key(row['original_source'])] for row in parent['window_sources']],
            provider_inputs=providers, system_libraries=systems, libraries=providers + systems,
            implicit_libraries=implicit, implicit_libraries_before=parent['implicit_libraries'], implicit_libraries_after=implicit,
            actual_implicit_library_namesfrommap=sorted(mapped & {Path(row['path']).name.casefold() for row in implicit}),
            build_tools=build_tools, provider_reports=reports, shared_lua_build=lua_build, ui_assets=assets,
            ui_asset_preparation=dict(executed_by_builder=False, report=plan['header'], status='SEALED_CURRENT_GENERATED_CATALOG'),
            dependency_discovery=dict(executed=True, syntax_only=True, translation_units=discoveries,
                                      closure_policy='ACTUAL_ZS_REPORT_UNION_RECHECKED_BY_FINAL_FROZEN_COMPILE'),
            final_compilation=dict(translation_units=completed), final_dependency_reports={row['translation_unit']: row['dependency_report'] for row in completed},
            response=completed[0]['response'], dependency_report=completed[0]['dependency_report'], link_response=common.artifact(link_path),
            link_log=common.artifact(attempt / 'link.log'), map=map_ref,
            executable={**image_ref, 'pe': dict(architecture='x64', pe_format='PE32+', is_dll=False)},
            imports=dict(dependencies=imports, log=common.artifact(static), source='PURE_PYTHON_STATIC_PE'), catalog=catalog,
            restore_contract_marker=dict(ascii=menu.MARKER.decode('ascii'), rva=markers[0], inclusion_evidence_only=True),
            current_source_inputs=list(current.values()), protected_artifacts=plan['protected_artifacts'], started=common.artifact(started),
            reviewed_preflight=plan_ref, source_revision_provenance=revisions,
            sources_changed_from_baseline=[row['after'] for row in revisions], new_source_inputs=added,
            final_environment={name: env.get(name, '') for name in ('INCLUDE', 'LIB', 'LIBPATH', 'TMP', 'TEMP', 'VSLANG', 'CL', '_CL_', 'LINK')},
            frozen_input_reuse=dict(hardlinked_files=counts['planned_hardlinks'], copied_files=counts['planned_private_copies'],
                copied_source_bytes=counts['private_copy_bytes'], donor_content_and_metadata_preserved=True),
            scope='Actual five-TU syntax discovery, frozen closure, five current compilations and one file-attested link; no Host or SDK run.',
            source_inputs_unchanged=True, provider_inputs_unchanged=True, host_runtime_executed=False, gamecore_loaded=False,
            sdk_linked=False, mods_updated=False, stage_updated=False, default_promoted=False, sdk_restore_verified=False,
            native_restore_approved=False, full_engine_goal_complete=False)
        # Inherited producers refer to the older immutable build as context only;
        # replace their live source aliases with the exact preserved donor copy.
        for field in ('exit_confirm_builder', 'exit_confirm_component'):
            if field in report:
                origin = common.key(report[field]['path'])
                if origin in old_by_origin:
                    report[field] = common.sealed(old_by_origin[origin])
        report_path = output / 'build_result.json'
        write(report_path, report)
        run = dict(schema='zerosis.menu_suite_host.run.v1', status='PASS_CURRENT_MENU_SUITE_HOST_OFFLINE_BUILD_ONLY',
            build_id=identifier, signature=signature, reviewed_preflight=plan_ref, build_result=common.artifact(report_path),
            commands=commands, compilation=completed, discovery=discoveries, materialized=list(materialized.values()),
            frozen_donors=list(donors.values()), current_inputs=list(current.values()), actual_counts=counts,
            protected_runtime_inputs=plan['protected_artifacts'], static_pe=common.artifact(static),
            denied_operations=guard.denied, host_sdk_clr_window_gpu_or_dll_executed=False, no_automatic_retry=True,
            full_engine_goal_complete=False)
        write(attempt / 'run.json', run)
        print(json.dumps(dict(status=run['status'], build_id=identifier, build_result=common.artifact(report_path),
                              run=common.artifact(attempt / 'run.json'), executable=image_ref)), flush=True)
        return run
    except BaseException as error:
        failure = attempt / 'failure.json'
        if not failure.exists():
            write(failure, dict(schema='zerosis.menu_suite_host.failure.v1', status='FAILED_DO_NOT_REPLAY',
                build_id=identifier, error_type=type(error).__name__, detail=str(error), commands=commands,
                discovery=discoveries, completed_translation_units=completed, materialized=list(materialized.values()),
                denied_operations=guard.denied, automatic_retry_allowed=False, host_sdk_clr_window_gpu_or_dll_executed=False))
        raise


def main(argv=None):
    cli = argparse.ArgumentParser(description=__doc__)
    choice = cli.add_mutually_exclusive_group(required=True)
    choice.add_argument('--plan', type=Path, help='Write a new file-only plan; no compiler is invoked')
    choice.add_argument('--build-plan', type=Path, help='Compile and link only the exact reviewed plan')
    cli.add_argument('--plan-sha256')
    cli.add_argument('--catalog-count', type=int)
    cli.add_argument('--additional-source', type=Path, action='append', default=[])
    cli.add_argument('--source-manifest', type=Path)
    cli.add_argument('--system-tool-selection', type=Path, help='Plan only: exact cmd-provider selection evidence')
    cli.add_argument('--system-tool-sha256', help='Plan only: SHA256 of the explicit cmd-provider selection')
    options = cli.parse_args(argv)
    require(sys.dont_write_bytecode and __debug__, 'Use Python -B without optimization')
    if options.plan:
        require(options.catalog_count is not None, 'File-only planning requires the exact current catalog count')
        path = options.plan.absolute()
        require(path.is_relative_to(STAGE) and not os.path.lexists(path), 'Plan must be a fresh leaf in the owned menu Host stage')
        plan = prepare_plan(options.additional_source, options.catalog_count, options.source_manifest,
                            options.system_tool_selection, options.system_tool_sha256)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open('xb') as stream:
            stream.write(json.dumps(plan, indent=2, ensure_ascii=True).encode('ascii') + b'\n')
        print(json.dumps(dict(status=plan['status'], plan=common.artifact(path), native_execution=False)))
        return 0
    require(options.system_tool_selection is None and options.system_tool_sha256 is None,
            'System-tool options are plan-only; build must use the sealed plan selection')
    require(options.plan_sha256 and re.fullmatch('[0-9a-f]{64}', options.plan_sha256), 'Build requires the exact reviewed plan SHA256')
    require(options.build_plan.absolute().is_relative_to(STAGE), 'Build plan lies outside its owned evidence stage')
    plan, plan_ref = read_document(options.build_plan.absolute(), options.plan_sha256)
    require(plan.get('schema') == 'zerosis.menu_suite_host.plan.v1' and
            plan.get('host_sdk_clr_hwnd_gpu_or_game_execution_allowed') is False and
            plan.get('automatic_retry_allowed') is False, 'Build plan exceeds its offline scope')
    build(plan, plan_ref)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
