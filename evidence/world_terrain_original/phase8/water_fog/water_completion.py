"""Seal owned water FOW sources and bounded offline evidence, without running a renderer."""
from pathlib import Path
import json,sys
sys.dont_write_bytecode=True
PROJECT=Path(__file__).absolute().parents[4]
sys.path.insert(0,str(PROJECT/'Tests'))
from original_water_shader import ref,write_new
ROOT=Path(__file__).parent

def main():
    names=['OriginalFogShader.h','OriginalFogGpu.inc','OriginalFogGpuTypes.inc','OriginalWaterSurfaceShader.h','OriginalWaterSurfaceGpu.inc','OriginalWaterSurfaceGpuTypes.inc','OriginalWaterFogBinding.h','OriginalWaterFogModel.h']
    sources=[ref(PROJECT/'Source/Presentation'/n)for n in names]
    tests=[ref(PROJECT/'Tests'/n)for n in ('original_water_fog.cpp','original_water_fog.py','original_water_fog_shader.py')]
    cpu=ROOT/'water_cpu02/water_result.json';shader=ROOT/'water_shader01/water_result.json'
    c=json.loads(cpu.read_text('utf8'));s=json.loads(shader.read_text('utf8'))
    assert c['status'].startswith('PASS_')and c['checks']==7146 and s['status'].startswith('PASS_')
    for r in c['inputs']+s['inputs']:
        current=ref(r['path']);assert all(current[k]==v for k,v in r.items())
    cleanup=[];deleted=allocated=0
    for stage in ('water_cpu01','water_cpu02','water_shader01'):
        p=ROOT/stage/'water_cleanup_result.json';d=json.loads(p.read_text('utf8'));assert d['status'].startswith('PASS')
        for row in d['files']:assert not Path(row['path']).exists()
        cleanup.append(ref(p));deleted+=d['deleted_files'];allocated+=d['released_unique_allocated_bytes']
    binding=PROJECT/'evidence/world_terrain_original/phase6/compiled_asset_binding.json'
    packages=[]
    for role,expected in json.loads(binding.read_text('utf8'))['packages'].items():
        actual=ref(expected['path'])
        for key in ('bytes','sha256','file_identity','mtime_ns','file_attributes'):assert actual[key]==expected[key],(role,key)
        packages.append(dict(role=role,reference=actual))
    seal=ROOT/'water_source_seal.json';write_new(seal,dict(schema='zerosis.original_water_fog.phase8.owned_sources.v1',sources=sources,tests=tests,other_production_source_modified=False))
    result=dict(schema='zerosis.original_water_fog.phase8.offline_completion.v1',status='PASS_OFFLINE_WATER_FRAGMENT_FOG_IMPLEMENTATION',
        source_seal=ref(seal),cpu=ref(cpu),strict_shader=ref(shader),original_blend_boundary=ref(ROOT/'water_original_blend_evidence.json'),
        source_contract=dict(fog_constant_bytes=224,surface_constant_bytes=320,dynamic_shadow_constant_bytes=112,
            fog_marker_srv=11,water_shadow_srv=11,separate_shader_resource_namespaces=True,marker_mrt=4,true_plot_mrt=1,
            marker_format='R8_UINT; root creates only when fog-enabled',fog_output_mrt=[0],unit_marker_value=0,water_marker_value=1,
            colour_order=['already gamma-encoded WaterPS RGB','premultiplied overlay','lerp(.4,colour,FOW.R)','LUT with R*(1-B)','distance fog'],
            water_colour_operations_preserve_input_alpha=True,current_upstream_opaque_scene_alpha=1),
        delivered=['Exact fragment marker distinguishes visible water surface from overlying units, independent of whole-plot water classification.',
            'Unknown public plot branch reaches replacement clouds before marker, scene-colour and LUT reads.',
            'Water post returns before the land branch, so gray/LUT/distance are applied once.',
            'Current projected dynamic-shadow receiver is connected before original water gamma/overlay/FOW operations.',
            'Six strict FXC stages include root embedded legacy unit/fallback Target4 uint-zero output.'],
        packages=packages,new_asset_packages=0,new_raw_asset_copies=0,temporary_deleted_files=deleted,released_owned_allocated_bytes=allocated,cleanup_receipts=cleanup,
        pending=['Final renderer whole-file reseal after screen-lighting integration finishes.','Root complete C++ renderer compile/link.','Actual GPU/game/screen acceptance remains on hold.'],
        candidates=['Neutral overlay source and existing LUT upload/sampling policy; original overlay producer is not bound.',
            'Current opaque water scene composition and RGB-only coast/river alpha blend, not established retail hardware blend state.',
            'Fog masks/distance calibration and fragment-classification policy for coast-on-water overlays.',
            'Private projected shadow camera2048/resolution/bias/PCF/runtime light parameters and silhouette policy.'],
        retail_hardware_blend_verified=False,actual_gpu_parity_verified=False,native_host_gamecore_clr_hwnd_gpu_audio_game_executed=False)
    output=ROOT/'water_completion.json';write_new(output,result)
    files=[ref(p)for p in ROOT.rglob('*')if p.is_file()]
    print(json.dumps(dict(status=result['status'],source_seal=ref(seal),completion=ref(output),cleanup_files=deleted,released_allocated_bytes=allocated,water_evidence_bytes=sum(r['bytes']for r in files),water_evidence_allocated_bytes=sum(r['allocated_bytes']for r in files))))

if __name__=='__main__':main()
