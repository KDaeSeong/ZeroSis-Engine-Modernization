"""Independent strict CPU verification of the production height adapter."""
from fractions import Fraction
from pathlib import Path
import argparse,gzip,json,os,re,struct,sys
sys.dont_write_bytecode=True
ROOT=Path(__file__).absolute().parent
PROJECT=ROOT.parents[3]
sys.path[:0]=[str(PROJECT/'tools'),str(PROJECT/'Tests'),str(ROOT)]
import build_exit_confirm_host as common
from menu_replay_restoration import build_cxx14
from menu_suite_storage import storage
from native_build import run


def write_new(path,value):
    with Path(path).open('x',encoding='utf8',newline='\n') as stream:json.dump(value,stream,indent=2);stream.write('\n')


def f32(value):return struct.unpack('<f',struct.pack('<f',value))[0]


def golden(path):
    offsets=[0.0,0.25,f32(15300/65535),0.5,1.0];codes=[]
    for offset in offsets:
        total=f32(0);weight=f32(1e-6)
        for raw,blend in [(32768,255),(65535,128)]:
            w=f32(blend*f32(1/255));value=f32(f32(f32(raw*f32(1/65535))-offset)*w)
            total=f32(total+value);weight=f32(weight+w)
        exact=(Fraction.from_float(total)/Fraction.from_float(weight)+Fraction.from_float(offset))*65535
        assert exact>=0 and exact<=65535
        codes.append(exact.numerator//exact.denominator)
    with path.open('x',encoding='ascii',newline='\n') as stream:
        stream.write('#pragma once\nnamespace HeightBindingGolden {\nconstexpr unsigned Count=%du;\n'%len(offsets))
        stream.write('constexpr float Offsets[]={'+','.join(repr(value)+'f' for value in offsets)+'};\n')
        stream.write('constexpr unsigned Raw[]={'+','.join(map(str,codes))+'};\n}\n')
    return dict(offsets=offsets,raw=codes,method='Original opcode float32 accumulation then independent exact Fraction divide/add/truncate; no production helper imported')


def main():
    cli=argparse.ArgumentParser();cli.add_argument('--attempt',type=int,default=1);args=cli.parse_args()
    assert 1<=args.attempt<=9 and not any(os.environ.get(name) for name in ('CL','_CL_','LINK'))
    stage=ROOT/('cache_height_binding_cpu/attempt%02d'%args.attempt)
    assert not stage.exists();stage.mkdir(parents=True);build=stage/'build';build.mkdir()
    names=['OriginalTerrainModel.h','OriginalTerrainGeometry.h','OriginalTerrainBinding.h',
        'OriginalTerrainNormalModel.h','OriginalTerrainCacheSamplingModel.h']
    inputs=[PROJECT/'Source/Presentation'/name for name in names]+[PROJECT/'Tests/original_terrain_height_binding.cpp',Path(__file__).absolute()]
    before=[common.artifact(path) for path in inputs];reference=golden(build/'height_binding_golden.h')
    write_new(stage/'cache_started.json',dict(inputs=before,reference=reference,root_baseline_complete=True))
    error=None;compiled=None;executable=None;checks=0;imports=[]
    try:
        compiled=build_cxx14('original_terrain_height_binding',build,stage,PROJECT/'Tests/original_terrain_height_binding.cpp',
                            [PROJECT/'Source/Presentation',build])
        result=run([Path(compiled['compiler']).with_name('dumpbin.exe'),'/dependents',compiled['path']],cwd=build,timeout=30)
        text=result.stdout.decode('mbcs',errors='replace');imports=sorted(set(re.findall(r'^\s+([A-Za-z0-9_.-]+\.dll)\s*$',text,re.M)))
        assert result.returncode==0 and {name.lower() for name in imports}=={'kernel32.dll'},imports
        with (stage/'cache_imports.txt').open('x',encoding='utf8') as stream:stream.write(text)
        executable=common.artifact(compiled['path']);done=run([compiled['path']],cwd=build,timeout=60)
        stdout,stderr=done.stdout.decode('ascii'),done.stderr.decode('ascii')
        with (stage/'cache_console.txt').open('x',encoding='ascii') as stream:stream.write(stdout+stderr)
        match=re.fullmatch(r'PASS_ORIGINAL_TERRAIN_HEIGHT_BINDING checks=(\d+)\s*',stdout)
        assert done.returncode==0 and not stderr and match,(done.returncode,stdout,stderr)
        checks=int(match[1])
    except BaseException as failure:
        error=failure
        with (stage/'cache_failed_test.cpp.gz').open('xb') as stream:stream.write(gzip.compress(inputs[-2].read_bytes(),mtime=0))
        write_new(stage/'cache_failure.json',dict(type=type(failure).__name__,message=str(failure)[:3000],compiled=compiled))
    finally:
        after=[common.artifact(path) for path in inputs];assert before==after,'Production inputs changed during controlled probe'
        rows=[]
        for path in sorted(build.iterdir()):
            assert path.is_file() and path.suffix in ('.h','.exe','.obj','.map','.rsp','.cmd')
            row=dict(common.artifact(path),allocated_bytes=storage.allocated(path));assert row['links']==1 and not row['file_attributes']&0x401;rows.append(row)
        write_new(stage/'cache_cleanup_plan.json',dict(directory=str(build),files=rows,protected_inputs=after))
        for row in rows:
            assert common.artifact(row['path'])=={k:v for k,v in row.items() if k!='allocated_bytes'}
            path=Path(row['path']);assert path.parent==build;path.unlink()
        assert not list(build.iterdir());build.rmdir()
        write_new(stage/'cache_cleanup_receipt.json',dict(status='PASS_EXACT_OWNED_CPU_TEMPORARIES_REMOVED',files=rows,
            deleted_files=len(rows),deleted_allocated_bytes=sum(row['allocated_bytes'] for row in rows),protected_inputs_unchanged=True))
    if error:raise error
    static={}
    text=(PROJECT/'Source/Presentation/OriginalTerrainShader.h').read_text(encoding='utf8')
    static['terrain_restores_original_height']='p.height*textureOrigin.z+fogInfo.z' in text
    static['terrain_uses_actual_y_metric']='(textureOrigin.y+p.uv.y)*fogInfo.w*textureOrigin.z' in text
    text=(PROJECT/'Source/Presentation/OriginalLightingFieldShader.h').read_text(encoding='utf8')
    static['field_restores_original_height']='p.height*origin.z+worldAdapter.x' in text
    static['field_uses_actual_y_metric']='tile.y*worldAdapter.y*origin.z' in text
    text=(PROJECT/'Source/Presentation/OriginalLightingFieldGpu.inc').read_text(encoding='utf8')
    static['field_reads_world_height']='OT::AtlasWorldHeight(surface.atlas,px,py)' in text
    static['field_origin_uploaded']='constants.worldAdapter[0]=OT::DisplayHeightOriginCandidate()' in text
    static['field_y_uploaded']='constants.worldAdapter[1]=OriginalTerrainCacheSampling::SourceMetricYDefault' in text
    assert all(static.values()),static
    report=dict(schema='zerosis.phase12.height_binding.cpu.v1',status='PASS_STRICT_CXX14_PRODUCTION_HEIGHT_BINDING',checks=checks,
        inputs_before=before,inputs_after=after,reference=reference,compiled=compiled,executable=executable,imports=imports,
        coverage=['All65536 finalized codes x8 centeredfloat offsets roundtrip losslessly','BuildAtlas original one-time truncate with independent opcode/Fraction expected code',
            'Positive-weight-before-numeric-read and unknown poison exclusion','Independent noninteger bilinear original-world heights',
            'Independent per-axis wrap/nonwrap boundaries and normal privacy fallback','Original .866 Ymetric flat-tilt normal golden','Origin restoration and actual normalized scale'],
        static_gpu_adapter=static,actual_controlled_cpu_component_executed=True,
        host_sdk_project_clr_granny_hwnd_gpu_audio_or_game_executed=False,
        cleanup=common.artifact(stage/'cache_cleanup_receipt.json'))
    write_new(stage/'cache_result.json',report)
    print(json.dumps(dict(status=report['status'],checks=checks,result=common.artifact(stage/'cache_result.json'))))


if __name__=='__main__':main()
