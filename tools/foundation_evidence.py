"""Provenance and scope gate for the actual SDK-shaped x64 foundation provider."""
import json
from pathlib import Path
from collect_baseline import PROJECT,digest,pe_header,read_text

def validate(build_path):
    build_path=Path(build_path).resolve();b=json.loads(build_path.read_text(encoding='utf-8'))
    cpath=PROJECT/'evidence/foundation/conformance.json';c=json.loads(cpath.read_text(encoding='utf-8'))
    artifacts=[*b['sources'],*b['sdk_inputs'],b['sdk_manifest'],c['build'],c['fixture'],*c['outputs'],
        *c['support_inputs'],c['patch_specification'],*[r['log'] for r in c['runs']],c['dependency_inspector'],
        *[r['log'] for r in c['direct_import_audits']]]
    for arch in ('x86','x64'):
        a=b[arch]
        artifacts += [a['executable'],*a['libraries'],a['map'],a['compiler'],*a['objects'],*a['logs'],*a['responses']]
        if pe_header(Path(a['executable']['path']))['architecture']!=arch:
            raise RuntimeError('Foundation harness architecture mismatch')
    if any(not Path(a['path']).is_file() or digest(Path(a['path']))!=a['sha256'] for a in artifacts):
        raise RuntimeError('Foundation source/build/reference/conformance artifact changed')
    if (b['status']!='FOUNDATION_PROVIDERS_BUILT' or b['runtime']!='/MD' or b['x64']['warning_codes']
        or b['x86']['warning_codes']!=['C4819'] or '/WX' not in b['x64']['flags']
        or c['status']!='SDK_FOUNDATION_CONFORMANCE_PASS' or c['failures']
        or len(c['direct_import_audits'])!=2
        or any(any(name in dll.lower() for name in ('cvgame','lua51','steam_api','fireworks')) for audit in c['direct_import_audits'] for dll in audit['direct_dependencies'])
        or Path(c['build']['path']).resolve()!=build_path or len(c['runs'])!=13 or any(r['returncode'] for r in c['runs'])
        or c['crc_cases']!=8981 or c['crc_results_per_architecture']!=35924 or c['crc_layouts']!=9 or c['crc_layout_bytes']!=1032
        or c['crc_invalid_input_rejections']!=4 or c['lock_workers']!=[1,2,4]
        or c['protected_increments_per_architecture']!=140000 or c['lock_lifetimes_per_architecture']!=512
        or c['clock_bracket_checks']!={'x86':384,'x64':384} or c['clock_worker_reads_per_architecture']!=80000
        or c['x64_concurrent_clock_first_use_workers']!=8
        or c['allocations']!={'x86':{'cases':378,'above_4gb':0,'invalid_parameter_callbacks':3},
            'x64':{'cases':378,'above_4gb':378,'invalid_parameter_callbacks':0}}
        or c['allocation_thread_workers']!=4 or c['threaded_allocations_per_architecture']!=4096
        or c['native_allocation_overflow_rejections']!=1
        or len(b['x64']['objects'])!=4
        or any(int.from_bytes(Path(o['path']).read_bytes()[:2],'little')!=0x8664 for o in b['x64']['objects'])
        or any((b['game_launched'],c['game_launched'],c['game_multicore_verified'],c['game_performance_verified']))):
        raise RuntimeError('Invalid foundation provider contract evidence')
    maptext=read_text(Path(b['x86']['map']['path']))
    if len(c['sdk_map_proof'])<18 or any(line not in maptext for line in c['sdk_map_proof']):
        raise RuntimeError('Actual SDK foundation linkage not proven')
    return b,c,{'name':'Foundation','library':b['x64']['libraries'][0],
        'build_report':{'path':str(build_path),'sha256':digest(build_path)},
        'conformance':{'path':str(cpath),'sha256':digest(cpath)},'runtime':'/MD',
        'scope':'CRC_LOCK_CLOCK_AND_CRT_ALIGNED_MEMORY_COMPONENTS_NOT_GAME_RUNTIME_OR_LEGACY_HOST_HEAP'}
