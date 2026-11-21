"""Promote one prepared manual runtime; preserve only changed release metadata."""
from pathlib import Path
import hashlib
import json
import os
from datetime import datetime, timezone

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
RUN = "20261012T121847Z_732a6d5f07ea"
OLD = "20261010T065253Z_25bd25e6bca5"
LAUNCHER = ROOT / "tools/Start-Engine.ps1"
RELEASE = ROOT / "Play/EarlyAccess/release.json"
GUIDE = ROOT / "docs/EARLY_ACCESS_KR.md"
DIRECT = ROOT / "바로 실행 안내.txt"


def sha(path):
    return hashlib.file_digest(path.open("rb"), "sha256").hexdigest()


def record(path):
    return {"path": path.relative_to(ROOT).as_posix(),
            "bytes": path.stat().st_size, "sha256": sha(path)}


def load(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def dump(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def main():
    validation = load(HERE / "runtime_validation.json")
    assert validation["status"] == "PASS", "Prepared runtime validation must pass first"
    baseline = load(HERE / "launcher_before.json")
    assert baseline["status"] == "PASS" and baseline["save_count"] == 12
    assert sha(LAUNCHER) == "6528061869a90cef937162e53684c611b2b2081f6c39a8e9f4072a359cc5a4d3"
    assert sha(RELEASE) == "c82209bdeec169ffdc363805782548934398faf3dec369c12c681a8cc6a31934"
    assert sha(GUIDE) == "fd8353b83b52734f53d794316ce6c8f98f3287244515e70033f7432d5257baa6"
    release = load(RELEASE)
    assert release["release"] == "0.5" and release["runtime_id"] == OLD
    launcher = LAUNCHER.read_text(encoding="utf-8-sig")
    old_prefix = "$earlyAccessRuntimeIds = @('" + OLD + "'"
    assert launcher.count(old_prefix) == 1 and RUN not in launcher
    launcher = launcher.replace(old_prefix, "$earlyAccessRuntimeIds = @('" + RUN + "', '" + OLD + "'", 1)

    guide = GUIDE.read_text(encoding="utf-8-sig")
    start = guide.index("## 시작하기")
    guide = (
        "# ZeroSis' 얼리 액세스 0.6\n\n"
        "2026-10-12 기준, 문명 5의 실제 게임 로직을 64비트로 실행하는 **로컬 초기 플레이용 프로토타입**이와요. "
        "이번 버전은 생산 선택창을 다시 열 때 원본 진행 표시와 화면 상태를 보존하도록 수정했답니다. "
        "기존의 첫 화면 자동 유닛 선택·원본 유닛 패널·도시 구매 후 복귀도 포함하와요.\n\n"
        "새 게임 자동 검증에서 **6턴 진행·저장 2회·정상 종료**를 확인했사와요. "
        "별도 프로세스에서 그 저장을 복원해 **12턴까지 진행·재저장·정상 종료·의미 상태 일치**도 확인했답니다. "
        "원래 복원 검사 결과는 알림 순서를 잘못 기대한 검증기 때문에 실패로 남아 있으며, "
        "보존된 원본 기록에 대한 별도 검증 통과를 함께 기록했사와요. "
        "이 결과가 일반 플레이 한 판 완주나 원본 전체 UI·기존 저장 호환성을 뜻하지는 않사와요.\n\n"
        + guide[start:]
    ).replace("0.5의 화면 변경", "0.6의 화면 변경")
    direct = DIRECT.read_text(encoding="utf-8-sig")
    assert "최신 UI 시험판 EA 0.5:" in direct
    direct = direct.replace("EA 0.5", "EA 0.6")
    direct = direct.replace(
        "첫 화면 자동 유닛 선택·원본 유닛 패널·오른쪽 중복 표시 정리·도시 건물 구매 후 화면 갱신 오류 수정.",
        "생산 선택창 재열기 시 원본 진행 표시·화면 상태 보존. 첫 화면 유닛 선택·원본 유닛 패널·도시 구매 복귀 포함.")
    direct = direct.replace(
        "새 게임 6턴·저장·종료 자동 검증 통과. 별도 복원은 기술 완성 알림의 자동검사 제약으로 끝까지 재저장 검증하지 못함.",
        "새 게임 6턴·저장·종료 통과. 보존된 별도 복원 기록은 12턴까지 진행·재저장·종료를 독립 검증. 일반 플레이 완주·원본 전체 UI는 미검증.")

    source = ROOT / "evidence/worker_production/20261011_production_retention"
    release.update(release="0.6", status="PREPARED_PRESERVED_NATIVE_PAIR_PASS_MANUAL_UNVERIFIED",
                   recorded_utc=datetime.now(timezone.utc).isoformat(), runtime_id=RUN,
                   runtime="Build/InteractiveGameRuntime/" + RUN,
                   host_sha256="fe0ba7df9fb9bd664cf7249b4bc85acb1c38486e12e7fadf8073aee50ddc30b8",
                   request=record(ROOT / "evidence/interactive_game" / RUN / "request.json"))
    release["baseline"] = {
        "host": record(ROOT / "evidence/ui_window_host/20261011T124501Z_5bf7bf678d40/build_result.json"),
        "fresh": record(ROOT / "evidence/interactive_game/20261011T124731Z_b821f4b6c26a/result.json"),
        "restore_original_failed": record(ROOT / "evidence/interactive_game/20261011T125838Z_2f697438e208/result.json"),
        "separate_preserved_pair": record(source / "policy_order/postvalidation_attempts/20261011T135936Z/result.json"),
        "production_change": record(source / "change.json"),
        "production_visual_review": record(source / "gpu_visual_review.json"),
    }
    release["validation"] = {
        "runtime_inputs": record(HERE / "runtime_validation.json"),
        "launcher_before": record(HERE / "launcher_before.json"),
        "fresh_native_pass": True, "original_restore_aggregate_pass": False,
        "separate_preserved_checkpoint_pair_pass": True,
        "native_original_results_reclassified": False,
        "manual_startup_observed": False, "manual_save_input_verified": False,
        "manual_close_verified": False, "manual_restore_verified": False,
        "human_gameplay_verified": False, "full_campaign_verified": False,
        "original_ui_equivalence_verified": False,
        "retail_save_compatibility_verified": False,
        "full_rng_equivalence_verified": False,
    }
    release["shipped"]["production_context_and_presentation_epoch_retained"] = True
    release["shipped"]["original_policy_notification_callback_order_verifier_corrected"] = True
    release["limits"] = [
        "Fixed new-game configuration.",
        "World and remaining right panel are prototype presentation; original UI equivalence incomplete.",
        "Original restore aggregate remains FAILED; independent preserved native pair passes its declared scope only.",
        "Manual native startup/save/load/close and human campaign play are not yet verified at this publication stage.",
        "Worker recommendation text still has some raw LINK markup.",
        "Only Warrior variants and sampled IdleA; other unit models and full movement/combat animation incomplete.",
        "Existing GameMenu child-screen limitations remain; menu regression was not rerun in this worker profile.",
        "Historical saves route to their original retained engine; use a new Early Access game for 0.6 UI.",
        "Custom zssave; retail Civ5Save, mods and multiplayer compatibility unverified.",
    ]
    history = ROOT / "Play/EarlyAccess/history/0.5"
    backups = HERE / "before"
    assert not history.exists() and not backups.exists() and not (HERE / "promotion.json").exists()
    backups.mkdir()
    history.mkdir()
    before = {str(path.relative_to(ROOT)): record(path) for path in (LAUNCHER, RELEASE, GUIDE, DIRECT)}
    originals = {path: path.read_bytes() for path in (LAUNCHER, RELEASE, GUIDE, DIRECT)}
    for path, data in originals.items():
        (backups / path.name).write_bytes(data)
    (history / "release.json").write_bytes(originals[RELEASE])
    (history / "EARLY_ACCESS_KR.md").write_bytes(originals[GUIDE])
    release["prior_release"] = record(history / "release.json")
    staged = {LAUNCHER: launcher.encode("utf-8"), GUIDE: guide.encode("utf-8"), DIRECT: direct.encode("utf-8")}
    for path, data in staged.items():
        assert sha(path) == before[str(path.relative_to(ROOT))]["sha256"]
        temporary = path.with_name(path.name + ".ea06.tmp")
        with temporary.open("xb") as output:
            output.write(data)
        os.replace(temporary, path)
    release["shared_launcher"] = record(LAUNCHER)
    release["guide"] = record(GUIDE)
    assert sha(RELEASE) == before[str(RELEASE.relative_to(ROOT))]["sha256"]
    temporary = RELEASE.with_name("release.json.ea06.tmp")
    with temporary.open("xb") as output:
        output.write(dump(release))
    os.replace(temporary, RELEASE)
    receipt = {"status": "EA06_PREPARED_PUBLISHED_MANUAL_UNVERIFIED", "runtime_id": RUN,
               "before": before, "after": {str(path.relative_to(ROOT)): record(path) for path in originals},
               "user_saves_written": False, "native_game_launched": False,
               "full_engine_goal_complete": False}
    (HERE / "promotion.json").write_bytes(dump(receipt))
    print(json.dumps({"status": receipt["status"], "runtime_id": RUN, "changed_files": len(originals)}))


if __name__ == "__main__":
    main()
