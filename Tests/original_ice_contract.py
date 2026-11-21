"""File-only original ice assets, CPU contract, and FXC VS validation.

No game/Host/SDK/Granny/CLR/window/GPU/audio execution or asset package writes.
Original FPK members are read in RAM and sent directly to a KERNEL32-only test.
"""
from pathlib import Path
import argparse,hashlib,importlib.util,json,os,re,struct,subprocess,sys,xml.etree.ElementTree as ET
sys.dont_write_bytecode=True
PROJECT=Path(__file__).absolute().parents[1]
EVIDENCE=PROJECT/'evidence/world_terrain_original/phase12/scene'
BUILD=PROJECT/'Build/OriginalIcePhase12'
sys.path.insert(0,str(PROJECT/'tools'))
from native_build import environment_for,run
from collect_baseline import digest,pe_header
from civ5_ui_assets import Fpk
from civ5_original_water_assets import validate_lean
spec=importlib.util.spec_from_file_location('scene_ice_pe',EVIDENCE/'scene_ice_pe.py')
probe=importlib.util.module_from_spec(spec);spec.loader.exec_module(probe)
FXC=Path(r'C:/Program Files (x86)/Windows Kits/10/bin/10.0.26100.0/x64/fxc.exe')
FXC_SHA='ced7c1f95e4dffb614971826625e70da6d24aff1b4f2a3ae5952939c9547d7e6'

def write_new(name,data):
    assert name.startswith('scene_') and Path(name).name==name
    path=EVIDENCE/name
    if path.exists():
        assert name=='scene_ice_result.json' and not path.lstat().st_file_attributes&0x400
        previous=json.loads(path.read_text('utf8'));assert previous['status']=='PASS_FILE_ONLY_ICE_COMPONENTS_GEOMETRY_PROVIDER_UNAVAILABLE'
        data['previous_receipt_sha256']=digest(path)
    with path.open('w'if path.exists()else'x',encoding='utf8')as stream:json.dump(data,stream,indent=2);stream.write('\n')
    return probe.reader.ref(path)

def sources():
    before=json.loads((EVIDENCE/'scene_ice_initial_contract.json').read_text('utf8'))
    pe=probe.reader.Pe();game=pe.path.parent;packs={};assets={};metadata=[];frame=bytearray(b'ZSICE12\0'+struct.pack('<I',6))
    for origin in before['assets']:
        path=Path(origin['pack_path'])
        if path not in packs:packs[path]=Fpk(path)
        data,record=packs[path].read(origin['entry']);assert record=={k:v for k,v in origin.items()if k not in ('header_hex','text')}
        assets[origin['entry']]=data
    for name in ('ice_bump.lean','ice_bump_sides.lean','ice_d.dds','ice_d_sides.dds','ice_environment_diffuse.dds','icedisplacement.dds'):
        data=assets[name];frame.extend(struct.pack('<I',len(data)));frame.extend(data)
        if name.endswith('.lean'):
            shape=validate_lean(data);assert shape['bytes_per_channel']==1 and shape['mips']==10
            samples=[]
            for mip in range(shape['mips']):
                a,b=(p['levels'][mip] for p in shape['planes']);w,h=a['width'],a['height']
                for x,y in ((0,0),(w//2,h//2),(w-1,h-1)):
                    rgba=data[a['offset']+y*a['row_pitch']+x*4:a['offset']+y*a['row_pitch']+x*4+4]
                    cross=data[b['offset']+y*b['row_pitch']+x];samples.append(dict(mip=mip,x=x,y=y,channels=list(rgba)+[cross]))
            frame.extend(struct.pack('<I',len(samples)))
            for row in samples:frame.extend(struct.pack('<III',row['mip'],row['x'],row['y'])+bytes(row['channels']))
            metadata.append(dict(name=name,sha256=digest_bytes(data),shape=shape,independent_samples=samples))
        else:
            words=struct.unpack_from('<32I',data);metadata.append(dict(name=name,sha256=digest_bytes(data),bytes=len(data),
                width=words[4],height=words[3],mips=words[7],pixel_format=list(words[20:27]),caps2=words[28]))
    def xml(data):
        assert len(data)<4096 and b'<!'not in data;root=ET.fromstring(data);assert root.tag=='IceSettings' and not list(root)
        return {k:float(v.strip())for k,v in root.attrib.items()}
    settings=xml(assets['icesettings.xml']);assert settings['TextureRepeat']==.005 and settings['BumpRepeat']==.009 and settings['SpecularPower']==150
    low_path=game/'Assets/Terrain/Ice/IceSettings_Low.xml';high_path=game/'Assets/Terrain/Ice/IceSettings.xml'
    low_origin=probe.reader.ref(low_path);assert low_origin['bytes']<4096;low=low_path.read_bytes();low_settings=xml(low)
    high_origin=probe.reader.ref(high_path);assert high_origin['bytes']<4096;loose_high=high_path.read_bytes();loose_settings=xml(loose_high)
    assert probe.reader.ref(low_path)==low_origin and probe.reader.ref(high_path)==high_origin
    changed={k:[low_settings.get(k),v]for k,v in settings.items()if low_settings.get(k)!=v}
    return pe,bytes(frame),dict(assets=metadata,high_settings=settings,low_settings=low_settings,low_origin=low_origin,loose_high_origin=high_origin,
        loose_high_byte_identical=loose_high==assets['icesettings.xml'],loose_high_semantic_identical=loose_settings==settings,
        loose_high_settings=loose_settings,loose_high_differences={k:[settings.get(k),v]for k,v in loose_settings.items()if settings.get(k)!=v},
        high_vs_low_changes=changed,seven_normal_quality_source_bytes=sum(len(x)for x in assets.values()),
        normal_quality_source_assets=7,source_asset_files_written=0,new_asset_packages=0,
        existing_water_python_lean_shape_validator_reused=True,existing_water_cpp16_decoder_unchanged=True)

def digest_bytes(data):return hashlib.sha256(data).hexdigest()

def trace(pe):
    blocks={}
    for name,start,stop in (
        ('geometry_pipeline_and_upload',0x4956f0,0x495e84),('settings_quality_choice',0x5a0bc0,0x5a0c14),
        ('material_source_loader',0x77a9c0,0x77abec),('lean_header_loader',0x8f3820,0x8f387c),
        ('vertex_format22_init',0x665a10,0x665ad0),('vertex_declaration_decoder',0x8bb810,0x8bbad8),
        ('index_buffer_width',0x8c62f0,0x8c6354),('complete_submit_record',0x8ccd80,0x8ccdfe)):
        raw=pe.data(start,stop-start);blocks[name]=dict(start=hex(start),stop=hex(stop),bytes=len(raw),sha256=digest_bytes(raw),listing=pe.listing(start,stop))
    layout=[struct.unpack('<III',pe.data(0xa222ec+i*12,12))for i in range(2)]
    assert layout==[(2,10,0),(3,8,4)]
    assert 'mov dword ptr [0xca01b8], 0xa222ec' in blocks['vertex_format22_init']['listing']
    return dict(exe=pe.before,blocks=blocks,vertex_layout=dict(format_id=22,stride=8,table='0xa222ec',raw_elements=layout,
        elements=[dict(semantic='TEXCOORD',index=0,dxgi_format=37,format='R16G16_SNORM',offset=0,bytes=4),
            dict(semantic='TEXCOORD',index=1,dxgi_format=28,format='R8G8B8A8_UNORM',offset=4,bytes=4)]),
        index_bits=16,bounds_record_bytes=20,feature_cell_bit=7,effect_id=59,
        settings_choice='IceSettings.xml iff available-memory difference>=64MiB and [0xd90f74]>1; otherwise IceSettings_Low.xml',
        lean_shader_scale_binding='LEAN file+4 -> 0x8f3820 output+8 -> this+0xff0c at0x77aad0 -> CB1[16].x at0x5fb274',
        resource_slots={0:'ice_environment_diffuse.dds cube',1:'ice_d.dds',2:'ice_bump.lean RGBA8 plane',
            3:'ice_bump.lean 8-bit scalar plane; loader format0x41; bound but unused by original PS',4:'ice_d_sides.dds',5:'ice_bump_sides.lean RGBA8 plane',
            6:'ice_bump_sides.lean 8-bit scalar plane; loader format0x41; original PS sample alpha',7:'existing fog ramp',8:'existing fog mask',9:'existing unexplored layer',10:'existing 3D color LUT'},
        original_pixel_shader_recovered=True,full_pixel_shader_port_implemented=False,
        original_geometry_provider_available=False,unsupported_scenes=['fractured ice producer','wonder geometry provider','landmark geometry provider'],
        native_host_sdk_clr_granny_hwnd_gpu_audio_or_game_executed=False)

def build():
    environment,compiler=environment_for(Path(r'C:/Program Files/Microsoft Visual Studio/2022/Community'),'x64',BUILD)
    name='original_ice_contract';exe=BUILD/(name+'.exe');obj=BUILD/(name+'.obj');map_file=BUILD/(name+'.map')
    flags=['/nologo','/std:c++14','/EHsc','/W4','/WX','/O2','/fp:strict','/MT',f'/I"{PROJECT/"Source/Presentation"}"',
        f'"{PROJECT/"Tests/original_ice_contract.cpp"}"',f'/Fo"{obj}"',f'/Fe"{exe}"']
    link=['/INCREMENTAL:NO','/Brepro','/WX','/OPT:REF','/OPT:ICF','/MACHINE:X64',f'/MAP:{map_file}']
    response=BUILD/'scene_compile.rsp';response.write_text('\n'.join(flags)+'\n',encoding='utf8')
    result=run([compiler,'@'+str(response),'/link',*link],cwd=BUILD,env=environment,timeout=120)
    output=(result.stdout+result.stderr).decode('mbcs',errors='replace');log=EVIDENCE/'scene_ice_compile.txt';log.write_text(output,encoding='utf8')
    assert result.returncode==0 and not re.search(r'\bwarning\s+[A-Z]+\d+|경고\s+[A-Z]+\d+',output,re.I),output[:3500]
    imported=run([Path(compiler).with_name('dumpbin.exe'),'/dependents',exe],cwd=BUILD,env=environment,timeout=30)
    deps=re.findall(r'^\s+([A-Za-z0-9_.-]+\.dll)\s*$',imported.stdout.decode('mbcs',errors='replace'),re.M)
    assert imported.returncode==0 and [x.lower()for x in deps]==['kernel32.dll'],deps
    return exe,dict(compiler=compiler,compiler_sha256=digest(Path(compiler)),flags=flags+['/link']+link,
        exe=probe.reader.ref(exe),pe=pe_header(exe),imports=deps,compiler_and_linker_warnings=0,log=probe.reader.ref(log))

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--prepare-only',action='store_true');args=parser.parse_args()
    pe,frame,assets=sources();trace_report=trace(pe);pe.verify()
    if args.prepare_only:
        report=write_new('scene_ice_asset_trace.json',dict(status='PASS_ORIGINAL_ASSET_AND_VERTEX_TRACE',**trace_report,asset_validation=assets))
        print(json.dumps(dict(status='PASS_ORIGINAL_ASSET_AND_VERTEX_TRACE',report=report)));return
    assert digest(FXC)==FXC_SHA;exe,compiled=build()
    result=subprocess.run([str(exe)],cwd=BUILD,input=frame,capture_output=True,timeout=30,creationflags=subprocess.CREATE_NO_WINDOW)
    assert result.returncode==0,result.stderr.decode('utf8',errors='replace');cpu=json.loads(result.stdout);assert cpu['status']=='PASS'and cpu['actual_assets']==6 and cpu['actual_lean_texels']==60
    emitted=run([exe,'--emit-vs'],cwd=BUILD,timeout=10);assert emitted.returncode==0
    hlsl=BUILD/'scene_ice_vs.hlsl';hlsl.write_bytes(emitted.stdout);cso=BUILD/'scene_ice_vs.cso';assembly=EVIDENCE/'scene_ice_vs_reconstructed.asm.txt'
    flags=['/nologo','/Ges','/WX','/O3','/T','vs_5_0','/E','OriginalIceVS','/Fo',str(cso),'/Fc',str(assembly),str(hlsl)]
    shader=run([FXC,*flags],cwd=BUILD,timeout=30);log=(shader.stdout+shader.stderr).decode('mbcs',errors='replace')
    assert shader.returncode==0 and 'warning'not in log.lower(),log
    assembled=assembly.read_text('utf8');assert 'vs_5_0'in assembled and 'CB1[14]'in assembled and 'SV_Position'in assembled and 'SV_Target'not in assembled
    pe.verify();report=write_new('scene_ice_result.json',dict(status='PASS_FILE_ONLY_ICE_COMPONENTS_GEOMETRY_PROVIDER_UNAVAILABLE',
        source_trace=trace_report,asset_validation=assets,compiled=compiled,cpu=cpu,
        fxc=dict(path=str(FXC),sha256=FXC_SHA,flags=flags,returncode=shader.returncode,compiler_warnings=0,
            hlsl=probe.reader.ref(hlsl),dxbc=probe.reader.ref(cso),assembly=probe.reader.ref(assembly)),
        source_files=[probe.reader.ref(PROJECT/name)for name in('Source/Presentation/OriginalIceContract.h','Source/Presentation/OriginalIceAssets.h',
            'Source/Presentation/OriginalIceShader.h','Tests/original_ice_contract.cpp','Tests/original_ice_contract.py')],
        limitations=['No original fracture/crack geometry producer: reflection Ice availability bit stays clear',
            'Original PS recovered; full material port remains unavailable','Wonders/landmarks are separate unsupported providers',
            'No original game or visual acceptance was attempted'],
        native_host_sdk_clr_granny_hwnd_gpu_audio_or_game_executed=False))
    print(json.dumps(dict(status='PASS_FILE_ONLY_ICE_COMPONENTS_GEOMETRY_PROVIDER_UNAVAILABLE',cpu=cpu,report=report)))

if __name__=='__main__':main()
