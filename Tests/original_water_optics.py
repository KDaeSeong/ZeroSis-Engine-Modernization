"""Strict C++14 CPU-only optics conformance; no Host, SDK or graphics loading."""
from __future__ import annotations
import argparse
import json
import math
import os
from pathlib import Path
import re
import struct
import sys

sys.dont_write_bytecode=True
PROJECT=Path(__file__).absolute().parents[1]
ROOT=PROJECT/'evidence/world_terrain_original/phase4/optics'
sys.path.insert(0,str(PROJECT/'tools'))
sys.path.insert(0,str(PROJECT/'Tests'))
import build_exit_confirm_host as common
from menu_replay_restoration import build_cxx14
from menu_suite_storage import storage
from native_build import run


def write_new(path,value):
    with path.open('x',encoding='utf8') as stream:json.dump(value,stream,indent=2);stream.write('\n')


def golden(path):
    # Independent rotated eigenbasis evaluation, not the production cofactor
    # formula. The exponent coefficient is the pinned original float32 literal.
    log2e=struct.unpack('<f',bytes.fromhex('3baab83f'))[0]
    wide_multiplier=struct.unpack('<f',bytes.fromhex('0ad7a33b'))[0]
    rows=[]
    for first in (0,0.003,0.02):
        for second in (0,0.007,0.06):
            for angle in (0,0.2,0.7,1.3):
                c,s=math.cos(angle),math.sin(angle)
                xx=first*c*c+second*s*s;yy=first*s*s+second*c*c;xy=(first-second)*c*s
                for x,y in ((0,0),(0.03,-0.07),(0.5,0.25),(2,-1)):
                    for k in (1,16,128):
                        for wide in (False,True):
                            a=first+(16 if wide else 1)/k;b=second+(16 if wide else 1)/k
                            axis0=c*x+s*y;axis1=-s*x+c*y
                            q=0.5*(axis0*axis0/a+axis1*axis1/b)
                            determinant=a*b
                            rejected=q>=16
                            value=0 if rejected else math.exp(-q*math.log(2)*log2e)/math.sqrt(determinant)*(wide_multiplier if wide else 1)
                            rows.append((xx,yy,xy,x,y,k,wide,q,determinant,value,rejected))
    text='#pragma once\nstruct GoldenOpticsGaussian{double xx,yy,xy,x,y,k;bool wide;double q,determinant,value;bool rejected;};\n'
    text+='constexpr GoldenOpticsGaussian GoldenOpticsGaussians[]={\n'
    for row in rows:
        values=[str(value).lower() if isinstance(value,bool) else format(value,'.17g') for value in row]
        text+='{'+','.join(values)+'},\n'
    text+='};\n'
    path.write_text(text,encoding='ascii')
    return dict(cases=len(rows),generated=common.artifact(path),
        method='Rotated positive-semidefinite eigenvalues plus diagonal regularisation; independent exponential/log formulation using original float literals; no production header called.')


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--attempt',type=int,default=0);args=parser.parse_args()
    assert 0<=args.attempt<=9
    stage=ROOT/('cpu' if args.attempt==0 else f'cpu_retry{args.attempt:02d}')
    assert not stage.exists(),'Inspect the owned prior attempt before retrying'
    assert not any(os.environ.get(name) for name in ('CL','_CL_','LINK'))
    stage.mkdir(parents=True);build=stage/'build';build.mkdir()
    names=['Source/Presentation/OriginalWaterOpticsModel.h','Tests/original_water_optics.cpp','Tests/original_water_optics.py',
        'evidence/world_terrain_original/phase3/semantics/bytecode/WaterShader_2_ps.asm',
        'evidence/world_terrain_original/phase4/semantics/lean_encoding.json']
    before=[common.artifact(PROJECT/name) for name in names]
    source=(PROJECT/names[0]).read_text('ascii')
    assert not re.search(r'\b(?:rand|srand|CreateWindow|D3D11CreateDevice|LoadLibrary|GetProcAddress)\s*\(',source)
    assert not re.search(r'#include\s*[<"](?:[Ww]indows|d3d|.*Package|WorldView)',source)
    reference=golden(build/'original_water_optics_golden.h')
    write_new(stage/'started.json',dict(inputs=before,golden=reference,host_sdk_clr_hwnd_gpu_audio_or_game_executed=False))
    compiled=None;executable=None;dlls=[];match=None;rows=[]
    try:
        compiled=build_cxx14('original_water_optics',build,stage,PROJECT/names[1],[PROJECT/'Source/Presentation',build])
        responses=list(build.glob('*.rsp'));assert responses
        flags='\n'.join(path.read_text('utf-8-sig') for path in responses)
        assert all(flag in flags for flag in ('/std:c++14','/O2','/W4','/WX','/MT'))
        imports=run([Path(compiled['compiler']).with_name('dumpbin.exe'),'/dependents',compiled['path']],cwd=build,timeout=30)
        dlls=sorted(set(re.findall(r'^\s+([A-Za-z0-9_.-]+\.dll)\s*$',imports.stdout.decode('mbcs',errors='replace'),re.M)))
        assert imports.returncode==0 and {name.lower() for name in dlls}=={'kernel32.dll'},dlls
        (stage/'imports.txt').write_text(imports.stdout.decode('mbcs',errors='replace'),encoding='utf8')
        executable=common.artifact(compiled['path']);done=run([compiled['path']],cwd=build,timeout=60)
        stdout,stderr=done.stdout.decode('ascii'),done.stderr.decode('ascii')
        (stage/'console.txt').write_text(stdout+stderr,encoding='ascii')
        match=re.fullmatch(r'PASS_ORIGINAL_WATER_OPTICS checks=(\d+) gaussian_cases=(\d+)\s*',stdout)
        assert done.returncode==0 and not stderr and match,(done.returncode,stdout,stderr)
        assert int(match[2])==reference['cases']
    finally:
        after=[common.artifact(PROJECT/name) for name in names];assert before==after
        for path in sorted(build.iterdir()):
            assert path.is_file() and path.suffix in ('.exe','.obj','.map','.rsp','.cmd','.h')
            row=dict(common.artifact(path),allocated_bytes=storage.allocated(path))
            assert row['links']==1 and not row['file_attributes']&0x401;rows.append(row)
        write_new(stage/'cleanup_plan.json',dict(directory=str(build),files=rows,protected_inputs=after))
        for row in rows:
            path=Path(row['path']);assert path.is_relative_to(build)
            assert all(common.artifact(path)[key]==row[key] for key in ('bytes','sha256','file_identity','mtime_ns','file_attributes','links'))
            assert storage.allocated(path)==row['allocated_bytes'];path.unlink()
        assert not any(build.iterdir());build.rmdir()
        write_new(stage/'cleanup_result.json',dict(status='PASS_EXACT_OWNED_OPTICS_CPU_INTERMEDIATES_REMOVED',files=rows,
            deleted_files=len(rows),deleted_logical_bytes=sum(row['bytes'] for row in rows),
            released_unique_allocated_bytes=sum(row['allocated_bytes'] for row in rows),protected_inputs_unchanged=True))
    result=dict(schema='zerosis.original_water.phase4.optics_cpu.v1',status='PASS_PRODUCTION_OPTICS_CXX14_CPU_ONLY',
        checks=int(match[1]),gaussian_reference_cases=int(match[2]),inputs_before=before,inputs_after=after,
        build=compiled,executed_console=executable,imported_dlls=dlls,golden=reference,
        cases=['Independent centred covariance composition for256 mixed moment pairs',
               'Independent rotated-eigenbasis Gaussian reference for864 narrow/wide cases',
               'det<=0/q>=16 rejection, exact q16, near threshold and negative-q behaviour without an added PSD rule',
               'Non-normalised material normal, unclamped Fresnel, clamped diffuse, half-vector horizontal/zero policies',
               'Exact asymmetric reflection offsets, average-before-gamma, original gamma literal bit patterns and HDR/zero domains',
               'Finite/malformed scale, k, weights, UV, colour and view validation'],
        original_operations='Source operation semantics only; no claim of bit-identical GPU arithmetic or runtime constants.',
        safety_policies=['Early determinant rejection avoids original invalid sqrt/divide intermediates.',
                         'Zero/horizontal half vectors return invalid; optional epsilon is an explicit candidate.',
                         'Negative RGB is rejected instead of propagating original logarithm NaN.'],
        cleanup=common.artifact(stage/'cleanup_result.json'),host_sdk_clr_hwnd_gpu_audio_or_game_executed=False,
        original_gpu_or_image_parity_verified=False)
    write_new(stage/'result.json',result)
    print(json.dumps(dict(status=result['status'],checks=result['checks'],gaussian_cases=result['gaussian_reference_cases'],
        deleted_files=len(rows),released_unique_allocated_bytes=sum(row['allocated_bytes'] for row in rows))))


if __name__=='__main__':main()
