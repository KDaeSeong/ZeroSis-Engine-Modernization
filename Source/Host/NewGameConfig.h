#pragma once

#include "HostServices.h"
#include <DatabaseResults.h>
#include <array>
#include <map>
#include <string>
#include <vector>

namespace ZeroSisHost {

// Configuration for a reproducible, isolated single-player new-game start.
// All database-backed enum values are resolved from the active rules database;
// no database row IDs are embedded in the host contract.
struct NewGameConfig {
    static constexpr const char* MapScript = "Assets/Maps/Continents.lua";
    static constexpr unsigned int MapSeed = 0x5A17C0DEu;
    static constexpr unsigned int SyncSeed = 0x0BADC0DEu;

    std::array<CivilizationTypes, 2> civilizations{};
    std::array<LeaderHeadTypes, 2> leaders{};
    std::array<MinorCivTypes, 2> minorCivilizations{};
    WorldSizeTypes worldSize{};
    GameSpeedTypes gameSpeed{};
    EraTypes era{};
    HandicapTypes handicap{};
    ClimateTypes climate{};
    SeaLevelTypes seaLevel{};
    CalendarTypes calendar{};
    TurnTimerTypes turnTimer{};
    std::map<std::string, int> mapOptions;
    std::map<std::string, int> gameOptions;
    std::vector<VictoryTypes> victories;

    static NewGameConfig Read(Database::Connection& database) {
        NewGameConfig config;
        config.civilizations[0] = static_cast<CivilizationTypes>(TypeId(database, "Civilizations", "CIVILIZATION_AMERICA"));
        config.leaders[0] = static_cast<LeaderHeadTypes>(TypeId(database, "Leaders", "LEADER_WASHINGTON"));
        config.civilizations[1] = static_cast<CivilizationTypes>(TypeId(database, "Civilizations", "CIVILIZATION_ROME"));
        config.leaders[1] = static_cast<LeaderHeadTypes>(TypeId(database, "Leaders", "LEADER_AUGUSTUS"));
        config.worldSize = static_cast<WorldSizeTypes>(TypeId(database, "Worlds", "WORLDSIZE_DUEL"));
        config.gameSpeed = static_cast<GameSpeedTypes>(TypeId(database, "GameSpeeds", "GAMESPEED_STANDARD"));
        config.era = static_cast<EraTypes>(TypeId(database, "Eras", "ERA_ANCIENT"));
        config.handicap = static_cast<HandicapTypes>(TypeId(database, "HandicapInfos", "HANDICAP_PRINCE"));
        config.climate = static_cast<ClimateTypes>(TypeId(database, "Climates", "CLIMATE_TEMPERATE"));
        config.seaLevel = static_cast<SeaLevelTypes>(TypeId(database, "SeaLevels", "SEALEVEL_MEDIUM"));
        config.calendar = static_cast<CalendarTypes>(TypeId(database, "Calendars", "CALENDAR_DEFAULT"));
        config.turnTimer = static_cast<TurnTimerTypes>(TypeId(database, "TurnTimers", "TURNTIMER_MEDIUM"));

        const auto minorIds = TypeIds(database, "MinorCivilizations", 2);
        config.minorCivilizations[0] = static_cast<MinorCivTypes>(minorIds[0]);
        config.minorCivilizations[1] = static_cast<MinorCivTypes>(minorIds[1]);

        // The SDK's Continents.lua reads custom option IDs 1..5. Its shipped
        // rule rows use the script's actual database filename and default values.
        Database::Results mapRows;
        Require(database, database.Execute(mapRows,
            "SELECT OptionID, DefaultValue FROM MapScriptOptions "
            "WHERE FileName=? ORDER BY CAST(OptionID AS INTEGER), OptionID"), "MapScriptOptions query");
        Require(database, mapRows.Bind(1, "Assets\\Maps\\Continents.lua"), "MapScriptOptions bind");
        while (mapRows.Step()) {
            const char* rawId = mapRows.GetText(0);
            if (!rawId) throw std::runtime_error("Continents.lua has a null custom-option ID");
            const std::string optionId(rawId);
            const int value = mapRows.GetInt(1);
            if ((optionId != "1" && optionId != "2" && optionId != "3" && optionId != "4" && optionId != "5") ||
                value < 1 || value > 4 || !config.mapOptions.emplace(optionId, value).second)
                throw std::runtime_error("Continents.lua custom-option rows are invalid or duplicated");
        }
        Complete(database, "MapScriptOptions iteration");
        if (config.mapOptions.size() != 5)
            throw std::runtime_error("Continents.lua must expose exactly five current database custom-option defaults");

        Database::Results gameOptionRows;
        Require(database, database.Execute(gameOptionRows,
            "SELECT Type, \"Default\" FROM GameOptions ORDER BY ID"), "GameOptions query");
        while (gameOptionRows.Step()) {
            const char* rawType = gameOptionRows.GetText(0);
            if (!rawType) throw std::runtime_error("GameOptions contains a null Type");
            if (!config.gameOptions.emplace(rawType, gameOptionRows.GetInt(1)).second)
                throw std::runtime_error("GameOptions contains a duplicate Type");
        }
        Complete(database, "GameOptions iteration");
        if (config.gameOptions.empty()) throw std::runtime_error("The rules database contains no game options");
        const auto timerOption = config.gameOptions.find("GAMEOPTION_END_TURN_TIMER_ENABLED");
        if (timerOption == config.gameOptions.end() || timerOption->second != 0)
            throw std::runtime_error("Single-player defaults must leave the end-turn timer option disabled");

        Database::Results victoryRows;
        Require(database, database.Execute(victoryRows, "SELECT ID FROM Victories ORDER BY ID"), "Victories query");
        while (victoryRows.Step()) {
            const int id = victoryRows.GetInt(0);
            if (id != static_cast<int>(config.victories.size()))
                throw std::runtime_error("Victories IDs are not a contiguous SDK enum sequence");
            config.victories.push_back(static_cast<VictoryTypes>(id));
        }
        Complete(database, "Victories iteration");
        if (config.victories.empty()) throw std::runtime_error("The rules database contains no victory definitions");
        return config;
    }

    void ApplyAndVerify(ICvPreGame1& pregame) const {
        // These setters have reset side effects in the SDK. Set the map first,
        // then apply its custom options after the script name has cleared them.
        pregame.setGameType(GAME_SINGLE_PLAYER, GAME_NEW);
        // The pregame static vectors predate database caching. Reset them now
        // so victories and every player's team/color/handicap have SDK defaults.
        pregame.resetGame();
        pregame.resetPlayers();
        pregame.setMapScriptName(CvString(MapScript));
        pregame.setWorldSize(worldSize, false);
        pregame.closeAllSlots();

        pregame.setGameSpeed(gameSpeed);
        // CvPreGame::setGameSpeed(STANDARD) selects TURNTIMER_MEDIUM. Reapply
        // the DB-resolved enum after that side effect and keep SP timer disabled.
        pregame.setTurnTimer(turnTimer);
        pregame.setEra(era);
        pregame.setClimate(climate);
        pregame.setSeaLevel(seaLevel);
        pregame.setCalendar(calendar);
        pregame.setGameTurn(0);
        pregame.setMapRandomSeed(MapSeed);
        pregame.setSyncRandomSeed(SyncSeed);
        pregame.setNumMinorCivs(2);

        for (int slot = 0; slot < 2; ++slot) {
            const auto player = static_cast<PlayerTypes>(slot);
            pregame.setCivilization(player, civilizations[slot]);
            pregame.setLeaderHead(player, leaders[slot]);
            pregame.setTeamType(player, static_cast<TeamTypes>(slot));
            pregame.setHandicap(player, handicap);
            pregame.setPlayable(player, true);
            pregame.setSlotStatus(player, slot == 0 ? SS_TAKEN : SS_COMPUTER);
        }
        pregame.setActivePlayer(static_cast<PlayerTypes>(0));

        for (int index = 0; index < 2; ++index) {
            const auto player = static_cast<PlayerTypes>(MAX_MAJOR_CIVS + index);
            pregame.setMinorCivType(player, minorCivilizations[index]);
            pregame.setMinorCiv(player, true);
            pregame.setSlotStatus(player, SS_COMPUTER);
        }

        for (const auto& option : mapOptions) {
            if (!pregame.SetMapOption(option.first.c_str(), option.second))
                throw std::runtime_error("GameCore rejected a Continents.lua custom option");
        }
        for (const auto& option : gameOptions) {
            if (!pregame.SetGameOption(option.first.c_str(), option.second))
                throw std::runtime_error("GameCore rejected a database-default game option");
        }
        for (const auto victory : victories) pregame.setVictory(victory, true);

        if (pregame.gameType() != GAME_SINGLE_PLAYER || pregame.gameStartType() != GAME_NEW ||
            pregame.mapScriptName() != CvString(MapScript) || pregame.worldSize() != worldSize ||
            pregame.gameSpeed() != gameSpeed || pregame.turnTimer() != turnTimer || pregame.era() != era ||
            pregame.climate() != climate || pregame.seaLevel() != seaLevel || pregame.calendar() != calendar ||
            pregame.gameTurn() != 0 || pregame.mapRandomSeed() != MapSeed || pregame.syncRandomSeed() != SyncSeed ||
            pregame.numMinorCivs() != 2 || pregame.activePlayer() != static_cast<PlayerTypes>(0))
            throw std::runtime_error("GameCore pregame scalar configuration verification failed");

        for (int slot = 0; slot < 2; ++slot) {
            const auto player = static_cast<PlayerTypes>(slot);
            if (pregame.civilization(player) != civilizations[slot] || pregame.leaderHead(player) != leaders[slot] ||
                pregame.teamType(player) != static_cast<TeamTypes>(slot) || pregame.handicap(player) != handicap ||
                pregame.slotStatus(player) != (slot == 0 ? SS_TAKEN : SS_COMPUTER) || !pregame.isPlayable(player))
                throw std::runtime_error("GameCore major-player configuration verification failed");
        }
        for (int index = 0; index < 2; ++index) {
            const auto player = static_cast<PlayerTypes>(MAX_MAJOR_CIVS + index);
            if (pregame.minorCivType(player) != minorCivilizations[index] || !pregame.isMinorCiv(player))
                throw std::runtime_error("GameCore city-state slot configuration verification failed");
        }
        if (pregame.GetMapOptionCount() != mapOptions.size())
            throw std::runtime_error("GameCore map-option count differs from Continents.lua defaults");
        for (const auto& option : mapOptions) {
            int actual = 0;
            if (!pregame.GetMapOption(option.first.c_str(), actual) || actual != option.second)
                throw std::runtime_error("GameCore map-option default verification failed");
        }
        if (pregame.GetGameOptionCount() != gameOptions.size())
            throw std::runtime_error("GameCore game-option count differs from the active database defaults");
        for (const auto& option : gameOptions) {
            int actual = 0;
            if (!pregame.GetGameOption(option.first.c_str(), actual) || actual != option.second)
                throw std::runtime_error("GameCore database-default game-option verification failed");
        }
        for (const auto victory : victories) {
            if (!pregame.isVictory(victory)) throw std::runtime_error("GameCore victory default verification failed");
        }
    }

private:
    static void Require(Database::Connection& database, bool ok, const char* operation) {
        if (!ok) throw std::runtime_error(std::string(operation) + ": " +
            (database.ErrorMessage() ? database.ErrorMessage() : "database operation failed"));
    }
    static void Complete(Database::Connection& database, const char* operation) {
        const int code = database.ErrorCode();
        if (code != 0 && code != 101)
            throw std::runtime_error(std::string(operation) + ": database iteration failed");
    }
    static int TypeId(Database::Connection& database, const char* table, const char* type) {
        const std::string sql = std::string("SELECT ID FROM ") + table + " WHERE Type=? LIMIT 2";
        Database::Results rows;
        Require(database, database.Execute(rows, sql.c_str()), "Type lookup");
        Require(database, rows.Bind(1, type), "Type bind");
        if (!rows.Step()) { Complete(database, "Type lookup"); throw std::runtime_error(std::string("Missing rules Type: ") + type); }
        const int id = rows.GetInt(0);
        if (rows.Step()) throw std::runtime_error(std::string("Duplicate rules Type: ") + type);
        Complete(database, "Type lookup");
        if (id < 0) throw std::runtime_error(std::string("Negative rules enum ID: ") + type);
        return id;
    }
    static std::array<int, 2> TypeIds(Database::Connection& database, const char* table, int required) {
        if (required != 2) throw std::logic_error("This configuration requires exactly two city-state types");
        const std::string sql = std::string("SELECT ID FROM ") + table + " ORDER BY ID LIMIT 3";
        Database::Results rows;
        Require(database, database.Execute(rows, sql.c_str()), "City-state type query");
        std::array<int, 2> ids{};
        int count = 0;
        while (rows.Step()) {
            if (count < 2) ids[static_cast<std::size_t>(count)] = rows.GetInt(0);
            ++count;
        }
        Complete(database, "City-state type iteration");
        if (count < 2 || ids[0] < 0 || ids[1] < 0 || ids[0] == ids[1])
            throw std::runtime_error("The rules database must contain at least two distinct city-state types");
        return ids;
    }
};

} // namespace ZeroSisHost
