"""Current-source water/height CPU regressions; no legacy driver main is run."""
from pathlib import Path
import argparse
import hashlib
import importlib.util
import json
import os
import re
import sys
sys.dont_write_bytecode=True
ROOT=Path(__file__).absolute().parent
PROJECT=ROOT.parents[3]
sys.path[:0]=[str(PROJECT/'tools'),str(PROJECT/'Tests'),str(ROOT)]
from menu_replay_restoration import build_cxx14
from menu_suite_storage import storage
from native_build import run
from reflection_verify_components import view,helper

PINNED={
    'Tests/original_water_bridge.py':'0abcf90262664524e55620b3a21652b4f7ff1f7153eecb16970d7ca1743bd4f4',
    'tools/civ5_original_water_assets.py':'9a21d1a4d39bceb04b5d55300d1253512cd41a0657086c58f548727935737c67'}
PACKAGE_SHA='2ff227dae9d16398e038e8ea33624940a9581e0eb2d37c3891121fae22c25afc'


def write(path,value):
    assert path.is_relative_to(ROOT) and not path.exists()
    with path.open('x',encoding='utf8') as stream:json.dump(value,stream,indent=2);stream.write('\n')


def closure(paths):
    selected=set(paths);pending=list(paths)
    while pending:
        path=pending.pop()
        for name in re.findall(r'^\s*#include\s+"([^"\r\n]+)"',path.read_text('utf8'),re.M):
            candidate=path.parent/name
            if not candidate.is_file():candidate=PROJECT/'Source/Presentation'/name
            assert candidate.is_file(),str(candidate)
            if candidate not in selected:selected.add(candidate);pending.append(candidate)
    return sorted(selected,key=str)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--attempt',required=True)
    parser.add_argument('--only',choices=['all','bridge'],default='all');args=parser.parse_args()
    assert re.fullmatch('reflection_water_regressions[0-9]{2}',args.attempt)
    stage=ROOT/args.attempt;assert not stage.exists()
    assert not any(os.environ.get(key) for key in ('CL','_CL_','LINK'))
    for name,digest in PINNED.items():assert view.ref(PROJECT/name)['sha256']==digest,name
    driver=PROJECT/'Tests/original_water_bridge.py'
    spec=importlib.util.spec_from_file_location('reflection_water_bridge_goldens_only',driver)
    goldens=importlib.util.module_from_spec(spec);spec.loader.exec_module(goldens)
    package=PROJECT/'Build/OriginalWaterAssets'/PACKAGE_SHA/'water-assets.bin'
    assert goldens.PACKAGE==package and view.ref(package)['sha256']==PACKAGE_SHA
    all_tests=[PROJECT/'Tests/original_water_surface.cpp',PROJECT/'Tests/original_water_bridge.cpp']
    tests=all_tests if args.only=='all' else all_tests[1:]
    carry=None;carry_paths=[]
    if args.only=='bridge':
        previous=ROOT/'reflection_water_regressions01/reflection_result.json'
        assert view.ref(previous)['sha256']=='95bef555790e5f90e0f56a7978262902efe73fbc0925250114f6bca44df42f9d'
        prior=json.loads(previous.read_text('utf8'))
        surface=next(row for row in prior['results'] if row['name']=='original_water_surface')
        assert surface['status']=='PASS_EXISTING_CPU_REGRESSION' and surface['checks']==853718
        surface_paths=closure(all_tests[:1]);old={row['path']:row for row in prior['inputs']}
        for path in surface_paths:assert view.ref(path)==old[str(path)],'Previously tested surface input changed: '+str(path)
        surface_result=previous.parent/'reflection_original_water_surface_result.json'
        assert json.loads(surface_result.read_text('utf8'))==surface
        carry=dict(name='original_water_surface',checks=surface['checks'],status=surface['status'],
            aggregate=view.ref(previous),component=view.ref(surface_result),current_source_closure_unchanged=True,reexecuted=False)
        carry_paths=[previous,surface_result]
    paths=closure(all_tests)+[PROJECT/name for name in PINNED]+[Path(__file__).absolute(),*carry_paths,package]
    inputs=[view.ref(path) for path in paths]
    work=stage/'work';work.mkdir(parents=True)
    write(stage/'reflection_started.json',dict(inputs=inputs,scope='NoNative0',existing_package_reused_without_copy=True,
        goldens_only=['original_water_bridge.reference_profiles','original_water_bridge.reference_maps'],legacy_python_main_called=False,
        rationale='Surface contour/privacy/LOD plus actual changed AtlasWorldHeight-to-water bridge; unchanged pure topology suite omitted.',
        selection=args.only,carried_forward=carry))
    results=[];fatal=None
    try:
        for source in tests:
            name=source.stem;directory=work/name;directory.mkdir()
            row=dict(name=name,source=view.ref(source),status='STARTED')
            try:
                arguments=[]
                if name=='original_water_bridge':
                    profiles,profile_summary=goldens.reference_profiles(directory)
                    maps,map_summary=goldens.reference_maps(directory)
                    arguments=[str(package),str(profiles),str(maps)]
                    row['independent_reference_profiles']=profile_summary;row['independent_reference_maps']=map_summary
                    row['package']=view.ref(package)
                compiled=build_cxx14(name,directory,stage,source,[PROJECT/'Source/Presentation'])
                executable=Path(compiled['path']);row['build']=compiled;row['imports']=helper.imports(executable)
                row['executed_console']=view.ref(executable)
                done=run([str(executable),*arguments],cwd=directory,timeout=180)
                stdout,stderr=done.stdout.decode('ascii'),done.stderr.decode('ascii')
                console=stage/('reflection_'+name+'_console.txt');console.write_text(stdout+stderr,encoding='ascii')
                row.update(returncode=done.returncode,stdout=stdout.strip(),stderr=stderr.strip(),console=view.ref(console))
                expected=r'PASS_ORIGINAL_WATER_SURFACE checks=(\d+)\s*' if name=='original_water_surface' else r'PASS_ORIGINAL_WATER_BRIDGE checks=(\d+) profile_samples=(\d+) maps=(\d+) height_samples=(\d+) rejections=(\d+)\s*'
                match=re.fullmatch(expected,stdout)
                if done.returncode or stderr or not match:row['status']='FAIL_EXISTING_CPU_REGRESSION'
                else:
                    row['status']='PASS_EXISTING_CPU_REGRESSION';row['checks']=int(match[1])
                    if name=='original_water_bridge':row.update(profile_samples=int(match[2]),maps=int(match[3]),height_samples=int(match[4]),rejections=int(match[5]))
            except BaseException as exc:
                row.update(status='FAIL_CPU_COMPONENT_SETUP_OR_COMPILE',error_type=type(exc).__name__,message=str(exc)[:7000])
            results.append(row)
            write(stage/('reflection_'+name+'_result.json'),row)
        assert [view.ref(path) for path in paths]==inputs,'Current shared source changed during regression'
    except BaseException as exc:
        fatal=dict(error_type=type(exc).__name__,message=str(exc)[:5000])
    finally:
        rows=[]
        for path in sorted(work.rglob('*')):
            if not path.is_file():continue
            info=path.lstat();assert path.resolve()==path and not info.st_file_attributes&0x401 and info.st_nlink==1
            row=view.ref(path);row['allocated_bytes']=storage.allocated(path);rows.append(row)
        write(stage/'reflection_cleanup_plan.json',dict(exact_owned_work=str(work),files=rows))
        for row in rows:
            path=Path(row['path']);assert path.is_relative_to(work)
            assert view.ref(path)=={key:value for key,value in row.items() if key!='allocated_bytes'}
            path.unlink()
        for directory in sorted((p for p in work.rglob('*') if p.is_dir()),key=lambda p:len(p.parts),reverse=True):directory.rmdir()
        work.rmdir()
        write(stage/'reflection_cleanup_result.json',dict(status='PASS_EXACT_OWNED_WATER_REGRESSION_INTERMEDIATES_REMOVED',
            files=len(rows),logical_bytes_removed=sum(row['bytes'] for row in rows),
            allocated_bytes_removed=sum(row['allocated_bytes'] for row in rows),work_absent=not work.exists(),package_unchanged=view.ref(package)==inputs[-1]))
    failed=sum(row['status']!='PASS_EXISTING_CPU_REGRESSION' for row in results)
    result=dict(schema='zerosis.phase12.reflection_water_regressions.v1',
        status='FAIL_CONTROLLED_WATER_REGRESSION_REQUIRES_REVIEW' if failed or fatal else 'PASS_CONTROLLED_WATER_HEIGHT_REGRESSIONS',
        inputs=inputs,results=results,carried_forward=carry,failure_count=failed,fatal=fatal,
        total_checks=sum(row.get('checks',0) for row in results)+(carry['checks'] if carry else 0),
        inputs_unchanged=[view.ref(path) for path in paths]==inputs,legacy_driver_main_called=False,
        native_host_sdk_clr_hwnd_gpu_audio_or_game_executed=False,
        cleanup=view.ref(stage/'reflection_cleanup_result.json'))
    write(stage/'reflection_result.json',result)
    print(json.dumps(dict(status=result['status'],components=[dict(name=row['name'],status=row['status'],checks=row.get('checks'),stderr=row.get('stderr','')) for row in results],output=view.ref(stage/'reflection_result.json'))))
    if failed or fatal:raise SystemExit(1)


if __name__=='__main__':main()
