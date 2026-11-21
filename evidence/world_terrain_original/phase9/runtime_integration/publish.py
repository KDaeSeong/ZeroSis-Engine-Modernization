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
    previous_path = PROJECT / 'evidence/world_terrain_original/phase8/current_work.json'
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
    value = dict(schema='zerosis.phase9.isolated_runtime.current_work.v1', utc=datetime.now(timezone.utc).isoformat(),
        status='PASS_PHASE9_LATEST_PHASE8_RUNTIME_INTEGRATED_FILE_ONLY_NATIVE_PENDING',
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
        proofs=proofs, startup=ref(STAGE / 'startup.json'), source_engine_changes=0, host_rebuilds=0, new_asset_packages=0,
        additional_asset_payload_copies=0, immutable_support_copies_removed=8,
        latest_source_matches_linked_candidate=True, prepared_runtime_matches_latest_source=True,
        native_host_sdk_clr_hwnd_gpu_audio_or_game_attempts=0, new_game_runtime_materialized=True,
        actual_runtime_acceptance=False, original_screen_equivalence_verified=False,
        preserved_previous_runtime='Build/InteractiveGameRuntime/20261115T101941Z_99b3c393ee9a',
        preserved_recovery_runtime='Build/InteractiveGameRuntime/20261115T011241Z_4c8fd55e99db',
        preserved_user_session='Build/InteractiveGameRuntime/20261108T003146Z_40a8030edf08/sessions/350dd3b9ceb408a391b5a8aa63b48301',
        protection=dict(before=ref(STAGE / 'protection_before.json.gz'), after_pending=True),
        storage=dict(before=ref(STAGE / 'storage_before.json'), after_pending=True, full_project_copies_created=0,
            mutable_db_bytes=57501696, payload_allocation_bytes=storage['metrics']['new_core_payload_allocated_bytes'], payload_budget_bytes=64 * 1024**2,
            payload_scope='New runtime/Host-cache unique IDs; evidence and directory allocation excluded. Project-wide change recorded separately.',
            exact_cleanup=overlay['cleanup_receipt'], confirmed_disposable_bytes=0, threshold_bytes=10 * 1024**3),
        remaining=[item for item in previous['remaining'] if not item.startswith('Latest compiled candidate')], piece_placement_report=previous['piece_placement_report'])
    assert value['storage']['payload_allocation_bytes'] <= value['storage']['payload_budget_bytes']
    save(output, value)
    index_path = PROJECT / 'evidence/save_menu/20261013_original_screen/current_progress.json'
    index = read(index_path)
    index.update(utc=value['utc'], status=value['status'], current_source_working_stage=str(STAGE),
        current_offline_stage=ref(output), current_prepared_runtime=value['current_prepared_runtime'],
        latest_source_matches_linked_candidate=True, prepared_runtime_matches_latest_source=True, full_engine_goal_complete=False,
        isolated_runtime_phase9_status='LATEST_PHASE8_HOST_AND_FIVE_PACKS_INTEGRATED_FILE_ONLY_NATIVE_PENDING')
    save(index_path, index)
    notes = (f"# 최신 빌드 격리 실행 묶음 연동 — 9단계\n\n2026-11-15. 최신 Host `{previous['current_host']['build_id']}`와 동일 SDK430을 새 `{overlay['run_id']}`에 파일 전용으로 연결했다. 엔진 소스 변경·재빌드·Host/GameCore/CLR/창/GPU/음향/실게임 실행0회, 기본 실행·등록·원본 설치/MODS/설정·사용자 저장 변경0이다.\n\n"
        f"위치: `{root}`. 이전99b3는 직전23c 조합으로,4c8f는 복구용으로,40a 사용자 저장은 그대로 보존한다. 최신 컴파일 후보·새 준비 묶음의 Host/SDK 및다섯팩SHA가 일치한다. 실제 게임·화면 수락은 보류다.\n\n"
        "기존 준비 helper5개의 정확한바이트핀·실행차단가드를 그대로 사용하고, 새래퍼에는명시phase8프로필/f351핀·새evidence root·build-ID부모폴더준비만적용했다. 기본 준비는1회에성공했고 새runtime도1개만만들었다. 전역Host선택과production tool소스는바꾸지않았다.\n\n"
        "완성된 기본이미지에만 SHA고정 overlay계획을단회적용했다. 원래request/bundle.manifest/Play본문은작은gzip에보존했다. 기본영수증은overlay이전이력이며 최종overlay/result.json·현재request·WorldAssets/assets.manifest.json이 현재기준이다.\n\n"
        "terrain-assets.bin은V2로연결하고 나머지4팩은WorldAssets에별도목록을둬 backend23payload+manifest1의allowlist를유지했다. 기존5팩130,465,485B/UI154/지원6개와준비자료·아이콘2개를하드링크로재사용했다. 공유팩/지원자료attrs32를바꾸거나본문쓰기/chmod하지않는다. DB2개57,501,696B와기존개별GR2/config6개는독립사본이다.\n\n"
        "Play에는묶음내4환경경로와고정manifest SHA를검사하는순수Python사전검사를앞에넣었다. 나머지원래Play본문은바이트그대로이고검사실패시중단한다. Resume의새게임전용/이전묶음저장차단도유지했다. 실행기자체는호출하지않았으며 사전검사CLI파서만실제실행해정상및잘못된핀/경로4개거부를확인했다.\n\n"
        "계약·자산·저장독립검증을통과했다. UI원본74·sidecar154·유닛/애니메이션·ownedfont15의봉인출처/실제읽기경로를대조했다. ownedfont는기존한국어복구입력이며설치본font와무조건동일하다는요구로바꾸지않았다. 글꼴의화면가독성과실제엔진표시는미검증이다.\n\n"
        f"새핵심고유실할당{storage['metrics']['new_core_payload_allocated_bytes']:,}B(약62.55MiB),64MiB한도여유{storage['metrics']['allocated_headroom_bytes']:,}B다. Hostcache/runtime동일ID는한번만계상했다. evidence/디렉터리/드라이버할당은이값에포함하지않으며프로젝트전체변화는current_work.json의최종storage를따른다. 새팩/원본DDS사본/전체프로젝트복제0이다.\n\n"
        "중복지원8개실할당8,212,480B를정리했고 V1지형cache의새별칭1개퇴역은payload회수0B로구분했다. 자산검토의미사용초기검토기2개29,568B도정리했으며작은실패요약과현재검토기·SHA증거는보존했다.\n\n"
        "원본캐시보기·압축·밉·실제해상도/배율·반사전체장면/카메라·원본하드웨어혼합·GPU색/깊이/ID/가림·실제UI/도시화면/입력·성능/VRAM·전체게임/저장/모드/멀티코어관문은남아있다. 조각배치는 **규칙 동등, 배치 동등은 미검증**이다.\n\n최종상태: `evidence/world_terrain_original/phase9/runtime_integration/current_work.json`.\n")
    (PROJECT / 'docs/RUNTIME_PHASE9_INTEGRATION.md').write_text(notes, encoding='utf8')
    path = PROJECT / 'docs/CLAUDE_HANDOFF.md'
    head, tail = path.read_text('utf8').split('\n', 1)
    entry = (f"## 최신8단계 빌드 격리 실행 묶음 연동 — 2026-11-15\n\n최신dbb01a1f4f50 Host/SDK430을 새 `{overlay['run_id']}`에 연결했다. 최신소스·컴파일본·준비묶음이일치한다. 5팩직접하드링크/UI154/지원8공유/4ENV/독립DB·새게임전용·사전검사와독립계약/자산/저장검증PASS다. 엔진소스변경·재빌드·Host/SDK/CLR/창/GPU/음향/게임실행·기본실행/등록변경0이다. 새핵심할당62.55MiB,5팩새복사0·중복지원7.83MiB회수,이전99b3/복구4c8f/40a사용자저장은보존했다. 실제화면/게임수락보류는유지한다. 상세는 `docs/RUNTIME_PHASE9_INTEGRATION.md`,최종상태는 `evidence/world_terrain_original/phase9/runtime_integration/current_work.json`이다.\n\n")
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
