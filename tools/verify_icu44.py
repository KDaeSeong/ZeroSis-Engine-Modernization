"""Execute isolated ICU44 AMD64 number/case probes and compare original localization output."""
import argparse
import json
from pathlib import Path
import re
from collect_baseline import PROJECT, digest
from native_build import build_program, checked_run, environment_for, run
from build_icu44 import artifact, verify_source
from verify_localization_reference import artifacts


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--vs", type=Path, default=Path(r"C:\Program Files\Microsoft Visual Studio\2022\Community"))
    args = parser.parse_args()
    root, _, _ = verify_source()
    evidence = PROJECT / "evidence/icu44"
    build_path = evidence / "build_result.json"
    build = json.loads(build_path.read_text(encoding="utf-8"))
    if build["status"] != "ICU44_AMD64_STATIC_LIBRARIES_BUILT":
        raise RuntimeError("ICU build not complete")
    for item in artifacts(build):
        if digest(Path(item["path"])) != item["sha256"]:
            raise RuntimeError("ICU build input or output differs: " + item["path"])
    libraries = []
    for component in build["components"]:
        lib = component["library"]
        if digest(Path(lib["path"])) != lib["sha256"]:
            raise RuntimeError("ICU library changed")
        libraries.append(Path(lib["path"]))
    backend_path = PROJECT / "evidence/localization/icu_backend/build_result.json"
    backend = json.loads(backend_path.read_text(encoding="utf-8"))
    if backend["status"] != "SDK_LOCALIZATION_ICU_BACKEND_BUILT":
        raise RuntimeError("Localization ICU backend is not built")
    for item in artifacts(backend):
        if digest(Path(item["path"])) != item["sha256"]:
            raise RuntimeError("Localization ICU backend differs: " + item["path"])
    libraries.insert(0, Path(backend["library"]["path"]))
    source = PROJECT / "Tests/icu44_trace.cpp"
    out = PROJECT / "Build/ICU44/probe"
    exe = build_program(name="icu44_trace", architecture="x64", vs=args.vs, directory=out, evidence=evidence,
        source=source, includes=[root / "source/common", root / "source/i18n", PROJECT / "Source/Providers/Localization"],
        defines=["U_STATIC_IMPLEMENTATION", "U_HAVE_INTTYPES_H=1"], objects=libraries, runtime="/MD",
        extra_link=["advapi32.lib"])
    env, compiler = environment_for(args.vs, "x64", out)
    imports = checked_run([Path(compiler).with_name("dumpbin.exe"), "/imports", exe["path"]], cwd=out, env=env)
    import_log = evidence / "probe_imports.log"
    import_log.write_bytes(imports.stdout + imports.stderr)
    dependencies = re.findall(r"^[ \t]+([^\\:\r\n]+\.dll)[ \t]*\r?$", imports.stdout.decode("mbcs", errors="replace"), re.M | re.I)
    allowed = {"kernel32.dll", "advapi32.dll", "msvcp140.dll", "vcruntime140.dll", "vcruntime140_1.dll"}
    if not dependencies or any(name.lower() not in allowed and not name.lower().startswith("api-ms-win-crt-") for name in dependencies):
        raise RuntimeError("Unexpected ICU probe import: " + repr(dependencies))
    reference_build_path = PROJECT / "evidence/localization/reference/build_result.json"
    reference_build = json.loads(reference_build_path.read_text(encoding="utf-8"))
    observations_path = PROJECT / "evidence/localization/reference/observations.json"
    observations = json.loads(observations_path.read_text(encoding="utf-8"))
    if observations["status"] != "SDK_LOCALIZATION_ORIGINAL_TRACE_RECORDED":
        raise RuntimeError("Original localization observations are incomplete")
    for item in artifacts(observations):
        if digest(Path(item["path"])) != item["sha256"]:
            raise RuntimeError("Original localization observations differ: " + item["path"])
    for item in reference_build["sources"] + [reference_build["builder"], reference_build["executable"]]:
        if digest(Path(item["path"])) != item["sha256"]:
            raise RuntimeError("Localization reference needs rebuilding: " + item["path"])
    for pair in reference_build["original_inputs"]:
        for item in pair.values():
            if digest(Path(item["path"])) != item["sha256"]:
                raise RuntimeError("Localization reference input differs")
    data_record = next(item for item in reference_build["original_inputs"] if item["copy"]["path"].endswith("icudt44l.dat"))
    for which in ("source", "copy"):
        item = data_record[which]
        if digest(Path(item["path"])) != item["sha256"]:
            raise RuntimeError("Original ICU data differs")
    result = run([exe["path"], data_record["copy"]["path"]], cwd=out, env=env)
    log = evidence / "probe_run.log"
    log.write_bytes(result.stdout + result.stderr)
    output = result.stdout.decode("ascii").replace("\r\n", "\n")
    if result.returncode or result.stderr or not re.search(r"^PASS\|\d+$", output, re.M):
        raise RuntimeError("ICU probe did not pass; see " + str(log))
    map_path = Path(exe["map"])
    map_lines = map_path.read_text(encoding="utf-8", errors="replace").splitlines()
    production_proof = []
    for name in ("FormatNumeric", "TransformTextCase"):
        matches = [line for line in map_lines if re.search(r"\s\?" + re.escape(name) + r"@ZeroSisLocalization@@\S+\s", line)
                   and "localization_icu:SdkLocalizationIcu.obj" in line]
        if len(matches) != 1:
            raise RuntimeError("Actual Localization backend link provenance missing: " + name)
        production_proof += matches
    if "DYNAMIC_AND_UNICODE_BOUNDARIES|PASS\n" not in output:
        raise RuntimeError("Dynamic formatting and Unicode boundary checks missing")
    reference_path = PROJECT / "evidence/localization/reference/numbers.log"
    reference = reference_path.read_text(encoding="utf-8")
    expected = [(parts[1], parts[-1]) for line in reference.splitlines() if line.startswith("TEXT|") for parts in [line.split("|")]]
    actual = [(parts[1], parts[-1]) for line in output.splitlines() if line.startswith(("TEXT|integer|", "TEXT|float|")) for parts in [line.split("|")]]
    differences = [{"index": i, "expected": a, "actual": b} for i, (a, b) in enumerate(zip(expected, actual)) if a != b]
    if len(expected) != 22 or len(actual) != 22:
        raise RuntimeError("ICU number comparison is incomplete")
    corpus_path = PROJECT / "evidence/localization/reference/numeric_corpus.log"
    expected_corpus = [line for line in corpus_path.read_text(encoding="utf-8").splitlines() if line.startswith("NUMERIC|")]
    actual_corpus = [line for line in output.splitlines() if line.startswith("NUMERIC|")]
    if len(expected_corpus) != 1140 or len(actual_corpus) != 1140:
        raise RuntimeError("ICU numeric corpus comparison is incomplete")
    corpus_differences = [{"index": i, "expected": a, "actual": b} for i, (a, b) in enumerate(zip(expected_corpus, actual_corpus)) if a != b]
    differences += corpus_differences
    report = {"status": "ICU44_COMPONENT_NUMBER_DIFFERENCES" if differences else "ICU44_COMPONENT_NUMBER_CONFORMANCE_PASS",
        "build": artifact(build_path), "backend": artifact(backend_path), "probe_source": artifact(source), "numeric_cases": artifact(PROJECT / "Tests/localization_numeric_cases.h"), "executable": exe,
        "imports": {"log": artifact(import_log), "dependencies": dependencies}, "data": data_record,
        "map": artifact(map_path), "production_implementation_proof": production_proof,
        "reference": artifact(reference_path), "reference_build": artifact(reference_build_path), "observations": artifact(observations_path), "execution": artifact(log),
        "numeric_outputs_compared": len(expected), "numeric_corpus": artifact(corpus_path), "numeric_corpus_outputs_compared": len(expected_corpus), "differences": differences,
        "case_outputs": sum(line.startswith("TEXT|case|") for line in output.splitlines()),
        "unavailable_title_cases": sum(line.startswith("CASE|") and line.endswith("|U_MISSING_RESOURCE_ERROR") for line in output.splitlines()),
        "nonfinite_rule_based_rejections": int(re.search(r"^NONFINITE_RULE_REJECTED\|(\d+)", output, re.M)[1]),
        "concurrent_formatting_calls": int(re.search(r"^CONCURRENT_FORMATS\|(\d+)\|failures=0", output, re.M)[1]),
        "dynamic_and_unicode_boundaries": True,
        "assertions": int(re.search(r"^PASS\|(\d+)", output, re.M)[1]),
        "verifier": artifact(Path(__file__).resolve()), "game_launched": False, "gamecore_loaded": False,
        "scope": "Actual Localization numeric/case backend; SDK String/parser/dictionary and game runtime integration pending"}
    (evidence / "conformance.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "numeric_outputs": len(expected) + len(expected_corpus), "nonfinite_rejections": report["nonfinite_rule_based_rejections"], "concurrent_calls": report["concurrent_formatting_calls"], "differences": differences}))
    if differences:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
