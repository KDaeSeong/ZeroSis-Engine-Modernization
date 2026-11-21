// Actual SDK FDataStream/FMemoryStream + exact extracted vector-writer bodies.
// The generated header is authenticated by the external build wrapper against
// the four original/candidate SDK templates; this test never includes GameCore.
// TestHooks replaces only type-name/hash resolution with deterministic markers.
// It does not validate real database hashes, retail placement, or game restore.
#include "SdkStreamIncludes.h"
#include <cstddef>
#include <stdexcept>

#ifdef _WIN64
#include "../Source/Porting/CvCheckedNarrow.h"
#include "../Source/Host/RetailSaveSupporting.h"
#include "../Source/Host/RetailSaveTeam.h"
#include "../Source/Host/RetailSaveMap.h"
#include <fcntl.h>
#include <io.h>
#endif

namespace TestHooks {
bool Write(FDataStream& stream, int type) {
    const unsigned int marker = type == 1 ? 0u :
        0xa1000000u | (static_cast<unsigned int>(type) & 0x00ffffffu);
    stream << marker;
    return type != 1;
}
bool WriteHashed(FDataStream& stream, int type) {
    const unsigned int marker = type == 1 ? 0u :
        0xb2000000u | (static_cast<unsigned int>(type) & 0x00ffffffu);
    stream << marker;
    return type != 1;
}
}

// Must follow TestHooks so each exact namespace can import the stand-in hooks.
#include "SdkTypeArrayWriters.h"

namespace {
typedef std::vector<unsigned char> WireBytes;
struct Checks {
    unsigned long checks, supportingChecks, supportingTruncations;
    Checks() : checks(0), supportingChecks(0), supportingTruncations(0) {}
    void Require(bool value, const char* message) {
        ++checks;
        if (!value) throw std::runtime_error(message);
    }
    void Supporting(bool value, const char* message) {
        ++supportingChecks; Require(value, message);
    }
};

// Keep this translation unit's x86 branch compatible with the original VC9.
#define DECLARE_WRITER_DISPATCH(Name, Scope) \
struct Name { \
    static void Run(unsigned int kind, FDataStream& stream, const std::vector<int>& values) { \
        switch (kind) { \
        case 0: Scope::WriteDataArray<int, int>(stream, values); break; \
        case 1: Scope::WriteHashedDataArray<int, int>(stream, values); break; \
        case 2: Scope::WriteTypeArray<int>(stream, values); break; \
        case 3: Scope::WriteHashedTypeArray<int>(stream, values); break; \
        default: throw std::logic_error("Unknown writer test kind"); \
        } \
    } \
};
DECLARE_WRITER_DISPATCH(OriginalDispatch, OriginalWriter)
#ifdef _WIN64
DECLARE_WRITER_DISPATCH(CandidateDispatch, CandidateWriter)
DECLARE_WRITER_DISPATCH(Legacy64Dispatch, Legacy64Writer)
#endif
#undef DECLARE_WRITER_DISPATCH

void Append32(WireBytes& bytes, unsigned int value) {
    for (unsigned int i = 0; i < 4; ++i)
        bytes.push_back(static_cast<unsigned char>(value >> (8 * i)));
}
WireBytes OraclePayload(unsigned int kind, const std::vector<int>& values) {
    WireBytes expected;
    for (std::size_t i = 0; i < values.size(); ++i) {
        // Literal stand-in contract, independent of either SDK writer body.
        const int identity = kind < 2 ? static_cast<int>(i) : values[i];
        const unsigned int tag = (kind == 1 || kind == 3) ? 0xb2000000u : 0xa1000000u;
        Append32(expected, identity == 1 ? 0u : tag | (static_cast<unsigned int>(identity) & 0x00ffffffu));
        if (kind < 2 && identity != 1) Append32(expected, static_cast<unsigned int>(values[i]));
    }
    return expected;
}
struct FamilyResult {
    unsigned int countBytes;
    std::vector<WireBytes> payloads;
    FamilyResult() : countBytes(0) {}
};
template<class Dispatch>
FamilyResult TestFamily(Checks& checks, unsigned int expectedCountBytes) {
    FamilyResult family;
    std::vector< std::vector<int> > cases(3);
    cases[1].push_back(-17);
    cases[2].push_back(-1); cases[2].push_back(1);
    cases[2].push_back(0x01234567); cases[2].push_back(-123456789);
    for (unsigned int kind = 0; kind < 4; ++kind) {
        for (std::size_t row = 0; row < cases.size(); ++row) {
            const std::vector<int>& values = cases[row];
            const std::vector<int> immutable(values);
            const WireBytes payload = OraclePayload(kind, values);
            FMemoryStream stream;
            Dispatch::Run(kind, stream, values);
            const unsigned int writerEnd = stream.GetEOF();
            checks.Require(stream.GetPosition() == writerEnd, "Writer cursor differs from EOF");
            checks.Require(writerEnd >= payload.size(), "Writer shorter than independently expected payload");
            const unsigned int measured = writerEnd - static_cast<unsigned int>(payload.size());
            checks.Require(measured == expectedCountBytes, "Wrong actual SDK count width");
            if (!family.countBytes) family.countBytes = measured;
            checks.Require(measured == family.countBytes, "Count width differs across vector cases");

            WireBytes literal;
            // The canonical count oracle is four little-endian bytes. The
            // negative control deliberately has four additional zero bytes.
            literal.push_back(static_cast<unsigned char>(values.size()));
            literal.push_back(0); literal.push_back(0); literal.push_back(0);
            if (expectedCountBytes == 8) {
                literal.push_back(0); literal.push_back(0); literal.push_back(0); literal.push_back(0);
            }
            literal.insert(literal.end(), payload.begin(), payload.end());
            checks.Require(writerEnd == literal.size(), "Writer extent differs from literal wire oracle");
            checks.Require(std::memcmp(stream.GetBuf(), &literal[0], literal.size()) == 0,
                "Exact writer bytes differ from independent count/payload oracle");
            const unsigned char* written = reinterpret_cast<const unsigned char*>(stream.GetBuf());
            family.payloads.push_back(WireBytes(written + measured, written + writerEnd));

            // The sentinel is written by the real SDK stream scalar operator.
            const unsigned int sentinel = 0xd3c2b1a0u;
            stream << sentinel;
            literal.push_back(0xa0); literal.push_back(0xb1); literal.push_back(0xc2); literal.push_back(0xd3);
            checks.Require(stream.GetEOF() == literal.size() && stream.GetPosition() == literal.size(),
                "Writer changed the following boundary sentinel position");
            checks.Require(std::memcmp(stream.GetBuf(), &literal[0], literal.size()) == 0,
                "Complete writer/sentinel wire differs");

            stream.Rewind();
            unsigned int count = UINT_MAX;
            stream >> count;
            checks.Require(count == values.size() && stream.GetPosition() == 4,
                "SDK uint32 count reader did not consume four bytes");
            if (expectedCountBytes == 8) {
                unsigned int upper = UINT_MAX; stream >> upper;
                checks.Require(upper == 0 && stream.GetPosition() == 8, "Legacy64 upper count bytes differ");
            }
            if (!payload.empty()) {
                WireBytes read(payload.size(), 0);
                checks.Require(stream.ReadIt(static_cast<unsigned int>(read.size()), &read[0]) == read.size(),
                    "Short actual SDK payload read");
                checks.Require(read == payload, "Actual SDK payload read differs");
            }
            unsigned int boundary = 0; stream >> boundary;
            checks.Require(boundary == sentinel && stream.GetPosition() == stream.GetEOF() && stream.AtEnd(),
                "Actual SDK read did not end at the sentinel boundary");

            // A canonical uint32-count reader sees the payload immediately at
            // byte four. Legacy64 instead exposes its zero upper count word.
            stream.Rewind(); unsigned int canonicalCount = UINT_MAX, nextWord = 0;
            stream >> canonicalCount >> nextWord;
            const unsigned int expectedNext = payload.empty() ? sentinel :
                static_cast<unsigned int>(payload[0]) |
                (static_cast<unsigned int>(payload[1]) << 8) |
                (static_cast<unsigned int>(payload[2]) << 16) |
                (static_cast<unsigned int>(payload[3]) << 24);
            checks.Require(canonicalCount == values.size(), "Canonical reader count differs");
            checks.Require(expectedNext != 0, "Negative-control fixture lacks a distinguishable boundary");
            checks.Require(expectedCountBytes == 4 ? nextWord == expectedNext : nextWord == 0 && nextWord != expectedNext,
                "Legacy64 negative control failed to expose count-induced misalignment");
            checks.Require(values == immutable, "Writer modified input vector");
        }
    }
    return family;
}

#ifdef _WIN64
void CheckCountOverflow(Checks& checks) {
    const unsigned __int64 maximum = static_cast<unsigned __int64>(UINT_MAX);
    checks.Require(CvChecked::Integer<uint>(maximum) == UINT_MAX, "Inclusive SDK count narrowing rejected UINT_MAX");
    checks.Require(CvChecked::Integer<uint>(static_cast<unsigned __int64>(0)) == 0, "Zero SDK count narrowing failed");
    bool rejected = false;
    try { (void)CvChecked::Integer<uint>(maximum + 1); }
    catch (const std::range_error&) { rejected = true; }
    checks.Require(rejected, "SDK count narrowing accepted UINT_MAX+1");
    // This tests the actual guard used in the candidate templates, without
    // fabricating a vector size or allocating more than UINT_MAX elements.
}

void SupportingFailure(Checks& checks, ZeroSisHost::RetailStateErrorCode expected,
    const unsigned char* data, std::size_t size, std::size_t start, std::size_t plots,
    const ZeroSisHost::RetailSaveStateLimits& limits) {
    try { (void)ZeroSisHost::RetailSaveSupporting::InspectAt(data, size, start, plots, limits); }
    catch (const ZeroSisHost::RetailStateError& error) {
        checks.Supporting(error.Code() == expected, "Wrong typed standalone Supporting rejection");
        checks.Supporting(error.Offset() <= size, "Standalone Supporting error offset outside input");
        return;
    }
    throw std::runtime_error("Expected standalone Supporting rejection");
}
void SupportingStandalone(Checks& checks) {
    const std::size_t counts[] = {0, 1, 960};
    const std::size_t starts[] = {0, 7, 19};
    for (unsigned int countIndex = 0; countIndex < 3; ++countIndex) {
        for (unsigned int startIndex = 0; startIndex < 3; ++startIndex) {
            const std::size_t plots = counts[countIndex], start = starts[startIndex];
            WireBytes bytes(start, 0xa5);
            Append32(bytes, 1); Append32(bytes, 1);
            // Both signed short arrays retain all-ones, without an array count.
            bytes.insert(bytes.end(), plots * 4, static_cast<unsigned char>(0xff));
            const std::size_t goodyVersion = bytes.size();
            Append32(bytes, 1);
            // Twenty-two major players, each with three signed int results.
            bytes.insert(bytes.end(), 22u * 3u * 4u, static_cast<unsigned char>(0xff));
            const std::size_t blockBytes = 276 + plots * 4;
            checks.Supporting(bytes.size() == start + blockBytes, "Independent Supporting byte-size oracle differs");
            const std::size_t end = bytes.size();
            bytes.insert(bytes.end(), 11, static_cast<unsigned char>(0x5a));
            const WireBytes immutable(bytes);
            const unsigned char* data = &bytes[0];
            ZeroSisHost::RetailSaveStateLimits limits;
            ZeroSisHost::RetailInflatedSpan span = ZeroSisHost::RetailSaveSupporting::InspectAt(data, bytes.size(), start, plots, limits);
            checks.Supporting(span.offset == start && span.bytes == blockBytes,
                "Standalone Supporting ignored explicit start or signed-payload framing");
            const ZeroSisHost::RetailInflatedSpan exact =
                ZeroSisHost::RetailSaveSupporting::InspectAt(data, end, start, plots, limits);
            checks.Supporting(exact.offset == start && exact.bytes == blockBytes, "Exact Supporting prefix required following bytes");

            for (std::size_t cut = 0; cut < end; ++cut) {
                SupportingFailure(checks, ZeroSisHost::RetailStateErrorCode::Truncated, data, cut, start, plots, limits);
                ++checks.supportingTruncations;
            }
            const std::size_t versions[] = {start, start + 4, goodyVersion};
            for (unsigned int versionIndex = 0; versionIndex < 3; ++versionIndex) {
                WireBytes changed(bytes);
                changed[versions[versionIndex]] = 2;
                SupportingFailure(checks, ZeroSisHost::RetailStateErrorCode::UnsupportedVersion,
                    &changed[0], changed.size(), start, plots, limits);
            }
            SupportingFailure(checks, ZeroSisHost::RetailStateErrorCode::UnsupportedVersion,
                data, bytes.size(), start + 1, plots, limits);

            limits.maxInputBytes = bytes.size();
            checks.Supporting(ZeroSisHost::RetailSaveSupporting::InspectAt(data, bytes.size(), start, plots, limits).bytes == blockBytes,
                "Inclusive Supporting input budget failed");
            --limits.maxInputBytes;
            SupportingFailure(checks, ZeroSisHost::RetailStateErrorCode::InputLimit, data, bytes.size(), start, plots, limits);
            limits = ZeroSisHost::RetailSaveStateLimits(); limits.maxPrefixBytes = end;
            checks.Supporting(ZeroSisHost::RetailSaveSupporting::InspectAt(data, bytes.size(), start, plots, limits).bytes == blockBytes,
                "Inclusive Supporting prefix budget failed");
            --limits.maxPrefixBytes;
            SupportingFailure(checks, ZeroSisHost::RetailStateErrorCode::PrefixLimit, data, bytes.size(), start, plots, limits);
            limits = ZeroSisHost::RetailSaveStateLimits(); limits.maxMapPlots = plots;
            checks.Supporting(ZeroSisHost::RetailSaveSupporting::InspectAt(data, bytes.size(), start, plots, limits).bytes == blockBytes,
                "Inclusive Supporting plot budget failed");
            if (plots) {
                --limits.maxMapPlots;
                SupportingFailure(checks, ZeroSisHost::RetailStateErrorCode::MapPlotLimit, data, bytes.size(), start, plots, limits);
            }
            limits = ZeroSisHost::RetailSaveStateLimits();
            limits.maxArrayRecords = 0; limits.maxTotalRecords = 0; limits.maxStringBytes = 0;
            checks.Supporting(ZeroSisHost::RetailSaveSupporting::InspectAt(data, bytes.size(), start, plots, limits).bytes == blockBytes,
                "Supporting fixed arrays were treated as dynamic lengths");
            checks.Supporting(bytes == immutable, "Standalone Supporting changed its caller-owned bytes");
        }
    }
    ZeroSisHost::RetailSaveStateLimits limits;
    const unsigned char one = 0;
    SupportingFailure(checks, ZeroSisHost::RetailStateErrorCode::NullInput, NULL, 1, 0, 0, limits);
    SupportingFailure(checks, ZeroSisHost::RetailStateErrorCode::Truncated, NULL, 0, 0, 0, limits);
    SupportingFailure(checks, ZeroSisHost::RetailStateErrorCode::Truncated,
        &one, 1, (std::numeric_limits<std::size_t>::max)(), 0, limits);
    SupportingFailure(checks, ZeroSisHost::RetailStateErrorCode::MapPlotLimit,
        &one, 1, 0, (std::numeric_limits<std::size_t>::max)(), limits);
    // Deliberately no Map-end call: this unit establishes only the standalone
    // caller-supplied-offset contract, never actual retail placement or loading.
}

struct PublicTeamResult {
    std::size_t teamsOffset, teamsBytes, teamsEnd, records;
    bool supportingAtMapRejected, supportingAfterTeamsAccepted;
    std::size_t supportingAfterTeamsOffset, supportingAfterTeamsBytes, supportingAfterTeamsErrorOffset;
    PublicTeamResult() : teamsOffset(1695150), teamsBytes(0), teamsEnd(0), records(0),
        supportingAtMapRejected(false), supportingAfterTeamsAccepted(false),
        supportingAfterTeamsOffset(0), supportingAfterTeamsBytes(0), supportingAfterTeamsErrorOffset(0) {}
};
WireBytes ReadPublicStdin() {
    if (_setmode(_fileno(stdin), _O_BINARY) == -1) throw std::runtime_error("Cannot set binary public stdin");
    const std::size_t maximum = 64u * 1024u * 1024u;
    unsigned char buffer[65536];
    WireBytes bytes;
    for (;;) {
        const std::size_t got = std::fread(buffer, 1, sizeof(buffer), stdin);
        if (got > maximum - bytes.size()) throw std::runtime_error("Public stdin exceeds byte budget");
        bytes.insert(bytes.end(), buffer, buffer + got);
        if (got != sizeof(buffer)) {
            if (std::ferror(stdin)) throw std::runtime_error("Public stdin read failed");
            if (std::feof(stdin)) break;
        }
    }
    return bytes;
}
PublicTeamResult PublicTeams(Checks& checks) {
    const WireBytes bytes = ReadPublicStdin();
    const WireBytes immutable(bytes);
    checks.Require(bytes.size() == 9762327, "Public inflated input length differs");
    const unsigned char* data = &bytes[0];
    ZeroSisHost::RetailSaveStateLimits limits;
    PublicTeamResult result;
    // Five is the explicit inspection profile; ruleset compatibility remains
    // unverified. Obtain Team start from ordered Map framing of these same bytes.
    const ZeroSisHost::RetailSaveMapInspection map = ZeroSisHost::RetailSaveMap::InspectGameAndMap(
        bytes, ZeroSisHost::RetailSaveStateProfile(5), limits);
    checks.Require(map.nextInflatedOffset == 1695150 && map.plotCount == 960,
        "Public ordered Map boundary or plot count changed");
    result.teamsOffset = map.nextInflatedOffset;
    ZeroSisHost::RetailStateDetail::Reader reader(data, bytes.size(), limits);
    reader.Skip(result.teamsOffset);
    for (unsigned int team = 0; team < 64; ++team) {
        const std::int32_t id = ZeroSisHost::RetailStateDetail::ReadTeam(reader);
        checks.Require(id == static_cast<std::int32_t>(team), "Public serialized team ID differs from ordinal");
    }
    result.teamsEnd = reader.Pos(); result.teamsBytes = result.teamsEnd - result.teamsOffset;
    result.records = reader.Records();
    checks.Require(result.teamsBytes >= 64u * 2424u && result.teamsEnd <= bytes.size(),
        "Public Team framing violates its SDK lower bound");

    // This fixed-position negative observation must not be turned into a scan
    // for some other plausible version word. It rejects the old guessed order.
    try {
        (void)ZeroSisHost::RetailSaveSupporting::InspectAt(data, bytes.size(), result.teamsOffset, 960, limits);
    } catch (const ZeroSisHost::RetailStateError& error) {
        checks.Require(error.Code() == ZeroSisHost::RetailStateErrorCode::UnsupportedVersion,
            "Unexpected Supporting-at-Map rejection type");
        checks.Require(error.Offset() <= bytes.size(), "Supporting-at-Map error offset outside input");
        result.supportingAtMapRejected = true;
    }
    checks.Require(result.supportingAtMapRejected, "Supporting unexpectedly accepted directly after public Map");

    // At the sequentially obtained Team end, inspect only this exact candidate.
    // Either typed rejection or a framed span is diagnostic; success is not an
    // assertion that the complete retail caller/load protocol is established.
    result.supportingAfterTeamsOffset = result.teamsEnd;
    try {
        const ZeroSisHost::RetailInflatedSpan span = ZeroSisHost::RetailSaveSupporting::InspectAt(
            data, bytes.size(), result.teamsEnd, 960, limits);
        checks.Require(span.offset == result.teamsEnd && span.bytes == 4116,
            "Supporting-after-Teams span differs from its independent size oracle");
        result.supportingAfterTeamsAccepted = true;
        result.supportingAfterTeamsOffset = span.offset; result.supportingAfterTeamsBytes = span.bytes;
    } catch (const ZeroSisHost::RetailStateError& error) {
        checks.Require(error.Offset() <= bytes.size(), "Supporting-after-Teams error offset outside input");
        result.supportingAfterTeamsErrorOffset = error.Offset();
    }
    checks.Require(bytes == immutable, "Public Team inspection modified input");
    return result;
}
void PrintPublicTeams(const PublicTeamResult& r) {
    std::printf(",\"public\":{\"input_bytes\":9762327,\"teams_offset\":%I64u,\"teams_bytes\":%I64u,\"teams_end\":%I64u,"
        "\"team_count\":64,\"array_records\":%I64u,\"supporting_at_map_rejected\":%s,"
        "\"supporting_after_teams_accepted\":%s,\"supporting_after_teams_typed_rejected\":%s,"
        "\"supporting_after_teams_offset\":%I64u,\"supporting_after_teams_bytes\":%I64u,"
        "\"supporting_after_teams_error_offset\":%I64u}",
        static_cast<unsigned __int64>(r.teamsOffset), static_cast<unsigned __int64>(r.teamsBytes),
        static_cast<unsigned __int64>(r.teamsEnd), static_cast<unsigned __int64>(r.records),
        r.supportingAtMapRejected ? "true" : "false", r.supportingAfterTeamsAccepted ? "true" : "false",
        r.supportingAfterTeamsAccepted ? "false" : "true", static_cast<unsigned __int64>(r.supportingAfterTeamsOffset),
        static_cast<unsigned __int64>(r.supportingAfterTeamsBytes), static_cast<unsigned __int64>(r.supportingAfterTeamsErrorOffset));
}
#endif

std::string JsonEscape(const char* message) {
    std::string escaped;
    for (const unsigned char* p = reinterpret_cast<const unsigned char*>(message); *p; ++p) {
        if (*p == '"' || *p == '\\') { escaped += '\\'; escaped += static_cast<char>(*p); }
        else if (*p >= 0x20 && *p < 0x7f) escaped += static_cast<char>(*p);
        else escaped += '?';
    }
    return escaped;
}
}

int main(int argc, char** argv) {
    Checks checks;
    try {
#ifdef _WIN64
        const bool publicMode = argc == 2 && std::strcmp(argv[1], "--public") == 0;
        checks.Require(argc == 1 || publicMode, "Usage: sdk_type_array_count [--public]");
#else
        checks.Require(argc == 1, "Original x86 count reference takes no arguments");
        (void)argv;
#endif
        checks.Require(sizeof(int) == 4 && sizeof(unsigned int) == 4, "SDK wire scalar width differs");
        checks.Require(sizeof(void*) == sizeof(std::size_t), "Unexpected host size_t ABI");
        const unsigned int originalWidth = static_cast<unsigned int>(sizeof(std::size_t));
        const FamilyResult original = TestFamily<OriginalDispatch>(checks, originalWidth);
        unsigned int candidateWidth = 0, legacyWidth = 0;
#ifdef _WIN64
        checks.Require(sizeof(void*) == 8 && sizeof(std::size_t) == 8, "Expected native x64 control");
        const FamilyResult candidate = TestFamily<CandidateDispatch>(checks, 4);
        const FamilyResult legacy = TestFamily<Legacy64Dispatch>(checks, 8);
        candidateWidth = candidate.countBytes; legacyWidth = legacy.countBytes;
        checks.Require(original.payloads == candidate.payloads && original.payloads == legacy.payloads,
            "Count fix changed a payload body");
        CheckCountOverflow(checks);
        SupportingStandalone(checks);
        PublicTeamResult publicResult;
        if (publicMode) publicResult = PublicTeams(checks);
#else
        checks.Require(sizeof(void*) == 4 && sizeof(std::size_t) == 4, "Expected original x86 reference");
#endif
        std::printf("{\"status\":\"PASS_SDK_TYPE_ARRAY_COUNT\",\"checks\":%lu,\"sizeof_pointer\":%u,\"sizeof_size_t\":%u,"
            "\"original_count_bytes\":%u,\"candidate_count_bytes\":%u,\"legacy64_count_bytes\":%u,"
            "\"supporting_checks\":%lu,\"supporting_truncations\":%lu,\"gamecore_loaded\":false,\"window_created\":false,"
            "\"user_saves_accessed\":false,\"complete_save_validated\":false,\"ruleset_compatibility_verified\":false,"
            "\"retail_supporting_placement_verified\":false",
            checks.checks, static_cast<unsigned int>(sizeof(void*)), static_cast<unsigned int>(sizeof(std::size_t)),
            original.countBytes, candidateWidth, legacyWidth, checks.supportingChecks, checks.supportingTruncations);
#ifdef _WIN64
        if (publicMode) PrintPublicTeams(publicResult);
#endif
        std::printf("}\n");
        return 0;
    } catch (const std::exception& error) {
        const std::string message = JsonEscape(error.what());
        std::printf("{\"status\":\"FAIL_SDK_TYPE_ARRAY_COUNT\",\"checks\":%lu,\"error\":\"%s\","
            "\"gamecore_loaded\":false,\"window_created\":false,\"complete_save_validated\":false,"
            "\"retail_supporting_placement_verified\":false}\n", checks.checks, message.c_str());
        return 1;
    }
}
