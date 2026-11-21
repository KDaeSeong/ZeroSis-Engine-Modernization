"""Seal targeted original normal/RT facts without running original code."""
from pathlib import Path
import hashlib,json,struct
from normal_contract_pe import Image
from normal_contract_bulk_dag import analyze,sum_terms
from normal_contract_reference import Reference

ROOT=Path(__file__).absolute().parent
PROJECT=ROOT.parents[3]


def artifact(path):
    path=Path(path).absolute();info=path.stat();raw=path.read_bytes()
    assert (info.st_dev,info.st_ino,info.st_size,info.st_mtime_ns)==(path.stat().st_dev,path.stat().st_ino,path.stat().st_size,path.stat().st_mtime_ns)
    return dict(path=str(path),bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest(),file_identity=[info.st_dev,info.st_ino],mtime_ns=info.st_mtime_ns)


def main():
    target=ROOT/'normal_contract_semantics.json';assert not target.exists()
    im=Image(r"C:\Program Files (x86)\Steam\steamapps\common\Sid Meier's Civilization V\CivilizationV_DX11.exe")
    original=artifact(im.path)
    ranges={'allocate':(0x5118e0,0x511a70),'writer':(0x5ce920,0x5cf197),'upload':(0x63ccd0,0x63cde0),
        'bulk':(0x728240,0x72966a),'scalar':(0x5e1300,0x5e1a58),'byte_getter':(0x719ba0,0x719c78),
        'kernels':(0x582a60,0x582c80),'cache_descriptor':(0x6cf830,0x6cfa2b),'normal_descriptor':(0x515630,0x5156b5),
        'temp_creation':(0x678787,0x678955),'rt_create':(0x8bc880,0x8bcb5e),'resolution':(0x453f80,0x454226),
        'normal_pass':(0x6958fe,0x6959bd),'chunk':(0x694a60,0x695d24)}
    blocks={};instructions={}
    for name,(start,stop) in ranges.items():
        raw=im.read(start,stop-start);listing=im.listing(start,stop);instructions[name]=listing
        blocks[name]=dict(start=f'{start:08x}',stop=f'{stop:08x}',bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest(),instructions=len(listing))
    checks=[]
    def prove(name,block,needles):
        rows=instructions[block];matched=[]
        for needle in needles:
            row=next(row for row in rows if row['instruction']==needle);matched.append(row)
        checks.append(dict(name=name,block=block,pass_=True,matched=matched))
    prove('24byte_source_allocation','allocate',['mov dword ptr [edi + 0x308], eax','add edx, edx'])
    prove('writer_selects_bulk_and_point_fallback','writer',['call 0x728240','call 0x719ba0','mov esi, dword ptr [edi + 0x308]'])
    prove('float_normal_projection_precedes_half','writer',['comiss xmm0, dword ptr [0x9fcec8]','mov dword ptr [esp + 0x18], 1','mov dword ptr [esp + 0x18], 2','call 0x8a86da'])
    prove('half4_normal_and_half2_uv_24byte_vertex','writer',['mov dword ptr [esi + 0xc], ecx','mov dword ptr [esi + 0x10], edx','mov dword ptr [esi + 0x14], eax'])
    prove('cache_decl12_uses_normal24_vertex_pool','cache_descriptor',['mov byte ptr [edx + 0x7c], 0xc','mov ecx, dword ptr [esi + 0xcc]','mov dword ptr [edx + 0x14], ecx'])
    prove('compressed_xy_decode','byte_getter',['subss xmm0, xmm1','mulss xmm0, xmm2','fsubp st(1)','fsqrt','call 0x5e1300'])
    prove('kernel_matrices_are_constructor_products','kernels',['lea eax, [esi + 0xffcc]','movss dword ptr [eax - 0x64], xmm2','movss dword ptr [eax + 0x10], xmm0'])
    prove('bulk_signed_halves_and_final_division','bulk',['sar ebx, 1','sar edx, 1','divps xmm6, xmm7','divps xmm5, xmm6','call 0x8a8698'])
    prove('original_normal_temp_rgba8_and_material_float16','temp_creation',['push 0x102','push 0xa','mov dword ptr [ebx + 0x6a0], eax','mov dword ptr [ebx + 0x694], eax'])
    prove('rt_rgba8_typeless_and_dual_srv_views','rt_create',['cmp eax, 0x102','mov edx, 0x1c','mov ecx, 0x1b','mov dword ptr [esp + 8], 0x1d','mov dword ptr [esp + 0x6c], 0x28'])
    prove('runtime_width_quality_choices','resolution',['mov esi, 0x100','lea ebp, [esi - 0x80]','mov dword ptr [0xd90f2c], 0x200','mov dword ptr [0xd90f2c], esi','mov dword ptr [0xd90f2c], ebp'])
    bulk=im.instructions(0x728679,0x7294a8)
    for left,right in ((0x7289a2,0x7289a5),(0x728f97,0x728f9a)):
        assert [next(ins for ins in bulk if ins.address==address).mnemonic+' '+next(ins for ins in bulk if ins.address==address).op_str for address in (left,right)]==['addps xmm6, xmm0']*2
    checks.append(dict(name='zero_derivative_row_still_advances_reference_twice',pass_=True,addresses=['007289a2','007289a5','00728f97','00728f9a']))
    graph=analyze(im)
    orders=[dict(final_div=f'{address:08x}',numerator_terms=[[f'{v:05x}' for v in term] for term in sum_terms(numerator)],
        denominator_terms=[[f'{v:05x}' for v in term] for term in sum_terms(denominator)]) for address,numerator,denominator in graph]
    constants={}
    for name,address in dict(byte_center=0x9ff880,reciprocal255=0x9f9e34,projection_threshold=0x9fcec8,range_quadratic=0x9e4450,
        bulk_norm=0xa09cb4,range_scale_squared=0xa01e88,a0=0xa03a18,a1=0x9da18c,a2=0x9d9998,b0=0x9f5c44,b1=0x9fd118).items():
        raw=im.read(address,4);constants[name]=dict(va=f'{address:08x}',bits='0x'+raw[::-1].hex(),value=struct.unpack('<f',raw)[0])
    assert constants['byte_center']['value']==128 and constants['reciprocal255']['bits']=='0x3b808081'
    imported=im.imports();assert imported[0x9d6b5c]==dict(dll='d3dx9_42.dll',name='D3DXFloat32To16Array')
    dll=Image(r'C:\Windows\SysWOW64\d3dx9_42.dll','f8b9cfab7fffbc8f98e41aa439d72921dc180634a1febca2a9d41a0df35d3472')
    half_block=dll.read(0x1002ea3c,0xa6)
    reference=Reference()
    flat=[]
    for raw in (0,1,15300,32768,65535):
        derivative,normal,half=reference.compute([raw]*25,(1/64,1/64,2.3*255/65535))
        flat.append(dict(raw_constant=raw,derivative=derivative,candidate_equal_xy_normal=normal,half=half))
    cpu=artifact(ROOT/'normal_contract_cpu/attempt04/normal_contract_result.json')
    im.finish();dll.finish();reference.image.finish();assert artifact(im.path)==original
    report=dict(schema='zerosis.phase8.original_normal_cache.static_contract.v1',status='PASS_TARGETED_NORMAL_PRODUCTION_AND_CACHE_FORMAT_TRACE',
        original_exe=original,blocks=blocks,checks=checks,check_count=len(checks),constants=constants,unrolled_sum_order=orders,
        confirmed=dict(producer='0x5ce920: heightmap +53c bulk0x728240, out-of-batch getter0x719ba0, 24B stream+308; upload0x63ccd0/0x691750',
            layout='CPU-written 24B payload: float3 position at0, HALF4(raw normalized float XYZ,1) at12, HALF2 UV at20. CacheBake descriptor selects declaration12 and the corresponding pooled base vertex.',
            projection='The same unquantized float normal is tested before half packing: z>float32(.9) =>0; otherwise absY>absX =>1, else2.',
            bulk='Unsigned raw height*float32(1/255); A=[.0228,.2293,.4948,.2293,.0228], B=[.0702,.3526,0,-.3526,-.0702]. Derivative matrices omit four corners. RefX=center-2*SAR(east-west,1)/255, RefY analogous; references advance +1 per row/column including the skipped zero derivative row.',
            range_weight='q=(reference-H)^2*float32(-10/3)*float32(1/16384); W=float32(1.03)*(1+q+.5*q*q)*matrixCoefficient; derivative=sum(W*H)/sum(abs(W)) in the recorded unrolled order.',
            normal='Z-up normalize(metricY*derivativeX*heightScale, metricX*derivativeY*heightScale, metricY*metricX); metrics are heightmap+a8/ac/b0.',
            compressed_xy='Getter active-cache branch: x=(byteX-128)*float32(1/255), y likewise, z=sqrt(1-x*x-y*y); no2*UNORM-1.',
            scratch_format='Material-height source +694: requested DXGI10 RGBA16_FLOAT. Actual normal-pass output +6a0: requested custom0x102, resource DXGI27 RGBA8_TYPELESS plus default view28 UNORM and additional view29 SRGB.',
            scratch_size='Width=height=globalD90F2C; quality globalD90F74 and device branches select128/256/512. Mips argument0 requests full bit-length(width) mip allocation, sampleCount1, bindFlags0x28.'),
        legacy_scalar_fallback=dict(address='005e1300',different_from_bulk=True,range_polynomial_order=3,
            bulk_bit_equivalence_claimed=False,note='Retained separately; x87 accumulation/imported normalization precision is not bit-verified by bulk goldens.'),
        half_conversion=dict(imported_function=imported[0x9d6b5c],system_dll_as_data=artifact(dll.path),scalar_block_va='1002ea3c',
            scalar_block_sha256=hashlib.sha256(half_block).hexdigest(),unit_normal_RNE_confirmed=True,runtime_dispatch_selection_verified=False),
        flat_positive_height_behavior=flat,cpu_reference=cpu,
        explicit_current_policies=['Unknown centre =>up; unknown neighbour numeric value is not read and is replaced by known centre.',
            'Finite guards and double-length normalization; original D3DX runtime dispatch/precision remains unverified.',
            'Current atlas raw reconstruction round((height+offset)*65535), world/metric scale mapping and wrap handling remain calibration candidates.'],
        unresolved=['Actual per-draw RTV/SRV choice between UNORM28 and SRGB29 is not established by the creation trace.',
            'Original compressed cache codecs and cross-frame residency/order remain untraced; local chunk draw order is separate.',
            'Runtime-selected cache resolution/mip update/resampling/view policy and tessellation basis are not accepted as current equal output.'],
        prior_evidence_modified=False,raw_binary_payloads_created=0,original_dll_or_exe_loaded_or_executed=False,
        host_gamecore_clr_hwnd_gpu_audio_or_game_executed=False)
    with target.open('x',encoding='utf-8',newline='\n') as stream:json.dump(report,stream,indent=2);stream.write('\n')
    print(json.dumps(dict(status=report['status'],checks=len(checks),path=str(target),sha256=hashlib.sha256(target.read_bytes()).hexdigest())))


if __name__=='__main__':main()
