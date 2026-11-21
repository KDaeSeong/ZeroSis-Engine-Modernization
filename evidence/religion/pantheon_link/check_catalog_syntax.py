"""Parse the generated source catalog with the sealed Lua 5.1 parser only."""
from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys


PROJECT = Path(r"C:\Users\home\OneDrive\Documents\Firaxis ModBuddy\ZeroSis' Engine Modernization")
STAGE = PROJECT / 'evidence/religion/pantheon_link'
SCOPE = STAGE / 'scope.json'
SCOPE_BYTES = 161661
SCOPE_SHA = '747c8710329e4b2a3a3905dc90b88ce9b9e2f106a0eed0c9ac918f35e6c0f99a'
HEADER = PROJECT / 'Source/Host/UiPopupAssets.generated.h'
LUA_BYTES = 166912
LUA_SHA = '4873cded3ddf52366abc7964e3d3e10546f88e983d966be93bce3465ef85d944'
MAX_HEADER = 128 * 1024 * 1024
MAX_SCRIPT = 32 * 1024 * 1024
ADDENDA = (
    ('hasRetainedCityUi', 'Source/Presentation/UiCityView.lua'),
    ('hasRetainedUnitUi', 'Source/Presentation/UiUnitPanel.lua'),
    ('hasRetainedSocialPolicyUi', 'Source/Presentation/UiSocialPolicy.lua'),
    ('hasRetainedEconomicUi', 'Source/Presentation/UiEconomicOverview.lua'),
    ('hasRetainedActionInfoUi', 'Source/Presentation/UiActionInfoPanel.lua'),
    ('hasRetainedNotificationUi', 'Source/Presentation/UiNotificationPanel.lua'),
)
RETAIL_USER_ROOTS = (
    r'C:\Users\home\OneDrive\Documents\My Games',
    r'C:\Users\home\Documents\My Games',
)


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def key(path):
    return os.path.normcase(os.path.abspath(os.fspath(path)))


def within(path, root):
    value, parent = key(path), key(root)
    return value == parent or value.startswith(parent + os.sep)


def ordinary(path):
    path = Path(path)
    info = path.lstat()
    require(stat.S_ISREG(info.st_mode) and not (getattr(info, 'st_file_attributes', 0) & 0x400),
            'Input must be an ordinary non-reparse file')
    return info


def artifact(path, limit=MAX_HEADER):
    path = Path(path).absolute()
    before = ordinary(path)
    require(0 <= before.st_size <= limit, 'Input exceeds its bounded size')
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    after = ordinary(path)
    require((before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) ==
            (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns), 'Input changed while hashing')
    return {'path': str(path), 'bytes': before.st_size, 'sha256': digest.hexdigest()}


def sealed(row, limit=MAX_HEADER):
    require(type(row) is dict and set(row) == {'path', 'bytes', 'sha256'} and
            type(row['path']) is str and type(row['bytes']) is int and
            re.fullmatch('[0-9a-f]{64}', row['sha256']) is not None, 'Malformed artifact identity')
    result = artifact(row['path'], limit)
    require(key(result['path']) == key(row['path']) and result['bytes'] == row['bytes'] and
            result['sha256'] == row['sha256'], 'Sealed artifact identity changed')
    return result


def read_json(path, limit=2 * 1024 * 1024):
    require(ordinary(path).st_size <= limit, 'JSON exceeds its bounded size')
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def install_guard(output):
    counts = {'explicit_lua_provider_loads': 0, 'blocked_process_attempts': 0,
              'blocked_retail_attempts': 0, 'blocked_write_attempts': 0, 'blocked_dll_attempts': 0,
              'blocked_read_attempts': 0}
    allowed_dll = {'path': None, 'read_paths': {key(SCOPE), key(HEADER), key(Path(__file__))},
                   'resolved_parser_functions': set()}

    def guard(event, args):
        if event.startswith(('subprocess.', 'os.exec', 'os.spawn')) or event in (
                'os.system', 'os.fork', 'os.forkpty', 'os.startfile', 'os.posix_spawn', 'os.posix_spawnp'):
            counts['blocked_process_attempts'] += 1
            raise PermissionError('Additional processes are forbidden')
        if event == 'ctypes.dlopen':
            name = args[0] if args else None
            if not isinstance(name, (str, bytes, os.PathLike)) or allowed_dll['path'] is None or \
                    key(os.fsdecode(name)) != allowed_dll['path'] or counts['explicit_lua_provider_loads']:
                counts['blocked_dll_attempts'] += 1
                raise PermissionError('Only the single sealed Lua parser provider may be loaded')
            counts['explicit_lua_provider_loads'] += 1
        if event in ('ctypes.dlsym', 'ctypes.dlsym/handle'):
            name = args[1] if len(args) > 1 else None
            if event != 'ctypes.dlsym' or name not in ('luaL_newstate', 'luaL_loadbuffer', 'lua_tolstring', 'lua_close'):
                counts['blocked_dll_attempts'] += 1
                raise PermissionError('Only the four Lua parser and state-lifetime functions may be resolved')
            allowed_dll['resolved_parser_functions'].add(name)
        if event in ('open', 'os.listdir', 'os.scandir', 'os.chdir') and args:
            path = args[0]
            if isinstance(path, (str, bytes, os.PathLike)):
                path = os.fsdecode(path)
                if any(within(path, root) for root in RETAIL_USER_ROOTS):
                    counts['blocked_retail_attempts'] += 1
                    raise PermissionError('Retail user state is forbidden')
                if event == 'open':
                    mode = args[1] if len(args) > 1 else None
                    flags = args[2] if len(args) > 2 else 0
                    writing = (isinstance(mode, str) and any(c in mode for c in 'wax+')) or \
                        (isinstance(flags, int) and bool(flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC)))
                    if writing and key(path) != key(output):
                        counts['blocked_write_attempts'] += 1
                        raise PermissionError('Only the fresh catalog receipt may be written')
                    if not writing and key(path) not in allowed_dll['read_paths']:
                        counts['blocked_read_attempts'] += 1
                        raise PermissionError('Read is outside the sealed catalog input set')
        if event in ('os.remove', 'os.unlink', 'os.rename', 'os.replace', 'os.rmdir', 'os.mkdir',
                     'os.link', 'os.symlink', 'os.chmod', 'os.utime', 'os.add_dll_directory'):
            counts['blocked_write_attempts'] += 1
            raise PermissionError('Filesystem mutations other than the fresh receipt are forbidden')

    sys.addaudithook(guard)
    return counts, allowed_dll


def parse_catalog(path):
    arrays, order = {}, None
    declaration = re.compile(rb'static const char ([A-Za-z_][A-Za-z0-9_]*)\[\]=\n')
    chunk = re.compile(rb'"(?:\\x[0-9a-f]{2}){0,64}"')
    catalog_row = re.compile(rb'\{"([A-Za-z_][A-Za-z0-9_]*)",([A-Za-z_][A-Za-z0-9_]*),sizeof\(\2\)-1\},\n')
    with Path(path).open('rb') as stream:
        while True:
            line = stream.readline(4097)
            if not line:
                break
            require(len(line) <= 4096, 'Generated header line exceeds its format bound')
            match = declaration.fullmatch(line)
            if match:
                name = match.group(1).decode('ascii')
                require(name not in arrays and len(arrays) < 256 and order is None, 'Duplicate or misplaced char array')
                raw = bytearray()
                previous_size = None
                while True:
                    line = stream.readline(4097)
                    require(line and len(line) <= 4096 and line.endswith(b'\n'), 'Truncated generated char array')
                    final = line.endswith(b';\n')
                    literal = line[:-2] if final else line[:-1]
                    require(chunk.fullmatch(literal) is not None and (previous_size is None or previous_size == 64),
                            'Generated char array is not exact 64-byte hexadecimal chunks')
                    value = bytes.fromhex(literal[1:-1].replace(b'\\x', b'').decode('ascii'))
                    require(value or final and previous_size is None, 'Empty nonterminal generated chunk')
                    raw.extend(value)
                    require(len(raw) <= MAX_SCRIPT, 'Registered script exceeds its bounded size')
                    previous_size = len(value)
                    if final:
                        break
                require(b'\0' not in raw, 'NUL in registered source script')
                arrays[name] = bytes(raw)
            elif line == b'static const Script scripts[]={\n':
                require(order is None, 'Duplicate script catalog')
                order = []
                while True:
                    line = stream.readline(4097)
                    if line == b'};\n':
                        break
                    match = catalog_row.fullmatch(line)
                    require(match is not None and len(order) < 256, 'Malformed script catalog row')
                    name, symbol = (part.decode('ascii') for part in match.groups())
                    require(name == symbol and name not in order and name in arrays, 'Catalog name does not resolve uniquely')
                    order.append(name)
    require(order and set(order) == set(arrays), 'Script catalog and char-array inventory differ')
    return arrays, order


def source_binding(scope, arrays):
    base = sealed(scope['base_build'], 2 * 1024 * 1024)
    base_report = read_json(base['path'])
    require(base_report.get('status') == 'UI_WINDOW_HOST_CANDIDATE_BUILT' and
            base_report.get('build_id') == scope['base_build_id'], 'Invalid frozen source baseline')
    refs = []
    for flag, relative in ADDENDA:
        matches = [row for row in base_report.get('sources', [])
                   if row.get('relative_path', '').replace('\\', '/') == relative]
        require(len(matches) == 1, 'Source addendum lacks one baseline receipt')
        row = matches[0]
        ref = artifact(PROJECT / relative)
        require(ref['bytes'] == row['bytes'] and ref['sha256'] == row['sha256'], 'Current source addendum differs from baseline')
        refs.append(ref)
    scene = (PROJECT / 'Source/Host/UiScene.lua').read_bytes() + b'\n' + \
        (PROJECT / 'Source/Presentation/UiPresentationInput.lua').read_bytes()
    for (flag, relative), ref in zip(ADDENDA, refs):
        scene += b'\nif ' + flag.encode('ascii') + b' then\n' + Path(ref['path']).read_bytes() + b'\nend\n'
    require(arrays.get('ZeroSisUiScene') == scene, 'Generated UI scene does not contain the exact current source and addenda')
    script_system = 'Source/Host/ScriptSystem.h'
    matches = [row for row in base_report.get('sources', [])
               if row.get('relative_path', '').replace('\\', '/') == script_system]
    require(len(matches) == 1, 'Script loader lacks one frozen baseline receipt')
    loader = artifact(PROJECT / script_system)
    require(loader['bytes'] == matches[0]['bytes'] and loader['sha256'] == matches[0]['sha256'],
            'Current script loader differs from the inspected BOM contract')
    refs.append(loader)
    originals = [sealed(row, 1024 * 1024) for row in scope['original_assets']]
    require(len(originals) == 2 and Path(originals[0]['path']).name == 'ChoosePantheonPopup.lua' and
            Path(originals[1]['path']).name == 'ChoosePantheonPopup.xml', 'Original Pantheon asset order changed')
    require(arrays.get('ChoosePantheonPopup') == Path(originals[0]['path']).read_bytes(), 'Catalog Pantheon Lua differs from immutable original')
    layout = arrays.get('PantheonLayout')
    require(isinstance(layout, bytes) and layout.startswith(b'ZeroSisUiLayout=') and all(token in layout for token in (
            b'ChoosePantheonPopup', b'ORIGINAL_BNW_PANTHEON_ONLY_V1', b'originalLayoutLua', b'originalLayoutXml',
            originals[0]['sha256'].encode('ascii'), originals[1]['sha256'].encode('ascii'))), 'Pantheon layout/source metadata is absent')
    snapshots = scope['new_source_snapshots']
    require(type(snapshots) is list and len(snapshots) == 2, 'Unexpected original snapshot inventory')
    for original, path in zip(originals, snapshots):
        expected = PROJECT / 'Source/Assets/UI/Assets/DLC/Expansion2/UI/InGame/Popups' / Path(original['path']).name
        require(key(path) == key(expected), 'Original snapshot escaped its exact destination')
        ref = artifact(path, 1024 * 1024)
        require(ref['bytes'] == original['bytes'] and ref['sha256'] == original['sha256'], 'Frozen Pantheon snapshot differs from original')
        refs.append(ref)
    refs.extend(originals)
    refs.append(base)
    return refs, {'exact_current_scene_input_and_six_addenda': True, 'original_pantheon_lua_exact': True,
                  'utf8_bom_rule_bound_to_current_script_loader': True,
                  'original_snapshots_exact': True, 'pantheon_layout_registered_with_source_metadata': True}


def parse_scripts(provider, arrays, order, allowed_dll):
    sealed(provider, 1024 * 1024)
    allowed_dll['path'] = key(provider['path'])
    lua = ctypes.CDLL(str(Path(provider['path']).absolute()))
    lua.luaL_newstate.argtypes = []; lua.luaL_newstate.restype = ctypes.c_void_p
    lua.luaL_loadbuffer.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_size_t, ctypes.c_char_p]
    lua.luaL_loadbuffer.restype = ctypes.c_int
    lua.lua_tolstring.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.POINTER(ctypes.c_size_t)]
    lua.lua_tolstring.restype = ctypes.c_void_p
    lua.lua_close.argtypes = [ctypes.c_void_p]; lua.lua_close.restype = None
    results = []
    for name in order:
        raw = arrays[name]
        bom = raw.startswith(b'\xef\xbb\xbf')
        code = raw[3:] if bom else raw  # Exact ScriptSystem::LoadFile behavior.
        row = {'name': name, 'raw_bytes': len(raw), 'raw_sha256': hashlib.sha256(raw).hexdigest(),
               'parse_input_bytes': len(code), 'parse_input_sha256': hashlib.sha256(code).hexdigest(),
               'utf8_bom_removed_for_parse': bom}
        state = lua.luaL_newstate()
        require(state, 'Cannot allocate Lua parser state')
        try:
            status = lua.luaL_loadbuffer(state, code, len(code), name.encode('ascii'))
            row['lua_status'] = status
            row['status'] = 'PASS_PARSE_ONLY' if status == 0 else 'FAILED_PARSE_ONLY'
            if status:
                length = ctypes.c_size_t()
                pointer = lua.lua_tolstring(state, -1, ctypes.byref(length))
                message = ctypes.string_at(pointer, min(length.value, 4096)) if pointer else b''
                row['diagnostic_sha256'] = hashlib.sha256(message).hexdigest()
                line = re.search(rb':([0-9]+):', message)
                row['diagnostic_line'] = int(line.group(1)) if line else None
                row['diagnostic_kind'] = 'UPVALUE_LIMIT' if b'upvalues' in message else 'LUA_LOAD_ERROR'
        finally:
            lua.lua_close(state)
        results.append(row)
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    output = Path(args.output).absolute()
    require(key(output.parent) == key(STAGE) and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,79}\.json', output.name) and
            not os.path.lexists(output), 'Receipt must be a fresh JSON directly below the scoped stage')
    for path in (PROJECT, PROJECT / 'evidence', PROJECT / 'evidence/religion', STAGE):
        info = path.lstat()
        require(stat.S_ISDIR(info.st_mode) and not getattr(info, 'st_file_attributes', 0) & 0x400, 'Stage directory is a reparse point')
    # Initialize this standard codec before the exact input-open allowlist.
    b'x'.decode('utf-8-sig')
    counts, allowed_dll = install_guard(output)
    report = {'schema': 'zerosis.pantheon_link.generated_script_catalog_syntax.v1', 'status': 'FAILED_PRECONDITION',
              'scripts_executed': False, 'lua_openlibs_called': False, 'host_executed': False,
              'gamecore_loaded': False, 'hwnd_created': False, 'retail_user_state_accessed': False,
              'additional_processes_started': 0, 'default_promoted': False, 'scripts': []}
    before = []
    exit_code = 1
    try:
        scope_ref = sealed({'path': str(SCOPE), 'bytes': SCOPE_BYTES, 'sha256': SCOPE_SHA}, 1024 * 1024)
        scope = read_json(SCOPE)
        require(scope.get('schema') == 'zerosis.pantheon_link.scope.v1' and
                scope.get('pure_lua_dll_syntax_only_allowed') is True and scope.get('host_execution_allowed') is False and
                scope.get('gamecore_execution_allowed') is False and scope.get('hwnd_execution_allowed') is False and
                scope.get('retail_user_state_or_game_process_access_allowed') is False and
                scope.get('retail_mod_test_hold_active') is True,
                'Scope does not authorize this pure parser boundary')
        sources = scope['source_seals']
        require(type(sources) is dict and len(sources) == 11, 'Expected exactly eleven sealed production inputs')
        allowed_dll['read_paths'].update(key(row['path']) for row in (
            scope['headless_lua_provider'], scope['source_stage'], scope['base_build'],
            *sources.values(), *scope['original_assets']))
        allowed_dll['read_paths'].update(key(path) for path in scope['new_source_snapshots'])
        allowed_dll['read_paths'].update(key(PROJECT / relative) for _, relative in ADDENDA)
        allowed_dll['read_paths'].add(key(PROJECT / 'Source/Host/ScriptSystem.h'))
        before = [scope_ref, artifact(Path(__file__)), artifact(HEADER), sealed(scope['headless_lua_provider'], 1024 * 1024),
                  sealed(scope['source_stage'], 1024 * 1024)]
        require(before[3]['bytes'] == LUA_BYTES and before[3]['sha256'] == LUA_SHA, 'Lua provider is not the approved binary')
        for relative, row in sources.items():
            require(key(PROJECT / relative) == key(row['path']), 'Production source identity escaped its scoped path')
            before.append(sealed(row))
        arrays, order = parse_catalog(HEADER)
        refs, proof = source_binding(scope, arrays)
        before.extend(refs)
        report['source_binding'] = proof
        report['scripts'] = parse_scripts(before[3], arrays, order, allowed_dll)
        failed = sum(row['lua_status'] != 0 for row in report['scripts'])
        report.update(catalog_count=len(order), parsed_count=len(report['scripts']), failed_count=failed)
        report['status'] = 'PASS_GENERATED_SCRIPT_CATALOG_LUA51_SYNTAX_ONLY' if not failed else 'FAILED_GENERATED_SCRIPT_CATALOG_LUA51_SYNTAX_ONLY'
        exit_code = 0 if not failed else 1
    except Exception as error:
        report['error_type'] = type(error).__name__
        report['error'] = str(error)[:240] if isinstance(error, (ValueError, PermissionError)) else 'Bounded catalog checker failed'
    try:
        require(before, 'No sealed inputs were established')
        after = [sealed(row) for row in before]
        report['inputs_before'] = before
        report['inputs_after'] = after
        report['inputs_unchanged'] = after == before
        require(not any(counts[name] for name in counts if name.startswith('blocked_')), 'A forbidden operation was attempted')
        if exit_code == 0:
            require(counts['explicit_lua_provider_loads'] == 1 and allowed_dll['resolved_parser_functions'] ==
                    {'luaL_newstate', 'luaL_loadbuffer', 'lua_tolstring', 'lua_close'}, 'Parser-only symbol boundary changed')
    except Exception as error:
        exit_code = 1; report['status'] = 'FAILED_INPUT_PRESERVATION_OR_GUARD'
        report['preservation_error_type'] = type(error).__name__
        report['inputs_unchanged'] = False
    report['guard'] = counts
    encoded = json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + '\n'
    require(len(encoded.encode('utf-8')) <= 128 * 1024, 'Bounded catalog receipt exceeded its size limit')
    with output.open('x', encoding='utf-8', newline='\n') as stream:
        stream.write(encoded)
    print(json.dumps({'status': report['status'], 'exit_code': exit_code,
                      'catalog_count': report.get('catalog_count', 0), 'failed_count': report.get('failed_count'),
                      'report': str(output)}, ensure_ascii=False))
    return exit_code


if __name__ == '__main__':
    raise SystemExit(main())
