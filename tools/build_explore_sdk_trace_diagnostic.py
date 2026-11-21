"""Prepare or build an isolated SDK DLL candidate with parallel explore scoring.

The default input is the current SaveRestoreSDK pointer. --prepare-only writes
only isolated sources and response files; it never invokes a compiler or linker.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import uuid
from datetime import datetime, timezone

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / "tools"))
from collect_baseline import digest, pe_header  # noqa: E402
from native_build import environment_for, run  # noqa: E402
from verify_world_builder_map_object import check_artifacts  # noqa: E402

BASE_POINTER = PROJECT / "evidence/extended_turns/diagnostics/player_write_trace_sdk/20260930T124153Z_062b570208b2/build_result.json"
ACCEPTED_POINTER = PROJECT / "evidence/sdk_x64/attempts/attempt_037/build_result.json"
MANIFEST = PROJECT / "evidence/sdk_x64/port_manifest.json"
SDK = PROJECT / "Source/SDK_BNW_x64/CvGameCoreDLL_Expansion2/CvEconomicAI.cpp"
GAMECORE_RSP = PROJECT / "evidence/sdk_x64/attempts/attempt_037/gamecore.rsp"
SCORE_HEADER = PROJECT / "Source/Concurrency/ExplorePlotScores.h"
BATCH_HEADER = PROJECT / "Source/Concurrency/OrderedBatch.h"
BRIDGE_HEADER = PROJECT / "Source/Concurrency/ExploreScoreBridge.h"
BRIDGE_SOURCE = PROJECT / "Source/Concurrency/ExploreScoreBridge.cpp"
VS = Path(r"C:\Program Files\Microsoft Visual Studio\2022\Community")

HELPERS = r'''#include "ExploreScoreBridge.h"
#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <stdexcept>
#include <vector>
static_assert(NUM_DIRECTION_TYPES == 6, "Explore bridge expects six Civ V plot directions");

static unsigned int ZeroSisExploreWorkerCount()
{
	const char* value = std::getenv("ZEROSIS_EXPLORE_WORKERS");
	if(value == NULL || value[0] == '\0' || std::strcmp(value, "0") == 0)
		return 0;
	if(std::strcmp(value, "1") == 0) return 1;
	if(std::strcmp(value, "2") == 0) return 2;
	if(std::strcmp(value, "4") == 0) return 4;
	throw std::runtime_error("ZEROSIS_EXPLORE_WORKERS must be 0, 1, 2, or 4");
}

static ZeroSisExploreScoreInput ZeroSisCaptureExploreInput(CvPlot* pPlot, TeamTypes eTeam, DomainTypes eDomain)
{
	static const int offsets[9][2] = {
		{-1, -1}, {-1, 0}, {-1, 1}, {0, -1}, {0, 0}, {0, 1}, {1, -1}, {1, 0}, {1, 1}
	};
	ZeroSisExploreScoreInput input = {};
	input.domain = eDomain == DOMAIN_SEA ? 1 : (eDomain == DOMAIN_LAND ? 0 : 2);
	const int originX = pPlot->getX();
	const int originY = pPlot->getY();
	for(int index = 0; index < 9; ++index)
	{
		ZeroSisExplorePlotValue& value = input.plots[index];
		value.offset_x = static_cast<int8_t>(offsets[index][0]);
		value.offset_y = static_cast<int8_t>(offsets[index][1]);
		CvPlot* pEvalPlot = plotXYWithRangeCheck(originX, originY, offsets[index][0], offsets[index][1], 1);
		if(pEvalPlot == NULL)
			continue;
		value.exists = 1;
		value.is_center_plot = pEvalPlot == pPlot;
		value.revealed = pEvalPlot->isRevealed(eTeam);
		value.adjacent_revealed = pEvalPlot->isAdjacentRevealed(eTeam);
		value.distance_from_origin = plotDistance(originX, originY, pEvalPlot->getX(), pEvalPlot->getY());
		value.water = pEvalPlot->isWater();
		value.mountain = pEvalPlot->isMountain();
		value.hills = pEvalPlot->isHills();	
		const FeatureTypes feature = pEvalPlot->getFeatureType();
		if(feature != NO_FEATURE)
		{
			value.has_feature = 1;
			const CvFeatureInfo* pFeatureInfo = GC.getFeatureInfo(feature);
			value.feature_impassable = pFeatureInfo->isImpassable();
			value.feature_see_through_change_positive = pFeatureInfo->getSeeThroughChange() > 0;
		}

		if(value.adjacent_revealed && value.distance_from_origin > 1)
		{
			for(int direction = 0; direction < NUM_DIRECTION_TYPES; ++direction)
			{
				CvPlot* pAdjacentPlot = plotDirection(pEvalPlot->getX(), pEvalPlot->getY(), static_cast<DirectionTypes>(direction));
				ZeroSisExploreNeighborValue& adjacent = value.adjacent_plots[direction];
				if(pAdjacentPlot == NULL)
					continue;
				adjacent.exists = 1;
				adjacent.revealed = pAdjacentPlot->isRevealed(eTeam);
				if(!adjacent.revealed)
					continue;
				adjacent.distance_from_origin = plotDistance(originX, originY, pAdjacentPlot->getX(), pAdjacentPlot->getY());
				if(adjacent.distance_from_origin > 1)
					continue;
				if(pPlot->canSeePlot(pEvalPlot, eTeam, 1, NO_DIRECTION))
				{
					value.origin_can_see_candidate = 1;
					break;
				}
			}
		}
	}
	return input;
}

static unsigned long long ZeroSisExploreElapsedUs(std::chrono::steady_clock::time_point start)
{
	return static_cast<unsigned long long>(std::chrono::duration_cast<std::chrono::microseconds>(
		std::chrono::steady_clock::now() - start).count());
}

static void ZeroSisEmitExploreMetrics(int player, int turn, unsigned int mode, unsigned int count,
	unsigned long long snapshotUs, const ZeroSisExploreBatchMetrics& batch,
	unsigned long long validationUs, unsigned long long updateUs)
{
	char workerIds[256] = {0};
	unsigned int used = 0;
	for(unsigned int index = 0; index < batch.worker_threads_used && index < 64; ++index)
	{
		const int written = std::snprintf(workerIds + used, sizeof(workerIds) - used,
			"%s%u", index == 0 ? "" : ",", batch.worker_ids[index]);
		if(written < 0 || static_cast<unsigned int>(written) >= sizeof(workerIds) - used)
			break;
		used += static_cast<unsigned int>(written);
	}
	char line[1024] = {0};
	std::snprintf(line, sizeof(line),
		"ZEROSIS_EXPLORE_BATCH player=%d turn=%d mode=%u requested_workers=%u plots=%u snapshot_us=%llu worker_us=%llu validation_us=%llu update_us=%llu workers_started=%u jobs_started=%u jobs_completed=%u worker_threads_used=%u max_overlap=%u worker_ids=%s\n",
		player, turn, mode == 0 ? 0 : 1, mode, count, snapshotUs,
		static_cast<unsigned long long>(batch.worker_batch_us), validationUs, updateUs,
		batch.workers_started, batch.jobs_started, batch.jobs_completed,
		batch.worker_threads_used, batch.maximum_overlapping_jobs, workerIds);
	std::printf("%s", line);
	std::fflush(stdout);
}
'''


def unique_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ_") + uuid.uuid4().hex[:12]


def write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def atomic_json(path: Path, value: dict) -> None:
    temporary = path.with_name(path.name + ".tmp-" + uuid.uuid4().hex)
    write_json(temporary, value)
    temporary.replace(path)


def record(path: Path) -> dict:
    return {"path": str(path), "sha256": digest(path), "size": path.stat().st_size}


def frozen_copy(source: Path, folder: Path, key: str) -> dict:
    target = folder / key / source.name
    target.parent.mkdir(parents=True, exist_ok=False)
    shutil.copyfile(source, target)
    return {"original_path": str(source), "artifact": record(target)}


def verify_artifact(ref: dict, label: str) -> Path:
    path = Path(ref["path"])
    if not path.is_file() or digest(path) != ref["sha256"]:
        raise RuntimeError(f"Frozen base {label} artifact is missing or changed: {path}")
    return path


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if text.count(old) != 1:
        raise RuntimeError(f"Expected one source anchor for {label}, found {text.count(old)}")
    return text.replace(old, new, 1)


def prepare_economic_source(source_text: str) -> str:
    source_text = replace_once(
        source_text,
        '#include "cvStopWatch.h"\r\n',
        '#include "cvStopWatch.h"\r\n' + HELPERS.replace("\n", "\r\n") + "\r\n",
        "bridge helper insertion",
    )
    start_marker = "/// Go through the plots for the exploration automation to evaluate\r\nvoid CvEconomicAI::UpdatePlots()\r\n{"
    if source_text.count(start_marker) != 1:
        raise RuntimeError("Could not locate the unique UpdatePlots function")
    function_start = source_text.index(start_marker)
    function_end = source_text.index("\r\n#define PATH_PLAN_LAST", function_start)
    body = source_text[function_start:function_end]
    body = replace_once(
        body,
        "void CvEconomicAI::UpdatePlots()\r\n{",
        "void CvEconomicAI::UpdatePlots()\r\n{\r\n"
        "\tconst std::chrono::steady_clock::time_point updateStart = std::chrono::steady_clock::now();\r\n"
        "\tconst unsigned int exploreWorkers = ZeroSisExploreWorkerCount();\r\n"
        "\tunsigned int exploreScoredPlotCount = 0;\r\n"
        "\tunsigned long long snapshotUs = 0;\r\n"
        "\tunsigned long long validationUs = 0;\r\n"
        "\tZeroSisExploreBatchMetrics exploreBatch = {};\r\n"
        "\tstd::vector<int> exploreScoresByIndex;\r\n"
        "\tif(exploreWorkers != 0)\r\n"
        "\t{\r\n"
        "\t\tconst int plotCount = GC.getMap().numPlots();\r\n"
        "\t\tstd::vector<int> candidateIndices;\r\n"
        "\t\tstd::vector<ZeroSisExploreScoreInput> snapshots;\r\n"
        "\t\tconst std::chrono::steady_clock::time_point snapshotStart = std::chrono::steady_clock::now();\r\n"
        "\t\tfor(int plotIndex = 0; plotIndex < plotCount; ++plotIndex)\r\n"
        "\t\t{\r\n"
        "\t\t\tCvPlot* pSnapshotPlot = GC.getMap().plotByIndexUnchecked(plotIndex);\r\n"
        "\t\t\tif(pSnapshotPlot == NULL || !pSnapshotPlot->isRevealed(m_pPlayer->getTeam())) continue;\r\n"
        "\t\t\tconst DomainTypes snapshotDomain = pSnapshotPlot->isWater() ? DOMAIN_SEA : DOMAIN_LAND;\r\n"
        "\t\t\tcandidateIndices.push_back(plotIndex);\r\n"
        "\t\t\tsnapshots.push_back(ZeroSisCaptureExploreInput(pSnapshotPlot, m_pPlayer->getTeam(), snapshotDomain));\r\n"
        "\t\t}\r\n"
        "\t\tsnapshotUs = ZeroSisExploreElapsedUs(snapshotStart);\r\n"
        "\t\tstd::vector<int> candidateScores(snapshots.size(), 0);\r\n"
        "\t\tconst int bridgeStatus = ZeroSisEvaluateExploreScores(snapshots.empty() ? NULL : &snapshots[0],\r\n"
        "\t\t\tstatic_cast<unsigned int>(snapshots.size()), exploreWorkers,\r\n"
        "\t\t\tcandidateScores.empty() ? NULL : &candidateScores[0], &exploreBatch);\r\n"
        "\t\tif(bridgeStatus != 0) throw std::runtime_error(\"Explore score bridge failed; no plot lists changed\");\r\n"
        "\t\tconst std::chrono::steady_clock::time_point validationStart = std::chrono::steady_clock::now();\r\n"
        "\t\tfor(size_t index = 0; index < candidateIndices.size(); ++index)\r\n"
        "\t\t{\r\n"
        "\t\t\tCvPlot* pShadowPlot = GC.getMap().plotByIndexUnchecked(candidateIndices[index]);\r\n"
        "\t\t\tif(pShadowPlot == NULL) throw std::runtime_error(\"Explore snapshot plot disappeared; no plot lists changed\");\r\n"
        "\t\t\tconst DomainTypes shadowDomain = pShadowPlot->isWater() ? DOMAIN_SEA : DOMAIN_LAND;\r\n"
        "\t\t\tconst int shadowScore = ScoreExplorePlot(pShadowPlot, m_pPlayer->getTeam(), 1, shadowDomain);\r\n"
        "\t\t\tif(shadowScore != candidateScores[index]) throw std::runtime_error(\"Explore score shadow mismatch; no plot lists changed\");\r\n"
        "\t\t}\r\n"
        "\t\tvalidationUs = ZeroSisExploreElapsedUs(validationStart);\r\n"
        "\t\texploreScoresByIndex.assign(static_cast<size_t>(plotCount), 0);\r\n"
        "\t\tfor(size_t index = 0; index < candidateIndices.size(); ++index)\r\n"
        "\t\t\texploreScoresByIndex[candidateIndices[index]] = candidateScores[index];\r\n"
        "\t}\r\n",
        "preflight snapshot, parallel evaluation, and full shadow validation",
    )
    body = replace_once(
        body,
        "\t\tint iScore = ScoreExplorePlot(pPlot, ePlayerTeam, 1, eDomain);",
        "\t\t++exploreScoredPlotCount;\r\n"
        "\t\tconst int iScore = exploreWorkers == 0 ? ScoreExplorePlot(pPlot, ePlayerTeam, 1, eDomain)\r\n"
        "\t\t\t: exploreScoresByIndex[static_cast<size_t>(i)];",
        "range-1 score lookup replacement",
    )
    body = replace_once(
        body,
        "\tm_bExplorationPlotsDirty = false;\r\n}",
        "\tm_bExplorationPlotsDirty = false;\r\n"
        "\tZeroSisEmitExploreMetrics(m_pPlayer->GetID(), GC.getGame().getGameTurn(), exploreWorkers, exploreScoredPlotCount,\r\n"
        "\t\tsnapshotUs, exploreBatch, validationUs, ZeroSisExploreElapsedUs(updateStart));\r\n"
        "}",
        "final UpdatePlots metric emission",
    )
    return source_text[:function_start] + body + source_text[function_end:]

def build_main(prepare_only: bool) -> dict:
    base_pointer_bytes = BASE_POINTER.read_bytes()
    base = json.loads(base_pointer_bytes.decode("utf-8"))
    check_artifacts(base)
    if base.get("status") != "SAVE_RESTORE_SDK_CANDIDATE_LINKED":
        raise RuntimeError("Current SaveRestoreSDK pointer is not a linked production candidate")
    base_id = base.get("build_id")
    if not base_id:
        raise RuntimeError("SaveRestoreSDK report lacks build_id")
    for key in ("accepted_build", "new_game_sdk_build", "shared_lua_build", "link_response", "gamecore", "map", "pch_reused"):
        if key not in base:
            raise RuntimeError(f"SaveRestoreSDK report lacks required {key} artifact")
    link_source = verify_artifact(base["link_response"], "link response")
    pch_path = verify_artifact(base["pch_reused"], "reused C++14 PCH")
    if digest(BASE_POINTER) != hashlib.sha256(base_pointer_bytes).hexdigest():
        raise RuntimeError("Current SaveRestoreSDK pointer changed during initial read")

    accepted_path = verify_artifact(base["accepted_build"], "accepted SDK result")
    accepted = json.loads(accepted_path.read_text(encoding="utf-8"))
    if accepted.get("status") != "SDK_X64_ALL_OBJECTS_COMPILED" or accepted.get("attempt") != 37:
        raise RuntimeError("Frozen candidate is not based on accepted attempt_037")
    manifest_path = verify_artifact(accepted["manifest"], "SDK port manifest")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    source_row = next((row for row in manifest if row.get("relative_path") ==
                       "CvGameCoreDLL_Expansion2/CvEconomicAI.cpp"), None)
    if source_row is None or Path(source_row["port"]).resolve() != SDK.resolve():
        raise RuntimeError("Port manifest does not identify the expected CvEconomicAI source")
    if digest(SDK) != source_row.get("port_sha256"):
        raise RuntimeError("Current CvEconomicAI source hash differs from frozen attempt_037 manifest")
    for path in (GAMECORE_RSP, SCORE_HEADER, BATCH_HEADER, BRIDGE_HEADER, BRIDGE_SOURCE, Path(__file__).resolve()):
        if not path.is_file():
            raise RuntimeError(f"Required candidate input is missing: {path}")
    if base.get("gamecore", {}).get("pe", {}).get("architecture") != "x64":
        raise RuntimeError("Frozen SaveRestoreSDK candidate is not x64")

    build_id = unique_id()
    build_dir = PROJECT / "Build/ExtendedTurnDiagnostics/ExploreSDK" / build_id
    evidence_dir = PROJECT / "evidence/extended_turns/diagnostics/explore_sdk" / build_id
    build_dir.mkdir(parents=True, exist_ok=False)
    evidence_dir.mkdir(parents=True, exist_ok=False)
    frozen_dir = evidence_dir / "frozen"
    frozen_dir.mkdir()

    frozen_inputs = []
    frozen_inputs.append(frozen_copy(SDK, frozen_dir, "sdk_source"))
    for key, path in (("score_kernel", SCORE_HEADER), ("ordered_batch", BATCH_HEADER),
                      ("bridge_header", BRIDGE_HEADER), ("bridge_source", BRIDGE_SOURCE),
                      ("compile_recipe", GAMECORE_RSP), ("accepted_manifest", manifest_path),
                      ("base_link_recipe", link_source), ("base_report", BASE_POINTER),
                      ("reused_pch", pch_path), ("builder", Path(__file__).resolve())):
        frozen_inputs.append(frozen_copy(path, frozen_dir, key))
    for key, ref_name in (("accepted_result", "accepted_build"),
                          ("new_game_result", "new_game_sdk_build"),
                          ("shared_lua_result", "shared_lua_build"),
                          ("base_gamecore", "gamecore"), ("base_map", "map")):
        path = verify_artifact(base[ref_name], ref_name)
        frozen_inputs.append(frozen_copy(path, frozen_dir, key))
    for key, ref_name in (("save_restore_builder", "builder"),
                          ("save_restore_patch_spec", "patch_specification"),
                          ("save_restore_patch_builder", "patch_builder")):
        if ref_name in base:
            path = verify_artifact(base[ref_name], ref_name)
            frozen_inputs.append(frozen_copy(path, frozen_dir, key))
    frozen_report = json.loads((frozen_dir / "base_report" / BASE_POINTER.name).read_text(encoding="utf-8"))
    if frozen_report.get("build_id") != base_id or digest(BASE_POINTER) != digest(frozen_dir / "base_report" / BASE_POINTER.name):
        raise RuntimeError("Frozen SaveRestoreSDK report is inconsistent")

    frozen_sdk = Path(next(row["artifact"]["path"] for row in frozen_inputs
                          if row["original_path"] == str(SDK)))
    frozen_bridge = Path(next(row["artifact"]["path"] for row in frozen_inputs
                              if row["original_path"] == str(BRIDGE_SOURCE)))
    frozen_gamecore_rsp = Path(next(row["artifact"]["path"] for row in frozen_inputs
                                    if row["original_path"] == str(GAMECORE_RSP)))
    frozen_link_source = Path(next(row["artifact"]["path"] for row in frozen_inputs
                                   if row["original_path"] == str(link_source)))
    source_text = frozen_sdk.read_bytes().decode("latin1")
    candidate_text = prepare_economic_source(source_text)
    overlay = build_dir / "Source/CvGameCoreDLL_Expansion2"
    overlay.mkdir(parents=True)
    economic_source = overlay / "CvEconomicAI.cpp"
    economic_source.write_bytes(candidate_text.encode("latin1"))
    bridge_source_copy = overlay / "ExploreScoreBridge.cpp"
    shutil.copyfile(frozen_bridge, bridge_source_copy)
    frozen_include_dir = build_dir / "Concurrency"
    frozen_include_dir.mkdir()
    for original in (SCORE_HEADER, BATCH_HEADER, BRIDGE_HEADER):
        frozen_path = Path(next(row["artifact"]["path"] for row in frozen_inputs
                                if row["original_path"] == str(original)))
        shutil.copyfile(frozen_path, frozen_include_dir / original.name)

    accepted_objects = accepted.get("objects", [])
    old_object_row = next((row for row in accepted_objects if Path(row.get("path", "")).name == "CvEconomicAI.obj"), None)
    if old_object_row is None:
        raise RuntimeError("Accepted SDK object manifest lacks CvEconomicAI.obj")
    base_object = Path(old_object_row["path"])
    if not base_object.is_file() or digest(base_object) != old_object_row["sha256"]:
        raise RuntimeError("Accepted CvEconomicAI.obj is absent or changed")
    economic_object = build_dir / "CvEconomicAI.obj"
    bridge_object = build_dir / "ExploreScoreBridge.obj"

    compile_flags = [line for line in frozen_gamecore_rsp.read_text(encoding="utf-8").splitlines()
                     if not line.startswith('"') and not line.startswith("/Fo") and line != "/MP4"]
    if "/std:c++14" not in compile_flags or not any(line.startswith("/Yu") for line in compile_flags):
        raise RuntimeError("Frozen SDK compile recipe lost C++14 PCH flags")
    economic_rsp = build_dir / "CvEconomicAI.rsp"
    economic_flags = compile_flags + [f'/I"{frozen_include_dir}"',
                                      f'/Fo"{economic_object}"', f'"{economic_source}"']
    economic_rsp.write_text("\n".join(economic_flags) + "\n", encoding="utf-8")
    bridge_rsp = build_dir / "ExploreScoreBridge.rsp"
    bridge_flags = ["/nologo", "/c", "/std:c++17", "/EHsc", "/MD", "/O2", "/W4", "/WX",
                    f'/I"{frozen_include_dir}"', f'/Fo"{bridge_object}"', f'"{bridge_source_copy}"']
    bridge_rsp.write_text("\n".join(bridge_flags) + "\n", encoding="utf-8")

    link_text = frozen_link_source.read_text(encoding="utf-8")
    def_match = re.search(r'^/DEF:"([^"]+)"$', link_text, re.M)
    if not def_match:
        raise RuntimeError("Frozen base link response lacks a quoted .def input")
    def_source = Path(def_match.group(1))
    if not def_source.is_file():
        raise RuntimeError("Frozen base .def input is missing")
    frozen_def = frozen_copy(def_source, frozen_dir, "module_definition")
    frozen_inputs.append(frozen_def)
    frozen_def_path = Path(frozen_def["artifact"]["path"])
    link_text = link_text.replace(def_match.group(0), f'/DEF:"{frozen_def_path}"', 1)
    quoted_old_object = '"' + str(base_object) + '"'
    if link_text.count(quoted_old_object) != 1:
        raise RuntimeError("Base link response does not contain CvEconomicAI.obj exactly once")
    link_text = link_text.replace(quoted_old_object, '"' + str(economic_object) + '"', 1)
    link_text = link_text.replace('"' + str(economic_object) + '"',
                                  '"' + str(economic_object) + '"\n"' + str(bridge_object) + '"', 1)
    candidate_dll = build_dir / "CvGameCoreDLL_Expansion2_x64.dll"
    candidate_map = build_dir / "CvGameCoreDLL_Expansion2_x64.map"
    for option, target in (("OUT", candidate_dll), ("IMPLIB", candidate_dll.with_suffix(".lib")),
                           ("MAP", candidate_map)):
        link_text, count = re.subn(r"^/" + option + r":[^\r\n]+",
                                   lambda _: f'/{option}:"{target}"', link_text, flags=re.M)
        if count != 1:
            raise RuntimeError("Base link output option was not uniquely located: " + option)
    link_rsp = build_dir / "link.rsp"
    link_rsp.write_text(link_text, encoding="utf-8")

    status = "EXPLORE_SDK_CANDIDATE_PREPARED_NOT_BUILT"
    build_records = None
    if not prepare_only:
        environment, compiler_name = environment_for(VS, "x64", build_dir)
        compiler = Path(compiler_name)
        environment["VSLANG"] = "1033"
        executions = []
        for name, response in (("CvEconomicAI", economic_rsp), ("ExploreScoreBridge", bridge_rsp)):
            result = run([compiler, "@" + str(response)], cwd=build_dir, env=environment, timeout=180)
            log_path = evidence_dir / f"{name}_compile.log"
            log_path.write_bytes(result.stdout + result.stderr)
            if result.returncode:
                raise RuntimeError(f"Candidate compilation failed for {name}: {log_path}")
            obj_path = economic_object if name == "CvEconomicAI" else bridge_object
            if not obj_path.is_file():
                raise RuntimeError(f"Compiler did not produce {obj_path.name}")
            executions.append({"name": name, "object": record(obj_path), "response": record(response),
                               "log": record(log_path)})
        linker = compiler.with_name("link.exe")
        linked = run([linker, "@" + str(link_rsp)], cwd=build_dir, env=environment, timeout=180)
        link_log = evidence_dir / "link.log"
        link_log.write_bytes(linked.stdout + linked.stderr)
        if linked.returncode or not candidate_dll.is_file() or not candidate_map.is_file():
            raise RuntimeError(f"Candidate link failed: {link_log}")
        dumpbin = compiler.with_name("dumpbin.exe")
        inspected = run([dumpbin, "/dependents", str(candidate_dll)], cwd=build_dir, env=environment, timeout=60)
        imports_log = evidence_dir / "imports.log"
        imports_log.write_bytes(inspected.stdout + inspected.stderr)
        imports = re.findall(r"^\s+([\w.-]+\.dll)\s*$",
                             (inspected.stdout + inspected.stderr).decode("mbcs", errors="replace"), re.M | re.I)
        if (inspected.returncode or "ZeroSisLua51_x64.dll" not in imports or
                "ZeroSisDatabase_x64.dll" not in imports):
            raise RuntimeError("Candidate DLL did not retain the shared Lua and database imports")
        pe = pe_header(candidate_dll)
        if pe.get("architecture") != "x64" or not pe.get("is_dll"):
            raise RuntimeError("Candidate output is not an x64 DLL")
        status = "EXPLORE_SDK_CANDIDATE_LINKED"
        build_records = {"executions": executions, "gamecore": record(candidate_dll),
                         "map": record(candidate_map), "link_response": record(link_rsp),
                         "link_log": record(link_log), "imports": imports,
                         "imports_log": record(imports_log), "pe": pe,
                         "compiler": record(compiler), "linker": record(linker),
                         "dumpbin": record(dumpbin)}

    if digest(BASE_POINTER) != hashlib.sha256(base_pointer_bytes).hexdigest():
        raise RuntimeError("Current SaveRestoreSDK pointer changed during candidate preparation")
    for source in (SDK, SCORE_HEADER, BATCH_HEADER, BRIDGE_HEADER, BRIDGE_SOURCE,
                   GAMECORE_RSP, Path(__file__).resolve(), def_source, pch_path):
        frozen_row = next((row for row in frozen_inputs if row["original_path"] == str(source)), None)
        if frozen_row is None or digest(source) != frozen_row["artifact"]["sha256"]:
            raise RuntimeError(f"Candidate source changed while preparing: {source}")

    report = {
        "status": status,
        "build_id": build_id,
        "base_save_restore_build_id": base_id,
        "frozen_inputs": frozen_inputs,
        "sdk_source": {"artifact": record(economic_source), "original_path": str(SDK),
                       "original_sha256": source_row["port_sha256"]},
        "candidate_source": record(economic_source),
        "compile_responses": {"economic_cxx14_pch": record(economic_rsp),
                               "bridge_cxx17": record(bridge_rsp)},
        "link_response": record(link_rsp),
        "base_link_response": {"artifact": record(frozen_link_source), "original_path": str(link_source)},
        "replacement_object": {"old": old_object_row, "new_path": str(economic_object)},
        "bridge_object": {"artifact": record(bridge_object), "linked": True} if build_records else
                         {"path": str(bridge_object), "built": False},
        "shared_lua_runtime": base["shared_lua_build"],
        "snapshot_source_us_field": "snapshot_us",
        "worker_batch_us_field": "worker_us",
        "shadow_validation_us_field": "validation_us",
        "full_update_us_field": "update_us",
        "runtime_log_prefix": "ZEROSIS_EXPLORE_BATCH",
        "worker_overlap_is_runtime_verified": False,
        "gamecore_loaded": False,
        "active_sdk_updated": False,
        "stage_updated": False,
        "build_records": build_records,
        "gamecore": build_records["gamecore"] if build_records else
                    {"path": str(candidate_dll), "built": False, "source_path": str(link_rsp)},
        "map": build_records["map"] if build_records else
               {"path": str(candidate_map), "built": False, "source_path": str(link_rsp)},
    }
    report_path = evidence_dir / "build_result.json"
    write_json(report_path, report)
    print(json.dumps({"status": status, "build_id": build_id, "build_dir": str(build_dir),
                      "evidence": str(report_path), "gamecore_built": not prepare_only}, ensure_ascii=False))
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prepare-only", action="store_true",
                        help="Write isolated source and response files without invoking tools")
    args = parser.parse_args()
    build_main(args.prepare_only)


if __name__ == "__main__":
    main()
