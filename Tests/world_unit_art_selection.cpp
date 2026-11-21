// Exercises the actual production selector without SDK, model, window or GPU APIs.
#include "../Source/Presentation/WorldUnitArtSelection.h"

#include <cstdio>
#include <initializer_list>
#include <stdexcept>
#include <string>
#include <type_traits>
#include <utility>

namespace {
using ZeroSisPresentation::SelectWorldUnitArt;
using ZeroSisPresentation::WorldUnitArtSelectionInput;
unsigned cases = 0, checks = 0;

static_assert(noexcept(SelectWorldUnitArt(std::declval<const WorldUnitArtSelectionInput&>())),
              "Art selection must not allocate or throw");
static_assert(std::is_same<decltype(SelectWorldUnitArt(std::declval<const WorldUnitArtSelectionInput&>())),
                           const std::string*>::value, "Selection must return a caller-owned tag pointer");
static_assert(std::is_reference<decltype(WorldUnitArtSelectionInput::type)>::value &&
              std::is_reference<decltype(WorldUnitArtSelectionInput::unitArtInfoTag)>::value &&
              std::is_reference<decltype(WorldUnitArtSelectionInput::artStylePrefix)>::value &&
              std::is_reference<decltype(WorldUnitArtSelectionInput::artStyleSuffix)>::value &&
              std::is_reference<decltype(WorldUnitArtSelectionInput::eraArtPrefix)>::value,
              "Input strings must be referenced without copies");

void Check(bool value, const char* reason) {
    ++checks;
    if (!value) throw std::runtime_error(reason);
}

// Own fixture strings so C++14 reference inputs never bind to dead temporaries.
struct OwnedInput {
    std::string type, unitArtInfoTag;
    bool unitArtInfoCulturalVariation, unitArtInfoEraVariation, embarked;
    std::string artStylePrefix, artStyleSuffix, eraArtPrefix;

    WorldUnitArtSelectionInput View() const {
        return {type, unitArtInfoTag, unitArtInfoCulturalVariation, unitArtInfoEraVariation,
                embarked, artStylePrefix, artStyleSuffix, eraArtPrefix};
    }
};

OwnedInput Settler() {
    return {"UNIT_SETTLER", "ART_DEF_UNIT__SETTLER", true, false, false,
            "EUROPEAN", "_EURO", "ANCIENT"};
}

OwnedInput Worker() {
    return {"UNIT_WORKER", "ART_DEF_UNIT__WORKER", false, true, false,
            "EUROPEAN", "_EURO", "ANCIENT"};
}

OwnedInput Warrior() {
    return {"UNIT_WARRIOR", "ART_DEF_UNIT__WARRIOR", false, false, false, {}, {}, {}};
}

void Reject(const OwnedInput& input, const char* reason) {
    ++cases;
    Check(SelectWorldUnitArt(input.View()) == nullptr, reason);
}

void InitialVisualInputs() {
    for (const auto& input : {Settler(), Worker()}) {
        ++cases;
        const auto result = SelectWorldUnitArt(input.View());
        Check(result && *result == input.unitArtInfoTag, "Initial civilian did not select its exact original tag");
        Check(result == &input.unitArtInfoTag, "Civilian selection substituted an art identity");
    }
    ++cases;
    std::string ownedTag = "ART_DEF_UNIT__SETTLER";
    const std::string type = "UNIT_SETTLER", prefix = "EUROPEAN", suffix = "_EURO", era = "ANCIENT";
    const WorldUnitArtSelectionInput input{type, ownedTag, true, false, false, prefix, suffix, era};
    const OwnedInput before{input.type, input.unitArtInfoTag, input.unitArtInfoCulturalVariation,
                            input.unitArtInfoEraVariation, input.embarked,
                            input.artStylePrefix, input.artStyleSuffix, input.eraArtPrefix};
    const auto result = SelectWorldUnitArt(input);
    Check(result == &ownedTag,
          "Selector lost the caller-owned tag binding");
    Check(input.type == before.type && input.unitArtInfoTag == before.unitArtInfoTag &&
          input.artStylePrefix == before.artStylePrefix && input.artStyleSuffix == before.artStyleSuffix &&
          input.eraArtPrefix == before.eraArtPrefix &&
          input.unitArtInfoCulturalVariation == before.unitArtInfoCulturalVariation &&
          input.unitArtInfoEraVariation == before.unitArtInfoEraVariation && input.embarked == before.embarked,
          "Selector modified its detached input");
}

void LiteralNonvariantArt() {
    auto custom = Warrior();
    custom.type = "UNIT_CUSTOM";
    custom.unitArtInfoTag = "ART_DEF_UNIT_CUSTOM";
    custom.artStylePrefix = "UNKNOWN";
    custom.eraArtPrefix = "FUTURE";
    // Both disabled flags are the prior nonvariant contract, including civilians.
    auto plainSettler = Settler();
    plainSettler.unitArtInfoCulturalVariation = false;
    auto plainWorker = Worker();
    plainWorker.unitArtInfoEraVariation = false;
    for (const auto& input : {Warrior(), custom, plainSettler, plainWorker}) {
        ++cases;
        Check(SelectWorldUnitArt(input.View()) == &input.unitArtInfoTag,
              "Existing nonvariant literal-tag selection changed");
    }
    auto empty = Warrior();
    empty.unitArtInfoTag = {};
    Reject(empty, "Missing nonvariant tag must remain empty");
}

void EmbarkedArt() {
    for (auto input : {Settler(), Worker(), Warrior()}) {
        input.embarked = true;
        Reject(input, "Embarked unit acquired a land model");
    }
}

void UnknownCulturesAndEras() {
    for (const auto& valid : {Settler(), Worker()}) {
        auto input = valid;
        input.artStylePrefix = "ASIAN";
        input.artStyleSuffix = "_ASIA";
        Reject(input, "Unsupported Asian tuple fell back to European art");
        input = valid;
        input.artStylePrefix = {};
        Reject(input, "Missing culture prefix was accepted");
        input = valid;
        input.artStyleSuffix = {};
        Reject(input, "Missing culture suffix was accepted");
        input = valid;
        input.artStylePrefix = "european";
        Reject(input, "Culture identity was compared loosely");
        input = valid;
        input.artStyleSuffix = "_MED";
        Reject(input, "Unapproved culture suffix acquired the initial art");
        for (const char* era : {"CLASSICAL", "INDUSTRIAL", "FUTURE", "UNKNOWN", "ancient", ""}) {
            input = valid;
            input.eraArtPrefix = era;
            Reject(input, "Unapproved or missing era acquired initial civilian art");
        }
    }
}

void IncorrectVariantFlags() {
    auto input = Settler();
    input.unitArtInfoCulturalVariation = false;
    input.unitArtInfoEraVariation = true;
    Reject(input, "Settler with Worker variation flags was accepted");
    input = Settler();
    input.unitArtInfoEraVariation = true;
    Reject(input, "Settler with two variation flags was accepted");
    input = Worker();
    input.unitArtInfoCulturalVariation = true;
    input.unitArtInfoEraVariation = false;
    Reject(input, "Worker with Settler variation flags was accepted");
    input = Worker();
    input.unitArtInfoCulturalVariation = true;
    Reject(input, "Worker with two variation flags was accepted");
    input = Warrior();
    input.unitArtInfoCulturalVariation = true;
    input.artStylePrefix = "EUROPEAN";
    input.artStyleSuffix = "_EURO";
    input.eraArtPrefix = "ANCIENT";
    Reject(input, "Unknown variant unit acquired a base model");
}

void ExactTypeAndArtIdentity() {
    for (const auto& valid : {Settler(), Worker()}) {
        auto input = valid;
        input.type = "UNIT_UNKNOWN";
        Reject(input, "Unknown variant unit type was accepted");
        input = valid;
        input.type = {};
        Reject(input, "Missing variant unit type was accepted");
        input = valid;
        input.unitArtInfoTag = "ART_DEF_UNIT__WARRIOR";
        Reject(input, "Civilian acquired Warrior art");
        input = valid;
        input.unitArtInfoTag = {};
        Reject(input, "Missing civilian art tag was accepted");
        input = valid;
        input.unitArtInfoTag = valid.type == "UNIT_SETTLER" ? "ART_DEF_UNIT__SETTLER_EURO" : "ART_DEF_UNIT__WORKER_LATE";
        Reject(input, "Unapproved culture or late tag was silently rewritten");
    }
}
}  // namespace

int main() {
    try {
        InitialVisualInputs();
        LiteralNonvariantArt();
        EmbarkedArt();
        UnknownCulturesAndEras();
        IncorrectVariantFlags();
        ExactTypeAndArtIdentity();
        std::printf("{\"status\":\"PASS_WORLD_UNIT_ART_SELECTION\",\"cases\":%u,\"checks\":%u}\n", cases, checks);
        return 0;
    } catch (const std::exception& error) {
        std::fprintf(stderr, "WORLD_UNIT_ART_SELECTION_FAILED: %s\n", error.what());
        return 1;
    }
}
