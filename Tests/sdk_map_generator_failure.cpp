#include "HostServices.h"

#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <memory>
#include <exception>

using namespace ZeroSisHost;

static unsigned checks = 0;

static void Check(bool value, const char* expression, int line)
{
    ++checks;
    if(!value)
    {
        std::fprintf(stderr, "MAP_GENERATOR_FAILURE_FAILED line=%d %s\n", line, expression);
        std::exit(1);
    }
}

#define CHECK(value) Check((value), #value, __LINE__)

class cvStopWatch
{
public:
    explicit cvStopWatch(const char*) {}
    ~cvStopWatch() {}
};

class CvMapGenerator
{
public:
    explicit CvMapGenerator(const char* mapScriptName);
    ~CvMapGenerator();
    void GenerateRandomMap();

    lua_State* TestState() const { return m_pkLuaState; }

private:
    static int pGenerateRandomMap(lua_State* state);
    lua_State* m_pkLuaState;
};

class FakeDLL
{
public:
    ICvEngineScriptSystem1* GetScriptSystem() const { return scriptSystem; }
    ICvEngineScriptSystem1* scriptSystem = nullptr;
};

static FakeDLL testDLL;
#ifdef gDLL
#undef gDLL
#endif
#define gDLL (&testDLL)

#include "map_generator_failure_methods.inc"

#undef gDLL

int main()
{
    ScriptSystem scripts;
    testDLL.scriptSystem = &scripts;

    scripts.RegisterFile("invalid_map.lua", "function =");
    bool loadFailed = false;
    try
    {
        std::unique_ptr<CvMapGenerator> generator(new CvMapGenerator("invalid_map.lua"));
    }
    catch(const std::exception&)
    {
        loadFailed = true;
    }
    CHECK(loadFailed);
    CHECK(scripts.ThreadCount() == 0);

    scripts.RegisterFile("missing_generate.lua", "return true");
    bool missingFailed = false;
    try
    {
        std::unique_ptr<CvMapGenerator> missing(new CvMapGenerator("missing_generate.lua"));
        missing->GenerateRandomMap();
    }
    catch(const std::exception&)
    {
        missingFailed = true;
    }
    CHECK(missingFailed);
    CHECK(scripts.ThreadCount() == 0);

    scripts.RegisterFile("error_generate.lua",
        "function GenerateMap() error('expected map generation failure') end");
    bool executionFailed = false;
    try
    {
        std::unique_ptr<CvMapGenerator> failing(new CvMapGenerator("error_generate.lua"));
        failing->GenerateRandomMap();
    }
    catch(const std::exception&)
    {
        executionFailed = true;
    }
    CHECK(executionFailed);
    CHECK(scripts.ThreadCount() == 0);

    scripts.RegisterFile("success_generate.lua",
        "function GenerateMap() generated_count = (generated_count or 0) + 1 end");
    std::unique_ptr<CvMapGenerator> successful(new CvMapGenerator("success_generate.lua"));
    successful->GenerateRandomMap();
    lua_getglobal(successful->TestState(), "generated_count");
    CHECK(lua_tointeger(successful->TestState(), -1) == 1);
    lua_pop(successful->TestState(), 1);
    CHECK(scripts.ThreadCount() == 1);
    successful.reset();
    CHECK(scripts.ThreadCount() == 0);

    lua_State* reused = scripts.CreateLuaThread("after-map-generator-failure");
    CHECK(reused != nullptr);
    CHECK(scripts.Execute(reused, "after_failure = 73", std::strlen("after_failure = 73")));
    lua_getglobal(reused, "after_failure");
    CHECK(lua_tointeger(reused, -1) == 73);
    lua_pop(reused, 1);
    scripts.FreeLuaThread(reused);
    CHECK(scripts.ThreadCount() == 0);
    CHECK(scripts.Close());

    std::printf("MAP_GENERATOR_FAILURE_PASS checks=%u GAMECORE_LOADED=false\n", checks);
    return 0;
}
