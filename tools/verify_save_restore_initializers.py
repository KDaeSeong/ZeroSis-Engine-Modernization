#!/usr/bin/env python3
"""Compile focused stand-in fixtures from accepted SDK initializer bodies.

The fixture uses the exact method bodies from SDK_BNW_Original and derives the
candidate bodies only by applying the two named rows from save_restore_patches.json.
It is a component regression, not an SDK DLL or game-runtime test.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import uuid


ENGINE = Path(__file__).resolve().parents[1]
SDK = ENGINE / "Source" / "SDK_BNW_Original"
EXP2 = SDK / "CvGameCoreDLL_Expansion2"
SPEC = ENGINE / "Source" / "Porting" / "save_restore_patches.json"
TEMPLATE = ENGINE / "Tests" / "save_restore_initializer_regression.cpp"
DEFINES = SDK / "CvGameCoreDLLUtil" / "include" / "CvDLLUtilDefines.h"
MUNIT = EXP2 / "CvMilitaryAI.cpp"
CULTURE = EXP2 / "CvCultureClasses.cpp"
OPERATION = EXP2 / "CvAIOperation.cpp"
PATCH_MILITARY = "initialize_military_player_arrays_with_player_bound"
PATCH_CULTURE = "initialize_culture_public_opinion_before_first_save"
PATCH_OPERATION = "initialize_operation_reinforcement_flag_in_reset"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def extract_function(text: str, signature: str) -> str:
    start = text.find(signature)
    if start < 0:
        raise RuntimeError(f"function signature not found: {signature}")
    brace = text.find("{", start + len(signature))
    if brace < 0:
        raise RuntimeError(f"function body not found: {signature}")

    depth = 0
    state = "code"
    i = brace
    while i < len(text):
        ch = text[i]
        nxt = text[i + 1] if i + 1 < len(text) else ""
        if state == "line_comment":
            if ch in "\r\n":
                state = "code"
        elif state == "block_comment":
            if ch == "*" and nxt == "/":
                state = "code"
                i += 1
        elif state in ("string", "char"):
            if ch == "\\":
                i += 1
            elif (state == "string" and ch == '"') or (state == "char" and ch == "'"):
                state = "code"
        else:
            if ch == "/" and nxt == "/":
                state = "line_comment"
                i += 1
            elif ch == "/" and nxt == "*":
                state = "block_comment"
                i += 1
            elif ch == '"':
                state = "string"
            elif ch == "'":
                state = "char"
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return text[brace + 1 : i]
        i += 1
    raise RuntimeError(f"unterminated function body: {signature}")


def find_patch(rows: list[dict], patch_id: str) -> dict:
    matches = [row for row in rows if row.get("id") == patch_id]
    if len(matches) != 1:
        raise RuntimeError(f"expected one patch row {patch_id}, found {len(matches)}")
    return matches[0]


def make_candidate(body: str, patch: dict) -> str:
    old, new = patch["old"], patch["new"]
    if body.count(old) != patch.get("count", 1):
        raise RuntimeError(f"patch text count mismatch inside extracted {patch['id']} body")
    return body.replace(old, new)


def macro_value(text: str, name: str) -> int:
    match = re.search(rf"^\s*#define\s+{re.escape(name)}\s+\((\d+)\)", text, re.MULTILINE)
    if not match:
        raise RuntimeError(f"could not resolve {name} from accepted SDK utility defines")
    return int(match.group(1))


def sha_map(paths: list[Path]) -> dict[str, str]:
    return {str(path): sha256(path) for path in paths}


def get_msvc() -> tuple[Path, Path]:
    roots = [
        Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"))
        / "Microsoft Visual Studio" / "Installer" / "vswhere.exe",
    ]
    vswhere = next((path for path in roots if path.is_file()), None)
    if vswhere is None:
        raise RuntimeError("Visual Studio vswhere.exe was not found")
    result = subprocess.run(
        [str(vswhere), "-latest", "-products", "*", "-property", "installationPath"],
        text=True,
        capture_output=True,
        check=True,
    )
    install = Path(result.stdout.strip())
    tools = install / "VC" / "Tools" / "MSVC"
    versions = sorted((path for path in tools.iterdir() if path.is_dir()), reverse=True)
    for version in versions:
        compiler = version / "bin" / "Hostx64" / "x64" / "cl.exe"
        vcvars = install / "VC" / "Auxiliary" / "Build" / "vcvars64.bat"
        if compiler.is_file() and vcvars.is_file():
            return compiler, vcvars
    raise RuntimeError(f"x64 MSVC compiler/vcvars64 not found under {install}")


def run() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-root", type=Path, default=ENGINE / "evidence" / "component_tests" / "save_restore_initializers")
    args = parser.parse_args()

    required = [SPEC, TEMPLATE, DEFINES, MUNIT, CULTURE, OPERATION, Path(__file__).resolve()]
    for path in required:
        if not path.is_file():
            raise RuntimeError(f"required frozen input missing: {path}")

    # Firaxis SDK source files use Windows-1252 (for copyright notices); the
    # extracted method bodies are kept otherwise byte-faithful and only used
    # in this local fixture.
    source_military = MUNIT.read_bytes().decode("cp1252")
    source_culture = CULTURE.read_bytes().decode("cp1252")
    source_operation = OPERATION.read_bytes().decode("cp1252")
    defines_text = DEFINES.read_bytes().decode("cp1252")
    spec = json.loads(SPEC.read_text(encoding="utf-8-sig"))
    rows = spec.get("patches", spec.get("rows", []))
    military_patch = find_patch(rows, PATCH_MILITARY)
    culture_patch = find_patch(rows, PATCH_CULTURE)
    operation_patch = find_patch(rows, PATCH_OPERATION)

    if sha256(MUNIT) != military_patch["source_sha256"]:
        raise RuntimeError("accepted CvMilitaryAI.cpp hash does not match the patch evidence")
    if sha256(CULTURE) != culture_patch["source_sha256"]:
        raise RuntimeError("accepted CvCultureClasses.cpp hash does not match the patch evidence")
    if sha256(OPERATION) != operation_patch["source_sha256"]:
        raise RuntimeError("accepted CvAIOperation.cpp hash does not match the patch evidence")

    military_original = extract_function(source_military, "void CvMilitaryAI::Reset()")
    culture_original = extract_function(source_culture, "void CvPlayerCulture::Init(CvPlayer* pPlayer)")
    military_candidate = make_candidate(military_original, military_patch)
    culture_candidate = make_candidate(culture_original, culture_patch)
    operation_original = extract_function(source_operation, "void CvAIOperation::Reset()")
    operation_candidate = make_candidate(operation_original, operation_patch)
    derived_city_attack_init = extract_function(source_operation, "void CvAIOperationBasicCityAttack::Init(")
    if "Reset();" not in derived_city_attack_init or "CvAIOperation::Init(" in derived_city_attack_init:
        raise RuntimeError("BasicCityAttack::Init no longer demonstrates the virtual Reset-only path")
    max_civ_players = macro_value(defines_text, "MAX_CIV_PLAYERS")
    max_major_civs = macro_value(defines_text, "MAX_MAJOR_CIVS")
    if max_civ_players != 63 or max_major_civs != 22:
        raise RuntimeError(f"unexpected accepted SDK constants: players={max_civ_players}, majors={max_major_civs}")

    frozen_paths = required + [DEFINES]
    before_hashes = sha_map(frozen_paths)
    run_id = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "_" + uuid.uuid4().hex[:8]
    outdir = args.output_root / run_id
    outdir.mkdir(parents=True, exist_ok=False)
    generated = TEMPLATE.read_text(encoding="utf-8-sig")
    replacements = {
        "@@MAX_CIV_PLAYERS@@": str(max_civ_players),
        "@@MAX_MAJOR_CIVS@@": str(max_major_civs),
        "@@MILITARY_RESET_BODY@@": military_original.replace("\r\n", "\n"),
        "@@MILITARY_RESET_CANDIDATE_BODY@@": military_candidate.replace("\r\n", "\n"),
        "@@CULTURE_INIT_BODY@@": culture_original.replace("\r\n", "\n"),
        "@@CULTURE_INIT_CANDIDATE_BODY@@": culture_candidate.replace("\r\n", "\n"),
        "@@OPERATION_RESET_BODY@@": operation_original.replace("\r\n", "\n"),
        "@@OPERATION_RESET_CANDIDATE_BODY@@": operation_candidate.replace("\r\n", "\n"),
    }
    for marker, value in replacements.items():
        if generated.count(marker) != 1:
            raise RuntimeError(f"fixture marker must occur exactly once: {marker}")
        generated = generated.replace(marker, value)
    if "@@" in generated:
        raise RuntimeError("unexpanded fixture marker remains")

    fixture = outdir / "save_restore_initializer_fixture.cpp"
    fixture.write_text(generated, encoding="utf-8", newline="\n")
    exe = outdir / "save_restore_initializer_fixture.exe"
    compiler, vcvars = get_msvc()
    object_file = outdir / "save_restore_initializer_fixture.obj"
    started_utc = utc_now()
    compile_command = (
        f'call "{vcvars}" >nul && "{compiler}" /nologo /std:c++14 /EHsc /W4 /WX /utf-8 '
        f'/Fo:"{object_file}" "{fixture}" /Fe:"{exe}"'
    )
    compile_script = outdir / "compile.cmd"
    compile_script.write_text("@echo off\r\n" + compile_command + "\r\n", encoding="utf-8")
    compile_result = subprocess.run(
        ["cmd.exe", "/d", "/c", compile_script.name],
        cwd=outdir,
        text=True,
        capture_output=True,
    )
    (outdir / "compile.log").write_text(
        compile_result.stdout + compile_result.stderr, encoding="utf-8", newline="\n"
    )
    if compile_result.returncode != 0:
        raise RuntimeError(f"MSVC compile failed with exit code {compile_result.returncode}; see {outdir / 'compile.log'}")

    test_result = subprocess.run([str(exe)], text=True, capture_output=True)
    (outdir / "test.log").write_text(
        test_result.stdout + test_result.stderr, encoding="utf-8", newline="\n"
    )
    after_hashes = sha_map(frozen_paths)
    if before_hashes != after_hashes:
        raise RuntimeError("a frozen input changed during compilation or execution")

    record = {
        "run_id": run_id,
        "started_utc": started_utc,
        "result": "pass" if test_result.returncode == 0 else "fail",
        "scope": "isolated component fixture using extracted method bodies; not full SDK DLL or Civ V runtime proof",
        "patch_ids": [PATCH_MILITARY, PATCH_CULTURE, PATCH_OPERATION],
        "operation_reset_poisoned_flag_values": {"original": True, "candidate": False},
        "derived_init_evidence": {"function": "CvAIOperationBasicCityAttack::Init", "calls_reset": True, "calls_base_init": False},
        "strategy_counts": [25, 63, 64, 80],
        "sdk_constants": {"MAX_CIV_PLAYERS": max_civ_players, "MAX_MAJOR_CIVS": max_major_civs},
        "inputs_sha256_before": before_hashes,
        "inputs_sha256_after": after_hashes,
        "fixture_sha256": sha256(fixture),
        "compiler": str(compiler),
        "compiler_sha256": sha256(compiler),
        "compiler_exit_code": compile_result.returncode,
        "object_file": str(object_file),
        "object_file_sha256": sha256(object_file),
        "binary": str(exe),
        "binary_sha256": sha256(exe),
        "test_exit_code": test_result.returncode,
        "compile_script_sha256": sha256(compile_script),
        "compile_log_sha256": sha256(outdir / "compile.log"),
        "test_log_sha256": sha256(outdir / "test.log"),
        "outputs": {
            "fixture": str(fixture),
            "compile_script": str(compile_script),
            "compile_log": str(outdir / "compile.log"),
            "test_log": str(outdir / "test.log"),
        },
    }
    record["finished_utc"] = utc_now()
    (outdir / "record.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"result": record["result"], "record": str(outdir / "record.json"), "outdir": str(outdir)}, indent=2))
    if test_result.returncode != 0:
        print(test_result.stdout, file=sys.stderr)
        print(test_result.stderr, file=sys.stderr)
    return test_result.returncode


if __name__ == "__main__":
    try:
        raise SystemExit(run())
    except Exception as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        raise SystemExit(1)
