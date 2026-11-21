"""Stage reviewed language-formatting sources/libraries; never install game files."""
import json
from pathlib import Path
import shutil
from collect_baseline import PROJECT, digest
from localization_icu_evidence import validate


def main():
    icu, backend, result, counts = validate()
    target_root = PROJECT / "Stage/LocalizationICU"
    files = []
    inputs = list((PROJECT / "Source/ThirdParty/ICU44").rglob("*"))
    inputs += [Path(item["path"]) for item in backend["sources"]]
    inputs += [Path(backend["library"]["path"])] + [Path(component["library"]["path"]) for component in icu["components"]]
    inputs += [PROJECT / "Tests" / name for name in ("icu44_trace.cpp", "sdk_localization_trace.cpp", "localization_numeric_cases.h")]
    inputs += [PROJECT / "tools" / (name + ".py") for name in ("fetch_icu44_source", "build_icu44", "build_localization_icu",
        "build_localization_reference", "verify_localization_reference", "verify_icu44", "localization_icu_evidence", "stage_localization_icu")]
    inputs += [PROJECT / "docs/M2_LOCALIZATION_PROVIDER.md"]
    for directory in ("evidence/icu44", "evidence/localization/icu_backend", "evidence/localization/reference"):
        inputs += [path for path in (PROJECT / directory).iterdir() if path.is_file() and path.name != "raw_icu_comparison.json"]
    for source in sorted(set(inputs)):
        if not source.is_file():
            continue
        relative = source.relative_to(PROJECT)
        target = target_root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        expected = digest(source)
        shutil.copyfile(source, target)
        if digest(source) != expected or digest(target) != expected:
            raise RuntimeError("Localization ICU stage copy differs: " + str(source))
        files.append({"source": str(source), "path": str(target), "sha256": expected})
    report = {"status": "LOCALIZATION_ICU_COMPONENT_REVIEW_BUNDLE_READY", "counts": counts, "files": files,
              "numeric_backend_only": True, "gamecore_linked": False, "game_launched": False,
              "scope": "Source/build/review only; SDK String, parser, dictionary and game integration pending"}
    (target_root / "review_bundle.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "files": len(files), "numeric_matches": counts["numeric_matches"]}))


if __name__ == "__main__":
    main()
