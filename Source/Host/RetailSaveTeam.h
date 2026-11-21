#pragma once

// Latest retained BNW CvTeam v1 and CvTeamTechs v1, using original Win32
// wire widths. This frames caller-owned inflated bytes without SDK or file I/O.
#include "RetailSaveStateWire.h"
#include <algorithm>
#include <cstddef>
#include <cstdint>
#include <utility>
#include <vector>

namespace ZeroSisHost {
namespace RetailStateDetail {

// CvTeam.cpp:6987-7097. Fixed fields use 2,336 bytes; the empty dynamic
// counts and nested Techs header use 88. This 2,424-byte lower bound does
// not prove any retail outer ordering, team-record count or load compatibility.
constexpr std::size_t TeamMinimumBytes = 2424u;
constexpr std::size_t TeamFixedTeams = 64;
constexpr std::size_t TeamCivilizationTeams = 63;
constexpr std::size_t TeamDomainTypes = 5;
constexpr std::size_t TeamYieldTypes = 6;

inline void ReadTeamHashBools(Reader& input) {
    // CvInfosSerializationHelper.h:247-269,554-565. A missing hash alone
    // has no value; unknown nonzero hashes still have a canonical bool byte.
    const auto count = input.Count(4);
    for (std::uint32_t i = 0; i < count; ++i)
        if (input.U32() != 0) input.Bool();
}

inline void ReadTeamSignedHashInts(Reader& input) {
    // CvInfos.cpp:1797-1898 and CvBuildingClasses.cpp:3617-3665. These
    // three legacy array helpers have signed counts, unlike generic Hashes.
    const auto count = input.SignedCount(4);
    for (std::uint32_t i = 0; i < count; ++i)
        if (input.U32() != 0) input.I32();
}

using TeamProjectCount = std::pair<std::uint32_t, std::int32_t>;
static_assert(sizeof(TeamProjectCount) == 8, "Project count index must use eight-byte entries");

inline std::vector<TeamProjectCount> ReadTeamProjectCounts(Reader& input) {
    // CvTeam.cpp:7065. Art-row lengths later depend on these values, not
    // on another length word. Count(4) budgets every hash row, including zero
    // rows; the temporary index reserves at most 8 * that bounded count bytes.
    const auto count = input.Count(4);
    std::vector<TeamProjectCount> projects;
    if (count > projects.max_size())
        input.Fail(RetailStateErrorCode::ArrayLimit, "BNW project count index exceeds capacity");
    projects.reserve(count);
    for (std::uint32_t i = 0; i < count; ++i) {
        const auto hash = input.U32();
        if (hash == 0) continue;
        const auto value = input.I32();
        if (value < 0)
            input.Fail(RetailStateErrorCode::InvalidValue, "Negative BNW project count");
        projects.emplace_back(hash, value);
    }
    std::sort(projects.begin(), projects.end(),
        [](const TeamProjectCount& left, const TeamProjectCount& right) {
            return left.first < right.first;
        });
    for (std::size_t i = 1; i < projects.size(); ++i)
        if (projects[i - 1].first == projects[i].first)
            input.Fail(RetailStateErrorCode::InvalidValue, "Duplicate BNW project count hash");
    return projects;
}

inline void ReadTeamProjectArt(Reader& input, std::vector<TeamProjectCount>& projects) {
    // CvTeam.cpp:7069-7077. A row is hash + ProjectCount[hash] int32s,
    // without its own inner count. A zero/missing hash loses the length:
    // do not guess it or copy Read's erroneous ProjectCount[-1] recovery.
    const auto rows = input.SignedCount(4);
    for (std::uint32_t i = 0; i < rows; ++i) {
        const auto hash = input.U32();
        if (hash == 0)
            input.Fail(RetailStateErrorCode::UnsupportedProfile, "BNW project art has no framing hash");
        const auto found = std::lower_bound(projects.begin(), projects.end(), hash,
            [](const TeamProjectCount& project, std::uint32_t key) {
                return project.first < key;
            });
        if (found == projects.end() || found->first != hash)
            input.Fail(RetailStateErrorCode::UnsupportedProfile, "BNW project art count is unavailable");
        if (found->second < 0)
            input.Fail(RetailStateErrorCode::InvalidValue, "Duplicate BNW project art hash");
        input.Fixed(static_cast<std::uint32_t>(found->second), 4);
        // All on-wire values were checked nonnegative. Reuse -1 internally
        // to mark a consumed hash and reject duplicate art rows without a
        // second allocation; sorting and lookup depend only on the hash.
        found->second = -1;
    }
}

inline void ReadTeamTechs(Reader& input) {
    // CvTechClasses.cpp:1782-1807; CvInfosSerializationHelper.h:471-487.
    // The five arrays have no individual count prefixes. A zero type hash
    // still owns one element in each of the four following data columns.
    input.Version(1);
    input.I32(); // Last acquired TechTypes is an int32 enum, not a type hash.
    const auto techs = input.SignedCount(14);
    input.Fixed(techs, 4); // All tech hashes, including zero hashes.
    for (std::uint32_t i = 0; i < techs; ++i) input.Bool(); // Has tech.
    for (std::uint32_t i = 0; i < techs; ++i) input.Bool(); // No-trade tech.
    input.Fixed(techs, 4); // Research progress in hundredths.
    input.Fixed(techs, 4); // Tech counts.
}

inline void ReadTeamImprovementYields(Reader& input) {
    // CvImprovementClasses.cpp:1158-1215. The inner width is the retained
    // SDK's NUM_YIELD_TYPES=6; it is not on the wire or a ruleset row count.
    // Only zero omits the values here: 0xffffffff still has six int32s.
    const auto rows = input.SignedCount(4);
    for (std::uint32_t i = 0; i < rows; ++i)
        if (input.U32() != 0) input.Fixed(TeamYieldTypes, 4);
}

inline std::int32_t ReadTeam(Reader& input) {
    // CvTeam.cpp:6990-7037. Current Team and nested Techs versions are 1.
    input.Version(1);
    input.Fixed(29, 4);
    for (unsigned i = 0; i < 8; ++i) input.Bool();
    const auto teamId = input.I32();
    input.Fixed(3, 4); // Era, liberated-by team, killed-by team (int32 enums).

    // CvTeam.h retains 80-slot storage, but these ArrayWrapperConst calls
    // write MAX_TEAMS/MAX_PLAYERS=64, without any count prefixes.
    input.Fixed(3u * TeamFixedTeams, 4); // Shares, war turns, locked war turns.
    input.Fixed(TeamDomainTypes, 4); // Extra moves; DomainTypes includes hover.
    input.Hashes(4); // Forced team-vote eligibility by VoteSourceTypes.
    input.Fixed(2u * TeamFixedTeams, 4); // Peace-treaty turns, ignored warnings.
    for (std::size_t i = 0; i < 10u * TeamFixedTeams; ++i) input.Bool();

    ReadTeamHashBools(input); // Can launch a victory.
    ReadTeamHashBools(input); // Victory achieved.
    ReadTeamHashBools(input); // Small award achieved.
    input.Hashes(4); // Route changes.
    input.Hashes(4); // Build-time changes.
    {
        auto projects = ReadTeamProjectCounts(input);
        input.Hashes(4); // Project default art types.
        ReadTeamProjectArt(input, projects);
    } // Release the bounded project index before the remaining state.
    input.Hashes(4); // Project making.
    ReadTeamSignedHashInts(input); // Unit-class counts.
    ReadTeamSignedHashInts(input); // Building-class counts.
    ReadTeamSignedHashInts(input); // Obsolete-building counts.
    input.Hashes(4); // Terrain trade counts.
    input.Hashes(4); // Victory countdowns; signed values can be sentinels.
    input.Fixed(TeamCivilizationTeams, 4); // Turn team met: MAX_CIV_TEAMS=63.

    ReadTeamTechs(input);
    ReadTeamImprovementYields(input); // All improvements.
    ReadTeamImprovementYields(input); // No fresh water.
    ReadTeamImprovementYields(input); // Fresh water.

    // CvInfosSerializationHelper.h:437-448,656-662. The original Win32
    // vector size is u32, followed only by hashes. The unadapted x64 writer's
    // size_t width is a separate ABI issue, never an alternative retail format.
    const auto resources = input.Count(4);
    input.Fixed(resources, 4);
    return teamId;
}

} // namespace RetailStateDetail
} // namespace ZeroSisHost
