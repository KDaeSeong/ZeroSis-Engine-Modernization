#pragma once
#include <array>
#include <cstdint>
#include <functional>
#include <memory>
#include <string>
#include <vector>

namespace ZeroSisHost {

// Immutable owner-thread snapshot supplied before the original SaveMenu opens.
// Unknown archive headers remain absent; UI preview must never invent SDK state.
struct UiSaveMenuHeader final {
    int playerCivilization=-1,gameSpeed=-1,startEra=-1,turnNumber=0;
    int difficulty=-1,worldSize=-1,currentEra=-1,gameType=-1;
    std::string mapScript,leaderName,civilizationName;
};
struct UiSaveMenuFile final {
    std::string fileName,modificationTime;
    std::shared_ptr<const UiSaveMenuHeader> header;
    // Keep FILETIME halves exact across the Lua-number boundary. These are
    // catalog observations only, not additional serialized archive fields.
    std::uint32_t modificationTimeHigh=0,modificationTimeLow=0;
    // Catalog observations only. Never serialized or exposed as preview fields.
    std::array<std::uint32_t,3> observedFileIdentity{};
    std::array<unsigned char,32> observedChecksum{};
};
inline bool SameUiSaveMenuHeader(const UiSaveMenuHeader& left,const UiSaveMenuHeader& right){
    return left.playerCivilization==right.playerCivilization && left.gameSpeed==right.gameSpeed &&
        left.startEra==right.startEra && left.turnNumber==right.turnNumber && left.difficulty==right.difficulty &&
        left.worldSize==right.worldSize && left.currentEra==right.currentEra && left.gameType==right.gameType &&
        left.mapScript==right.mapScript && left.leaderName==right.leaderName && left.civilizationName==right.civilizationName;
}
inline bool SameUiSaveMenuObservation(const UiSaveMenuFile& left,const UiSaveMenuFile& right){
    return left.fileName==right.fileName && left.modificationTime==right.modificationTime &&
        left.modificationTimeHigh==right.modificationTimeHigh && left.modificationTimeLow==right.modificationTimeLow &&
        left.observedFileIdentity==right.observedFileIdentity && left.observedChecksum==right.observedChecksum &&
        !!left.header==!!right.header && (!left.header || SameUiSaveMenuHeader(*left.header,*right.header));
}
struct UiSaveMenuCatalog final {
    std::vector<UiSaveMenuFile> files;
    UiSaveMenuHeader current;
    std::function<bool(const std::string&)> nameAvailable;
    // Optional owned-file service. It revalidates the complete observation on
    // one exclusive handle before deleting; it never receives an unlisted path.
    std::function<void(const UiSaveMenuFile&)> deleteFile;
    // Capability only. SDK capture and replacement run after both original
    // menu lifetimes have ended, never inside the Lua callback.
    bool overwriteSupported=false;
};
struct SaveMenuRequest final {
    enum class Kind { Save,Close,Overwrite };
    Kind kind;int owner,turn;std::string name;
    // Own an independent complete observation across child Lua destruction.
    // Save and Close never carry an overwrite target.
    std::shared_ptr<const UiSaveMenuFile> expected;
};

}
