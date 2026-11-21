"""Create an isolated CitySite SDK candidate from the frozen Explore SDK base.

This tool intentionally has no host-run or active-pointer update path. It compiles
only when explicitly invoked without --prepare-only; the root task owns that gate.
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

BASE_ID = "20260930T130230Z_1d2ea0512c6b"
BASE_DIR = PROJECT / "Build/ExploreSDK" / BASE_ID
BASE_REPORT_PATH = PROJECT / "evidence/explore_sdk" / BASE_ID / "build_result.json"
SDK_SOURCE = PROJECT / "Source/SDK_BNW_x64/CvGameCoreDLL_Expansion2/CvCitySpecializationAI.cpp"
CITY_HEADER = PROJECT / "Source/Concurrency/CitySiteScoreBridge.h"
CITY_SOURCE = PROJECT / "Source/Concurrency/CitySiteScoreBridge.cpp"
TRACE_HEADER = PROJECT / "Source/Diagnostics/CitySiteCpuTrace.h"
TRACE_SOURCE = PROJECT / "Source/Diagnostics/CitySiteCpuTrace.cpp"
TRACE_ETW_LIBRARY = Path(r"C:\Program Files (x86)\Windows Kits\10\Lib\10.0.26100.0\um\x64\Advapi32.Lib")
KERNEL = PROJECT / "Source/Concurrency/CitySiteScores.h"
BATCH = PROJECT / "Source/Concurrency/OrderedBatch.h"
VS = Path(r"C:\Program Files\Microsoft Visual Studio\2022\Community")

PATCH_HELPERS = r'''#include "CitySiteScoreBridge.h"
#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <stdexcept>
#include <vector>
static_assert(YIELD_FOOD == 0 && YIELD_PRODUCTION == 1 && YIELD_GOLD == 2 &&
	YIELD_SCIENCE == 3 && CITY_HOME_PLOT == 0, "City-site POD yield/home order mismatch");

static unsigned int ZeroSisCitySiteWorkerCount()
{
	const char* value = std::getenv("ZEROSIS_CITY_SITE_WORKERS");
	if(value == NULL || value[0] == '\0' || std::strcmp(value, "0") == 0) return 0;
	if(std::strcmp(value, "1") == 0) return 1;
	if(std::strcmp(value, "2") == 0) return 2;
	if(std::strcmp(value, "4") == 0) return 4;
	throw std::runtime_error("ZEROSIS_CITY_SITE_WORKERS must be 0, 1, 2, or 4");
}

static unsigned long long ZeroSisCitySiteNowUs()
{
	return static_cast<unsigned long long>(std::chrono::duration_cast<std::chrono::microseconds>(
		std::chrono::steady_clock::now().time_since_epoch()).count());
}

static void ZeroSisCitySiteHashU32(unsigned long long& hash, unsigned int value)
{
	for(unsigned int shift = 0; shift != 32; shift += 8) { hash ^= (value >> shift) & 0xffu; hash *= 1099511628211ULL; }
}

static void ZeroSisCitySiteHashI32(unsigned long long& hash, int value)
{
	ZeroSisCitySiteHashU32(hash, static_cast<unsigned int>(value));
}

static void ZeroSisCitySiteHashRow(unsigned long long& hash, int plotIndex, const int values[4])
{
	ZeroSisCitySiteHashI32(hash, plotIndex);
	for(int yield = 0; yield < 4; ++yield) ZeroSisCitySiteHashI32(hash, values[yield]);
}

struct ZeroSisCitySiteRecordedValue
{
	int plot_index;
	int values[4];
};

static ZeroSisCitySiteInput ZeroSisCaptureCitySite(CvPlot* pPlot, CvPlayer* pPlayer)
{
	ZeroSisCitySiteInput input = {};
	input.abi_version = ZEROSIS_CITY_SITE_ABI_VERSION;
	input.config_version = ZEROSIS_CITY_SITE_CONFIG_VERSION;
	input.tile_count = static_cast<unsigned int>(GC.getAI_CITY_SPECIALIZATION_YIELD_NUM_TILES_CONSIDERED());
	if(input.tile_count > ZEROSIS_CITY_SITE_MAX_TILES) throw std::runtime_error("City-site tile count exceeds ABI capacity");
	input.ring_weights[0] = GC.getAI_CITY_SPECIALIZATION_YIELD_WEIGHT_FIRST_RING();
	input.ring_weights[1] = GC.getAI_CITY_SPECIALIZATION_YIELD_WEIGHT_SECOND_RING();
	input.ring_weights[2] = GC.getAI_CITY_SPECIALIZATION_YIELD_WEIGHT_THIRD_RING();
	for(unsigned int index = 0; index < input.tile_count; ++index)
	{
		ZeroSisCitySiteCell& cell = input.cells[index];
		if(index == CITY_HOME_PLOT) continue;
		CvPlot* pCellPlot = plotCity(pPlot->getX(), pPlot->getY(), index);
		if(pCellPlot == NULL) continue;
		cell.present = 1;
		cell.ring_distance = plotDistance(pCellPlot->getX(), pCellPlot->getY(), pPlot->getX(), pPlot->getY());
		cell.yields[0] = pCellPlot->getYield(YIELD_FOOD);
		cell.yields[1] = pCellPlot->getYield(YIELD_PRODUCTION);
		cell.yields[2] = pCellPlot->getYield(YIELD_GOLD);
		cell.yields[3] = pCellPlot->getYield(YIELD_SCIENCE);
		cell.foreign_owned = pCellPlot->isOwned() && pCellPlot->getOwner() != pPlayer->GetID();
		cell.science_clear = pCellPlot->getResourceType() == NO_RESOURCE &&
			pCellPlot->getFeatureType() == NO_FEATURE && !pCellPlot->isHills() &&
			pCellPlot->getImprovementType() == NO_IMPROVEMENT;
	}
	return input;
}

static void ZeroSisEmitCitySiteTrace(unsigned int callId, int player, int turn, int cities,
	unsigned int requested, unsigned int count, unsigned int cells, const int best[4],
	unsigned long long hash, unsigned long long snapshotUs, unsigned long long workerUs,
	unsigned long long shadowUs, unsigned long long reductionUs, unsigned long long totalUs,
	const ZeroSisCitySiteMetrics& metrics)
{
	char tids[128] = {0}; unsigned int used = 0;
	for(unsigned int i = 0; i < metrics.worker_threads_used && i < 4; ++i) {
		const int n = std::snprintf(tids + used, sizeof(tids) - used, "%s%u:%u", i ? "," : "",
			metrics.worker_thread_ids[i], metrics.worker_job_counts[i]);
		if(n < 0 || static_cast<unsigned int>(n) >= sizeof(tids) - used) break; used += static_cast<unsigned int>(n);
	}
	std::printf("ZEROSIS_CITY_SITE_TRACE abi=%u config=%u status=%u call_id=%u player=%d turn=%d cities=%d mode=%s requested_workers=%u eligible_sites=%u input_cells=%u input_cells_scope=eligible_sites_times_tile_count_including_home_and_missing_plot_slots best_food=%d best_production=%d best_gold=%d best_science=%d ordered_output_fnv1a64=%016llx fnv_scope=plot_index_u32le_then_food_prod_gold_science_i32le_per_eligible_plot snapshot_us=%llu worker_us=%llu shadow_us=%llu reduction_us=%llu total_us=%llu jobs_total=%u jobs_started=%u jobs_completed=%u workers_started=%u used_threads=%u max_overlap=%u worker_tids_job_counts=%s\n",
		ZEROSIS_CITY_SITE_ABI_VERSION, ZEROSIS_CITY_SITE_CONFIG_VERSION, metrics.status, callId, player, turn, cities,
		requested == 0 ? "scalar-original" : "owned-worker", requested, count, cells,
		best[0], best[1], best[2], best[3], hash, snapshotUs, workerUs, shadowUs, reductionUs, totalUs,
		metrics.jobs_total, metrics.jobs_started, metrics.jobs_completed, metrics.workers_started,
		metrics.worker_threads_used, metrics.maximum_overlapping_jobs, tids);
	std::fflush(stdout);
}
'''


def record(path: Path) -> dict:
    return {"path": str(path), "sha256": digest(path), "size": path.stat().st_size}


def freeze_copy(source: Path, frozen_root: Path, name: str) -> tuple[Path, dict]:
    if not source.is_file():
        raise RuntimeError(f"Cannot freeze missing input: {source}")
    before = digest(source)
    target_dir = frozen_root / name
    target_dir.mkdir(parents=True, exist_ok=False)
    target = target_dir / source.name
    shutil.copyfile(source, target)
    frozen = digest(target)
    after = digest(source)
    if before != frozen or before != after:
        raise RuntimeError(f"Input changed while freezing: {source}")
    return target, {"original_path": str(source), "sha256_before": before,
                    "sha256_after": after, "artifact": record(target)}


def read_source_dependencies(path: Path) -> list[Path]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    includes = payload.get("Data", {}).get("Includes")
    if not isinstance(includes, list):
        raise RuntimeError(f"Unsupported /sourceDependencies schema: {path}")
    return [Path(value) for value in includes]


def replace_once(text: str, old: str, new: str, name: str) -> str:
    if text.count(old) != 1:
        raise RuntimeError(f"Expected unique anchor {name}, found {text.count(old)}")
    return text.replace(old, new, 1)


def prepare_source(source: bytes) -> bytes:
    text = source.decode("latin1")
    if "\r\n" not in text:
        raise RuntimeError("Expected CRLF source encoding/layout")
    text = replace_once(text, '#include "cvStopWatch.h"\r\n',
                        '#include "cvStopWatch.h"\r\n' + PATCH_HELPERS.replace("\n", "\r\n") + "\r\n",
                        "bridge helpers after cvStopWatch")
    start = "/// Find the best nearby city site for all yield types\r\nvoid CvCitySpecializationAI::FindBestSites()\r\n{"
    if text.count(start) != 1:
        raise RuntimeError("Unique FindBestSites anchor missing")
    begin = text.index(start)
    end = text.index("\r\n/// Evaluate strength of an existing city", begin)
    replacement = r'''/// Find the best nearby city site for all yield types
void CvCitySpecializationAI::FindBestSites()
{
	if(gDLL == NULL || !gDLL->IsGameCoreThread() || !gDLL->HasGameCoreLock()) throw std::logic_error("FindBestSites requires the game-core thread and lock");
	static unsigned int s_citySiteCallId = 0;
	const unsigned int callId = ++s_citySiteCallId;
	const unsigned long long totalStart = ZeroSisCitySiteNowUs();
	const unsigned int workers = ZeroSisCitySiteWorkerCount();
	int best[4] = {0, 0, 0, 0};
	if(workers == 0) for(int iI = 0; iI <= YIELD_SCIENCE; ++iI) m_iBestValue[iI] = 0;
	const int evalDistance = GC.getSETTLER_EVALUATION_DISTANCE() / 2;
	CvSiteEvaluatorForSettler* siteEval = GC.getGame().GetSettlerSiteEvaluator();
	unsigned int eligible = 0;
	unsigned int cellCount = 0;
	std::vector<ZeroSisCitySiteRecordedValue> recordedValues;
	unsigned long long orderedHash = 14695981039346656037ULL;
	unsigned long long snapshotUs = 0, workerUs = 0, shadowUs = 0, reductionUs = 0;
	ZeroSisCitySiteMetrics metrics = {};
	if(workers == 0)
	{
		for(int index = 0; index < GC.getMap().numPlots(); ++index)
		{
			CvPlot* plot = GC.getMap().plotByIndexUnchecked(index);
			if(siteEval->CanFound(plot, m_pPlayer, true))
			{
				CvCity* nearest = GC.getMap().findCity(plot->getX(), plot->getY(), m_pPlayer->GetID(), NO_TEAM, true /* bSameArea */);
				if(nearest != NULL && plotDistance(plot->getX(), plot->getY(), nearest->getX(), nearest->getY()) <= evalDistance)
				{
					int row[4];
					for(int y = 0; y < 4; ++y) row[y] = y == YIELD_SCIENCE ? PlotValueForScience(plot) : PlotValueForSpecificYield(plot, (YieldTypes)y);
					for(int y = 0; y < 4; ++y) if(row[y] > m_iBestValue[y]) m_iBestValue[y] = row[y];
					ZeroSisCitySiteHashRow(orderedHash, index, row);
					ZeroSisCitySiteRecordedValue recorded = {};
					recorded.plot_index = index;
					for(int y = 0; y < 4; ++y) recorded.values[y] = row[y];
					recordedValues.push_back(recorded);
					cellCount += static_cast<unsigned int>(GC.getAI_CITY_SPECIALIZATION_YIELD_NUM_TILES_CONSIDERED());
					++eligible;
				}
			}
		}
		for(int y = 0; y < 4; ++y) best[y] = m_iBestValue[y];
	}
	else
	{
		std::vector<int> indices;
		std::vector<ZeroSisCitySiteInput> inputs;
		std::vector<CvPlot*> plots;
		const unsigned long long snapshotStart = ZeroSisCitySiteNowUs();
		for(int index = 0; index < GC.getMap().numPlots(); ++index)
		{
			CvPlot* plot = GC.getMap().plotByIndexUnchecked(index);
			if(siteEval->CanFound(plot, m_pPlayer, true))
			{
				CvCity* nearest = GC.getMap().findCity(plot->getX(), plot->getY(), m_pPlayer->GetID(), NO_TEAM, true /* bSameArea */);
				if(nearest != NULL && plotDistance(plot->getX(), plot->getY(), nearest->getX(), nearest->getY()) <= evalDistance)
				{
					indices.push_back(index); plots.push_back(plot);
					inputs.push_back(ZeroSisCaptureCitySite(plot, m_pPlayer));
					cellCount += inputs.back().tile_count;
				}
			}
		}
		eligible = static_cast<unsigned int>(indices.size());
		snapshotUs = ZeroSisCitySiteNowUs() - snapshotStart;
		std::vector<ZeroSisCitySiteResult> outputs(eligible);
		const unsigned long long workerStart = ZeroSisCitySiteNowUs();
		const int bridgeStatus = ZeroSisEvaluateCitySites(inputs.empty() ? NULL : &inputs[0], eligible, workers,
			outputs.empty() ? NULL : &outputs[0], &metrics);
		workerUs = ZeroSisCitySiteNowUs() - workerStart;
		if(bridgeStatus != ZEROSIS_CITY_SITE_OK) throw std::runtime_error("City-site bridge failed; prior best values remain unchanged");
		const unsigned long long shadowStart = ZeroSisCitySiteNowUs();
		for(unsigned int i = 0; i < eligible; ++i)
		{
			int row[4];
			for(int y = 0; y < 4; ++y) row[y] = y == YIELD_SCIENCE ? PlotValueForScience(plots[i]) : PlotValueForSpecificYield(plots[i], (YieldTypes)y);
			for(int y = 0; y < 4; ++y) if(row[y] != outputs[i].values[y]) throw std::runtime_error("City-site scalar shadow mismatch; prior best values remain unchanged");
			ZeroSisCitySiteHashRow(orderedHash, indices[i], row);
			ZeroSisCitySiteRecordedValue recorded = {};
			recorded.plot_index = indices[i];
			for(int y = 0; y < 4; ++y) recorded.values[y] = row[y];
			recordedValues.push_back(recorded);
		}
		shadowUs = ZeroSisCitySiteNowUs() - shadowStart;
		const unsigned long long reductionStart = ZeroSisCitySiteNowUs();
		for(unsigned int i = 0; i < eligible; ++i)
			for(int y = 0; y < 4; ++y) if(outputs[i].values[y] > best[y]) best[y] = outputs[i].values[y];
		reductionUs = ZeroSisCitySiteNowUs() - reductionStart;
	}
	// Worker mode preserves the old array through capture, bridge, and scalar shadow;
	// this single commit is reached only after complete validation and ordered reduction.
	if(workers != 0) for(int y = 0; y < 4; ++y) m_iBestValue[y] = best[y];
	if(workers == 0) { metrics.abi_version = ZEROSIS_CITY_SITE_ABI_VERSION; metrics.config_version = ZEROSIS_CITY_SITE_CONFIG_VERSION; metrics.status = ZEROSIS_CITY_SITE_OK; }
	if(workers == 0) { metrics.jobs_total = eligible; metrics.jobs_started = eligible; metrics.jobs_completed = eligible; }
	else metrics.jobs_total = eligible;
	const unsigned long long totalUs = ZeroSisCitySiteNowUs() - totalStart;
	std::printf("ZEROSIS_CITY_SITE_VALUES call_id=%u records=", callId);
	if(recordedValues.empty()) std::printf("-");
	for(size_t i = 0; i < recordedValues.size(); ++i) {
		const ZeroSisCitySiteRecordedValue& row = recordedValues[i];
		std::printf("%s%d:%d,%d,%d,%d", i == 0 ? "" : ";", row.plot_index,
			row.values[0], row.values[1], row.values[2], row.values[3]);
	}
	std::printf("\n");
	ZeroSisEmitCitySiteTrace(callId, m_pPlayer->GetID(), GC.getGame().getGameTurn(), m_pPlayer->getNumCities(),
		workers, eligible, cellCount, best, orderedHash, snapshotUs, workerUs, shadowUs, reductionUs, totalUs, metrics);
	LogBestSites();
}
'''.replace("\n", "\r\n")
    text = text[:begin] + replacement + text[end:]
    return text.encode("latin1")


def frozen_ref(report: dict, original: str) -> Path:
    for row in report.get("frozen_inputs", []):
        if row.get("original_path", "").lower() == original.lower():
            ref = row["artifact"]
            path = Path(ref["path"])
            if not path.is_file() or digest(path) != ref["sha256"]:
                raise RuntimeError(f"Frozen input changed: {path}")
            return path
    raise RuntimeError(f"Frozen input not recorded: {original}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prepare-only", action="store_true", help="Do not invoke compiler/linker")
    args = parser.parse_args()
    report_bytes = BASE_REPORT_PATH.read_bytes()
    base = json.loads(report_bytes.decode("utf-8"))
    if base.get("status") != "EXPLORE_SDK_CANDIDATE_LINKED" or base.get("build_id") != BASE_ID:
        raise RuntimeError("Immutable Explore SDK candidate identity/status mismatch")
    base_report_path = frozen_ref(base, str(PROJECT / "evidence/save_restore_sdk/build_result.json"))
    accepted_result_path = frozen_ref(base, str(PROJECT / "evidence/sdk_x64/attempts/attempt_037/build_result.json"))
    base_report_input_row = next((row for row in base.get("frozen_inputs", [])
                                  if row.get("original_path", "").lower() == str(PROJECT / "evidence/save_restore_sdk/build_result.json").lower()), None)
    accepted_input_row = next((row for row in base.get("frozen_inputs", [])
                               if row.get("original_path", "").lower() == str(PROJECT / "evidence/sdk_x64/attempts/attempt_037/build_result.json").lower()), None)
    if base_report_input_row is None or digest(base_report_path) != base_report_input_row["artifact"]["sha256"]:
        raise RuntimeError("Frozen SaveRestore report does not match its Explore manifest entry")
    if accepted_input_row is None or digest(accepted_result_path) != accepted_input_row["artifact"]["sha256"]:
        raise RuntimeError("Frozen accepted result does not match its Explore manifest entry")
    frozen = json.loads(base_report_path.read_text(encoding="utf-8"))
    accepted = json.loads(accepted_result_path.read_text(encoding="utf-8"))
    if frozen.get("build_id") != base.get("base_save_restore_build_id"):
        raise RuntimeError("Explore candidate frozen SaveRestore report chain mismatch")
    if accepted.get("status") != "SDK_X64_ALL_OBJECTS_COMPILED" or accepted.get("attempt") != 37:
        raise RuntimeError("Explore candidate is not based on accepted attempt 037")
    manifest_path = frozen_ref(base, str(PROJECT / "evidence/sdk_x64/port_manifest.json"))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    sdk_manifest_row = next((row for row in manifest if row.get("relative_path") ==
                       "CvGameCoreDLL_Expansion2/CvCitySpecializationAI.cpp"), None)
    if sdk_manifest_row is None or Path(sdk_manifest_row.get("port", "")).resolve() != SDK_SOURCE.resolve():
        raise RuntimeError("Accepted port manifest does not identify the current CitySpecialization SDK source")
    if digest(SDK_SOURCE) != sdk_manifest_row.get("port_sha256"):
        raise RuntimeError("Current CitySpecialization source differs from accepted attempt_037 manifest")
    base_link = Path(base["link_response"]["path"])
    if digest(base_link) != base["link_response"]["sha256"]:
        raise RuntimeError("Explore candidate link recipe changed")
    gamecore_rsp = frozen_ref(base, r"C:\Users\home\OneDrive\Documents\Firaxis ModBuddy\ZeroSis' Engine Modernization\evidence\sdk_x64\attempts\attempt_037\gamecore.rsp")
    pch = frozen_ref(base, r"C:\Users\home\OneDrive\Documents\Firaxis ModBuddy\ZeroSis' Engine Modernization\Build\SDK_x64\attempt_037\GameCore_x64.pch")
    old_object_row = next((r for r in accepted.get("objects", []) if Path(r.get("path", "")).name == "CvCitySpecializationAI.obj"), None)
    if not old_object_row:
        raise RuntimeError("Accepted object inventory lacks CvCitySpecializationAI.obj")
    old_obj = Path(old_object_row["path"])
    if not old_obj.is_file() or digest(old_obj) != old_object_row["sha256"]:
        raise RuntimeError("Accepted CvCitySpecializationAI object changed")
    required = [SDK_SOURCE, CITY_HEADER, CITY_SOURCE, TRACE_HEADER, TRACE_SOURCE, TRACE_ETW_LIBRARY,
                KERNEL, BATCH, Path(__file__).resolve()]
    for path in required:
        if not path.is_file(): raise RuntimeError(f"Missing candidate input: {path}")

    build_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ_") + uuid.uuid4().hex[:12]
    build_dir = PROJECT / "Build/CitySiteSDK" / build_id
    evidence_dir = PROJECT / "evidence/city_site_sdk" / build_id
    build_dir.mkdir(parents=True, exist_ok=False); evidence_dir.mkdir(parents=True, exist_ok=False)
    frozen_dir = evidence_dir / "frozen"; frozen_dir.mkdir()
    frozen_inputs = []
    frozen_builder, frozen_row = freeze_copy(Path(__file__).resolve(), frozen_dir, "builder")
    frozen_inputs.append(frozen_row)
    frozen_tools = {}
    for name, path in (("native_build", PROJECT / "tools/native_build.py"),
                       ("collect_baseline", PROJECT / "tools/collect_baseline.py")):
        frozen_tools[name], frozen_row = freeze_copy(path, frozen_dir, name)
        frozen_inputs.append(frozen_row)
    frozen_sdk, frozen_row = freeze_copy(SDK_SOURCE, frozen_dir, "sdk_source")
    frozen_inputs.append(frozen_row)
    frozen_city_header, frozen_row = freeze_copy(CITY_HEADER, frozen_dir, "city_site_bridge_header")
    frozen_inputs.append(frozen_row)
    frozen_city_source, frozen_row = freeze_copy(CITY_SOURCE, frozen_dir, "city_site_bridge_source")
    frozen_inputs.append(frozen_row)
    frozen_trace_header, frozen_row = freeze_copy(TRACE_HEADER, frozen_dir, "city_site_trace_header")
    frozen_inputs.append(frozen_row)
    frozen_trace_source, frozen_row = freeze_copy(TRACE_SOURCE, frozen_dir, "city_site_trace_source")
    frozen_inputs.append(frozen_row)
    frozen_etw_library, frozen_row = freeze_copy(TRACE_ETW_LIBRARY, frozen_dir, "city_site_trace_etw_library")
    frozen_inputs.append(frozen_row)
    frozen_kernel, frozen_row = freeze_copy(KERNEL, frozen_dir, "city_site_kernel")
    frozen_inputs.append(frozen_row)
    frozen_batch, frozen_row = freeze_copy(BATCH, frozen_dir, "ordered_batch")
    frozen_inputs.append(frozen_row)
    frozen_gamecore_rsp, frozen_row = freeze_copy(gamecore_rsp, frozen_dir, "accepted_gamecore_recipe")
    frozen_inputs.append(frozen_row)
    frozen_base_link, frozen_row = freeze_copy(base_link, frozen_dir, "base_explore_link_recipe")
    frozen_inputs.append(frozen_row)
    # This TU does not consume the historical PCH; retain its immutable base
    # artifact identity without making another 123 MiB copy for each candidate.
    frozen_pch = pch
    pch_reference_sha256 = digest(frozen_pch)
    pch_original = Path(next(row["original_path"] for row in base["frozen_inputs"]
                             if row["artifact"]["path"] == str(pch)))
    if not pch_original.is_file() or digest(pch_original) != digest(frozen_pch):
        raise RuntimeError("Compiler PCH path does not match the frozen accepted PCH")
    frozen_manifest, frozen_row = freeze_copy(manifest_path, frozen_dir, "accepted_manifest")
    frozen_inputs.append(frozen_row)
    frozen_base_report, frozen_row = freeze_copy(BASE_REPORT_PATH, frozen_dir, "explore_candidate_report")
    frozen_inputs.append(frozen_row)
    if digest(frozen_base_report) != hashlib.sha256(report_bytes).hexdigest():
        raise RuntimeError("Explore report changed after initial identity read")
    frozen_ancestor_report, frozen_row = freeze_copy(base_report_path, frozen_dir, "save_restore_ancestor_report")
    frozen_inputs.append(frozen_row)
    frozen_accepted_result, frozen_row = freeze_copy(accepted_result_path, frozen_dir, "accepted_sdk_result")
    frozen_inputs.append(frozen_row)
    base_gamecore = Path(base["gamecore"]["path"])
    frozen_base_gamecore, frozen_row = freeze_copy(base_gamecore, frozen_dir, "base_explore_gamecore")
    frozen_inputs.append(frozen_row)
    if digest(frozen_base_gamecore) != base["gamecore"]["sha256"]:
        raise RuntimeError("Frozen Explore candidate DLL differs from immutable report")
    source_dir = build_dir / "Source/CvGameCoreDLL_Expansion2"; source_dir.mkdir(parents=True)
    include_dir = build_dir / "Source/Concurrency"; include_dir.mkdir()
    diagnostic_dir = build_dir / "Source/Diagnostics"; diagnostic_dir.mkdir()
    candidate_source = source_dir / "CvCitySpecializationAI.cpp"
    candidate_source.write_bytes(prepare_source(frozen_sdk.read_bytes()))
    city_bridge = include_dir / "CitySiteScoreBridge.cpp"; shutil.copyfile(frozen_city_source, city_bridge)
    city_trace = diagnostic_dir / "CitySiteCpuTrace.cpp"; shutil.copyfile(frozen_trace_source, city_trace)
    shutil.copyfile(frozen_trace_header, diagnostic_dir / "CitySiteCpuTrace.h")
    for path in (frozen_city_header, frozen_kernel, frozen_batch): shutil.copyfile(path, include_dir / path.name)

    compile_flags = [line for line in frozen_gamecore_rsp.read_text(encoding="utf-8").splitlines()
                     if not line.startswith('"') and not line.startswith("/Fo") and line != "/MP4"]
    if "/std:c++14" not in compile_flags or not any(line.startswith("/Yu") for line in compile_flags):
        raise RuntimeError("Frozen accepted gamecore C++14/PCH recipe invalid")
    # Original SDK bytes include Windows-1252 copyright comments. Specify the
    # source decoder instead of interpreting those bytes as the local CP949.
    compile_flags.append('/source-charset:.1252')
    pch_options = [index for index, line in enumerate(compile_flags) if re.match(r"(?i)^/fp(?:\"| )", line)]
    if len(pch_options) != 1: raise RuntimeError("Accepted compile recipe must have one PCH output/input option")
    # The historical PCH used the implicit local source charset. C2855 forbids
    # reusing it with an explicit decoder. Compile this one replacement TU
    # without PCH; all other accepted/base objects remain untouched.
    compile_flags = [line for line in compile_flags
                     if not line.lower().startswith('/yu') and not re.match(r"(?i)^/fp(?:\"| )", line)]
    city_obj = build_dir / "CvCitySpecializationAI.obj"; bridge_obj = build_dir / "CitySiteScoreBridge.obj"
    trace_obj = build_dir / "CitySiteCpuTrace.obj"
    city_rsp = build_dir / "CvCitySpecializationAI.rsp"
    city_dependencies = build_dir / "CvCitySpecializationAI.dependencies.json"
    city_rsp.write_text("\n".join(compile_flags + [f'/I"{include_dir}"', f'/Fo"{city_obj}"',
        f'/sourceDependencies "{city_dependencies}"', f'"{candidate_source}"']) + "\n", encoding="utf-8")
    baseline_obj = build_dir / "CvCitySpecializationAI.baseline.obj"
    baseline_rsp = build_dir / "CvCitySpecializationAI.baseline.rsp"
    baseline_dependencies = build_dir / "CvCitySpecializationAI.baseline.dependencies.json"
    baseline_rsp.write_text("\n".join(compile_flags + [f'/I"{include_dir}"', f'/Fo"{baseline_obj}"',
        f'/sourceDependencies "{baseline_dependencies}"', f'"{frozen_sdk}"']) + "\n", encoding="utf-8")
    bridge_rsp = build_dir / "CitySiteScoreBridge.rsp"
    bridge_dependencies = build_dir / "CitySiteScoreBridge.dependencies.json"
    bridge_rsp.write_text("\n".join(["/nologo", "/c", "/std:c++17", "/EHsc", "/MD", "/O2", "/W4", "/WX",
        f'/I"{include_dir}"', f'/Fo"{bridge_obj}"', f'/sourceDependencies "{bridge_dependencies}"',
        f'"{city_bridge}"']) + "\n", encoding="utf-8")
    trace_rsp = build_dir / "CitySiteCpuTrace.rsp"
    trace_dependencies = build_dir / "CitySiteCpuTrace.dependencies.json"
    trace_rsp.write_text("\n".join(["/nologo", "/c", "/std:c++14", "/EHsc", "/MD", "/O2", "/W4", "/WX",
        "/DWIN32_LEAN_AND_MEAN", "/DNOMINMAX", "/D_WIN32_WINNT=0x0A00", "/fp:strict", "/utf-8",
        f'/Fo"{trace_obj}"', f'/sourceDependencies "{trace_dependencies}"', f'"{city_trace}"']) + "\n", encoding="utf-8")

    link_text = frozen_base_link.read_text(encoding="utf-8")
    def_match = re.search(r'^/DEF:"([^"]+)"$', link_text, re.M | re.I)
    if not def_match: raise RuntimeError("Explore link response lacks a quoted module definition")
    def_source = Path(def_match.group(1))
    frozen_def, frozen_row = freeze_copy(def_source, frozen_dir, "module_definition")
    frozen_inputs.append(frozen_row)
    link_text = link_text.replace(def_match.group(0), f'/DEF:"{frozen_def}"', 1)
    base_link_text = link_text
    base_link_paths = re.findall(r'^"([^"\r\n]+\.obj|[^"\r\n]+\.lib)"$', base_link_text, re.M | re.I)
    link_inputs_before = []
    for value in base_link_paths:
        path = Path(value)
        if not path.is_file(): raise RuntimeError(f"Base Explore link input missing: {path}")
        link_inputs_before.append({"path": str(path), "sha256": digest(path), "size": path.stat().st_size})
    quoted_old = '"' + str(old_obj) + '"'
    if link_text.count(quoted_old) != 1: raise RuntimeError("Explore link response does not contain old city object exactly once")
    link_text = link_text.replace(quoted_old, '"' + str(city_obj) + '"', 1)
    link_text = link_text.replace('"' + str(city_obj) + '"',
                                  '"' + str(city_obj) + '"\n"' + str(bridge_obj) + '"\n"' + str(trace_obj) + '"', 1)
    # The optional TraceLogging provider uses only the Windows ETW API.
    link_text += '\n"' + str(frozen_etw_library) + '"\n'
    candidate_dll = build_dir / "CvGameCoreDLL_Expansion2_x64.dll"
    for option, target in (("OUT", candidate_dll), ("IMPLIB", candidate_dll.with_suffix(".lib")), ("MAP", build_dir / "CvGameCoreDLL_Expansion2_x64.map")):
        link_text, n = re.subn(r"^/" + option + r":[^\r\n]+", lambda _: f'/{option}:"{target}"', link_text, flags=re.M)
        if n != 1: raise RuntimeError(f"Non-unique link output option {option}")
    link_rsp = build_dir / "link.rsp"; link_rsp.write_text(link_text, encoding="utf-8")
    status = "CITY_SITE_SDK_CANDIDATE_PREPARED_NOT_BUILT"
    records = None
    if not args.prepare_only:
        environment, compiler_name = environment_for(VS, "x64", build_dir)
        compiler = Path(compiler_name); environment["VSLANG"] = "1033"
        executions = []
        baseline_warnings = None
        for name, response, obj in (("CvCitySpecializationAI_baseline", baseline_rsp, baseline_obj),
                                    ("CvCitySpecializationAI", city_rsp, city_obj),
                                    ("CitySiteScoreBridge", bridge_rsp, bridge_obj),
                                    ("CitySiteCpuTrace", trace_rsp, trace_obj)):
            compiler_hash_before = digest(compiler)
            result = run([compiler, "@" + str(response)], cwd=build_dir, env=environment, timeout=180)
            compiler_hash_after = digest(compiler)
            if compiler_hash_before != compiler_hash_after:
                raise RuntimeError("Compiler binary changed during compilation")
            log = evidence_dir / f"{name}_compile.log"; log.write_bytes(result.stdout + result.stderr)
            if result.returncode or not obj.is_file(): raise RuntimeError(f"Compile failed for {name}: {log}")
            warning_count = len(re.findall(rb"\bwarning\s+(?:C|LNK)\d+\b", result.stdout + result.stderr, re.I))
            warnings = [line.decode('mbcs', errors='replace').strip()
                        for line in (result.stdout + result.stderr).splitlines()
                        if re.search(rb'\bwarning\s+(?:C|LNK)\d+\b', line, re.I)]
            if name == 'CvCitySpecializationAI_baseline':
                baseline_warnings = warnings
            elif name == 'CvCitySpecializationAI':
                if warnings != baseline_warnings:
                    raise RuntimeError(f"SDK candidate changed the exact baseline warning list: {log}")
            elif warning_count:
                raise RuntimeError(f"Worker bridge emitted {warning_count} warning(s): {log}")
            executions.append({"name": name, "object": record(obj), "response": record(response), "log": record(log),
                               "warning_count": warning_count, "warnings": warnings,
                               "warnings_exactly_match_baseline": name == 'CvCitySpecializationAI' and warnings == baseline_warnings,
                               "compiler_sha256_before": compiler_hash_before,
                               "compiler_sha256_after": compiler_hash_after})
        linker = compiler.with_name("link.exe"); linker_hash_before = digest(linker)
        linked = run([linker, "@" + str(link_rsp)], cwd=build_dir, env=environment, timeout=180)
        linker_hash_after = digest(linker)
        if linker_hash_before != linker_hash_after:
            raise RuntimeError("Linker binary changed during linking")
        link_log = evidence_dir / "link.log"; link_log.write_bytes(linked.stdout + linked.stderr)
        link_warning_count = len(re.findall(rb"\bwarning\s+LNK\d+\b", linked.stdout + linked.stderr, re.I))
        if link_warning_count: raise RuntimeError(f"Linker emitted {link_warning_count} warning(s): {link_log}")
        candidate_map = build_dir / "CvGameCoreDLL_Expansion2_x64.map"
        if linked.returncode or not candidate_dll.is_file() or not candidate_map.is_file(): raise RuntimeError("CitySite candidate link/map failed")
        dumpbin = compiler.with_name("dumpbin.exe"); dumpbin_hash_before = digest(dumpbin)
        inspected = run([dumpbin, "/dependents", str(candidate_dll)], cwd=build_dir, env=environment, timeout=60)
        dumpbin_hash_after = digest(dumpbin)
        if dumpbin_hash_before != dumpbin_hash_after: raise RuntimeError("dumpbin binary changed during PE/import inspection")
        imports_log = evidence_dir / "imports.log"; imports_log.write_bytes(inspected.stdout + inspected.stderr)
        imports = [value.decode("ascii", errors="replace") for value in re.findall(
            rb"^\s+([\w.-]+\.dll)\s*$", inspected.stdout + inspected.stderr, re.M | re.I)]
        if inspected.returncode or "ZeroSisLua51_x64.dll" not in imports or "ZeroSisDatabase_x64.dll" not in imports:
            raise RuntimeError("Candidate lost required shared Lua/Database imports")
        pe = pe_header(candidate_dll)
        if pe.get("architecture") != "x64" or not pe.get("is_dll"):
            raise RuntimeError("Candidate output is not an x64 DLL")
        status = "CITY_SITE_SDK_CANDIDATE_LINKED"
        records = {"executions": executions, "gamecore": record(candidate_dll), "map": record(candidate_map),
                   "link_response": record(link_rsp), "link_log": record(link_log), "imports": imports,
                   "link_warning_count": link_warning_count,
                   "imports_log": record(imports_log), "pe": pe, "compiler": record(compiler),
                   "compiler_sha256_after": digest(compiler), "linker": record(linker),
                   "linker_sha256_before": linker_hash_before, "linker_sha256_after": linker_hash_after,
                   "dumpbin": record(dumpbin), "dumpbin_sha256_before": dumpbin_hash_before,
                   "dumpbin_sha256_after": dumpbin_hash_after}

    compiler_dependency_inputs = []
    dependency_reports = []
    for dep_path in (baseline_dependencies, city_dependencies, bridge_dependencies, trace_dependencies):
        if not dep_path.is_file():
            if not args.prepare_only: raise RuntimeError(f"Compiler did not write /sourceDependencies output: {dep_path}")
            continue
        dep_files = read_source_dependencies(dep_path)
        dep_data = json.loads(dep_path.read_text(encoding="utf-8"))["Data"]
        source_path = Path(dep_data["Source"])
        all_paths = list(dict.fromkeys([source_path] + dep_files))
        rows = []
        for path in all_paths:
            if not path.is_file(): raise RuntimeError(f"Actual compiler dependency missing: {path}")
            after_compile_hash = digest(path)
            row = {"path": str(path), "sha256_after_compile": after_compile_hash}
            rows.append(row); compiler_dependency_inputs.append(row)
        dependency_reports.append({"report": record(dep_path), "source": str(source_path),
                                   "includes_count": len(dep_files), "inputs": rows})

    linked_paths = re.findall(r'^"([^"\r\n]+\.obj|[^"\r\n]+\.lib)"$', link_text, re.M | re.I)
    link_input_hashes = []
    for p in linked_paths:
        path = Path(p)
        if path in (city_obj, bridge_obj, trace_obj): link_input_hashes.append({"path": str(path), "sha256": digest(path) if path.exists() else None, "new_candidate_object": True})
        elif path == frozen_etw_library:
            link_input_hashes.append({"path": str(path), "sha256": digest(path), "new_etw_import_library": True})
        else:
            if not path.is_file(): raise RuntimeError(f"Base link input missing: {path}")
            link_input_hashes.append({"path": str(path), "sha256": digest(path), "reused": True})
    normalize = lambda value: os.path.normcase(os.path.abspath(str(value)))
    before_by_path = {normalize(row["path"]): row for row in link_inputs_before}
    after_by_path = {normalize(row["path"]): row for row in link_input_hashes}
    old_key = normalize(old_obj)
    if old_key not in before_by_path or old_key in after_by_path:
        raise RuntimeError("Candidate link did not replace exactly the accepted city-specialization object")
    expected_after = (set(before_by_path) - {old_key}) | {normalize(city_obj), normalize(bridge_obj), normalize(trace_obj), normalize(frozen_etw_library)}
    if set(after_by_path) != expected_after:
        raise RuntimeError("Candidate link object/library set differs beyond the intended TU replacement and bridge")
    for key in set(before_by_path) - {old_key}:
        if before_by_path[key]["sha256"] != after_by_path[key]["sha256"]:
            raise RuntimeError("Reused base object/library hash changed: " + before_by_path[key]["path"])
    for row in frozen_inputs:
        original = Path(row["original_path"])
        if not original.is_file() or digest(original) != row["sha256_before"]:
            raise RuntimeError(f"Frozen input changed after preparation/build: {original}")
    if digest(frozen_pch) != pch_reference_sha256:
        raise RuntimeError('The retained unused PCH reference changed during the candidate build')
    for row in compiler_dependency_inputs:
        after_link_hash = digest(Path(row["path"]))
        if after_link_hash != row["sha256_after_compile"]:
            raise RuntimeError("Actual sourceDependencies input changed after compilation: " + row["path"])
        row["sha256_after_link"] = after_link_hash
    report = {"status": status, "build_id": build_id, "base_explore_build_id": BASE_ID,
        "base_explore_build": record(frozen_base_gamecore),
        "base_explore_build_original": record(base_gamecore),
        "base_explore_report": record(BASE_REPORT_PATH), "base_explore_build_report": record(frozen_base_report),
        "frozen_base_report": record(frozen_ancestor_report),
        "frozen_accepted_result": record(frozen_accepted_result), "accepted_attempt": 37,
        "accepted_manifest": record(frozen_manifest), "accepted_source_sha256": sdk_manifest_row["port_sha256"],
        "candidate_source": record(candidate_source), "sdk_source": {"path": str(SDK_SOURCE),
            "accepted_manifest_sha256": sdk_manifest_row["port_sha256"], "verified_current_sha256": digest(SDK_SOURCE),
            "frozen_source": record(frozen_sdk)},
        "builder": record(frozen_builder), "builder_original": record(Path(__file__).resolve()),
        "frozen_inputs": frozen_inputs,
        "frozen_tools": {name: record(path) for name, path in frozen_tools.items()},
        "input_sources": {"city_site_bridge_header": record(frozen_city_header), "city_site_bridge_source": record(frozen_city_source),
                          "city_site_kernel": record(frozen_kernel), "ordered_batch": record(frozen_batch),
                          "city_site_trace_header": record(frozen_trace_header), "city_site_trace_source": record(frozen_trace_source)},
        "bridge_source": record(city_bridge), "bridge_header": record(include_dir / CITY_HEADER.name),
        "kernel": record(include_dir / KERNEL.name), "ordered_batch": record(include_dir / BATCH.name),
        "cpu_trace_source": record(city_trace), "cpu_trace_header": record(diagnostic_dir / TRACE_HEADER.name),
        "cpu_trace_etw_import_library": record(frozen_etw_library),
        "pch_reference_not_consumed": record(frozen_pch), "pch_reused": False,
        "source_charset": "Windows-1252 explicitly decoded with /source-charset:.1252",
        "gamecore_compile_recipe": record(frozen_gamecore_rsp),
        "compile_responses": {"city_sdk_cxx14_without_pch": record(city_rsp),
                              "unmodified_sdk_baseline_cxx14": record(baseline_rsp), "bridge_cxx17": record(bridge_rsp),
                              "cpu_trace_cxx14": record(trace_rsp)},
        "warning_policy": "Replacement SDK TU must exactly match warnings from an unmodified frozen SDK TU compiled with identical options; bridge and linker must emit zero warnings. SDK header warnings are retained verbatim, never suppressed.",
        "unmodified_baseline_object_linked": False,
        "link_response": record(link_rsp), "link_inputs_before": link_inputs_before, "link_inputs_after": link_input_hashes,
        "replaced_object": {"old": old_object_row, "new": str(city_obj)}, "added_object": str(bridge_obj),
        "added_objects": [str(bridge_obj), str(trace_obj)],
        "module_definition": record(frozen_def), "source_dependency_reports": dependency_reports,
        "source_dependency_inputs": compiler_dependency_inputs,
        "source_dependency_scope": "Exact /sourceDependencies Source plus Includes paths discovered by each final TU compile; each is hashed after compile and after link and equality checked. Direct candidate sources, SDK source, custom headers, builder, helper Python files, recipes, manifest, base DLL and module definition are frozen and pre/post checked before compilation. Historical PCH is an existing immutable reference and is not consumed or copied. System headers are not frozen before compile; compiler and linker tools are hashed, while linker helper DLLs and OS environment are not frozen.",
        "compiler_dependency_precompile_snapshot_complete": False,
        "active_sdk_updated": False,
        "stage_updated": False, "gamecore_loaded": False, "runtime_trace_prefix": "ZEROSIS_CITY_SITE_TRACE",
        "ordered_output_hash": "FNV-1a64 over explicit little-endian plot-index u32 then FOOD/PRODUCTION/GOLD/SCIENCE i32 per eligible plot; excludes struct padding",
        "ordered_values_trace": "ZEROSIS_CITY_SITE_VALUES records=plotIndex:food,production,gold,science;... emitted immediately before call summary for literal per-site comparison",
        "trace_io_in_timed_total": False, "trace_is_diagnostic_and_can_affect_runtime_timing": True,
        "cpu_trace_opt_in_environment": "ZEROSIS_CITY_SITE_CPU_TRACE=1",
        "cpu_trace_default_enabled": False, "cpu_trace_provider_guid": "2d76305f-91f4-4d48-9b32-281507669f73",
        "cpu_trace_scope": "Per-job scoring QPC intervals with separate opt-in TraceLogging markers; no barriers, synthetic work, persistent workers or CPU-affinity changes",
        "build_records": records, "gamecore": records["gamecore"] if records else {"path": str(candidate_dll), "built": False}}
    report_path = evidence_dir / "build_result.json"; report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": status, "build_id": build_id, "build_dir": str(build_dir), "evidence": str(report_path)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
