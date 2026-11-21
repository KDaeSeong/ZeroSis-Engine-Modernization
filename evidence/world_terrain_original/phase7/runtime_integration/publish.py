"""Publish file-only runtime integration receipts without native/default promotion."""
from datetime import datetime, timezone
from pathlib import Path
import argparse, hashlib, json, sys
sys.dont_write_bytecode = True
STAGE = Path(__file__).absolute().parent
PROJECT = STAGE.parents[3]
sys.path.insert(0, str(PROJECT / 'tools'))
import build_exit_confirm_host as common


def read(path):
    return json.loads(Path(path).read_text('utf8'))


def ref(path):
    return common.artifact(Path(path).absolute())


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf8')


def publish():
    output = STAGE / 'current_work.json'
    assert not output.exists()
    overlay = read(STAGE / 'overlay/result.json')
    previous_path = PROJECT / 'evidence/world_terrain_original/phase6/current_work.json'
    previous = read(previous_path)
    assert overlay['status'].startswith('PASS') and overlay['native_attempts'] == 0
    assert not overlay['default_or_registration_changed'] and overlay['new_game_only']
    proofs = {name: ref(STAGE / name) for name in (
        'contracts/contract_preparer_audit.json', 'contracts/contract_overlay_plan_review.json',
        'contracts/contract_final_verification.json', 'assets/asset_final_verification.json',
        'storage/storage_overlay_verification.json', 'overlay/preflight_verification.json')}
    for name, row in proofs.items():
        assert read(row['path'])['status'].startswith('PASS'), name
    storage = read(STAGE / 'storage/storage_overlay_verification.json')
    root = Path(overlay['runtime_directory'])
    assert overlay['host']['sha256'] == previous['current_host']['executable']['sha256']
    assert overlay['gamecore']['sha256'] == previous['packages'].get('gamecore', {}).get('sha256',
        '430f3122d0b555d6daae14aa7c011ef43ce8f978270477c8af596ca4b0493ab9')
    value = dict(schema='zerosis.phase7.isolated_runtime.current_work.v1', utc=datetime.now(timezone.utc).isoformat(),
        status='PASS_PHASE7_LATEST_PHASE6_RUNTIME_INTEGRATED_FILE_ONLY_NATIVE_PENDING',
        completed_scope='Latest compiled Host/unchanged attested SDK/five original packs/UI support integrated into one private new-game-only runtime; file-level verification only.',
        full_goal_redefined=False, full_engine_goal_complete=False,
        current_host=previous['current_host'], previous_source_milestone=ref(previous_path),
        current_prepared_runtime=dict(run_id=overlay['run_id'], runtime_directory=str(root), host=overlay['host'],
            gamecore=overlay['gamecore'], launcher=overlay['launcher'], request=overlay['request'],
            asset_manifest=overlay['asset_manifest'], backend_manifest=overlay['backend_manifest'],
            backend_input_count=24, backend_payload_count=23, required_ui_sidecar_files=154, frozen_support_modules=6,
            new_game_only=True, cross_bundle_resume_allowed=False, native_attempts=0, default_or_global_registration_changed=False),
        packages=overlay['packages'], shared_support=overlay['shared_support'], overlay_result=ref(STAGE / 'overlay/result.json'),
        base_preparation_result=overlay['base_result'], base_snapshot=overlay['base_snapshot'],
        base_result_interpretation='Historical before-overlay image; superseded request/manifest/launcher bytes are preserved in base_snapshot. Final overlay/request/asset manifests are authoritative.',
        proofs=proofs, source_engine_changes=0, host_rebuilds=0, new_asset_packages=0,
        additional_asset_payload_copies=0, immutable_support_copies_removed=8,
        latest_source_matches_linked_candidate=True, prepared_runtime_matches_latest_source=True,
        native_host_sdk_clr_hwnd_gpu_audio_or_game_attempts=0, new_game_runtime_materialized=True,
        actual_runtime_acceptance=False, original_screen_equivalence_verified=False,
        preserved_previous_runtime='Build/InteractiveGameRuntime/20261115T011241Z_4c8fd55e99db',
        preserved_user_session='Build/InteractiveGameRuntime/20261108T003146Z_40a8030edf08/sessions/350dd3b9ceb408a391b5a8aa63b48301',
        protection=dict(before=ref(STAGE / 'protection_before.json.gz'), after_pending=True),
        storage=dict(before=ref(STAGE / 'storage_before.json'), after_pending=True, full_project_copies_created=0,
            mutable_db_bytes=57501696, payload_allocation_bytes=65560880, payload_budget_bytes=64 * 1024**2,
            payload_scope='New runtime/Host-cache unique IDs; evidence and directory allocation excluded. Project-wide change recorded separately.',
            exact_cleanup=overlay['cleanup_receipt'], confirmed_disposable_bytes=0, threshold_bytes=10 * 1024**3),
        remaining=previous['remaining'], piece_placement_report=previous['piece_placement_report'])
    assert value['storage']['payload_allocation_bytes'] <= value['storage']['payload_budget_bytes']
    save(output, value)
    index_path = PROJECT / 'evidence/save_menu/20261013_original_screen/current_progress.json'
    index = read(index_path)
    index.update(utc=value['utc'], status=value['status'], current_source_working_stage=str(STAGE),
        current_offline_stage=ref(output), current_prepared_runtime=value['current_prepared_runtime'],
        latest_source_matches_linked_candidate=True, prepared_runtime_matches_latest_source=True, full_engine_goal_complete=False,
        isolated_runtime_phase7_status='LATEST_PHASE6_HOST_AND_FIVE_PACKS_INTEGRATED_FILE_ONLY_NATIVE_PENDING')
    save(index_path, index)
    notes = (f'# 최신 빌드 격리 실행 묶음 연동 — 7단계\n\n2026-11-15. 최신 Host `20261115T093013Z_23c5037b12b9`와 '
        f'SDK430을 새 묶음 `{overlay["run_id"]}`에 연결했다. 엔진 소스 수정·Host 재빌드0회, '
        'Host/GameCore/CLR/창/GPU/음향/실게임 실행0회다. 기본 실행·전역 등록·원본 게임/MODS/설정·사용자 저장은 변경하지 않았다.\n\n'
        f'위치: `{root}`. `Play.ps1`에는 실제 원본 실행기 본문을 그대로 남기고, '
        '앞에 4개 묶음 내부 환경 경로와 파일 전용 검사만 추가했다. 실행 자체는 보류다. '
        'Resume.ps1의 이전 묶음 저장 불러오기 차단도 유지했다.\n\n'
        '기존 준비 도구의 명시적 프로필 경로와 실행 차단 감사 가드를 재사용했다. '
        '첫 시도는 사용자 지정 출력 부모 폴더가 없어 runtime 생성 전에 멈췄으며, '
        '부모를 만든 새 경로에서 파일 준비가 성공했다. 실패 원문/호출 기록을 남겼고 실제 runtime은 하나만 생성했다.\n\n'
        '기본 파일 준비가 끝난 새 묶음에만 별도 파일 어댑터를 적용했다. '
        '원래 request/bundle.manifest/Play 원문은 작은 gzip으로 보존했다. 기본 준비 영수증은 변경 전 이력이고, '
        '최종 overlay/result.json·현재 request·WorldAssets/assets.manifest.json을 최종 근거로 삼는다. '
        '같은 새 묶음을 V1 전용 지형 재사용 도구의 입력으로 무조건 취급하지 않는다.\n\n'
        '지형 V2는 기존 terrain-assets.bin 행을 바꿨다. 안개·물·LEAN·조명은 WorldAssets의 별도 목록에 둬 '
        'V4 backend allowlist(23payload+manifest1)를 유지했다. 다섯 팩130,465,485B는 직접 하드링크라 '
        '새 cache/payload 복사가0이다. source와 target의SHA/ID/mtime/속성을 대조했고 '
        '팩의기존attrs32를바꾸지않았다. 공유자료는읽기전용으로사용하며chmod/내용쓰기를하지않는다.\n\n'
        '같은 UI 준비자료·아이콘·지원Python6개도 기존4c8f 입력으로 공유해 새 사본8개를 제거했다. '
        '반면 rules.db/localization.db57,501,696B와기존private모델/config사본정책은유지했다. '
        '새세션·옵션은새runtime아래에만생기도록기존경계를보존했다. UI154·지원6개·원본font/UI읽기루트·UnitV2/애니메이션·SDK를독립대조했다.\n\n'
        '실제파일전용사전검사와잘못된pin/경로4개거부,계약/자산/저장독립검토가통과했다. '
        '새핵심자료고유실할당65,560,880B(약62.52MiB)는64MiB예산안이다. '
        '이값은증거/디렉터리를제외하며전체폴더증가량과다르다. 중복지원8개의실할당8,212,480B를정리했고 '
        '구형지형cachealias1개삭제는payload회수0B로구분했다.\n\n'
        '남은원본조명/카메라/동적그림자·성능·UI/클릭/저장/모드/멀티코어·실제GPU/원본화면관문은그대로다. '
        '현재의파일연동성공은실게임수락을뜻하지않는다. 상태: '
        '`evidence/world_terrain_original/phase7/runtime_integration/current_work.json`.\n')
    (PROJECT / 'docs/RUNTIME_PHASE7_INTEGRATION.md').write_text(notes, encoding='utf8')
    path = PROJECT / 'docs/CLAUDE_HANDOFF.md'
    head, tail = path.read_text('utf8').split('\n', 1)
    entry = (f'## 최신 빌드 격리 실행 묶음 연동 — 2026-11-15\n\n'
        f'최신23c5037 Host/SDK430을 새 `{overlay["run_id"]}`에 파일 전용으로 연동했다. '
        '이제최신소스·컴파일본·격리준비본이일치한다. 다섯원본팩직접하드링크·UI154/지원6개·4ENV·새DB격리·'
        '파일사전검사/독립계약·자산·저장검사를통과했다. 소스/재빌드0·게임/Host/GPU실행0·기본실행/등록변경0이다. '
        '기존4c8f와40a사용자저장은보존했다. 새핵심실할당62.52MiB,새팩복사0·중복지원8개회수7.83MiB다. '
        '원본화면/게임플레이수락은계속보류다. 상세는 `docs/RUNTIME_PHASE7_INTEGRATION.md`, '
        '최종상태는 `evidence/world_terrain_original/phase7/runtime_integration/current_work.json`이다.\n\n')
    path.write_text(head + '\n\n' + entry + tail.lstrip('\n'), encoding='utf8')
    print(json.dumps(dict(status=value['status'], run_id=overlay['run_id'], native_attempts=0, default_promoted=False)))


def close():
    path = STAGE / 'current_work.json'
    value = read(path)
    assert value['storage']['after_pending']
    protection = read(STAGE / 'protection_after.json')
    assert protection['status'] == 'PASS'
    before, after = read(STAGE / 'storage_before.json'), read(STAGE / 'storage_after.json')
    value['protection'].update(after=ref(STAGE / 'protection_after.json'), after_pending=False)
    value['storage'].update(after=ref(STAGE / 'storage_after.json'), after_pending=False,
        before_unique_allocated_bytes=before['unique_allocated_bytes'], after_unique_allocated_bytes=after['unique_allocated_bytes'],
        allocated_bytes_change=after['unique_allocated_bytes']-before['unique_allocated_bytes'],
        measurement='Real os.stat identities deduplicate hardlinks; small close/index receipts follow scan.')
    save(path, value)
    index_path = PROJECT / 'evidence/save_menu/20261013_original_screen/current_progress.json'
    index = read(index_path)
    index['current_offline_stage'] = ref(path)
    save(index_path, index)
    print(json.dumps(dict(status='PASS_CLOSED_FILE_ONLY_RUNTIME_INTEGRATION', run_id=value['current_prepared_runtime']['run_id'],
        protected=protection['paths'], project_unique_allocated_bytes=after['unique_allocated_bytes'],
        allocated_bytes_change=value['storage']['allocated_bytes_change'], native_attempts=0)))


if __name__ == '__main__':
    cli = argparse.ArgumentParser()
    cli.add_argument('action', choices=['publish', 'close'])
    args = cli.parse_args()
    publish() if args.action == 'publish' else close()
