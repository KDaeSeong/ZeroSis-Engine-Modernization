// Included only in an isolated CvSiteEvaluationClasses.cpp candidate.
// The game thread owns all SDK reads and all ordered map/area writes.
#include "FoundValueScoreBridge.h"
#include <Windows.h>
#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <limits>
#include <stdexcept>
#include <typeinfo>
#include <vector>

unsigned long long ZeroSisFoundValueNowUs()
{
    return static_cast<unsigned long long>(std::chrono::duration_cast<std::chrono::microseconds>(
        std::chrono::steady_clock::now().time_since_epoch()).count());
}

unsigned int ZeroSisFoundValueWorkerCount()
{
    const char* value = std::getenv("ZEROSIS_FOUND_VALUE_WORKERS");
    if(value == NULL || value[0] == '\0' || std::strcmp(value, "0") == 0) return 0;
    if(std::strcmp(value, "1") == 0) return 1;
    if(std::strcmp(value, "2") == 0) return 2;
    if(std::strcmp(value, "4") == 0) return 4;
    throw std::runtime_error("ZEROSIS_FOUND_VALUE_WORKERS must be 0, 1, 2, or 4");
}

bool ZeroSisFoundValueTraceEnabled()
{
    const char* value = std::getenv("ZEROSIS_FOUND_VALUE_TRACE");
    return value != NULL && std::strcmp(value, "1") == 0;
}

void ZeroSisTraceFoundValues(CvPlayer* player, const int* orderedValues, bool startingLocation, unsigned int callId,
    unsigned int workers, unsigned int helperPlots, unsigned long long snapshotUs,
    unsigned long long workerUs, unsigned long long shadowUs, unsigned long long reductionUs,
    unsigned long long totalUs, const ZeroSisFoundValueMetrics* metrics)
{
    if(!ZeroSisFoundValueTraceEnabled()) return;
    if(gDLL == NULL || !gDLL->IsGameCoreThread() || !gDLL->HasGameCoreLock())
        throw std::logic_error("Found-value diagnostics require the game-core thread and lock");
    const int plots = GC.getMap().numPlots();
    if(plots > 0 && orderedValues == NULL) throw std::logic_error("Found-value diagnostics lack their non-mutating ordered observation");
    unsigned int revealed = 0;
    std::printf("ZEROSIS_FOUND_VALUE_VALUES call_id=%u records=", callId);
    for(int i = 0; i < plots; ++i) {
        CvPlot* plot = GC.getMap().plotByIndexUnchecked(i);
        if(plot->isRevealed(player->getTeam())) ++revealed;
        // getFoundValue() lazily recomputes -1 entries, so it must never be used
        // for diagnostics. These values come directly from the caller's writes.
        std::printf("%s%d:%d", i == 0 ? "" : ";", i, orderedValues[i]);
    }
    if(plots == 0) std::printf("-");
    std::printf("\nZEROSIS_FOUND_VALUE_AREAS call_id=%u records=", callId);
    int loop = 0;
    bool first = true;
    for(CvArea* area = GC.getMap().firstArea(&loop); area != NULL; area = GC.getMap().nextArea(&loop)) {
        std::printf("%s%d:%d", first ? "" : ";", area->GetID(), area->getTotalFoundValue());
        first = false;
    }
    if(first) std::printf("-");
    const ZeroSisFoundValueMetrics empty = {};
    const ZeroSisFoundValueMetrics& m = metrics != NULL ? *metrics : empty;
    std::printf("\nZEROSIS_FOUND_VALUE_TRACE version=1 call_id=%u turn=%d player=%d starting_loc=%u "
        "mode=%s requested_workers=%u map_plots=%d revealed=%u helper_unique_plots=%u "
        "snapshot_us=%llu worker_us=%llu shadow_us=%llu reduction_us=%llu total_us=%llu "
        "jobs_total=%u jobs_started=%u jobs_completed=%u workers_started=%u used_threads=%u "
        "max_overlap=%u worker_tids_job_counts=",
        callId, GC.getGame().getGameTurn(), player->GetID(), startingLocation ? 1u : 0u,
        workers == 0 ? "scalar-original" : "owned-worker", workers, plots, revealed, helperPlots,
        snapshotUs, workerUs, shadowUs, reductionUs, totalUs, m.jobs_total, m.jobs_started,
        m.jobs_completed, m.workers_started, m.worker_threads_used, m.maximum_overlapping_jobs);
    first = true;
    for(unsigned int i = 0; i < ZEROSIS_FOUND_VALUE_WORKER_SLOTS; ++i) {
        if(m.worker_job_counts[i] == 0) continue;
        std::printf("%s%u:%u", first ? "" : ",", m.worker_thread_ids[i], m.worker_job_counts[i]);
        first = false;
    }
    if(first) std::printf("-");
    std::printf("\n");
    std::fflush(stdout);
}

static bool ZeroSisFoundValueSpecificCivilization(CvPlayer* player, const char* name)
{
    const ImprovementTypes improvement = static_cast<ImprovementTypes>(GC.getInfoTypeForString(name, true));
    if(improvement == NO_IMPROVEMENT) return false;
    CvImprovementEntry* entry = GC.getImprovementInfo(improvement);
    return entry != NULL && entry->IsSpecificCivRequired() &&
        entry->GetRequiredCivilization() == player->getCivilizationType();
}

struct ZeroSisFoundValueHelperCache
{
    ZeroSisFoundValueTile tile;
    unsigned int ready;
    unsigned int strategicReady;
    int strategic[8];
    ZeroSisFoundValueHelperCache() : tile(), ready(0), strategicReady(0), strategic() {}
};

bool CvSiteEvaluatorForSettler::ZeroSisOwnedFoundValues(CvPlayer* player, unsigned int workers,
    unsigned int callId, unsigned long long totalStart)
{
    if(gDLL == NULL || !gDLL->IsGameCoreThread() || !gDLL->HasGameCoreLock())
        throw std::logic_error("Owned found-value capture requires the game-core thread and lock");
    // Unknown subclasses retain their original virtual path. No class layout or
    // virtual method is added to the candidate header.
    if(player == NULL || typeid(*this) != typeid(CvSiteEvaluatorForSettler)) return false;
    if(NUM_CITY_RINGS != 3 || GC.getMIN_CITY_RANGE() < 0 || GC.getMIN_CITY_RANGE() >= 8) return false;
    const int plots = GC.getMap().numPlots();
    if(plots < 0 || workers == 0 || workers > ZEROSIS_FOUND_VALUE_WORKER_SLOTS) return false;
    ComputeFlavorMultipliers(player);
    const TeamTypes team = player->getTeam();
    const PlayerTypes owner = player->GetID();
    const unsigned long long snapshotStart = ZeroSisFoundValueNowUs();
    ZeroSisFoundValueInput common = {};
    common.abi_version = ZEROSIS_FOUND_VALUE_ABI_VERSION;
    common.config_version = ZEROSIS_FOUND_VALUE_CONFIG_VERSION;
    common.path = ZEROSIS_FOUND_VALUE_PATH_SETTLER_NO_YIELD_NO_COAST_ONLY;
    common.valid = 1;
    common.has_player = 1;
    common.center_present = 1;
    CvCity* capital = player->getCapitalCity();
    common.capital_present = capital != NULL;
    common.capital_area = capital != NULL ? capital->getArea() : 0;
    common.naval_flavor = player->GetGrandStrategyAI()->GetPersonalityAndGrandStrategy(static_cast<FlavorTypes>(m_iNavalIndex));
    common.growth_flavor = player->GetGrandStrategyAI()->GetPersonalityAndGrandStrategy(static_cast<FlavorTypes>(m_iGrowthIndex));
    common.expansion_flavor = player->GetGrandStrategyAI()->GetPersonalityAndGrandStrategy(static_cast<FlavorTypes>(m_iExpansionIndex));
    common.boldness = player->GetDiplomacyAI()->GetBoldness();
    common.coastal_civilization = player->getCivilizationInfo().isCoastalCiv();
    common.human_player = player->isHuman();
    common.faith_from_unimproved_forest = player->GetPlayerTraits()->IsFaithFromUnimprovedForest();
    common.move_friendly_woods_as_road = player->GetPlayerTraits()->IsMoveFriendlyWoodsAsRoad();
    common.gets_natural_wonder_yield_modifier = player->GetPlayerTraits()->GetNaturalWonderYieldModifier() > 0;
    common.is_inca = ZeroSisFoundValueSpecificCivilization(player, "IMPROVEMENT_TERRACE_FARM");
    common.is_brazil = ZeroSisFoundValueSpecificCivilization(player, "IMPROVEMENT_BRAZILWOOD_CAMP");
    common.is_morocco = ZeroSisFoundValueSpecificCivilization(player, "IMPROVEMENT_KASBAH");
    common.is_netherlands = ZeroSisFoundValueSpecificCivilization(player, "IMPROVEMENT_POLDER");
    for(unsigned int i = 0; i < 8; ++i) common.ring_modifier[i] = m_iRingModifier[i];
    common.settler_food_multiplier = GC.getSETTLER_FOOD_MULTIPLIER();
    common.settler_happiness_multiplier = GC.getSETTLER_HAPPINESS_MULTIPLIER();
    common.settler_production_multiplier = GC.getSETTLER_PRODUCTION_MULTIPLIER();
    common.settler_gold_multiplier = GC.getSETTLER_GOLD_MULTIPLIER();
    common.settler_science_multiplier = GC.getSETTLER_SCIENCE_MULTIPLIER();
    common.settler_faith_multiplier = GC.getSETTLER_FAITH_MULTIPLIER();
    common.faith_flavor_multiplier = m_iFlavorMultiplier[YIELD_FAITH];
    common.settler_resource_multiplier = GC.getSETTLER_RESOURCE_MULTIPLIER();
    common.settler_strategic_multiplier = GC.getSETTLER_STRATEGIC_MULTIPLIER();
    common.build_on_resource_percent = GC.getBUILD_ON_RESOURCE_PERCENT();
    common.build_on_river_percent = GC.getBUILD_ON_RIVER_PERCENT();
    common.build_on_coast_percent = GC.getSETTLER_BUILD_ON_COAST_PERCENT();
    common.min_city_range = GC.getMIN_CITY_RANGE();
    common.min_water_size_for_ocean = GC.getMIN_WATER_SIZE_FOR_OCEAN();
    common.brazil_multiplier = m_iBrazilMultiplier;
    common.spain_multiplier = m_iSpainMultiplier;
    common.morocco_multiplier = m_iMorrocoMultiplier;
    common.netherlands_multiplier = m_iNetherlandsMultiplier;
    common.inca_multiplier = m_iIncaMultiplier;
    common.major_civ_count = MAX_MAJOR_CIVS;

    std::vector<ZeroSisFoundValueHelperCache> cache(static_cast<size_t>(plots));
    std::vector<ZeroSisFoundValueInput> inputs;
    std::vector<int> indices;
    std::vector<int> values(static_cast<size_t>(plots), -1);
    std::vector<unsigned char> revealed(static_cast<size_t>(plots), 0);
    unsigned int helperPlots = 0;
    for(int index = 0; index < plots; ++index) {
        CvPlot* center = GC.getMap().plotByIndexUnchecked(index);
        if(center == NULL) throw std::logic_error("Found-value map contains a missing indexed plot");
        if(!center->isRevealed(team)) continue;
        revealed[static_cast<size_t>(index)] = 1;
        if(center->area() == NULL) return false;
        ZeroSisFoundValueInput input = common;
        input.center_area = center->getArea();
        input.center_can_found_visible = CanFound(center, player, true);
        input.center_can_found_full = input.center_can_found_visible && CanFound(center, player, false);
        input.center_has_unique_luxury = player->GetPlayerTraits()->WillGetUniqueLuxury(center->area());
        input.center_has_resource_for_team = center->getResourceType(team) != NO_RESOURCE;
        input.center_is_river = center->isRiver();
        input.center_is_coastal = center->isCoastalLand(common.min_water_size_for_ocean);
        input.tiles[112].present = 1;
        input.tiles[112].distance = 0;
        if(input.center_can_found_full) {
            for(int dx = -7; dx <= 7; ++dx) {
                for(int dy = -7; dy <= 7; ++dy) {
                    CvPlot* plot = plotXY(center->getX(), center->getY(), dx, dy);
                    if(plot == NULL) continue;
                    const int distance = plotDistance(center->getX(), center->getY(), plot->getX(), plot->getY());
                    if(distance > 7) continue;
                    const int plotIndex = plot->GetPlotIndex();
                    if(plotIndex < 0 || plotIndex >= plots) throw std::logic_error("Found-value neighbor index is outside the map");
                    ZeroSisFoundValueHelperCache& entry = cache[static_cast<size_t>(plotIndex)];
                    if((entry.ready & 1u) == 0) {
                        entry.tile.present = 1;
                        const PlayerTypes plotOwner = plot->getOwner();
                        entry.tile.owner = plotOwner == NO_PLAYER ? ZEROSIS_FOUND_VALUE_OWNER_UNOWNED :
                            plotOwner == owner ? ZEROSIS_FOUND_VALUE_OWNER_PLAYER : ZEROSIS_FOUND_VALUE_OWNER_OTHER;
                        entry.tile.city = plot->isCity();
                        entry.tile.city_owner_is_major = plotOwner >= 0 && plotOwner < MAX_MAJOR_CIVS;
                        const FeatureTypes feature = plot->getFeatureType();
                        entry.tile.forest = feature == FEATURE_FOREST;
                        entry.tile.jungle = feature == FEATURE_JUNGLE;
                        entry.tile.wetlands = feature == FEATURE_MARSH || feature == FEATURE_FLOOD_PLAINS;
                        entry.tile.natural_wonder = plot->IsNaturalWonder();
                        entry.tile.desert_without_resource = plot->getTerrainType() == TERRAIN_DESERT && plot->getResourceType() == NO_RESOURCE;
                        entry.tile.hills = plot->isHills();
                        entry.tile.adjacent_mountains = common.is_inca && entry.tile.hills ? plot->GetNumAdjacentMountains() : 0;
                        entry.tile.unimproved = plot->getImprovementType() == NO_IMPROVEMENT;
                        entry.ready |= 1u;
                    }
                    if(entry.tile.owner != ZEROSIS_FOUND_VALUE_OWNER_OTHER && distance > 0 && distance <= 3 && (entry.ready & 2u) == 0) {
                        entry.tile.food_value = ComputeFoodValue(plot, player);
                        entry.tile.production_value = ComputeProductionValue(plot, player);
                        entry.tile.gold_value = ComputeGoldValue(plot, player);
                        entry.tile.science_value = ComputeScienceValue(plot, player);
                        entry.tile.faith_value = ComputeFaithValue(plot, player);
                        entry.ready |= 2u;
                    }
                    if(entry.tile.owner == ZEROSIS_FOUND_VALUE_OWNER_UNOWNED && distance <= 5 && (entry.ready & 4u) == 0) {
                        entry.tile.happiness_value = ComputeHappinessValue(plot, player);
                        entry.tile.resource_value = ComputeTradeableResourceValue(plot, player);
                        entry.ready |= 4u;
                    }
                    if(entry.tile.owner == ZEROSIS_FOUND_VALUE_OWNER_UNOWNED && distance > 0 && distance <= 5 && (entry.strategicReady & (1u << distance)) == 0) {
                        entry.strategic[distance] = ComputeStrategicValue(plot, player, distance);
                        entry.strategicReady |= 1u << distance;
                    }
                    ZeroSisFoundValueTile tile = entry.tile;
                    tile.distance = distance;
                    tile.strategic_value = distance > 0 && distance <= 5 ? entry.strategic[distance] : 0;
                    input.tiles[static_cast<size_t>((dx + 7) * 15 + dy + 7)] = tile;
                }
            }
        }
        inputs.push_back(input);
        indices.push_back(index);
    }
    for(size_t i = 0; i < cache.size(); ++i) if((cache[i].ready & 6u) != 0 || cache[i].strategicReady != 0) ++helperPlots;
    const unsigned long long snapshotUs = ZeroSisFoundValueNowUs() - snapshotStart;
    std::vector<ZeroSisFoundValueResult> results(inputs.size());
    ZeroSisFoundValueMetrics metrics = {};
    ZeroSisFoundValueConfig config = {};
    config.abi_version = ZEROSIS_FOUND_VALUE_ABI_VERSION;
    config.config_version = ZEROSIS_FOUND_VALUE_CONFIG_VERSION;
    config.requested_workers = workers;
    config.owner_thread_id = ::GetCurrentThreadId();
    const unsigned long long workerStart = ZeroSisFoundValueNowUs();
    const int status = ZeroSisFoundValueEvaluateBatch(inputs.empty() ? NULL : &inputs[0],
        static_cast<unsigned int>(inputs.size()), &config, results.empty() ? NULL : &results[0], &metrics);
    const unsigned long long workerUs = ZeroSisFoundValueNowUs() - workerStart;
    if(status != ZEROSIS_FOUND_VALUE_OK) throw std::runtime_error("Owned found-value batch failed before map/area commit");
    const unsigned long long shadowStart = ZeroSisFoundValueNowUs();
    for(size_t i = 0; i < indices.size(); ++i) {
        const int expected = PlotFoundValue(GC.getMap().plotByIndexUnchecked(indices[i]), player, NO_YIELD, false);
        if(results[i].status != ZEROSIS_FOUND_VALUE_OK || results[i].score != expected)
            throw std::runtime_error("Owned found-value score differs from the original scalar before map/area commit");
        values[static_cast<size_t>(indices[i])] = results[i].score;
    }
    const unsigned long long shadowUs = ZeroSisFoundValueNowUs() - shadowStart;
    const unsigned long long reductionStart = ZeroSisFoundValueNowUs();
    const int threshold = GC.getAI_STRATEGY_MINIMUM_SETTLE_FERTILITY();
    std::vector<CvArea*> areas;
    std::vector<int> totals;
    std::vector<int> plotAreaSlots(static_cast<size_t>(plots), -1);
    int loop = 0;
    for(CvArea* area = GC.getMap().firstArea(&loop); area != NULL; area = GC.getMap().nextArea(&loop)) {
        areas.push_back(area);
        totals.push_back(0);
    }
    // Original plot-index order is retained, with checked accumulation before
    // any found-value or area-total setter becomes observable.
    for(int i = 0; i < plots; ++i) {
        const int value = values[static_cast<size_t>(i)];
        // Unrevealed plots keep -1 and never contribute, even if a mod changes
        // the minimum fertility threshold below zero.
        if(!revealed[static_cast<size_t>(i)] || value < threshold) continue;
        CvArea* area = GC.getMap().getArea(GC.getMap().plotByIndexUnchecked(i)->getArea());
        if(area == NULL || area->isWater()) continue;
        size_t at = 0;
        while(at < areas.size() && areas[at] != area) ++at;
        if(at == areas.size()) throw std::logic_error("Found-value reduction area is missing from the captured area order");
        plotAreaSlots[static_cast<size_t>(i)] = static_cast<int>(at);
        const long long sum = static_cast<long long>(totals[at]) + value;
        if(sum < (std::numeric_limits<int>::min)() || sum > (std::numeric_limits<int>::max)())
            throw std::overflow_error("Found-value area accumulation overflowed before commit");
        totals[at] = static_cast<int>(sum);
    }
    if(!gDLL->IsGameCoreThread() || !gDLL->HasGameCoreLock()) throw std::logic_error("Found-value owner/lock changed before commit");
    for(size_t i = 0; i < areas.size(); ++i) areas[i]->setTotalFoundValue(0);
    for(int i = 0; i < plots; ++i) {
        const int value = values[static_cast<size_t>(i)];
        GC.getMap().plotByIndexUnchecked(i)->setFoundValue(owner, value);
        const int at = plotAreaSlots[static_cast<size_t>(i)];
        if(at >= 0) {
            CvArea* area = areas[static_cast<size_t>(at)];
            area->setTotalFoundValue(area->getTotalFoundValue() + value);
        }
    }
    const unsigned long long reductionUs = ZeroSisFoundValueNowUs() - reductionStart;
    ZeroSisTraceFoundValues(player, values.empty() ? NULL : &values[0], false, callId, workers, helperPlots, snapshotUs, workerUs,
        shadowUs, reductionUs, ZeroSisFoundValueNowUs() - totalStart, &metrics);
    return true;
}
