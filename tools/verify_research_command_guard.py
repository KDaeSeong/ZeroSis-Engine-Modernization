"""Run the ResearchCommandGuard against the bundled x64 Lua 5.1 runtime."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
DEFAULT_LUA = PROJECT / "Build/SharedLuaRuntime/Lua/ZeroSisLua51_x64.dll"
GUARD = PROJECT / "Source/Host/ResearchCommandGuard.lua"
TEST = PROJECT / "Tests/research_command_guard.lua"
PROBE = PROJECT / "Tests/research_tree_official_selection.lua"
TECH_TREE = Path(r"C:\Program Files (x86)\Steam\steamapps\common\Sid Meier's Civilization V\Assets\DLC\Expansion2\UI\TechTree\TechTree.lua")


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--lua-dll", type=Path, default=DEFAULT_LUA)
    parser.add_argument("--evidence-root", type=Path, default=PROJECT / "evidence/research_command_guard")
    args = parser.parse_args()
    frozen = {"guard": GUARD.read_bytes(), "test": TEST.read_bytes(), "lua": args.lua_dll.resolve().read_bytes(),
              "tech_tree": TECH_TREE.read_bytes(), "probe": PROBE.read_bytes()}
    hashes = {name: sha(data) for name, data in frozen.items()}
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "_" + uuid.uuid4().hex[:12]
    evidence = args.evidence_root.resolve() / run_id
    frozen_dir = evidence / "frozen_inputs"
    frozen_dir.mkdir(parents=True, exist_ok=False)
    copies = {}
    for name, path in (("guard", GUARD), ("test", TEST), ("lua", args.lua_dll.resolve()),
                       ("tech_tree", TECH_TREE), ("probe", PROBE)):
        target = frozen_dir / (name + path.suffix)
        target.write_bytes(frozen[name])
        if sha(target.read_bytes()) != hashes[name]:
            raise RuntimeError("frozen input copy mismatch: " + name)
        copies[name] = target

    spec = importlib.util.spec_from_file_location("ui_scene_verifier", PROJECT / "tools/verify_ui_scene.py")
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    source = b"local SOURCE_GUARD=" + b"[====[" + frozen["guard"] + b"]====]\n" + frozen["test"].replace(
        b"@@SOURCE_GUARD@@", b"[====[" + frozen["guard"] + b"]====]"
    )
    failure = None
    result = None
    try:
        result = json.loads(module.run_lua(copies["lua"], source))
        assert result["status"] == "PASS_RESEARCH_COMMAND_GUARD_COMPONENT"
        assert result["nativeMock"] and not result["sdkReceiverExecuted"] and not result["gamecoreExecuted"]
        assert result["dispatches"] == 2 and result["rejectedCases"] == 16
        tech = frozen["tech_tree"].decode("utf-8-sig")
        assert "Network.SendResearch(eTech, 0, stealingTechTargetPlayerID, UIManager:GetShift())" in tech
        assert "Network.SendResearch(eTech, player:GetNumFreeTechs(), -1, UIManager:GetShift())" in tech
        assert "player:CanResearch( techID ) and not scienceDisabled" in tech
        guard = frozen["guard"].decode("utf-8")
        assert "ZeroSisUi.PopupKind=='ResearchTree'" in guard and "ZeroSisUi.ContextName=='TechTree'" in guard
        match = re.search(rb"(?ms)^function TechSelected[ \t]*\([^\n]*\)\r?\n.*?^end[ \t\r]*$",
                          frozen["tech_tree"])
        assert match, "stock TechSelected function extraction failed"
        probe_template = frozen["probe"].replace(
            b"@@SOURCE_GUARD@@", b"[====[" + frozen["guard"] + b"]====]").replace(
            b"@@STOCK_TECH_SELECTED@@", b"[====[" + match.group(0) + b"]====]")
        probe_source = b"local SOURCE_GUARD=[====[" + frozen["guard"] + b"]====]\n" + \
            b"local STOCK_TECH_SELECTED=[====[" + match.group(0) + b"]====]\n" + \
            probe_template
        probe_result = json.loads(module.run_lua(copies["lua"], probe_source))
        assert probe_result["status"] == "PASS_RESEARCH_TREE_OFFICIAL_SELECTION_PROBE"
        assert probe_result["dispatches"] == 1 and probe_result["rejectedCases"] == 4
        assert probe_result["popupRemainedOpen"] and probe_result["timer"] == 1 and \
               probe_result["turn"] == 0 and probe_result["clock"] == 0.25 and \
               probe_result["seed"] == 9281 and probe_result["nativeMock"] and \
               not probe_result["sdkReceiverExecuted"] and not probe_result["gamecoreExecuted"]
    except Exception as exc:
        failure = f"{type(exc).__name__}: {exc}"
    live = {"guard": sha(GUARD.read_bytes()), "test": sha(TEST.read_bytes()), "lua": sha(args.lua_dll.resolve().read_bytes()),
            "tech_tree": sha(TECH_TREE.read_bytes()), "probe": sha(PROBE.read_bytes())}
    copies_live = {name: sha(path.read_bytes()) for name, path in copies.items()}
    unchanged = live == hashes == copies_live
    status = "PASS_RESEARCH_COMMAND_GUARD_COMPONENT" if failure is None and unchanged else "FAIL_RESEARCH_COMMAND_GUARD_COMPONENT"
    report = {
        "status": status, "run_id": run_id,
        "scope": "ResearchCommandGuard Lua component with mock owner, rules, context, and native callback",
        "inputs_unchanged_after_run": unchanged,
        "inputs": {name: {"path": str(path), "frozen_path": str(copies[name]), "sha256": hashes[name],
                           "original_unchanged": live[name] == hashes[name],
                           "frozen_unchanged": copies_live[name] == hashes[name]}
                   for name, path in (("guard", GUARD), ("test", TEST), ("lua", args.lua_dll.resolve()),
                                      ("tech_tree", TECH_TREE), ("probe", PROBE))},
        "component_result": result, "stock_tech_tree_callback_probe": probe_result if failure is None else None,
        "failure": failure,
        "sdk_execution": False, "gamecore_execution": False,
        "limitations": [
            "The command callback is a test mock; this does not execute the SDK receiver or GameCore.",
            "The native Host ResearchTree context/owner lock and LocalSdkSession binding require the root Host proof.",
            "The stock TechTree passes its free-tech count and Shift state; the guard admits only (tech,0,-1,false) until the receiver supports other tuples.",
            "The stock UI registers unavailable-but-ever-researchable technologies; CanResearch rejects those future queue selections before native mutation.",
        ],
    }
    (evidence / "conformance.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": status, "evidence": str(evidence), "failure": failure}, ensure_ascii=False))
    return 0 if status.startswith("PASS_") else 1


if __name__ == "__main__":
    raise SystemExit(main())
