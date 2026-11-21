#include <algorithm>
#include <climits>
#include <cstddef>
#include <cstdint>
#include <cstdlib>
#include <fstream>
#include <iostream>
#include <iterator>
#include <stdexcept>
#include <string>
#include <vector>

#include "FoundValueSharedBridge.h"

namespace {
unsigned int checks = 0;

void require(bool condition, const char* message) {
    if (!condition) throw std::runtime_error(message);
    ++checks;
}

std::string read_file(const char* path) {
    std::ifstream input(path, std::ios::binary);
    if (!input) throw std::runtime_error(std::string("cannot read ") + path);
    return std::string(std::istreambuf_iterator<char>(input), std::istreambuf_iterator<char>());
}

std::string compact(const std::string& text) {
    std::string result;
    result.reserve(text.size());
    for (char value : text)
        if (value != ' ' && value != '\t' && value != '\r' && value != '\n') result.push_back(value);
    return result;
}

std::string body_after(const std::string& source, const std::string& signature) {
    const std::size_t marker = source.find(signature);
    if (marker == std::string::npos) throw std::runtime_error("source function signature missing: " + signature);
    const std::size_t open = source.find('{', marker + signature.size());
    if (open == std::string::npos) throw std::runtime_error("source function body missing: " + signature);
    unsigned int depth = 0;
    bool lineComment = false;
    bool blockComment = false;
    bool string = false;
    bool character = false;
    bool escaped = false;
    for (std::size_t at = open; at < source.size(); ++at) {
        const char ch = source[at];
        const char next = at + 1 < source.size() ? source[at + 1] : '\0';
        if (lineComment) { if (ch == '\n') lineComment = false; continue; }
        if (blockComment) { if (ch == '*' && next == '/') { blockComment = false; ++at; } continue; }
        if (string || character) {
            if (escaped) escaped = false;
            else if (ch == '\\') escaped = true;
            else if ((string && ch == '"') || (character && ch == '\'')) { string = false; character = false; }
            continue;
        }
        if (ch == '/' && next == '/') { lineComment = true; ++at; continue; }
        if (ch == '/' && next == '*') { blockComment = true; ++at; continue; }
        if (ch == '"') { string = true; continue; }
        if (ch == '\'') { character = true; continue; }
        if (ch == '{') ++depth;
        else if (ch == '}' && --depth == 0) return source.substr(open, at - open + 1);
    }
    throw std::runtime_error("source function body is unbalanced: " + signature);
}

std::size_t position(const std::string& source, const std::string& token, std::size_t start = 0) {
    const std::size_t found = source.find(token, start);
    if (found == std::string::npos) throw std::runtime_error("required source expression missing: " + token);
    return found;
}

struct MockState {
    std::vector<int> plot_values;
    std::vector<int> area_totals;
    std::vector<int> plot_areas;
    std::vector<unsigned char> water_areas;
    std::vector<std::string> effects;
};

bool mock_commit(MockState& state, const std::vector<int>& values,
                 const std::vector<unsigned char>& revealed, int threshold,
                 bool owner_lock, bool bridge_ok, bool shadow_ok) {
    if (!owner_lock || !bridge_ok || !shadow_ok || values.size() != state.plot_values.size() ||
        revealed.size() != values.size() || state.plot_areas.size() != values.size()) return false;
    std::vector<long long> totals(state.area_totals.size(), 0);
    std::vector<int> slots(values.size(), -1);
    for (std::size_t plot = 0; plot < values.size(); ++plot) {
        if (!revealed[plot] || values[plot] < threshold) continue;
        const int area = state.plot_areas[plot];
        if (area < 0 || static_cast<std::size_t>(area) >= totals.size() ||
            state.water_areas[static_cast<std::size_t>(area)]) continue;
        const long long sum = totals[static_cast<std::size_t>(area)] + values[plot];
        if (sum < INT_MIN || sum > INT_MAX) return false;
        totals[static_cast<std::size_t>(area)] = sum;
        slots[plot] = area;
    }
    for (std::size_t area = 0; area < state.area_totals.size(); ++area) {
        state.area_totals[area] = 0;
        state.effects.push_back("reset-area:" + std::to_string(area));
    }
    for (std::size_t plot = 0; plot < values.size(); ++plot) {
        state.plot_values[plot] = values[plot];
        state.effects.push_back("set-plot:" + std::to_string(plot));
        const int area = slots[plot];
        if (area >= 0) {
            state.area_totals[static_cast<std::size_t>(area)] += values[plot];
            state.effects.push_back("add-area:" + std::to_string(area) + ":plot:" + std::to_string(plot));
        }
    }
    return true;
}

void test_source_contract(const std::string& capture, const std::string& player,
                          const std::string& site, const std::string& activePlayer,
                          const std::string& activeSite) {
    require(site == activeSite, "active and original x64 site evaluator source must match");
    require(compact(body_after(player, "void CvPlayerAI::AI_updateFoundValues")) ==
            compact(body_after(activePlayer, "void CvPlayerAI::AI_updateFoundValues")),
            "active and original AI_updateFoundValues function bodies must match");
    const std::string owned = compact(body_after(capture,
        "ZeroSisOwnedSharedFoundValues(CvPlayer* player"));
    const std::string diagnostics = compact(body_after(capture, "void ZeroSisTraceFoundValues"));
    const std::string layout = compact(body_after(capture, "void ZeroSisTraceFoundValueSharedLayout"));

    const std::size_t ownerGuard = position(owned, "!gDLL->IsGameCoreThread()||!gDLL->HasGameCoreLock()");
    const std::size_t mapRead = position(owned, "GC.getMap().numPlots()");
    require(ownerGuard < mapRead, "owner and lock validation must precede SDK map access");
    require(owned.find("typeid(*this)!=typeid(CvSiteEvaluatorForSettler)") < mapRead,
            "unknown evaluator subclasses must use the scalar fallback");
    require(owned.find("if(NUM_CITY_RINGS!=3||GC.getMIN_CITY_RANGE()<0||GC.getMIN_CITY_RANGE()>=8)returnfalse;") != std::string::npos,
            "unsupported ring and city-range configurations must use the scalar fallback");
    require(owned.find("if(plotCount<0||workers==0||workers>ZEROSIS_FOUND_VALUE_WORKER_SLOTS)returnfalse;") != std::string::npos,
            "unsupported worker counts must use the scalar fallback");

    require(owned.find("ZeroSisFoundValueSharedCommoncommon={};") != std::string::npos &&
            owned.find("common.center_present=1;") != std::string::npos,
            "one zero-initialized common ABI record must carry the old player/config observations");
    require(owned.find("common.faith_flavor_multiplier=m_iFlavorMultiplier[YIELD_FAITH];") != std::string::npos &&
            owned.find("common.settler_faith_multiplier=GC.getSETTLER_FAITH_MULTIPLIER();") != std::string::npos,
            "settler faith multiplier and faith-flavor multiplier must remain distinct");
    require(owned.find("ComputeFlavorMultipliers(player);") < position(owned, "common.naval_flavor=") &&
            owned.find("common.faith_flavor_multiplier=m_iFlavorMultiplier[YIELD_FAITH];") != std::string::npos,
            "common flavors must be computed on the owner thread before snapshot scoring");

    require(owned.find("std::vector<ZeroSisFoundValueSharedPlot>plots(static_cast<size_t>(plotCount));") != std::string::npos &&
            owned.find("std::vector<unsignedchar>ready(static_cast<size_t>(plotCount),0);") != std::string::npos &&
            owned.find("std::vector<unsignedchar>strategicReady(static_cast<size_t>(plotCount),0);") != std::string::npos,
            "one map-sized facts array and independent readiness arrays are required");
    const std::size_t reserveCandidates = position(owned, "candidates.reserve(static_cast<size_t>(plotCount));");
    const std::size_t reserveIndices = position(owned, "indices.reserve(static_cast<size_t>(plotCount));");
    const std::size_t centerLoop = position(owned, "for(intindex=0;index<plotCount;++index)");
    require(reserveCandidates < centerLoop && reserveIndices < centerLoop,
            "candidate and ordered-index storage must reserve by map plot count before capture");
    require(owned.find("std::vector<int>values(static_cast<size_t>(plotCount),-1);") != std::string::npos &&
            owned.find("if(!center->isRevealed(team))continue;") != std::string::npos &&
            owned.find("revealed[static_cast<size_t>(index)]=1;") != std::string::npos,
            "hidden plots must retain the -1 sentinel and separate revealed eligibility");

    const std::size_t centerPresent = position(owned, "centerFacts.tile.present=1;");
    const std::size_t fullGate = position(owned, "if(candidate.center_can_found_full)");
    const std::size_t basicReady = position(owned, "ready[mapIndex]|=1u;");
    require(centerPresent < fullGate && fullGate < basicReady,
            "CanFound-false centers stay present without being marked helper-ready");
    require(owned.find("candidate.slots[112].map_plot_index=static_cast<unsignedint>(index);") != std::string::npos &&
            owned.find("candidate.slots[112].distance=0;") != std::string::npos,
            "every eligible candidate must carry the index/distance center slot even when not foundable");
    require(owned.find("candidate.slots[slot].map_plot_index=static_cast<unsignedint>(plotIndex);") != std::string::npos &&
            owned.find("candidate.slots[slot].distance=distance;") != std::string::npos &&
            owned.find("(dx+7)*15+dy+7") != std::string::npos,
            "candidate geometry must preserve dx-major/dy-minor scan order and source distance");
    require(owned.find("candidate.slots[slot].map_plot_index=ZEROSIS_FOUND_VALUE_SHARED_MISSING_PLOT;") != std::string::npos &&
            owned.find("candidate.slots[slot].distance=0;") != std::string::npos,
            "missing geometry must use the ABI sentinel and zero distance");
    require(owned.find("if(distance<0)returnfalse;") != std::string::npos &&
            owned.find("if(plotIndex<0||plotIndex>=plotCount)throwstd::logic_error") != std::string::npos,
            "unrepresentable distance falls back and invalid SDK indices fail before commit");
    require(owned.find("if(center->GetPlotIndex()!=index)throwstd::logic_error") != std::string::npos,
            "center plot facts must use the same index as the map slot");

    require(owned.find("if((ready[mapIndex]&1u)==0)") != std::string::npos &&
            owned.find("if(entry.tile.owner!=ZEROSIS_FOUND_VALUE_OWNER_OTHER&&distance>0&&distance<=3&&(ready[mapIndex]&2u)==0)") != std::string::npos &&
            owned.find("if(entry.tile.owner==ZEROSIS_FOUND_VALUE_OWNER_UNOWNED&&distance<=5&&(ready[mapIndex]&4u)==0)") != std::string::npos,
            "basic tile, yield, and unowned happiness/resource facts need separate readiness conditions");
    require(owned.find("if(entry.tile.owner==ZEROSIS_FOUND_VALUE_OWNER_UNOWNED&&distance>0&&distance<=5&&(strategicReady[mapIndex]&(1u<<distance))==0)") != std::string::npos &&
            owned.find("entry.strategic_by_distance[distance]=ComputeStrategicValue(plot,player,distance);") != std::string::npos,
            "strategic helper facts must be cached independently by unique plot and distance");
    require(owned.find("ComputeFoodValue(plot,player)") != std::string::npos &&
            owned.find("ComputeHappinessValue(plot,player)") != std::string::npos &&
            owned.find("ComputeProductionValue(plot,player)") != std::string::npos &&
            owned.find("ComputeGoldValue(plot,player)") != std::string::npos &&
            owned.find("ComputeScienceValue(plot,player)") != std::string::npos &&
            owned.find("ComputeFaithValue(plot,player)") != std::string::npos &&
            owned.find("ComputeTradeableResourceValue(plot,player)") != std::string::npos,
            "all original per-plot helper calls must stay in owner-thread capture");

    const std::size_t bridge = position(owned, "ZeroSisFoundValueEvaluateSharedBatch(");
    const std::size_t bridgeFail = position(owned, "if(status!=ZEROSIS_FOUND_VALUE_OK)throw");
    const std::size_t shadow = position(owned, "constunsignedlonglongshadowStart=");
    const std::size_t shadowFailure = position(owned, "results[i].score!=expected");
    const std::size_t overflow = position(owned, "throwstd::overflow_error(\"Found-valueareaaccumulationoverflowedbeforecommit\")");
    const std::size_t ownerRecheck = position(owned, "if(!gDLL->IsGameCoreThread()||!gDLL->HasGameCoreLock())", overflow);
    const std::size_t reset = position(owned, "areas[i]->setTotalFoundValue(0)");
    const std::size_t plotSet = position(owned, "->setFoundValue(owner,value)");
    const std::size_t areaAdd = position(owned, "area->setTotalFoundValue(area->getTotalFoundValue()+value)");
    require(bridge < bridgeFail && bridgeFail < shadow && shadow < shadowFailure &&
            shadowFailure < overflow && overflow < ownerRecheck && ownerRecheck < reset &&
            reset < plotSet && plotSet < areaAdd,
            "bridge, scalar shadow, checked reduction, owner lock, and setter order must be transactional");
    require(owned.find("PlotFoundValue(GC.getMap().plotByIndexUnchecked(indices[i]),player,NO_YIELD,false)") != std::string::npos,
            "every worker score must be compared with the original known settler scalar path");
    require(owned.find("if(!revealed[static_cast<size_t>(i)]||value<threshold)continue;") != std::string::npos &&
            owned.find("if(value<0||value<threshold)") == std::string::npos,
            "hidden -1 must remain ineligible even under negative thresholds; revealed negative values keep source rules");
    require(owned.find("static_cast<longlong>(totals[at])+value") != std::string::npos &&
            owned.find("(std::numeric_limits<int>::min)()") != std::string::npos &&
            owned.find("(std::numeric_limits<int>::max)()") != std::string::npos,
            "area accumulation must use checked wide arithmetic before any setter");

    require(diagnostics.find("plot->getFoundValue(") == std::string::npos &&
            diagnostics.find("plot.getFoundValue(") == std::string::npos &&
            diagnostics.find("orderedValues[i]") != std::string::npos,
            "diagnostics must print owned output values and never trigger lazy found-value recomputation");
    const std::size_t valuesLine = position(capture, "ZEROSIS_FOUND_VALUE_VALUES call_id=%u records=");
    const std::size_t areasLine = position(capture, "ZEROSIS_FOUND_VALUE_AREAS call_id=%u records=");
    const std::size_t traceLine = position(capture, "ZEROSIS_FOUND_VALUE_TRACE version=1 call_id=%u");
    const std::size_t layoutLine = position(capture, "ZEROSIS_FOUND_VALUE_LAYOUT version=1 call_id=%u input_layout=SHARED_FACTS cpu_batch_id=%llu");
    require(valuesLine < areasLine && areasLine < traceLine && traceLine < layoutLine,
            "the existing adjacent VALUES/AREAS/TRACE protocol must precede the additive LAYOUT record");
    require(layout.find("sizeof(ZeroSisFoundValueSharedCommon)") != std::string::npos &&
            layout.find("sizeof(ZeroSisFoundValueSharedPlot)") != std::string::npos &&
            layout.find("sizeof(ZeroSisFoundValueSharedCandidate)") != std::string::npos &&
            layout.find("sizeof(ZeroSisFoundValueInput)") != std::string::npos &&
            layout.find("commonBytes+plotBytes+candidateBytes") != std::string::npos &&
            layout.find("static_cast<unsignedlonglong>(plotCount)*sizeof(ZeroSisFoundValueSharedPlot)") != std::string::npos &&
            layout.find("static_cast<unsignedlonglong>(candidateCount)*sizeof(ZeroSisFoundValueSharedCandidate)") != std::string::npos &&
            layout.find("static_cast<unsignedlonglong>(candidateCount)*sizeof(ZeroSisFoundValueInput)") != std::string::npos,
            "layout accounting must derive byte counts from the shared ABI types and dense baseline");

    const std::string originalUpdate = compact(body_after(player, "void CvPlayerAI::AI_updateFoundValues"));
    const std::size_t originalReset = position(originalUpdate, "pLoopArea->setTotalFoundValue(0)");
    const std::size_t originalFlavors = position(originalUpdate, "ComputeFlavorMultipliers(this)");
    const std::size_t originalReveal = position(originalUpdate, "if(pLoopPlot->isRevealed(eTeam))");
    const std::size_t originalScore = position(originalUpdate, "PlotFoundValue(pLoopPlot,this,NO_YIELD,false)");
    const std::size_t originalPlotSet = position(originalUpdate, "pLoopPlot->setFoundValue(eID,iValue)");
    const std::size_t originalThreshold = position(originalUpdate, "if(iValue>=iGoodEnoughToBeWorthOurTime)");
    const std::size_t originalAreaAdd = position(originalUpdate,
        "pLoopArea->setTotalFoundValue(pLoopArea->getTotalFoundValue()+iValue)");
    const std::size_t originalHidden = position(originalUpdate, "pLoopPlot->setFoundValue(eID,-1)");
    require(originalReset < originalFlavors && originalFlavors < originalReveal &&
            originalReveal < originalScore && originalScore < originalPlotSet &&
            originalPlotSet < originalThreshold && originalThreshold < originalAreaAdd &&
            originalAreaAdd < originalHidden,
            "original AI update order remains the reference contract");
    const std::string wrapper = compact(body_after(site, "int CvSiteEvaluatorForSettler::PlotFoundValue"));
    require(position(wrapper, "if(!CanFound(pPlot,pPlayer,true))") <
            position(wrapper, "if(bCoastOnly&&!bIsCoastal&&iNumAreaCities==0)") &&
            position(wrapper, "if(bCoastOnly&&!bIsCoastal&&iNumAreaCities==0)") <
            position(wrapper, "if(pPlayer->GetPlayerTraits()->WillGetUniqueLuxury(pArea))") &&
            wrapper.find("bCoastOnly&&!bIsCoastal") != std::string::npos,
            "the original visible/coast/unique-luxury wrapper remains source truth for shadowing");
    const std::string base = compact(body_after(site, "int CvCitySiteEvaluator::PlotFoundValue"));
    require(base.find("if(!CanFound(pPlot,pPlayer,false))") != std::string::npos &&
            base.find("iDistance>0&&iDistance<=NUM_CITY_RINGS") != std::string::npos &&
            base.find("iDistance<=5&&pLoopPlot->getOwner()==NO_PLAYER") != std::string::npos &&
            base.find("iDistance)iStrategicValue=ComputeStrategicValue(pLoopPlot,pPlayer,iDistance)") != std::string::npos,
            "the exact original full-found, yield, unowned, and distance-helper branches must remain authoritative");
}

struct MockFact {
    bool present = false;
    unsigned char ready = 0;
    unsigned char strategic_ready = 0;
    int owner = ZEROSIS_FOUND_VALUE_OWNER_UNOWNED;
    int basic_calls = 0;
    int yield_calls = 0;
    int unowned_calls = 0;
    int strategic_calls[8] = {};
};

void capture_center_only(MockFact& fact) {
    fact.present = true;
}

void capture_neighbor_use(MockFact& fact, int distance) {
    if ((fact.ready & 1u) == 0) { fact.present = true; ++fact.basic_calls; fact.ready |= 1u; }
    if (fact.owner != ZEROSIS_FOUND_VALUE_OWNER_OTHER && distance > 0 && distance <= 3 &&
        (fact.ready & 2u) == 0) { ++fact.yield_calls; fact.ready |= 2u; }
    if (fact.owner == ZEROSIS_FOUND_VALUE_OWNER_UNOWNED && distance <= 5 &&
        (fact.ready & 4u) == 0) { ++fact.unowned_calls; fact.ready |= 4u; }
    if (fact.owner == ZEROSIS_FOUND_VALUE_OWNER_UNOWNED && distance > 0 && distance <= 5 &&
        (fact.strategic_ready & (1u << distance)) == 0) {
        ++fact.strategic_calls[distance];
        fact.strategic_ready |= static_cast<unsigned char>(1u << distance);
    }
}

std::size_t slot_offset(int dx, int dy) {
    return static_cast<std::size_t>((dx + 7) * 15 + dy + 7);
}

void test_shared_geometry_and_lazy_cache() {
    ZeroSisFoundValueSharedCandidate clipped{};
    for (unsigned int slot = 0; slot < ZEROSIS_FOUND_VALUE_TILE_COUNT; ++slot)
        clipped.slots[slot].map_plot_index = ZEROSIS_FOUND_VALUE_SHARED_MISSING_PLOT;
    clipped.center_plot_index = 4;
    clipped.slots[112].map_plot_index = 4;
    clipped.slots[112].distance = 0;
    const int width = 3, height = 3, center_x = 1, center_y = 1;
    for (int dx = -7; dx <= 7; ++dx) for (int dy = -7; dy <= 7; ++dy) {
        const int x = center_x + dx, y = center_y + dy;
        if (x < 0 || x >= width || y < 0 || y >= height) continue;
        const std::size_t at = slot_offset(dx, dy);
        clipped.slots[at].map_plot_index = static_cast<unsigned int>(y * width + x);
        clipped.slots[at].distance = (std::abs(dx) + std::abs(dy) + std::abs(dx + dy)) / 2;
    }
    require(clipped.slots[112].map_plot_index == 4 && clipped.slots[112].distance == 0,
            "clipped geometry retains its required center reference");
    require(clipped.slots[slot_offset(-7, 0)].map_plot_index == ZEROSIS_FOUND_VALUE_SHARED_MISSING_PLOT &&
            clipped.slots[slot_offset(-7, 0)].distance == 0,
            "clipped plots retain missing sentinels with zero distances");

    ZeroSisFoundValueSharedCandidate wrapped{};
    for (unsigned int slot = 0; slot < ZEROSIS_FOUND_VALUE_TILE_COUNT; ++slot)
        wrapped.slots[slot].map_plot_index = ZEROSIS_FOUND_VALUE_SHARED_MISSING_PLOT;
    wrapped.center_plot_index = 4;
    wrapped.slots[112] = {4, 0};
    bool duplicate_distance_refs = false;
    for (int dx = -7; dx <= 7; ++dx) for (int dy = -7; dy <= 7; ++dy) {
        const int x = (center_x + dx % width + width) % width;
        const int y = (center_y + dy % height + height) % height;
        const std::size_t at = slot_offset(dx, dy);
        const unsigned int index = static_cast<unsigned int>(y * width + x);
        const int distance = (std::abs(dx) + std::abs(dy) + std::abs(dx + dy)) / 2;
        wrapped.slots[at] = {index, distance};
        if (index == 5u && distance == 1) {
            const std::size_t other = slot_offset(-2, 0);
            wrapped.slots[other] = {index, 2};
            duplicate_distance_refs = true;
        }
    }
    require(duplicate_distance_refs, "wrapped geometry creates one unique plot used at multiple distances");

    MockFact forbidden_center{};
    capture_center_only(forbidden_center);
    require(forbidden_center.present && forbidden_center.ready == 0 && forbidden_center.basic_calls == 0,
            "CanFound-false center is present but does not claim basic-neighbor readiness");
    capture_neighbor_use(forbidden_center, 1);
    require(forbidden_center.present && forbidden_center.basic_calls == 1 &&
            forbidden_center.yield_calls == 1 && forbidden_center.unowned_calls == 1 &&
            forbidden_center.strategic_calls[1] == 1,
            "a forbidden center later used as a neighbor receives exactly the required helpers");
    capture_neighbor_use(forbidden_center, 1);
    capture_neighbor_use(forbidden_center, 2);
    require(forbidden_center.basic_calls == 1 && forbidden_center.yield_calls == 1 &&
            forbidden_center.unowned_calls == 1 && forbidden_center.strategic_calls[1] == 1 &&
            forbidden_center.strategic_calls[2] == 1,
            "unique helper readiness is reused while strategic readiness remains distance-specific");

    MockFact foreign{};
    foreign.present = true;
    foreign.owner = ZEROSIS_FOUND_VALUE_OWNER_OTHER;
    capture_neighbor_use(foreign, 2);
    require(foreign.basic_calls == 1 && foreign.yield_calls == 0 && foreign.unowned_calls == 0 &&
            foreign.strategic_ready == 0,
            "foreign plot capture omits yield, happiness/resource, and strategic helpers");
}

void test_mock_transaction() {
    MockState state{{41, 42, 43, 44}, {91, 92}, {0, 0, 0, 1}, {0, 0}, {}};
    const std::vector<int> values{5, -1, -2, 7};
    const std::vector<unsigned char> revealed{1, 0, 1, 1};
    require(mock_commit(state, values, revealed, -3, true, true, true),
            "valid shadowed capture transaction must commit");
    require(state.plot_values == values, "commit writes all plots and preserves hidden -1");
    require(state.area_totals[0] == 3 && state.area_totals[1] == 7,
            "hidden -1 is excluded while revealed negative values follow the threshold");
    require(state.effects.size() == 9 && state.effects[0] == "reset-area:0" &&
            state.effects[1] == "reset-area:1" && state.effects[2] == "set-plot:0" &&
            state.effects[3] == "add-area:0:plot:0" && state.effects[4] == "set-plot:1" &&
            state.effects[5] == "set-plot:2" && state.effects[6] == "add-area:0:plot:2" &&
            state.effects[7] == "set-plot:3" && state.effects[8] == "add-area:1:plot:3",
            "setter sequence must reset areas then write plot indices and totals in order");

    const auto unchanged = [](bool owner, bool bridge, bool shadow, const std::vector<int>& input) {
        MockState candidate{{11, 12}, {21}, {0, 0}, {0}, {}};
        const MockState before = candidate;
        const bool committed = mock_commit(candidate, input, {1, 1}, 0, owner, bridge, shadow);
        return !committed && candidate.plot_values == before.plot_values &&
            candidate.area_totals == before.area_totals && candidate.effects.empty();
    };
    require(unchanged(true, false, true, {1, 2}), "bridge status failure leaves setters untouched");
    require(unchanged(true, true, false, {1, 2}), "scalar shadow mismatch leaves setters untouched");
    require(unchanged(false, true, true, {1, 2}), "owner-lock loss leaves setters untouched");
    require(unchanged(true, true, true, {INT_MAX, 1}), "area overflow leaves setters untouched");
    MockState water{{9}, {8}, {0}, {1}, {}};
    require(mock_commit(water, {6}, {1}, 0, true, true, true) && water.area_totals[0] == 0,
            "water areas receive plot values but no fertility total");
}

void test_abi() {
    require(sizeof(ZeroSisFoundValueSharedCommon) == 240 && sizeof(ZeroSisFoundValueSharedPlot) == 116 &&
            sizeof(ZeroSisFoundValueSharedCandidate) == 1848 &&
            offsetof(ZeroSisFoundValueSharedCandidate, slots) == 48,
            "shared capture must use the frozen common/plot/candidate ABI sizes");
    require(sizeof(ZeroSisFoundValueInput) == 19140 && sizeof(ZeroSisFoundValueResult) == 8,
            "dense shadow and result ABI reference sizes must remain known");
}
} // namespace

int main(int argc, char** argv) {
    try {
        if (argc != 6)
            throw std::runtime_error("usage: shared_capture.exe <capture.inc> <original-player.cpp> <original-site.cpp> <active-player.cpp> <active-site.cpp>");
        test_source_contract(read_file(argv[1]), read_file(argv[2]), read_file(argv[3]),
                             read_file(argv[4]), read_file(argv[5]));
        test_shared_geometry_and_lazy_cache();
        test_mock_transaction();
        test_abi();
        std::cout << "FOUND_VALUE_SHARED_SDK_CAPTURE_EXACT_BODY_MOCK_PASS checks=" << checks
                  << " capture=false GAMECORE_LOADED=false SDK_BUILD=false WPR=false\n";
        return 0;
    } catch (const std::exception& error) {
        std::cerr << "FOUND_VALUE_SHARED_SDK_CAPTURE_MOCK_FAIL " << error.what() << '\n';
        return 1;
    }
}
