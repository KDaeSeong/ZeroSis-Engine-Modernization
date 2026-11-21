"""Strict CPU-only reflection projection checks with exact temporary cleanup."""
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
sys.path[:0]=[str(PROJECT/'tools'),str(PROJECT/'Tests')]
from menu_replay_restoration import build_cxx14
from menu_suite_storage import storage
from native_build import run
VIEW=PROJECT/'evidence/world_terrain_original/phase10/reflection/water_pe_view.py'
spec=importlib.util.spec_from_file_location('reflection_component_pe_reader',VIEW)
view=importlib.util.module_from_spec(spec);spec.loader.exec_module(view)
IMPORT_HELPER=PROJECT/'evidence/world_terrain_original/phase10/reflection/water_verify_components.py'
spec=importlib.util.spec_from_file_location('reflection_component_import_check',IMPORT_HELPER)
helper=importlib.util.module_from_spec(spec);spec.loader.exec_module(helper)


def write(path,data):
    assert path.is_relative_to(ROOT) and not path.exists()
    with path.open('x',encoding='utf8') as stream:json.dump(data,stream,indent=2);stream.write('\n')


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--attempt',required=True);args=parser.parse_args()
    assert re.fullmatch('reflection_components[0-9]{2}',args.attempt)
    stage=ROOT/args.attempt;assert not stage.exists()
    startup=json.loads((ROOT.parent/'startup.json').read_text('utf8'))
    assert startup['status'].startswith('PASS'),startup['status']
    assert not any(os.environ.get(key) for key in ('CL','_CL_','LINK'))
    source=PROJECT/'Source/Presentation/OriginalReflectionProjectionModel.h'
    test=PROJECT/'Tests/original_reflection_projection.cpp'
    paths=[source,test,Path(__file__).absolute(),VIEW,IMPORT_HELPER,ROOT.parent/'startup.json']
    inputs=[view.ref(path) for path in paths]
    work=stage/'work';work.mkdir(parents=True)
    write(stage/'reflection_started.json',dict(scope='NoNative0',inputs=inputs,strict_cpu_console_only=True))
    error=None;result=None
    try:
        compiled=build_cxx14('original_reflection_projection',work,stage,test,[source.parent])
        executable=Path(compiled['path']);imports=helper.imports(executable)
        before=view.ref(executable)
        done=run([str(executable)],cwd=work,timeout=45)
        stdout,stderr=done.stdout.decode('ascii'),done.stderr.decode('ascii')
        assert done.returncode==0 and not stderr,(done.returncode,stdout,stderr)
        match=re.fullmatch(r'PASS_ORIGINAL_REFLECTION_PROJECTION checks=(\d+) native_graphics_calls=0\s*',stdout)
        assert match,stdout
        assert [view.ref(path) for path in paths]==inputs,'Inputs changed during controlled CPU test'
        result=dict(schema='zerosis.phase12.reflection_projection_components.v1',
            status='PASS_REFLECTION_PROJECTION_CXX14_CPU_ONLY',scope='NoNative0',inputs=inputs,
            build=compiled,executed_console=before,imports=imports,checks=int(match[1]),stdout=stdout.strip(),
            validated=['explicit-input gate','signed original orthographic depth planes','row-vector composition',
                       'axial analytic UV edges','translated-bounds invariance','producer-consumer world-adapter agreement',
                       'explicit half-space adapter','degenerate/nonfinite input rejection'],
            native_host_gamecore_clr_hwnd_gpu_audio_or_game_executed=False,
            original_world_inputs_supplied_to_production=False,original_plane_clipping_verified=False,
            limitations=['D3DX dispatched floating-point parity unverified','indexed-view adjustment unsupported',
                         'no calibrated original frame bounds/axis/current-world adapter provider',
                         'explicit plane helper is algebra only, not an original waterline assertion'])
    except BaseException as exc:
        error=exc
        write(stage/'reflection_failure.json',dict(status='FAIL_CONTROLLED_REFLECTION_COMPONENT_CHECK',
            error_type=type(exc).__name__,message=str(exc)[:5000],inputs_unchanged=[view.ref(path) for path in paths]==inputs))
    finally:
        rows=[]
        for path in sorted(work.rglob('*')):
            if not path.is_file():continue
            info=path.lstat()
            assert path.resolve()==path and not info.st_file_attributes&0x401 and info.st_nlink==1
            row=view.ref(path);row['allocated_bytes']=storage.allocated(path);rows.append(row)
        write(stage/'reflection_cleanup_plan.json',dict(exact_owned_work=str(work),files=rows,reason='Reproducible controlled CPU intermediates'))
        for row in rows:
            path=Path(row['path'])
            assert path.is_relative_to(work) and view.ref(path)=={key:value for key,value in row.items() if key!='allocated_bytes'}
            path.unlink()
        for directory in sorted((p for p in work.rglob('*') if p.is_dir()),key=lambda p:len(p.parts),reverse=True):directory.rmdir()
        work.rmdir()
        write(stage/'reflection_cleanup_result.json',dict(status='PASS_EXACT_OWNED_REFLECTION_INTERMEDIATES_REMOVED',
            removed_files=len(rows),logical_bytes_removed=sum(row['bytes'] for row in rows),
            allocated_bytes_removed=sum(row['allocated_bytes'] for row in rows),work_absent=not work.exists()))
    if error:raise error
    result['cleanup']=view.ref(stage/'reflection_cleanup_result.json')
    write(stage/'reflection_result.json',result)
    print(json.dumps(dict(status=result['status'],checks=result['checks'],output=view.ref(stage/'reflection_result.json'))))


if __name__=='__main__':main()
