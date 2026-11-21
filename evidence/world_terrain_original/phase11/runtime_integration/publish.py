"""Record the new file-verified runtime without launching or registering it."""
from datetime import datetime,timezone
from pathlib import Path
import argparse,json,sys
sys.dont_write_bytecode=True
STAGE=Path(__file__).absolute().parent
PROJECT=STAGE.parents[3]
sys.path.insert(0,str(PROJECT/'tools'))
import build_exit_confirm_host as common

def read(path):return json.loads(Path(path).read_text('utf8'))
def ref(path):return common.artifact(Path(path).absolute())
def save(path,value):Path(path).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf8')

def index(value):
    path=PROJECT/'evidence/save_menu/20261013_original_screen/current_progress.json';data=read(path)
    data.update(utc=value['utc'],status=value['status'],current_source_working_stage=str(STAGE),
        current_offline_stage=ref(STAGE/'current_work.json'),current_host_build_id=value['current_host']['build_id'],
        current_prepared_runtime=value['current_prepared_runtime'],latest_source_matches_linked_candidate=True,
        prepared_runtime_matches_latest_source=True,prepared_runtime_matches_current_linked_candidate=True,
        full_engine_goal_complete=False,isolated_runtime_phase11_status='LATEST_PHASE10_HOST_AND_SIX_PACKS_FILE_ONLY_NATIVE_PENDING')
    save(path,data)

def publish():
    output=STAGE/'current_work.json';assert not output.exists()
    previous_path=PROJECT/'evidence/world_terrain_original/phase10/current_work.json';previous=read(previous_path)
    overlay=read(STAGE/'overlay/result.json');root=Path(overlay['runtime_directory'])
    assert overlay['native_attempts']==0 and not overlay['guard_denials'] and overlay['new_game_only']
    assert not (root/'sessions').exists()
    assert overlay['host']['sha256']==previous['current_host']['executable']['sha256']
    assert len(overlay['packages'])==6 and len(overlay['shared_support'])==8
    for row in overlay['packages'].values():
        for key in ('bytes','sha256','file_identity','mtime_ns','file_attributes'):
            assert ref(row['source']['path'])[key]==ref(row['target']['path'])[key]
        assert ref(row['source']['path'])['file_attributes']==32
    proofs={name:ref(STAGE/name) for name in ('contract_preparer_audit.json','contract_overlay_plan_review.json',
        'contract_final_verification.json','asset_final_review.json','storage_final_review.json','preflight_verification.json')}
    assert all(read(row['path'])['status'].startswith('PASS') for row in proofs.values())
    storage=read(STAGE/'storage_final_review.json');charged=storage['core_new_identity_allocated_bytes']
    assert charged<=64*1024**2
    request=read(overlay['request']['path']);assert len(request['runtime_inputs'])==24 and request['resume_from'] is None
    value=dict(schema='zerosis.phase11.isolated_runtime.current_work.v1',utc=datetime.now(timezone.utc).isoformat(),
        status='PASS_PHASE11_LATEST_PHASE10_RUNTIME_AND_SIX_ASSETS_INTEGRATED_FILE_ONLY_NATIVE_PENDING',
        completed_scope='Latest014dd Host/unchanged SDK430/six pinned presentation packs and UI154 linked in one isolated new-game-only runtime.',
        current_host=previous['current_host'],previous_source_milestone=ref(previous_path),
        current_prepared_runtime=dict(run_id=overlay['run_id'],runtime_directory=str(root),host=overlay['host'],
            gamecore=overlay['gamecore'],launcher=overlay['launcher'],request=overlay['request'],
            asset_manifest=overlay['asset_manifest'],backend_manifest=overlay['backend_manifest'],
            backend_input_count=24,backend_payload_count=23,required_ui_sidecar_files=154,
            supplemental_presentation_packs=6,local_presentation_environment_paths=5,
            new_game_only=True,cross_bundle_resume_allowed=False,native_attempts=0,default_or_global_registration_changed=False),
        packages=overlay['packages'],shared_support=overlay['shared_support'],proofs=proofs,
        overlay_result=ref(STAGE/'overlay/result.json'),base_preparation_result=overlay['base_result'],
        base_snapshot=overlay['base_snapshot'],
        base_result_interpretation='Before-overlay history only; current overlay/request/manifests are authoritative.',
        latest_source_matches_linked_candidate=True,prepared_runtime_matches_latest_source=True,
        full_engine_goal_complete=False,full_goal_redefined=False,actual_runtime_acceptance=False,
        original_screen_equivalence_verified=False,source_engine_changes=0,host_rebuilds=0,new_asset_packages=0,
        additional_asset_payload_copies=0,immutable_support_copies_removed=8,
        native_host_sdk_clr_hwnd_gpu_audio_or_game_attempts=0,new_game_runtime_materialized=True,
        original_install_mods_settings_saves_default_or_registration_changed=False,
        retained_previous_runtime='Build/InteractiveGameRuntime/20261115T134603Z_aa8853762399',
        retained_extra_prior_runtime='Build/InteractiveGameRuntime/20261115T101941Z_99b3c393ee9a',
        retained_recovery_runtime='Build/InteractiveGameRuntime/20261115T011241Z_4c8fd55e99db',
        retained_user_session='Build/InteractiveGameRuntime/20261108T003146Z_40a8030edf08/sessions/350dd3b9ceb408a391b5a8aa63b48301',
        retention_reason='No runtime/native acceptance yet. Prior bundles and unique user/test sessions remain protected; ambiguous old roles are not disposable.',
        remaining_scope_results=previous['scope_results'],piece_placement_report=previous['piece_placement_report'],
        protection=dict(before=ref(STAGE/'protection_before.json.gz'),after_pending=True),
        storage=dict(before=ref(STAGE/'storage_before.json'),after_pending=True,
            core_payload_allocated_bytes=charged,core_payload_budget_bytes=64*1024**2,
            core_scope='New runtime plus new Host/cache identity counted once; evidence and directory allocation excluded.',
            exact_cleanup=overlay['cleanup_receipt'],full_project_copies_created=0,existing_asset_package_copies=0,
            confirmed_disposable_bytes=0,threshold_bytes=10*1024**3))
    save(output,value)
    notes=(f"# 최신 빌드 격리 실행 묶음 연동 — 11단계\n\n2026-11-16. 최신 Host `{previous['current_host']['build_id']}`와 기존 SDK430을 새 `{overlay['run_id']}`에 연결했다. "
        '파일 전용 연동이며 엔진 소스 변경·재빌드·Host/GameCore/CLR/창/GPU/음향/게임 실행은 0회다. 기본 실행·등록·원본 설치·MODS·설정·사용자 저장을 변경하지 않았다.\n\n'
        f'위치: `{root}`. 기존 aa885는 직전 준비본, 99b3/4c8f는 이전·복구 자료, 40a의 사용자 저장은 보존했다. 새 게임 전용이며 다른 묶음의 저장을 Resume으로 넘기는 경로는 차단 상태다.\n\n'
        '기존 준비 도구5개의 바이트 핀과 Native 차단 가드를 재사용했다. 새 래퍼는 명시014dd/3e2ad 준비 profile과 별도 증거 루트만 선택한다. 기본 묶음을 1회 준비하고 검토한6팩 overlay를 1회 적용했다. 초기 request/manifest/Play는 작은 gzip 이력으로 보존했으며 최종 overlay/request/manifest가 현재 기준이다.\n\n'
        'terrain/fog/water/LEAN/lighting/screen_light 여섯 팩은 원본과 동일한 파일 ID·SHA·수정 시각·속성을 가진 직접 하드링크다. 새 자산 복사·패키지 생성은 0이다. 정적 specscreenmap은 물 Raw 반사와 분리해 새 ZEROSIS_SCREEN_LIGHT_ASSETS 경로에 연결했다.\n\n'
        '필수 UI154개와 지원 자료8개를 공유하며, 공유 원본의 attrs32/바이트는 변경하지 않았다. DB2개와 GR2/config는 독립 사본이다. Backend V4는23payload+manifest1을 유지하고 보충 자산은 WorldAssets의 별도 고정 목록으로 검증한다.\n\n'
        'Play에는 묶음 내부5환경 경로와 고정 manifest를 읽는 순수Python 검사만 앞에 추가했고 나머지 기존본문은 그대로 보존했다. Play/Resume은 호출하지 않았다. 파일검사 함수/CLI 정상 입력과 잘못된 핀·경로4건 거부를 확인했고 독립 계약/자산/저장 검토도 통과했다.\n\n'
        f'새 핵심 실할당은 {charged:,}B이며64MiB이하다. 기존 지원 자료의 중복8개는8,212,480B를 회수했고 V1 terrain 별칭1개 삭제는 공유payload 회수0B로 구분했다. 전체 프로젝트 전후 용량은 current_work.json의 최종storage를 따른다.\n\n'
        '실제 원본 화면·UI·게임·저장/모드·멀티코어 성능 수락은 보류다. 원본 캐시 재표본화/압축·높이 보정, 반사 카메라/누락 제공자, 숲 GR2/배치·곡면 기저·세계 카메라 연결은 이전 단계의 남은 작업으로 유지한다. **규칙 동등, 배치 동등은 미검증**이다.\n\n'
        '최종 상태: `evidence/world_terrain_original/phase11/runtime_integration/current_work.json`.\n')
    (PROJECT/'docs/RUNTIME_PHASE11_INTEGRATION.md').write_text(notes,encoding='utf8')
    path=PROJECT/'docs/CLAUDE_HANDOFF.md';head,tail=path.read_text('utf8').split('\n',1)
    entry=(f"## 최신014dd 빌드 격리 실행 묶음 연동 — 2026-11-16\n\n최신014dd Host/SDK430을 새 `{overlay['run_id']}`에 파일 전용으로 연결했다. "
        '최신 소스·컴파일본·준비묶음의 Host/SDK/6팩SHA가 일치하고 static specscreenmap을 별도5번째ENV에 연결했다. '
        'UI154/지원8/6팩 직접공유·독립DB/GR2/config·새게임전용/교차Resume차단·독립 계약/자산/저장/사전검사 PASS다. '
        '소스변경·재빌드·Host/SDK/CLR/창/GPU/음향/게임 실행·기본실행/등록변경0이다. 기존 aa885/99b3/4c8f/40a 저장과 기존6팩을 보존했다. '
        '중복지원8개7.83MiB회수·원본 자산복사0이며 실제 게임/화면 수락보류는 유지한다. 상세는 docs/RUNTIME_PHASE11_INTEGRATION.md, 최종상태는 evidence/world_terrain_original/phase11/runtime_integration/current_work.json이다.\n\n')
    path.write_text(head+'\n\n'+entry+tail.lstrip('\n'),encoding='utf8');index(value)
    print(json.dumps(dict(status=value['status'],run_id=overlay['run_id'],core_allocated_bytes=charged,native_attempts=0)))

def close():
    path=STAGE/'current_work.json';value=read(path);assert value['storage']['after_pending']
    extra=STAGE/'storage_private_inputs_addendum.json'
    assert read(extra)['status'].startswith('PASS')
    value['proofs']['storage_private_inputs_addendum.json']=ref(extra)
    protection=read(STAGE/'protection_after.json');assert protection['status']=='PASS' and not protection['differences']
    before,after=read(STAGE/'storage_before.json'),read(STAGE/'storage_after.json')
    value['protection'].update(after=ref(STAGE/'protection_after.json'),after_pending=False)
    value['storage'].update(after=ref(STAGE/'storage_after.json'),after_pending=False,
        before_unique_allocated_bytes=before['unique_allocated_bytes'],after_unique_allocated_bytes=after['unique_allocated_bytes'],
        allocated_bytes_change=after['unique_allocated_bytes']-before['unique_allocated_bytes'],
        measurement='Real os.stat file identities counted once; receipt/index writes follow scan.')
    value['utc']=datetime.now(timezone.utc).isoformat();save(path,value);index(value)
    print(json.dumps(dict(status='PASS_CLOSED_FILE_ONLY_RUNTIME_INTEGRATION',run_id=value['current_prepared_runtime']['run_id'],
        protected=protection['paths'],unique_allocated_bytes=after['unique_allocated_bytes'],delta=value['storage']['allocated_bytes_change'])))

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=('publish','close'));args=parser.parse_args()
    publish() if args.action=='publish' else close()
