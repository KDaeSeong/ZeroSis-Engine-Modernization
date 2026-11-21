#pragma once
// An instrumented interface only. It does not implement actual GameCore objects.
#include <functional>
namespace ZeroSisHost {
class ScriptUtilityFixture final : public ICvScriptSystemUtility1 {
public:
    unsigned registrations=0,destroys=0;
    std::function<void(lua_State*)> registration;
    void* DLLCALL QueryInterface(GUID id) override{return id==guidICvScriptSystemUtility1 || id==guidICvUnknown?this:nullptr;}
    void DLLCALL Destroy() override{++destroys;}
    void DLLCALL RegisterScriptLibraries(lua_State* state) override{++registrations;if(registration)registration(state);}
    void DLLCALL PushCvCityInstance(lua_State*,ICvCity1*) override{Unsupported("fixture city push");}
    ICvCity1* DLLCALL GetCvCityInstance(lua_State*,int,bool) override{Unsupported("fixture city get");}
    void DLLCALL PushCvDealInstance(lua_State*,ICvDeal1*) override{Unsupported("fixture deal push");}
    ICvDeal1* DLLCALL GetCvDealInstance(lua_State*,int,bool) override{Unsupported("fixture deal get");}
    void DLLCALL PushCvPlotInstance(lua_State*,ICvPlot1*) override{Unsupported("fixture plot push");}
    ICvPlot1* DLLCALL GetCvPlotInstance(lua_State*,int,bool) override{Unsupported("fixture plot get");}
    void DLLCALL PushCvUnitInstance(lua_State*,ICvUnit1*) override{Unsupported("fixture unit push");}
    ICvUnit1* DLLCALL GetCvUnitInstance(lua_State*,int,bool) override{Unsupported("fixture unit get");}
    void DLLCALL PushReplayFromStream(lua_State*,FDataStream&) override{Unsupported("fixture replay");}
};
}
