"""Review current EA0.6 route semantics without changing historical receipts."""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]


def require(value, message):
    if not value:
        raise RuntimeError(message)


def load(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def ref(path):
    data = path.read_bytes()
    return dict(path=path.relative_to(ROOT).as_posix(), bytes=len(data),
                sha256=hashlib.sha256(data).hexdigest())


def check_ref(record):
    path = ROOT / record["path"]
    require(path.resolve().is_relative_to(ROOT), "Reference escaped the project")
    require(ref(path) == record, "Reference drifted: " + record["path"])


def main():
    report = HERE / "route_clarification_review.json"
    require(not report.exists(), "Refuse to replace an existing independent review")
    protected = [HERE / name for name in ("publication_review.json", "native_publication_review.json",
                  "storage_publication_review.json", "publication.json", "storage_finalization.json")]
    protected += [ROOT / "docs/ENGINE_COMPLETION_STATUS.md", ROOT / "Play/EarlyAccess/release.json"]
    before_hashes = [ref(path) for path in protected]
    publication = load(HERE / "publication.json")
    storage = load(HERE / "storage_finalization.json")
    require(ref(HERE / "publication.json")["sha256"] ==
            "86008c311bc331ea5779a6c760b4ab71e7bb5ac5d2a89db6422692bf18a44b81",
            "Current publication hash differs from the reviewed clarification")
    require(ref(ROOT / "docs/ENGINE_COMPLETION_STATUS.md")["sha256"] ==
            "1d2673852239cf2d7e3c71f66fe2c6cb23894596bff87680240b7aeb3c2773e3",
            "Current completion document hash differs")
    for key in ("release", "guide", "completion_status", "manual_native", "strict_runtime_inputs",
                "publication_before_route_clarification"):
        check_ref(publication[key])
    check_ref(storage["publication"])
    check_ref(storage["completion_status"])
    semantics = publication["route_preservation"]
    require(storage["route_clarification"]["semantics"] == semantics,
            "Current storage/publication route semantics differ")
    expected = dict(original_route_keys_preserved=28,
                    original_route_values_unchanged_at_promotion=27,
                    intentionally_changed_route="ea:New", new_runtime="20261012T121847Z_732a6d5f07ea",
                    original_route_values_unchanged_after_promotion=28,
                    continue_runtime="20261009T163702Z_0461db127034",
                    original_routes_preserved_field_means="retained route keys, not all unchanged pre-promotion values")
    require(all(semantics.get(key) == value for key, value in expected.items()),
            "Route annotation is ambiguous or changed")
    require(publication["original_routes_preserved"] == 28, "Original retained-key field changed")
    launcher_refs = semantics["launcher_evidence"]
    require([Path(row["path"]).name for row in launcher_refs] ==
            ["launcher_before.json", "launcher_after.json", "launcher_post_probe.json"],
            "Launcher evidence order changed")
    for row in launcher_refs:
        check_ref(row)
    before, promoted, post = [load(ROOT / row["path"]) for row in launcher_refs]
    require(all(row["status"] == "PASS" for row in (before, promoted, post)), "Launcher receipt is not PASS")
    original_keys = set(before["plans"])
    require(len(original_keys) == 28 and original_keys.issubset(promoted["plans"]) and
            original_keys.issubset(post["plans"]), "Original route key lost")
    changed = sorted(key for key in original_keys if before["plans"][key] != promoted["plans"][key])
    require(changed == ["ea:New"] and promoted["plans"]["ea:New"]["runtime"] == expected["new_runtime"],
            "An unexpected pre-promotion route value changed")
    require(all(promoted["plans"][key] == post["plans"][key] for key in original_keys),
            "A route changed after promotion")
    require(post["plans"]["ea:Continue"]["runtime"] == expected["continue_runtime"], "Continue runtime changed")
    require(len(before["saves"]) == len(promoted["saves"]) == 12 and
            all(promoted["saves"].get(key) == post["saves"].get(key) == value
                for key, value in before["saves"].items()), "Original save identity/content/time differs")
    require(len(post["saves"]) == post["save_count"] == 19 and
            len(post["plans"]) == post["plan_count"] == 42, "Post-probe inventory differs")
    require(len(set(post["saves"]) - set(before["saves"])) == publication["owned_test_saves"] == 7,
            "Owned test save count differs")
    for row in storage["route_clarification"]["metadata_backups"]:
        check_ref(row)
    require(len(storage["route_clarification"]["metadata_backups"]) == 3 and
            storage["route_clarification"]["historical_reviews_unchanged"] is True,
            "Clarification recovery evidence differs")
    require(all(publication[key] is False and storage[key] is False
                for key in ("human_play_verified", "full_engine_goal_complete")), "Unproved broad claim")
    document = (ROOT / "docs/ENGINE_COMPLETION_STATUS.md").read_text(encoding="utf-8-sig")
    require(all(text in document for text in ("경로 키 28개", "값 27개", "`ea:New`만 EA 0.6으로 교체",
                                              "기존 28개 경로 값은 모두 같았고")), "Document route wording differs")
    require([ref(path) for path in protected] == before_hashes, "Protected evidence changed during review")
    result = dict(status="PASS_CURRENT_EA06_ROUTE_CLARIFICATION_INDEPENDENT_REVIEW",
                  recorded_utc=datetime.now(timezone.utc).isoformat(),
                  reviewer_scope="Current immutable receipt hashes and route/save records; no game execution",
                  route_keys_preserved=28, unchanged_at_promotion=27, intentional_change="ea:New",
                  unchanged_after_promotion=28, original_save_records_preserved=12,
                  post_probe_saves=19, post_probe_plans=42, owned_test_saves=7,
                  current_refs_verified=True, metadata_backups_verified=3,
                  historical_reviews_preserved_during_this_review=True,
                  protected_refs=before_hashes, launcher_refs=launcher_refs,
                  human_play_verified=False, full_engine_goal_complete=False,
                  live_game_or_launcher_executed=False)
    report.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(dict(status=result["status"], route_keys=28, unchanged_at_promotion=27,
                          unchanged_after_promotion=28, report=ref(report))))


if __name__ == "__main__":
    main()
