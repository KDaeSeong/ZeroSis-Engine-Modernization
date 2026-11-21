"""Seal bounded cache findings and independently checked component inputs."""
from datetime import datetime,timezone
from pathlib import Path
import hashlib
import json
import os
import sys

sys.dont_write_bytecode=True
ROOT=Path(__file__).absolute().parent
PROJECT=ROOT.parents[3]
sys.path[:0]=[str(PROJECT/'tools'),str(ROOT)]
import build_exit_confirm_host as common
from menu_suite_storage import storage
from cache_reference import Reference


def write_new(path,value):
    with Path(path).open('x',encoding='utf8',newline='\n') as stream:
        json.dump(value,stream,ensure_ascii=False,indent=2);stream.write('\n')


def main():
    assert not (ROOT/'cache_completion.json').exists()
    reference=Reference()
    image=reference.image
    required={
        (0x608270,0x6082ac):['call 0x463b10','call 0x70b490'],
        (0x694c9e,0x694d4b):['lea ecx, [eax - 1]','lea edx, [ecx - 1]',
            'mov edx, dword ptr [ebp + 0xd4]','call 0x8a86d4'],
        (0x694d4b,0x694da5):['mulss xmm0, dword ptr [0x9dbbbc]',
            'mulss xmm0, dword ptr [0x9ed65c]','call 0x8a86bc','call 0x8a868c'],
        (0x6958fe,0x6959bd):['movss xmm0, dword ptr [0x9efba8]',
            'divss xmm0, dword ptr [esp + 0x34]','divss xmm1, dword ptr [esp + 0x68]',
            'call 0x8cd6a0','call 0x8ccd80','call 0x8cdb20','call 0x8cd440'],
        (0x8c00e0,0x8c0163):['shr edx, cl','shr eax, cl','mov eax, dword ptr [ecx + 0xb0]'],
        (0x695d24,0x69600b):['call 0x8cd830','call 0x8cdd20','call 0x8cd6a0'],
    }
    for (start,stop),instructions in required.items():reference.assert_instructions(start,stop,instructions)
    imports=image.imports()
    assert imports[0x9d6b60]['name']=='D3DXMatrixOrthoOffCenterRH'
    assert imports[0x9d6b70]['name']=='D3DXMatrixTranslation'
    assert imports[0x9d6b90]['name']=='D3DXMatrixMultiply'
    image.finish()
    result_path=ROOT/'cache_sampling_cpu/attempt01/cache_result.json'
    result=json.loads(result_path.read_text(encoding='utf8'))
    assert result['status']=='PASS_STRICT_CXX14_CACHE_SAMPLING' and result['checks']==2355453
    source=PROJECT/'Source/Presentation/OriginalTerrainCacheSamplingModel.h'
    assert common.artifact(source)==result['inputs_after'][0]
    traces=[ROOT/name for name in ('cache_scratch_coordinates01.json','cache_quad_and_copy01.json',
        'cache_height_globals01.json','cache_height_chain01.json','cache_height_chain02.json','cache_stamp_normalize01.json')]
    contract=dict(schema='zerosis.phase12.cache_sampling.contract.v1',
        status='PASS_BOUNDED_ORIGINAL_CACHE_HEIGHT_AND_COORDINATE_COMPONENT',utc=datetime.now(timezone.utc).isoformat(),
        original=common.artifact(image.path),reference=reference.report(),
        original_owner_adjustment=dict(primary_to_chunk_owner=8,
            evidence=common.artifact(PROJECT/'evidence/world_terrain_original/phase10/cache/cache_owner_contract.json')),
        confirmed=[
            dict(id='stamp-to-heightmap',sites=['00463e2f..00463e5c','0060829b..006082a2','0070b4e7..0070b53e'],
                rule='sum += (pieceU16*float(1/65535)-reference)*float(blendU8)*float(1/255); weight += blend; heightmapU16 = low16(trunc((sum/weight+sameReference)*double65535)).',
                boundary='The source sampler receives the finalized heightmap code, not unconverted piece floats.'),
            dict(id='heightmap-to-world',sites=['0067837e..006783a6','005cebf6..005cec66'],
                rule='worldX=float(texelX)*objectMetricX; worldY=float(texelY)*objectMetricY; worldZ=(float(heightmapU16)*float(1/255))*objectMetricZ.',
                file_defaults=reference.constants,runtime_metric_overrides_closed=False),
            dict(id='source-and-raster-coordinates',sites=['00694c9e..00694da0','005ce9fd..005cea69','005cec99..005ced17'],
                rule='u=(localX+1)/(chunkCellsX+1), v=(localY+1)/(chunkCellsY+1); clip=(2u-1-1/N,1-2v+1/N,0.5). Sampling UV retains (u,v).',
                projection='OrthoOffCenterRH(x0-1,x0+cellsX,y0+cellsY,y0-1,-1,+1)*Translation(-1/N,+1/N,0).',
                raster_inverse='sourceX=x0-1+(SV_POSITION.x+0.5)*(cellsX+1)/N; analogousY.',
                packing_boundary='The retail separate normal-cache vertex stores UV as HALF2; this helper describes the coordinates before that pack.'),
            dict(id='shared-scratch-and-mips',sites=['00694aed..00694b31','00695904..006959b8','008c00e0..008c0161','008c0790..008c07f1'],
                rule='Source shared scratch N is128/256/512, the normal stencil step is1/N. Viewport derives output resource dimensions shifted by output mip. End-stage GenerateMips uses the default UNORM SRV when levels!=1.',
                prior_evidence=common.artifact(PROJECT/'evidence/world_terrain_original/phase10/cache/cache_view_contract.json')),
            dict(id='packed-cache-is-separate',sites=['00694b4d..00694c28','00695d24..0069600b'],
                rule='Advanced path first bakes shared scratch into a selected chunk source, then loops log2(chunkExtent)-2 compression output mips and queues a separate resource copy. Nonadvanced branch renders directly to chunk198.',
                boundary='The packed block-target dimensions and shader registry do not establish a complete bit-identical BC codec or residency schedule.',
                prior_evidence=common.artifact(PROJECT/'evidence/world_terrain_original/phase10/cache/cache_compression_trace.json')),
        ],
        production_api=dict(header=common.artifact(source),namespace='ZeroSisPresentation::OriginalTerrainCacheSampling',
            functions=['FinalizeStampedHeight','QuantizeCenteredHeight','RawHeightToOriginalWorld','NormalizeOriginalHeight',
                'RestoreOriginalHeight','ScratchSampleUv','ScratchRasterUv','ScratchRasterToSource','HaloTexelCenter','GuardedLinearClamp'],
            original_defaults='File-backed object metric defaults1/.866/.2; normalized range(.2*65535/255)/64 is a coordinate-transform result, not a guessed visual strength.',
            privacy='Guard all four bilinear support nodes before any numeric sample, including zero-weight corners. No terrain ID is interpolated.',
            current_adapter='ScratchFootprint default cells64 and HaloTexelCenter describe current bounded chunk policy. Caller supplies original runtime chunk cells to represent retail topology.',
            float_storage_codec='Root may store finalizedU16 in the existing centeredfloat atlas and use independently tested nearest decoding solely as a representation codec; no second stamp truncation is required.'),
        remaining=[
            'Actual runtime height reference and selected display origin; current15300 reference is an explicit calibration candidate.',
            'Runtime updates of file-backed metric defaults, actual world camera and tessellation basis remain separate from this component.',
            'Original x87 extended-precision division cutoff bits versus MSVC x64 double; original invalid overflow/low16 wrap is rejected by this safety policy.',
            'Shared scratch lifetime/residency, dynamic original chunk extents and current68/66 halo geometry equivalence.',
            'Full bit-identical packed CompressBC codec and hardware generated-mip precision are not restored here.',
            'Runtime GPU, final pixels, actual performance and placement equivalence remain unverified.'
        ],controlled_test=common.artifact(result_path),trace_inputs=[common.artifact(path) for path in traces],
        native_engine_executions=0,host_sdk_project_clr_granny_hwnd_gpu_audio_or_game_executed=False,
        original_mods_settings_saves_default_or_registration_modified=False)
    write_new(ROOT/'cache_sampling_contract.json',contract)
    cleanup=json.loads(Path(result['cleanup']['path']).read_text(encoding='utf8'))
    sources=[source,PROJECT/'Tests/original_terrain_cache_sampling.cpp',PROJECT/'Tests/original_terrain_cache_sampling.py',ROOT/'cache_reference.py']
    files=[path for path in ROOT.rglob('*') if path.is_file()]
    seen=set();allocated=0
    for path in files:
        info=path.stat();key=(info.st_dev,info.st_ino)
        if key not in seen:allocated+=storage.allocated(path);seen.add(key)
    completion=dict(schema='zerosis.phase12.cache_sampling.completion.v1',status='PASS_OFFLINE_COMPONENT_READY_FOR_ROOT_INTEGRATION',
        contract=common.artifact(ROOT/'cache_sampling_contract.json'),controlled_cpu=common.artifact(result_path),
        source_inputs=[common.artifact(path) for path in sources],checks=result['checks'],new_source_files=1,new_test_files=2,
        temporary_files_deleted=cleanup['deleted_files'],temporary_allocated_bytes_deleted=cleanup['deleted_allocated_bytes'],
        owned_evidence_before_this_receipt=dict(files=len(files),logical_bytes=sum(path.stat().st_size for path in files),unique_allocated_bytes=allocated),
        host_sdk_project_clr_granny_hwnd_gpu_audio_or_game_executed=False,large_asset_pack_or_world_copy_created=False,
        production_integration_owned_by_root=True)
    write_new(ROOT/'cache_completion.json',completion)
    print(json.dumps(dict(status=completion['status'],checks=result['checks'],contract=common.artifact(ROOT/'cache_sampling_contract.json'),completion=common.artifact(ROOT/'cache_completion.json'))))


if __name__=='__main__':main()
