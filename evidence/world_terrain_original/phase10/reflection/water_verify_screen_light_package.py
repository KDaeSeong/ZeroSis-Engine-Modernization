"""Strict C++14 original static-t9 package parser/pixel conformance only."""
from pathlib import Path
import argparse
import json
import re
import sys
sys.dont_write_bytecode=True
PROJECT=Path(__file__).absolute().parents[4]
STAGE=Path(__file__).absolute().parent
sys.path[:0]=[str(PROJECT/'tools'),str(PROJECT/'Tests'),str(STAGE)]
from menu_replay_restoration import build_cxx14
from menu_suite_storage import storage
from native_build import run
from water_pe_view import ref
from water_verify_components import imports


def write_new(path,value):
    assert path.is_relative_to(STAGE) and not path.exists()
    with path.open('x',encoding='utf8') as f:json.dump(value,f,indent=2);f.write('\n')


def main():
    cli=argparse.ArgumentParser();cli.add_argument('--attempt',default='water_package_cpu01');args=cli.parse_args()
    assert re.fullmatch('water_package_cpu[0-9]{2}',args.attempt)
    stage=STAGE/args.attempt;work=stage/'work';assert not stage.exists();work.mkdir(parents=True)
    prep=json.loads((STAGE/'water_screen_light_preparation.json').read_text('utf8'));package=Path(prep['package']['path'])
    paths=[PROJECT/'Source/Presentation/OriginalScreenLightPackage.h',PROJECT/'Source/Presentation/OriginalTerrainSha256.h',
           PROJECT/'Tests/original_screen_light_package.cpp',package,Path(__file__)]
    inputs=[ref(p) for p in paths];assert inputs[3]==prep['package'];failure=None
    write_new(stage/'water_started.json',dict(scope='NoNative0',inputs=inputs))
    try:
        compiled=build_cxx14('original_screen_light_package',work,stage,paths[2],[PROJECT/'Source/Presentation'])
        executable=Path(compiled['path']);dlls=imports(executable);exeref=ref(executable)
        done=run([str(executable),str(package)],cwd=work,timeout=60)
        stdout,stderr=done.stdout.decode('ascii'),done.stderr.decode('ascii')
        match=re.fullmatch(r'PASS_ORIGINAL_SCREEN_LIGHT_PACKAGE checks=(\d+) rejected=(\d+) mip_levels=11 decoded_pixels=1048576 native_graphics_calls=0\s*',stdout)
        assert done.returncode==0 and not stderr and match,(done.returncode,stdout,stderr)
        assert [ref(p) for p in paths]==inputs
    except BaseException as e:
        failure=e;write_new(stage/'water_failure.json',dict(scope='NoNative0',error_type=type(e).__name__,message=str(e)[:4000]))
    finally:
        rows=[]
        for path in sorted(work.iterdir()):
            assert path.is_file() and path.resolve()==path and not path.lstat().st_file_attributes&0x401 and path.stat().st_nlink==1
            rows.append(dict(ref(path),allocated_bytes=storage.allocated(path)))
        write_new(stage/'water_cleanup_plan.json',dict(exact_owned_work=str(work),files=rows))
        for row in rows:
            path=Path(row['path']);assert path.parent==work and ref(path)=={k:v for k,v in row.items() if k!='allocated_bytes'};path.unlink()
        work.rmdir()
        write_new(stage/'water_cleanup_result.json',dict(status='PASS_EXACT_SCREEN_LIGHT_CPU_INTERMEDIATES_REMOVED',files=len(rows),logical_bytes_removed=sum(r['bytes'] for r in rows),allocated_bytes_removed=sum(r['allocated_bytes'] for r in rows)))
    if failure:raise failure
    result=dict(schema='zerosis.phase10.static_screen_light_package_cpu.v1',status='PASS_ORIGINAL_STATIC_T9_PACKAGE_CXX14_FULL_TOP_MIP_AND_REJECTIONS',scope='NoNative0',
        inputs=inputs,checks=int(match[1]),rejected=int(match[2]),mip_levels=11,decoded_pixels=1048576,
        compile=compiled,executed_console=exeref,imports=dlls,stdout=stdout.strip(),
        preparation=ref(STAGE/'water_screen_light_preparation.json'),owner_correction=ref(STAGE/'water_t9_owner_correction.json'),
        unchanged_original_five_packages=True,raw_dds_separate_copies=0,native_host_gamecore_clr_hwnd_gpu_audio_or_game_executed=False,
        limitations='Byte-preserving BC3 package and independent CPU decoder conformance only; original FTXT native loader and actual GPU sampling/pixels remain unexecuted.',
        cleanup=ref(stage/'water_cleanup_result.json'))
    write_new(stage/'water_result.json',result);print(dict(status=result['status'],checks=result['checks'],rejected=result['rejected'],output=ref(stage/'water_result.json')))


if __name__=='__main__':main()
