"""Publish the verified offline candidate; preserve registered/prepared choices."""
from datetime import datetime, timezone
import gzip
import hashlib
import json
from pathlib import Path

P=Path(__file__).resolve().parents[4]
S=P/'evidence/game_menu/original_menu_followup'
identifier='20261101T091435Z_bc34fab66a03'

def read(path):return json.loads(path.read_bytes())
def ref(path):
    raw=path.read_bytes()
    return dict(path=str(path),bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())

def main():
    build_path=P/'evidence/ui_window_host'/identifier/'build_result.json'
    build=read(build_path)
    assert ref(build_path)['sha256']=='cd167cb92abb1dc02b53893c87123c741f8a27bbf11434dbaf2f8d20cb9e3404'
    pair=S/'pair_preparation'/identifier
    att=read(pair/'independent_attestation.json')
    assert att['status'].startswith('PASS_') and att['code_objects_checked']==5
    cleanup=read(pair/'cleanup_result.json')
    assert cleanup['files_deleted']==6 and cleanup['current_image_unchanged'] is True
    sidecar=read(S/'host_build/sidecar.json')
    assert sidecar['build_id']==identifier and sidecar['hardlinked_files']==62
    stages={name:ref(S/relative) for name,relative in {
        'options':'options/final_result.json','frontend':'frontend/final.json',
        'replay':'replay/completion.json','embedding':'options/embedding_cross_tests.json',
        'slider_boundary':'integration/cpp_slider_result.json',
        'independent_host':f'pair_preparation/{identifier}/independent_attestation.json',
        'intermediate_cleanup':f'pair_preparation/{identifier}/cleanup_result.json',
        'sidecar':'host_build/sidecar.json',
    }.items()}
    progress_path=P/'evidence/save_menu/20261013_original_screen/current_progress.json'
    before=progress_path.read_bytes();progress=json.loads(before)
    backup=S/'integration/changed_file_backups'/('current_progress.'+hashlib.sha256(before).hexdigest()[:16]+'.json.gz')
    assert not backup.exists();backup.write_bytes(gzip.compress(before,mtime=0))
    now=datetime.now(timezone.utc).isoformat()
    proof=dict(status='PASS_ACTUAL_CURRENT_CPP_COMPILE_LINK_AND_EMBEDDING_FILE_ONLY',build_id=identifier,
        build_result=ref(build_path),executable=build['executable'],attestation=stages['independent_host'],
        sidecar=stages['sidecar'],host_executed=False,sdk_executed=False,hwnd_created=False,gpu_executed=False)
    progress['prior_current_host_before_original_menu_followup']=progress.get('current_host_build')
    progress['prior_limits_before_original_menu_followup']=progress.get('limits',[])
    progress.update(utc=now,status='PASS_ORIGINAL_MENUS_OFFLINE_COMPILED_UNREGISTERED_NATIVE_HOLD',
        current_host_build_id=identifier,current_registered_host_build_id='20261101T074006Z_c2fd2fe9be38',
        latest_source_matches_linked_candidate=True,latest_host_source_matches_current_link_proof=True,
        latest_source_matches_integrated_syntax_proof=True,latest_cpp_source_matches_actual_host_syntax_proof=True,
        latest_current_source_actual_cpp_compilation_verified=True,
        latest_current_source_compile_link_proof=proof,latest_integrated_syntax_proof=proof,
        latest_actual_host_syntax_proof=proof,latest_current_source_pe_attestation=stages['independent_host'],
        latest_actual_host_syntax_proof_scope='Current generated 74-payload UI header and all five actual frozen translation units; compiler/linker only.',
        latest_source_matches_linked_candidate_scope='Current 657-input Host closure with original front-end sidecar. The registered/prepared Host remains Host4.',
        syntax_proof_uses_preserved_generated_ui_header=False,
        latest_full_source_embedding_limit='Options/common UI payloads are current and linked. Front-end assets are an exact 62-file sidecar. New runtime transport/profile registration and native acceptance are pending.',
        prepared_runtime_matches_current_linked_candidate=False,prepared_runtime_matches_latest_source=False,
        latest_private_prepared_pair_matches_current_host_and_selected_sdk_sources=False,
        default_prepared_runtime_matches_latest_source=False,
        current_native_or_screen_relaunch_allowed=False,screen_verification_deferred=True,
        native_acceptance_complete=False,full_engine_goal_complete=False,default_promoted=False,
        limits=['Full original UI/gameplay/save/mod/multicore acceptance remains open.',
                'Native Host/GameCore/window/GPU and screen verification remain deferred.',
                'Original options are a supported subset; full frontend branches and retail animation/metrics remain incomplete.',
                'Replay uses actual exported records with a simplified map/layout; retail wrapper/original ReplayMap/rich markup remain incomplete.',
                'The new sidecar-bearing candidate is compile-only and unregistered. Existing Host4/SDK430/424fb preparation and default are preserved.'])
    progress['current_host_build']=dict(build_id=identifier,status='COMPILE_ONLY_UNREGISTERED_WITH_REQUIRED_SIDECAR',
        executable=build['executable'],build_result=ref(build_path),attestation=stages['independent_host'],
        current_source_inputs=len(build['current_source_inputs']),compiler_dependency_count=len(build['compiler_inputs']),
        catalog_entries=74,original_ui_layouts=30,sidecar_files=62,sidecar=stages['sidecar'],registered=False,
        host_executed=False,gamecore_loaded=False,screen_verification_deferred=True,full_engine_goal_complete=False)
    progress['current_prepared_runtime']['matches_latest_source']=False
    progress['current_prepared_runtime']['preserved_original_menu_followup']=True
    progress['original_menu_followup_stage']=dict(status='PASS_SOURCE_OFFLINE_COMPONENT_EMBEDDING_COMPILE_AND_SIDECAR_NO_NATIVE',
        evidence=stages,requirements=ref(S/'requirements.json'),registered=False,prepared_runtime_updated=False,
        full_original_options_supported=False,full_original_frontend_supported=False,full_original_replay_viewer_supported=False)
    progress.setdefault('proofs',{})['original_menu_followup']=stages
    progress_path.write_text(json.dumps(progress,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    publication=dict(status=progress['status'],utc=now,build_id=identifier,proof=proof,evidence=stages,
        progress_before=dict(bytes=len(before),sha256=hashlib.sha256(before).hexdigest(),backup=ref(backup)),
        progress_after=ref(progress_path),prepared_runtime_preserved='20261101T080450Z_424fb64608b2',
        registered_host_preserved='20261101T074006Z_c2fd2fe9be38',profile_registration_changed=False,
        native_execution_allowed=False,full_engine_goal_complete=False)
    out=S/'publication.json';assert not out.exists();out.write_text(json.dumps(publication,indent=2)+'\n',encoding='utf8')
    (S/'current_work.json').write_text(json.dumps(dict(status='PASS_OFFLINE_SCOPE_NATIVE_HOLD',build_id=identifier,
        publication=ref(out),remaining='New runtime transport/profile support and deferred native UI/game tests',
        full_engine_goal_complete=False),indent=2)+'\n',encoding='utf8')
    print(json.dumps(dict(status=publication['status'],build_id=identifier,prepared_runtime_updated=False)))

if __name__=='__main__':main()
