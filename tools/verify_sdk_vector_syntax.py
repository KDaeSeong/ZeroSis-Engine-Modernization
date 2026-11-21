"""Syntax-check actual SDK consumers and four real enum template instances only."""
from __future__ import annotations
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys

sys.dont_write_bytecode = True
from verify_retail_save_header import artifact, require, key, within, COMPILER, COMPILER_SHA, VS
from native_build import environment_for, run

PROJECT = Path(__file__).absolute().parents[1]
SDK = PROJECT/'Source/SDK_BNW_x64'
GAMECORE = SDK/'CvGameCoreDLL_Expansion2'
STAGE = PROJECT/'evidence/serialization/vector_count_syntax'
REPORT = STAGE/'build_result.json'
TARGETS = [('team', GAMECORE/'CvTeam.cpp'), ('four_templates', PROJECT/'Tests/sdk_vector_count_compile.cpp')]


def main():
    require(len(sys.argv) == 1 and not sys.flags.optimize, 'Unexpected syntax verifier arguments')
    helper = GAMECORE/'CvInfosSerializationHelper.h'
    inputs = [artifact(p) for p in [*[p for _, p in TARGETS], helper, GAMECORE/'CvGameCoreDLLPCH.h',
        PROJECT/'Source/Porting/sdk_x64_patches.json', PROJECT/'evidence/sdk_x64/port_manifest.json',
        *sorted((PROJECT/'Source/Porting').glob('*.h')), PROJECT/'Source/LuaBorrowed/ZeroSisLuaBorrowed.h',
        Path(__file__).absolute(), PROJECT/'tools/verify_retail_save_header.py', PROJECT/'tools/native_build.py']]
    compiler = artifact(COMPILER)
    require(compiler['sha256'] == COMPILER_SHA, 'Reviewed compiler changed')
    identifier = hashlib.sha256(json.dumps(dict(inputs=inputs, compiler=compiler), sort_keys=True).encode()).hexdigest()[:16]
    root = PROJECT/'Build/SdkVectorCountSyntax'/identifier
    if REPORT.exists():
        old = json.loads(REPORT.read_text(encoding='utf-8'))
        require(old['status'] == 'PASS_ACTUAL_SDK_VECTOR_COUNT_SYNTAX' and old['inputs'] == inputs, 'Inspect prior syntax result first')
        for row in old['consumed_project_headers']:
            require(artifact(row['path']) == row, 'Consumed SDK header changed')
        print(json.dumps(dict(status=old['status'], reused=True)))
        return
    require(not root.exists(), 'Inspect partial syntax build before retrying')
    manifest = json.loads((PROJECT/'evidence/sdk_x64/port_manifest.json').read_text(encoding='utf-8'))
    expected_sdk = {key(row['port']):row['port_sha256'] for row in manifest}
    require(expected_sdk[key(helper)] == artifact(helper)['sha256'], 'Manifest does not include the corrected helper')
    protected = [artifact(PROJECT/name) for name in ('Play/EarlyAccess/release.json',
        'evidence/save_menu/20261013_original_screen/current_progress.json',
        'evidence/goody_hut/runtime_fonts/preparation_identity_audit.json',
        'evidence/goody_hut/runtime_fonts/system_freeze_hold.json',
        'evidence/serialization/type_array_count/build_result.json')]
    for part in (root, *root.parents, STAGE):
        if part.exists(): require(not part.lstat().st_file_attributes & 0x400, 'Reparse syntax output path')
    root.parent.mkdir(parents=True, exist_ok=True); STAGE.mkdir(exist_ok=True)
    allowed, calls = {('cmd.exe', '/d', '/c', str(root/'read_build_environment.cmd'))}, []
    reports = {key(STAGE/name) for name in ('build_started.json', 'build_result.json', 'failed_attempt.json', 'compile_team.log', 'compile_four_templates.log')}

    def audit(event, args):
        if event == 'subprocess.Popen':
            command = next((x for x in allowed if subprocess.list2cmdline(x) == args[1]), None) \
                if isinstance(args[1], str) else tuple(str(x) for x in args[1])
            require(command in allowed, 'Unapproved syntax-only child command')
            require(args[0] is None or key(args[0]) == key(command[0]) or
                Path(args[0]).name.casefold() == command[0].casefold() == 'cmd.exe', 'Unexpected executable override')
            calls.append(command)
        if event == 'open' and args and isinstance(args[0], (str, bytes, os.PathLike)):
            writing = isinstance(args[1], str) and any(c in args[1] for c in 'wax+') or \
                isinstance(args[2], int) and args[2] & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND)
            if writing: require(within(os.fsdecode(args[0]), root) or key(os.fsdecode(args[0])) in reports, 'Write escaped syntax outputs')
        if event in ('os.remove', 'os.rmdir', 'os.mkdir', 'os.rename', 'os.chmod', 'os.link', 'os.symlink'):
            for target in (args[:2] if event in ('os.rename', 'os.link', 'os.symlink') else args[:1]):
                if isinstance(target, (str, bytes, os.PathLike)):
                    require(within(os.fsdecode(target), root), 'Mutation escaped syntax root')
        if event.startswith(('ctypes.dlopen', 'socket.', 'urllib.', 'http.client.')) or event in ('os.system', 'os.startfile', 'os.startfile/2'):
            raise RuntimeError('Network, dynamic loading and interactive launches forbidden during syntax checks')
    sys.addaudithook(audit)
    root.mkdir()
    (STAGE/'build_started.json').write_text(json.dumps(dict(build_root=str(root), inputs=inputs, protected=protected,
        previous_goal_turn_classification='progress'), indent=2)+'\n', encoding='utf-8')
    results, consumed = [], {}
    try:
        environment, selected = environment_for(VS, 'x64', root)
        require(key(selected) == key(COMPILER), 'Compiler selection changed')
        environment['VSLANG'] = '1033'; environment['TMP'] = environment['TEMP'] = str(root)
        includes = [GAMECORE, PROJECT/'Source/Porting', PROJECT/'Source/LuaBorrowed'] + [SDK/name for name in (
            'CvWorldBuilderMap/include', 'CvGameCoreDLLUtil/include', 'CvLocalization/include', 'CvGameDatabase/include',
            'FirePlace/include', 'FirePlace/include/FireWorks', 'ThirdPartyLibs/Lua51/include')]
        flags = ['/nologo', '/Zs', '/Y-', '/showIncludes', '/std:c++14', '/EHsc', '/MD', '/Od', '/fp:strict', '/W3', '/bigobj', '/FC',
            '/we4302', '/we4311', '/we4312', '/DFXS_IS_DLL', '/DWIN32', '/DNDEBUG', '/D_WINDOWS', '/D_USRDLL',
            '/DCVGAMECOREDLL_EXPORTS', '/DFINAL_RELEASE', '/D_CRT_SECURE_NO_WARNINGS', '/D_SILENCE_STDEXT_HASH_DEPRECATION_WARNINGS',
            *[f'/I"{path}"' for path in includes]]
        for label, source in TARGETS:
            response = root/(label+'.rsp')
            response.write_text('\n'.join([*flags, f'"{source}"'])+'\n', encoding='ascii')
            command = [str(COMPILER), '@'+str(response)]
            allowed.add(tuple(command)); compiled = run(command, cwd=root, env=environment, timeout=120)
            raw = compiled.stdout+compiled.stderr; text = raw.decode('mbcs', errors='replace')
            include_lines, diagnostic_lines, headers = [], [], []
            for line in text.splitlines():
                match = re.search(r'([A-Za-z]:[\\/].*\.(?:h|hpp|inl|inc))\s*$', line, re.I)
                if match:
                    path = Path(match.group(1))
                    if within(path, PROJECT):
                        require(not path.lstat().st_file_attributes & 0x400, 'Reparse consumed header')
                        record = artifact(path)
                        if within(path, SDK): require(expected_sdk.get(key(path)) == record['sha256'], 'Untracked consumed SDK header')
                        require('sdk_bnw_original' not in key(path), 'Original SDK included by x64 syntax check')
                        consumed[key(path)] = record; headers.append(record); include_lines.append(line)
                else: diagnostic_lines.append(line)
            warnings = [line for line in diagnostic_lines if re.search(r'\bwarning\s+[A-Z]+\d+', line, re.I)]
            log = STAGE/('compile_'+label+'.log')
            log.write_text('\n'.join([*include_lines, *diagnostic_lines])+ '\n', encoding='utf-8')
            require(compiled.returncode == 0, 'Actual SDK syntax failure; inspect '+log.name)
            require(any(key(row['path']) == key(helper) for row in headers), 'Corrected helper was not consumed')
            require(any(key(row['path']) == key(PROJECT/'Source/Porting/CvCheckedNarrow.h') for row in headers), 'Actual checked-count helper was not consumed')
            results.append(dict(target=label, source=artifact(source), response=artifact(response), log=artifact(log),
                returncode=compiled.returncode, raw_output_sha256=hashlib.sha256(raw).hexdigest(), raw_output_bytes=len(raw),
                consumed_project_header_count=len(headers), warning_records=warnings, syntax_only=True,
                object_or_pch_created=False, code_generation_or_link_performed=False))
        require(inputs == [artifact(x['path']) for x in inputs] and protected == [artifact(x['path']) for x in protected],
            'Inputs or protected runtime evidence changed')
        generated = [p for p in root.rglob('*') if p.is_file()]
        require(all(p.name in ('team.rsp', 'four_templates.rsp', 'read_build_environment.cmd') for p in generated), 'Unexpected syntax artifact generated')
        setup = root/'read_build_environment.cmd'; info = setup.stat()
        require(info.st_nlink == 1 and not info.st_file_attributes & 0x400, 'Shared syntax setup cleanup target')
        retired = dict(**artifact(setup), file_identity=[info.st_dev, info.st_ino], mtime_ns=info.st_mtime_ns)
        setup.unlink()
        report = dict(schema='zerosis.sdk.vector_count.syntax.v1', status='PASS_ACTUAL_SDK_VECTOR_COUNT_SYNTAX',
            utc=datetime.now(timezone.utc).isoformat(), build_root=str(root), inputs=inputs, compiler=compiler, results=results,
            consumed_project_headers=list(consumed.values()), protected=protected, protected_unchanged=True, child_commands=[list(x) for x in calls],
            retired_intermediates=[retired], retired_logical_bytes=retired['bytes'], all_four_real_resource_enum_instances_checked=True,
            actual_cvteam_translation_unit_syntax_checked=True, pch_or_objects_generated=False, code_generation_or_link_performed=False,
            host_gamecore_or_hwnd_executed=False, full_sdk_recompiled=False, integrated_into_current_host=False,
            sdk_restore_verified=False, full_engine_goal_complete=False)
        REPORT.write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
        print(json.dumps(dict(status=report['status'], consumed_project_headers=len(consumed), warnings=[len(r['warning_records']) for r in results],
            report=artifact(REPORT))))
    except BaseException as error:
        (STAGE/'failed_attempt.json').write_text(json.dumps(dict(status='FAILED_SDK_VECTOR_COUNT_SYNTAX',
            error=type(error).__name__+': '+str(error), build_root=str(root), inputs=inputs, completed_targets=results,
            protected_unchanged=protected == [artifact(x['path']) for x in protected]), indent=2)+'\n', encoding='utf-8')
        raise


if __name__ == '__main__':
    main()
