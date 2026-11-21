"""Compile the current water projector consumer without loading graphics APIs."""
from pathlib import Path
import hashlib,json,math,os,re,struct,subprocess,sys
sys.dont_write_bytecode=True
ROOT=Path(__file__).absolute().parent
PROJECT=ROOT.parents[2]
STAGE=ROOT/'water_shader02'
FXC=Path(r'C:\Program Files (x86)\Windows Kits\10\bin\10.0.26100.0\x64\fxc.exe')
FXC_SHA='ced7c1f95e4dffb614971826625e70da6d24aff1b4f2a3ae5952939c9547d7e6'


def ref(path):
    path=Path(path).absolute();s=os.stat(path,follow_symlinks=False)
    assert not s.st_file_attributes&0x400
    return dict(path=str(path),bytes=s.st_size,sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        file_identity=[s.st_dev,s.st_ino],mtime_ns=s.st_mtime_ns,file_attributes=s.st_file_attributes)


def write_new(path,value):
    with path.open('x',encoding='utf8') as stream:json.dump(value,stream,indent=2);stream.write('\n')


def extract(name,variable):
    path=PROJECT/'Source/Presentation'/name;text=path.read_text(encoding='utf-8-sig')
    match=re.search(r'\b'+re.escape(variable)+r'\[\]\s*=\s*R"HLSL\((.*?)\)HLSL"',text,re.S)
    assert match,path
    return match.group(1),ref(path)


def constant_buffer_size(raw,name):
    # RDEF cbuffer descriptors retain the complete declared layout even when
    # the executable stage only addresses a smaller active prefix.
    chunks=struct.unpack_from('<I',raw,28)[0]
    for index in range(chunks):
        at=struct.unpack_from('<I',raw,32+index*4)[0]
        if raw[at:at+4]!=b'RDEF':continue
        payload=raw[at+8:at+8+struct.unpack_from('<I',raw,at+4)[0]]
        count,offset=struct.unpack_from('<II',payload,0)
        for row in range(count):
            label,_,_,size,_,_=struct.unpack_from('<6I',payload,offset+24*row)
            end=payload.index(0,label)
            if payload[label:end].decode('ascii')==name:return size
    raise AssertionError('Missing reflected constant buffer: '+name)


def main():
    assert hashlib.sha256(FXC.read_bytes()).hexdigest()==FXC_SHA
    assert not STAGE.exists(),'A completed or failed attempt must not be replayed'
    STAGE.mkdir()
    shadow,shadow_ref=extract('OriginalDynamicShadowShader.h','SamplingSource')
    water,water_ref=extract('OriginalWaterSurfaceShader.h','ShaderSource')
    shader=STAGE/'water.hlsl';shader.write_text('#define DYNAMIC_SHADOW_SLOT t11\n'+shadow+water,encoding='utf8')
    inputs=[shadow_ref,water_ref]+[ref(PROJECT/'Source/Presentation'/name) for name in (
        'OriginalWaterReflection.inc','OriginalWaterSurfaceGpu.inc','OriginalWaterSurfaceGpuTypes.inc','WorldTerrainRenderer.cpp')]
    checks=[]
    def check(name,condition):
        checks.append(dict(name=name,passed=bool(condition)))
        assert condition,name
    check('row_major_shared_projector','row_major float4x4 reflectionViewProjection' in water)
    check('project_world_position_in_vs','p.reflection=mul(float4(p.local,1),reflectionViewProjection)' in water)
    check('dedicated_projected_uv','projected.xy/projected.w*float2(0.5,-0.5)-0.5' in water)
    check('main_screen_coordinates_removed','Reflection(p.p.xy/viewport.xy' not in water)
    check('invalid_projector_denied_before_sample','motion.w>0.5&&all(isfinite(p.reflection))&&abs(p.reflection.w)>0.00000001' in water)
    # Independent raster identity: NDC -> ordinary render-target UV differs
    # from the original expression by exactly one period in each coordinate.
    # This comparison covers non-unit homogeneous W and subpixel positions.
    count=0
    for w in (0.125,0.75,1,2,32):
        for x in (-0.99,-0.625,-0.125,0,0.375,0.99):
            for y in (-0.99,-0.5,0,0.125,0.875,0.99):
                projected=(x*w,y*w,w)
                recovered=(projected[0]/w*.5-.5,-projected[1]/w*.5-.5)
                raster=((x+1)*.5,(1-y)*.5)
                assert all(math.isclose(a-b,-1,abs_tol=1e-14) for a,b in zip(recovered,raster))
                count+=1
    results=[]
    for profile,entry in (('vs_5_0','vertexMain'),('ps_5_0','pixelMain')):
        output=STAGE/(profile+'.cso');assembly=STAGE/(profile+'.asm.txt')
        command=[str(FXC),'/nologo','/Ges','/WX','/T',profile,'/E',entry,'/Fo',str(output),'/Fc',str(assembly),str(shader)]
        run=subprocess.run(command,cwd=PROJECT,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
            creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0),check=False)
        (STAGE/(profile+'.stdout.txt')).write_bytes(run.stdout)
        (STAGE/(profile+'.stderr.txt')).write_bytes(run.stderr)
        assert run.returncode==0,(profile,run.returncode,run.stderr.decode(errors='replace'))
        assert not re.search(rb'\bwarning\b',run.stdout+run.stderr,re.I)
        raw=output.read_bytes();assert raw[:4]==b'DXBC' and struct.unpack_from('<I',raw,24)[0]==len(raw)
        asm=assembly.read_text(encoding='utf-8-sig')
        check(profile+'_cb368',constant_buffer_size(raw,'Surface')==368)
        check(profile+'_projector_offset0',bool(re.search(r'reflectionViewProjection;\s*//\s*Offset:\s*0\s+Size:\s*64',asm)))
        if profile=='ps_5_0':
            check('integer_pick_output',bool(re.search(r'SV_Target\s+1\s+.*uint',asm)))
            check('raw_reflection_unorm_wrap_binding','ReflectionCache' in asm and 'WrapSampler' in asm)
        results.append(dict(profile=profile,returncode=run.returncode,warnings=0,command=command,
            bytecode=ref(output),assembly=ref(assembly)))
    result=dict(status='PASS_SHARED_RAW_PROJECTOR_WATER_SM5_COMPILE_ONLY',inputs=inputs,compiler=ref(FXC),
        independent_homogeneous_wrap_checks=count,checks=checks,compiled=results,
        constant_buffer_bytes=368,raw_draw_camera='CANDIDATE_MIRROR_MAIN_VP',
        original_bounds_axis_projector_production_enabled=False,
        native_host_sdk_clr_hwnd_gpu_audio_or_game_executed=False)
    write_new(STAGE/'result.json',result)
    # Delete only regenerated, private leaves after recording their exact
    # identities and digests. Compiler assembly and logs remain as evidence.
    cleanup=[]
    for path in (shader,STAGE/'vs_5_0.cso',STAGE/'ps_5_0.cso'):
        before=ref(path);assert os.stat(path,follow_symlinks=False).st_nlink==1
        path.unlink();assert not path.exists();cleanup.append(dict(before=before,deleted=True))
    write_new(STAGE/'cleanup.json',dict(status='PASS_EXACT_OWNED_SHADER_TEMP_CLEANUP',files=cleanup,
        released_logical_bytes=sum(row['before']['bytes'] for row in cleanup),native_execution=False))
    print(json.dumps(dict(status=result['status'],checks=len(checks),homogeneous_checks=count,shader_profiles=2,warnings=0)))


if __name__=='__main__':main()
