"""Record scoped native play/load proof without expanding full-game claims."""
from pathlib import Path
import hashlib
import json
from datetime import datetime, timezone
import runpy

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
RUN = "20261012T121847Z_732a6d5f07ea"


def load(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def record(path):
    return {"path": path.relative_to(ROOT).as_posix(), "bytes": path.stat().st_size, "sha256": sha(path)}


def dump(value):
    return json.dumps(value, ensure_ascii=False, indent=2) + "\n"


def main():
    probe = load(HERE / "manual_probe_result.json")
    strict = load(HERE / "runtime_validation_strict.json")
    before_native = load(HERE / "launcher_after.json")
    post_native = load(HERE / "launcher_post_probe.json")
    assert probe["status"] == "MANUAL_NATIVE_PROBE_PASS" and probe["run_id"] == RUN
    assert strict["status"] == "PASS" and strict["strict_ui_source_resolve"] is True
    assert before_native["status"] == post_native["status"] == "PASS"
    assert all(post_native["saves"].get(k) == v for k, v in before_native["saves"].items())
    assert all(post_native["plans"].get(k) == v for k, v in before_native["plans"].items())
    assert before_native["save_count"] == 12
    assert all(key.startswith("Build/InteractiveGameRuntime/" + RUN + "/sessions/")
               for key in set(post_native["saves"]) - set(before_native["saves"]))
    assert probe["restore"]["semantic_snapshot_equal"] is True
    assert probe["original_saves_after"]["unchanged"] is True
    native = runpy.run_path(str(HERE / "manual_probe.py"), run_name="release_close_guard")
    for launch in probe["launches"]:
        assert launch["status"] == "CLOSED" and launch["driver_result"]["returncode"] == 0
        assert native["find_owned_host"](int(launch["driver_pid"])) is None

    release_path = ROOT / "Play/EarlyAccess/release.json"
    guide_path = ROOT / "docs/EARLY_ACCESS_KR.md"
    direct_path = ROOT / "바로 실행 안내.txt"
    completion_path = ROOT / "docs/ENGINE_COMPLETION_STATUS.md"
    release = load(release_path)
    assert release["runtime_id"] == RUN and release["release"] == "0.6"
    assert release["status"] == "PREPARED_PRESERVED_NATIVE_PAIR_PASS_MANUAL_UNVERIFIED"
    backup = HERE / "before_finalize"
    assert not backup.exists() and not (HERE / "publication.json").exists()
    backup.mkdir()
    for path in (release_path, guide_path, direct_path, completion_path):
        (backup / path.name).write_bytes(path.read_bytes())

    guide = guide_path.read_text(encoding="utf-8")
    assert guide.count("## 시작하기") == 1
    note = (
        "일반 실행기의 **새 게임 시작·F5 저장·별도 프로세스 불러오기·정상 종료**도 확인했사와요. "
        "이번 확인은 0턴에서 자동 입력으로 수행했고, 복원 전후 SDK 상태 표본이 일치했답니다. "
        "직접 플레이한 한 판의 안정성은 아직 확인하지 않았사와요.\n\n"
    )
    guide_path.write_text(guide.replace("## 시작하기", note + "## 시작하기", 1), encoding="utf-8", newline="\n")
    direct = direct_path.read_text(encoding="utf-8")
    needle = "일반 플레이 완주·원본 전체 UI는 미검증."
    assert direct.count(needle) == 1
    direct_path.write_text(direct.replace(needle, needle + "\n일반 실행 0턴에서 F5 저장·별도 불러오기·정상 종료 및 SDK 상태 표본 일치 확인.", 1),
                           encoding="utf-8", newline="\n")

    release["status"] = "PUBLISHED_MANUAL_NATIVE_STARTUP_SAVE_LOAD_CLOSE_VERIFIED"
    release["recorded_utc"] = datetime.now(timezone.utc).isoformat()
    checks = release["validation"]
    checks.update(runtime_inputs=record(HERE / "runtime_validation_strict.json"),
                  launcher_after=record(HERE / "launcher_after.json"),
                  launcher_post_probe=record(HERE / "launcher_post_probe.json"),
                  manual_native=record(HERE / "manual_probe_result.json"),
                  manual_save_relocation=record(HERE / "manual_probe_relocation.json"),
                  first_manual_probe_failure=record(HERE / "attempts/first_log_lock_failure/manual_probe_result.json"),
                  first_manual_close=record(HERE / "first_probe_close.json"),
                  manual_startup_observed=True, manual_save_input_verified=True,
                  manual_close_verified=True, manual_restore_verified=True,
                  manual_native_scope="machine-posted owned-window F5 and close at turn 0; separate play-load process; SDK semantic snapshot sample equal",
                  original_user_save_count=12, original_user_saves_unchanged=True,
                  existing_28_routes_unchanged_after_native_probe=True,
                  owned_test_save_count=7, owned_test_saves_excluded_from_continue=True)
    assert checks["human_gameplay_verified"] is False and checks["full_campaign_verified"] is False
    release["limits"] = [
        "Ordinary native startup/F5/save-load/close is verified at turn 0 with machine-owned window input; human play and full campaign remain unverified."
        if limit.startswith("Manual native startup") else limit for limit in release["limits"]]
    release["guide"] = record(guide_path)
    release_path.write_text(dump(release), encoding="utf-8", newline="\n")

    text = completion_path.read_text(encoding="utf-8")
    assert "<!-- early-access-06-manual-native-20261012 -->" not in text
    text = text.replace(
        "EA 0.5 기본 실행기는 유지하며 이번 후보를 사용자용으로 승격하거나 수동 게임을 실행하지 않았답니다.",
        "이 생산 수정 후보는 이후 EA 0.6 새 게임에 연결했으며, 일반 실행의 저장·별도 불러오기·정상 종료도 아래 최신 승격 기록으로 확인했답니다.", 1)
    header = "# 전체 엔진 완료 조건과 현재 상태\n\n"
    assert text.startswith(header)
    current = (
        "<!-- early-access-06-manual-native-20261012 -->\n"
        "2026-10-12 [얼리 액세스 0.6](EARLY_ACCESS_KR.md)을 사용자용 새 게임에 연결했사와요. "
        "생산 선택창의 컨텍스트와 원본 화면 시간 기준 보존 수정이 포함됐답니다. "
        "전체 진척도는 여전히 **약 30%라는 거친 추정**이며 기능 목록을 실측한 완료율은 아니랍니다.\n\n"
        "| 이번 사용자용 반영 | 확인한 범위 |\n|---|---|\n"
        "| 실행 묶음 | [엄격한 입력 검사](../evidence/runtime_promotion/20261012_early_access_06/runtime_validation_strict.json) 통과. 새 빌드 없이 검증된 x64 Host와 동결 UI 지원을 재사용했사와요. |\n"
        "| 일반 실행·복원 | [실제 시험](../evidence/runtime_promotion/20261012_early_access_06/manual_probe_result.json) 통과. `--play`의 0턴에서 F5 저장·닫기, 별도 `--play-load`로 복원·닫기, 82,857바이트 SDK 상태 표본 일치를 확인했사와요. 사람이 한 판 플레이한 증거는 아니랍니다. |\n"
        "| 기존 저장·경로 | [승격 직후 검사](../evidence/runtime_promotion/20261012_early_access_06/launcher_after.json) 12개 저장·28건 계획 통과. [실행 후 검사](../evidence/runtime_promotion/20261012_early_access_06/launcher_post_probe.json)에서 기존 저장의 내용·식별자·수정 시각과 기존 28건 경로를 보존했고, 새 시험 저장 7개까지 총 19개·42건을 확인했사와요. |\n"
        "| 시험 실패 보존 | 첫 시험 도구는 실행 중 로그 잠금 때문에 실패했사와요. [실패 원문](../evidence/runtime_promotion/20261012_early_access_06/attempts/first_log_lock_failure/manual_probe_result.json)을 보존하고 도구를 수정했답니다. [첫 창의 별도 종료 기록](../evidence/runtime_promotion/20261012_early_access_06/first_probe_close.json)은 일반 실행 정상 종료만 확인하며 F5 성공으로 재분류하지 않사와요. |\n"
        "| 이어하기 | 새 시험의 직접 저장만 [시험용 이름](../evidence/runtime_promotion/20261012_early_access_06/manual_probe_relocation.json)으로 보존하여, 기존 사용자 저장으로 연결되는 이어하기를 유지했사와요. |\n\n"
        "원본 복원 검사 FAILED와 별도 보존 자료 pair PASS는 기존 범위로 유지하와요. "
        "전체 원본 UI·세계 표시·전투와 외교·장기 캠페인·멀티코어 턴 성능·기존 문명 5 저장과 모드 호환성은 아직 남아 있답니다.\n\n"
    )
    completion_path.write_text(header + current + text[len(header):], encoding="utf-8", newline="\n")
    receipt = {
        "status": "EA06_PUBLISHED_WITH_SCOPED_MANUAL_NATIVE_SAVE_LOAD_CLOSE_PASS",
        "runtime_id": RUN, "recorded_utc": release["recorded_utc"],
        "release": record(release_path), "guide": record(guide_path),
        "completion_status": record(completion_path),
        "manual_native": record(HERE / "manual_probe_result.json"),
        "strict_runtime_inputs": record(HERE / "runtime_validation_strict.json"),
        "original_user_saves_preserved": 12, "original_routes_preserved": 28,
        "owned_test_saves": 7, "human_play_verified": False, "full_engine_goal_complete": False,
    }
    (HERE / "publication.json").write_text(dump(receipt), encoding="utf-8", newline="\n")
    print(json.dumps({"status": receipt["status"], "runtime_id": RUN,
                      "user_saves_preserved": 12, "full_engine_goal_complete": False}))


if __name__ == "__main__":
    main()
