#pragma once

#include <string>

namespace ZeroSisPresentation {

struct WorldUnitArtSelectionInput {
    const std::string& type;
    const std::string& unitArtInfoTag;
    bool unitArtInfoCulturalVariation = false, unitArtInfoEraVariation = false, embarked = false;
    const std::string& artStylePrefix;
    const std::string& artStyleSuffix;
    const std::string& eraArtPrefix;
};

// Returns the caller-owned tag or nullptr, never a substitute model identity.
// Referenced strings must outlive the input and any returned pointer.
// The variant mapping is grounded in the default American Ancient visual tuple.
// Other civilizations with that exact European tuple select the same original
// art. This does not implement general culture fallback or an era transition.
inline const std::string* SelectWorldUnitArt(const WorldUnitArtSelectionInput& input) noexcept {
    if (input.embarked || input.unitArtInfoTag.empty()) return nullptr;

    // Preserve the existing literal-tag policy when neither variation is enabled.
    if (!input.unitArtInfoCulturalVariation && !input.unitArtInfoEraVariation)
        return &input.unitArtInfoTag;

    if (input.artStylePrefix != "EUROPEAN" || input.artStyleSuffix != "_EURO" ||
        input.eraArtPrefix != "ANCIENT")
        return nullptr;

    if (input.type == "UNIT_SETTLER" && input.unitArtInfoTag == "ART_DEF_UNIT__SETTLER" &&
        input.unitArtInfoCulturalVariation && !input.unitArtInfoEraVariation)
        return &input.unitArtInfoTag;

    if (input.type == "UNIT_WORKER" && input.unitArtInfoTag == "ART_DEF_UNIT__WORKER" &&
        !input.unitArtInfoCulturalVariation && input.unitArtInfoEraVariation)
        return &input.unitArtInfoTag;

    return nullptr;
}

}  // namespace ZeroSisPresentation
