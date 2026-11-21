#include "RetailSaveState.h"
#include "RetailSavePlot.h"
#include "RetailSaveMapTail.h"
#include <array>
#include <cstddef>
#include <cstdint>
#include <cstdio>
#include <exception>
#include <iostream>
#include <limits>
#include <stdexcept>
#include <string>
#include <vector>
#if defined(_WIN32)
#include <fcntl.h>
#include <io.h>
#endif

// One source-ordered Game/Map diagnostic over caller-owned inflated stdin.
// No serializer, layout search, file access or restore approval occurs here.
namespace {
using namespace ZeroSisHost;
using Bytes = std::vector<unsigned char>;
constexpr std::size_t MaximumInput = 64u * 1024u * 1024u;
struct Options {
    std::uint32_t awards = 0;
    std::size_t maximumInput = MaximumInput;
    RetailBooleanWireProfile booleanProfile = RetailBooleanWireProfile::CanonicalZeroOne;
    const char* booleanEncoding = "unselected";
    bool awardsDeclared = false;
    bool booleanEncodingDeclared = false;
};
struct PlotSpan {
    RetailInflatedSpan whole;
    std::uint32_t index = 0;
    std::size_t records = 0;
};
struct PlotCoordinate {
    std::size_t begin = 0, end = 0, headerBytes = 0, failureOffset = 0;
    std::uint32_t index = 0, version = 0, expectedX = 0, expectedY = 0;
    std::int32_t actualX = 0, actualY = 0;
    int failureCode = -1;
    bool expectedKnown = false, expectedInGrid = false, versionObserved = false, xyObserved = false;
    bool matches = false, completed = false, endKnown = false, failed = false;
};
struct CoordinateSummary {
    static constexpr std::size_t RecentCapacity = 4, ContextCapacity = 5;
    std::array<PlotCoordinate, RecentCapacity> recent{};
    std::array<PlotCoordinate, ContextCapacity> firstContext{};
    PlotCoordinate firstMismatch;
    std::size_t recentCount = 0, contextCount = 0, contextFollowing = 0;
    std::uint32_t attempted = 0, observed = 0, unavailable = 0, successful = 0, failures = 0;
    std::uint32_t matches = 0, mismatches = 0, successfulMismatches = 0, failureMismatches = 0, unexpectedVersions = 0;
    std::int64_t actualXSum = 0, actualYSum = 0;
    bool firstMismatchKnown = false;
};
struct Observation {
    const char* status = "DIAGNOSTIC_INPUT_OR_INTERNAL_REJECTED";
    const char* stage = "arguments";
    const char* errorDomain = "input";
    std::string errorMessage;
    RetailSaveStateInspection prefix;
    RetailInflatedSpan gameFront, gameTail;
    RetailStateDetail::MapTailInspection tail;
    std::array<PlotSpan, 2> lastPlots{};
    CoordinateSummary coordinates;
    PlotCoordinate currentCoordinate, errorCoordinate;
    std::size_t coordinateSelfChecks = 0;
    std::size_t inputBytes = 0, stdinBytesObserved = 0, stageStart = 0, currentPlotStart = 0;
    std::size_t lastCompletedOffset = 0, readerPosition = 0, recordsCompleted = 0, recordsObserved = 0;
    std::size_t errorOffset = 0;
    std::uint32_t plotCount = 0, completedPlots = 0, currentPlot = 0, retainedPlots = 0;
    std::uint32_t declaredDatabaseBytes = 0;
    int errorCode = -1;
    bool stdinReadComplete = false, prefixObserved = false, currentPlotActive = false;
    bool readerPositionObserved = false, tailObserved = false, mapObserved = false, errorOffsetKnown = false;
    bool gameFrontObserved = false, gameTailObserved = false, databaseObserved = false, mapHeaderStarted = false;
    bool coordinatePending = false, errorCoordinateObserved = false, coordinateSelfChecksPassed = false;
};
std::int32_t Signed16LE(const unsigned char* data) noexcept {
    const auto raw = static_cast<std::uint32_t>(data[0]) | (static_cast<std::uint32_t>(data[1]) << 8);
    return raw <= 0x7fffu ? static_cast<std::int32_t>(raw) : static_cast<std::int32_t>(raw) - 65536;
}
PlotCoordinate PeekPlotCoordinate(const unsigned char* data, std::size_t size, std::size_t begin,
        std::uint32_t index, std::uint32_t width, std::uint32_t height) noexcept {
    // Original CvPlot.cpp:53,9578-9582 and CvPlot.h:749-750: uint32 v7,
    // signed short X, signed short Y. This bounded peek never touches Reader.
    PlotCoordinate result; result.begin = begin; result.index = index;
    result.expectedKnown = width != 0u && height != 0u;
    if (result.expectedKnown) {
        result.expectedX = index % width; result.expectedY = index / width;
        result.expectedInGrid = result.expectedY < height;
    }
    if (!data || begin > size) return result;
    const auto available = size - begin; result.headerBytes = available < 8u ? available : 8u;
    if (available >= 4u) {
        result.version = static_cast<std::uint32_t>(data[begin]) | (static_cast<std::uint32_t>(data[begin + 1u]) << 8) |
            (static_cast<std::uint32_t>(data[begin + 2u]) << 16) | (static_cast<std::uint32_t>(data[begin + 3u]) << 24);
        result.versionObserved = true;
    }
    if (available < 8u || result.version != 7u) return result;
    result.actualX = Signed16LE(data + begin + 4u); result.actualY = Signed16LE(data + begin + 6u);
    result.xyObserved = true;
    result.matches = result.expectedKnown && result.expectedInGrid && result.actualX >= 0 && result.actualY >= 0 &&
        static_cast<std::uint32_t>(result.actualX) == result.expectedX && static_cast<std::uint32_t>(result.actualY) == result.expectedY;
    return result;
}
void RecordPlotCoordinate(CoordinateSummary& summary, const PlotCoordinate& row) noexcept {
    ++summary.attempted;
    if (row.versionObserved && row.version != 7u) ++summary.unexpectedVersions;
    const bool mismatch = row.xyObserved && row.expectedKnown && !row.matches;
    if (row.xyObserved) {
        ++summary.observed; summary.actualXSum += row.actualX; summary.actualYSum += row.actualY;
        if (row.completed) ++summary.successful;
        if (row.failed) ++summary.failures;
        if (row.matches) ++summary.matches;
        if (mismatch) {
            ++summary.mismatches;
            if (row.completed) ++summary.successfulMismatches;
            if (row.failed) ++summary.failureMismatches;
        }
    } else ++summary.unavailable;
    if (!summary.firstMismatchKnown && mismatch) {
        summary.firstMismatchKnown = true; summary.firstMismatch = row;
        const auto preceding = summary.recentCount < 2u ? summary.recentCount : 2u;
        for (std::size_t at = summary.recentCount - preceding; at < summary.recentCount; ++at)
            summary.firstContext[summary.contextCount++] = summary.recent[at];
        summary.firstContext[summary.contextCount++] = row; summary.contextFollowing = 2;
    } else if (summary.firstMismatchKnown && summary.contextFollowing != 0u) {
        if (summary.contextCount < summary.firstContext.size()) summary.firstContext[summary.contextCount++] = row;
        --summary.contextFollowing;
    }
    if (summary.recentCount < summary.recent.size()) summary.recent[summary.recentCount++] = row;
    else {
        for (std::size_t at = 1; at < summary.recent.size(); ++at) summary.recent[at - 1u] = summary.recent[at];
        summary.recent.back() = row;
    }
}
void CoordinateSelfChecks(Observation& result) {
    // Literal headers only: no Game/Map parser, Reader, stdin or source data.
    const std::array<unsigned char, 8> origin = {7,0,0,0,0,0,0,0};
    const std::array<unsigned char, 8> second = {7,0,0,0,1,0,0,0};
    const std::array<unsigned char, 8> third = {7,0,0,0,2,0,0,0};
    const std::array<unsigned char, 8> wrap = {7,0,0,0,0,0,1,0};
    const std::array<unsigned char, 8> fifth = {7,0,0,0,1,0,1,0};
    const std::array<unsigned char, 8> last = {7,0,0,0,2,0,1,0};
    const std::array<unsigned char, 8> negatives = {7,0,0,0,255,255,0,128};
    const std::array<unsigned char, 8> extrema = {7,0,0,0,0,128,255,127};
    const std::array<unsigned char, 8> otherVersion = {8,0,0,0,2,0,1,0};
    const std::array<unsigned char, 11> prefixed = {0xaa,0xbb,0xcc,7,0,0,0,2,0,1,0};
    auto check = [&](bool value, const char* message) {
        ++result.coordinateSelfChecks;
        if (!value) throw std::runtime_error(message);
    };
    auto a = PeekPlotCoordinate(origin.data(), origin.size(), 0, 0, 3, 2);
    check(a.xyObserved && a.matches && a.actualX == 0 && a.actualY == 0 && a.expectedX == 0u && a.expectedY == 0u,
        "Coordinate origin literal differs");
    auto b = PeekPlotCoordinate(second.data(), second.size(), 0, 1, 3, 2);
    check(b.matches && b.actualX == 1 && b.actualY == 0 && b.expectedX == 1u && b.expectedY == 0u, "Coordinate next-X literal differs");
    auto c = PeekPlotCoordinate(wrap.data(), wrap.size(), 0, 3, 3, 2);
    check(c.matches && c.actualX == 0 && c.actualY == 1 && c.expectedX == 0u && c.expectedY == 1u, "Coordinate row-wrap literal differs");
    auto d = PeekPlotCoordinate(last.data(), last.size(), 0, 5, 3, 2);
    check(d.matches && d.expectedX == 2u && d.expectedY == 1u && d.version == 7u, "Coordinate final-cell literal differs");
    auto negative = PeekPlotCoordinate(negatives.data(), negatives.size(), 0, 0, 3, 2);
    check(negative.xyObserved && negative.actualX == -1 && negative.actualY == -32768 && !negative.matches, "Signed coordinate literal differs");
    auto extreme = PeekPlotCoordinate(extrema.data(), extrema.size(), 0, 0, 3, 2);
    check(extreme.actualX == -32768 && extreme.actualY == 32767 && !extreme.matches, "Signed coordinate extrema differ");
    auto repeated = PeekPlotCoordinate(origin.data(), origin.size(), 0, 1, 3, 2);
    check(repeated.xyObserved && !repeated.matches && repeated.expectedX == 1u && repeated.expectedY == 0u,
        "Repeated coordinate was not observed as a mismatch");
    auto unsupported = PeekPlotCoordinate(otherVersion.data(), otherVersion.size(), 0, 5, 3, 2);
    check(unsupported.versionObserved && unsupported.version == 8u && !unsupported.xyObserved && !unsupported.matches,
        "Unsupported raw version was interpreted with the v7 coordinate layout");
    for (std::size_t cut = 0; cut < 8u; ++cut) {
        const auto shortRow = PeekPlotCoordinate(origin.data(), cut, 0, 0, 3, 2);
        check(!shortRow.xyObserved && shortRow.headerBytes == cut && shortRow.versionObserved == (cut >= 4u) &&
            (!shortRow.versionObserved || shortRow.version == 7u),
            "Short coordinate prefix escaped its byte bounds");
    }
    const auto shifted = PeekPlotCoordinate(prefixed.data(), prefixed.size(), 3, 5, 3, 2);
    check(shifted.begin == 3u && shifted.headerBytes == 8u && shifted.matches && shifted.actualX == 2 && shifted.actualY == 1,
        "Nonzero coordinate begin differs");
    check(!PeekPlotCoordinate(origin.data(), origin.size(), origin.size(), 0, 3, 2).xyObserved, "End coordinate begin was read");
    check(!PeekPlotCoordinate(origin.data(), origin.size(), origin.size() + 1u, 0, 3, 2).xyObserved, "Past-end coordinate begin was read");
    check(!PeekPlotCoordinate(origin.data(), origin.size(), (std::numeric_limits<std::size_t>::max)(), 0, 3, 2).xyObserved,
        "Overflow coordinate begin was read");
    check(!PeekPlotCoordinate(nullptr, 0, 0, 0, 3, 2).xyObserved, "Null coordinate prefix was read");
    check(!PeekPlotCoordinate(origin.data(), origin.size(), 0, 0, 0, 2).expectedKnown, "Zero-width coordinate division occurred");
    check(!PeekPlotCoordinate(origin.data(), origin.size(), 0, 0, 3, 0).expectedKnown, "Zero-height coordinate grid was assumed");
    const auto large = (std::numeric_limits<std::uint32_t>::max)();
    const auto wide = PeekPlotCoordinate(origin.data(), origin.size(), 0, large, large, large);
    check(wide.expectedKnown && wide.expectedX == 0u && wide.expectedY == 1u && wide.expectedInGrid && !wide.matches,
        "Wide coordinate arithmetic overflowed");
    const auto tall = PeekPlotCoordinate(origin.data(), origin.size(), 0, large, 1, large);
    check(tall.expectedX == 0u && tall.expectedY == large && !tall.expectedInGrid && !tall.matches,
        "Past-grid coordinate metadata differs");
    CoordinateSummary summary;
    a.completed = true; a.endKnown = true; a.end = 8; RecordPlotCoordinate(summary, a);
    repeated.completed = true; repeated.endKnown = true; repeated.end = 8; RecordPlotCoordinate(summary, repeated);
    auto thirdRow = PeekPlotCoordinate(third.data(), third.size(), 0, 2, 3, 2); thirdRow.completed = true;
    RecordPlotCoordinate(summary, thirdRow); c.completed = true; RecordPlotCoordinate(summary, c);
    auto fifthRow = PeekPlotCoordinate(fifth.data(), fifth.size(), 0, 4, 3, 2); fifthRow.completed = true; RecordPlotCoordinate(summary, fifthRow);
    check(summary.attempted == 5u && summary.observed == 5u && summary.successful == 5u && summary.matches == 4u &&
        summary.mismatches == 1u && summary.successfulMismatches == 1u && summary.actualXSum == 3 && summary.actualYSum == 2,
        "Coordinate aggregate literal totals differ");
    check(summary.firstMismatchKnown && summary.firstMismatch.index == 1u && summary.contextCount == 4u &&
        summary.firstContext[0].index == 0u && summary.firstContext[1].index == 1u &&
        summary.firstContext[2].index == 2u && summary.firstContext[3].index == 3u,
        "First coordinate mismatch context moved or grew");
    check(summary.recentCount == 4u && summary.recent[0].index == 1u && summary.recent[3].index == 4u,
        "Recent coordinate list did not retain its fixed capacity");
    negative = PeekPlotCoordinate(negatives.data(), negatives.size(), 0, 5, 3, 2);
    negative.failed = true; negative.endKnown = true; negative.end = 4;
    negative.failureCode = 9; negative.failureOffset = 4; RecordPlotCoordinate(summary, negative);
    check(summary.attempted == 6u && summary.failures == 1u && summary.failureMismatches == 1u && summary.mismatches == 2u &&
        summary.firstMismatch.index == 1u && summary.contextCount == 4u && summary.recent.back().index == 5u &&
        summary.recent.back().failureCode == 9 && summary.recent.back().failureOffset == 4u && summary.recent.back().end == 4u,
        "Failed coordinate metadata changed the first context or was not counted");
    const auto missing = PeekPlotCoordinate(origin.data(), 7, 0, 6, 3, 3); RecordPlotCoordinate(summary, missing);
    check(summary.attempted == 7u && summary.observed == 6u && summary.unavailable == 1u, "Unavailable coordinate prefix was invented");
    CoordinateSummary fullContext;
    RecordPlotCoordinate(fullContext, a); RecordPlotCoordinate(fullContext, b);
    auto lateMismatch = PeekPlotCoordinate(origin.data(), origin.size(), 0, 2, 3, 2);
    lateMismatch.completed = true; RecordPlotCoordinate(fullContext, lateMismatch);
    RecordPlotCoordinate(fullContext, c); RecordPlotCoordinate(fullContext, fifthRow); RecordPlotCoordinate(fullContext, d);
    check(fullContext.contextCount == 5u && fullContext.contextFollowing == 0u && fullContext.firstMismatch.index == 2u &&
        fullContext.firstContext[0].index == 0u && fullContext.firstContext[1].index == 1u &&
        fullContext.firstContext[2].index == 2u && fullContext.firstContext[3].index == 3u && fullContext.firstContext[4].index == 4u,
        "Five-row coordinate mismatch context did not remain bounded");
    CoordinateSummary unsupportedSummary; unsupported.failed = true; RecordPlotCoordinate(unsupportedSummary, unsupported);
    check(unsupportedSummary.unexpectedVersions == 1u && unsupportedSummary.attempted == 1u && unsupportedSummary.observed == 0u &&
        unsupportedSummary.unavailable == 1u && unsupportedSummary.matches == 0u && unsupportedSummary.mismatches == 0u,
        "Unsupported version observation incorrectly entered coordinate totals or comparisons");
    check(origin == std::array<unsigned char, 8>{7,0,0,0,0,0,0,0} && prefixed == std::array<unsigned char, 11>{0xaa,0xbb,0xcc,7,0,0,0,2,0,1,0},
        "Coordinate self-check inputs were changed");
    result.coordinateSelfChecksPassed = true;
}
std::size_t Number(const char* raw, std::size_t maximum) {
    if (!raw || !*raw) throw std::invalid_argument("Expected a nonempty unsigned decimal argument");
    std::size_t value = 0;
    for (const unsigned char* at = reinterpret_cast<const unsigned char*>(raw); *at; ++at) {
        if (*at < '0' || *at > '9') throw std::invalid_argument("Expected an unsigned decimal argument");
        const auto digit = static_cast<std::size_t>(*at - '0');
        if (value > maximum / 10u || (value == maximum / 10u && digit > maximum % 10u))
            throw std::invalid_argument("Decimal argument exceeds its supported bound");
        value = value * 10u + digit;
    }
    return value;
}
Options Arguments(int argc, char** argv) {
    Options result; bool inputDeclared = false;
    for (int index = 1; index < argc; ++index) {
        const std::string name(argv[index]);
        if (name != "--awards" && name != "--max-input" && name != "--boolean-encoding")
            throw std::invalid_argument("Only --awards, --boolean-encoding and optional --max-input are accepted");
        if (index + 1 >= argc) throw std::invalid_argument("Option is missing its argument");
        ++index;
        if (name == "--awards") {
            if (result.awardsDeclared) throw std::invalid_argument("Duplicate --awards option");
            result.awards = static_cast<std::uint32_t>(Number(argv[index], 4096u)); result.awardsDeclared = true;
        } else if (name == "--boolean-encoding") {
            if (result.booleanEncodingDeclared) throw std::invalid_argument("Duplicate --boolean-encoding option");
            const std::string encoding(argv[index]);
            if (encoding == "canonical") {
                result.booleanProfile = RetailBooleanWireProfile::CanonicalZeroOne; result.booleanEncoding = "canonical";
            } else if (encoding == "sdk-byte") {
                result.booleanProfile = RetailBooleanWireProfile::SdkRawByte; result.booleanEncoding = "sdk-byte";
            } else throw std::invalid_argument("Boolean encoding must be canonical or sdk-byte");
            result.booleanEncodingDeclared = true;
        } else {
            if (inputDeclared) throw std::invalid_argument("Duplicate --max-input option");
            result.maximumInput = Number(argv[index], MaximumInput); inputDeclared = true;
            if (result.maximumInput == 0u) throw std::invalid_argument("--max-input must be positive");
        }
    }
    if (!result.awardsDeclared) throw std::invalid_argument("Explicit --awards is required");
    if (!result.booleanEncodingDeclared) throw std::invalid_argument("Explicit --boolean-encoding is required");
    return result;
}
Bytes ReadInput(std::size_t maximum, std::size_t& observed) {
#if defined(_WIN32)
    if (_setmode(_fileno(stdin), _O_BINARY) == -1) throw std::runtime_error("Cannot select binary stdin");
#endif
    Bytes data; std::array<char, 16384> block{};
    while (std::cin.read(block.data(), static_cast<std::streamsize>(block.size())) || std::cin.gcount() > 0) {
        const auto count = std::cin.gcount();
        if (count < 0) throw std::runtime_error("Negative stdin byte count");
        const auto amount = static_cast<std::size_t>(count); observed += amount;
        if (data.size() > maximum || amount > maximum - data.size())
            throw std::runtime_error("Inflated stdin exceeds the declared input byte budget");
        data.insert(data.end(), block.data(), block.data() + count);
    }
    if (!std::cin.eof()) throw std::runtime_error("Inflated stdin read failed");
    return data;
}
void Trace(const Bytes& data, const Options& options, Observation& result) {
    result.status = "DIAGNOSTIC_MAP_PARSER_REJECTED"; result.stage = "game_front";
    result.errorDomain = "inflated_state"; result.stageStart = 0;
    auto limits = RetailSaveStateLimits{};
    limits.maxInputBytes = options.maximumInput; limits.maxPrefixBytes = options.maximumInput;
    limits.booleanWireProfile = options.booleanProfile;
    // This is the exact prefix field sequence in RetailSaveState.h. One Reader
    // retains its position and record budget through prefix, plots and tail.
    RetailStateDetail::Reader input(data.data(), data.size(), limits);
    result.readerPositionObserved = true;
    auto completed = [&] {
        result.lastCompletedOffset = result.readerPosition = input.Pos();
        result.recordsCompleted = result.recordsObserved = input.Records();
    };
    try {
        RetailStateDetail::ReadGameFront(input, RetailSaveStateProfile(options.awards));
        result.gameFront = input.SpanFrom(0); result.gameFrontObserved = true; completed();
        result.stage = "game_tail"; result.stageStart = input.Pos();
        RetailStateDetail::ReadGameTail(input);
        result.gameTail = input.SpanFrom(result.stageStart); result.gameTailObserved = true; completed();
        result.stage = "database"; result.stageStart = input.Pos();
        result.declaredDatabaseBytes = input.U32();
        if (result.declaredDatabaseBytes > limits.maxEmbeddedDatabaseBytes)
            input.Fail(RetailStateErrorCode::EmbeddedDatabaseLimit, "Embedded database exceeds byte budget");
        const auto databaseStart = input.Pos(); result.prefix.embeddedDatabase.offset = databaseStart;
        input.Skip(result.declaredDatabaseBytes);
        result.prefix.embeddedDatabase = input.SpanFrom(databaseStart);
        result.prefix.game = input.SpanFrom(0); result.databaseObserved = true; completed();
        result.stage = "map_header_fields"; result.stageStart = input.Pos();
        result.prefix.mapHeader.offset = input.Pos(); result.mapHeaderStarted = true;
        input.Version(1);
        const auto width = input.I32(), height = input.I32();
        if (width <= 0 || height <= 0)
            input.Fail(RetailStateErrorCode::InvalidValue, "Nonpositive BNW map dimensions");
        result.prefix.mapWidth = static_cast<std::uint32_t>(width);
        result.prefix.mapHeight = static_cast<std::uint32_t>(height);
        if (result.prefix.mapWidth > limits.maxMapPlots / result.prefix.mapHeight)
            input.Fail(RetailStateErrorCode::MapPlotLimit, "BNW map dimensions exceed plot budget");
        if (result.prefix.mapWidth > static_cast<std::uint32_t>((std::numeric_limits<std::int32_t>::max)()) /
                result.prefix.mapHeight)
            input.Fail(RetailStateErrorCode::MapPlotLimit, "Map grid exceeds the signed SDK wire capacity");
        result.plotCount = result.prefix.mapWidth * result.prefix.mapHeight;
        input.Fixed(5, 4); completed();
        result.stage = "map_wrap_x"; result.stageStart = input.Pos(); input.Bool(); completed();
        result.stage = "map_wrap_y"; result.stageStart = input.Pos(); input.Bool(); completed();
        result.stage = "map_guid"; result.stageStart = input.Pos(); input.Skip(16); completed();
        result.stage = "map_resources"; result.stageStart = input.Pos(); input.Hashes(4); input.Hashes(4); completed();
        result.prefix.mapHeader = input.SpanFrom(result.prefix.mapHeader.offset);
        result.prefix.nextInflatedOffset = input.Pos(); result.prefix.arrayRecords = input.Records();
        result.prefixObserved = true;
        result.stage = "plots";
        for (std::uint32_t plot = 0; plot < result.plotCount; ++plot) {
            result.currentPlot = plot; result.currentPlotActive = true;
            result.currentPlotStart = result.stageStart = input.Pos(); const auto before = input.Records();
            result.currentCoordinate = PeekPlotCoordinate(data.data(), data.size(), result.currentPlotStart, plot,
                result.prefix.mapWidth, result.prefix.mapHeight);
            result.coordinatePending = true;
            RetailStateDetail::ReadMapPlot(input);
            result.currentCoordinate.completed = true; result.currentCoordinate.endKnown = true; result.currentCoordinate.end = input.Pos();
            RecordPlotCoordinate(result.coordinates, result.currentCoordinate); result.coordinatePending = false;
            PlotSpan row; row.index = plot; row.whole = input.SpanFrom(result.currentPlotStart); row.records = input.Records() - before;
            if (result.retainedPlots < 2u) {
                result.lastPlots[result.retainedPlots] = row; ++result.retainedPlots;
            } else { result.lastPlots[0] = result.lastPlots[1]; result.lastPlots[1] = row; }
            ++result.completedPlots; completed();
        }
        result.currentPlotActive = false; result.stage = "map_tail"; result.stageStart = input.Pos();
        result.tail = RetailStateDetail::ReadMapTail(input); result.tailObserved = true;
        completed();
        result.mapObserved = true; result.stage = "complete"; result.errorDomain = "none";
        result.status = "DIAGNOSTIC_MAP_WIRE_OBSERVED";
    } catch (const RetailStateError& error) {
        if (result.currentPlotActive && result.coordinatePending) {
            result.currentCoordinate.failed = true; result.currentCoordinate.endKnown = true; result.currentCoordinate.end = input.Pos();
            result.currentCoordinate.failureCode = static_cast<int>(error.Code()); result.currentCoordinate.failureOffset = error.Offset();
            result.errorCoordinate = result.currentCoordinate; result.errorCoordinateObserved = true;
            RecordPlotCoordinate(result.coordinates, result.currentCoordinate); result.coordinatePending = false;
        }
        result.readerPosition = input.Pos(); result.recordsObserved = input.Records();
        if (!result.prefixObserved) result.prefix.arrayRecords = input.Records();
        if (result.mapHeaderStarted && !result.prefixObserved)
            result.prefix.mapHeader = input.SpanFrom(result.prefix.mapHeader.offset);
        throw;
    }
}
const char* Boolean(bool value) { return value ? "true" : "false"; }
void Text(const std::string& raw) {
    std::cout << '"';
    for (const char value : raw) {
        const auto ch = static_cast<unsigned char>(value);
        if (ch == '"' || ch == '\\') std::cout << '\\';
        std::cout << (ch < 32 ? '?' : static_cast<char>(ch));
    }
    std::cout << '"';
}
void Span(const RetailInflatedSpan& value) {
    std::cout << "{\"offset\":" << value.offset << ",\"bytes\":" << value.bytes << '}';
}
void Coordinate(const PlotCoordinate& row) {
    std::cout << "{\"index\":" << row.index << ",\"begin\":" << row.begin << ",\"end\":";
    if (row.endKnown) std::cout << row.end; else std::cout << "null";
    std::cout << ",\"end_is_complete_boundary\":" << Boolean(row.completed)
        << ",\"header_bytes_available\":" << row.headerBytes << ",\"raw_version\":";
    if (row.versionObserved) std::cout << row.version; else std::cout << "null";
    std::cout << ",\"version7_observed\":" << Boolean(row.versionObserved && row.version == 7u) << ",\"actual\":";
    if (row.xyObserved) std::cout << "{\"x\":" << row.actualX << ",\"y\":" << row.actualY << '}'; else std::cout << "null";
    std::cout << ",\"expected\":";
    if (row.expectedKnown)
        std::cout << "{\"x\":" << row.expectedX << ",\"y\":" << row.expectedY << ",\"in_grid\":" << Boolean(row.expectedInGrid) << '}';
    else std::cout << "null";
    std::cout << ",\"matches_expected\":";
    if (row.xyObserved && row.expectedKnown) std::cout << Boolean(row.matches); else std::cout << "null";
    std::cout << ",\"plot_read_completed\":" << Boolean(row.completed) << ",\"plot_read_failed\":" << Boolean(row.failed)
        << ",\"failure\":";
    if (row.failed) std::cout << "{\"code\":" << row.failureCode << ",\"offset\":" << row.failureOffset << '}'; else std::cout << "null";
    std::cout << '}';
}
void Coordinates(const Observation& result) {
    const auto& value = result.coordinates;
    std::cout << "{\"observation_only\":true,\"fixed_layout\":\"CvPlot-v7-u32-i16x-i16y\""
        << ",\"expected_order\":\"x=index%width,y=index/width\",\"attempted_plots\":" << value.attempted
        << ",\"xy_observed\":" << value.observed << ",\"successful_plot_coordinates\":" << value.successful
        << ",\"failed_plot_coordinates\":" << value.failures << ",\"xy_unavailable\":" << value.unavailable
        << ",\"matching_coordinates\":" << value.matches << ",\"mismatching_coordinates\":" << value.mismatches
        << ",\"successful_plot_mismatches\":" << value.successfulMismatches << ",\"failed_plot_mismatches\":" << value.failureMismatches
        << ",\"unexpected_raw_versions\":" << value.unexpectedVersions << ",\"actual_x_sum\":" << value.actualXSum
        << ",\"actual_y_sum\":" << value.actualYSum << ",\"recent_capacity\":" << CoordinateSummary::RecentCapacity
        << ",\"first_context_capacity\":" << CoordinateSummary::ContextCapacity << ",\"first_mismatch\":";
    if (value.firstMismatchKnown) Coordinate(value.firstMismatch); else std::cout << "null";
    std::cout << ",\"first_mismatch_context\":[";
    for (std::size_t index = 0; index < value.contextCount; ++index) {
        if (index) std::cout << ',';
        Coordinate(value.firstContext[index]);
    }
    std::cout << "],\"recent\":[";
    for (std::size_t index = 0; index < value.recentCount; ++index) {
        if (index) std::cout << ',';
        Coordinate(value.recent[index]);
    }
    std::cout << "],\"error_plot\":";
    if (result.errorCoordinateObserved) Coordinate(result.errorCoordinate); else std::cout << "null";
    std::cout << ",\"coordinate_rejection_used\":false,\"reader_mutated_by_coordinate_helpers\":false}";
}
void Print(const Options& options, const Observation& result) {
    std::cout << "{\"schema\":\"zerosis.retail.map_trace.v1\",\"mode\":\"map_trace\",\"status\":\"" << result.status
        << "\",\"stage\":\"" << result.stage << "\",\"stage_start\":" << result.stageStart
        << ",\"profiles\":{\"awards\":" << options.awards << ",\"widths_explicit\":" << Boolean(options.awardsDeclared)
        << ",\"boolean_encoding\":\"" << options.booleanEncoding << "\",\"boolean_encoding_explicit\":" << Boolean(options.booleanEncodingDeclared) << '}'
        << ",\"maximum_input_bytes\":" << options.maximumInput << ",\"stdin_read_complete\":" << Boolean(result.stdinReadComplete)
        << ",\"coordinate_self_checks_passed\":" << Boolean(result.coordinateSelfChecksPassed)
        << ",\"coordinate_self_checks\":" << result.coordinateSelfChecks
        << ",\"stdin_bytes_observed\":" << result.stdinBytesObserved << ",\"input_bytes\":";
    if (result.stdinReadComplete) std::cout << result.inputBytes; else std::cout << "null";
    std::cout << ",\"prefix_observed\":" << Boolean(result.prefixObserved) << ",\"prefix\":{\"complete\":" << Boolean(result.prefixObserved)
        << ",\"game_front_complete\":" << Boolean(result.gameFrontObserved) << ",\"game_front\":"; Span(result.gameFront);
    std::cout << ",\"game_tail_complete\":" << Boolean(result.gameTailObserved) << ",\"game_tail\":"; Span(result.gameTail);
    std::cout << ",\"database_complete\":" << Boolean(result.databaseObserved)
        << ",\"declared_database_bytes\":" << result.declaredDatabaseBytes << ",\"game\":"; Span(result.prefix.game);
    std::cout << ",\"embedded_database\":"; Span(result.prefix.embeddedDatabase);
    std::cout << ",\"map_header_started\":" << Boolean(result.mapHeaderStarted) << ",\"map_header_complete\":" << Boolean(result.prefixObserved)
        << ",\"map_header\":"; Span(result.prefix.mapHeader);
    std::cout << ",\"next_offset\":";
    if (result.prefixObserved) std::cout << result.prefix.nextInflatedOffset; else std::cout << "null";
    std::cout << ",\"width\":" << result.prefix.mapWidth << ",\"height\":" << result.prefix.mapHeight
        << ",\"array_records\":" << result.prefix.arrayRecords << '}';
    std::cout << ",\"plot_count\":" << result.plotCount << ",\"plots_completed\":" << result.completedPlots
        << ",\"current_plot\":";
    if (result.currentPlotActive) std::cout << result.currentPlot; else std::cout << "null";
    std::cout << ",\"current_plot_start\":";
    if (result.currentPlotActive) std::cout << result.currentPlotStart; else std::cout << "null";
    std::cout << ",\"last_completed_offset\":" << result.lastCompletedOffset << ",\"reader_position\":";
    if (result.readerPositionObserved) std::cout << result.readerPosition; else std::cout << "null";
    std::cout << ",\"array_records_completed\":" << result.recordsCompleted << ",\"array_records_observed\":" << result.recordsObserved
        << ",\"last_completed_plots\":[";
    for (std::uint32_t index = 0; index < result.retainedPlots; ++index) {
        const auto& plot = result.lastPlots[index]; if (index) std::cout << ',';
        std::cout << "{\"index\":" << plot.index << ",\"span\":"; Span(plot.whole);
        std::cout << ",\"array_records\":" << plot.records << '}';
    }
    std::cout << "],\"coordinate_diagnostic\":"; Coordinates(result);
    std::cout << ",\"map_tail_observed\":" << Boolean(result.tailObserved) << ",\"map_tail\":";
    if (result.tailObserved) {
        std::cout << "{\"areas\":"; Span(result.tail.areas);
        std::cout << ",\"landmasses\":"; Span(result.tail.landmasses);
        std::cout << ",\"area_count\":" << result.tail.areaCount << ",\"landmass_count\":" << result.tail.landmassCount << '}';
    } else std::cout << "null";
    std::cout << ",\"map_wire_framed\":" << Boolean(result.mapObserved) << ",\"error_domain\":\"" << result.errorDomain
        << "\",\"error_code\":";
    if (result.errorCode >= 0) std::cout << result.errorCode; else std::cout << "null";
    std::cout << ",\"error_offset\":";
    if (result.errorOffsetKnown) std::cout << result.errorOffset; else std::cout << "null";
    std::cout << ",\"error_relative_to_current_plot\":";
    if (result.errorOffsetKnown && result.currentPlotActive && result.errorOffset >= result.currentPlotStart)
        std::cout << result.errorOffset - result.currentPlotStart;
    else std::cout << "null";
    std::cout << ",\"error_message\":"; Text(result.errorMessage);
    std::cout << ",\"error\":{\"domain\":\"" << result.errorDomain << "\",\"code\":";
    if (result.errorCode >= 0) std::cout << result.errorCode; else std::cout << "null";
    std::cout << ",\"offset\":";
    if (result.errorOffsetKnown) std::cout << result.errorOffset; else std::cout << "null";
    std::cout << ",\"stage_start\":" << result.stageStart << ",\"message\":"; Text(result.errorMessage); std::cout << '}';
    std::cout << ",\"automatic_profile_retry\":false,\"signature_search_used\":false,\"automatic_bool_relaxation_used\":false"
        << ",\"gamecore_loaded\":false,\"window_created\":false,\"game_accessed\":false,\"user_saves_accessed\":false"
        << ",\"complete_player_validated\":false,\"complete_save_validated\":false,\"complete_save_verified\":false"
        << ",\"ruleset_compatibility_verified\":false,\"restore_approved\":false,\"full_engine_goal_complete\":false}\n";
}
} // namespace

int main(int argc, char** argv) {
    static_assert(sizeof(void*) == 8, "Map trace requires an x64 executable");
    Options options; Observation result; int exitCode = 1;
    try {
        options = Arguments(argc, argv); result.stage = "coordinate_self_checks"; result.errorDomain = "internal_diagnostic";
        CoordinateSelfChecks(result);
        result.stage = "stdin"; result.errorDomain = "input";
        const auto input = ReadInput(options.maximumInput, result.stdinBytesObserved);
        result.inputBytes = input.size(); result.stdinReadComplete = true;
        Trace(input, options, result); exitCode = 0;
    } catch (const RetailStateError& error) {
        result.errorCode = static_cast<int>(error.Code()); result.errorOffset = error.Offset();
        result.errorOffsetKnown = true; result.errorMessage = error.what();
    } catch (const std::exception& error) { result.errorMessage = error.what(); }
    Print(options, result); return exitCode;
}
