#pragma once
struct lua_State;
namespace ZeroSisHost {
// The service owns this source until every VM, including its finalizers, is closed.
class ScriptRules {
public:
    virtual ~ScriptRules()=default;
    virtual void Install(lua_State* state)=0;
};
}
