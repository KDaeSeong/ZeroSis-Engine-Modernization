"""Link an isolated shared-facts PlotFoundValue candidate onto the retained CitySite SDK.

Only two SDK objects and one new bridge are compiled. No PCH is copied/used,
no GameCore is loaded, and no SDK/Stage/MODS deployment pointer is changed.
"""
from __future__ import annotations

import argparse
import ast
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import shutil
import uuid

from collect_baseline import PROJECT, digest, pe_header
from native_build import environment_for, run
from probe_world_builder import artifact
from verify_world_builder_map_object import check_artifacts

BASE_ID = '20261001T135932Z_86b1d2704654'
BASE_REPORT = PROJECT / 'evidence/city_site_sdk' / BASE_ID / 'build_result.json'
SDK = PROJECT / 'Source/SDK_BNW_x64/CvGameCoreDLL_Expansion2'
VS = Path(r'C:\Program Files\Microsoft Visual Studio\2022\Community')
SOURCE = PROJECT / 'Source/Concurrency'


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def replace_once(text, old, new, label):
    require(text.count(old) == 1, 'Non-unique source patch: ' + label)
    return text.replace(old, new, 1)


def function_span(text, declaration):
    begin = text.index(declaration)
    opening = text.index('\n{', begin) + 1
    # These pinned SDK definitions have an unindented closing brace; all nested
    # braces are indented. Reject changes to that known source shape.
    end = text.index('\n}', opening) + 2
    body = text[opening:end]
    require(body.count('{') == body.count('}'), 'Pinned SDK function brace shape changed')
    return begin, opening, end


def prepare_header(data):
    text = data.decode('cp1252')
    anchor = 'class CvSiteEvaluatorForSettler: public CvCitySiteEvaluator'
    begin = text.index(anchor)
    end = text.index('\n};', begin)
    block = text[begin:end]
    old = '\tint PlotFoundValue(CvPlot* pPlot, CvPlayer* pPlayer, YieldTypes eYield = NO_YIELD, bool bCoastOnly=true);'
    new = old + ('\n\t// Nonvirtual candidate method; original layout and vtable stay intact.\n'
                 '\tbool ZeroSisOwnedSharedFoundValues(CvPlayer* player, unsigned int workers,\n'
                 '\t\tunsigned int callId, unsigned long long totalStart);')
    block = replace_once(block, old, new, 'nonvirtual settler method')
    text = text[:begin] + block + text[end:]
    text += '''

#include "FoundValueSharedBridge.h"
unsigned int ZeroSisFoundValueWorkerCount();
unsigned long long ZeroSisFoundValueNowUs();
bool ZeroSisFoundValueTraceEnabled();
void ZeroSisTraceFoundValues(CvPlayer* player, const int* orderedValues,
    bool startingLocation, unsigned int callId, unsigned int workers,
    unsigned int helperPlots, unsigned long long snapshotUs,
    unsigned long long workerUs, unsigned long long shadowUs,
    unsigned long long reductionUs, unsigned long long totalUs,
    const ZeroSisFoundValueMetrics* metrics);
'''
    return text.encode('cp1252')


def prepare_player(data):
    text = data.decode('cp1252')
    begin, opening, end = function_span(text, 'void CvPlayerAI::AI_updateFoundValues(bool bStartingLoc)')
    body = text[opening:end]
    prologue = '''{
    if(gDLL == NULL || !gDLL->IsGameCoreThread() || !gDLL->HasGameCoreLock())
        throw std::logic_error("AI_updateFoundValues requires the game-core thread and lock");
    static unsigned int zeroSisCallId = 0;
    const unsigned int callId = ++zeroSisCallId;
    const unsigned long long totalStart = ZeroSisFoundValueNowUs();
    const unsigned int requested = ZeroSisFoundValueWorkerCount();
    if(!bStartingLoc && requested != 0 &&
        GC.getGame().GetSettlerSiteEvaluator()->ZeroSisOwnedSharedFoundValues(this, requested, callId, totalStart)) return;
    const bool diagnostic = ZeroSisFoundValueTraceEnabled();
    std::vector<int> diagnosticValues(diagnostic ? static_cast<size_t>(GC.getMap().numPlots()) : 0, -1);
'''
    body = prologue + body[1:]
    line = '\t\t\t\tpLoopPlot->setFoundValue(eID, iValue);'
    body = replace_once(body, line,
        '\t\t\t\tif(diagnostic) diagnosticValues[static_cast<size_t>(iI)] = iValue;\n' + line,
        'non-mutating scalar observation')
    tail = '''
    ZeroSisTraceFoundValues(this, diagnosticValues.empty() ? NULL : &diagnosticValues[0],
        bStartingLoc, callId, 0, 0, 0, 0, 0, 0, ZeroSisFoundValueNowUs() - totalStart, NULL);
}'''
    body = body[:-1] + tail
    return (text[:opening] + body + text[end:]).encode('cp1252')


def tool_closure():
    pending = [Path(__file__).resolve()]
    found = set()
    while pending:
        path = pending.pop()
        if path in found:
            continue
        found.add(path)
        for node in ast.walk(ast.parse(path.read_text(encoding='utf8'))):
            modules = [node.module] if isinstance(node, ast.ImportFrom) and node.module and node.level == 0 else \
                      [item.name for item in node.names] if isinstance(node, ast.Import) else []
            for name in modules:
                candidate = PROJECT / 'tools' / (name.split('.')[0] + '.py')
                if candidate.is_file() and candidate.resolve() not in found:
                    pending.append(candidate.resolve())
    return sorted(found)


def freeze(source, directory, label):
    target = directory / label / source.name
    target.parent.mkdir(parents=True, exist_ok=True)
    before = digest(source)
    shutil.copy2(source, target)
    require(digest(target) == before == digest(source), 'Input changed while freezing: ' + str(source))
    return target, {'original_path': str(source), **artifact(target)}


def dependencies(path, source):
    data = json.loads(path.read_text(encoding='utf8'))['Data']
    require(Path(data['Source']).resolve() == source.resolve(), 'Compiler dependency source differs')
    return list(dict.fromkeys([source.resolve(), *(Path(value).resolve(strict=True) for value in data['Includes'])]))


def warnings(output):
    return re.findall(r'\bwarning\s+(?:C|LNK)\d+:[^\r\n]*', output.decode('mbcs', errors='replace'), re.I)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prepare-only', action='store_true')
    parser.add_argument('--kernel-component', type=Path, default=PROJECT / 'evidence/found_value_shared_scores/20261002T154249Z_2930c8a3f4/conformance.json')
    parser.add_argument('--bridge-component', type=Path, required=True)
    parser.add_argument('--capture-component', type=Path, required=True)
    parser.add_argument('--cpu-trace-component', type=Path, default=PROJECT / 'evidence/found_value_cpu_trace/20261002T151042Z_0d8765878529/conformance.json')
    args = parser.parse_args()
    base = json.loads(BASE_REPORT.read_text(encoding='utf8')); check_artifacts(base)
    require(base.get('status') == 'CITY_SITE_SDK_CANDIDATE_LINKED' and base.get('build_id') == BASE_ID,
            'Retained CitySite base is not the exact isolated linked candidate')
    require(base.get('active_sdk_updated') is False and base.get('stage_updated') is False,
            'Base report claims active SDK/Stage mutation')
    manifest_path = Path(base['accepted_manifest']['path']).resolve()
    accepted_path = Path(base['frozen_accepted_result']['path']).resolve()
    manifest_initial_hash, accepted_initial_hash = digest(manifest_path), digest(accepted_path)
    manifest = json.loads(manifest_path.read_text(encoding='utf8'))
    accepted = json.loads(accepted_path.read_text(encoding='utf8'))
    require(digest(manifest_path) == manifest_initial_hash and digest(accepted_path) == accepted_initial_hash,
            'Accepted manifest/result changed while being read')
    names = ('CvPlayerAI.cpp', 'CvSiteEvaluationClasses.cpp', 'CvSiteEvaluationClasses.h', 'CvGameCoreDLLPCH.h')
    originals = {}
    for name in names:
        path = SDK / name
        rows = [row for row in manifest if row.get('relative_path') == 'CvGameCoreDLL_Expansion2/' + name]
        require(len(rows) == 1 and Path(rows[0]['port']).resolve() == path.resolve() and
                digest(path) == rows[0]['port_sha256'], 'Accepted SDK input drifted: ' + name)
        originals[name] = {'original_source_path': str(path), 'original_source_sha256': digest(path), 'original_source_size': path.stat().st_size}
    kernel_proof_path = args.kernel_component.resolve(strict=True)
    bridge_proof_path = args.bridge_component.resolve(strict=True)
    capture_proof_path = args.capture_component.resolve(strict=True)
    cpu_proof_path = args.cpu_trace_component.resolve(strict=True)
    kernel_proof = json.loads(kernel_proof_path.read_text(encoding='utf8')); check_artifacts(kernel_proof)
    bridge_proof = json.loads(bridge_proof_path.read_text(encoding='utf8')); check_artifacts(bridge_proof)
    require(kernel_proof.get('status') == 'FOUND_VALUE_SHARED_SCORES_ORIGINAL_BODY_DIFFERENTIAL_PASS', 'Shared kernel component is not passing')
    require(bridge_proof.get('status') == 'FOUND_VALUE_SHARED_BRIDGE_CPP14_CPP17_PASS', 'Shared bridge component is not passing')
    capture_proof = json.loads(capture_proof_path.read_text(encoding='utf8')); check_artifacts(capture_proof)
    require(capture_proof.get('status') == 'FOUND_VALUE_SHARED_SDK_CAPTURE_EXACT_BODY_MOCK_PASS', 'Shared capture component is not passing')
    cpu_proof = json.loads(cpu_proof_path.read_text(encoding='utf8')); check_artifacts(cpu_proof)
    require(cpu_proof.get('status') == 'FOUND_VALUE_CPU_TRACE_OFFLINE_PASS', 'Found CPU trace component is not passing')
    require(digest(SOURCE / 'FoundValueSharedScores.h') == '8358736a84e2c396480a6028aabe40e553fde46b86301c8e142f09bfecbeb7d0',
            'Shared kernel differs from its frozen passing source-oracle component')
    require(digest(SOURCE / 'FoundValueScores.h') == '29700a1073545e0ea6c9deb81c73f2837dfedd7b8c1a6269d1f4f3b3c7f84eaa',
            'Kernel differs from its exact source-oracle component')
    run_id = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ_') + uuid.uuid4().hex[:12]
    build = PROJECT / 'Build/FoundValueSharedSDK' / run_id
    evidence = PROJECT / 'evidence/found_value_shared_sdk' / run_id
    frozen = evidence / 'frozen'
    build.mkdir(parents=True, exist_ok=False); frozen.mkdir(parents=True, exist_ok=False)
    sources = [*(SDK / name for name in names), *(SOURCE / name for name in
        ('FoundValueScores.h', 'FoundValueScoreBridge.h', 'FoundValueSharedScores.h', 'FoundValueSharedBridge.h', 'FoundValueSharedBridge.cpp', 'FoundValueSharedSdkCapture.inc', 'FoundValueCpuTrace.h', 'OrderedBatch.h')),
        BASE_REPORT, manifest_path, accepted_path, kernel_proof_path, bridge_proof_path, capture_proof_path, cpu_proof_path, *tool_closure()]
    sources = list(dict.fromkeys(path.resolve() for path in sources))
    before = {str(path): digest(path) for path in sources}
    require(before[str(manifest_path)] == manifest_initial_hash and before[str(accepted_path)] == accepted_initial_hash,
            'Accepted manifest/result changed before preparation')
    refs, paths = [], {}
    for index, source in enumerate(sources):
        target, row = freeze(source, frozen, f'{index:03d}')
        refs.append(row); paths[source] = target
    manifest = json.loads(paths[manifest_path].read_text(encoding='utf8'))
    accepted = json.loads(paths[accepted_path].read_text(encoding='utf8'))
    frozen_base, row = freeze(Path(base['gamecore']['path']), frozen, 'base_city_site_gamecore'); refs.append(row)
    frozen_recipe, row = freeze(Path(base['gamecore_compile_recipe']['path']), frozen, 'accepted_recipe'); refs.append(row)
    frozen_link, row = freeze(Path(base['link_response']['path']), frozen, 'base_link_recipe'); refs.append(row)
    source_dir = build / 'Source/CvGameCoreDLL_Expansion2'; source_dir.mkdir(parents=True)
    concurrency = build / 'Source/Concurrency'; concurrency.mkdir()
    player = source_dir / 'CvPlayerAI.cpp'; player.write_bytes(prepare_player(paths[SDK / 'CvPlayerAI.cpp'].read_bytes()))
    site = source_dir / 'CvSiteEvaluationClasses.cpp'
    site.write_bytes(paths[SDK / 'CvSiteEvaluationClasses.cpp'].read_bytes() + b'\n#include "FoundValueSharedSdkCapture.inc"\n')
    site_header = source_dir / 'CvSiteEvaluationClasses.h'
    site_header.write_bytes(prepare_header(paths[SDK / 'CvSiteEvaluationClasses.h'].read_bytes()))
    # A small source header copy routes its quoted include to the candidate
    # declaration; no binary PCH is consumed or duplicated.
    shutil.copy2(paths[SDK / 'CvGameCoreDLLPCH.h'], source_dir / 'CvGameCoreDLLPCH.h')
    for name in ('FoundValueScores.h', 'FoundValueScoreBridge.h', 'FoundValueSharedScores.h', 'FoundValueSharedBridge.h', 'FoundValueSharedBridge.cpp', 'FoundValueSharedSdkCapture.inc', 'FoundValueCpuTrace.h', 'OrderedBatch.h'):
        shutil.copy2(paths[SOURCE / name], concurrency / name)
    flags = [line for line in frozen_recipe.read_text(encoding='utf8').splitlines()
             if not line.startswith('"') and not line.startswith('/Fo') and line != '/MP4' and
             not line.lower().startswith('/yu') and not re.match(r'(?i)^/fp(?:"| )', line)]
    flags.append('/source-charset:.1252')
    require('/std:c++14' in flags and not any(line.lower().startswith('/yu') for line in flags), 'Accepted SDK recipe changed')
    compile_rows = [
        ('CvPlayerAI_baseline', paths[SDK / 'CvPlayerAI.cpp'], flags),
        ('CvSiteEvaluationClasses_baseline', paths[SDK / 'CvSiteEvaluationClasses.cpp'], flags),
        ('CvPlayerAI', player, flags + [f'/I"{concurrency}"']),
        ('CvSiteEvaluationClasses', site, flags + [f'/I"{concurrency}"']),
        ('FoundValueSharedBridge', concurrency / 'FoundValueSharedBridge.cpp',
         ['/nologo', '/c', '/std:c++17', '/EHsc', '/MD', '/O2', '/W4', '/WX', '/fp:strict', '/utf-8', f'/I"{concurrency}"']),
    ]
    report = {'status': 'FOUND_VALUE_SHARED_SDK_CANDIDATE_PREPARED_NOT_BUILT', 'build_id': run_id,
        'base_city_site_build_id': BASE_ID, 'base_city_site_build_report': artifact(paths[BASE_REPORT]),
        'base_city_site_build': artifact(frozen_base),
        'base_city_site_report_original': {'original_source_path': str(BASE_REPORT), 'original_source_sha256': digest(BASE_REPORT)},
        'original_sdk_sources': originals, 'frozen_inputs': refs, 'input_hashes_before': before,
        'candidate_sources': [artifact(path) for path in (player, site, site_header, source_dir / 'CvGameCoreDLLPCH.h')],
        'builder': artifact(paths[Path(__file__).resolve()]),
        'builder_original': {'original_source_path': str(Path(__file__).resolve()), 'original_source_sha256': digest(Path(__file__))},
        'kernel': artifact(paths[SOURCE / 'FoundValueSharedScores.h']),
        'dense_kernel': artifact(paths[SOURCE / 'FoundValueScores.h']),
        'input_layout': 'SHARED_FACTS',
        'input_abi_sizes': {'common': 240, 'plot': 116, 'candidate': 1848},
        'accepted_manifest_frozen': artifact(paths[manifest_path]),
        'accepted_result_frozen': artifact(paths[accepted_path]),
        'bridge_source': artifact(paths[SOURCE / 'FoundValueSharedBridge.cpp']),
        'bridge_header': artifact(paths[SOURCE / 'FoundValueSharedBridge.h']),
        'dense_abi_header': artifact(paths[SOURCE / 'FoundValueScoreBridge.h']),
        'cpu_trace_header': artifact(paths[SOURCE / 'FoundValueCpuTrace.h']),
        'cpu_trace_provider_guid': '{49a604e1-6c99-4e01-b41d-73694f2290a6}',
        'cpu_trace_provider_name': 'ZeroSis.FoundValueCpuTrace',
        'capture_source': artifact(paths[SOURCE / 'FoundValueSharedSdkCapture.inc']),
        'kernel_component': artifact(paths[kernel_proof_path]), 'bridge_component': artifact(paths[bridge_proof_path]),
        'capture_component': artifact(paths[capture_proof_path]), 'cpu_trace_component': artifact(paths[cpu_proof_path]),
        'compile_recipe': artifact(frozen_recipe), 'base_link_response': artifact(frozen_link),
        'source_charset': 'Windows-1252 SDK; UTF-8 standalone bridge', 'pch_reused': False, 'pch_copied': False,
        'active_sdk_updated': False, 'stage_updated': False, 'mods_updated': False, 'gamecore_loaded': False,
        'found_value_worker_environment': 'ZEROSIS_FOUND_VALUE_WORKERS', 'found_value_default_workers': 0,
        'found_value_diagnostic_environment': 'ZEROSIS_FOUND_VALUE_TRACE', 'found_value_trace_default_enabled': False,
        'scalar_shadow_required_for_owned_commit': True, 'class_data_or_vtable_layout_changed': False,
        'diagnostics_use_owned_write_values_not_lazy_getFoundValue': True,
        'shared_input_capture_on_owner_only': True, 'geometry_preserves_source_scan_order_and_duplicates': True,
        'found_value_cpu_trace_environment': 'ZEROSIS_FOUND_VALUE_CPU_TRACE', 'found_value_cpu_trace_default_enabled': False,
        'performance_improvement_verified': False, 'complete_engine_multicore_verified': False}
    code = 0
    try:
        if not args.prepare_only:
            env, compiler_name = environment_for(VS, 'x64', build)
            env['VSLANG'] = '1033'
            compiler = Path(compiler_name)
            tool_paths = [compiler, compiler.with_name('link.exe'), compiler.with_name('dumpbin.exe'),
                          *compiler.parent.glob('*.dll'), VS / 'VC/Auxiliary/Build/vcvars64.bat', build / 'read_build_environment.cmd']
            tool_before = {str(path): digest(path) for path in tool_paths}
            include_roots = [Path(value).resolve() for value in env.get('INCLUDE', '').split(';') if value]
            discovered = set()
            executions = []
            baseline_warnings = {}

            def compile_one(name, source, options, phase):
                directory = build / phase; directory.mkdir(exist_ok=True)
                obj, dep, rsp = (directory / (name + suffix) for suffix in ('.obj', '.dependencies.json', '.rsp'))
                rsp.write_text('\n'.join([*options, f'/Fo"{obj}"', f'/sourceDependencies "{dep}"', f'"{source}"']) + '\n', encoding='utf8')
                result = run([compiler, '@' + str(rsp)], cwd=build, env=env, timeout=180)
                log = evidence / (phase + '_' + name + '.log'); log.write_bytes(result.stdout + result.stderr)
                require(result.returncode == 0 and obj.is_file() and dep.is_file(), 'Compiler failed: ' + str(log))
                return {'name': name, 'phase': phase, 'source': artifact(source), 'object': artifact(obj),
                        'response': artifact(rsp), 'log': artifact(log), 'warnings': warnings(result.stdout + result.stderr),
                        'dependencies': dependencies(dep, source), 'dependency_report': artifact(dep)}

            # Discovery compiles never become linked output. Their exact include
            # closure is copied before final builds, which reject any new header.
            for name, source, options in compile_rows:
                row = compile_one(name, source, options, 'discovery')
                discovered.update(row['dependencies']); executions.append(row)
            project_overlay = frozen / 'dependencies/project_source'
            overlays = [frozen / 'dependencies/includes' / f'{index:03d}' for index in range(len(include_roots))]
            for path in (project_overlay, *overlays): path.mkdir(parents=True, exist_ok=True)
            closure = []
            final_allowed = {}
            for dependency in sorted(discovered):
                targets = []
                if dependency.is_relative_to((PROJECT / 'Source').resolve()):
                    targets = [project_overlay / dependency.relative_to((PROJECT / 'Source').resolve())]
                else:
                    targets = [overlay / dependency.relative_to(root) for root, overlay in zip(include_roots, overlays)
                               if dependency.is_relative_to(root)]
                if not targets:
                    require(dependency.is_relative_to(build.resolve()) or dependency.is_relative_to(frozen.resolve()),
                            'Discovered input is outside owned sources/include roots: ' + str(dependency))
                    targets = [dependency]
                original_hash = digest(dependency)
                for target in targets:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    if target != dependency: shutil.copy2(dependency, target)
                    require(digest(target) == original_hash, 'Frozen header differs: ' + str(dependency))
                    closure.append({'original_path': str(dependency), **artifact(target)})
                    final_allowed[target.resolve()] = original_hash
            require(bool(closure), 'Discovered compiler closure is empty')
            closure_before = {str(path): digest(path) for path in discovered}
            env['INCLUDE'] = ';'.join(str(path) for path in overlays)
            final_options = []
            for name, source, options in compile_rows:
                mapped = []
                for option in options:
                    match = re.fullmatch(r'/I"([^"]+)"', option, re.I)
                    if match and Path(match[1]).resolve().is_relative_to((PROJECT / 'Source').resolve()):
                        option = f'/I"{project_overlay / Path(match[1]).resolve().relative_to((PROJECT / "Source").resolve())}"'
                    mapped.append(option)
                final_options.append((name, source, mapped))
            objects = {}
            for name, source, options in final_options:
                row = compile_one(name, source, options, 'final')
                for dependency in row['dependencies']:
                    require(dependency in final_allowed and digest(dependency) == final_allowed[dependency],
                            'Final build read an unfrozen/new header: ' + str(dependency))
                if name.endswith('_baseline'):
                    baseline_warnings[name.removesuffix('_baseline')] = row['warnings']
                elif name == 'FoundValueSharedBridge':
                    require(not row['warnings'], 'New bridge warnings: ' + str(row['log']))
                else:
                    require(row['warnings'] == baseline_warnings[name], 'Candidate changed baseline warnings: ' + str(row['log']))
                    row['warnings_exactly_match_baseline_messages'] = True
                objects[name] = Path(row['object']['path']); executions.append(row)
            link_text = frozen_link.read_text(encoding='utf8')
            old_objects = {}
            for name in ('CvPlayerAI', 'CvSiteEvaluationClasses'):
                rows = [row for row in accepted['objects'] if Path(row['path']).name == name + '.obj']
                require(len(rows) == 1, 'Accepted object inventory differs: ' + name)
                old = rows[0]; require(digest(Path(old['path'])) == old['sha256'], 'Accepted object changed')
                old_objects[name] = old
                link_text = replace_once(link_text, '"' + old['path'] + '"', '"' + str(objects[name]) + '"', name + ' object replacement')
            link_text += '\n"' + str(objects['FoundValueSharedBridge']) + '"\n'
            advapi = next((Path(root) / 'advapi32.lib' for root in env.get('LIB', '').split(';')
                           if (Path(root) / 'advapi32.lib').is_file()), None)
            require(advapi is not None, 'Found ETW provider requires advapi32.lib')
            frozen_advapi, advapi_ref = freeze(advapi.resolve(), frozen, 'found_etw_advapi32')
            refs.append(advapi_ref)
            link_text += '"' + str(frozen_advapi) + '"\n'
            dll = build / 'CvGameCoreDLL_Expansion2_x64.dll'
            for option, target in (('OUT', dll), ('IMPLIB', dll.with_suffix('.lib')), ('MAP', build / 'CvGameCoreDLL_Expansion2_x64.map')):
                link_text, count = re.subn(r'^/' + option + r':[^\r\n]+', lambda _: f'/{option}:"{target}"', link_text, flags=re.M)
                require(count == 1, 'Link output option is not unique: ' + option)
            link_rsp = build / 'link.rsp'; link_rsp.write_text(link_text, encoding='utf8')
            link_paths = [Path(path) for path in re.findall(r'^"([^"\r\n]+\.(?:obj|lib))"$', link_text, re.M | re.I)]
            definition = re.search(r'^/DEF:"([^"]+)"$', link_text, re.M | re.I)
            require(definition is not None, 'Base link lacks a module definition')
            link_paths.append(Path(definition[1]))
            link_before = {str(path): digest(path) for path in link_paths}
            linked = run([compiler.with_name('link.exe'), '@' + str(link_rsp)], cwd=build, env=env, timeout=180)
            link_log = evidence / 'link.log'; link_log.write_bytes(linked.stdout + linked.stderr)
            require(linked.returncode == 0 and dll.is_file() and not warnings(linked.stdout + linked.stderr), 'Link failed/warned: ' + str(link_log))
            inspected = run([compiler.with_name('dumpbin.exe'), '/dependents', str(dll)], cwd=build, env=env, timeout=60)
            imports_log = evidence / 'imports.log'; imports_log.write_bytes(inspected.stdout + inspected.stderr)
            imports = re.findall(r'^\s+([\w.-]+\.dll)\s*$', (inspected.stdout + inspected.stderr).decode('ascii', errors='replace'), re.M | re.I)
            require(inspected.returncode == 0 and {'ZeroSisLua51_x64.dll', 'ZeroSisDatabase_x64.dll'} <= set(imports), 'Required shared imports disappeared')
            pe = pe_header(dll); require(pe.get('architecture') == 'x64' and pe.get('is_dll'), 'Linked output is not an x64 DLL')
            link_after = {str(path): digest(path) for path in link_paths}
            tools_after = {str(path): digest(path) for path in tool_paths}
            closure_after = {str(path): digest(path) for path in discovered}
            require(link_before == link_after and tool_before == tools_after and closure_before == closure_after,
                    'A linker/compiler/source dependency changed during the candidate build')
            for row in closure: require(digest(Path(row['path'])) == row['sha256'], 'Frozen compiler input changed')
            serializable = [{**row, 'dependencies': [str(path) for path in row['dependencies']]} for row in executions]
            report.update(status='FOUND_VALUE_SHARED_SDK_CANDIDATE_LINKED', gamecore=artifact(dll), gamecore_pe=pe,
                compiler=artifact(compiler), toolchain_hashes_before=tool_before, toolchain_hashes_after=tools_after,
                source_dependency_closure=closure, dependency_hashes_before=closure_before, dependency_hashes_after=closure_after,
                compiler_dependency_precompile_snapshot_complete=True, final_compiler_reads_only_frozen_discovered_inputs=True,
                build_records=serializable, replaced_objects=old_objects, link_response=artifact(link_rsp),
                link_log=artifact(link_log), link_input_hashes_before=link_before, link_input_hashes_after=link_after,
                imports=imports, imports_log=artifact(imports_log),
                provenance_limit='Inherited linked objects are hash-pinned; implicit linker default libraries, environment setup script transitive dependencies and OS/runtime are not a complete frozen reproducible-build environment.')
        after = {str(path): digest(path) for path in sources}
        require(before == after, 'Builder/source/component inputs changed during preparation/build')
        report.update(input_hashes_after=after, inputs_unchanged=True)
        check_artifacts(report)
    except Exception as error:
        report.update(status='FOUND_VALUE_SHARED_SDK_CANDIDATE_FAILED', error=str(error)); code = 2
    target = evidence / 'build_result.json'
    target.write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n', encoding='utf8')
    if code == 0 and not args.prepare_only:
        pointer = evidence.parent / ('build_result.json.tmp-' + uuid.uuid4().hex)
        shutil.copy2(target, pointer); pointer.replace(evidence.parent / 'build_result.json')
    print(json.dumps({'status': report['status'], 'build': artifact(target), 'error': report.get('error')}, ensure_ascii=False), flush=True)
    return code


if __name__ == '__main__':
    raise SystemExit(main())
