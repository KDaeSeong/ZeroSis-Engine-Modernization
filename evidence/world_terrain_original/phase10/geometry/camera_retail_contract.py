"""Record original matrix imports and camera callsites without DLL loading."""
from pathlib import Path
import hashlib
import importlib.util
import json
import struct
import sys
sys.dont_write_bytecode=True
ROOT=Path(__file__).absolute().parent
spec=importlib.util.spec_from_file_location('camera_pe',ROOT.parent/'reflection/water_pe_view.py')
m=importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def main():
    pe=m.Pe()
    address=struct.unpack_from('<I',pe.raw,60)[0]
    rva,size=struct.unpack_from('<II',pe.raw,address+24+104)
    descriptor=pe.base+rva
    imports=[]
    while pe.u32(descriptor+12):
        original,stamp,chain,name,iat=struct.unpack('<5I',pe.data(descriptor,20))
        module=pe.string(pe.base+name)
        index=0
        while pe.u32(pe.base+(original or iat)+4*index):
            value=pe.u32(pe.base+(original or iat)+4*index)
            if value<0x80000000:
                text=pe.string(pe.base+value+2)
                if text in ('D3DXMatrixPerspectiveFovRH','D3DXMatrixLookAtRH'):
                    imports.append(dict(module=module,name=text,iat=hex(pe.base+iat+4*index)))
            index+=1
        descriptor+=20
    assert {row['name'] for row in imports}=={'D3DXMatrixPerspectiveFovRH','D3DXMatrixLookAtRH'}
    blocks={}
    for name,start,stop in (
        ('perspective_import_thunk',0x8a871c,0x8a8722),('lookat_import_thunk',0x8a86e0,0x8a86e6),
        ('camera_projection_method',0x8e4a80,0x8e4adb),('general_camera_reset',0x8e4ae0,0x8e4bb4),
        ('camera_lookat_method',0x8e4c00,0x8e4c36),('projection_secondary_consumer',0x8e5030,0x8e507c)):
        raw=pe.data(start,stop-start)
        blocks[name]=dict(start=hex(start),stop=hex(stop),sha256=hashlib.sha256(raw).hexdigest(),listing=pe.listing(start,stop))
    assert 'jmp dword ptr [0x9d6b40]' in blocks['perspective_import_thunk']['listing']
    assert 'jmp dword ptr [0x9d6b58]' in blocks['lookat_import_thunk']['listing']
    assert all(line in blocks['camera_projection_method']['listing'] for line in (
        'movss xmm0, dword ptr [esi + 8]','mulsd xmm0, qword ptr [0x9fc5d8]',
        'cvtpd2ps xmm0, xmm0','fld dword ptr [esi + 0xc]','fld dword ptr [esi + 0xd0]',
        'fld dword ptr [esi + 0xd4]','call 0x8a871c'))
    values=dict(degrees_to_radians=struct.unpack('<d',pe.data(0x9fc5d8,8))[0],
        reset_near=struct.unpack('<f',pe.data(0x9f72f4,4))[0],
        reset_far=struct.unpack('<f',pe.data(0xa01238,4))[0])
    assert values==dict(degrees_to_radians=0.017453292519943295,reset_near=1.0,reset_far=10000.0)
    pe.verify()
    with (ROOT/'camera_retail_contract.json').open('x',encoding='utf8') as stream:
        json.dump(dict(status='PASS_STATIC_CAMERA_MATRIX_OPERATIONS',original=pe.before,
            imports=imports,blocks=blocks,values=values,
            decoded_fields=dict(fov_degrees='+8',aspect='+c',near='+d0',far='+d4'),
            limitations=['general camera operations are not a trace of the active world-camera instance',
                'runtime D3DX normalization and tangent precision are unverified',
                'world FOV, zoom curve, map unit scale and pose remain unresolved'],
            original_camera_calibration_verified=False,native_host_sdk_clr_hwnd_gpu_audio_or_game_executed=False),stream,indent=2)
        stream.write('\n')
    print(json.dumps(dict(status='PASS_STATIC_CAMERA_MATRIX_OPERATIONS',blocks=len(blocks),imports=len(imports))))


if __name__=='__main__':
    main()
