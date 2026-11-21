"""File-only regression checks of the idle cache integration and unchanged math."""
from __future__ import annotations
import difflib
import gzip
import json
from pathlib import Path
import sys

sys.dont_write_bytecode=True
STAGE=Path(__file__).absolute().parent
PROJECT=STAGE.parents[2]
sys.path.insert(0,str(PROJECT/'tools'))
import build_exit_confirm_host as common

def previous(name):
    paths=list((STAGE/'source_before').glob(name.replace('/','__')+'.*.gz'))
    assert len(paths)==1
    return gzip.decompress(paths[0].read_bytes()).decode('utf8').replace('\r\n','\n')

def between(text,start,end):
    begin=text.index(start)
    return text[begin:text.index(end,begin)]

def lines(text):
    return [line.strip() for line in text.splitlines() if line.strip()]

def main():
    output=STAGE/'source_integration_review2.json'
    prior=common.artifact(output) if output.exists() else None
    if prior:assert json.loads(output.read_text('utf8'))['schema']=='zerosis.idle_cache.source_integration.v1'
    name='Source/Presentation/WorldTerrainRenderer.cpp'
    before=previous(name);after=(PROJECT/name).read_text('utf8')
    checks={}
    for label,start,end in [
        ('ground_geometry_material_fog_projection_unchanged','for(const auto& p:view.plots){','Require(result.triangles<=3000000'),
        ('unit_visibility_art_pose_geometry_unchanged','std::map<unsigned,Group> unitGroups;','for(auto& entry:unitGroups)'),
        ('id_anchor_and_raster_contour_math_unchanged','for(auto it=result.centers.begin();','if(callerTarget)')]:
        a=between(before,start,end);b=between(after,start,end)
        if label=='id_anchor_and_raster_contour_math_unchanged':
            b=b[:b.index('// Own a separate copy:')]
        if label=='unit_visibility_art_pose_geometry_unchanged':
            b=b[:b.index('for(auto it=cache.unitBuffers.begin();')]
        checks[label]=lines(a)==lines(b)
    host='Source/Host/InteractiveGameLoop.h'
    before_host=previous(host);after_host=(PROJECT/host).read_text('utf8')
    expected=before_host.replace('RenderWorldViewToTexture(retainedView,device,context,target,&candidate,why,nullptr);',
        'RenderWorldViewToTexture(retainedView,device,context,target,&candidate,why,nullptr,false);')
    checks['animation_clock_overlay_generation_and_input_checks_unchanged']=expected==after_host
    checks['single_owner_cache_and_separate_metadata_copy']=all(s in after for s in (
        'WorldTerrainReuse<GroundData> ground;', 'if(groundData)result=groundData->metadata;',
        'candidate->metadata.picking=result.picking;', 'candidate->metadata.projectedPlots=result.projectedPlots;'))
    checks['clear_depth_each_pose_before_ground_and_units']=(after.index('ClearDepthStencilView(surfaces.depthView.Get()')<
        after.index('for(const auto& entry:groundData->groups)')<after.index('std::map<unsigned,Group> unitGroups;'))
    checks['candidate_id_readback_only']=('if(candidate){\n            result.picking.indices.resize' in after and
        after.count('ReadBack(cache,surfaces.ids.Get()')==1)
    checks['publish_after_complete_metadata_and_target_copy']=(after.index('candidate->metadata.projectedPlots=')<
        after.index('if(callerTarget)cache.context->CopyResource')<after.index('cache.ground.Publish(')<after.index('*frame=std::move(result)'))
    checks['bounded_viewport_targets_replace_only_after_all_views_created']=(after.index('CreateDepthStencilView(next->depth.Get()')<
        after.index('cache.targets.swap(next)'))
    checks['unit_dynamic_buffer_discard_upload_and_capacity_guard']=all(s in after for s in (
        'retained.capacity!=bytes', 'D3D11_USAGE_DYNAMIC', 'D3D11_MAP_WRITE_DISCARD',
        'std::memcpy(mapped.pData,vertices.data(),bytes);', 'cache.unitBuffers.clear();'))
    checks['inactive_unit_groups_evicted']=('if(!unitGroups.count(it->first))it=cache.unitBuffers.erase(it);' in after)
    checks['no_unit_assets_release_prior_unit_buffers']='else cache.unitBuffers.clear();' in after
    # Keep unchanged physical lines as they were, including legacy mixed endings.
    changed=[]
    for name in ['Source/Presentation/WorldTerrainRenderer.cpp','Source/Presentation/WorldTerrainRenderer.h',
                 'Source/Presentation/WorldViewRenderer.cpp','Source/Presentation/WorldViewRenderer.h','Source/Host/InteractiveGameLoop.h']:
        path=PROJECT/name
        backup=next((STAGE/'source_before').glob(name.replace('/','__')+'.*.gz'))
        old=gzip.decompress(backup.read_bytes()).decode('utf8').splitlines(True)
        new=path.read_text('utf8').splitlines(True)
        matcher=difflib.SequenceMatcher(None,[s.rstrip('\r\n') for s in old],[s.rstrip('\r\n') for s in new],autojunk=False)
        pieces=[];count=0
        for tag,i,j,a,b in matcher.get_opcodes():
            if tag=='equal':pieces.extend(old[i:j])
            else:
                pieces.extend(s.rstrip('\r\n')+'\r\n' for s in new[a:b]);count+=max(j-i,b-a)
        raw=''.join(pieces).encode('utf8')
        if raw!=path.read_bytes():path.write_bytes(raw)
        changed.append(dict(source=common.artifact(path),changed_lines=count))
    value=dict(schema='zerosis.idle_cache.source_integration.v1',status='PASS' if all(checks.values()) else 'FAIL',
        checks=checks,changed_sources=changed,reviewer=common.artifact(__file__),
        scope='Source comparison and integration guards only; actual cache policy CPU tests are separate.',
        gpu_d3d_shader_or_native_game_executed=False,measured_live_cpu_reduction=False)
    if prior:value['superseded_generated_check']=dict(sha256=prior['sha256'],bytes=prior['bytes'],reason='Bound unit buffers to exact current-frame sizes and evict inactive groups before source freeze.')
    with output.open('w' if prior else 'x',encoding='utf8') as f:json.dump(value,f,indent=2);f.write('\n')
    assert all(checks.values()),checks
    print(json.dumps(dict(status=value['status'],checks=len(checks),changed_source_files=len(changed))))

if __name__=='__main__':main()
