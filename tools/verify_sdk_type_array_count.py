"""Compare exact SDK vector writers with real x86/x64 streams, without GameCore."""
from __future__ import annotations
from datetime import datetime, timezone
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import struct
import subprocess
import sys

sys.dont_write_bytecode = True
from verify_retail_save_header import artifact, require, key, within, COMPILER, COMPILER_SHA, VS
from verify_retail_save_state import public_input, OUTPUT_SHA
from native_build import environment_for, run
from collect_baseline import pe_header

PROJECT = Path(__file__).absolute().parents[1]
STAGE = PROJECT/'evidence/serialization/type_array_count'
REPORT = STAGE/'build_result.json'
TEST = PROJECT/'Tests/sdk_type_array_count.cpp'
ORIGINAL = PROJECT/'Source/SDK_BNW_Original/CvGameCoreDLL_Expansion2/CvInfosSerializationHelper.h'
CANDIDATE = PROJECT/'Source/SDK_BNW_x64/CvGameCoreDLL_Expansion2/CvInfosSerializationHelper.h'
BACKUP = STAGE/'CvInfosSerializationHelper.h.before.gz'
VC9 = Path(r'C:\Program Files (x86)\Microsoft Visual Studio 9.0\VC')
WIN7 = Path(r'C:\Program Files (x86)\Microsoft SDKs\Windows\v7.0A')
CL86 = VC9/'bin/cl.exe'
CL86_SHA = 'a9251084c3593d46d49bb992f54db3a8727dc64eec3ae2a9bf01935b3edf85bf'
LIBRARIES = {
    'x86': [(PROJECT/'Source/SDK_BNW_Original/CvGameCoreDLLUtil/lib/CvGameCoreDLLUtilWin32.lib',
             '8660209ead4e9e7350194f17e7560b4fa1a99a648838923aa3ce36cfa54323e1'),
            (PROJECT/'Source/SDK_BNW_Original/FirePlace/lib/FireWorksWin32.lib',
             'a0eda192b8d81e5d3bef789787b8d794b810d00e6c9957f9df60183002a71672')],
    'x64': [(PROJECT/'Build/Streams_provider/x64/ZeroSis_Streams_x64.lib',
             '565eceddf47259c29d3617b8cfc7e25328b89424429b22f53a65a0405d36d94e')],
}
HEADERS = [PROJECT/'Source/Host'/name for name in ('RetailSaveStateWire.h', 'RetailSaveSupporting.h', 'RetailSaveTeam.h',
    'RetailSaveMap.h', 'RetailSavePlot.h', 'RetailSaveMapTail.h', 'RetailSaveState.h', 'RetailSaveGameFront.h', 'RetailSaveGameTail.h')]
NAMES = ('WriteDataArray', 'WriteHashedDataArray', 'WriteTypeArray', 'WriteHashedTypeArray')


def extract(data, name):
    text = data.decode('latin1')
    kind = 'TData' if name in NAMES[:2] else 'TType'
    array = 'aArray' if kind == 'TData' else 'aiArray'
    signature = f'void {name}(FDataStream& kStream, const std::vector<{kind}>& {array})'
    require(text.count(signature) == 1, 'Ambiguous vector writer: '+name)
    start = text.rfind('template<', 0, text.index(signature))
    opening = text.index('{', text.index(signature))
    end, depth = opening + 1, 1
    while depth:
        if text[end] == '{': depth += 1
        elif text[end] == '}': depth -= 1
        end += 1
    body = data[start:end]
    body.decode('ascii')
    return body, dict(name=name, offset=start, bytes=len(body), sha256=hashlib.sha256(body).hexdigest())


def generate(path):
    original, previous, fixed = ORIGINAL.read_bytes(), gzip.decompress(BACKUP.read_bytes()), CANDIDATE.read_bytes()
    require(original == previous, 'Before-patch x64 helper differs from original reference')
    require(hashlib.sha256(fixed).hexdigest() == 'b33060722669f0374d6307a79364c065d84739ae0c958bbe41eb8e1b8a4acb9f',
            'Reviewed SDK count patch changed')
    parts, provenance = [b'#pragma once\n'], []
    for namespace, data in (('OriginalWriter', original), ('Legacy64Writer', previous), ('CandidateWriter', fixed)):
        if namespace != 'OriginalWriter': parts.append(b'#ifdef _WIN64\n')
        parts.append(('namespace '+namespace+' {\nusing TestHooks::Write;\nusing TestHooks::WriteHashed;\n').encode())
        rows = []
        for name in NAMES:
            body, row = extract(data, name)
            if namespace == 'CandidateWriter':
                require(body.index(b'CvChecked::Integer<uint>') < body.index(b'kStream << uiArraySize;'),
                        'Count guard must precede the first stream write')
            parts.append(body+b'\n')
            rows.append(row)
        parts.append(b'}\n')
        if namespace != 'OriginalWriter': parts.append(b'#endif\n')
        provenance.append(dict(namespace=namespace, source_sha256=hashlib.sha256(data).hexdigest(), functions=rows))
    path.write_bytes(b'\n'.join(parts))
    return dict(generated=artifact(path), families=provenance, type_hash_resolution='TestHooks only; not real ruleset IDs')


def imports(path):
    data = path.read_bytes()
    pe = struct.unpack_from('<I', data, 0x3c)[0]
    count, optional_bytes = struct.unpack_from('<H12xH', data, pe+6)
    optional = pe+24
    magic = struct.unpack_from('<H', data, optional)[0]
    require(magic in (0x10b, 0x20b), 'Unsupported test PE format')
    directory = optional + (104 if magic == 0x10b else 120)
    import_rva, _ = struct.unpack_from('<II', data, directory)
    sections = []
    for i in range(count):
        off = optional+optional_bytes+40*i
        virtual_size, rva, raw_size, raw = struct.unpack_from('<IIII', data, off+8)
        sections.append((rva, max(virtual_size, raw_size), raw))
    def file_offset(rva):
        for begin, size, raw in sections:
            if begin <= rva < begin+size: return raw+rva-begin
        raise RuntimeError('Unmapped import RVA')
    cursor, result = file_offset(import_rva), []
    while any(struct.unpack_from('<IIIII', data, cursor)):
        name_rva = struct.unpack_from('<I', data, cursor+12)[0]
        begin = file_offset(name_rva)
        name = data[begin:data.index(b'\0', begin)].decode('ascii').lower()
        require(name in {'kernel32.dll', 'user32.dll', 'advapi32.dll', 'psapi.dll', 'dbghelp.dll', 'ole32.dll',
            'shell32.dll', 'winmm.dll', 'msvcr90.dll', 'msvcp90.dll', 'msvcp140.dll', 'vcruntime140.dll',
            'vcruntime140_1.dll', 'ucrtbase.dll'} or name.startswith('api-ms-win-crt-'), 'Unexpected test import: '+name)
        result.append(name)
        cursor += 20
    return result


def main():
    require(len(sys.argv) == 1 and not sys.flags.optimize, 'Unexpected verifier arguments')
    paths = [TEST, ORIGINAL, CANDIDATE, BACKUP, *HEADERS, PROJECT/'Source/Porting/CvCheckedNarrow.h',
        PROJECT/'Source/Providers/Streams/SdkStreamIncludes.h', PROJECT/'Tests/sdk_stream_reference_host.cpp',
        Path(__file__).absolute(), PROJECT/'tools/native_build.py', PROJECT/'tools/collect_baseline.py',
        PROJECT/'tools/verify_retail_save_header.py', PROJECT/'tools/verify_retail_save_state.py']
    paths.extend(path for values in LIBRARIES.values() for path, _ in values)
    inputs = [artifact(p) for p in paths]
    for values in LIBRARIES.values():
        for path, expected in values: require(artifact(path)['sha256'] == expected, 'Reviewed stream library changed')
    compilers = [artifact(CL86), artifact(COMPILER)]
    require(compilers[0]['sha256'] == CL86_SHA and compilers[1]['sha256'] == COMPILER_SHA, 'Reviewed compiler changed')
    identifier = hashlib.sha256(json.dumps(dict(inputs=inputs, compilers=compilers), sort_keys=True).encode()).hexdigest()[:16]
    root = PROJECT/'Build/SdkTypeArrayCount'/identifier
    if REPORT.exists():
        old = json.loads(REPORT.read_text(encoding='utf-8'))
        require(old['inputs'] == inputs and old['status'] == 'PASS_SDK_VECTOR_COUNT_ABI_COMPONENT', 'Inspect previous result first')
        for row in old['results']: require(artifact(row['executable']['path']) == row['executable'], 'Retained test changed')
        print(json.dumps(dict(status=old['status'], reused=True)))
        return
    require(not root.exists(), 'Inspect and retire partial ABI build before retrying')
    public = public_input()
    require(hashlib.sha256(public).hexdigest() == OUTPUT_SHA, 'Public RAM input changed')
    protected = [artifact(PROJECT/name) for name in ('Play/EarlyAccess/release.json',
        'evidence/save_menu/20261013_original_screen/current_progress.json',
        'evidence/goody_hut/runtime_fonts/preparation_identity_audit.json',
        'evidence/goody_hut/runtime_fonts/system_freeze_hold.json',
        'evidence/retail_save_container/map_state/build_result.json', 'docs/M7_RETAIL_SAVE_BOUNDARY.md')]
    for part in (root, *root.parents, STAGE):
        if part.exists(): require(not part.lstat().st_file_attributes & 0x400, 'Reparse build path')
    root.parent.mkdir(parents=True, exist_ok=True)
    allowed, calls = set(), []
    setup = root/'read_build_environment.cmd'
    allowed.add(('cmd.exe', '/d', '/c', str(setup)))

    def audit(event, args):
        if event == 'subprocess.Popen':
            command = next((x for x in allowed if subprocess.list2cmdline(x) == args[1]), None) \
                if isinstance(args[1], str) else tuple(str(x) for x in args[1])
            require(command in allowed, 'Unapproved ABI-test child command')
            require(args[0] is None or key(args[0]) == key(command[0]) or
                    Path(args[0]).name.casefold() == command[0].casefold() == 'cmd.exe', 'Unexpected executable override')
            calls.append(command)
        if event == 'open' and args and isinstance(args[0], (str, bytes, os.PathLike)):
            writing = isinstance(args[1], str) and any(c in args[1] for c in 'wax+') or \
                isinstance(args[2], int) and args[2] & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND)
            if writing: require(within(os.fsdecode(args[0]), root) or within(os.fsdecode(args[0]), STAGE), 'Write escaped owned test outputs')
        if event in ('os.remove', 'os.rmdir', 'os.mkdir', 'os.rename', 'os.chmod', 'os.link', 'os.symlink'):
            for target in (args[:2] if event in ('os.rename', 'os.link', 'os.symlink') else args[:1]):
                if isinstance(target, (str, bytes, os.PathLike)):
                    require(within(os.fsdecode(target), root), 'Mutation escaped owned build root')
        if event.startswith(('ctypes.dlopen', 'socket.', 'urllib.', 'http.client.')) or event in ('os.system', 'os.startfile', 'os.startfile/2'):
            raise RuntimeError('Network, dynamic loading and interactive launches are forbidden during tests')
    sys.addaudithook(audit)
    root.mkdir()
    generated = generate(root/'SdkTypeArrayWriters.h')
    (STAGE/'build_started.json').write_text(json.dumps(dict(build_root=str(root), inputs=inputs, protected=protected), indent=2), encoding='utf-8')
    results, retired, public_probe = [], [], None
    try:
        environment64, selected = environment_for(VS, 'x64', root)
        require(key(selected) == key(COMPILER), 'Compiler selection changed')
        for arch, flavor, optimization in (('x86', 'O2', ['/O2']), ('x64', 'O2', ['/O2']), ('x64', 'Od', ['/Od', '/RTC1'])):
            out = root/(arch+'_'+flavor)
            out.mkdir()
            sdk = PROJECT/('Source/SDK_BNW_Original' if arch == 'x86' else 'Source/SDK_BNW_x64')
            if arch == 'x86':
                env = {k.upper(): v for k, v in os.environ.items()}
                env['INCLUDE'] = str(VC9/'include')+';'+str(WIN7/'Include')
                env['LIB'] = str(VC9/'lib')+';'+str(WIN7/'Lib')
                env['PATH'] = ';'.join([str(VC9/'bin'), str(VC9.parent/'Common7/IDE'), str(WIN7/'bin'), env.get('PATH', '')])
                compiler = CL86
            else: env, compiler = environment64.copy(), COMPILER
            env['VSLANG'] = '1033'
            # Avoid compiler scratch files outside this content-addressed build.
            env['TMP'] = env['TEMP'] = str(out)
            includes = [sdk/'FirePlace/include', sdk/'CvGameCoreDLLUtil/include']
            own_includes = [PROJECT/'Source/Providers/Streams', PROJECT/'Source/Porting', root]
            flags = ['/nologo', '/EHsc', '/MD', '/fp:strict', '/D_CRT_SECURE_NO_WARNINGS', '/DFINAL_RELEASE',
                '/D_SECURE_SCL=0', '/D_HAS_ITERATOR_DEBUGGING=0', *optimization]
            # VC9 interprets an unchanged SDK copyright byte through CP949.
            # Suppress that encoding-only legacy warning; retain its first receipt.
            flags += (['/W3', '/wd4819']+[f'/I"{p}"' for p in includes+own_includes]) if arch == 'x86' else (
                ['/std:c++14', '/W4', '/WX', '/D_SILENCE_STDEXT_HASH_DEPRECATION_WARNINGS', '/external:W0']+
                [f'/external:I"{p}"' for p in includes]+[f'/I"{p}"' for p in own_includes])
            sources = [TEST]+([PROJECT/'Tests/sdk_stream_reference_host.cpp'] if arch == 'x86' else [])
            objects, dependencies, logs = [], [], []
            for source in sources:
                obj, response = out/(source.stem+'.obj'), out/(source.stem+'.rsp')
                dep = out/(source.stem+'.dependencies.json')
                args = [*flags, '/c', f'"{source}"', f'/Fo"{obj}"']
                args += ['/showIncludes'] if arch == 'x86' else [f'/sourceDependencies "{dep}"']
                response.write_text('\n'.join(args)+'\n', encoding='ascii')
                command = [str(compiler), '@'+str(response)]
                allowed.add(tuple(command))
                built = run(command, cwd=out, env=env, timeout=120)
                text = (built.stdout+built.stderr).decode('mbcs', errors='replace')
                log = STAGE/(arch+'_'+flavor+'_'+source.stem+'.log')
                log.write_text(text, encoding='utf-8')
                require(built.returncode == 0 and not re.search(r'\bwarning\s+[A-Z]+\d+', text, re.I), 'Compile failed: '+log.name)
                if arch == 'x64':
                    data = json.loads(dep.read_text(encoding='utf-8-sig'))['Data']
                    needed = [root/'SdkTypeArrayWriters.h', *HEADERS, PROJECT/'Source/Porting/CvCheckedNarrow.h']
                    require(key(data['Source']) == key(source) and all(any(key(x) == key(h) for x in data['Includes']) for h in needed),
                            'Actual source/header dependency mismatch')
                    dependencies.append(artifact(dep))
                elif source == TEST: require(str(root/'SdkTypeArrayWriters.h').casefold() in text.casefold(), 'Original writer header was not consumed')
                objects.append(artifact(obj)); logs.append(artifact(log))
            exe, linkmap = out/'SdkTypeArrayCountTests.exe', out/'SdkTypeArrayCountTests.map'
            link = ['/nologo', '/INCREMENTAL:NO', '/OPT:REF', '/OPT:ICF', '/MACHINE:'+arch.upper(), '/MAP:'+str(linkmap)]
            link += ['/LTCG'] if arch == 'x86' else ['/Brepro', '/WX']
            # Call LINK directly so VC9's driver cannot strip quotes while
            # forwarding paths containing spaces to another command line.
            command = [str(compiler.with_name('link.exe')), '/OUT:'+str(exe), *[x['path'] for x in objects],
                *[str(p) for p, _ in LIBRARIES[arch]], *link,
                *[n+'.lib' for n in ('kernel32', 'user32', 'advapi32', 'psapi', 'dbghelp', 'ole32', 'shell32', 'winmm')]]
            allowed.add(tuple(command))
            linked = run(command, cwd=out, env=env, timeout=120)
            text = (linked.stdout+linked.stderr).decode('mbcs', errors='replace')
            log = STAGE/(arch+'_'+flavor+'_link.log'); log.write_text(text, encoding='utf-8')
            require(linked.returncode == 0 and not re.search(r'\bwarning\s+[A-Z]+\d+', text, re.I), 'Link failed: '+log.name)
            manifest = exe.with_suffix('.exe.manifest')
            if arch == 'x86' and manifest.exists():
                command = [str(WIN7/'bin/mt.exe'), '-nologo', '-manifest', str(manifest), '-outputresource:'+str(exe)+';1']
                allowed.add(tuple(command)); embedded = run(command, cwd=out, env=env, timeout=30)
                require(embedded.returncode == 0, 'Original CRT manifest embed failed')
            command = [str(exe)]; allowed.add(tuple(command))
            tested = run(command, cwd=out, env=env, timeout=60)
            text = (tested.stdout+tested.stderr).decode('utf-8', errors='replace').strip()
            log = STAGE/(arch+'_'+flavor+'_test.log'); log.write_text(text+'\n', encoding='utf-8')
            require(tested.returncode == 0, 'Native test failed: '+log.name)
            result = json.loads(text)
            require(result['status'] == 'PASS_SDK_TYPE_ARRAY_COUNT' and result['original_count_bytes'] == (4 if arch == 'x86' else 8)
                and result['candidate_count_bytes'] == (0 if arch == 'x86' else 4)
                and result['legacy64_count_bytes'] == (0 if arch == 'x86' else 8)
                and all(result[name] is False for name in ('gamecore_loaded', 'window_created', 'user_saves_accessed',
                    'complete_save_validated', 'ruleset_compatibility_verified', 'retail_supporting_placement_verified')), 'Native ABI result scope differs')
            if arch == 'x64': require(result['supporting_truncations'] > 1000, 'Missing Supporting adversarial tests')
            mapping = linkmap.read_text(encoding='mbcs', errors='replace')
            require('FMemoryStream' in mapping and ('FireWorksWin32' if arch == 'x86' else 'ZeroSis_Streams_x64') in mapping,
                    'Link map does not bind the actual SDK stream library')
            results.append(dict(arch=arch, flavor=flavor, executable=artifact(exe), pe=pe_header(exe), imports=imports(exe),
                objects=objects, dependencies=dependencies, map=artifact(linkmap), compile_logs=logs, test_log=artifact(log), test=result))
            if arch == 'x64':
                command = [str(exe), '--public']; allowed.add(tuple(command))
                tested = subprocess.run(command, cwd=out, env=env, input=public, capture_output=True, timeout=60,
                    creationflags=subprocess.CREATE_NO_WINDOW)
                text = (tested.stdout+tested.stderr).decode('utf-8', errors='replace').strip()
                log = STAGE/(arch+'_'+flavor+'_public.log'); log.write_text(text+'\n', encoding='utf-8')
                probe = dict(returncode=tested.returncode, log=artifact(log), result=json.loads(text))
                if tested.returncode == 0:
                    row = probe['result']['public']
                    require(row['team_count'] == 64 and row['teams_offset'] == 1695150 and row['supporting_at_map_rejected'] is True,
                            'Public sequential framing witness changed')
                    begin, end = row['teams_offset'], row['teams_end']
                    require(begin+row['teams_bytes'] == end <= len(public), 'Noncontiguous Team batch')
                    probe['span_sha256'] = hashlib.sha256(public[begin:end]).hexdigest()
                    probe['unparsed_following_bytes'] = len(public)-end
                if public_probe is not None:
                    require(probe['result'] == public_probe['result'], 'Optimized/checked public observations differ')
                public_probe = probe
                results[-1]['public_probe'] = probe
        require(inputs == [artifact(x['path']) for x in inputs] and protected == [artifact(x['path']) for x in protected],
                'Inputs or protected runtime/settings evidence changed')
        for path in [*[Path(o['path']) for r in results for o in r['objects']], setup]:
            info = path.stat()
            require(within(path, root) and info.st_nlink == 1 and not info.st_file_attributes & 0x400, 'Unexpected cleanup identity')
            row = dict(**artifact(path), file_identity=[info.st_dev, info.st_ino], mtime_ns=info.st_mtime_ns)
            require(artifact(path) == {k:row[k] for k in ('path','bytes','sha256')}, 'Intermediate changed before cleanup')
            path.unlink(); retired.append(row)
        report = dict(schema='zerosis.sdk.vector_count_abi.v1', status='PASS_SDK_VECTOR_COUNT_ABI_COMPONENT',
            utc=datetime.now(timezone.utc).isoformat(), build_root=str(root), inputs=inputs, compilers=compilers, generated_extracts=generated,
            results=results, protected=protected, protected_unchanged=True, child_commands=[list(x) for x in calls],
            retired_intermediates=retired, retired_logical_bytes=sum(r['bytes'] for r in retired),
            public_teams_framed=public_probe['returncode'] == 0, public_inflated_input_bytes=len(public), public_inflated_sha256=OUTPUT_SHA,
            public_save_or_body_retained=False, original_install_or_user_saves_accessed=False, host_gamecore_or_hwnd_executed=False,
            full_sdk_recompiled=False, integrated_into_current_host=False, sdk_restore_verified=False, full_engine_goal_complete=False)
        REPORT.write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
        print(json.dumps(dict(status=report['status'], checks=[r['test']['checks'] for r in results],
            public_probe=public_probe['result'], retired_bytes=report['retired_logical_bytes'], report=artifact(REPORT))))
    except BaseException as error:
        (STAGE/'failed_attempt.json').write_text(json.dumps(dict(status='FAILED_SDK_VECTOR_COUNT_TEST',
            error=type(error).__name__+': '+str(error), build_root=str(root), inputs=inputs, completed_modes=results,
            protected_unchanged=protected == [artifact(x['path']) for x in protected]), indent=2)+'\n', encoding='utf-8')
        raise


if __name__ == '__main__':
    main()
