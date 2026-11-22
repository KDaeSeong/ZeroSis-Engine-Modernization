#pragma once

#include "HostServices.h"

namespace ZeroSisHost {
namespace TurnBenchmarkObservation {
inline bool Enabled() {
    wchar_t value[2]{};
    return GetEnvironmentVariableW(L"ZEROSIS_FULL_TURN_BENCHMARK", value, 2) == 1 && value[0] == L'1';
}

inline unsigned long SyncSeed(ICvGame1& game) {
    std::unique_ptr<ICvRandom1> random(game.GetRandomNumberGenerator());
    if (!random) throw std::runtime_error("Missing SDK synchronous RNG");
    return random->GetSeed();
}

inline std::string UnitOrder(ICvPlayer1& player, int& count) {
    std::string ids;
    int cursor = 0;
    std::unique_ptr<ICvUnit1> unit(player.FirstUnit(&cursor));
    while (unit) {
        if (count++) ids += ',';
        ids += std::to_string(unit->GetID());
        unit.reset(player.NextUnit(&cursor));
    }
    return ids;
}

inline int ReadSkippedUnits(lua_State* vm) {
    auto* ids = static_cast<std::string*>(lua_touserdata(vm, 1));
    lua_getglobal(vm, "ZeroSisTurnBenchmarkSkips");
    if (!ids || lua_type(vm, -1) != LUA_TSTRING) return luaL_error(vm, "Missing benchmark mission order");
    std::size_t size = 0;
    const char* data = lua_tolstring(vm, -1, &size);
    ids->assign(data, size);
    lua_pop(vm, 1);
    lua_pushnil(vm);
    lua_setglobal(vm, "ZeroSisTurnBenchmarkSkips");
    return 0;
}

inline void End(ICvGame1& game, HostState& host, lua_State* vm, const char* prefix, std::size_t firstEvent,
                const std::string& nativeOrder) {
    const auto seed = SyncSeed(game);
    std::string skipped;
    if (!host.scripts->CallCFunction(vm, &ReadSkippedUnits, &skipped))
        throw std::runtime_error(host.scripts->LastError());
    if (nativeOrder != skipped) throw std::runtime_error("SDK mission recipients differ from the native unit roster");
    std::printf("%s_BENCH_SKIPPED_UNITS=%s\n", prefix, skipped.empty() ? "-" : skipped.c_str());
    const auto events = host.Events();
    if (events.size() < firstEvent) throw std::logic_error("Turn event stream was reset");
    std::size_t count = 0;
    for (std::size_t i = firstEvent; i < events.size(); ++i) {
        const auto& event = events[i];
        if (event.compare(0, 6, "local-") == 0) {
            std::printf("%s_BENCH_EVENT=%zu|%s\n", prefix, count, event.c_str());
            ++count;
        }
    }
    std::printf("%s_BENCH_END=%d|%lu|%zu\n", prefix, game.GetGameTurn(), seed, count);
}
}
}
