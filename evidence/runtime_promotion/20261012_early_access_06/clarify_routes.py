"""Clarify the intentional EA New promotion without changing original receipts."""
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
    return dict(path=path.relative_to(ROOT).as_posix(), bytes=len(data), sha256=hashlib.sha256(data).hexdigest())


def main():
    doc_path = ROOT / "docs/ENGINE_COMPLETION_STATUS.md"
    pub_path = HERE / "publication.json"
    receipt_path = HERE / "storage_finalization.json"
    before_path, after_path, probe_path = [HERE / name for name in
        ("launcher_before.json", "launcher_after.json", "launcher_post_probe.json")]
    before, after, probe = [load(path) for path in (before_path, after_path, probe_path)]
    require(all(row["status"] == "PASS" for row in (before, after, probe)), "Launcher receipts are not PASS")
    old_keys = set(before["plans"])
    require(len(old_keys) == 28 and old_keys.issubset(after["plans"]) and old_keys.issubset(probe["plans"]),
            "Original plan keys were not retained")
    changed = sorted(key for key in old_keys if before["plans"][key] != after["plans"][key])
    require(changed == ["ea:New"] and after["plans"]["ea:New"]["runtime"] == "20261012T121847Z_732a6d5f07ea",
            "The intended EA New promotion differs")
    require(all(after["plans"][key] == probe["plans"][key] for key in old_keys), "Post-promotion routes changed")
    require(len(before["saves"]) == 12 and all(probe["saves"].get(key) == value for key, value in before["saves"].items()),
            "Original save receipts differ")
    require(probe["save_count"] == 19 and probe["plan_count"] == 42 and
            probe["plans"]["ea:Continue"]["runtime"] == "20261009T163702Z_0461db127034", "Post-probe scope differs")
    original_doc, original_pub, original_receipt = [path.read_bytes() for path in (doc_path, pub_path, receipt_path)]
    publication, receipt = load(pub_path), load(receipt_path)
    require(publication["completion_status"] == ref(doc_path) and receipt["publication"] == ref(pub_path) and
            receipt["completion_status"] == ref(doc_path), "Current references are stale")
    require(not publication["full_engine_goal_complete"] and not publication["human_play_verified"], "Unexpected broad claim")
    document = original_doc.decode("utf-8-sig")
    old = "에서 기존 저장의 내용·식별자·수정 시각과 기존 28건 경로를 보존했고, 새 시험 저장 7개까지 총 19개·42건을 확인했사와요."
    new = ("에서 기존 저장 12개의 내용·식별자·수정 시각을 보존했사와요. 승격 전 경로 키 28개는 모두 유지했고 값 27개는 같으며, "
           "`ea:New`만 EA 0.6으로 교체했답니다. 승격 직후부터 실행 후까지 기존 28개 경로 값은 모두 같았고, "
           "새 시험 저장 7개를 포함한 총 19개 저장·42건 계획을 확인했사와요.")
    require(document.count(old) == 1 and "route_preservation" not in publication, "Unexpected document or repeated clarification")
    backup = HERE / "before_route_clarification"
    require(not backup.exists(), "Refuse to replace previous metadata snapshots")
    backup.mkdir()
    for name, data in (("ENGINE_COMPLETION_STATUS.md", original_doc), ("publication.json", original_pub),
                       ("storage_finalization.json", original_receipt)):
        (backup / name).write_bytes(data)
    doc_path.write_bytes(document.replace(old, new, 1).encode("utf-8"))
    semantics = dict(original_route_keys_preserved=28, original_route_values_unchanged_at_promotion=27,
        intentionally_changed_route="ea:New", new_runtime="20261012T121847Z_732a6d5f07ea",
        original_route_values_unchanged_after_promotion=28,
        continue_runtime="20261009T163702Z_0461db127034",
        original_routes_preserved_field_means="retained route keys, not all unchanged pre-promotion values",
        launcher_evidence=[ref(path) for path in (before_path, after_path, probe_path)])
    publication["completion_status"] = ref(doc_path)
    publication["route_preservation"] = semantics
    publication["publication_before_route_clarification"] = ref(backup / "publication.json")
    pub_path.write_text(json.dumps(publication, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    receipt["publication"] = ref(pub_path)
    receipt["completion_status"] = ref(doc_path)
    receipt["route_clarification"] = dict(recorded_utc=datetime.now(timezone.utc).isoformat(), semantics=semantics,
        metadata_backups=[ref(backup / name) for name in ("ENGINE_COMPLETION_STATUS.md", "publication.json", "storage_finalization.json")],
        historical_reviews_unchanged=True)
    receipt_path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    require(load(pub_path)["completion_status"] == ref(doc_path) and load(receipt_path)["publication"] == ref(pub_path),
            "Refreshed current references differ")
    print(json.dumps(dict(status="EA06_ROUTE_CLARIFICATION_PASS", route_keys=28, unchanged_at_promotion=27,
        intended_change="ea:New", unchanged_after_promotion=28, publication=ref(pub_path), document=ref(doc_path)), ensure_ascii=False))


if __name__ == "__main__":
    main()
