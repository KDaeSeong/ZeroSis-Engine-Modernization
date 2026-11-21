// Read-only stdin diagnostics for caller-supplied public retail fixtures.
// Widths and the 64-slot layout are explicit hypotheses, never inferred/retried.
#include "RetailSavePregame.h"
#include "RetailSaveMap.h"
#include "RetailSaveTeam.h"
#include "RetailSavePlayers.h"
#include "RetailSaveSupporting.h"
#include "RetailSaveChunkFrames.h"
#include <array>
#include <cstddef>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>
#ifdef _WIN32
#include <fcntl.h>
#include <io.h>
#endif

namespace {
using namespace ZeroSisHost;
using Bytes = std::vector<unsigned char>;
constexpr std::size_t MaximumInputBytes = 64u * 1024u * 1024u;
constexpr std::size_t ExpectedSlots = 64u;
constexpr std::size_t MaximumMetadataStringBytes = 256u;
enum class Mode { Unselected, Header, Inflated };

struct Options {
    Mode mode = Mode::Unselected;
    std::uint32_t awards = 0, grand = 0, projects = 0;
    std::size_t maximumInputBytes = MaximumInputBytes;
    std::size_t maximumTotalRecords = RetailSaveStateLimits{}.maxTotalRecords;
    bool widthsDeclared = false;
    const char* booleanEncoding = "canonical";
    RetailBooleanWireProfile booleanWireProfile = RetailBooleanWireProfile::CanonicalZeroOne;
    bool booleanEncodingDeclared = false, framingDeclared = false, recordBudgetDeclared = false;
};

std::uint32_t Number(const char* text, std::uint32_t maximum) {
    if (!text || !*text) throw std::invalid_argument("Missing unsigned decimal option value");
    std::uint32_t value = 0;
    for (const char* current = text; *current; ++current) {
        if (*current < '0' || *current > '9')
            throw std::invalid_argument("Option values must contain decimal digits only");
        const auto digit = static_cast<std::uint32_t>(*current - '0');
        if (value > (maximum - digit) / 10u)
            throw std::invalid_argument("Option value exceeds its explicit bound");
        value = value * 10u + digit;
    }
    return value;
}

Options Arguments(int argc, char** argv) {
    Options result;
    bool awards = false, grand = false, projects = false, inputLimit = false;
    for (int index = 1; index < argc; ++index) {
        const std::string name(argv[index]);
        if (name == "--header" || name == "--inflated") {
            if (result.mode != Mode::Unselected) throw std::invalid_argument("Choose exactly one probe mode");
            result.mode = name == "--header" ? Mode::Header : Mode::Inflated;
            continue;
        }
        if (name != "--awards" && name != "--grand" && name != "--projects" && name != "--max-input" &&
            name != "--boolean-encoding" && name != "--framing" && name != "--max-records")
            throw std::invalid_argument("Unknown probe option; input paths are not accepted");
        if (index + 1 >= argc) throw std::invalid_argument("A named option is missing its value");
        const char* value = argv[++index];
        if (name == "--awards") {
            if (awards) throw std::invalid_argument("Duplicate --awards option");
            result.awards = Number(value, 4096u); awards = true;
        } else if (name == "--grand") {
            if (grand) throw std::invalid_argument("Duplicate --grand option");
            result.grand = Number(value, 4096u); grand = true;
        } else if (name == "--projects") {
            if (projects) throw std::invalid_argument("Duplicate --projects option");
            result.projects = Number(value, 4096u); projects = true;
        } else if (name == "--boolean-encoding") {
            if (result.booleanEncodingDeclared) throw std::invalid_argument("Duplicate --boolean-encoding option");
            if (std::strcmp(value, "canonical") == 0) {
                result.booleanEncoding = "canonical";
                result.booleanWireProfile = RetailBooleanWireProfile::CanonicalZeroOne;
            } else if (std::strcmp(value, "sdk-byte") == 0) {
                result.booleanEncoding = "sdk-byte";
                result.booleanWireProfile = RetailBooleanWireProfile::SdkRawByte;
            } else throw std::invalid_argument("Unknown --boolean-encoding value");
            result.booleanEncodingDeclared = true;
        } else if (name == "--framing") {
            if (result.framingDeclared) throw std::invalid_argument("Duplicate --framing option");
            if (std::strcmp(value, "u32-length-to-end") != 0)
                throw std::invalid_argument("Unknown --framing value");
            result.framingDeclared = true;
        } else if (name == "--max-records") {
            if (result.recordBudgetDeclared) throw std::invalid_argument("Duplicate --max-records option");
            result.maximumTotalRecords = Number(value, static_cast<std::uint32_t>(MaximumInputBytes));
            if (result.maximumTotalRecords == 0u) throw std::invalid_argument("Record budget must be positive");
            result.recordBudgetDeclared = true;
        } else {
            if (inputLimit) throw std::invalid_argument("Duplicate --max-input option");
            result.maximumInputBytes = Number(value, static_cast<std::uint32_t>(MaximumInputBytes));
            if (result.maximumInputBytes == 0u) throw std::invalid_argument("Input byte limit must be positive");
            inputLimit = true;
        }
    }
    if (result.mode == Mode::Unselected || !awards || !grand || !projects)
        throw std::invalid_argument("Require --header or --inflated and explicit --awards N --grand N --projects N");
    if (result.framingDeclared && result.mode != Mode::Header)
        throw std::invalid_argument("--framing requires --header mode");
    if (result.recordBudgetDeclared && result.mode != Mode::Inflated)
        throw std::invalid_argument("--max-records requires --inflated mode");
    result.widthsDeclared = true;
    return result;
}

Bytes ReadInput(std::size_t maximum) {
#ifdef _WIN32
    if (_setmode(_fileno(stdin), _O_BINARY) == -1) throw std::runtime_error("Cannot select binary stdin");
#endif
    Bytes result;
    std::array<char, 65536> block{};
    while (std::cin.read(block.data(), static_cast<std::streamsize>(block.size())) || std::cin.gcount() > 0) {
        const auto count = static_cast<std::size_t>(std::cin.gcount());
        if (count > maximum - result.size()) throw std::runtime_error("Stdin exceeded its declared input byte budget");
        for (std::size_t index = 0; index < count; ++index)
            result.push_back(static_cast<unsigned char>(block[index]));
    }
    if (!std::cin.eof()) throw std::runtime_error("Cannot read binary stdin");
    return result;
}

RetailSavePlayersProfile PlayerProfiles(const Options& options) {
    const RetailSavePlayerWireProfile player{
        RetailSavePlayerProfile(options.grand, RetailPlayerCatalogProfile::InitializedBuildings),
        RetailPlayerAiMidCatalogProfile::InitializedTechs, RetailPlayerAiLateProfile::InitializedMinorQuests,
        RetailSaveCityProfile(options.projects, RetailCityProductionCatalogProfile::InitializedBuildingsAndUnits, 6u),
        RetailUnitWriterProfile::Bnw9CompleteGreatWorkHashWord,
        RetailSavePlayerEndProfile(RetailPlayerOperationsProfile::BnwCurrentFactory20,
            RetailPlayerEndWriterProfile::Current16With64Players)};
    return {RetailPlayerBlockProfile::Bnw64InSlotOrder, player};
}

struct TeamRow {
    std::size_t start = 0, end = 0, records = 0;
    std::int32_t id = -1;
};
struct PlayerRow {
    std::size_t start = 0, end = 0, records = 0;
    std::int32_t id = -1;
    std::uint32_t cities = 0, units = 0, armies = 0, operations = 0;
};
struct Observation {
    const char* status = "DIAGNOSTIC_ARGUMENT_REJECTED";
    const char* phase = "arguments";
    const char* errorDomain = "arguments";
    std::string errorMessage;
    int errorCode = -1;
    bool errorOffsetKnown = false;
    std::size_t errorOffset = 0, inputBytes = 0, stageStart = 0, completedOffset = 0, records = 0;
    std::int32_t failedTeamSlot = -1, failedPlayerSlot = -1, currentObservedId = -1;
    bool currentIdObserved = false, headerObserved = false, pregameObserved = false, mapObserved = false;
    bool sequenceObserved = false, supportingObserved = false, inputReadComplete = false;
    bool chunkFramesObserved = false;
    RetailSavePregame pregame;
    RetailSaveChunkFramesInspection chunkFrames;
    RetailSaveMapInspection map;
    RetailInflatedSpan supporting;
    std::array<TeamRow, ExpectedSlots> teams{};
    std::array<PlayerRow, ExpectedSlots> players{};
    std::size_t teamCount = 0, playerCount = 0, cities = 0, units = 0, armies = 0, operations = 0;
};

void ProbeHeader(const Bytes& input, const Options& options, Observation& result) {
    result.phase = "header"; result.errorDomain = "header";
    result.pregame.metadata = RetailSaveHeader::ParsePrefix(input);
    result.headerObserved = true;
    result.completedOffset = result.pregame.metadata.consumedPrefixBytes;
    result.stageStart = result.completedOffset;
    result.phase = "pregame"; result.errorDomain = "pregame";
    result.pregame = RetailSavePregame::ParsePrefix(input);
    result.pregameObserved = true;
    result.completedOffset = result.pregame.compressedDataOffset;
    if (options.framingDeclared) {
        result.phase = "chunk_frames"; result.errorDomain = "chunk_frames";
        result.stageStart = result.pregame.compressionHeader.offset + 4u;
        result.chunkFrames = RetailSaveChunkFrames::Inspect(input.data(), input.size(), result.stageStart,
            RetailSaveChunkFramingProfile::U32LengthPayloadsToEnd);
        result.chunkFramesObserved = true;
    }
    result.status = "DIAGNOSTIC_HEADER_PREFIX_OBSERVED";
    result.errorDomain = "none";
}

void ProbeInflated(const Bytes& input, const Options& options, Observation& result) {
    auto remaining = RetailSaveStateLimits{};
    remaining.maxInputBytes = options.maximumInputBytes;
    remaining.maxTotalRecords = options.maximumTotalRecords;
    remaining.booleanWireProfile = options.booleanWireProfile;
    const auto profiles = PlayerProfiles(options);
    result.errorDomain = "inflated_state";
    result.phase = "game_map";
    auto advance = [&](std::size_t next, std::size_t records) {
        if (next <= result.completedOffset || next > input.size())
            throw RetailStateError(RetailStateErrorCode::InvalidValue, result.stageStart,
                "Diagnostic stage returned a noncontiguous or empty boundary");
        if (records > remaining.maxTotalRecords)
            throw RetailStateError(RetailStateErrorCode::TotalRecordLimit, result.stageStart,
                "Diagnostic stages exceeded the shared record budget");
        remaining.maxTotalRecords -= records;
        result.records += records;
        result.completedOffset = next;
    };
    result.map = RetailSaveMap::InspectGameAndMap(input, RetailSaveStateProfile(options.awards), remaining);
    result.mapObserved = true;
    advance(result.map.nextInflatedOffset, result.map.arrayRecords);

    result.phase = "teams";
    const auto recordsBeforeTeams = result.records;
    const auto teamLimits = remaining;
    RetailStateDetail::Reader teams(input.data(), input.size(), teamLimits);
    teams.Skip(result.completedOffset);
    for (std::size_t slot = 0; slot < ExpectedSlots; ++slot) {
        result.stageStart = teams.Pos();
        result.failedTeamSlot = static_cast<std::int32_t>(slot);
        result.currentIdObserved = false;
        const auto before = teams.Records();
        const auto id = RetailStateDetail::ReadTeam(teams);
        result.currentObservedId = id; result.currentIdObserved = true;
        if (id != static_cast<std::int32_t>(slot))
            throw RetailStateError(RetailStateErrorCode::InvalidValue, result.stageStart,
                "Team ID differs from the explicit 64-slot order");
        result.teams[slot] = {result.stageStart, teams.Pos(), teams.Records() - before, id};
        ++result.teamCount;
        result.completedOffset = teams.Pos();
        result.records = recordsBeforeTeams + teams.Records();
    }
    if (teams.Records() > remaining.maxTotalRecords)
        throw RetailStateError(RetailStateErrorCode::TotalRecordLimit, result.stageStart,
            "Team trace exceeded the remaining shared record budget");
    remaining.maxTotalRecords -= teams.Records();
    result.failedTeamSlot = -1; result.currentIdObserved = false;

    result.phase = "players";
    if (profiles.blockProfile != RetailPlayerBlockProfile::Bnw64InSlotOrder)
        throw RetailStateError(RetailStateErrorCode::UnsupportedProfile, result.completedOffset,
            "Unsupported diagnostic contiguous Player profile");
    for (std::size_t slot = 0; slot < ExpectedSlots; ++slot) {
        result.stageStart = result.completedOffset;
        result.failedPlayerSlot = static_cast<std::int32_t>(slot);
        result.currentIdObserved = false;
        // This is a single source-ordered trace. A failure is never retried with
        // another width, start offset, catalog branch, or aggregate parser.
        const auto player = RetailSavePlayer::InspectAt(input.data(), input.size(), result.stageStart,
            profiles.playerProfile, remaining);
        result.currentObservedId = player.playerId; result.currentIdObserved = true;
        if (player.playerId != static_cast<std::int32_t>(slot) || player.prefix.playerId != player.playerId)
            throw RetailStateError(RetailStateErrorCode::InvalidValue, result.stageStart,
                "Player ID differs from the explicit 64-slot order");
        if (player.whole.offset != result.stageStart || player.nextInflatedOffset <= result.stageStart ||
                player.nextInflatedOffset > input.size() ||
                player.whole.bytes != player.nextInflatedOffset - result.stageStart || !player.completePlayerWireFramed)
            throw RetailStateError(RetailStateErrorCode::InvalidValue, result.stageStart,
                "Player trace returned an inconsistent contiguous wire span");
        if (player.completePlayerVerified || player.completeSaveVerified ||
                player.rulesetCompatibilityVerified || player.restoreApproved)
            throw RetailStateError(RetailStateErrorCode::InvalidValue, result.stageStart,
                "Wire diagnostic cannot grant semantic or restore approval");
        advance(player.nextInflatedOffset, player.arrayRecords);
        auto& row = result.players[slot];
        row.start = result.stageStart; row.end = player.nextInflatedOffset;
        row.records = player.arrayRecords; row.id = player.playerId;
        row.cities = player.cities.pool.liveCount; row.units = player.units.pool.liveCount;
        row.armies = player.ending.armyPool.liveCount; row.operations = player.ending.operations.declaredCount;
        ++result.playerCount;
        result.cities += row.cities; result.units += row.units;
        result.armies += row.armies; result.operations += row.operations;
    }
    result.failedPlayerSlot = -1; result.currentIdObserved = false;
    result.phase = "supporting"; result.stageStart = result.completedOffset;
    result.supporting = RetailSaveSupporting::InspectAt(input.data(), input.size(), result.stageStart,
        result.map.plotCount, remaining);
    if (result.supporting.offset != result.stageStart || result.supporting.offset > input.size() ||
            result.supporting.bytes > input.size() - result.supporting.offset)
        throw RetailStateError(RetailStateErrorCode::InvalidValue, result.stageStart,
            "Supporting trace returned an inconsistent wire span");
    result.completedOffset = result.supporting.offset + result.supporting.bytes;
    result.supportingObserved = true; result.sequenceObserved = true;
    result.phase = "sequence_end"; result.errorDomain = "none";
    result.status = "DIAGNOSTIC_SEQUENCE_OBSERVED";
}

const char* Boolean(bool value) { return value ? "true" : "false"; }
void OptionalSlot(std::int32_t value) {
    if (value < 0) std::cout << "null";
    else std::cout << value;
}
void Text(const std::string& value) {
    // Metadata strings are untrusted raw bytes. Byte escapes keep even invalid
    // UTF-8/NUL data valid JSON; the encoding and truncation are explicit below.
    constexpr char Hex[] = "0123456789abcdef";
    std::cout << '"';
    const auto count = value.size() < MaximumMetadataStringBytes ? value.size() : MaximumMetadataStringBytes;
    for (std::size_t index = 0; index < count; ++index) {
        const auto byte = static_cast<unsigned char>(value[index]);
        if (byte == '"') std::cout << "\\\"";
        else if (byte == '\\') std::cout << "\\\\";
        else if (byte < 0x20u || byte >= 0x7fu)
            std::cout << "\\u00" << Hex[byte >> 4u] << Hex[byte & 15u];
        else std::cout << static_cast<char>(byte);
    }
    std::cout << '"';
}
void Metadata(const RetailSaveHeader& header) {
    const bool truncated = header.gameVersion.size() > MaximumMetadataStringBytes ||
        header.gameBuild.size() > MaximumMetadataStringBytes || header.playerCivilization.size() > MaximumMetadataStringBytes ||
        header.difficulty.size() > MaximumMetadataStringBytes || header.startingEra.size() > MaximumMetadataStringBytes ||
        header.currentEra.size() > MaximumMetadataStringBytes || header.gamePace.size() > MaximumMetadataStringBytes ||
        header.mapSize.size() > MaximumMetadataStringBytes || header.mapFile.size() > MaximumMetadataStringBytes;
    std::cout << "{\"save_game_version\":" << header.saveGameVersion
        << ",\"current_turn\":" << header.currentTurn << ",\"game_mode\":" << static_cast<unsigned int>(header.gameMode)
        << ",\"metadata_prefix_bytes\":" << header.consumedPrefixBytes << ",\"game_version\":";
    Text(header.gameVersion); std::cout << ",\"game_build\":"; Text(header.gameBuild);
    std::cout << ",\"player_civilization\":"; Text(header.playerCivilization);
    std::cout << ",\"difficulty\":"; Text(header.difficulty);
    std::cout << ",\"starting_era\":"; Text(header.startingEra);
    std::cout << ",\"current_era\":"; Text(header.currentEra);
    std::cout << ",\"game_pace\":"; Text(header.gamePace);
    std::cout << ",\"map_size\":"; Text(header.mapSize);
    std::cout << ",\"map_file\":"; Text(header.mapFile);
    std::cout << ",\"dlc_count\":" << header.enabledDlc.size() << ",\"mod_count\":" << header.enabledMods.size()
        << ",\"text_encoding\":\"byte-preserving-u00xx\",\"maximum_text_bytes_per_field\":" << MaximumMetadataStringBytes
        << ",\"text_fields_truncated\":" << Boolean(truncated) << '}';
}

void Print(const Options& options, const Observation& result) {
    const char* mode = options.mode == Mode::Header ? "header" : options.mode == Mode::Inflated ? "inflated" : "unselected";
    std::cout << "{\"schema\":\"zerosis.retail.public_probe.v1\",\"status\":\"" << result.status
        << "\",\"mode\":\"" << mode << "\",\"stdin_read_complete\":" << Boolean(result.inputReadComplete)
        << ",\"input_bytes\":";
    if (result.inputReadComplete) std::cout << result.inputBytes; else std::cout << "null";
    std::cout << ",\"maximum_input_bytes\":" << options.maximumInputBytes
        << ",\"maximum_total_records\":" << options.maximumTotalRecords;
    if (options.mode == Mode::Inflated)
        std::cout << ",\"outer_sequence_basis\":\"caller_declared_experiment\",\"retail_outer_sequence_verified\":false";
    std::cout << ",\"profiles\":{\"awards\":" << options.awards << ",\"grand\":" << options.grand
        << ",\"projects\":" << options.projects << ",\"widths_explicit\":" << Boolean(options.widthsDeclared)
        << ",\"record_budget_explicit\":" << Boolean(options.recordBudgetDeclared)
        << ",\"catalog_hypotheses_only\":true,\"player_block\":\"Bnw64InSlotOrder\""
        << ",\"team_slots\":64,\"player_slots\":64,\"top_level_layout_hypothesis\":true"
        << ",\"unit_writer\":\"Bnw9CompleteGreatWorkHashWord\",\"boolean_encoding\":\"" << options.booleanEncoding
        << "\",\"boolean_encoding_explicit\":" << Boolean(options.booleanEncodingDeclared) << '}'
        << ",\"phase\":\"" << result.phase << "\",\"last_completed_offset\":" << result.completedOffset
        << ",\"remaining_input_bytes\":";
    if (result.inputReadComplete && result.completedOffset <= result.inputBytes)
        std::cout << result.inputBytes - result.completedOffset;
    else std::cout << "null";
    std::cout << ",\"compressed_offset\":";
    if (result.pregameObserved) std::cout << result.pregame.compressedDataOffset; else std::cout << "null";
    std::cout << ",\"header_observed\":" << Boolean(result.headerObserved)
        << ",\"pregame_observed\":" << Boolean(result.pregameObserved) << ",\"metadata\":";
    if (result.headerObserved) Metadata(result.pregame.metadata); else std::cout << "null";
    std::cout << ",\"pregame\":";
    if (result.pregameObserved) {
        const auto& value = result.pregame;
        std::cout << "{\"slot_hints_version\":" << value.slotHintsVersion << ",\"archive_version\":" << value.archiveVersion
            << ",\"world_info_version\":" << value.worldInfoVersion << ",\"compression_format\":" << value.compressionFormatId
            << ",\"compression_chunk_size\":" << value.compressionChunkSize << ",\"array_records\":" << value.arrayRecords
            << ",\"compression_header_offset\":" << value.compressionHeader.offset
            << ",\"compression_header_bytes\":" << value.compressionHeader.bytes << '}';
    } else std::cout << "null";
    std::cout << ",\"chunk_frames\":";
    if (result.chunkFramesObserved) {
        const auto& value = result.chunkFrames;
        std::cout << "{\"container_span\":{\"offset\":" << value.containerSpan.offset
            << ",\"bytes\":" << value.containerSpan.bytes << "},\"total_payload_bytes\":" << value.totalPayloadBytes
            << ",\"frames\":[";
        for (std::size_t index = 0; index < value.frames.size(); ++index) {
            const auto& frame = value.frames[index]; if (index != 0u) std::cout << ',';
            std::cout << "{\"header\":{\"offset\":" << frame.header.offset << ",\"bytes\":" << frame.header.bytes
                << "},\"payload\":{\"offset\":" << frame.payload.offset << ",\"bytes\":" << frame.payload.bytes << "}}";
        }
        std::cout << "]}";
    } else std::cout << "null";
    std::cout << ",\"game_map\":";
    if (result.mapObserved) {
        const auto& map = result.map;
        std::cout << "{\"game_end_offset\":" << map.prefix.game.offset + map.prefix.game.bytes
            << ",\"map_header_end_offset\":" << map.prefix.nextInflatedOffset << ",\"map_end_offset\":" << map.nextInflatedOffset
            << ",\"width\":" << map.prefix.mapWidth << ",\"height\":" << map.prefix.mapHeight << ",\"plots\":" << map.plotCount
            << ",\"areas\":" << map.areaCount << ",\"landmasses\":" << map.landmassCount
            << ",\"embedded_database_bytes\":" << map.prefix.embeddedDatabase.bytes << ",\"array_records\":" << map.arrayRecords << '}';
    } else std::cout << "null";
    std::cout << ",\"teams_completed\":" << result.teamCount << ",\"players_completed\":" << result.playerCount
        << ",\"array_records_completed\":" << result.records << ",\"object_counts_completed\":{\"cities\":" << result.cities
        << ",\"units\":" << result.units << ",\"armies\":" << result.armies << ",\"operations\":" << result.operations
        << "},\"teams\":[";
    for (std::size_t slot = 0; slot < result.teamCount; ++slot) {
        if (slot != 0u) std::cout << ',';
        const auto& row = result.teams[slot];
        std::cout << "{\"slot\":" << slot << ",\"id\":" << row.id << ",\"start\":" << row.start
            << ",\"end\":" << row.end << ",\"records\":" << row.records << '}';
    }
    std::cout << "],\"players\":[";
    for (std::size_t slot = 0; slot < result.playerCount; ++slot) {
        if (slot != 0u) std::cout << ',';
        const auto& row = result.players[slot];
        std::cout << "{\"slot\":" << slot << ",\"id\":" << row.id << ",\"start\":" << row.start
            << ",\"end\":" << row.end << ",\"records\":" << row.records << ",\"cities\":" << row.cities
            << ",\"units\":" << row.units << ",\"armies\":" << row.armies << ",\"operations\":" << row.operations << '}';
    }
    std::cout << "],\"supporting\":";
    if (result.supportingObserved)
        std::cout << "{\"start\":" << result.supporting.offset << ",\"bytes\":" << result.supporting.bytes
            << ",\"end\":" << result.completedOffset << '}';
    else std::cout << "null";
    std::cout << ",\"declared_sequence_observed\":" << Boolean(result.sequenceObserved)
        << ",\"declared_sequence_has_zero_remainder\":"
        << Boolean(result.sequenceObserved && result.completedOffset == result.inputBytes)
        << ",\"error\":{\"domain\":\"" << result.errorDomain << "\",\"code\":";
    if (result.errorCode >= 0) std::cout << result.errorCode; else std::cout << "null";
    std::cout << ",\"offset\":";
    if (result.errorOffsetKnown) std::cout << result.errorOffset; else std::cout << "null";
    std::cout << ",\"stage_start\":";
    if (std::strcmp(result.errorDomain, "none") == 0) std::cout << "null"; else std::cout << result.stageStart;
    std::cout << ",\"failed_team_slot\":"; OptionalSlot(result.failedTeamSlot);
    std::cout << ",\"failed_player_slot\":"; OptionalSlot(result.failedPlayerSlot);
    std::cout << ",\"observed_id\":";
    if (result.currentIdObserved) std::cout << result.currentObservedId; else std::cout << "null";
    std::cout << ",\"message\":"; Text(result.errorMessage);
    std::cout << "},\"automatic_profile_retry\":false,\"native_inflate_performed\":false"
        << ",\"host_gamecore_or_hwnd_executed\":false,\"game_or_user_save_paths_accessed\":false"
        << ",\"complete_player_validated\":false,\"complete_save_verified\":false"
        << ",\"ruleset_compatibility_verified\":false,\"restore_approved\":false,\"full_engine_goal_complete\":false}\n";
}
} // namespace

int main(int argc, char** argv) {
    static_assert(sizeof(void*) == 8, "The portable public probe requires x64");
    Options options;
    Observation result;
    int exitCode = 1;
    try {
        options = Arguments(argc, argv);
        result.phase = "stdin"; result.errorDomain = "input";
        const auto input = ReadInput(options.maximumInputBytes);
        result.inputBytes = input.size(); result.inputReadComplete = true;
        result.status = "DIAGNOSTIC_PARSER_REJECTED";
        if (options.mode == Mode::Header) ProbeHeader(input, options, result);
        else ProbeInflated(input, options, result);
        exitCode = 0;
    } catch (const RetailSaveHeaderError& error) {
        result.status = "DIAGNOSTIC_PARSER_REJECTED"; result.errorDomain = "header";
        result.errorCode = static_cast<int>(error.Code()); result.errorMessage = error.what();
    } catch (const RetailSavePregameError& error) {
        result.status = "DIAGNOSTIC_PARSER_REJECTED"; result.errorDomain = "pregame";
        result.errorCode = static_cast<int>(error.Code()); result.errorMessage = error.what();
    } catch (const RetailSaveChunkFramesError& error) {
        result.status = "DIAGNOSTIC_PARSER_REJECTED"; result.errorDomain = "chunk_frames";
        result.errorCode = static_cast<int>(error.Code()); result.errorMessage = error.what();
        result.errorOffsetKnown = true; result.errorOffset = error.Offset();
    } catch (const RetailStateError& error) {
        result.status = "DIAGNOSTIC_PARSER_REJECTED"; result.errorDomain = "inflated_state";
        result.errorCode = static_cast<int>(error.Code()); result.errorMessage = error.what();
        result.errorOffsetKnown = true; result.errorOffset = error.Offset();
    } catch (const std::exception& error) {
        result.errorMessage = error.what();
        if (options.widthsDeclared) result.status = "DIAGNOSTIC_INPUT_OR_INTERNAL_REJECTED";
    }
    Print(options, result);
    return exitCode;
}
