"""Propose minimal map-generator failure propagation on accepted SDK attempt_037."""
import json
from functools import lru_cache
from pathlib import Path

from collect_baseline import PROJECT, digest


PREFIX = "new_game_"
BASE = PROJECT / "evidence/sdk_x64/attempts/attempt_037/sdk_x64_patches.json"
ROOT = "CvGameCoreDLL_Expansion2/"
MAP_GENERATOR = ROOT + "CvMapGenerator.cpp"
GAME = ROOT + "CvGame.cpp"
EXPECTED_BASELINE_PATCHES = 693


@lru_cache(maxsize=None)
def baseline_text(source):
    text = (PROJECT / "Source/SDK_BNW_Original" / source).read_bytes().decode("latin1")
    rows = json.loads(BASE.read_text(encoding="utf-8"))["patches"]
    for patch in rows:
        if patch["file"] == source:
            if text.count(patch["old"]) != patch["count"]:
                raise RuntimeError("Accepted attempt_037 baseline mismatch: " + patch["id"])
            text = text.replace(patch["old"], patch["new"])
    return text


@lru_cache(maxsize=None)
def patches():
    result = []

    def add(source, name, old, new, reason):
        original = baseline_text(source)
        newline = "\r\n" if "\r\n" in original else "\n"
        old = old.replace("\r\n", "\n").replace("\n", newline)
        new = new.replace("\r\n", "\n").replace("\n", newline)
        if original.count(old) != 1:
            raise RuntimeError("New-game patch context mismatch: " + name)
        result.append({
            "id": PREFIX + name,
            "file": source,
            "source_sha256": digest(PROJECT / "Source/SDK_BNW_Original" / source),
            "old": old,
            "new": new,
            "count": 1,
            "reason": reason,
        })

    add(MAP_GENERATOR, "load_stdexcept",
        '#include "CvGameCoreDLLPCH.h"\n',
        '#include "CvGameCoreDLLPCH.h"\n#include <stdexcept>\n',
        "Use the existing C++ runtime_error path when a required map script cannot be loaded.")

    add(MAP_GENERATOR, "load_failure_releases_vm",
        'const bool bLoaded = pkScriptSystem->LoadFile(m_pkLuaState, szMapScriptName);\n\tDEBUG_VARIABLE(bLoaded);\n\tCvAssertMsg(bLoaded, "Cannot load mapscript.");',
        'if(m_pkLuaState == NULL)\n\t\tthrow std::runtime_error("Cannot create map script VM.");\n\ttry\n\t{\n\t\tif(!pkScriptSystem->LoadFile(m_pkLuaState, szMapScriptName))\n\t\t\tthrow std::runtime_error("Cannot load mapscript.");\n\t}\n\tcatch(...)\n\t{\n\t\tpkScriptSystem->FreeLuaThread(m_pkLuaState);\n\t\tm_pkLuaState = NULL;\n\t\tthrow;\n\t}',
        "Release a partially constructed generator's Lua VM before failing construction; do not leave a usable-looking empty generator.")

    add(MAP_GENERATOR, "map_init_data_outer_call_failure",
        'pkScriptSystem->CallCFunction(m_pkLuaState, pGetMapInitData, &args);',
        'if(!pkScriptSystem->CallCFunction(m_pkLuaState, pGetMapInitData, &args))\n\t\tthrow std::runtime_error("Map script GetMapInitData() failed.");',
        "Propagate callback execution failure; an absent optional function still returns normally with bSuccess false and retains the engine default.")

    add(MAP_GENERATOR, "generate_map_outer_call_failure",
        'pkScriptSystem->CallCFunction(m_pkLuaState, pGenerateRandomMap, pkScriptSystem);',
        'if(!pkScriptSystem->CallCFunction(m_pkLuaState, pGenerateRandomMap, pkScriptSystem))\n\t\tthrow std::runtime_error("Map script GenerateMap() failed.");',
        "Stop map initialization when the protected GenerateMap callback reports failure.")

    add(MAP_GENERATOR, "initial_overrides_outer_call_failure",
        'pkScriptSystem->CallCFunction(m_pkLuaState, pGetGameInitialItemsOverrides, &args);',
        'if(!pkScriptSystem->CallCFunction(m_pkLuaState, pGetGameInitialItemsOverrides, &args))\n\t\tthrow std::runtime_error("Map script GetGameInitialItemsOverrides() failed.");',
        "Propagate execution failure of an optional override hook while preserving the absent-hook default result.")

    add(MAP_GENERATOR, "map_init_data_inner_call_failure",
        'pArgs->pkScriptSystem->CallFunction(L, 1, 1);',
        'if(!pArgs->pkScriptSystem->CallFunction(L, 1, 1))\n\t\t\treturn luaL_error(L, "Map script GetMapInitData() failed.");',
        "Turn a present GetMapInitData Lua-call failure into a protected callback error; leave the absent-function path untouched.")

    add(MAP_GENERATOR, "initial_overrides_inner_call_failure",
        'pArgs->pkScriptSystem->CallFunction(L, 0, 1);',
        'if(!pArgs->pkScriptSystem->CallFunction(L, 0, 1))\n\t\t\treturn luaL_error(L, "Map script GetGameInitialItemsOverrides() failed.");',
        "Turn a present GetGameInitialItemsOverrides Lua-call failure into a protected callback error; leave the absent-function path untouched.")

    add(MAP_GENERATOR, 'collect_inside_map_callback',
        '\tpkScriptSystem->CallFunction(L, 0, 0);\n\n\treturn 0;',
        '\tpkScriptSystem->CallFunction(L, 0, 0);\n\n\tlua_gc(L, LUA_GCCOLLECT, 0);\n\treturn 0;',
        'Collect after successful map generation while the Lua error boundary remains active.')

    add(MAP_GENERATOR, "generate_map_inner_call_failure",
        'pkScriptSystem->CallFunction(L, 0, 0);',
        'if(!pkScriptSystem->CallFunction(L, 0, 0))\n\t\treturn luaL_error(L, "Map script GenerateMap() failed.");',
        "Propagate the protected Lua GenerateMap invocation failure instead of returning success from its callback.")

    for name, call in (
        ("map_init_data", '\tcvStopWatch stopWatch("CvMapGenerator - GetMapInitData()");'),
        ("initial_overrides", '\tcvStopWatch stopWatch("CvMapGenerator - GetGameInitialItemsOverrides()");'),
        ("generate_map", '\tcvStopWatch stopWatch("CvMapGenerator - GenerateRandomMap()");'),
    ):
        add(MAP_GENERATOR, "remove_lua_callback_stopwatch_" + name,
            call,
            "",
            "Do not keep a non-trivial C++ stopwatch alive across Lua APIs that may longjmp, including luaL_error and allocation failures.")

    for signature, label in (
        ('bool CvMapGenerator::GetMapInitData(CvMapInitData& kData, WorldSizeTypes eWorldSize)', 'GetMapInitData()'),
        ('bool CvMapGenerator::GetGameInitialItemsOverrides(CvGameInitialItemsOverrides& kOverrides)', 'GetGameInitialItemsOverrides()'),
        ('void CvMapGenerator::GenerateRandomMap()', 'GenerateRandomMap()'),
    ):
        add(MAP_GENERATOR, 'outer_stopwatch_'+label[:-2].lower(), signature+'\n{',
            signature+'\n{\n\tcvStopWatch stopWatch("CvMapGenerator - '+label+'");',
            'Retain profiling in the native caller, outside the nested protected Lua execution frame.')

    add(MAP_GENERATOR, 'protected_map_collection', '\n\tlua_gc(m_pkLuaState, LUA_GCCOLLECT, 0);', '',
        'Move full collection into the protected callback so finalizer or allocation errors are returned through CallCFunction.')

    add(GAME, "map_generator_unique_ownership",
        'CvMapGenerator* pGenerator = FNEW(CvMapGenerator(strMapName.c_str()), c_eMPoolTypeGame, 0);',
        'std::unique_ptr<CvMapGenerator> pGenerator(FNEW(CvMapGenerator(strMapName.c_str()), c_eMPoolTypeGame, 0));',
        "Own the generator with RAII so propagated map-script exceptions release its Lua state and allocation.")

    add(GAME, "map_generator_no_manual_delete",
        '\n\t\tdelete pGenerator;\n',
        '\n',
        "Let unique_ptr release the map generator on both normal return and exception unwinding.")

    candidate = {}
    for source in (MAP_GENERATOR, GAME):
        text = baseline_text(source)
        for patch in result:
            if patch["file"] == source:
                if text.count(patch["old"]) != patch["count"]:
                    raise RuntimeError("New-game candidate patch ordering mismatch: " + patch["id"])
                text = text.replace(patch["old"], patch["new"])
        candidate[source] = text
    if "delete pGenerator;" in candidate[GAME] or "std::unique_ptr<CvMapGenerator> pGenerator" not in candidate[GAME]:
        raise RuntimeError("Map-generator RAII candidate is incomplete")
    if "CvAssertMsg(bLoaded" in candidate[MAP_GENERATOR]:
        raise RuntimeError("Map-script load failure candidate is incomplete")
    return result


def main():
    baseline = json.loads(BASE.read_text(encoding="utf-8"))
    if len(baseline["patches"]) != EXPECTED_BASELINE_PATCHES:
        raise RuntimeError("Accepted attempt_037 patch baseline changed")

    proposed = patches()
    report = {
        "status": "SDK_NEW_GAME_PATCHES_PROPOSED_NOT_APPLIED",
        "baseline": {"path": str(BASE), "sha256": digest(BASE)},
        "recipe": {"path": str(Path(__file__).resolve()), "sha256": digest(Path(__file__).resolve())},
        "baseline_patch_count": EXPECTED_BASELINE_PATCHES,
        "added_patch_count": len(proposed),
        "patches": proposed,
        "target_files": [MAP_GENERATOR, GAME],
        "generator_raii_proposed": True,
        "optional_hooks_keep_absent_default": True,
        "stopwatch_longjmp_reviewed": True,
        "gamecore_loaded": False,
        "game_launched": False,
    }
    output = PROJECT / "evidence/new_game_debugger/sdk_patch_plan.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(report["status"])


if __name__ == "__main__":
    main()
