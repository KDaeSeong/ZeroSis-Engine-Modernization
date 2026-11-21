"""Thin independent postbuild review; reads bytes, never loads the new Host."""
from pathlib import Path
import ast,hashlib,json,os,re,struct

ROOT=Path(__file__).absolute().parent
PROJECT=ROOT.parents[3]
PHASE=ROOT.parent
BID='20261115T121456Z_dbb01a1f4f50'
def key(path):return os.path.normcase(os.path.abspath(path))
def artifact(path):
    path=Path(path);info=path.stat();raw=path.read_bytes();after=path.stat()
    assert (info.st_dev,info.st_ino,info.st_size,info.st_mtime_ns)==(after.st_dev,after.st_ino,after.st_size,after.st_mtime_ns)
    return dict(path=str(path),bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())
def checked(row):
    value=artifact(row['path']);assert value['sha256']==row['sha256'] and value['bytes']==row.get('bytes',value['bytes']);return value


def main():
    target=ROOT/'normal_contract_postbuild_review.json';assert not target.exists()
    report_path=PROJECT/'evidence/ui_window_host'/BID/'build_result.json'
    report_ref=artifact(report_path);assert report_ref['sha256']=='1334205b2b3cd302ffbd49f4e21184db103423d91c74fa721befc6f85cece07c'
    report=json.loads(report_path.read_bytes());assert report['build_id']==BID and report['status']=='UI_WINDOW_HOST_CANDIDATE_BUILT'
    profile_path=PHASE/'pair_preparation'/BID/'prepared_profile.json';profile_ref=artifact(profile_path)
    assert profile_ref['sha256']=='f351d6ae32fa1d69788a9f945a59c0799ff1c51e3a96cee61952a16d25f5a959'
    profile=json.loads(profile_path.read_bytes())
    assert profile['prepared_profile_only'] is True and profile['globally_registered'] is False and profile['native_execution'] is False
    assert profile['build_id']==BID and key(PROJECT/profile['report_path'])==key(report_path) and profile['report_sha256']==report_ref['sha256']
    proofs={}
    for name in ('run','attestation','audit','cleanup_result','retirement_ledger'):
        path=PROJECT/profile[name+'_path'];row=artifact(path);assert row['sha256']==profile[name+'_sha256'];proofs[name]=json.loads(path.read_bytes())
    run=proofs['run'];assert run['status']=='PASS_CURRENT_MENU_SUITE_HOST_OFFLINE_BUILD_ONLY' and run['build_id']==BID
    assert run['build_result']['sha256']==report_ref['sha256'] and run['denied_operations']==[] and run['host_sdk_clr_window_gpu_or_dll_executed'] is False
    assert run['no_automatic_retry'] is True and run['full_engine_goal_complete'] is False
    plan_path=PHASE/'host_build_retry01/plan.json';plan=json.loads(plan_path.read_bytes())
    assert artifact(plan_path)['sha256']=='aaa51f353c8fd028ee9338508af3715fbe8203e38dcb7b10ed12189a34e37eba'
    assert run['reviewed_preflight']['sha256']==artifact(plan_path)['sha256']
    assert len(run['commands'])==12 and [row['phase'] for row in run['commands']]==plan['direct_child_phases']
    for row in run['commands']:
        assert row['returncode']==0 and 'error_type' not in row
        checked(row['log'])
        text=Path(row['log']['path']).read_bytes();assert not re.search(rb'\bwarning\s+(?:C|LNK)\d+',text,re.I)
    assert len(report['final_compilation']['translation_units'])==len(report['dependency_discovery']['translation_units'])==5
    language=[];dependency_paths=set()
    for row in report['final_compilation']['translation_units']:
        assert row['returncode']==0 and row['actual_dependency_count']==row['expected_dependency_count']
        checked(row['response']);checked(row['dependency_report']);checked(row['log'])
        text=Path(row['response']['path']).read_text('utf-8-sig')
        assert all(flag in text for flag in ('/W4','/WX','/O2','/fp:strict'))
        standards=re.findall(r'/std:c\+\+\d+',text);assert len(standards)==1
        language.append(dict(translation_unit=row['translation_unit'],standard=standards[0],fp_strict=True))
        dependencies=json.loads(Path(row['dependency_report']['path']).read_bytes())['Data']
        dependency_paths.add(key(dependencies['Source']));dependency_paths.update(map(key,dependencies['Includes']))
    assert report['compiler_dependency_count']==len(report['compiler_inputs'])==len(dependency_paths)==642
    assert {key(row['path']) for row in report['compiler_inputs']}==dependency_paths
    assert len(report['current_source_inputs'])==1058 and len(report['sources_changed_from_baseline'])==16 and len(report['new_source_inputs'])==30
    actual={key(row['original_path']):row for row in run['materialized']};current={key(row['path']):row for row in report['current_source_inputs']}
    # Current context includes build tools/receipts; frozen materialization also
    # includes link providers. They are different inventories with equal counts.
    assert len(actual)==len(current)==1058
    selected=[row for row in report['sources_changed_from_baseline']+report['new_source_inputs']]
    frozen_verified=[]
    for row in selected:
        frozen=actual[key(row['path'])]
        assert checked(row)['sha256']==checked(frozen)['sha256']
        frozen_verified.append(dict(original=row['path'],frozen=frozen['path'],sha256=row['sha256']))
    freeze=json.loads((PHASE/'root_source_freeze.json').read_bytes())
    for row in freeze['sources']:
        assert checked(row)['sha256']==checked(actual[key(row['path'])])['sha256']
    def compiled(name):
        source=PROJECT/'Source/Presentation'/name;row=actual[key(source)];assert key(row['path']) in dependency_paths
        return Path(row['path']).read_text('ascii')
    normal=compiled('OriginalTerrainNormalModel.h');terrain=compiled('OriginalTerrainModel.h');gpu=compiled('OriginalTerrainGpu.inc');field=compiled('OriginalLightingFieldGpu.inc')
    assert 'if(outer==2){referenceX=referenceX+1.0f;referenceY=referenceY+1.0f;continue;}' in normal
    assert 'CaptureKnownWindow' in terrain and 'heightScale*(255.0f/65535.0f)' in terrain
    assert 'QuantizeVertexNormal({normal.x,normal.y,normal.z})' in gpu and 'UnbindScreenLighting(cache.context.Get())' in gpu
    assert 'td.Format=DXGI_FORMAT_R8G8B8A8_UNORM' in field and 'td.Format=DXGI_FORMAT_R16_FLOAT' in field
    assert 'PSGetShaderResources(0,45,rawResources.data())' in field and 'PSSetShaderResources(0,45,oldResources.data())' in field
    image=checked(report['executable']);assert image['bytes']==7788544 and image['sha256']==profile['executable_sha256']=='8e67b0fc6c90c354c6341dfcc39f87b5ae030dd564da9bb1210ad602ba3a70e5'
    raw=Path(image['path']).read_bytes();pe=struct.unpack_from('<I',raw,0x3c)[0]
    assert raw[pe:pe+4]==b'PE\0\0' and struct.unpack_from('<H',raw,pe+4)[0]==0x8664 and struct.unpack_from('<H',raw,pe+24)[0]==0x20b
    assert not struct.unpack_from('<H',raw,pe+22)[0]&0x2000
    static=json.loads(Path(run['static_pe']['path']).read_bytes());checked(run['static_pe'])
    assert static['image']['sha256']==image['sha256'] and static['executable_or_dll_loaded'] is False and static['clr_directory_empty'] is True
    assert proofs['attestation']['compiler_input_count']==642 and proofs['attestation']['current_input_count']==1058
    assert proofs['attestation']['code_objects_checked']==5
    assert proofs['audit']['original_Host_SDK_game_window_or_GPU_execution'] is False and proofs['audit']['current_native_or_screen_relaunch_allowed'] is False
    assert proofs['audit']['screen_verification_deferred'] is True and proofs['audit']['globally_registered'] is False
    assert proofs['cleanup_result']['current_image_unchanged'] is True and proofs['cleanup_result']['runtime_default_or_saves_deleted'] is False
    assert proofs['retirement_ledger']['native_execution'] is False
    sidecar=profile['required_sidecar'];assert sidecar['file_count']==len(sidecar['files'])==154
    for row in sidecar['files']:
        left=Path(row['source']['path']).stat();right=Path(row['frozen']['path']).stat()
        assert (left.st_dev,left.st_ino)==(right.st_dev,right.st_ino) and left.st_size==right.st_size
    native_fields=('host_runtime_executed','gamecore_loaded','sdk_linked','mods_updated','stage_updated','default_promoted','sdk_restore_verified',
                   'native_restore_approved','full_engine_goal_complete')
    assert all(report.get(name) is False for name in native_fields)
    assert report['source_inputs_unchanged'] is True and report['provider_inputs_unchanged'] is True
    assert report['menu_suite_builder']['sha256']==checked(plan['builder'])['sha256']=='58259d8d079d8ea0b5c1da011034014d1fc44b6b56de9d692ab360d20750d75f'
    retained=PROJECT/'tools/retained_host_runtime_input.py';tree=ast.parse(retained.read_bytes())
    pins=next(ast.literal_eval(node.value) for node in tree.body if isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='MENU_PROFILE_PINS' for t in node.targets))
    assert BID not in pins
    old_runtime=PROJECT/'Build/InteractiveGameRuntime/20261115T101941Z_99b3c393ee9a'
    old_host=artifact(old_runtime/'ZeroSisHost_x64.exe');assert old_host['sha256']=='fed2c23df266efb74650df573245001b09a21ffaec619baed319ca5f783e0106'
    assert not (old_runtime/'sessions').exists() and not list(old_runtime.glob('interactive-ui-*.json'))
    assert not (PROJECT/'Build/UiWindowHost/20261115T115920Z_a4b5d1514cc1').exists()
    result=dict(schema='zerosis.phase8.normal_contract.thin_postbuild_review.v1',status='PASS_CURRENT_COMPILED_SNAPSHOTS_AND_UNREGISTERED_OFFLINE_PROFILE',
        build_report=report_ref,profile=profile_ref,executable=image,actual_direct_children=12,command_exit_codes=0,compiler_or_linker_warnings=0,
        translation_units=language,actual_compiler_dependency_union=642,current_inputs=1058,changed_existing=16,added_sources=30,
        actual_changed_and_added_frozen_snapshots=frozen_verified,normal_raw_projection_then_half_fetch=True,compiled_normal_cache_RGBA8=True,
        field_CB160_and_45resource_pipeline_preserved=True,private_frontend_hardlinks=154,frontend_payload_copies=0,
        new_profile_globally_registered=False,old_runtime99b3_still_phase6_host=old_host,interrupted_uncertified_build_tree_retired=True,
        immutable_dataset_full_hash_scan_repeated=False,root_full_protection_scan_is_separate=True,
        original_process_records_for_first_attempt_reconstructed=False,native_hold_flags={name:False for name in native_fields},
        verifier_launched_host_sdk_clr_hwnd_gpu_audio_or_game=False,live_original_or_visual_acceptance=False,blockers=[])
    assert artifact(report_path)==report_ref and artifact(profile_path)==profile_ref
    with target.open('x',encoding='utf-8',newline='\n') as stream:json.dump(result,stream,indent=2);stream.write('\n')
    print(json.dumps(dict(status=result['status'],path=str(target),sha256=artifact(target)['sha256'],compiled_snapshot_checks=len(frozen_verified))))


if __name__=='__main__':main()
