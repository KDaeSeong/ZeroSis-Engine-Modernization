"""Refresh existing project status documents from the completed cleanup receipt."""
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
summary = json.loads((HERE / 'summary.json').read_text(encoding='utf8'))
assert summary['status'] == 'PASS_TRADE_ROUTE_PAIR_RETIREMENT_AND_PRESERVATION'
size = summary['unique_ntfs_file_allocation']
gib = 1024 ** 3
paragraph = (
    '2026-10-09 [최신 정리 결과](../evidence/storage_cleanup/20261009_trade_route_pair_cleanup/summary.json)의 '
    f"NTFS 고유 파일 점유량은 **{size['initial_before_bytes']/gib:.2f}→{size['final_bytes']/gib:.2f}GiB**, "
    f"누적 **{size['total_reduction_bytes']/gib:.2f}GiB·{size['total_reduction_percent']:.2f}% 감소**랍니다. "
    '직전 9.06GiB 측정 이후 만든 별도 프로세스 복원 검증 자료까지 포함했사와요. '
    '구형 Host와 교역로 실행 두 묶음의 Build/evidence 여섯 폴더·11,555개 파일을 삭제하고, '
    '새 복원 DB/DDS 416개는 내용 변경 없이 압축했답니다. '
    '삭제 전후 보호 파일 80,355개의 SHA가 같으며 사용자 저장 8개·실행 경로 10건도 재확인했사와요. '
    f"경로별 파일 크기 합계는 {summary['logical_path_bytes']/gib:.2f}GiB이고, "
    '여기 보고한 점유량은 하드링크 중복과 NTFS 압축을 반영한 파일 데이터 크기랍니다.'
)
history = (
    '구형 교역로 Host `135705`와 실행 `140841`·`161612`의 원본 Build/evidence는 최신 '
    '새 게임·복원 쌍으로 대체하여 삭제했사와요. `140841`은 문명 아이콘 처리에서 실패했고, '
    '`161612`의 자체 PASS 표시는 실제 탭 입력을 재검사했을 때 인정되지 않았답니다. '
    '경로·크기·SHA는 [압축 삭제 목록]'
    '(../evidence/storage_cleanup/20261009_trade_route_pair_cleanup/recovery_01/retired-files.jsonl.gz)에, '
    '당시 결과는 [상태 기록](../evidence/storage_cleanup/20261009_trade_route_pair_cleanup/recovery_01/retired-statuses.json.gz)에 남겼사와요. '
    '현재 통과 근거는 위 `225105`·`233650` 쌍이며, 삭제된 구형 원본 링크를 현재 증거로 사용하지 않사와요.'
)
changes = []
for name in ('ENGINE_COMPLETION_STATUS.md', 'CONTINUOUS_PLAY.md', 'WORLD_TERRAIN.md'):
    path = ROOT / 'docs' / name
    text = path.read_text(encoding='utf-8-sig')
    parts = text.split('\n\n')
    assert parts[1].startswith('2026-10-09 [작업 후 최종 정리 결과]'), name
    parts[1] = paragraph
    for index, part in enumerate(parts):
        if part.startswith(('이전 교역로 개발 후보 ', '2026-10-09 교역로 개발 후보는 ')):
            parts[index] = history
        elif part.startswith('실패 지점은 [원본 snapshot `play-ui-51`]'):
            parts[index] = ''
    updated = '\n\n'.join(part for part in parts if part)
    path.write_text(updated, encoding='utf8')
    changes.append({'path': str(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()})
(HERE / 'documentation-update.json').write_text(json.dumps({'status': 'PASS_EXISTING_DOCUMENTS_UPDATED',
    'files': changes}, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
print(json.dumps({'status': 'PASS_EXISTING_DOCUMENTS_UPDATED', 'files': len(changes)}))
