"""Compile exact UiPopupContext timer/failure/stop bodies with fake GameCore adapters."""
from __future__ import annotations

import hashlib
import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path

from collect_baseline import PROJECT
from native_build import build_program, run
from probe_world_builder import artifact

VS = Path(r"C:\Program Files\Microsoft Visual Studio\2022\Community")
SOURCE = PROJECT / "Source/Host/UiPopupContext.h"
SCRIPT_SYSTEM = PROJECT / "Source/Host/ScriptSystem.h"
TEST = PROJECT / "Tests/ui_popup_failure.cpp"
TOOL = Path(__file__).resolve()


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def source_block(text: str, signature: str) -> str:
    start = text.find(signature)
    if start < 0:
        raise ValueError("missing source method: " + signature)
    opening = text.find("{", start)
    if opening < 0:
        raise ValueError("missing method body: " + signature)
    depth = 0
    state = "code"
    cursor = opening
    while cursor < len(text):
        char = text[cursor]
        nxt = text[cursor + 1] if cursor + 1 < len(text) else ""
        if state == "code":
            if char == "/" and nxt == "/":
                state = "line"
                cursor += 2
                continue
            if char == "/" and nxt == "*":
                state = "block"
                cursor += 2
                continue
            if char == '"':
                state = "string"
            elif char == "'":
                state = "char"
            elif char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    return text[start:cursor + 1]
        elif state == "line":
            if char == "\n":
                state = "code"
        elif state == "block":
            if char == "*" and nxt == "/":
                state = "code"
                cursor += 2
                continue
        elif state in ("string", "char"):
            if char == "\\":
                cursor += 2
                continue
            if (state == "string" and char == '"') or (state == "char" and char == "'"):
                state = "code"
        cursor += 1
    raise ValueError("unterminated source method: " + signature)


def main() -> int:
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "_" + uuid.uuid4().hex[:12]
    root = PROJECT / "evidence/ui_popup_failure" / run_id
    frozen_dir = root / "frozen_inputs"
    build_dir = PROJECT / "Build/UiPopupFailure" / run_id
    frozen_dir.mkdir(parents=True)
    build_dir.mkdir(parents=True)
    originals = {"ui_context": SOURCE, "script_system": SCRIPT_SYSTEM, "test_template": TEST, "verifier": TOOL}
    frozen = {key: path.read_bytes() for key, path in originals.items()}
    hashes = {key: sha(data) for key, data in frozen.items()}
    frozen_paths = {}
    for key, path in originals.items():
        target = frozen_dir / (key + path.suffix)
        target.write_bytes(frozen[key])
        if sha(target.read_bytes()) != hashes[key]:
            raise RuntimeError("could not retain frozen input: " + key)
        frozen_paths[key] = target

    context_text = frozen["ui_context"].decode("utf-8-sig")
    script_text = frozen["script_system"].decode("utf-8-sig")
    test_text = frozen["test_template"].decode("utf-8-sig")
    timer_state_match = re.search(r"enum class TimerState\s*\{[^}]+\};", context_text)
    if not timer_state_match:
        raise RuntimeError("TimerState enum shape changed")
    extracted = {
        "timer_state": timer_state_match.group(0),
        "timer_transition": source_block(context_text, 'if(std::strcmp(operation,"timer")==0){'),
        "close": source_block(context_text, "void CloseInformationalPopup(){"),
        "call": source_block(context_text, "void Call(lua_CFunction function,void* argument){"),
        "fault": source_block(context_text, "void Fault() noexcept {"),
        "stop": source_block(context_text, "void Stop(){"),
    }
    # Confirm Lua registered callbacks pass through ScriptSystem's exception
    # barrier; the standalone test exercises extracted context methods beneath it.
    if "lua_pushcclosure(state,&SafeCallback,1)" not in script_text or "return ProtectedCallback(state,*function);" not in script_text:
        raise RuntimeError("registered native callback is no longer protected by ScriptSystem")
    generated = test_text.replace("@@TIMER_STATE@@", extracted["timer_state"])
    generated = generated.replace("@@TIMER_BLOCK@@", extracted["timer_transition"])
    for token, key in (("@@CLOSE_METHOD@@", "close"), ("@@CALL_METHOD@@", "call"),
                       ("@@FAULT_METHOD@@", "fault"), ("@@STOP_METHOD@@", "stop")):
        generated = generated.replace(token, extracted[key])
    if "@@" in generated:
        raise RuntimeError("unfilled extracted-body placeholder")
    generated_path = frozen_dir / "ui_popup_failure_extracted.cpp"
    generated_bytes = generated.encode("utf-8")
    generated_path.write_bytes(generated_bytes)
    generated_hash = sha(generated_bytes)
    build = build_program(name="ui_popup_failure", architecture="x64", vs=VS, directory=build_dir,
                          evidence=root, source=generated_path, runtime="/MT")
    result = run([build["path"]], cwd=build_dir, timeout=30)
    log = result.stdout + result.stderr
    log_path = root / "execution.log"
    log_path.write_bytes(log)
    output = log.decode("mbcs", errors="replace")
    match = re.search(r"UI_POPUP_FAILURE_COMPONENT_PASS checks=(\d+) GAMECORE_LOADED=false", output)
    if result.returncode or not match:
        raise RuntimeError("isolated extracted-method test failed: " + output[-4000:])

    live_after = {key: sha(path.read_bytes()) for key, path in originals.items()}
    frozen_after = {key: sha(path.read_bytes()) for key, path in frozen_paths.items()}
    if hashes != live_after or hashes != frozen_after:
        raise RuntimeError("a frozen or live input changed during native component test")
    if sha(generated_path.read_bytes()) != generated_hash:
        raise RuntimeError("compiled extracted source changed during the native test")
    report = {
        "status": "UI_POPUP_FAILURE_EXTRACTED_COMPONENT_PASS",
        "run_id": run_id,
        "native_checks": int(match.group(1)),
        "inputs_unchanged_after_run": True,
        "inputs": {key: {"original_source": str(originals[key]), "frozen_copy": str(frozen_paths[key]),
                         "sha256": hashes[key], "bytes": len(frozen[key])} for key in originals},
        "extracted_method_sha256": {key: sha(value.encode("utf-8")) for key, value in extracted.items()},
        "generated_source": artifact(generated_path),
        "compiler": build["compiler"],
        "compiler_sha256": build["compiler_sha256"],
        "compiler_flags": build["flags"],
        "binary": {"path": build["path"], "sha256": build["sha256"]},
        "compile_log": {"path": build["log"], "sha256": build["log_sha256"]},
        "execution_log": artifact(log_path),
        "exit_code": result.returncode,
        "checks": {
            "shown_failure_balances_held_timer_once": True,
            "processed_failure_does_not_repeat_released_timer": True,
            "native_timer_transition_exception_latches_unknown": True,
            "recovery_error_preserves_first_script_error": True,
            "stop_disposes_only_balanced_quiescent_faulted_vm": True,
            "uncertain_stop_retry_never_decrements_or_frees_vm": True,
            "registered_callback_exception_barrier_checked": True,
        },
        "scope": "Exact extracted UiPopupContext timer/Close/Call/Fault/Stop bodies with fake GameCore timer and ScriptSystem adapters; component behavior only, not actual GameCore timer guarantees.",
        "gamecore_loaded": False,
        "game_launched": False,
    }
    (root / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "evidence": str(root), "checks": report["native_checks"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
