#pragma once
#include "NewGameConfig.h"
#include "NewGameLuaProbe.h"
#include <array>

namespace ZeroSisHost {
class NewGameProbe {
public:
    void Begin(ICvGameContext3& context,HostState& host,Database::Connection& database){
        if(started_)throw std::logic_error("New game probe already started; use a fresh session");
        if(host.gameThread!=GetCurrentThreadId() || !host.gameLock.HeldByCurrentThread())
            throw std::logic_error("New game requires the GameCore owner lock");
        if(!host.scripts || *host.scripts->LastError())throw std::logic_error("New game requires a script service with no prior failures");
        started_=true;std::puts("NEW_GAME_PHASE=read_configuration");
        std::printf("PLATFORM_STATISTICS_AVAILABLE=%s\n",EngineServices::PlatformStatisticsAvailable()?"true":"false");
        const auto config=NewGameConfig::Read(database);
        std::unique_ptr<ICvPreGame1> pregame(context.GetPreGame());
        if(!pregame)throw std::runtime_error("GameCore did not provide the pregame interface");
        std::puts("NEW_GAME_PHASE=apply_configuration");config.ApplyAndVerify(*pregame);
        std::puts("NEW_GAME_CONFIGURATION_VERIFIED");
        std::unique_ptr<ICvGame1> game(context.GetGame());
        if(!game)throw std::runtime_error("GameCore did not provide the game interface");
        std::puts("NEW_GAME_PHASE=game_init");game->Init(config.handicap);
        std::puts("NEW_GAME_PHASE=players_and_map");
        if(!game->Init2())throw std::runtime_error("GameCore Init2 rejected new game creation");
        // The SDK's map generator ignores some Lua call return values. A map
        // built after a script failure must never count as a successful start.
        if(*host.scripts->LastError())throw std::runtime_error(std::string("New-game script failure: ")+host.scripts->LastError());
        std::puts("NEW_GAME_PHASE=observe");
        std::unique_ptr<ICvMap1> map(context.GetMap());
        if(!map)throw std::runtime_error("New game did not provide its map interface");
        values_[0]=map->GetGridWidth();values_[1]=map->GetGridHeight();values_[2]=map->NumPlots();
        values_[3]=game->GetGameTurn();values_[4]=game->IsFinalInitialized()?1:0;
        for(int id=0;id<2;++id){
            std::unique_ptr<ICvPlayer1> player(game->GetPlayer(static_cast<PlayerTypes>(id)));
            if(!player || player->GetID()!=id || !player->IsAlive())throw std::runtime_error("New game major player is missing");
            values_[5+id]=CountUnits(*player);values_[7+id]=player->GetNumCities();
        }
        const auto surface=host.mapSurface.Snapshot();
        if(values_[0]<=0 || values_[1]<=0 || static_cast<long long>(values_[0])*values_[1]!=values_[2]
           || values_[3]!=0 || values_[4]!=1 || values_[5]<=0 || values_[6]<=0
           || !surface || surface->dirtyPlots.size()!=static_cast<std::size_t>(values_[2]))
            throw std::runtime_error("New game/map observation failed");
        const auto lua=InspectNewGameLua(host);
        luaValues_={{lua.plots,lua.land,lua.water,lua.missingTerrain,lua.majorPlayers,lua.minorPlayers,lua.majorUnits,lua.minorUnits}};
        if(lua.plots!=values_[2] || lua.majorUnits!=values_[5]+values_[6])
            throw std::runtime_error("New game SDK and Lua observations differ");
        ready_=true;
    }
    std::string Observation() const {
        if(!ready_)throw std::logic_error("New game probe has not completed");
        std::string result="NEW_GAME_OBSERVATION=";
        for(std::size_t i=0;i<values_.size();++i){if(i)result+=",";result+=std::to_string(values_[i]);}
        result+="\nNEW_GAME_LUA_OBSERVATION=";
        for(std::size_t i=0;i<luaValues_.size();++i){if(i)result+=",";result+=std::to_string(luaValues_[i]);}
        return result;
    }
private:
    static int CountUnits(ICvPlayer1& player){
        int cursor=0;std::set<int> ids;
        std::unique_ptr<ICvUnit1> unit(player.FirstUnit(&cursor));
        while(unit){
            if(!ids.insert(unit->GetID()).second || ids.size()>static_cast<std::size_t>(INT_MAX))
                throw std::runtime_error("New game unit enumeration is invalid");
            unit.reset(player.NextUnit(&cursor));
        }
        return static_cast<int>(ids.size());
    }
    std::array<int,9> values_{};
    std::array<int,8> luaValues_{};
    bool started_=false,ready_=false;
};
}
