// Fixed public-fixture containment diagnostic. No SDK objects are constructed.
#include "RetailSavePlayer.h"
#include <cstddef>
#include <cstdio>
#include <iostream>
#include <stdexcept>
#include <vector>
#ifdef _WIN32
#include <fcntl.h>
#include <io.h>
#endif

namespace {
using namespace ZeroSisHost;
constexpr std::size_t InputBytes = 16727961u;
constexpr std::size_t PlayerStart = 7625870u, PlayerEnd = 7799422u;
constexpr std::size_t WitnessOffset = 7795644u;
struct NamedSpan { const char* name; RetailInflatedSpan span; };

void Require(bool condition, const char* message) {
    if (!condition) throw std::runtime_error(message);
}
void Text(const char* value) {
    static constexpr char Hex[] = "0123456789abcdef";
    std::cout << '"';
    for (const auto* cursor = reinterpret_cast<const unsigned char*>(value); *cursor; ++cursor) {
        const auto byte = *cursor;
        if (byte == '"' || byte == '\\') std::cout << '\\' << static_cast<char>(byte);
        else if (byte < 32u || byte >= 127u)
            std::cout << "\\u00" << Hex[byte >> 4] << Hex[byte & 15u];
        else std::cout << static_cast<char>(byte);
    }
    std::cout << '"';
}
void FalseFlags() {
    std::cout << ",\"sdk_executed\":false,\"gamecore_loaded\":false,\"window_created\":false"
        << ",\"game_accessed\":false,\"user_saves_accessed\":false,\"complete_player_validated\":false"
        << ",\"complete_save_verified\":false,\"restore_approved\":false,\"full_engine_goal_complete\":false}\n";
}
RetailInflatedSpan Between(std::size_t start, std::size_t end) {
    Require(start <= end && end <= InputBytes, "Invalid inspected stage boundary");
    return {start, end - start};
}
std::vector<unsigned char> ReadInput() {
#ifdef _WIN32
    Require(_setmode(_fileno(stdin), _O_BINARY) != -1, "Cannot select binary stdin");
#endif
    std::vector<unsigned char> bytes(InputBytes);
    std::cin.read(reinterpret_cast<char*>(bytes.data()), static_cast<std::streamsize>(bytes.size()));
    Require(std::cin.gcount() == static_cast<std::streamsize>(InputBytes), "Pinned stdin length differs");
    char extra = 0;
    Require(!std::cin.get(extra), "Stdin exceeds its exact byte budget");
    Require(std::cin.eof() && !std::cin.bad(), "Cannot finish binary stdin");
    return bytes;
}
} // namespace

int main(int argc, char**) {
    static_assert(sizeof(void*) == 8, "This diagnostic requires x64");
    try {
        Require(argc == 1, "This fixed diagnostic accepts no CLI arguments");
        const auto bytes = ReadInput();
        Require(bytes[WitnessOffset] == 68u, "Pinned witness byte differs");
        const RetailSavePlayerWireProfile profile{
            RetailSavePlayerProfile(4u, RetailPlayerCatalogProfile::InitializedBuildings),
            RetailPlayerAiMidCatalogProfile::InitializedTechs, RetailPlayerAiLateProfile::InitializedMinorQuests,
            RetailSaveCityProfile(6u, RetailCityProductionCatalogProfile::InitializedBuildingsAndUnits, 6u),
            RetailUnitWriterProfile::Bnw9CompleteGreatWorkHashWord,
            RetailSavePlayerEndProfile(RetailPlayerOperationsProfile::BnwCurrentFactory20,
                RetailPlayerEndWriterProfile::Current16With64Players)};
        RetailSaveStateLimits limits;
        limits.maxInputBytes = InputBytes;
        limits.maxTotalRecords = 1048576u;
        limits.booleanWireProfile = RetailBooleanWireProfile::SdkRawByte;
        const auto value = RetailSavePlayer::InspectAt(bytes.data(), bytes.size(), PlayerStart, profile, limits);
        Require(value.playerId == 1 && value.whole.offset == PlayerStart &&
            value.whole.bytes == PlayerEnd - PlayerStart && value.nextInflatedOffset == PlayerEnd,
            "Player identity or pinned public slot boundary differs");
        const NamedSpan spans[] = {
            {"prefix.whole", Between(PlayerStart, value.prefix.nextInflatedOffset)},
            {"middle.whole", Between(value.prefix.nextInflatedOffset, value.middle.nextInflatedOffset)},
            {"late.whole", Between(value.middle.nextInflatedOffset, value.late.nextInflatedOffset)},
            {"postTraits.whole", Between(value.late.nextInflatedOffset, value.postTraits.nextInflatedOffset)},
            {"cities.whole", value.cities.whole}, {"units.whole", value.units.whole}, {"ending.whole", value.ending.whole},
            {"prefix.front", value.prefix.front}, {"prefix.policies", value.prefix.policies},
            {"prefix.economicAI", value.prefix.economicAI}, {"prefix.citySpecializationAI", value.prefix.citySpecializationAI},
            {"prefix.wonderProductionAI", value.prefix.wonderProductionAI}, {"prefix.militaryAI", value.prefix.militaryAI},
            {"prefix.grandStrategyAI", value.prefix.grandStrategyAI},
            {"middle.diplomacyAI", value.middle.diplomacyAI}, {"middle.playerReligions", value.middle.playerReligions},
            {"middle.religionAI", value.middle.religionAI}, {"middle.playerTechs", value.middle.playerTechs},
            {"middle.flavorManager", value.middle.flavorManager}, {"middle.tacticalAI", value.middle.tacticalAI},
            {"middle.homelandAI", value.middle.homelandAI},
            {"late.minorCivAI", value.late.minorCivAI}, {"late.dealAI", value.late.dealAI},
            {"late.builderTaskingAI", value.late.builderTaskingAI}, {"late.cityConnections", value.late.cityConnections},
            {"late.dangerPlots", value.late.dangerPlots}, {"late.traits", value.late.traits},
            {"postTraits.espionage", value.postTraits.espionage}, {"postTraits.espionageAI", value.postTraits.espionageAI},
            {"postTraits.trade", value.postTraits.trade}, {"postTraits.tradeAI", value.postTraits.tradeAI},
            {"postTraits.leagueAI", value.postTraits.leagueAI}, {"postTraits.culture", value.postTraits.culture},
            {"postTraits.notifications", value.postTraits.notifications}, {"postTraits.treasury", value.postTraits.treasury},
            {"postTraits.preCityFields", value.postTraits.preCityFields}
        };
        for (const auto& item : spans)
            Require(item.span.offset >= PlayerStart && item.span.offset <= PlayerEnd &&
                item.span.bytes <= PlayerEnd - item.span.offset, "Inspected span exceeds the pinned Player");
        std::cout << "{\"schema\":\"zerosis.retail.player_bool_trace.v1\",\"status\":\"OBSERVED_PINNED_PLAYER_BOOL_CONTAINMENT\""
            << ",\"input_bytes\":" << bytes.size() << ",\"player_id\":" << value.playerId
            << ",\"player_start\":" << value.whole.offset << ",\"player_end\":" << value.nextInflatedOffset
            << ",\"array_records\":" << value.arrayRecords << ",\"witness\":{\"offset\":" << WitnessOffset
            << ",\"value\":" << static_cast<unsigned>(bytes[WitnessOffset]) << '}'
            << ",\"profiles\":{\"grand\":4,\"projects\":6,\"player_slots\":64,\"boolean_encoding\":\"sdk-byte\""
            << ",\"unit_writer\":\"Bnw9CompleteGreatWorkHashWord\",\"max_total_records\":1048576},\"spans\":[";
        bool first = true;
        for (const auto& item : spans) {
            if (!first) std::cout << ',';
            first = false;
            const bool contains = WitnessOffset >= item.span.offset && WitnessOffset - item.span.offset < item.span.bytes;
            std::cout << "{\"name\":"; Text(item.name);
            std::cout << ",\"offset\":" << item.span.offset << ",\"bytes\":" << item.span.bytes
                << ",\"contains_witness\":" << (contains ? "true" : "false") << '}';
        }
        std::cout << ']'; FalseFlags();
        return 0;
    } catch (const RetailStateError& error) {
        std::cout << "{\"status\":\"FAILED_PINNED_PLAYER_BOOL_TRACE\",\"error_code\":" << static_cast<int>(error.Code())
            << ",\"error_offset\":" << error.Offset() << ",\"message\":";
        Text(error.what()); FalseFlags();
    } catch (const std::exception& error) {
        std::cout << "{\"status\":\"FAILED_PINNED_PLAYER_BOOL_TRACE\",\"message\":";
        Text(error.what()); FalseFlags();
    }
    return 1;
}
