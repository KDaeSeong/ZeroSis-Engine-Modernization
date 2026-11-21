#pragma once
#include "UiSaveMenuContract.h"

namespace ZeroSisHost {

// The owner supplies an immutable list and a live exact-file/bundle validator.
// This does not enumerate retail saves or infer unobserved SDK preview fields.
struct UiLoadMenuCatalog final {
    enum class Profile { Unknown,OwnedCurrentExactBundleNoAdditionalContent };
    std::vector<UiSaveMenuFile> files;
    std::function<bool(const std::string&)> canLoad;
    std::function<void(const UiSaveMenuFile&)> deleteFile;
    // Only an independently verified current bundle and empty activation
    // manifest may claim that no additional DLC/mod packages are required.
    Profile profile=Profile::Unknown;
};
struct LoadMenuRequest final {
    enum class Kind { Load,Close };
    Kind kind;int owner,turn;std::string fileName;
};

}
