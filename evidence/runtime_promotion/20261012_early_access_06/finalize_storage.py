"""Record completed retirement and refresh only the current status document reference."""
import argparse
import gzip
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
HOSTS = (
    "20261011T095830Z_0e393114a58d",
    "20261011T104734Z_8c80ee26b062",
    "20261011T112831Z_f6767cca6e60",
    "20261011T123601Z_25d4e2bf0bdb",
)
MARKER = "<!-- ea06-storage-retirement-20261012 -->"


def require(value, message):
    if not value:
        raise RuntimeError(message)


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def checked(path, parent):
    path = Path(path).resolve(strict=True)
    require(path.is_file() and path.is_relative_to(parent), "Unexpected evidence path: " + str(path))
    return path


def ref(path):
    data = path.read_bytes()
    return dict(path=path.relative_to(ROOT).as_posix(), bytes=len(data), sha256=hashlib.sha256(data).hexdigest())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cleanup", required=True)
    parser.add_argument("--after", required=True)
    parser.add_argument("--apply-receipt", required=True)
    args = parser.parse_args()
    cleanup_path = checked(args.cleanup, ROOT / "evidence/storage_cleanup")
    plan_path = checked(cleanup_path.parent / "plan.json", ROOT / "evidence/storage_cleanup")
    after_path = checked(args.after, ROOT / "evidence/storage")
    receipt_path = checked(args.apply_receipt, ROOT / "evidence/storage_cleanup")
    before_path = ROOT / "evidence/storage/20261012T130335Z.json"
    cleanup, plan, receipt = map(read_json, (cleanup_path, plan_path, receipt_path))
    before, after = map(read_json, (before_path, after_path))
    require(cleanup["status"] == "PASS_OBSOLETE_ARTIFACT_RETIREMENT" and not cleanup["errors"] and
            cleanup["protected_hashes_verified_before"] and cleanup["protected_hashes_verified_after"],
            "Base retirement did not preserve protected content")
    require(receipt["status"] == "GUARDED_WRAPPER_COMPLETED" and receipt["exit_code"] == 0 and
            receipt["plan_sha256"] == ref(plan_path)["sha256"] == cleanup["plan_sha256"],
            "Wrapper completion receipt does not identify this plan")
    require(list(HOSTS) == plan["selected_host_ids"] and plan["outside_deletion_or_compression"] is False,
            "Different retirement scope")
    expected_dirs = {f"{group}/{host}" for group in ("Build/UiWindowHost", "evidence/ui_window_host") for host in HOSTS}
    actual_dirs = {row["path"].replace("\\", "/") for row in plan["directories"]}
    completed_dirs = {name.replace("\\", "/") for name in cleanup["completed_directories"]}
    require(expected_dirs == actual_dirs == completed_dirs and all(not (ROOT / name).exists() for name in expected_dirs),
            "Retirement directories are incomplete")
    require(cleanup["removed_files"] == plan["files"], "Retirement count differs")
    source_paths = [cleanup_path.parent / ("source_guard_" + phase + ".json") for phase in ("before", "after")]
    source_guards = [read_json(path) for path in source_paths]
    require(all(row["status"] == "CURRENT_HOST_64_SOURCE_CONTENT_AND_METADATA_PASS" and
                row["plan_sha256"] == ref(plan_path)["sha256"] and row["source_count"] == 64 and
                row["lua_source_count"] == 10 for row in source_guards) and
            source_guards[0]["sources"] == source_guards[1]["sources"] and
            source_guards[0]["lua_sources"] == source_guards[1]["lua_sources"], "Original source guards differ")
    for audit in (before, after):
        require(audit["status"] == "COMPLETE_METADATA_AUDIT" and audit["root"] == str(ROOT) and
                not audit["errors"] and not audit["skipped"], "Storage audit is incomplete")
    before_bytes, after_bytes = (audit["unique_allocated_bytes"] for audit in (before, after))
    require(before_bytes > after_bytes, "Fresh storage audit did not decrease")
    with gzip.open(plan["protected"]["path"], "rt", encoding="utf-8") as stream:
        protected_count = len(json.load(stream))

    doc_path = ROOT / "docs/ENGINE_COMPLETION_STATUS.md"
    publication_path = HERE / "publication.json"
    original_doc = doc_path.read_bytes()
    original_publication = publication_path.read_bytes()
    document = original_doc.decode("utf-8-sig")
    publication = json.loads(original_publication.decode("utf-8-sig"))
    require(MARKER not in document and publication["full_engine_goal_complete"] is False and
            publication["human_play_verified"] is False, "Unexpected status or repeated finalization")
    result_path = HERE / "storage_finalization.json"
    require(not result_path.exists(), "Refuse to replace storage finalization evidence")
    backup = HERE / "before_storage"
    require(not backup.exists(), "Refuse to replace the previous metadata backup")
    backup.mkdir()
    (backup / "ENGINE_COMPLETION_STATUS.md").write_bytes(original_doc)
    (backup / "publication.json").write_bytes(original_publication)
    gib = 1024 ** 3
    cleanup_link = cleanup_path.relative_to(ROOT).as_posix()
    after_link = after_path.relative_to(ROOT).as_posix()
    section = (
        f"{MARKER}\n"
        f"이번 구형 호스트 정리의 [전후 기록](../{cleanup_link})에서는 Build·검증 폴더 8개의 "
        f"{cleanup['removed_files']:,}개 파일을 제거했사와요. 보호 파일 {protected_count:,}개와 수동 실행 저장 "
        f"{len(plan['actual_user_saves'])}개의 내용·식별자·메타데이터를 보존했으며, 프로젝트 밖 Python 실행 도구는 "
        "읽기 전용으로 전후 검사했답니다. 현재 Host의 C++ 입력 64개와 Lua 소스 10개도 별도 대조로 보존했사와요. "
        "현재 실행본·사용자 저장·원본 게임 자료는 정리 대상에 포함하지 않았사와요.\n\n"
        f"[정리 전 감사](../evidence/storage/20261012T130335Z.json)와 [정리 후 감사](../{after_link})의 고유 파일 점유량은 "
        f"**{before_bytes / gib:.2f}→{after_bytes / gib:.2f}GiB**, 순감소 **{(before_bytes - after_bytes) / gib:.2f}GiB**랍니다. "
        f"정리 후 경로별 논리 합계는 {after['logical_path_bytes'] / gib:.2f}GiB이며 하드링크 중복과 압축 전 크기를 포함하와요. "
        "두 감사의 오류·건너뜀은 0개이며, 이 파일 점유량 차이를 볼륨 여유 공간 증가량으로 바꾸어 설명하지 않사와요. "
        "[현재 참조 갱신 기록](../evidence/runtime_promotion/20261012_early_access_06/storage_finalization.json)에서 경로·크기·해시를 추적하와요.\n\n"
        "다음 UI 복원 범위는 원본 `SaveMenu`의 저장 목록·이름 입력·저장·취소랍니다. 실제 문자 입력과 자식 화면의 입력 수명, "
        "세션 내부의 이름 있는 원자적 저장을 연결해야 하와요. 원본 문명 5 저장과의 호환성·삭제·덮어쓰기·클라우드·지도 저장은 "
        "별도 관문으로 남아 있답니다. 전체 진척도는 약 30%의 거친 추정으로 유지하와요.\n\n"
    )
    anchor = "<!-- natural-worker-production-boundary-20261012 -->"
    require(document.count(anchor) == 1, "Current status anchor differs")
    section = section.replace("\n", "\r\n") if "\r\n" in document else section
    document = document.replace(anchor, section + anchor, 1)
    document = document.replace("[최종 고유 파일 점유량](../evidence/storage/20261012T111800Z.json)",
                                "[앞선 검증 단계의 고유 파일 점유량](../evidence/storage/20261012T111800Z.json)", 1)
    doc_path.write_bytes(document.encode("utf-8"))
    publication["completion_status"] = ref(doc_path)
    publication["publication_before_storage"] = ref(backup / "publication.json")
    publication["storage_retirement"] = dict(cleanup=ref(cleanup_path), plan=ref(plan_path),
        wrapper_completion=ref(receipt_path), before_audit=ref(before_path), after_audit=ref(after_path),
        current_source_guards=[ref(path) for path in source_paths],
        before_unique_allocated_bytes=before_bytes, after_unique_allocated_bytes=after_bytes,
        unique_allocated_bytes_decrease=before_bytes - after_bytes, protected_files=protected_count,
        protected_manual_saves=len(plan["actual_user_saves"]), outside_mutation=False)
    publication_path.write_text(json.dumps(publication, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    result = dict(status="EA06_STORAGE_RETIREMENT_AND_CURRENT_REFS_PASS", recorded_utc=datetime.now(timezone.utc).isoformat(),
        publication=ref(publication_path), completion_status=ref(doc_path), metadata_backups=[ref(backup / name) for name in
        ("publication.json", "ENGINE_COMPLETION_STATUS.md")], storage_retirement=publication["storage_retirement"],
        human_play_verified=False, full_engine_goal_complete=False, overall_progress="approximately 30 percent; rough estimate")
    result_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(dict(status=result["status"], report=str(result_path),
                         before_gib=round(before_bytes / gib, 3), after_gib=round(after_bytes / gib, 3)), ensure_ascii=False))


if __name__ == "__main__":
    main()
