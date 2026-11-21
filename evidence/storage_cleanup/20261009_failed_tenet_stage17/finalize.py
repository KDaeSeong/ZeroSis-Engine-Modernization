"""Record the completed bounded cleanup and current policy-tenet evidence."""
from datetime import datetime, timezone
import gzip
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
FRESH = '20261009T080148Z_94a71ea1588c'
RESTORE = '20261009T080652Z_ba55a6903d7e'
HOST = '20261009T074845Z_3b9099f7c315'
FAILED = '20261009T075113Z_315e609b50e6'
GIB = 1024 ** 3


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def ref(path):
    path = Path(path)
    return {'path': str(path), 'sha256': sha(path), 'bytes': path.stat().st_size}


def audit(name):
    rows = (HERE / name).read_text(encoding='utf-8-sig').splitlines()
    data, pointer = json.loads(rows[0]), json.loads(rows[1])
    full = read(pointer['report'])
    assert data['status'] == full['status'] == 'COMPLETE_METADATA_AUDIT'
    assert full['root'] == str(ROOT) and not full['errors'] and not full['skipped']
    assert data['unique_allocated_bytes'] == full['unique_allocated_bytes']
    return full, ref(pointer['report'])


assert not (HERE / 'summary.json').exists(), 'Final summary already exists'
before, before_ref = audit('before-audit.log')
after, after_ref = audit('after-audit.log')
plan, receipt, inventory = (read(HERE / name) for name in ('plan.json', 'cleanup.json', 'inventory.json'))
assert receipt['status'] == 'PASS_OBSOLETE_ARTIFACT_RETIREMENT' and not receipt['errors']
assert receipt['plan_sha256'] == sha(HERE / 'plan.json')
assert receipt['protected_hashes_verified_before'] and receipt['protected_hashes_verified_after']
assert plan['protected_files'] == 32273 and receipt['removed_files'] == plan['files'] == 6467
assert set(receipt['completed_directories']) == {
    str(Path('Build/InteractiveGameRuntime') / FAILED), str(Path('evidence/interactive_game') / FAILED)}
for name in receipt['completed_directories']:
    path = (ROOT / name).resolve()
    assert path.is_relative_to(ROOT) and not path.exists()
for item in inventory['preserved_compressed_evidence']:
    assert sha(item['path']) == item['sha256']
    assert hashlib.sha256(gzip.decompress(Path(item['path']).read_bytes())).hexdigest() == item['uncompressed_sha256']

compression_path = ROOT / 'evidence/storage/20261009T082043Z_aa19f3132927/compression.json'
compression = read(compression_path)
assert compression['status'] == 'PASS_RETAINED_CONTENT_COMPRESSION' and not compression['errors']
assert set(compression['requested_run_ids']) == {FRESH, RESTORE}
assert len(compression['completed']) == 831 and compression['deleted_files'] == 0
assert {row['run_id'] for row in compression['completed']} == {FRESH, RESTORE}
assert all(row['sha256'] == row['sha256_after'] for row in compression['completed'])
assert sha(compression['script']['path']) == compression['script']['sha256']
for row in compression['records']:
    for kind in ('result', 'request'):
        assert sha(row[kind]['path']) == row[kind]['sha256']

routes_path = HERE / 'post_cleanup_validation.json'
routes = read(routes_path)
assert routes['status'] == 'PASS_MANUAL_NEW_CONTINUE_AND_ALL_SAVED_BUNDLES'
assert routes['count'] == 10 and routes['user_saves'] == 8 and routes['saves_unchanged']
assert sha(ROOT / 'tools/Start-Engine.ps1') == routes['launcher_sha256']
for save in routes['saves']:
    assert Path(save['path']).stat().st_size == save['bytes'] and sha(save['path']) == save['sha256']

tidy_path = ROOT / 'evidence/build_tidy/20261009T080101Z_5fd387b35915/cleanup.json'
tidy = read(tidy_path)
assert tidy['status'] == 'UNREFERENCED_INTERMEDIATES_REMOVED_RETAINED_INPUTS_UNCHANGED'
assert len(tidy['removed']) == 5 and tidy['reference_documents_unchanged']
for row in tidy['retained']:
    assert sha(row['path']) == row['sha256']

runs = []
for run_id in (FRESH, RESTORE):
    folder = ROOT / 'evidence/interactive_game' / run_id
    result, validation = read(folder / 'result.json'), read(folder / 'policy_tenets_validation.json')
    assert result['status'].endswith('_PASS') and result['returncode'] == 0 and not result['timed_out']
    assert not result['failures'] and validation['status'] == 'PASS_INTERACTIVE_POLICY_TENETS_NATIVE_SDK_SMOKE'
    assert validation['result']['sha256'] == sha(folder / 'result.json') and validation['native_save_count'] == 2
    if run_id == RESTORE:
        assert validation['restore']['source_run_id'] == FRESH
        assert not validation['restore']['fixture_mutation_applied']
    runs.append({'run_id': run_id, 'result': ref(folder / 'result.json'),
                 'validation': ref(folder / 'policy_tenets_validation.json'),
                 'native_pid': result['pid'], 'driver_pid': result['driver_pid'],
                 'actions': validation['posted_actions'], 'native_policy_inputs': validation['native_policy_inputs'],
                 'native_save_count': validation['native_save_count'], 'adoptions': validation['adoptions'],
                 'restore': validation['restore']})
assert runs[0]['native_pid'] != runs[1]['native_pid'] and runs[0]['driver_pid'] != runs[1]['driver_pid']

baseline_path = ROOT / 'evidence/storage_cleanup/20261009_failed_policy_tenet_064236/summary.json'
baseline = read(baseline_path)['baseline_unique_allocated_bytes']
old, new = before['unique_allocated_bytes'], after['unique_allocated_bytes']
summary = {
    'status': 'PASS_BOUNDED_STORAGE_REDUCTION_AND_TENET_FRESH_RESTORE_RETENTION',
    'utc': datetime.now(timezone.utc).isoformat(), 'storage_measurement_utc': after['utc'],
    'before_unique_allocated_bytes': old, 'after_unique_allocated_bytes': new,
    'this_cleanup_reduction_bytes': old-new, 'this_cleanup_reduction_percent': 100*(old-new)/old,
    'baseline_unique_allocated_bytes': baseline, 'baseline_reference': ref(baseline_path),
    'cumulative_reduction_bytes': baseline-new, 'cumulative_reduction_percent': 100*(baseline-new)/baseline,
    'after_logical_path_bytes': after['logical_path_bytes'],
    'removed_failed_runtime_files': receipt['removed_files'], 'removed_failed_runtime_logical_bytes': receipt['removed_logical_bytes'],
    'removed_unreferenced_objects': len(tidy['removed']), 'removed_object_logical_bytes': tidy['removed_bytes'],
    'object_cleanup_precedes_before_audit': True,
    'deletion_protected_files': plan['protected_files'], 'deletion_before_after_hashes_equal': True,
    'compressed_files': len(compression['completed']), 'compression_stored_reduction_bytes': compression['stored_reduction'],
    'retained_diagnostic_archives': len(inventory['preserved_compressed_evidence']),
    'retained_diagnostic_archive_bytes': inventory['preserved_total_compressed_bytes'],
    'user_saves_verified': 8, 'manual_routes_verified': 10, 'manual_play_launched_by_route_check': False,
    'evidence': {'before_audit': before_ref, 'after_audit': after_ref, 'plan': ref(HERE / 'plan.json'),
                 'deletion': ref(HERE / 'cleanup.json'), 'inventory': ref(HERE / 'inventory.json'),
                 'compression': ref(compression_path), 'object_tidy': ref(tidy_path), 'manual_routes': ref(routes_path)},
    'tenet_host': ref(ROOT / 'evidence/ui_window_host' / HOST / 'build_result.json'), 'tenet_native_runs': runs,
    'scrollbar_default': ref(ROOT / 'evidence/social_policy_scene/20261009_original_scrollbar_default/result.json'),
    'scrollbar_component': ref(ROOT / 'evidence/social_policy_scene/20261009_auto_scroll_visibility/result.json'),
    'bounded_compression_tool': ref(ROOT / 'tools/compact_completed_runtime_evidence.py'),
    'engine_status': {'overall_estimate_percent': 30, 'manual_default_changed': False,
                     'normal_ideology_selection_verified': False, 'higher_level_tenets_verified': False,
                     'blocked_branch_switch_verified': False, 'ideology_change_verified': False,
                     'retail_pixel_equivalence_verified': False, 'full_gameplay_verified': False},
    'limits': ['Allocation deduplicates NTFS file IDs and reflects compression; MFT/directory overhead and volume free space are excluded.',
               'The initial 25.63GiB baseline and this before-cleanup audit differ; this audit includes the newly retained native proof pair.',
               'Fresh tenet prerequisites and one exact-cost culture grant are test fixtures, not proof of normal ideology eligibility.',
               'Game save section changed on reload; player sections match, but reload RNG equivalence remains unverified.',
               'Broad cold-artifact preview was rejected by automatic review; only the two explicit completed DB/DDS run sets were compressed.',
               'The bounded compression selector was added after deletion verification; the deletion map records the earlier tool revision.'],
}
(HERE / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2)+'\n', encoding='utf8')

marker = '<!-- current-tenet-cleanup-20261009-stage17 -->'
text = f'''{marker}
2026-10-09 이번 [정리 결과](../evidence/storage_cleanup/20261009_failed_tenet_stage17/summary.json)는 실제 파일 점유량 **{old/GIB:.2f}→{new/GIB:.2f}GiB**, **{(old-new)/GIB:.2f}GiB·{100*(old-new)/old:.2f}% 감소**랍니다. 새 검증 자료까지 포함한 값이며 최초 {baseline/GIB:.2f}GiB 대비 누적 {100*(baseline-new)/baseline:.2f}% 감소했사와요. 실패 시험본 6,467개와 불필요한 오브젝트 5개를 삭제하고, 새 게임·복원 두 시험본의 DB·텍스처 831개만 무손실 압축했답니다. 삭제 전후 보호 파일 32,273개와 압축 대상 전후 해시가 같으며 사용자 저장 8개·실행 경로 10건도 보존했사와요. 오브젝트 정리는 위 측정 전이며, 경로별 파일 크기 합계 {after['logical_path_bytes']/GIB:.2f}GiB에는 하드링크 중복과 압축 전 크기가 포함된답니다.

[새 게임 신조 검사](../evidence/interactive_game/{FRESH}/policy_tenets_validation.json)와 [별도 프로세스 복원 검사](../evidence/interactive_game/{RESTORE}/policy_tenets_validation.json)가 모두 통과했사와요. 시험 전제로 이념을 준비한 뒤 원본 선택·취소·확인 입력으로 1단계 신조를 무료 2회, 문화 25를 소비하여 1회 채택했답니다. 취소 시 상태 보존·닫기/재열기/Escape·정상 턴 진행과 각 저장 2회를 확인했고, 복원에서는 추가 시험 지급 없이 신조 정보와 플레이어 저장 구역이 일치했사와요. 최초 검사기의 닫기 상태·팝업 기본값 판정 오류는 수정했으며 실패 판정과 당시 진단은 위 압축 보존 목록에 남겼답니다.

원본 정책 탭의 이념 신조 제외 조건을 바로잡고, [원본 실행 파일의 스크롤 막대 기본 동작](../evidence/social_policy_scene/20261009_original_scrollbar_default/result.json)을 확인하여 내용이 넘치지 않는 패널의 막대를 숨기도록 연결했사와요. [표시 부품 검사](../evidence/social_policy_scene/20261009_auto_scroll_visibility/result.json)도 통과했답니다. **정상 이념 선택·2/3단계 신조·차단된 정책 계열 전환·이념 변경·원본 전체 화면 동등성과 정상 한 판 플레이는 미완료**랍니다. 수동 기본 실행본과 전체 추정 약 30%는 유지하며, 아래는 이전 단계의 검증 기록이와요.

'''
for name in ('ENGINE_COMPLETION_STATUS.md', 'CONTINUOUS_PLAY.md'):
    path = ROOT / 'docs' / name
    current = path.read_text(encoding='utf8')
    assert marker not in current, 'Current status already inserted'
    heading, separator, body = current.partition('\n')
    assert separator and heading.startswith('#')
    path.write_text(heading+'\n\n'+text+body.lstrip('\n'), encoding='utf8')
print(json.dumps({'status': summary['status'], 'before_gib': old/GIB, 'after_gib': new/GIB,
                  'reduced_gib': (old-new)/GIB, 'reduced_percent': summary['this_cleanup_reduction_percent'],
                  'cumulative_reduction_percent': summary['cumulative_reduction_percent'],
                  'logical_gib': after['logical_path_bytes']/GIB, 'summary': str(HERE / 'summary.json')}, ensure_ascii=False))
