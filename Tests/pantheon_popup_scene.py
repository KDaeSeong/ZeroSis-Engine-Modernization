"""Exercise original BNW pantheon callbacks in the production retained Lua UI.

Only the sealed pure Lua 5.1 component DLL may be loaded. Native SDK mutation,
faith, notification expiration, windows and full-game acceptance are unverified.
"""
from __future__ import annotations

from contextlib import ExitStack
import argparse
import ctypes
import hashlib
import importlib
import json
import os
from pathlib import Path
import re
import stat
import sys
import tempfile
from unittest.mock import patch
import xml.etree.ElementTree as ET

sys.dont_write_bytecode = True
PROJECT = Path(__file__).absolute().parents[1]
STAGE = PROJECT / 'evidence/religion/pantheon_source'
SCOPE = STAGE / 'scope.json'
SCOPE_SHA = '726ee93659a55a695b33bcbfb44b9c7ab12454e8a68b1f967e9e52bbbfce70cf'
LUA_SHA = '4873cded3ddf52366abc7964e3d3e10546f88e983d966be93bce3465ef85d944'
SOURCE_PATHS = {'scene': 'Source/Host/UiScene.lua',
                'input': 'Source/Presentation/UiPresentationInput.lua',
                'preparer': 'tools/prepare_ui_popup_assets.py',
                'pixel': 'tools/ui_pixel_scene.py',
                'sdk_popup_enums': 'Source/SDK_BNW_x64/CvGameCoreDLLUtil/include/CvEnums.h',
                'tests': 'Tests/pantheon_popup_scene.py',
                'cases': 'Tests/pantheon_command_guard.lua'}


def require(value, message):
    if not value:
        raise RuntimeError(message)


def key(path):
    return os.path.normcase(os.path.abspath(path))


def artifact(path):
    path = Path(os.path.abspath(path))
    for parent in (path, *path.parents):
        info = parent.lstat()
        require(not stat.S_ISLNK(info.st_mode) and not getattr(info, 'st_file_attributes', 0) & 0x400,
                'A component input contains a reparse point')
        if parent.parent == parent:
            break
    before = path.stat()
    identity = lambda row: (row.st_dev, row.st_ino, row.st_size, row.st_mtime_ns)
    require(stat.S_ISREG(before.st_mode), 'Expected an ordinary component input')
    with path.open('rb') as stream:
        require(identity(os.fstat(stream.fileno())) == identity(before), 'Input changed while opening')
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
        require(identity(os.fstat(stream.fileno())) == identity(before), 'Input changed while reading')
    require(identity(path.stat()) == identity(before), 'Input path changed while reading')
    return {'path': str(path), 'bytes': before.st_size, 'sha256': digest}


def sealed(row):
    observed = artifact(row['path'])
    require(observed == row, 'Sealed component input changed: ' + row['path'])
    return observed


def execute_lua(source, library):
    require(artifact(library)['sha256'] == LUA_SHA, 'Pure Lua component DLL changed')
    lua = ctypes.CDLL(str(library))
    lua.luaL_newstate.argtypes, lua.luaL_newstate.restype = [], ctypes.c_void_p
    lua.luaL_openlibs.argtypes, lua.luaL_openlibs.restype = [ctypes.c_void_p], None
    lua.luaL_loadbuffer.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_size_t, ctypes.c_char_p]
    lua.luaL_loadbuffer.restype = ctypes.c_int
    lua.lua_pcall.argtypes, lua.lua_pcall.restype = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_int], ctypes.c_int
    lua.lua_tolstring.argtypes, lua.lua_tolstring.restype = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p], ctypes.c_char_p
    lua.lua_close.argtypes, lua.lua_close.restype = [ctypes.c_void_p], None
    state = lua.luaL_newstate()
    require(state, 'Cannot create the isolated Lua component state')
    try:
        lua.luaL_openlibs(state)
        data = source.encode('utf-8')
        status = lua.luaL_loadbuffer(state, data, len(data), b'@Pantheon-original-component.lua')
        if not status:
            status = lua.lua_pcall(state, 0, 1, 0)
        message = lua.lua_tolstring(state, -1, None)
        require(not status and message, 'Original pantheon component failed: ' +
                (message.decode('utf-8', errors='replace') if message else 'no returned JSON'))
        require(len(message) <= 8 * 1024 * 1024, 'Component report exceeds its bound')
        return json.loads(message.decode('utf-8'))
    finally:
        lua.lua_close(state)


def verify_component(output=None):
    if output is not None:
        output = Path(os.path.abspath(output))
        require(output.parent == STAGE and not os.path.lexists(output), 'Use a fresh report in the scoped stage')
    scope_ref = artifact(SCOPE)
    require(scope_ref['sha256'] == SCOPE_SHA, 'Reviewed pantheon scope changed')
    scope = json.loads(SCOPE.read_text(encoding='utf-8-sig'))
    require(scope['schema'] == 'zerosis.pantheon_source.scope.v1', 'Unexpected pantheon scope')
    originals = [sealed(row) for row in scope['original_assets']]
    require(len(originals) == 2 and [Path(row['path']).suffix.lower() for row in originals] == ['.lua', '.xml'],
            'Expected the exact original BNW Lua/XML pair')
    library = Path(scope['headless_lua_provider']['path'])
    require(sealed(scope['headless_lua_provider'])['sha256'] == LUA_SHA and
            key(library) == key(PROJECT / 'Build/SharedLuaRuntime/Lua/ZeroSisLua51_x64.dll'),
            'Only the reviewed pure Lua provider is permitted')
    sources = {name: artifact(PROJECT / relative) for name, relative in SOURCE_PATHS.items()}
    denied, roots, removed, dll_loads = [], {}, [], []
    retail = key(r"C:\Users\home\OneDrive\Documents\My Games\Sid Meier's Civilization 5")

    def owned(path):
        value = key(path)
        return any(value == root or value.startswith(root + os.sep) for root in roots)

    def audit(event, arguments):
        if event in ('open', 'os.listdir', 'os.scandir') and arguments and isinstance(arguments[0], (str, bytes, os.PathLike)):
            target = key(os.fsdecode(arguments[0]))
            if target.startswith('\\\\?\\'):
                target = target[4:]
            if target == retail or target.startswith(retail + os.sep):
                denied.append(event)
                raise RuntimeError('Retail MODS, saves and settings are forbidden')
            if event == 'open':
                mode, flags = arguments[1:3]
                writing = (isinstance(mode, str) and any(c in mode for c in 'wax+')) or (
                    type(flags) is int and flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND))
                if writing and not owned(target) and (output is None or target != key(output)):
                    denied.append('write-outside-owned-fixture')
                    raise RuntimeError('Component writes must remain in its new private fixture directory')
        if event in ('os.remove', 'os.rmdir') and arguments:
            require(owned(arguments[0]), 'Refusing cleanup outside the owned fixture')
        if event == 'ctypes.dlopen':
            if not arguments or not isinstance(arguments[0], (str, bytes, os.PathLike)) or key(os.fsdecode(arguments[0])) != key(library):
                denied.append(event)
                raise RuntimeError('A non-component native library load was attempted')
            dll_loads.append(str(library))
        if event in ('subprocess.Popen', 'os.system', 'os.startfile', 'os.startfile/2', 'os.exec', 'os.spawn', 'os.posix_spawn'):
            denied.append(event)
            raise RuntimeError('Actual process/game execution is forbidden')

    sys.addaudithook(audit)
    with ExitStack() as stack:
        blocked = [stack.enter_context(patch(name, side_effect=RuntimeError('Execution forbidden: ' + name)))
                   for name in ('subprocess.Popen', 'os.startfile')]
        stack.enter_context(patch.object(sys, 'path', [str(PROJECT / 'tools'), *sys.path]))
        preparation = importlib.import_module('prepare_ui_popup_assets')
        pixel = importlib.import_module('ui_pixel_scene')
        require(key(preparation.__file__) == key(sources['preparer']['path']) and
                key(pixel.__file__) == key(sources['pixel']['path']), 'Imported a different production UI tool')
        enum_source = Path(sources['sdk_popup_enums']['path']).read_text(encoding='cp1252')
        match = re.search(r'\benum\s+ButtonPopupTypes\s*\{([^}]+)\}\s*;', enum_source, re.S)
        require(match is not None, 'Original SDK popup enum is missing')
        enum_body = re.sub(r'/\*.*?\*/|//[^\r\n]*', '', match.group(1), flags=re.S)
        enum_names = [item.strip() for item in enum_body.split(',') if item.strip()]
        require(enum_names and len(enum_names) == len(set(enum_names)) and
                all(re.fullmatch(r'BUTTONPOPUP_[A-Z0-9_]+|NUM_FIXED_BUTTONPOPUP_TYPES', item) for item in enum_names),
                'The scoped SDK popup enum is no longer a plain sequential declaration')
        popup_types = {name: value for value, name in enumerate(enum_names)}
        require('BUTTONPOPUP_FOUND_PANTHEON' in popup_types, 'SDK popup enum lacks original Pantheon type')
        paths = {'scene': PROJECT / SOURCE_PATHS['scene'], 'input': PROJECT / SOURCE_PATHS['input'],
                 'stock': Path(originals[0]['path']),
                 'IconSupport': PROJECT / 'Source/Assets/UI/Assets/UI/IconSupport.lua',
                 'InstanceManager': PROJECT / 'Source/Assets/UI/Assets/UI/InstanceManager.lua',
                 'FLuaVector': PROJECT / 'Source/Assets/UI/Assets/Gameplay/Lua/FLuaVector.lua'}
        include_refs = [artifact(paths[name]) for name in ('IconSupport', 'InstanceManager', 'FLuaVector')]
        text = {name: path.read_text(encoding='utf-8-sig') for name, path in paths.items()}
        tree = preparation.pantheon_control_tree(ET.parse(originals[1]['path']).getroot())
        tree.update(contextName='ChoosePantheonPopup', popupKind='Pantheon')
        production_refs = preparation.pantheon_original_sources()
        require(production_refs == {'lua': originals[0], 'xml': originals[1]},
                'Production Pantheon source metadata differs from the sealed original pair')
        # The production preparer main attaches this exact metadata after its
        # tree builder; reuse its source binder without materializing all UI.
        tree['pantheon'] = {'policy': 'ORIGINAL_BNW_PANTHEON_ONLY_V1',
            'originalLayoutLua': production_refs['lua'], 'originalLayoutXml': production_refs['xml'],
            'rowTemplate': 'ItemInstance', 'reformationSupported': False, 'nativeAcceptanceVerified': False}
        require(tree['pantheon']['reformationSupported'] is False and tree['pantheon']['nativeAcceptanceVerified'] is False,
                'Production layout overstated pantheon scope')
        inline = json.loads((PROJECT / 'evidence/ui_popup/assets/inline_icons.json').read_text(encoding='utf-8-sig'))['icons']
        temporary = tempfile.TemporaryDirectory(prefix='pantheon-component-', dir=PROJECT / 'Tests')
        root = Path(temporary.name).absolute()
        info = root.lstat()
        require(root.parent == PROJECT / 'Tests' and stat.S_ISDIR(info.st_mode) and not info.st_file_attributes & 0x400,
                'Component temporary root is not newly owned and ordinary')
        roots[key(root)] = (info.st_dev, info.st_ino)
        try:
            styles = preparation.production_style_defaults(root, tree)
            tree.update(styleDefaults=styles['controls'], styleDefaultsSource=styles['source'], styleDefaultsPolicy=styles['policy'])
            tree['fontMetrics'] = preparation.production_font_metrics(tree, inline)
            harness = (PROJECT / SOURCE_PATHS['cases']).read_text(encoding='utf-8')
            source = (harness.replace('@@SOURCES@@', preparation.lua_value(text))
                      .replace('@@LAYOUT@@', preparation.lua_value(tree))
                      .replace('@@POPUP_TYPES@@', preparation.lua_value(popup_types)))
            require(all(marker not in source for marker in ('@@SOURCES@@', '@@LAYOUT@@', '@@POPUP_TYPES@@')),
                    'Unresolved component fixture input')
            report = execute_lua(source, library)
            snapshots = report.pop('snapshots')
            require(type(snapshots) is dict and set(snapshots) == {'list', 'confirmation', 'closed'},
                    'Missing actual original popup lifecycle snapshots')
            pixel_proofs = {}
            for name, snapshot in snapshots.items():
                pixel_proofs[name] = pixel.pantheon_controls_contract(snapshot, closed=name == 'closed')
            report['production_pixel_contracts'] = pixel_proofs
        finally:
            current = root.lstat()
            require((current.st_dev, current.st_ino) == roots[key(root)] and not current.st_file_attributes & 0x400,
                    'Owned temporary root identity changed before cleanup')
            for parent, dirs, files in os.walk(root, followlinks=False):
                for name in dirs:
                    require(not (Path(parent) / name).lstat().st_file_attributes & 0x400, 'Reparse directory in own fixture')
                for name in files:
                    row = artifact(Path(parent) / name)
                    removed.append({**row, 'result': 'OWNED_TEMPORARY_REMOVED'})
            temporary.cleanup()
        require(not os.path.lexists(root) and not denied and all(call.call_count == 0 for call in blocked) and
                dll_loads == [str(library)], 'Component cleanup or execution guard failed')
        for row in [scope_ref, *sources.values(), *originals, *include_refs, scope['headless_lua_provider']]:
            sealed(row)
        report.update(schema='zerosis.pantheon.original_popup_headless_component.v1',
            status='PASS_ORIGINAL_PANTHEON_POPUP_HEADLESS_COMPONENT', scope=scope_ref,
            source_inputs=sources, original_inputs=originals, include_inputs=include_refs,
            popup_enum_source=sources['sdk_popup_enums'], popup_enum_derivation='SOURCE_SEQUENTIAL_ENUM_ORDER',
            found_pantheon_popup_type=popup_types['BUTTONPOPUP_FOUND_PANTHEON'], sdk_runtime_enum_binding_verified=False,
            sources_unchanged=True, original_assets_unchanged=True, pure_lua_provider=scope['headless_lua_provider'],
            permitted_component_dll_loads=dll_loads, forbidden_access_attempts=denied,
            owned_temporary_roots=[str(root)], owned_temporary_artifacts=removed, owned_scratch_cleaned=True,
            actual_host_processes=0, host_executed=False, gamecore_loaded=False, hwnd_created=False,
            retail_user_state_accessed=False, game_process_queries=0, live_sdk_pantheon_commit_verified=False,
            live_sdk_faith_belief_rng_verified=False, live_sdk_notification_expiration_verified=False,
            native_pixels_verified=False, full_game_acceptance=False)
        return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    result = verify_component(args.output)
    if args.output is not None:
        with args.output.open('x', encoding='utf-8') as stream:
            json.dump(result, stream, ensure_ascii=False, indent=2)
            stream.write('\n');stream.flush();os.fsync(stream.fileno())
        print(json.dumps({'status': result['status'], 'checks': result['checks'],
                          'cases': len(result['cases']), 'report': artifact(args.output)}, ensure_ascii=False))
    else:
        print(json.dumps(result, ensure_ascii=False))
