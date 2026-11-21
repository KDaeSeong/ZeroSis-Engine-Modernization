#pragma once

// BNW wire authority: CvGame.cpp:9431-9435 and the corresponding serializers in
// CvDealClasses, CvReligionClasses, CvBeliefClasses, CvCultureClasses,
// CvVotingClasses and CvTradeClasses. This is a bounded metadata/state walker,
// not an SDK object loader. Each nested serializer has its own version word.
// The embedded database size word belongs to the caller, after ReadGameTail.
#include "RetailSaveStateWire.h"
#include <cstddef>
#include <cstdint>

namespace ZeroSisHost {
namespace RetailStateDetail {

// Minimum sizes include every version/count/string-length word, but no array
// elements or string payloads. They are wire sizes, not sizeof(native objects).
constexpr std::size_t TailTradedItemMinimum = 35;
constexpr std::size_t TailDealMinimum = 47;
constexpr std::size_t TailReligionMinimum = 270;
constexpr std::size_t TailGreatWorkMinimum = 28;
constexpr std::size_t TailEnactMinimum = 155;
constexpr std::size_t TailActiveResolutionMinimum = 151;
constexpr std::size_t TailRepealMinimum = 175;
constexpr std::size_t TailLeagueMinimum = 194;
constexpr std::size_t TailLeagueMemberMinimum = 27;
constexpr std::size_t TailLeagueProjectMinimum = 10;
constexpr std::size_t TailTradeConnectionMinimum = 109;

// CvDLLUtilDefines.h fixes MAX_MAJOR_CIVS at 22. Expansion2/CvGameCoreEnums.h
// enumerates food, production, gold, science, culture and faith before its
// NUM_YIELD_TYPES sentinel. This reader does not infer either value from IDs.
constexpr std::size_t TailMajorCivilizations = 22;
constexpr std::size_t TailYieldTypes = 6;

inline void ReadTailTradedItem(Reader& input) {
    input.Version(2);
    // Item type, duration, final turn, data1, data2, data3.
    input.Fixed(6, 4);
    input.Bool(); // Flag1.
    input.I32();  // From player.
    input.Bool(); // From renewed.
    input.Bool(); // To renewed.
}

inline void ReadTailDeal(Reader& input) {
    input.Version(3);
    // From/to players, final turn, duration, start turn.
    input.Fixed(5, 4);
    input.Bool(); // Considering for renewal.
    input.Bool(); // Checked for renewal.
    input.Bool(); // Cancelled.
    // Peace treaty, surrendering, demanding and requesting players.
    input.Fixed(4, 4);
    const auto items = input.SignedCount(TailTradedItemMinimum);
    for (std::uint32_t i = 0; i < items; ++i) ReadTailTradedItem(input);
}

inline void ReadTailGameDeals(Reader& input) {
    input.Version(1);
    // Proposed, current and historical lists use the same independently
    // versioned Deal representation. OldLoad is deliberately unsupported.
    for (unsigned int group = 0; group < 3; ++group) {
        const auto deals = input.SignedCount(TailDealMinimum);
        for (std::uint32_t i = 0; i < deals; ++i) ReadTailDeal(input);
    }
}

inline void ReadTailReligionBeliefs(Reader& input) {
    input.Version(2);
    // 22 integral modifiers, followed by faith-building tourism (added in v2).
    input.Fixed(23, 4);
    // Obsolete era, revealed resource and spread-doubling technology.
    input.Fixed(3, 4);
    const auto beliefs = input.Count(4);
    input.Fixed(beliefs, 4); // One type hash per selected belief.

    // BuildingClassArrayHelpers::Read uses a signed entry count. A zero hash
    // has no value; unknown nonzero hashes still retain a 4-byte int value.
    const auto buildings = input.SignedCount(4);
    for (std::uint32_t i = 0; i < buildings; ++i) {
        if (input.U32() != 0) input.I32();
    }
}

inline void ReadTailReligion(Reader& input) {
    input.Version(4);
    // Religion, founder, holy-city x/y, turn founded.
    input.Fixed(5, 4);
    input.Bool(); // Pantheon.
    input.Bool(); // Enhanced.
    input.Fixed(128, 1); // char customName[128], no length word or NUL scan.
    ReadTailReligionBeliefs(input);
}

inline void ReadTailGameReligions(Reader& input) {
    input.Version(4);
    input.I32(); // Minimum faith for the next pantheon.
    const auto religions = input.SignedCount(TailReligionMinimum);
    for (std::uint32_t i = 0; i < religions; ++i) ReadTailReligion(input);
}

inline void ReadTailGreatWork(Reader& input) {
    input.Version(3);
    input.String(); // Great person name, not the removed v1 great-work name.
    // Work type, class, founding turn, era and player.
    input.Fixed(5, 4);
}

inline void ReadTailGameCulture(Reader& input) {
    input.Version(2);
    const auto works = input.SignedCount(TailGreatWorkMinimum);
    for (std::uint32_t i = 0; i < works; ++i) ReadTailGreatWork(input);
    input.Bool(); // Reported someone influential.
}

inline void ReadTailResolutionDecision(Reader& input) {
    input.Version(1);
    input.I32(); // Resolution decision type.
}

inline void ReadTailPlayerVote(Reader& input) {
    input.Version(1);
    input.Fixed(3, 4); // Player, number of votes, choice.
}

inline void ReadTailVoterDecision(Reader& input) {
    ReadTailResolutionDecision(input);
    input.Version(1);
    const auto votes = input.SignedCount(16);
    for (std::uint32_t i = 0; i < votes; ++i) ReadTailPlayerVote(input);
}

inline void ReadTailProposerDecision(Reader& input) {
    ReadTailResolutionDecision(input);
    input.Version(1);
    ReadTailPlayerVote(input);
}

inline void ReadTailResolutionEffects(Reader& input) {
    input.Version(9);
    input.Bool(); // Diplomatic victory.
    input.Bool(); // Change league host.
    input.Fixed(2, 4); // One-time gold and gold percent.
    input.Bool(); // Raise city-state influence to neutral.
    input.I32(); // Enabled league project.
    input.Fixed(2, 4); // Gold per turn, resource quantity.
    input.Bool(); // Embargo city states.
    input.Bool(); // Embargo player.
    input.Bool(); // Disable resource happiness.
    // Unit maintenance, discovered-tech modifier, culture/wonder and
    // culture/natural wonder. No native alignment precedes the next bool.
    input.Fixed(4, 4);
    input.Bool(); // Disable nuclear-weapon training.
    // Religion votes, holy-city tourism, religion-spread strength (v9).
    input.Fixed(3, 4);
    input.Fixed(2, 4); // Ideology votes and other-ideology rebellion.
    input.Fixed(2, 4); // Artsy and sciencey great-person rate modifiers.
    input.Fixed(2, 4); // Great-person improvement and landmark culture.
}

inline void ReadTailResolution(Reader& input) {
    input.Version(2);
    input.Fixed(3, 4); // Unique ID, resolution type, league.
    ReadTailResolutionEffects(input);
    ReadTailVoterDecision(input);
    ReadTailProposerDecision(input);
}

inline void ReadTailProposal(Reader& input) {
    ReadTailResolution(input);
    input.Version(1);
    input.I32(); // Proposing player.
}

inline void ReadTailEnactProposal(Reader& input) {
    ReadTailProposal(input);
    input.Version(1);
}

inline void ReadTailActiveResolution(Reader& input) {
    ReadTailResolution(input);
    input.Version(2); // Legacy v1 also contained a now-moved ID word.
    input.I32(); // Turn enacted.
}

inline void ReadTailRepealProposal(Reader& input) {
    ReadTailProposal(input);
    input.Version(1);
    input.I32(); // Target resolution ID.
    ReadTailVoterDecision(input);
}

inline void ReadTailLeagueMember(Reader& input) {
    // This embedded record follows League14, without a separate version.
    input.Fixed(2, 4); // Player and extra votes.
    input.String(); // Vote sources.
    input.Bool(); // May propose.
    input.Fixed(3, 4); // Proposals, votes, abstained votes.
    input.Bool(); // Ever been host.
    input.Bool(); // Always been host.
}

inline void ReadTailLeagueProject(Reader& input) {
    // This embedded record also follows the enclosing League14 version.
    input.I32(); // Project type.
    const auto contributions = input.SignedCount(4);
    // ProjectProductionList can grow beyond its initial inline capacity.
    // The writer emits its actual size; the shared record budgets apply here.
    input.Fixed(contributions, 4);
    input.Bool(); // Complete.
    input.Bool(); // Progress warning sent.
}

inline void ReadTailEnactProposals(Reader& input) {
    const auto count = input.SignedCount(TailEnactMinimum);
    for (std::uint32_t i = 0; i < count; ++i) ReadTailEnactProposal(input);
}

inline void ReadTailRepealProposals(Reader& input) {
    const auto count = input.SignedCount(TailRepealMinimum);
    for (std::uint32_t i = 0; i < count; ++i) ReadTailRepealProposal(input);
}

inline void ReadTailLeague(Reader& input) {
    input.Version(14);
    input.I32(); // League ID.
    input.Bool(); // United Nations.
    input.Bool(); // In session.
    input.Fixed(2, 4); // Turns until session, total resolutions enacted.
    ReadTailEnactProposals(input);
    ReadTailRepealProposals(input);
    const auto active = input.SignedCount(TailActiveResolutionMinimum);
    for (std::uint32_t i = 0; i < active; ++i) ReadTailActiveResolution(input);
    const auto members = input.SignedCount(TailLeagueMemberMinimum);
    for (std::uint32_t i = 0; i < members; ++i) ReadTailLeagueMember(input);
    input.I32(); // Host.
    const auto projects = input.SignedCount(TailLeagueProjectMinimum);
    for (std::uint32_t i = 0; i < projects; ++i) ReadTailLeagueProject(input);
    input.Fixed(2, 4); // Consecutive hosted sessions, assigned name.
    input.Fixed(128, 1); // char customName[128].
    input.Fixed(2, 4); // Last/current special session.
    ReadTailEnactProposals(input); // On hold.
    ReadTailRepealProposals(input); // On hold.
}

inline void ReadTailGameLeagues(Reader& input) {
    input.Version(5);
    input.I32(); // Generated ID count.
    const auto leagues = input.SignedCount(TailLeagueMinimum);
    for (std::uint32_t i = 0; i < leagues; ++i) ReadTailLeague(input);
    // Number ever founded, diplomatic victor, last era trigger.
    input.Fixed(3, 4);
}

inline void ReadTailTradeConnection(Reader& input) {
    // GameTrade3 supplies the version for each embedded connection.
    input.I32(); // Connection ID.
    // Origin x/y, destination x/y, origin/destination owner, domain,
    // connection type, and trade-unit location index.
    input.Fixed(9, 4);
    input.Bool(); // Moving forward.
    // Unit ID, circuits completed, circuits required, route-completion turn.
    input.Fixed(4, 4);
    const auto plots = input.SignedCount(8);
    input.Fixed(plots, 8); // Each path point is x/y int32; no UI display cap.
    input.Fixed(TailYieldTypes, 8); // Interleaved origin/destination yield.
}

inline void ReadTailGameTrade(Reader& input) {
    input.Version(3);
    const auto connections = input.SignedCount(TailTradeConnectionMinimum);
    for (std::uint32_t i = 0; i < connections; ++i) ReadTailTradeConnection(input);
    input.Fixed(TailMajorCivilizations * TailMajorCivilizations, 4);
    input.I32(); // Next connection ID.
}

inline void ReadGameTail(Reader& input) {
    ReadTailGameDeals(input);
    ReadTailGameReligions(input);
    ReadTailGameCulture(input);
    ReadTailGameLeagues(input);
    ReadTailGameTrade(input);
    // Stop before CvGame's embedded-database size. The caller indexes its
    // length-prefixed span and then validates the following Map prefix.
}

} // namespace RetailStateDetail
} // namespace ZeroSisHost
