"""Bounded pure CPU checks of explicit forest, tessellation and camera models."""
from pathlib import Path
import argparse, json, os, re, sys
sys.dont_write_bytecode=True
PROJECT=Path(__file__).absolute().parents[1]
STAGE=PROJECT/'evidence/world_terrain_original/phase10/geometry'
sys.path[:0]=[str(PROJECT/'tools')]
import build_exit_confirm_host as common
from native_build import environment_for, run
from menu_suite_storage import storage

def write_new(path,value):
    with path.open('x',encoding='utf8') as stream:json.dump(value,stream,ensure_ascii=False,indent=1);stream.write('\n')

def main(attempt):
    assert re.fullmatch('[0-9]{2}',attempt)
    out=STAGE/('forest_tessellation_cpu_attempt'+attempt);assert not out.exists(),'Inspect the earlier attempt; use a new owned directory'
    out.mkdir(parents=True);work=out/'work';work.mkdir()
    names=['Source/Presentation/OriginalForestModel.h','Source/Presentation/OriginalTerrainTessellationModel.h',
        'Source/Presentation/OriginalCameraModel.h','Tests/original_forest_tessellation.cpp','Tests/original_forest_tessellation.py']
    before=[common.artifact(PROJECT/name) for name in names]
    write_new(out/'started.json',dict(inputs=before,runtime_or_game_execution_allowed=False))
    assert not any(os.environ.get(name) for name in ('CL','_CL_','LINK'))
    environment,compiler=environment_for(Path(r'C:/Program Files/Microsoft Visual Studio/2022/Community'),'x64',work)
    modes=[]
    for mode,flag in [('optimized','/O2'),('unoptimized','/Od')]:
        exe=work/('forest_tessellation_'+mode+'.exe');rsp=exe.with_suffix('.rsp');mapfile=exe.with_suffix('.map')
        flags=['/nologo','/std:c++14','/EHsc','/W4','/WX',flag,'/fp:strict','/MT',
            '/I"'+str(PROJECT/'Source/Presentation')+'"','"'+str(PROJECT/'Tests/original_forest_tessellation.cpp')+'"',
            '/Fo"'+str(exe.with_suffix('.obj'))+'"','/Fe"'+str(exe)+'"']
        links=['/INCREMENTAL:NO','/Brepro','/WX','/OPT:REF','/OPT:ICF','/MACHINE:X64','/MAP:'+str(mapfile)]
        with rsp.open('x',encoding='utf8') as stream:stream.write('\n'.join(flags)+'\n')
        compiled=run([compiler,'@'+str(rsp),'/link',*links],cwd=work,env=environment,timeout=60)
        text=(compiled.stdout+compiled.stderr).decode('mbcs',errors='replace');log=out/('compile_'+mode+'.txt')
        with log.open('x',encoding='utf8') as stream:stream.write(text)
        assert compiled.returncode==0 and not re.search(r'\bwarning\s+[A-Z]+\d+|경고\s+[A-Z]+\d+',text,re.I),'Component build failed: '+str(log)
        executable=common.artifact(exe)
        imported=run([Path(compiler).with_name('dumpbin.exe'),'/dependents',exe],cwd=work,env=environment,timeout=20);assert imported.returncode==0
        libraries=sorted(set(re.findall(r'^\s+([A-Za-z0-9_.-]+\.dll)\s*$',imported.stdout.decode('mbcs',errors='replace'),re.M)))
        assert {name.lower() for name in libraries}=={'kernel32.dll'},libraries
        executed=run([exe],cwd=work,env=environment,timeout=30);stdout=executed.stdout.decode('ascii');stderr=executed.stderr.decode('ascii')
        raw=out/('output_'+mode+'.json');write_new(raw,dict(returncode=executed.returncode,stdout=stdout,stderr=stderr,executable=executable))
        match=re.fullmatch(r'PASS_FOREST_TESSELLATION checks=(\d+) surface_samples=(\d+) colour_samples=(\d+) max_surface_error=([0-9.eE+-]+) max_colour_error=([0-9.eE+-]+) original_basis_verified=0 runtime_executed=0\s*',stdout)
        assert executed.returncode==0 and not stderr and match,'Component checks failed: '+str(raw)
        modes.append(dict(mode=mode,compiler=common.artifact(compiler),flags=flags+['/link']+links,cpp_dialect='c++14',
            compiler_and_linker_warnings=0,executable=executable,imported_dlls=libraries,compile_log=common.artifact(log),output=common.artifact(raw),
            checks=int(match[1]),surface_samples=int(match[2]),colour_samples=int(match[3]),maximum_surface_error=float(match[4]),maximum_colour_error=float(match[5])))
    after=[common.artifact(PROJECT/name) for name in names];assert before==after
    assert modes[0]['checks']==modes[1]['checks'] and modes[0]['surface_samples']==modes[1]['surface_samples'] and modes[0]['colour_samples']==modes[1]['colour_samples']
    receipt=dict(status='PASS_FOREST_BICUBIC_AND_EXPLICIT_CAMERA_CPU_REFERENCE_GUARDS',inputs_before=before,inputs_after=after,modes=modes,
        forest_original_assets=common.artifact(STAGE/'forest_assets_contract.json'),camera_original_contract=common.artifact(STAGE/'camera_retail_contract.json'),
        verified=['Explicit test-only Bezier basis against independent double Bernstein sums; plane, shared edges and 64 generated height grids',
            'All 16 unknown-footprint positions skip NaN controls; known byte, basis, UV, height and factor 1..64 bounds',
            '90/90/1 batches preserve 181 known transforms and ignore poisoned unknown instances; explicit scale/transform overflow guards',
            'Alpha 0.1 neighbours and exact boundary; 16384 independent chroma-overlay matrix combinations; colour domain rejection',
            'Explicit RH perspective analytic near/far and frustum edges; float-degree to double-radian to float narrowing',
            'LookAt orthonormal axes, right handedness, eye origin and target negative-Z; invalid and degenerate camera inputs'],
        bicubic_original_uploaded_basis_verified=False,original_forest_gr2_decoded=False,original_random_forest_placement_verified=False,
        actual_world_camera_pose_fov_or_world_units_calibrated=False,runtime_d3dx_float_parity_verified=False,
        renderer_submission_connected=False,native_host_sdk_clr_hwnd_gpu_audio_or_game_executed=False)
    write_new(out/'result.json',receipt)
    files=[]
    for path in sorted(work.iterdir()):
        assert path.is_file() and path.suffix in ('.cmd','.rsp','.obj','.exe','.map')
        row=common.artifact(path);assert row['links']==1 and not row['file_attributes']&0x401;row['allocated_bytes']=storage.allocated(path);files.append(row)
    write_new(out/'cleanup_plan.json',dict(directory=str(work),files=files,protected_sources=after))
    for row in files:
        actual=common.artifact(row['path']);assert all(actual[k]==row[k] for k in ('bytes','sha256','file_identity','mtime_ns','file_attributes','links'))
        path=Path(row['path']);assert path.resolve().is_relative_to(out.resolve());path.unlink()
    assert not list(work.iterdir());work.rmdir()
    cleanup=dict(status='PASS_EXACT_OWNED_FOREST_TESSELLATION_CAMERA_COMPONENT_INTERMEDIATES_REMOVED',files=files,deleted_files=len(files),released_logical_bytes=sum(x['bytes'] for x in files),released_unique_allocated_bytes=sum(x['allocated_bytes'] for x in files),source_or_runtime_deleted=False)
    write_new(out/'cleanup_result.json',cleanup)
    print(json.dumps(dict(status=receipt['status'],modes=[{k:r[k] for k in ('mode','checks','surface_samples','colour_samples','maximum_surface_error','maximum_colour_error')} for r in modes],cleanup_files=len(files),released_allocated_bytes=cleanup['released_unique_allocated_bytes'])))

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--attempt',required=True);args=parser.parse_args()
    try:main(args.attempt)
    except Exception as error:
        out=STAGE/('forest_tessellation_cpu_attempt'+args.attempt);failure=out/'failure.json'
        if out.is_dir() and not failure.exists():write_new(failure,dict(status='FAILED_CONTROLLED_CPU_COMPONENT_ATTEMPT',error=repr(error),runtime_executed=False))
        raise
