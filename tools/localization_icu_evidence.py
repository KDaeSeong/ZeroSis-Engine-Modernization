"""Validate the recorded numeric/case implementation without executing a binary."""
from collections import Counter
import json
from pathlib import Path
import re
from collect_baseline import PROJECT, digest, pe_header, read_text
from build_icu44 import verify_source
from verify_localization_reference import artifacts


def validate():
    _, _, manifest = verify_source()
    read = lambda relative: json.loads((PROJECT / relative).read_text(encoding="utf-8"))
    icu = read("evidence/icu44/build_result.json")
    backend = read("evidence/localization/icu_backend/build_result.json")
    reference = read("evidence/localization/reference/build_result.json")
    observations = read("evidence/localization/reference/observations.json")
    defect = read("evidence/localization/reference/spellout_nan_failure.json")
    result = read("evidence/icu44/conformance.json")
    for item in artifacts([icu, backend, reference, observations, defect, result]):
        if digest(Path(item["path"])) != item["sha256"]:
            raise RuntimeError("Localization ICU evidence changed: " + item["path"])
    if (icu["status"] != "ICU44_AMD64_STATIC_LIBRARIES_BUILT" or not icu["original_files_unchanged"]
            or backend["status"] != "SDK_LOCALIZATION_ICU_BACKEND_BUILT" or backend["compiler_warnings"]
            or observations["status"] != "SDK_LOCALIZATION_ORIGINAL_TRACE_RECORDED"
            or reference["status"] != "SDK_LOCALIZATION_REFERENCE_BUILT"
            or result["status"] != "ICU44_COMPONENT_NUMBER_CONFORMANCE_PASS" or result["differences"]
            or any(item["game_launched"] or item["gamecore_loaded"] for item in (icu, backend, reference, observations, defect, result))):
        raise RuntimeError("Localization ICU status/scope differs")
    if [len(component["objects"]) for component in icu["components"]] != [151, 149, 1]:
        raise RuntimeError("ICU translation unit accounting differs")
    warning_total = 0
    for component in icu["components"]:
        warnings = Counter(re.findall(r"(?:warning|경고)\s+(C\d+)", read_text(Path(component["log"]["path"])), re.I))
        if dict(warnings) != component["warning_code_occurrences"] or component["returncode"]:
            raise RuntimeError("ICU compiler warning record differs")
        warning_total += sum(warnings.values())
    for item in [backend["object"]] + [obj for component in icu["components"] for obj in component["objects"]]:
        with Path(item["path"]).open("rb") as stream:
            if int.from_bytes(stream.read(2), "little") != 0x8664:
                raise RuntimeError("Localization ICU object is not AMD64")
    if pe_header(Path(result["executable"]["path"]))["architecture"] != "x64" or pe_header(Path(reference["executable"]["path"]))["architecture"] != "x86":
        raise RuntimeError("Localization probe architecture differs")
    for log in (Path(backend["log"]["path"]), Path(result["executable"]["log"])):
        if re.search(r"(?:warning|경고)\s+[A-Z]+\d+", read_text(log), re.I):
            raise RuntimeError("Localization implementation/probe emitted warnings")
    if digest(Path(result["executable"]["log"])) != result["executable"]["log_sha256"]:
        raise RuntimeError("Localization probe build log differs")
    linkmap = read_text(Path(result["map"]["path"]))
    if len(result["production_implementation_proof"]) != 2 or any(line not in linkmap or "localization_icu:SdkLocalizationIcu.obj" not in line
                                                                   for line in result["production_implementation_proof"]):
        raise RuntimeError("Localization backend link provenance differs")
    output = read_text(Path(result["execution"]["path"])).replace("\r\n", "\n")
    expected = [line for line in read_text(Path(result["numeric_corpus"]["path"])).splitlines() if line.startswith("NUMERIC|")]
    actual = [line for line in output.splitlines() if line.startswith("NUMERIC|")]
    extract = lambda text: [(parts[1], parts[-1]) for line in text.splitlines()
                            if line.startswith(("TEXT|integer|", "TEXT|float|")) for parts in [line.split("|")]]
    if expected != actual or len(actual) != result["numeric_corpus_outputs_compared"] or len(actual) != 1140:
        raise RuntimeError("Localization corpus equality differs")
    if extract(output) != extract(read_text(Path(result["reference"]["path"]))) or len(extract(output)) != result["numeric_outputs_compared"] or len(extract(output)) != 22:
        raise RuntimeError("Localization basic numeric equality differs")
    if (result["nonfinite_rule_based_rejections"] != 48 or "NONFINITE_RULE_REJECTED|48" not in output
            or result["concurrent_formatting_calls"] != 2048 or "CONCURRENT_FORMATS|2048|failures=0" not in output
            or not result["dynamic_and_unicode_boundaries"] or "DYNAMIC_AND_UNICODE_BOUNDARIES|PASS" not in output
            or result["case_outputs"] != 12 or result["unavailable_title_cases"] != 6
            or not re.search(r"(?m)^PASS\|" + str(result["assertions"]) + r"$", output)):
        raise RuntimeError("Localization boundary/concurrency accounting differs")
    if defect["exit_hex"] != "0xc00000fd" or defect["executable"] != observations["imports"][0]["binary"]:
        raise RuntimeError("Original NaN spellout failure provenance differs")
    if len(observations["executions"]) != 6 or any(row["exit_code"] for row in observations["executions"]):
        raise RuntimeError("Original successful observation count differs")
    return icu, backend, result, {"original_files": len(manifest), "icu_objects": 301, "third_party_warning_occurrences": warning_total,
                                  "numeric_matches": 1162, "known_original_defects": 1}


if __name__ == "__main__":
    print(json.dumps(validate()[3]))
