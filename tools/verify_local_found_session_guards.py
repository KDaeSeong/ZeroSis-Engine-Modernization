"""Compile extracted LocalSdkSession founding guards against narrow owned mocks."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import uuid
from datetime import datetime, timezone

from collect_baseline import PROJECT, digest
from probe_world_builder import artifact
from verify_world_builder_map_object import check_artifacts


SOURCE = PROJECT / 'Source/Host/LocalSdkSession.h'
TEST = PROJECT / 'Tests/local_found_session_guards.cpp'
TOOL = Path(__file__).resolve()
OUT = PROJECT / 'evidence/local_found_session_guards'
BUILD = PROJECT / 'Build/LocalFoundSessionGuards'
VS = Path(r'C:\Program Files\Microsoft Visual Studio\2022\Community')
OWNER_SIGNATURE = 'void RequireCommandOwner() const {'
LAMBDA_SIGNATURE = '[this,&receiver,&game,&context](int unitID,MissionTypes mission,int data1,int data2,int flags,bool shift){'


def fail(message: str) -> None:
    raise RuntimeError(message)


def sha(path: Path) -> str:
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def balanced_end(text: str, opening: int) -> int:
    depth = 0
    quote = None
    escaped = False
    line_comment = False
    block_comment = False
    i = opening
    while i < len(text):
        char = text[i]
        nxt = text[i + 1] if i + 1 < len(text) else ''
        if line_comment:
            if char == '\n': line_comment = False
        elif block_comment:
            if char == '*' and nxt == '/': block_comment = False; i += 1
        elif quote:
            if escaped: escaped = False
            elif char == '\\': escaped = True
            elif char == quote: quote = None
        elif char == '/' and nxt == '/': line_comment = True; i += 1
        elif char == '/' and nxt == '*': block_comment = True; i += 1
        elif char in ('"', "'"): quote = char
        elif char == '{': depth += 1
        elif char == '}':
            depth -= 1
            if depth == 0: return i + 1
        i += 1
    fail('Unbalanced source body while extracting LocalSdkSession implementation')


def extract_definition(text: str, signature: str) -> str:
    start = text.find(signature)
    if start < 0 or text.find(signature, start + 1) >= 0:
        fail(f'Expected exactly one source definition: {signature}')
    opening = text.find('{', start + len(signature) - 1)
    if opening < 0: fail(f'Missing body after source definition: {signature}')
    return text[start:balanced_end(text, opening)]


def unique_id() -> str:
    return datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '_' + uuid.uuid4().hex[:12]


def create_environment(directory: Path) -> tuple[Path, Path, dict[str, str]]:
    directory.mkdir(parents=True, exist_ok=False)
    vcvars = VS / 'VC/Auxiliary/Build/vcvars64.bat'
    if not vcvars.is_file(): fail('Visual Studio x64 environment setup is unavailable')
    setup = directory / 'environment.cmd'
    setup.write_text(f'@echo off\ncall "{vcvars}" >nul\nif errorlevel 1 exit /b 1\nset\n', encoding='utf-8')
    proc = subprocess.run(['cmd.exe', '/d', '/c', str(setup)], cwd=directory, capture_output=True,
                           creationflags=subprocess.CREATE_NO_WINDOW, timeout=60)
    if proc.returncode: fail('Could not initialize the x64 MSVC environment')
    env = {key.upper(): value for key, value in os.environ.items()}
    paths = []
    for line in proc.stdout.decode('mbcs', errors='replace').splitlines():
        if '=' not in line or line.startswith('='): continue
        key, value = line.split('=', 1); env[key.upper()] = value
        if key.upper() == 'PATH': paths.append(value)
    env['PATH'] = ';'.join(dict.fromkeys(item for value in paths for item in value.split(';')))
    compiler = next((Path(item) / 'cl.exe' for item in env['PATH'].split(';') if (Path(item) / 'cl.exe').is_file()), None)
    linker = next((Path(item) / 'link.exe' for item in env['PATH'].split(';') if (Path(item) / 'link.exe').is_file()), None)
    if compiler is None or linker is None: fail('MSVC x64 compiler/linker missing after environment setup')
    return compiler.resolve(), linker.resolve(), env


def compile_call(compiler: Path, env: dict[str, str], source: Path, directory: Path,
                 optimization: str, include_roots: list[Path]) -> dict:
    directory.mkdir(parents=True, exist_ok=False)
    exe, obj = directory / 'local_found_session_guards.exe', directory / 'fixture.obj'
    dependencies, response = directory / 'dependencies.json', directory / 'compile.rsp'
    compile_flags = ['/nologo', '/std:c++14', '/EHsc', '/W4', '/WX', optimization, '/MD', '/fp:strict', '/utf-8',
                     '/c', f'"{source}"', f'/Fo"{obj}"', f'/sourceDependencies "{dependencies}"']
    if include_roots: compile_flags.insert(8, '/I"' + str(include_roots[0]) + '"')
    response.write_text('\n'.join(compile_flags) + '\n', encoding='utf-8')
    env = env.copy()
    if include_roots: env['INCLUDE'] = ';'.join(str(root) for root in include_roots)
    log = directory / 'compile.log'
    result = subprocess.run([str(compiler), '@' + str(response)], cwd=directory, env=env,
                            capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW, timeout=180)
    transcript = result.stdout + result.stderr
    log.write_bytes(transcript)
    if result.returncode or re.search(rb'\bwarning\s+[A-Z]?\d+', transcript, re.I):
        fail(f'{optimization} compile failed or emitted warnings: {transcript.decode("mbcs", errors="replace")[-5000:]}')
    link = directory / 'link.rsp'
    link.write_text('\n'.join(['/nologo', f'"{obj}"', f'/OUT:"{exe}"', '/INCREMENTAL:NO', '/MACHINE:X64',
                               '/Brepro', '/WX', '/OPT:REF', '/OPT:ICF']) + '\n', encoding='utf-8')
    link_log = directory / 'link.log'
    linked = subprocess.run([str(compiler.with_name('link.exe')), '@' + str(link)], cwd=directory, env=env,
                            capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW, timeout=120)
    link_bytes = linked.stdout + linked.stderr; link_log.write_bytes(link_bytes)
    if linked.returncode or re.search(rb'\bwarning\s+[A-Z]?\d+', link_bytes, re.I):
        fail(f'{optimization} link failed or emitted warnings: {link_bytes.decode("mbcs", errors="replace")[-5000:]}')
    deps = json.loads(dependencies.read_text(encoding='utf-8-sig'))['Data']
    if Path(deps['Source']).resolve() != source.resolve(): fail('Compiler consumed a different fixture source')
    run = subprocess.run([str(exe)], cwd=directory, env=env, capture_output=True,
                         creationflags=subprocess.CREATE_NO_WINDOW, timeout=30)
    output = (run.stdout + run.stderr).decode('utf-8', errors='replace').replace('\r\n', '\n')
    execution = directory / 'execution.log'; execution.write_text(output, encoding='utf-8')
    match = re.search(r'^LOCAL_FOUND_SESSION_GUARDS_PASS checks=(\d+) GAMECORE_LOADED=false SDK_LOADER_USED=false$', output, re.M)
    if run.returncode or not match:
        fail(f'{optimization} guard fixture failed: {output[-5000:]}')
    return {'optimization': optimization, 'executable': artifact(exe), 'object': artifact(obj),
            'response': artifact(response), 'link_response': artifact(link), 'dependencies': artifact(dependencies),
            'compile_log': artifact(log), 'link_log': artifact(link_log), 'execution_log': artifact(execution),
            'checks': int(match.group(1)), 'compiler_inputs': [Path(deps['Source']), *(Path(x) for x in deps['Includes'])]}


def main() -> None:
    if len(os.sys.argv) != 1: fail('This verifier performs one O2/Od component build; it does not launch GameCore')
    run_id = unique_id(); evidence = OUT / run_id; build_root = BUILD / run_id
    evidence.mkdir(parents=True, exist_ok=False); build_root.mkdir(parents=True, exist_ok=False)
    frozen = evidence / 'frozen_inputs'; frozen.mkdir()
    before = {str(path.resolve()): artifact(path) for path in (SOURCE, TEST, TOOL)}
    for path, rel in ((SOURCE, 'Source/Host/LocalSdkSession.h'),
                      (TEST, 'Tests/local_found_session_guards.cpp'), (TOOL, 'tools/verify_local_found_session_guards.py')):
        target = frozen / rel; target.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(path, target)
        if sha(path) != sha(target): fail(f'Could not freeze verifier input: {path}')
    frozen_source = frozen / 'Source/Host/LocalSdkSession.h'
    frozen_template = frozen / 'Tests/local_found_session_guards.cpp'
    src_text = frozen_source.read_text(encoding='utf-8')
    owner = extract_definition(src_text, OWNER_SIGNATURE)
    callback = extract_definition(src_text, LAMBDA_SIGNATURE)
    if 'RequireCommandOwner();' not in callback or 'ResponsePushMission(active,unitID,mission,data1,data2,flags,shift);' not in callback:
        fail('Extracted founding callback no longer preserves owner check or exact SDK receiver route')
    harness = frozen_template.read_text(encoding='utf-8')
    harness = harness.replace('// EXTRACTED_PUSH_MISSION_LAMBDA', 'pushMission_ = ' + callback + ';')
    harness = harness.replace('// EXTRACTED_REQUIRE_COMMAND_OWNER', owner)
    if 'EXTRACTED_' in harness: fail('An extraction marker was not replaced')
    generated = frozen / 'Tests/local_found_session_guards.generated.cpp'
    generated.write_text(harness, encoding='utf-8', newline='\n')
    generated_hash = sha(generated)

    compiler, linker, live_env = create_environment(build_root / 'environment')
    compiler_before, linker_before = artifact(compiler), artifact(linker)
    include_roots = [Path(item).resolve() for item in live_env.get('INCLUDE', '').split(';') if item and Path(item).is_dir()]
    discovery_dir = build_root / 'dependency_discovery'; discovery_dir.mkdir()
    discovery_obj = discovery_dir / 'discovery.obj'; dep_file = discovery_dir / 'dependencies.json'
    discovery_rsp = discovery_dir / 'discovery.rsp'
    discovery_rsp.write_text('\n'.join(['/nologo', '/std:c++14', '/EHsc', '/W4', '/WX', '/O2', '/MD', '/fp:strict', '/utf-8',
                                         '/c', f'"{generated}"', f'/Fo"{discovery_obj}"', f'/sourceDependencies "{dep_file}"']) + '\n', encoding='utf-8')
    proc = subprocess.run([str(compiler), '@' + str(discovery_rsp)], cwd=discovery_dir, env=live_env,
                          capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW, timeout=180)
    discovery_log = discovery_dir / 'discovery.log'; discovery_log.write_bytes(proc.stdout + proc.stderr)
    if proc.returncode: fail('Compiler dependency discovery failed: ' + (proc.stdout + proc.stderr).decode('mbcs', errors='replace')[-4000:])
    dep_data = json.loads(dep_file.read_text(encoding='utf-8-sig'))['Data']
    if Path(dep_data['Source']).resolve() != generated.resolve(): fail('Dependency discovery did not compile the frozen generated harness')
    consumed_live = {Path(dep_data['Source']).resolve(), *(Path(p).resolve() for p in dep_data['Includes'])}
    if not include_roots or any(not any(path.is_relative_to(root) for root in include_roots) for path in consumed_live - {generated.resolve()}):
        fail('A compiler include is outside the active MSVC include roots')
    original_roots = {root: frozen / 'compiler_includes' / f'root_{i:03d}' for i, root in enumerate(include_roots)}
    for root in original_roots.values(): root.mkdir(parents=True, exist_ok=True)
    frozen_map = {generated.resolve(): generated}
    include_records = []
    for path in sorted(consumed_live - {generated.resolve()}, key=lambda p: str(p).casefold()):
        root = next((candidate for candidate in include_roots if path.is_relative_to(candidate)), None)
        if root is None: fail('No compiler include root owns a consumed header')
        target = original_roots[root] / path.relative_to(root)
        target.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(path, target)
        if sha(path) != sha(target): fail(f'Compiler header freeze mismatch: {path}')
        frozen_map[path] = target
        include_records.append({'original_source': str(path), **artifact(target)})
    frozen_includes = [original_roots[root] for root in include_roots]
    (evidence / 'dependency_discovery.json').write_text(json.dumps({
        'source': artifact(generated), 'compiler': compiler_before,
        'consumed_live_inputs': [artifact(path) for path in sorted(consumed_live, key=lambda p: str(p).casefold())],
        'discovery_log': artifact(discovery_log)}, indent=2) + '\n', encoding='utf-8')

    # Compile the exact generated source from the retained frozen tree, and resolve
    # all CRT/Windows SDK headers from the physical copies above.
    discovered_keys = {(0, 'generated.cpp')}
    frozen_source_for_compile = generated
    for path in consumed_live - {generated.resolve()}:
        root = next(candidate for candidate in include_roots if path.is_relative_to(candidate))
        discovered_keys.add((include_roots.index(root), str(path.relative_to(root)).casefold()))
    configs = []
    for label, opt in (('optimized_O2', '/O2'), ('unoptimized_Od', '/Od')):
        report = compile_call(compiler, live_env, frozen_source_for_compile, build_root / label, opt, frozen_includes)
        actual = {Path(p).resolve() for p in report.pop('compiler_inputs')}
        expected_paths = {generated.resolve(), *(p.resolve() for p in frozen_map.values() if p != generated)}
        if actual != expected_paths:
            fail(f'{label} compiler include closure changed; missing={actual-expected_paths}; extra={expected_paths-actual}')
        if any(not path.is_relative_to(frozen.resolve()) for path in actual):
            fail(f'{label} compiled a live mutable input')
        report['compiler_inputs'] = [artifact(p) for p in sorted(actual, key=lambda p: str(p).casefold())]
        configs.append(report)

    after = {str(path.resolve()): artifact(path) for path in (SOURCE, TEST, TOOL)}
    if before != after: fail('A live source/test/verifier changed during the frozen guard build')
    if artifact(compiler) != compiler_before or artifact(linker) != linker_before:
        fail('MSVC compiler or linker changed during component verification')
    for path in consumed_live - {generated.resolve()}:
        if artifact(path)['sha256'] != next(record['sha256'] for record in include_records
                                            if record['original_source'] == str(path)):
            fail('A live compiler header changed while building')
    if sha(generated) != generated_hash: fail('Generated frozen source changed during build')
    report = {
        'status': 'LOCAL_FOUND_SESSION_GUARDS_COMPONENT_PASS', 'run_id': run_id,
        'source': before[str(SOURCE.resolve())], 'test_template': before[str(TEST.resolve())],
        'extracted_bodies': {'require_command_owner_sha256': hashlib.sha256(owner.encode()).hexdigest(),
                             'push_mission_lambda_sha256': hashlib.sha256(callback.encode()).hexdigest(),
                             'generated_harness': artifact(generated)},
        'compiler': compiler_before, 'linker': linker_before, 'compiler_header_copies': include_records,
        'configs': configs, 'checks': {row['optimization']: row['checks'] for row in configs},
        'sdk_dll_loaded': False, 'gamecore_loaded': False,
        'scope': 'EXACT_EXTRACTED_LOCAL_SDK_SESSION_OWNER_GUARD_AND_FOUND_MISSION_CALLBACK_WITH_SOURCE_SHAPED_FAKE_SDK_OBJECTS',
        'limitations': 'Validates callback input guards, dispatch tuple, early owner rejection, and wrapper cleanup in a narrow C++14 fixture; does not load GameCore or prove SDK/runtime mission acceptance.'}
    out = evidence / 'conformance.json'; out.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    check_artifacts(report)
    print(json.dumps({'status': report['status'], 'run_id': run_id, 'checks': report['checks'],
                      'evidence': artifact(out), 'gamecore_loaded': False}))


if __name__ == '__main__':
    main()
