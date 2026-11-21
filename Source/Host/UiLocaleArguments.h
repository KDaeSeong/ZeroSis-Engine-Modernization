#pragma once

extern "C" {
#include <lua.h>
}

#include <cmath>
#include <stdexcept>

namespace ZeroSisHost {

// Retail Locale.Lookup (0x5cc8d0) and Locale.ConvertTextKey (0x70d450) push every argument after the key
// by its Lua type (evidence/game_menu/replay_season_wheel/retail_static_probe.json, locale.functions):
//   boolean -> lua_toboolean -> Localization::String::PushArgument(int)   true=1, false=0
//   number  -> lua_tonumber  -> Localization::String::PushArgument(double) integral values included
//   string  -> lua_tolstring -> Localization::String::PushArgument(const char*)
//   other   -> a Lua type error
// The string branch keeps this Host's key lookup and NUL rejection supplied by the caller. Nonfinite numbers
// stay rejected: the original rule-based ICU path recurses without bound on them.
template<class Value,class TextArgument>
bool PushRetailLocaleArgument(lua_State* state,int index,Value& value,TextArgument&& text){
    switch(lua_type(state,index)){
    case LUA_TBOOLEAN:return value.PushArgument(lua_toboolean(state,index)?1:0);
    case LUA_TNUMBER:{
        const double number=static_cast<double>(lua_tonumber(state,index));
        if(!std::isfinite(number))throw std::invalid_argument("Nonfinite localization argument");
        return value.PushArgument(number);
    }
    case LUA_TSTRING:return value.PushArgument(text(index));
    default:throw std::invalid_argument("Unsupported localization argument type");
    }
}

} // namespace ZeroSisHost
