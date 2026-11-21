#pragma once

// Current BNW Player v16 fields after Traits, stopping before the city objects.
// This frames bytes only. It neither resolves rules nor mutates SDK state.
#include "RetailSavePlayerEspionage.h"
#include "RetailSavePlayerTrade.h"
#include "RetailSavePlayerServices.h"
#include <cstddef>

namespace ZeroSisHost {

struct RetailSavePlayerPostTraitsInspection {
    RetailInflatedSpan espionage, espionageAI, trade, tradeAI;
    RetailInflatedSpan leagueAI, culture, notifications, treasury, preCityFields;
    bool hasNotifications = false;
    std::size_t nextInflatedOffset = 0, arrayRecords = 0;
    bool completePlayerVerified = false;
    bool completeSaveVerified = false;
    bool rulesetCompatibilityVerified = false;
    bool restoreApproved = false;
};

namespace RetailStateDetail {

constexpr std::size_t PlayerPostTraitsMinimumBytes = 602u;
constexpr std::size_t PlayerPostTraitsNotificationsMinimumBytes = 4722u;

inline void ReadPlayerFieldsBeforeCities(Reader& reader) {
    // CvPlayer::Write after Treasury: two FAutoVariable<vector<Array<int,6>>>
    // values. The vector count is uint32; each row has six unprefixed ints.
    for (unsigned matrix = 0; matrix < 2; ++matrix) {
        const auto rows = reader.Count(24);
        reader.Fixed(rows, 24);
    }
    // CvUnitCycler delegates to CLinkList<int>. The research queue is
    // CLinkList<TechTypes>; both use signed int counts and four-byte values.
    const auto cycleUnits = reader.SignedCount(4);
    reader.Fixed(cycleUnits, 4);
    const auto queuedTechs = reader.SignedCount(4);
    reader.Fixed(queuedTechs, 4);
    reader.Bool(); // Ever popped a goody hut.
    reader.Bool(); // Ever trained a builder.
    reader.I32(); // EndTurnBlockingTypes, with no type-hash codec.
    reader.I32(); // Blocking notification index.
    // CLinkList<CvString> also has a signed count. String lengths are uint32
    // byte counts; content is not normalized or interpreted as native wchar_t.
    const auto cityNames = reader.SignedCount(4);
    for (std::uint32_t i = 0; i < cityNames; ++i) reader.String();
}

} // namespace RetailStateDetail

class RetailSavePlayerPostTraits {
public:
    static RetailSavePlayerPostTraitsInspection InspectAt(const unsigned char* data,
        std::size_t size, std::size_t start,
        const RetailSaveStateLimits& limits = RetailSaveStateLimits{}) {
        RetailStateDetail::Reader input(data, size, limits);
        input.Skip(start);
        RetailSavePlayerPostTraitsInspection result;
        auto begin = input.Pos();
        RetailStateDetail::ReadPlayerEspionage(input);
        result.espionage = input.SpanFrom(begin);
        begin = input.Pos();
        RetailStateDetail::ReadPlayerEspionageAI(input);
        result.espionageAI = input.SpanFrom(begin);
        begin = input.Pos();
        RetailStateDetail::ReadPlayerTrade(input);
        result.trade = input.SpanFrom(begin);
        begin = input.Pos();
        RetailStateDetail::ReadPlayerTradeAI(input);
        result.tradeAI = input.SpanFrom(begin);
        begin = input.Pos();
        RetailStateDetail::ReadPlayerLeagueAI(input);
        result.leagueAI = input.SpanFrom(begin);
        begin = input.Pos();
        RetailStateDetail::ReadPlayerCulture(input);
        result.culture = input.SpanFrom(begin);
        // CvPlayer writes this presence byte, not CvNotifications itself.
        result.hasNotifications = input.Bool();
        begin = input.Pos();
        if (result.hasNotifications) RetailStateDetail::ReadPlayerNotifications(input);
        result.notifications = input.SpanFrom(begin);
        begin = input.Pos();
        RetailStateDetail::ReadPlayerTreasury(input);
        result.treasury = input.SpanFrom(begin);
        begin = input.Pos();
        RetailStateDetail::ReadPlayerFieldsBeforeCities(input);
        result.preCityFields = input.SpanFrom(begin);
        result.nextInflatedOffset = input.Pos();
        result.arrayRecords = input.Records();
        return result;
    }
};

} // namespace ZeroSisHost
