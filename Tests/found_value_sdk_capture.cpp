#include <algorithm>
#include <climits>
#include <cstddef>
#include <fstream>
#include <iostream>
#include <iterator>
#include <map>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

#include "FoundValueScoreBridge.h"

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
    if (marker == std::string::npos) throw std::runtime_error("source function signature missing");
    const std::size_t open = source.find('{', marker + signature.size());
    if (open == std::string::npos) throw std::runtime_error("source function body missing");
    unsigned int depth = 0;
    for (std::size_t at = open; at < source.size(); ++at) {
        if (source[at] == '{') ++depth;
        else if (source[at] == '}' && --depth == 0) return source.substr(open, at - open + 1);
    }
    throw std::runtime_error("source function body is unbalanced");
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
    std::vector<std::string> effects;
};

bool mock_commit(MockState& state, const std::vector<int>& values,
                 const std::vector<unsigned char>& revealed, int threshold,
                 bool bridge_ok, bool shadow_ok) {
    if (!bridge_ok || !shadow_ok || values.size() != state.plot_values.size() ||
        revealed.size() != values.size() || state.plot_areas.size() != values.size()) return false;
    std::vector<long long> totals(state.area_totals.size(), 0);
    std::vector<int> slots(values.size(), -1);
    for (std::size_t i = 0; i < values.size(); ++i) {
        if (!revealed[i] || values[i] < threshold) continue;
        const int area = state.plot_areas[i];
        if (area < 0 || static_cast<std::size_t>(area) >= totals.size()) continue;
        const long long sum = totals[static_cast<std::size_t>(area)] + values[i];
        if (sum < INT_MIN || sum > INT_MAX) return false;
        totals[static_cast<std::size_t>(area)] = sum;
        slots[i] = area;
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

void test_source_protocol(const std::string& capture, const std::string& player,
                          const std::string& site) {
    const std::string owned = compact(body_after(capture,
        "ZeroSisOwnedFoundValues(CvPlayer* player"));
    const std::string diagnostics = compact(body_after(capture, "void ZeroSisTraceFoundValues"));

    const std::size_t ownership = position(owned, "!gDLL->IsGameCoreThread()||!gDLL->HasGameCoreLock()");
    const std::size_t first_map_read = position(owned, "GC.getMap().numPlots()");
    require(ownership < first_map_read, "owner/lock check must precede map access");
    require(owned.find("::GetCurrentThreadId()") < owned.find("ZeroSisFoundValueEvaluateBatch("),
            "owner thread ID must be captured for the bridge");
    require(owned.find("config.owner_thread_id=::GetCurrentThreadId()") != std::string::npos,
            "bridge config must bind to the owning thread");

    const std::size_t batch = position(owned, "ZeroSisFoundValueEvaluateBatch(");
    const std::size_t batch_failure = position(owned, "if(status!=ZEROSIS_FOUND_VALUE_OK)throw");
    const std::size_t shadow = position(owned, "constunsignedlonglongshadowStart=");
    const std::size_t shadow_failure = position(owned, "results[i].score!=expected");
    const std::size_t overflow = position(owned, "throwstd::overflow_error(\"Found-valueareaaccumulationoverflowedbeforecommit\")");
    const std::size_t reset = position(owned, "areas[i]->setTotalFoundValue(0)");
    const std::size_t plot_set = position(owned, "->setFoundValue(owner,value)");
    const std::size_t area_add = position(owned, "area->setTotalFoundValue(area->getTotalFoundValue()+value)");
    require(batch < batch_failure && batch_failure < shadow && shadow < shadow_failure &&
            shadow_failure < overflow && overflow < reset && reset < plot_set && plot_set < area_add,
            "all bridge/shadow/overflow gates must precede ordered commit setters");
    const std::size_t commit_owner = position(owned, "if(!gDLL->IsGameCoreThread()||!gDLL->HasGameCoreLock())", overflow);
    require(commit_owner > overflow && commit_owner < reset,
            "owner/lock must be rechecked immediately before commit");

    const std::size_t revealed_vector = position(owned, "std::vector<unsignedchar>revealed(static_cast<size_t>(plots),0)");
    const std::size_t reveal_test = position(owned, "if(!center->isRevealed(team))continue;");
    const std::size_t mark_revealed = position(owned, "revealed[static_cast<size_t>(index)]=1;");
    const std::size_t eligibility = position(owned, "if(!revealed[static_cast<size_t>(i)]||value<threshold)continue;");
    require(revealed_vector < reveal_test && reveal_test < mark_revealed && mark_revealed < eligibility,
            "revealed eligibility must distinguish hidden -1 from valid negative scores");
    require(owned.find("if(value<0||value<threshold)") == std::string::npos,
            "negative score values must not be silently excluded from area totals");

    require(owned.find("entry.ready&1u") != std::string::npos &&
            owned.find("entry.ready&2u") != std::string::npos &&
            owned.find("entry.ready&4u") != std::string::npos,
            "unique-plot helper cache needs independent tile, yield, and unowned helper readiness");
    require(owned.find("entry.tile.owner!=ZEROSIS_FOUND_VALUE_OWNER_OTHER&&distance>0&&distance<=3&&(entry.ready&2u)==0") != std::string::npos &&
            owned.find("entry.tile.owner==ZEROSIS_FOUND_VALUE_OWNER_UNOWNED&&distance<=5&&(entry.ready&4u)==0") != std::string::npos,
            "shared helper cache guards must match base evaluator owner and radius rules");
    require(owned.find("entry.strategicReady&(1u<<distance)") != std::string::npos &&
            owned.find("entry.tile.owner==ZEROSIS_FOUND_VALUE_OWNER_UNOWNED&&distance>0&&distance<=5&&(entry.strategicReady&(1u<<distance))==0") != std::string::npos &&
            owned.find("entry.strategic[distance]=ComputeStrategicValue(plot,player,distance)") != std::string::npos,
            "strategic helper cache must distinguish the same plot at each distance");
    require(owned.find("tile.strategic_value=distance>0&&distance<=5?entry.strategic[distance]:0") != std::string::npos,
            "candidate tile must receive its distance-specific strategic helper");

    require(diagnostics.find("plot->getFoundValue(") == std::string::npos &&
            diagnostics.find("plot.getFoundValue(") == std::string::npos,
            "diagnostics must not trigger lazy found-value computation");
    require(diagnostics.find("orderedValues[i]") != std::string::npos,
            "diagnostics must print the caller-owned committed observation");

    const std::string original = compact(body_after(player, "void CvPlayerAI::AI_updateFoundValues"));
    const std::size_t original_reset = position(original, "pLoopArea->setTotalFoundValue(0)");
    const std::size_t original_flavors = position(original, "ComputeFlavorMultipliers(this)");
    const std::size_t original_reveal = position(original, "if(pLoopPlot->isRevealed(eTeam))");
    const std::size_t original_score = position(original, "PlotFoundValue(pLoopPlot,this,NO_YIELD,false)");
    const std::size_t original_plot_set = position(original, "pLoopPlot->setFoundValue(eID,iValue)");
    const std::size_t original_threshold = position(original, "if(iValue>=iGoodEnoughToBeWorthOurTime)");
    const std::size_t original_area_add = position(original, "pLoopArea->setTotalFoundValue(pLoopArea->getTotalFoundValue()+iValue)");
    const std::size_t original_hidden = position(original, "pLoopPlot->setFoundValue(eID,-1)");
    require(original_reset < original_flavors && original_flavors < original_reveal &&
            original_reveal < original_score && original_score < original_plot_set &&
            original_plot_set < original_threshold && original_threshold < original_area_add &&
            original_area_add < original_hidden,
            "original setter and hidden-sentinel behavior must remain the comparison contract");

    const std::string wrapper = compact(body_after(site,
        "int CvSiteEvaluatorForSettler::PlotFoundValue"));
    const std::size_t visible_gate = position(wrapper, "if(!CanFound(pPlot,pPlayer,true))");
    const std::size_t area_read = position(wrapper, "CvArea*pArea=pPlot->area()");
    const std::size_t coast_gate = position(wrapper, "if(bCoastOnly&&!bIsCoastal&&iNumAreaCities==0)");
    const std::size_t luxury_gate = position(wrapper, "if(pPlayer->GetPlayerTraits()->WillGetUniqueLuxury(pArea))");
    const std::size_t luxury_base = position(wrapper, "CvCitySiteEvaluator::PlotFoundValue(pPlot,pPlayer,eYield)*2");
    const std::size_t ordinary_base = position(wrapper, "returnCvCitySiteEvaluator::PlotFoundValue(pPlot,pPlayer,eYield)");
    require(visible_gate < area_read && area_read < coast_gate && coast_gate < luxury_gate &&
            luxury_gate < luxury_base && luxury_base < ordinary_base,
            "settler wrapper CanFound/coast/unique-luxury gates must stay in the scalar shadow contract");

    const std::string base = compact(body_after(site, "int CvCitySiteEvaluator::PlotFoundValue"));
    require(base.find("if(!CanFound(pPlot,pPlayer,false))") != std::string::npos &&
            base.find("if(iDistance>0&&iDistance<=NUM_CITY_RINGS)") != std::string::npos &&
            base.find("if(iDistance<=5&&pLoopPlot->getOwner()==NO_PLAYER)") != std::string::npos &&
            base.find("if(iDistance)iStrategicValue=ComputeStrategicValue(pLoopPlot,pPlayer,iDistance)") != std::string::npos,
            "base evaluator full-found, yield-ring, unowned-ring, and distance helper conditions must remain authoritative");

    const std::string helper = compact(body_after(site, "int CvCitySiteEvaluator::ComputeStrategicValue"));
    require(helper.find("iPlotsFromCity==2&&(pPlot->isImpassable()||pPlot->isMountain())") != std::string::npos &&
            helper.find("iPlotsFromCity==1&&pPlot->isHills()") != std::string::npos &&
            helper.find("m_iFlavorMultiplier[SITE_EVALUATION_STRATEGIC]") != std::string::npos,
            "strategic mock fixture must remain grounded in the original distance-based helper");
}

void test_mock_transaction() {
    MockState state{{41, 42, 43, 44}, {91, 92}, {0, 0, 0, 1}, {}};
    const std::vector<int> values{5, -1, -2, 7};
    const std::vector<unsigned char> revealed{1, 0, 1, 1};
    require(mock_commit(state, values, revealed, -3, true, true),
            "valid shadowed component transaction should commit");
    require(state.plot_values == values, "commit must write every plot, including hidden -1");
    require(state.area_totals[0] == 3 && state.area_totals[1] == 7,
            "hidden -1 must be excluded while revealed negative values obey the threshold");
    require(state.effects.size() == 9 && state.effects[0] == "reset-area:0" &&
            state.effects[1] == "reset-area:1" && state.effects[2] == "set-plot:0" &&
            state.effects[3] == "add-area:0:plot:0" && state.effects[4] == "set-plot:1" &&
            state.effects[5] == "set-plot:2" && state.effects[6] == "add-area:0:plot:2" &&
            state.effects[7] == "set-plot:3" &&
            state.effects[8] == "add-area:1:plot:3" && state.area_totals[1] == 7,
            "commit effects must follow original reset-then-plot-index setter order");

    const auto expect_unchanged = [](bool bridge_ok, bool shadow_ok,
                                     const std::vector<int>& input, int threshold) {
        MockState candidate{{11, 12}, {21}, {0, 0}, {}};
        const MockState before = candidate;
        const bool committed = mock_commit(candidate, input, {1, 1}, threshold,
                                           bridge_ok, shadow_ok);
        return !committed && candidate.plot_values == before.plot_values &&
            candidate.area_totals == before.area_totals && candidate.effects.empty();
    };
    require(expect_unchanged(false, true, {1, 2}, 0),
            "bridge failure must leave all observed state unchanged");
    require(expect_unchanged(true, false, {1, 2}, 0),
            "shadow mismatch must leave all observed state unchanged");
    require(expect_unchanged(true, true, {INT_MAX, 1}, 0),
            "late area overflow must leave all observed state unchanged");
}

void test_capture_abi() {
    require(sizeof(ZeroSisFoundValueTile) == 84 &&
            offsetof(ZeroSisFoundValueTile, strategic_value) == 48 &&
            sizeof(ZeroSisFoundValueInput) == 19140 &&
            offsetof(ZeroSisFoundValueInput, faith_flavor_multiplier) == 168 &&
            offsetof(ZeroSisFoundValueInput, settler_strategic_multiplier) == 176 &&
            ZEROSIS_FOUND_VALUE_TILE_COUNT == 225,
            "C POD ABI must retain explicit strategic helper and faith flavor fields");
}
} // namespace

int main(int argc, char** argv) {
    try {
        if (argc != 4) throw std::runtime_error("usage: found_value_sdk_capture.exe <capture.inc> <CvPlayerAI.cpp> <CvSiteEvaluationClasses.cpp>");
        test_source_protocol(read_file(argv[1]), read_file(argv[2]), read_file(argv[3]));
        test_mock_transaction();
        test_capture_abi();
        std::cout << "FOUND_VALUE_SDK_CAPTURE_MOCK_PASS checks=" << checks
                  << " capture=false GAMECORE_LOADED=false SDK_BUILD=false WPR=false\n";
        return 0;
    } catch (const std::exception& error) {
        std::cerr << "FOUND_VALUE_SDK_CAPTURE_MOCK_FAIL " << error.what() << '\n';
        return 1;
    }
}
