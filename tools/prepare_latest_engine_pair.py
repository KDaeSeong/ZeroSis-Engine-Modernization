"""Prepare the current attested Host/SDK pair without native execution.

The established materializer owns the runtime layout and immutable cache. This
bounded adapter preserves the older candidate, default release and private saves.
It exposes a new-game-only candidate; it does not approve any runtime or restore.
"""
from __future__ import annotations

import argparse
import ast
import codecs
from contextlib import ExitStack, redirect_stderr, redirect_stdout
import importlib
import json
import os
from pathlib import Path
import stat
import sys
from unittest.mock import patch

import prepare_current_sdk_play as base


PROJECT = Path(__file__).absolute().parents[1]
STAGE_ROOT = PROJECT / 'evidence/sdk_runtime_play/latest_pair_preparation'
STAGE = STAGE_ROOT / 'materialization'
SOURCE_RUN = '20261022T001546Z_7fba195072e4'
SOURCE_REQUEST_SHA = 'c47775cec96ae5fc762ebadf394d894fcd524e7314ed8428d52b5220028477e7'
SDK_REPORT = PROJECT / 'evidence/serialization/unit_great_work_save/sdk_2bdcdf80a1695780f864/result.json'
SDK_REPORT_SHA = '4b6310ce04dc6d1b155c406ac470b855682c2934eb03f6742ab1f065a6ef12ec'
HOST_BUILD = '20261024T021245Z_18bbd0dd26e7'
HOST_SHA = 'b96055dc020cec0bea86ad4e53f4335b2cad88694d27b56d63137bb4ff852aea'
RESTORE_HOST_BUILD = '20261024T042219Z_e6399c82ee5c'
RESTORE_STAGE_ROOT = PROJECT / 'evidence/native_restore_contract/pair_preparation'
WORLD_HUD_HOST_BUILD = '20261024T055841Z_974a5be57533'
WORLD_HUD_STAGE_ROOT = PROJECT / 'evidence/original_world_hud/pair_preparation'
HOVER_HOST_BUILD = '20261024T082423Z_b604cddf0d2d'
HOVER_STAGE_ROOT = PROJECT / 'evidence/original_world_hud/hover_repaint/pair_preparation'
MENU_STAGE_ROOT = PROJECT / 'evidence/game_menu/offline_menu_suite/pair_preparation'
EXPLICIT_MENU_STAGE_ROOT = PROJECT / 'evidence/game_menu/menu_runtime_ui_followup/pair_preparation'
SDK_SHA = '430f3122d0b555d6daae14aa7c011ef43ce8f978270477c8af596ca4b0493ab9'


def audit_python_support_closure(directory, inventory):
    """Resolve local imports from sealed sibling files, without importing them."""
    directory = Path(directory).absolute()
    base.require(type(inventory) is dict and inventory, 'Python support inventory is missing')
    checked, edges = {}, {}
    for name, reference in inventory.items():
        base.require(type(name) is str and Path(name).name == name and name.endswith('.py'),
                     'Python support must be a plain sibling module')
        row = reference.get('frozen', reference)
        base.require(base.key(row['path']) == base.key(directory / name),
                     'Python support path escaped its selected sibling directory')
        checked[name] = base.checked(row)
    names = {Path(name).stem: name for name in checked}
    for name, row in checked.items():
        tree = ast.parse(Path(row['path']).read_text(encoding='utf-8-sig'), filename=row['path'])
        imports = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(alias.name.split('.')[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                base.require(node.level == 0 and node.module, 'Relative Python support import requires an explicit package contract')
                imports.add(node.module.split('.')[0])
            elif isinstance(node, ast.Call):
                function = node.func
                base.require(not (isinstance(function, ast.Name) and function.id in ('__import__', 'exec', 'eval')) and
                             not (isinstance(function, ast.Attribute) and function.attr in
                                  ('import_module', 'spec_from_file_location', 'module_from_spec')),
                             'Dynamic Python support loading is outside the sealed import closure')
                base.require(not (isinstance(function, ast.Attribute) and isinstance(function.value, ast.Attribute) and
                                  isinstance(function.value.value, ast.Name) and function.value.value.id == 'sys' and
                                  function.value.attr == 'path'), 'Python support may not fall back to a live tools path')
        missing = sorted(module for module in imports if module not in names and module not in sys.stdlib_module_names)
        base.require(not missing, 'Python support has missing frozen modules: ' + ', '.join(missing))
        edges[name] = sorted(names[module] for module in imports if module in names)
    return dict(schema='zerosis.latest_pair.python_support_closure.v1', status='PASS_EXACT_SIBLING_PYTHON_SUPPORT_IMPORT_CLOSURE',
        module_count=len(checked), modules=checked, local_import_edges=edges, dynamic_imports=False,
        live_project_tools_fallback=False, imported_or_executed_modules=False, native_execution=False)


def audit_menu_data_bindings(prepared):
    """Check metadata roots without opening installed assets or loading a backend."""
    game = Path(r"C:\Program Files (x86)\Steam\steamapps\common\Sid Meier's Civilization V")
    originals = {}
    for name in ('MenuOptionsLayout', 'TouchHelpLayout', 'MapMenuLayout'):
        tree = prepared['xml_control_trees'][name]
        metadata = tree.get('menuOptions', tree.get('mapMenu'))
        base.require(type(metadata) is dict, 'Prepared private menu source metadata is missing')
        for field in ('originalLua', 'originalXml'):
            row = metadata[field]
            path = Path(row['path'])
            base.require(path.is_absolute() and path.is_relative_to(game / 'Assets/UI') and
                         isinstance(row.get('sha256'), str) and type(row.get('bytes')) is int and row['bytes'] > 0,
                         'Private menu original root no longer matches the retained renderer GAME root')
            originals[base.key(path)] = dict(row)
    font = prepared['font_input_profile']
    font_root = Path(font['asset_root'])
    header = Path(prepared['compiled_assets']['path'])
    base.require(header == PROJECT / 'Source/Host/UiPopupAssets.generated.h' and
                 font_root.parent == PROJECT / 'Build/SharedUiFontInputs' and
                 font.get('input_storage') == 'CONTENT_ADDRESSED_ENGINE_OWNED_FONT_INPUTS' and
                 len(font['original_inputs']) == 15 and
                 all(Path(row['path']).is_relative_to(font_root) for row in font['original_inputs']),
                 'Prepared font/header provenance was rewritten outside its original immutable cache contract')
    verified_fonts = [base.checked(row) for row in font['original_inputs']]
    return dict(schema='zerosis.latest_pair.private_menu_data_bindings.v1', original_ui_sources=len(originals),
        original_game_root=str(game), installed_originals_read_only=True, path_rewriting_required=False,
        source_tools_fallback=False, owned_font_input_count=15, owned_font_root=str(font_root),
        owned_font_inputs=verified_fonts, owned_font_inputs_verified=True,
        frozen_prepared_bindings_and_owned_cache_only=True, installed_assets_opened=False, native_execution=False)


class PairGuard(base.PreparationGuard):
    """Apply the existing preparation guard to exactly two new cache payloads."""
    def __init__(self, rows, sidecar=None):
        super().__init__()
        self.sidecar_rows = {}
        if sidecar is not None:
            for row in sidecar['files']:
                actual = base.checked(row['frozen'])
                info = Path(actual['path']).stat()
                base.require(getattr(info, 'st_file_attributes', 0) & base.READONLY, 'Required sidecar source is mutable')
                self.sidecar_rows[base.key(actual['path'])] = (row['relative_path'], actual, (info.st_dev, info.st_ino))
                self.cache_ids.add((info.st_dev, info.st_ino))
        self.new_payloads = {base.key(self.cache_root / row['sha256'][:2] / row['sha256']): row
                             for row in rows}
        base.require(len(self.new_payloads) == 2, 'Expected distinct new Host and SDK payloads')
        self.new_cache = Path(next(iter(self.new_payloads)))

    def audit(self, event, args):
        if event == 'os.link' and args:
            source, target = (Path(os.fsdecode(value)) for value in args[:2])
            row = self.sidecar_rows.get(base.key(source))
            if row is not None:
                self.check_read(event, source);self.check_read(event, target)
                relative, origin, identity = row
                expected = (self.parents[0] / self.run_id / 'UIFrontEnd' / relative) if self.run_id else None
                info = source.stat()
                if (expected is None or base.key(target) != base.key(expected) or os.path.lexists(target) or
                        (info.st_dev, info.st_ino) != identity or not getattr(info, 'st_file_attributes', 0) & base.READONLY):
                    self.fail(event, 'Required sidecar link escaped its exact new-runtime member')
                base.checked(origin)
                return
        # The inherited guard allows one content-addressed publication at a time.
        # Select only an attested Host/SDK shard for open/mkdir/atomic rename.
        file_events = {'open', 'os.mkdir', 'os.rename', 'os.replace', 'os.remove',
                       'os.chmod', 'os.utime', 'os.truncate'}
        candidate = ((args[1] if event in ('os.rename', 'os.replace') else args[0])
                     if event in file_events and args else None)
        if isinstance(candidate, (str, bytes, os.PathLike)):
            path = Path(os.fsdecode(candidate))
            for cache in self.new_payloads:
                if base.key(path) == cache or base.key(path) == base.key(Path(cache).parent) or (
                        base.key(path.parent) == base.key(Path(cache).parent)):
                    self.new_cache = Path(cache)
                    break
        return super().audit(event, args)


def recheck_protected_inputs(protected, host, menu_sources, host_spec=None):
    """Recheck compiler sources with their sealed checker, keeping base scope local."""
    menu_rows = ({base.key(row['path']): row for row in menu_sources['verified_inputs']}
                 if menu_sources is not None else {})
    for row in protected:
        expected = menu_rows.get(base.key(row['path']))
        if expected is None:
            base.checked(row)
        else:
            base.require(row['sha256'] == expected['sha256'] and
                         row.get('bytes', expected['bytes']) == expected['bytes'],
                         'Protected menu source differs from the sealed current-source inventory')
    if menu_sources is None:
        return None
    from retained_host_runtime_input import check_current_menu_host_sources
    current = check_current_menu_host_sources(host, PROJECT, host_spec)
    base.require(current == menu_sources, 'Menu current-source closure changed during preparation')
    return current


def freeze_menu_host_registration(request, host_spec, guard):
    """Keep the selected gate and registration beside the frozen generic gate."""
    import retained_host_runtime_input as retained
    helper = retained._menu_suite_helper()
    profile = host_spec.get('explicit_input_profile') or helper.registration_reference(host_spec['build_id'])
    destination = PROJECT / 'evidence/interactive_game' / guard.run_id
    references = request.get('provenance')
    base.require(isinstance(references, dict) and 'retained_host_runtime_input' in references,
                 'Prepared request lacks its frozen retained Host gate')
    result = {}
    for name, source, filename in (
            ('retained_menu_suite_host_input',
             dict(path=str(PROJECT / host_spec['helper_path']), sha256=host_spec['helper_sha256']),
             'retained_menu_suite_host_input.py'),
            ('retained_menu_suite_host_profile', profile, helper.FROZEN_PROFILE_NAME)):
        actual = base.checked(source)
        target = destination / filename
        base.require(not os.path.lexists(target), 'Inspect the existing frozen menu gate instead of replacing it')
        with Path(actual['path']).open('rb') as incoming, target.open('xb') as outgoing:
            for block in iter(lambda: incoming.read(1024 * 1024), b''):
                outgoing.write(block)
        frozen = base.checked(dict(path=str(target), bytes=actual['bytes'], sha256=actual['sha256']))
        references[name] = frozen
        result[name] = frozen
    return result


def main(argv=None):
    global STAGE
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--attempt', type=int, choices=range(10), default=0)
    selected = parser.add_mutually_exclusive_group()
    selected.add_argument('--host-input-profile', type=Path, help='Prepare a hash-pinned menu Host without global registration')
    parser.add_argument('--host-input-profile-sha256', help='Expected SHA-256 of that preparation-only profile')
    selected.add_argument('--restore-contract-host', action='store_true',
                          help='Prepare the retained restore-contract Host without execution')
    selected.add_argument('--original-world-hud-host', action='store_true',
                          help='Prepare the current linked original-world-HUD Host without execution')
    selected.add_argument('--hud-hover-repaint-host', action='store_true',
                          help='Prepare the attested HUD-hover Host without execution')
    selected.add_argument('--exit-confirm-host', action='store_true',
                          help='Prepare the registered ExitConfirm Host after an actual-source recheck')
    selected.add_argument('--menu-suite-host', action='store_true',
                          help='Prepare only the finally attested integrated menu Host without execution')
    args = parser.parse_args(argv)
    base.require(not sys.flags.optimize, 'Run the bounded preparation without Python optimization')
    base.require(bool(args.host_input_profile) == bool(args.host_input_profile_sha256),
                 '--host-input-profile and --host-input-profile-sha256 must be supplied together')
    host_spec = None
    if args.host_input_profile:
        from retained_host_runtime_input import explicit_host_input_spec
        host_spec = explicit_host_input_spec(PROJECT,
            dict(path=str(args.host_input_profile.absolute()), sha256=args.host_input_profile_sha256))
        selected_build = host_spec['build_id']
        stage_root = EXPLICIT_MENU_STAGE_ROOT / selected_build
    elif args.menu_suite_host:
        import retained_host_runtime_input as retained
        selected_build = retained.MENU_SUITE_BUILD_ID
        base.require(selected_build is not None, 'The final menu-suite Host has not been byte-attested and registered')
        stage_root = MENU_STAGE_ROOT
    elif args.exit_confirm_host:
        import retained_host_runtime_input as retained
        stage_root, selected_build = MENU_STAGE_ROOT, retained._menu_suite_helper().EXIT_BUILD_ID
    elif args.hud_hover_repaint_host:
        stage_root, selected_build = HOVER_STAGE_ROOT, HOVER_HOST_BUILD
    elif args.original_world_hud_host:
        stage_root, selected_build = WORLD_HUD_STAGE_ROOT, WORLD_HUD_HOST_BUILD
    elif args.restore_contract_host:
        stage_root, selected_build = RESTORE_STAGE_ROOT, RESTORE_HOST_BUILD
    else:
        stage_root, selected_build = STAGE_ROOT, HOST_BUILD
    from retained_host_runtime_input import registered_host_spec
    host_spec = host_spec or registered_host_spec(selected_build)
    base.require(host_spec is not None and host_spec['build_id'] == selected_build,
                 'Selected Host is not registered for retained-input validation')
    STAGE = stage_root / ('materialization' if args.attempt == 0 else f'materialization_retry{args.attempt:02d}')
    if args.attempt:
        previous = stage_root / ('materialization' if args.attempt == 1 else f'materialization_retry{args.attempt-1:02d}')
        failure = base.read(previous / 'failure.json')
        base.require(failure['status'] == 'FAILED_PREPARATION_ONLY' and failure['native_attempts'] == 0
                     and failure['denied'] == [],
                     'Retry requires the preserved preparation-only failure')
    base.require(not STAGE.exists(), 'Inspect the existing materialization instead of repeating it')
    sys.dont_write_bytecode = True
    # Initialize lazy encodings before adding the read/write audit boundary.
    for encoding in ('utf-8', 'utf-8-sig', 'ascii', 'mbcs', 'cp1252'):
        codecs.lookup(encoding)
        'x'.encode(encoding).decode(encoding)
    source_path = PROJECT / f'evidence/interactive_game/{SOURCE_RUN}/request.json'
    source_ref = base.checked(dict(path=str(source_path), sha256=SOURCE_REQUEST_SHA))
    source = base.read(source_path)
    host_path = PROJECT / host_spec['report_path']
    host_ref = base.checked(dict(path=str(host_path), sha256=host_spec['report_sha256']))
    host = base.read(host_path)
    sdk_ref = base.checked(dict(path=str(SDK_REPORT), sha256=SDK_REPORT_SHA))
    host_payload = base.checked(host['executable'])
    sdk_payload = base.checked(dict(path=str(PROJECT /
        'Build/UnitGreatWorkSaveSDK/2bdcdf80a1695780f864/CvGameCoreDLL_Expansion2_x64.dll'), sha256=SDK_SHA))
    base.require(host_payload['sha256'] == host_spec['executable_sha256'], 'Unexpected Host payload')
    menu_sources = None
    if host_spec['kind'] == 'retained_menu_suite':
        from retained_host_runtime_input import check_current_menu_host_sources, validate_retained_host_runtime
        # Validate immutable evidence, then actual sources. Neither one substitutes
        # for the other and no materialization has occurred at this point.
        validate_retained_host_runtime(host, PROJECT, host_spec)
        menu_sources = check_current_menu_host_sources(host, PROJECT, host_spec)
    source_support_audit = audit_python_support_closure(PROJECT / 'tools',
        {name: base.artifact(PROJECT / 'tools' / name) for name in base.TOOLS})
    old_rows = {Path(row['path']).name: row for row in source['runtime_inputs']}
    base.require(len(old_rows) == 24 and source['smoke'] is False and source['resume_from'] is None,
                 'Unexpected source preparation profile')
    protected = [source_ref, host_ref, sdk_ref, host_payload, sdk_payload]
    if menu_sources is not None:
        protected.extend(menu_sources['verified_inputs'])
    protected.extend(base.checked(row) for row in old_rows.values())
    for relative in ('Play/EarlyAccess/release.json', 'tools/Start-Engine.ps1',
                     'evidence/goody_hut/runtime_fonts/system_freeze_hold.json'):
        protected.append(base.artifact(PROJECT / relative))
    protected.extend(base.source_closure([
        Path(__file__).absolute(), PROJECT / 'tools/run_interactive_game.py',
        PROJECT / 'tools/retained_host_runtime_input.py', PROJECT / 'tools/current_runtime_sdk_input.py',
        *([PROJECT / 'tools/retained_world_hud_host_input.py'] if args.original_world_hud_host else []),
        *([PROJECT / 'tools/retained_hover_repaint_host_input.py'] if args.hud_hover_repaint_host else []),
        *([PROJECT / 'tools/retained_menu_suite_host_input.py'] if menu_sources is not None else []),
        *(PROJECT / 'tools' / name for name in base.TOOLS),
        PROJECT / 'tools/sealed_terrain_input.py']))
    protected.extend(base.artifact(PROJECT / relative) for relative in (
        'evidence/concurrency/runtime_configuration/PolicyInfo.ini',
        'evidence/ui_popup/assets/inline_icons.json', 'evidence/ui_popup/assets/prepared.json'))
    operational_revisions = None
    if args.restore_contract_host or args.original_world_hud_host or args.hud_hover_repaint_host:
        operational_revisions = base.artifact(stage_root / 'operational_revisions.json')
        protected.append(operational_revisions)
    if menu_sources is not None:
        import retained_host_runtime_input as retained
        protected.append(base.checked(host_spec.get('explicit_input_profile') or retained._menu_suite_helper().registration_reference(selected_build)))
        if 'required_sidecar' in host_spec:
            sidecar = host_spec['required_sidecar']
            protected.append(base.checked(sidecar['manifest']))
            protected.extend(base.checked(row[name]) for row in sidecar['files'] for name in ('source', 'frozen'))
    identity = base.read(base.IDENTITY)
    base.checked(dict(path=str(base.IDENTITY), sha256=base.IDENTITY_SHA))
    guard = PairGuard([host_payload, sdk_payload], host_spec.get('required_sidecar'))
    # Start from the exact retained cache aliases, including the older pair.
    for row in identity['immutable_cache_links']:
        cache, target = base.checked(row['cache']), base.checked(row['target'])
        left, right = Path(cache['path']).stat(), Path(target['path']).stat()
        base.require((left.st_dev, left.st_ino) == (right.st_dev, right.st_ino) and
                     getattr(left, 'st_file_attributes', 0) & base.READONLY, 'Retained cache alias changed')
        guard.cache_rows[base.key(cache['path'])] = cache
        guard.cache_ids.add((left.st_dev, left.st_ino))
    for path, row in guard.new_payloads.items():
        if os.path.lexists(path):
            cache = base.checked(dict(path=path, sha256=row['sha256'], bytes=row['bytes']))
            info = Path(path).stat()
            base.require(getattr(info, 'st_file_attributes', 0) & base.READONLY, 'Existing pair cache is mutable')
            guard.cache_rows[path] = cache
            guard.cache_ids.add((info.st_dev, info.st_ino))
    protected.extend(guard.cache_rows.values())
    base.STAGE = STAGE
    sys.addaudithook(guard.audit)
    STAGE.mkdir(exist_ok=False)
    policy = PROJECT / 'evidence/concurrency/runtime_configuration/PolicyInfo.ini'
    unit_manifest = PROJECT / ('Build/UnitAssets/'
        'fbb3b9ec4b43242cbee022b9cdf712f37ccbdf6290015ee2ee27b6547a570573/unit-assets.manifest.json')
    arguments = [str(PROJECT / 'tools/run_interactive_game.py'), '--host-build', str(host_path),
        '--runtime-sdk-build', str(SDK_REPORT), '--runtime-sdk-build-sha256', SDK_REPORT_SHA,
        '--terrain-assets-from-run', SOURCE_RUN, '--unit-assets-manifest', str(unit_manifest),
        '--policy-info-settings', str(policy), '--found-value-workers', 'auto', '--language', 'ko_KR',
        '--top-panel', '--action-info-panel', '--notification-panel', '--timeout', '300']
    if args.host_input_profile:
        arguments += ['--host-input-profile', str(args.host_input_profile.absolute()),
                      '--host-input-profile-sha256', args.host_input_profile_sha256]
    base.write_new(STAGE / 'started.json', dict(schema='zerosis.latest_pair.preparation_started.v1',
        host=host_ref, sdk=sdk_ref, source_request=source_ref, runner_argv=arguments,
        host_build_id=selected_build, operational_revisions=operational_revisions,
        actual_menu_source_closure_rechecked=menu_sources is not None,
        source_python_support_audit=source_support_audit,
        protected_inputs=protected, native_execution_allowed=False, default_promotion_allowed=False))
    stdout, stderr = base.Capture(), base.Capture()
    original_argv = sys.argv[:]
    try:
        with ExitStack() as stack:
            stack.enter_context(patch.object(os, 'stat', guard.guarded_stat))
            stack.enter_context(patch.object(os, 'lstat', guard.guarded_lstat))
            stack.enter_context(patch.object(os, 'access', guard.guarded_access))
            runner = importlib.import_module('run_interactive_game')
            sys.argv = arguments
            with redirect_stdout(stdout), redirect_stderr(stderr):
                code = runner.main()
            base.require(code in (None, 0), 'Production preparation returned failure')
    except BaseException as error:
        base.write_new(STAGE / 'failure.json', dict(status='FAILED_PREPARATION_ONLY',
            error=type(error).__name__ + ': ' + str(error), run_id=guard.run_id,
            denied=guard.denied, native_attempts=guard.native_attempts))
        raise
    finally:
        sys.argv[:] = original_argv
        for name, capture in (('stdout.log', stdout), ('stderr.log', stderr)):
            with (STAGE / name).open('x', encoding='utf8') as stream:
                stream.write(capture.getvalue())
    try:
        summaries = [json.loads(line) for line in stdout.getvalue().splitlines() if line.startswith('{')]
        base.require(len(summaries) == 1 and summaries[0]['status'] == 'PRIVATE_CONTINUOUS_GAME_PREPARED'
                     and summaries[0]['run_id'] == guard.run_id, 'No unique production preparation result')
        request_path = PROJECT / f'evidence/interactive_game/{guard.run_id}/request.json'
        request = base.read(request_path)
        frozen_inventory = request['interactive_ui_support_inventory']
        frozen_support_audit = audit_python_support_closure(
            PROJECT / 'Build/InteractiveGameRuntime' / guard.run_id / 'interactive_ui_support/tools',
            frozen_inventory['tools'])
        base.require(set(source_support_audit['modules']) == set(frozen_support_audit['modules']) and
                     all(source_support_audit['modules'][name]['sha256'] == frozen_support_audit['modules'][name]['sha256']
                         for name in source_support_audit['modules']), 'Frozen Python support differs from its actual source import closure')
        request['frozen_python_support_import_closure'] = frozen_support_audit
        frozen_menu_registration = None
        required_sidecar_validation = None
        if menu_sources is not None:
            frozen_prepared = base.read(Path(frozen_inventory['asset_preparation_provenance']['frozen']['path']))
            if all(name in frozen_prepared['xml_control_trees'] for name in ('MenuOptionsLayout', 'TouchHelpLayout', 'MapMenuLayout')):
                request['private_menu_data_bindings'] = audit_menu_data_bindings(frozen_prepared)
            frozen_menu_registration = freeze_menu_host_registration(request, host_spec, guard)
            if 'required_sidecar' in host_spec:
                from retained_host_runtime_input import _Files, _menu_suite_helper
                required_sidecar_validation = _menu_suite_helper().verify_runtime_required_sidecars(
                    PROJECT, selected_build, host_spec['required_sidecar'],
                    PROJECT / 'Build/InteractiveGameRuntime' / guard.run_id,
                    request['required_host_sidecars'], _Files(check_metadata=True))
                base.require(required_sidecar_validation == request['required_host_sidecar_validation'],
                             'Runtime required sidecar verification changed after production preparation')
            request['menu_host_preparation_scope'] = dict(
                actual_current_source_closure_verified=True, verified_source_count=menu_sources['source_count'],
                frozen_host_registration=frozen_menu_registration, native_execution=False,
                new_game_only=True, cross_bundle_load_allowed=False, default_promoted=False)
        # This request was generated in the fresh preparation and has not been
        # published. Preserve its additional provenance before sealing its hash.
        with request_path.open('w', encoding='utf-8') as stream:
            stream.write(json.dumps(request, ensure_ascii=False, indent=2) + '\n')
        current = {Path(row['path']).name: row for row in request['runtime_inputs']}
        base.require(len(current) == 24 and current.keys() == old_rows.keys(), 'Runtime input name set changed')
        changed = {name for name in current if current[name]['sha256'] != old_rows[name]['sha256']}
        base.require(changed == {'ZeroSisHost_x64.exe', 'CvGameCoreDLL_Expansion2_x64.dll', 'bundle.manifest'} and
                     current['ZeroSisHost_x64.exe']['sha256'] == host_spec['executable_sha256'] and
                     current['CvGameCoreDLL_Expansion2_x64.dll']['sha256'] == SDK_SHA, 'Runtime payload pair differs')
        for row in current.values():
            base.checked(row)
        scope = request['runtime_sdk_candidate_scope']
        base.require(scope['new_game_only'] is True and scope['host_sdk_execution_verified'] is False and
                     request['smoke'] is False and request['resume_from'] is None and
                     request['stage_or_mods_changed'] is False, 'Candidate claims execution or migration')
        base.require("throw 'Save loading is disabled" in Path(request['resume_launcher']['path']).read_text(
            encoding='utf-8-sig'), 'Candidate exposes an older bundle restore')
        final_menu_sources = recheck_protected_inputs(protected, host, menu_sources, host_spec)
        base.require(not guard.denied and guard.native_attempts == 0, 'Preparation crossed its execution boundary')
        methods = request['materializations']
        result = dict(schema='zerosis.latest_pair.prepared.v1', status='PASS_CURRENT_HOST_AND_GREAT_WORK_SDK_PREPARED_NOT_EXECUTED',
            request=base.artifact(request_path), run_id=guard.run_id, host=base.checked(current['ZeroSisHost_x64.exe']),
            host_build_id=selected_build, operational_revisions=operational_revisions,
            actual_menu_source_closure_rechecked=menu_sources is not None,
            final_current_source_count=final_menu_sources['source_count'] if final_menu_sources else None,
            frozen_menu_registration=frozen_menu_registration,
            explicit_host_input_profile=host_spec.get('explicit_input_profile'),
            required_sidecar_validation=required_sidecar_validation,
            sidecar_files=(required_sidecar_validation['file_count'] if required_sidecar_validation else 0),
            frozen_python_support_import_closure=frozen_support_audit,
            gamecore=base.checked(current['CvGameCoreDLL_Expansion2_x64.dll']),
            bundle_manifest=base.checked(current['bundle.manifest']), changed_backend_inputs=sorted(changed),
            runtime_input_count=len(current), immutable_links=sum(r.get('materialization_method') == 'hardlink' for r in methods),
            cache_created=sorted(guard.created_cache), protected_inputs_unchanged=len(protected),
            guard_denials=[], native_attempts=0, new_game_only=True, host_or_sdk_executed=False,
            current_original_world_hud_included=args.original_world_hud_host or args.hud_hover_repaint_host,
            current_hover_repaint_included=args.hud_hover_repaint_host,
            save_compatibility_verified=False, prior_bundle_migrated=False, default_promoted=False,
            original_ui_accepted=False, full_engine_goal_complete=False)
        base.write_new(STAGE / 'result.json', result)
        print(json.dumps(dict(status=result['status'], run_id=guard.run_id, result=str(STAGE / 'result.json'))))
        return 0
    except BaseException as error:
        base.write_new(STAGE / 'failure.json', dict(status='FAILED_PREPARATION_ONLY',
            error=type(error).__name__ + ': ' + str(error), run_id=guard.run_id,
            failed_phase='POST_MATERIALIZATION_VALIDATION', denied=guard.denied,
            native_attempts=guard.native_attempts))
        raise


if __name__ == '__main__':
    raise SystemExit(main())
