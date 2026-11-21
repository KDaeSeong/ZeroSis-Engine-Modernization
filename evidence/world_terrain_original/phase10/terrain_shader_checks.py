"""Strict compile of the actual concatenated terrain/screen-light shader."""
from pathlib import Path
import argparse
import json
import re
import subprocess
import sys
sys.dont_write_bytecode=True
ROOT=Path(__file__).absolute().parent
PROJECT=ROOT.parents[2]
sys.path.insert(0,str(PROJECT/'Tests'))
from original_water_shader import ref,write_new


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--attempt',required=True);args=parser.parse_args()
    assert re.fullmatch(r'terrain_shader\d{2}',args.attempt)
    stage=ROOT/args.attempt;assert not stage.exists();stage.mkdir()
    compiler=Path(r'C:\Program Files (x86)\Windows Kits\10\bin\10.0.26100.0\x64\fxc.exe')
    assert ref(compiler)['sha256']=='ced7c1f95e4dffb614971826625e70da6d24aff1b4f2a3ae5952939c9547d7e6'
    protected=[ref(compiler),ref(Path(__file__).absolute())]
    parts=[]
    for name in ('OriginalScreenLightingShader.h','OriginalTerrainShader.h'):
        path=PROJECT/'Source/Presentation'/name;protected.append(ref(path))
        literals=re.findall(r'R"HLSL\((.*?)\)HLSL"',path.read_text('utf8'),re.S)
        assert len(literals)==1;parts.append(literals[0])
    write_new(stage/'started.json',dict(inputs=protected,native_execution=False))
    owned=[];passes=[]
    try:
        source=stage/'terrain.hlsl';source.write_text(''.join(parts),encoding='ascii');owned.append(source)
        for entry,profile in (('vertexMain','vs_5_0'),('pixelMain','ps_5_0')):
            output=stage/(entry+'.cso');owned.append(output)
            assembly=stage/(entry+'.asm.txt')
            command=[str(compiler),'/nologo','/Ges','/WX','/T',profile,'/E',entry,'/Fo',str(output),'/Fc',str(assembly),str(source)]
            result=subprocess.run(command,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                timeout=30,check=False,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            log=(result.stdout+result.stderr).decode('mbcs');(stage/(entry+'.log')).write_text(log,encoding='utf8')
            assert result.returncode==0 and not re.search(r'\b(?:error|warning)\s+[A-Z]?\d+',log,re.I),log
            listing=assembly.read_text('ascii')
            assert profile in listing and 'dcl_uav' not in listing and 'oDepth' not in listing
            if profile=='ps_5_0':
                assert 't44' in listing and 'dcl_resource_texture2d (uint,uint,uint,uint) t24' in listing
                assert re.search(r'^// SV_Target\s+1\s+\S+\s+1\s+TARGET\s+uint',listing,re.M)
                assert 'dcl_output o1.x' in listing
                # Exact public state is tested before material/lighting reads in
                # the production source; selected tile IDs never use weights.
                pixel=parts[1][parts[1].index('O pixelMain('):]
                gate=pixel.index('if(state.y==0)')
                assert pixel.index('PlotState.Load(')<gate<pixel.index('.Sample(')
                assert 'o.pick=state.x;' in pixel and 'o.pick=' not in pixel[pixel.index('o.pick=state.x;')+len('o.pick=state.x;'):]
            passes.append(dict(entry=entry,profile=profile,command=command,return_code=0,warnings=0,
                bytecode_before_cleanup=ref(output),assembly=ref(assembly)))
        assert all(ref(row['path'])==row for row in protected)
        write_new(stage/'result.json',dict(status='PASS_CURRENT_CONCATENATED_TERRAIN_SHADER',passes=passes,
            inputs=protected,integer_id_target=True,unknown_guard_before_material_reads=True,
            native_host_sdk_clr_hwnd_gpu_audio_or_game_executed=False))
    finally:
        rows=[ref(p) for p in owned if p.exists()]
        write_new(stage/'cleanup_plan.json',dict(files=rows,exact_owned_leaves_only=True))
        for row in rows:
            path=Path(row['path']);assert path.parent==stage and row['links']==1 and not row['file_attributes']&0x401
            assert ref(path)==row;path.unlink()
        write_new(stage/'cleanup_result.json',dict(status='PASS_EXACT_OWNED_SHADER_INTERMEDIATES_REMOVED',
            files=rows,deleted_files=len(rows),released_unique_allocated_bytes=sum(row['allocated_bytes']for row in rows)))
    print(json.dumps(dict(status='PASS_CURRENT_CONCATENATED_TERRAIN_SHADER',passes=len(passes),warnings=0)))


if __name__=='__main__':main()
