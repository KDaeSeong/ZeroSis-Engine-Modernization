"""Seal the completed cleanup receipts and refresh current status documentation.

This script does not delete, compress, build, launch, or promote a runtime.
"""
import gzip
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
A = ROOT / 'evidence/storage_cleanup/20261009_failed_policy_driver_060253'
B = HERE
FRESH = '20261009T065612Z_717e525d9e22'
RESTORE = '20261009T070344Z_3ac99a0df5c9'
HOST = '20261009T063449Z_4cc92cfed9b4'


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def ref(path):
    path = Path(path)
    return {'path': str(path), 'sha256': sha(path), 'bytes': path.stat().st_size}


def write(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


receipts, archives, cleanup_refs = [], [], []
for folder in (A, B):
    receipt = read(folder / 'cleanup.json')
    plan = read(folder / 'plan.json')
    inventory = read(folder / 'inventory.json')
    assert receipt['status'] == 'PASS_OBSOLETE_ARTIFACT_RETIREMENT'
    assert receipt['errors'] == []
    assert receipt['plan_sha256'] == sha(folder / 'plan.json')
    assert receipt['protected_hashes_verified_before'] and receipt['protected_hashes_verified_after']
    for relative in receipt['completed_directories']:
        target = (ROOT / relative).resolve()
        assert target.is_relative_to(ROOT) and not target.exists(), str(target)
    for item in inventory['preserved_compressed_evidence']:
        assert sha(item['path']) == item['sha256']
        assert hashlib.sha256(gzip.decompress(Path(item['path']).read_bytes())).hexdigest() == item['uncompressed_sha256']
        archives.append(item)
    receipts.append(receipt)
    cleanup_refs.append({'plan': ref(folder / 'plan.json'), 'applied_receipt': ref(folder / 'cleanup.json'),
                         'inventory': ref(folder / 'inventory.json'), 'protected_files': plan['protected_files']})

compression_path = ROOT / 'evidence/storage/20261009T071619Z_a512b0855223/compression.json'
compression = read(compression_path)
assert compression['status'] == 'PASS_RETAINED_CONTENT_COMPRESSION' and not compression['errors']
assert len(compression['completed']) == 775
assert {r['run_id'] for r in compression['completed']} == {FRESH, RESTORE}
assert all(r['sha256'] == r['sha256_after'] for r in compression['completed'])
for record in compression['records']:
    for key in ('result', 'request'):
        assert sha(record[key]['path']) == record[key]['sha256']

runs = []
for run_id in (FRESH, RESTORE):
    folder = ROOT / 'evidence/interactive_game' / run_id
    result = read(folder / 'result.json')
    validation = read(folder / 'social_policy_validation.json')
    assert result['status'].endswith('_PASS') and result['returncode'] == 0
    assert not result['failures'] and not result['timed_out']
    assert validation['status'] == 'PASS_INTERACTIVE_SOCIAL_POLICY_NATIVE_SDK_SMOKE'
    assert validation['result']['sha256'] == sha(folder / 'result.json')
    assert validation['native_save_count'] == 2
    runs.append({'run_id': run_id, 'native_result': ref(folder / 'result.json'),
                 'independent_verifier': ref(folder / 'social_policy_validation.json'),
                 'native_pid': result['pid'], 'driver_pid': result['driver_pid'],
                 'posted_actions': validation['posted_actions'], 'native_policy_inputs': validation['native_policy_inputs'],
                 'native_save_count': validation['native_save_count'], 'restore': validation['restore']})
assert runs[0]['native_pid'] != runs[1]['native_pid'] and runs[0]['driver_pid'] != runs[1]['driver_pid']
assert runs[1]['restore']['source_run_id'] == FRESH
assert runs[1]['restore']['sdk_policy_inventory_exact'] and runs[1]['restore']['player_sections_byte_equal']
assert not runs[1]['restore']['fixture_mutation_applied']

source_hashes = {
    'Source/Host/UiScene.lua': 'd55066c73c993805502fb664bffa7104b5943603800d7d0ae7ae917a154957bd',
    'tools/interactive_ui_driver.py': '4ca2899536b21587198f32b40dc2d0774be5a625fbd729bf3f3962c70ffe85a3',
    'tools/render_ui_popup.py': 'cf04f0a4d49392e4bba74b82bb27fe6f3fa9955f0855308667079205979a987b',
    'tools/ui_pixel_scene.py': 'c85c2ebb1af3fcb8bc249a56953e97fe1833138ea40abfcd2b6959adde2d9528',
    'Tests/social_policy_renderer.py': '3397b347adb8c626fc51d2fcb309d902d7d0f46137bdcb6ef980c3b10572ba1f',
}
for relative, expected in source_hashes.items():
    assert sha(ROOT / relative) == expected, relative
assert sha(ROOT / 'Build/UiWindowHost' / HOST / 'final/ZeroSisHost_x64.exe') == '6588dc66da31914e10984e77b5a7726ba6046de810a7f8e198ac39a1a96baa4c'

routes_path = B / 'post_cleanup_validation.json'
routes = read(routes_path)
assert routes['status'] == 'PASS_MANUAL_NEW_CONTINUE_AND_ALL_SAVED_BUNDLES'
assert routes['count'] == 10 and routes['user_saves'] == 8 and routes['saves_unchanged']
assert sha(ROOT / 'tools/Start-Engine.ps1') == routes['launcher_sha256']
for saved in routes['saves']:
    assert sha(saved['path']) == saved['sha256']

audit_path = ROOT / 'evidence/storage/20261009T072102Z.json'
audit = read(audit_path)
assert audit['status'] == 'COMPLETE_METADATA_AUDIT' and not audit['errors'] and not audit['skipped']
baseline_path = ROOT / 'evidence/storage_cleanup/20261009_failed_policy_budget_054455/summary.json'
baseline = read(baseline_path)['baseline_unique_allocated_bytes']
current = audit['unique_allocated_bytes']
alpha_path = ROOT / 'evidence/social_policy_scene/20261009_policy_tenet_alpha/result.json'
alpha = read(alpha_path)
assert alpha['focused_suite']['tests_run'] == 21 and alpha['focused_suite']['exit_code'] == 0

retired_index = {
    'status': 'VERIFIED_RETIRED_DIAGNOSTIC_ARCHIVE_INDEX',
    'scope': 'Host12 and failed policy Fresh10/Fresh11/Fresh12 raw Build and evidence directories have been deleted.',
    'historical_reports_with_retired_input_references': [
        'evidence/storage_cleanup/20261009_failed_policy_budget_054455/summary.json',
        'evidence/social_policy_scene/20261009_policy_branch_eligibility/result.json',
        'evidence/social_policy_scene/20261009_policy_branch_eligibility/driver-result.json',
        'evidence/social_policy_scene/20261009_policy_branch_eligibility/manifest-roundtrip-result.json',
        'evidence/social_policy_scene/20261009_policy_branch_eligibility/scrollbar-review.json',
        'evidence/social_policy_scene/20261009_policy_tenet_alpha/result.json',
    ],
    'original_reports_preserved_as_historical': True,
    'gpu14_historical_observation_correction': 'Fresh10 GPU frame14 DOES show the policy popup; the prior missing-popup observation was incorrect. The exact frame14/frame17 pixels and correction report are archived below. This does not change the failed native verdict of Fresh10.',
    'archived_files': archives,
    'all_compressed_and_uncompressed_hashes_verified': True,
    'not_a_full_runtime_recovery_archive': True,
}
write(B / 'retired_reference_index.json', retired_index)

summary = {
    'status': 'PASS_STORAGE_REDUCTION_AND_POLICY_FRESH_RESTORE_RETENTION',
    'utc': datetime.now(timezone.utc).isoformat(),
    'storage_measurement_utc': audit['utc'],
    'baseline_unique_allocated_bytes': baseline,
    'after_unique_allocated_bytes': current,
    'after_logical_path_bytes': audit['logical_path_bytes'],
    'cumulative_reduction_bytes': baseline - current,
    'cumulative_reduction_percent': 100 * (baseline - current) / baseline,
    'this_followup_cleanup_directories': sum(len(r['completed_directories']) for r in receipts),
    'this_followup_cleanup_files': sum(r['removed_files'] for r in receipts),
    'this_followup_deleted_logical_bytes': sum(r['removed_logical_bytes'] for r in receipts),
    'latest_cleanup_protected_files': 18899,
    'protected_hashes_verified_before_and_after': True,
    'retained_diagnostics_files': len(archives),
    'retained_diagnostics_bytes': sum(a['compressed_bytes'] for a in archives),
    'ntfs_compressed_files': len(compression['completed']),
    'ntfs_compression_stored_reduction_bytes': compression['stored_reduction'],
    'manual_routes_verified': 10, 'user_saves_verified': 8,
    'cleanup_passes': cleanup_refs,
    'evidence': [ref(audit_path), ref(baseline_path), ref(compression_path), ref(routes_path),
                 ref(B / 'retired_reference_index.json'), ref(alpha_path),
                 ref(ROOT / 'evidence/social_policy_scene/20261009_policy_branch_eligibility/manifest-roundtrip-result.json')],
    'current_source_files': [ref(ROOT / relative) for relative in source_hashes],
    'policy_host': ref(ROOT / 'evidence/ui_window_host' / HOST / 'build_result.json'),
    'policy_native_runs': runs,
    'engine_status': {
        'manual_runtime_promoted': False,
        'full_engine_completion_claimed': False,
        'retail_pixel_equivalence_verified': False,
        'normal_full_game_human_play_verified': False,
        'game_reload_rng_equivalence_verified': False,
        'whole_engine_rough_progress_estimate_percent': 30,
        'remaining_policy_routes': validation['unverified_policy_routes'],
        'remaining_visual_issue': 'Lower four original policy ScrollBars exceed card/popup bounds; original clipping/default semantics remain unresolved.',
    },
    'limits': [
        'Current allocation includes the newly retained successful native policy fresh/restore pair, which was absent from the earlier 8.75 GiB measurement.',
        'Allocation is unique NTFS file data including compression and hardlinks; it is not volume free space and excludes directory/MFT overhead.',
        'Logical removed bytes are not reported as physical storage reclaimed.',
        'The storage audit precedes this small final report and documentation update.',
        'Preview inventory/plan states are intentionally unchanged; the applied cleanup receipts establish deletion completion.',
    ],
}
write(B / 'summary.json', summary)

intro = """2026-10-09 07:21 UTC [최종 정리 기록](../evidence/storage_cleanup/20261009_failed_policy_tenet_064236/summary.json)의 NTFS 고유 파일 점유량은 **25.63→9.49GiB**, 누적 **16.14GiB·62.98% 감소**랍니다. 이번 후속 정리로 대체된 정책 Host/실패 실행의 8개 폴더·6,335개 파일을 삭제하고, 성공 실행 두 묶음의 DB/DDS 775개를 내용 변경 없이 압축해 약 1.68GiB를 줄였사와요. 마지막 삭제 전후 보호 파일 18,899개의 SHA가 같고, [사용자 저장 8개·실행 연결 10건](../evidence/storage_cleanup/20261009_failed_policy_tenet_064236/post_cleanup_validation.json)을 확인했답니다. 필요한 진단 43개는 합계 약 1.99MiB gzip으로 보존했사와요. [실측](../evidence/storage/20261009T072102Z.json)의 경로별 논리 합계는 22.10GiB이며, 9.49GiB는 하드링크 중복과 NTFS 압축을 반영한 점유량이랍니다. 이전 8.75GiB 측정 뒤 새로 통과한 정책 새 게임·복원 자료가 추가되었으며 아래의 다른 용량은 각 당시 기록이와요.

정책의 최신 [Host `20261009T063449Z_4cc92cfed9b4`](../evidence/ui_window_host/20261009T063449Z_4cc92cfed9b4/build_result.json)에서 [새 게임](../evidence/interactive_game/20261009T065612Z_717e525d9e22/social_policy_validation.json)과 [별도 프로세스 복원](../evidence/interactive_game/20261009T070344Z_3ac99a0df5c9/social_policy_validation.json)이 모두 **네이티브 실행 및 독립 검사 PASS**랍니다. 새 게임은 원본 취소 시 상태 보존·분기 0 채택으로 자동 정책 6 추가·정책 7 채택·원본 정책/이념 탭·설정·닫기/복귀·정상 0→1턴과 저장 2회를 확인했사와요. 시험 전용 문화 지급 뒤 실제 SDK 비용 25·30을 각각 소비했으며 게임 밸런스는 바꾸지 않았답니다. 복원은 원본 저장의 SDK 정책 보유 정보와 플레이어 구역 일치·추가 시험 지급 없음·1→2턴·재저장 2회를 확인했사와요. 저장 133개 구역 중 Game 구역만 다르며 난수 동등성은 미검증으로 남겼답니다.

이번 수정은 원본 정책 탭의 순차 분기 목록과 도시 유무를 장면 메타데이터에 넣고, 소유·문화 부족·도시 없는 상태의 버튼 검증과 실제 manifest 저장 누락을 바로잡았사와요. 원본 두 개의 크기 0×0 AlphaAnim 라벨 감싸기는 정확한 속성을 확인하여 허용했으며 [집중 검사 21개·실제 SDK 장면 변환](../evidence/social_policy_scene/20261009_policy_tenet_alpha/result.json)과 [저장 manifest 재검증](../evidence/social_policy_scene/20261009_policy_branch_eligibility/manifest-roundtrip-result.json)을 통과했답니다. **차단된 정책 분기 전환·이념 신조 선택·이념 변경, 하단 ScrollBar 넘침, 원본 전체 픽셀 동등성과 정상 한 판 플레이는 남아 있사와요.** 수동 기본 실행본·교역로 통과 쌍과 전체 추정 약 30%는 유지하와요.

삭제된 Host12/Fresh10/Fresh11/Fresh12와 이전 부품 검사의 입력은 [원본 경로·SHA·압축 진단 매핑](../evidence/storage_cleanup/20261009_failed_policy_tenet_064236/retired_reference_index.json)으로 추적하와요. Fresh10의 첫 GPU 프레임 14에 정책창이 없다는 이전 판독은 오류였으며, 원본 픽셀과 정정 보고서를 함께 보존했답니다. 당시 실패 판정은 그대로이며 최신 통과 근거는 위 새 게임·복원 쌍이랍니다."""

for name in ('ENGINE_COMPLETION_STATUS.md', 'CONTINUOUS_PLAY.md'):
    path = ROOT / 'docs' / name
    old = path.read_text(encoding='utf-8-sig')
    paragraphs = old.split('\n\n')
    assert paragraphs[1].startswith('2026-10-09 06:14 UTC ')
    assert paragraphs[2].startswith('정책의 최신 시험은 ')
    updated = '\n\n'.join([paragraphs[0], intro] + paragraphs[3:])
    updated = updated.replace('개발 소스의 정책 추가 연결은 위 재빌드·실행 검증 대기 상태로 구분하와요.',
                              '정책 추가 연결은 문서 상단의 Host 063449 새 게임·복원 쌍에서 별도로 통과했사와요.')
    updated = updated.replace('**현재 상단창은 과학 버튼만 연결된 개발 후보랍니다.**',
                              '**아래 2026-10-08 구형 상단창 후보는 당시 과학 버튼만 연결했사와요.**')
    path.write_text(updated, encoding='utf-8')

print(json.dumps({'status': summary['status'], 'current_GiB': current / 2**30,
                  'reduced_GiB': (baseline-current) / 2**30, 'reduced_percent': summary['cumulative_reduction_percent'],
                  'removed_files': summary['this_followup_cleanup_files'], 'retained_diagnostics': len(archives),
                  'summary': str(B/'summary.json')}, ensure_ascii=False))
