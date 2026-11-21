"""Pinned original IceShader, feature-mask and draw submission evidence only."""
from pathlib import Path
import collections,hashlib,importlib.util,json,re,struct,sys
sys.dont_write_bytecode=True
ROOT=Path(__file__).absolute().parent
PROJECT=ROOT.parents[3]
spec=importlib.util.spec_from_file_location('scene_original_pe',PROJECT/'evidence/world_terrain_original/phase10/reflection/water_pe_view.py')
reader=importlib.util.module_from_spec(spec);spec.loader.exec_module(reader)
sys.path.insert(0,str(PROJECT/'tools'))
from civ5_ui_assets import Fpk

def write_new(name,value):
    path=ROOT/name;assert name.startswith('scene_') and path.parent==ROOT
    with path.open('x',encoding='utf8') as stream:json.dump(value,stream,indent=2);stream.write('\n')

def blob(pe,address):
    offset=pe.offset(address,32);assert pe.raw[offset:offset+4]==b'DXBC'
    size,count=struct.unpack_from('<II',pe.raw,offset+24)
    data=pe.raw[offset:offset+size];assert len(data)==size
    for field in struct.unpack_from('<%dI'%count,data,32):
        if data[field:field+4] in (b'SHDR',b'SHEX'):
            token=struct.unpack_from('<I',data,field+8)[0]
            kind={0:'ps',1:'vs',2:'gs',3:'hs',4:'ds',5:'cs'}[token>>16]
            return dict(address=hex(address),file_offset=offset,bytes=size,sha256=hashlib.sha256(data).hexdigest(),
                stage=kind,model=f'{kind}_{(token>>4)&15}_{token&15}'),data
    raise AssertionError('Missing shader code chunk')

def shaders(pe):
    instructions=list(pe.rows(0x4e5c20,0x4f5ca0))
    creators={'0x8bbc40':'vs','0x8bbbf0':'ps','0x8bbcc0':'hs','0x8bbd10':'ds'}
    handles=collections.defaultdict(list);pushes=[];pending=None
    for address,size,mnemonic,operands in instructions:
        if mnemonic=='push':pushes.append(operands);continue
        if mnemonic=='call' and operands in creators:
            source=next(int(x,16) for x in reversed(pushes) if x.startswith('0x') and int(x,16)>0x1000000)
            pending=(address,creators[operands],source);pushes=[];continue
        match=re.fullmatch(r'word ptr \[(0x[0-9a-f]+)\], ax',operands)
        if mnemonic=='mov' and match and pending:
            information,data=blob(pe,pending[2]);assert information['stage']==pending[1]
            handles[int(match[1],16)].append(dict(site=hex(pending[0]),**information));pending=None
        if mnemonic=='call':pushes=[]
    record=0x5d1e5c0+0x3b*0x520;writes={};registers={}
    for address,size,mnemonic,operands in instructions:
        match=re.fullmatch(r'(\w+), word ptr \[(0x[0-9a-f]+)\]',operands)
        if mnemonic=='movzx' and match:registers[match[1]]=int(match[2],16);continue
        match=re.fullmatch(r'dword ptr \[(0x[0-9a-f]+)\], (\w+)',operands)
        if mnemonic=='mov' and match:
            target=int(match[1],16)
            if record<=target<record+0x520:
                value=match[2]
                if value in registers:writes[target-record]=('handle',registers[value],address)
                elif value.startswith('0x') or value.isdigit():writes[target-record]=('immediate',int(value,0),address)
                else:writes[target-record]=('unknown',value,address)
        elif operands.split(',')[0] in registers and mnemonic in ('mov','xor','pop','lea','movzx'):
            registers.pop(operands.split(',')[0],None)
    count=writes[0x500]
    result=[];seen={};slots=('vs','ps','gs','hs','ds')
    for index in range(8):
        entry={}
        for number,stage in enumerate(slots):
            value=writes.get(index*20+number*4)
            if not value or value[0]!='handle':continue
            variants=handles[value[1]];sm5=[row for row in variants if row['model']==stage+'_5_0'];assert len(sm5)==1
            row=sm5[0];entry[stage]=dict(handle=hex(value[1]),record_write=hex(value[2]),original=row)
            if row['sha256'] not in seen:
                metadata,data=blob(pe,int(row['address'],16));assert metadata['sha256']==row['sha256']
                path=ROOT/('scene_ice_'+str(index)+'_'+stage+'.dxbc');assert not path.exists();path.write_bytes(data)
                seen[row['sha256']]=reader.ref(path)
            entry[stage]['extracted']=seen[row['sha256']]
        if not entry:break
        result.append(entry)
    assert result
    if count[0]=='immediate':assert count[1]==len(result)
    return dict(effect_id='0x3b',name=pe.string(pe.u32(0xc9e890+0x3b*8)),record=hex(record),passes=result,
        pass_count_initialization=dict(kind=count[0],value=count[1],site=hex(count[2]))),list(seen.values())

def main():
    pe=reader.Pe();effect,extracted=shaders(pe);assert effect['name']=='IceShader'
    blocks={}
    for name,start,stop in (
        ('reflection_callback',0x751f30,0x751f41),('ice_draw',0x5facb0,0x5fb4d3),
        ('mark_feature_cell',0x639850,0x639860),('cell_lookup',0x42e940,0x42ead0),
        ('ice_buffer_registration',0x4e6081,0x4e6099),('submit_draw',0x8ccd80,0x8ccdf0)):
        data=pe.data(start,stop-start)
        blocks[name]=dict(start=hex(start),stop=hex(stop),bytes=len(data),sha256=hashlib.sha256(data).hexdigest(),
            listing=pe.listing(start,stop))
    assert all(value in blocks['reflection_callback']['listing'] for value in ('push 1','push 0','call 0x5facb0'))
    assert 'or byte ptr [eax], 0x80' in blocks['mark_feature_cell']['listing']
    assert pe.string(0xa29c18)=='Ice'
    game=pe.path.parent;assets=[];archives=[]
    selected={'Resource/Common/TerrainModels.fpk':['icesettings.xml','ice_bump.lean','ice_bump_sides.lean'],
        'Resource/DX9/TerrainTextures.fpk':['icedisplacement.dds','ice_d.dds','ice_d_sides.dds','ice_environment_diffuse.dds']}
    for relative,names in selected.items():
        path=game/relative;before=reader.ref(path);pack=Fpk(path)
        for name in names:
            data,origin=pack.read(name);row=dict(**origin)
            if name.endswith('.xml'):row['text']=data.decode('utf-8-sig')
            else:row['header_hex']=data[:128].hex()
            assets.append(row)
        assert reader.ref(path)==before;archives.append(before)
    pe.verify()
    write_new('scene_ice_initial_contract.json',dict(status='PASS_PINNED_ORIGINAL_ICE_ASSET_SHADER_AND_SUBMISSION_BYTES',
        exe=pe.before,effect=effect,extracted_shaders=extracted,blocks=blocks,assets=assets,archives=archives,
        confirmed=['Ice feature input marks bit7 without changing terrain piece mask',
            'Raw reflection callback passes args(context,0,1) to original Ice draw',
            'Original draw rejects disabled/empty geometry and culls 20-byte bounds records',
            'Original producer is fractured procedural geometry, not an invented six-triangle hex'],
        candidates_or_unknown=['full fracture/crack-propagation geometry algorithm','original world/height calibration',
            'actual pixel/input acceptance','wonders and landmarks geometry providers'],
        source_assets_extracted_to_files=0,new_asset_packages=0,existing_six_packages_modified=False,
        native_host_sdk_clr_granny_hwnd_gpu_audio_or_game_executed=False))
    print(json.dumps(dict(status='PASS_PINNED_ORIGINAL_ICE_ASSET_SHADER_AND_SUBMISSION_BYTES',
        shader_passes=len(effect['passes']),shader_blobs=len(extracted),selected_assets=len(assets))))

if __name__=='__main__':main()
