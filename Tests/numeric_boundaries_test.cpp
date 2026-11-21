#include "CvCheckedNarrow.h"
#include "CvLuaCheckedInteger.h"
#include "CvAutoArchiveSupport.h"
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <vector>
#include <tchar.h>

static unsigned long checks = 0, luaCases = 0, rejected = 0, recoveries = 0;
static int committed = 0;
static void Require(bool condition)
{
    ++checks;
    if (!condition) { std::fprintf(stderr, "Failed assertion %lu\n", checks); std::exit(2); }
}
template<class To, class From> static void Convert(From source, FILE* output)
{
    To value = 42;
    const bool valid = CvChecked::TryInteger(source, value);
    bool threw = false;
    try { Require(CvChecked::Integer<To>(source) == value); }
    catch (const std::range_error&) { threw = true; }
    Require(threw != valid);
    if (!valid) Require(value == 42); // Failure must not publish a partial result.
    const unsigned char success = valid ? 1 : 0;
    const std::uint64_t bits = valid ? static_cast<std::uint64_t>(value) : 0;
    Require(std::fwrite(&success, 1, 1, output) == 1);
    Require(std::fwrite(&bits, sizeof(bits), 1, output) == 1);
}
template<class From> static void Target(unsigned char target, From source, FILE* output)
{
    switch (target) {
    case 0: Convert<std::int8_t>(source, output); break;
    case 1: Convert<std::uint8_t>(source, output); break;
    case 2: Convert<std::int16_t>(source, output); break;
    case 3: Convert<std::uint16_t>(source, output); break;
    case 4: Convert<std::int32_t>(source, output); break;
    case 5: Convert<std::uint32_t>(source, output); break;
    case 6: Convert<std::int64_t>(source, output); break;
    case 7: Convert<std::uint64_t>(source, output); break;
    case 8: Convert<std::size_t>(source, output); break;
    case 9: Convert<std::ptrdiff_t>(source, output); break;
    default: Require(false);
    }
}

// Definitions below are extracted verbatim from the generated SDK port by the
// verifier. Only their surrounding owner/allocation harness is supplied here.
struct TestOwner {
    int touches = 0;
    template<class T> void touch(T&) { ++touches; }
};
template<class T, class Owner> class FAutoVariable;
template<class ElementType> struct AutoVectorCommand;
template<class ElementType, class ClassContainer>
class FAutoVariable<std::vector<ElementType>, ClassContainer> {
public:
    ClassContainer m_owner;
    std::vector<ElementType> m_value;
    std::vector<AutoVectorCommand<ElementType>> m_commands;
    void setAt(std::size_t index, const ElementType& v);
    void insert(std::size_t index, const ElementType& v);
    void erase(std::size_t index);
    void resize(std::size_t count);
    void resize(std::size_t count, const ElementType& v);
};
class CvDatabaseUtility {
public:
    void Initialize2DArray(int**& array, std::size_t rows, std::size_t columns, int value);
    void SafeDelete2DArray(int**& array);
};
#define FNEW(expression, category, flags) new expression
#define CvAssertMsg(condition, message) ((void)0)
namespace FLua {
static int errors = 0;
inline void Error(const char*) { ++errors; }
namespace Details {
template<class T> struct ArgValidator;
template<class T> struct FromLuaAnalog;
}
}
typedef unsigned int uint;
#include "sdk_numeric_extracts.h"
#undef FNEW
#undef CvAssertMsg

static int ToInt(lua_State* state) { const int value = CvLuaChecked::ToInt(state, 1); ++committed; lua_pushinteger(state, value); return 1; }
static int CheckInt(lua_State* state) { const int value = CvLuaChecked::CheckInt(state, 1); ++committed; lua_pushinteger(state, value); return 1; }
static int OptInt(lua_State* state) { const int value = CvLuaChecked::OptInt(state, 1, -7); ++committed; lua_pushinteger(state, value); return 1; }
static int CheckUInt(lua_State* state) { const unsigned int value = CvLuaChecked::CheckUInt(state, 1); ++committed; lua_pushinteger(state, value); return 1; }
static int ToNative(lua_State* state) { const lua_Integer value = CvLuaChecked::ToInteger(state, 1); ++committed; lua_pushinteger(state, value); return 1; }

enum InputKind { NUMBER, STRING, BOOLEAN, NIL, MISSING };
static void LuaCase(lua_State* state, lua_CFunction function, InputKind kind, double number,
                    const char* text, bool valid, lua_Integer expected)
{
    ++luaCases;
    lua_settop(state, 0);
    committed = 0;
    lua_pushcfunction(state, function);
    switch (kind) {
    case NUMBER: lua_pushnumber(state, number); break;
    case STRING: lua_pushstring(state, text); break;
    case BOOLEAN: lua_pushboolean(state, 1); break;
    case NIL: lua_pushnil(state); break;
    case MISSING: break;
    }
    const int result = lua_pcall(state, kind == MISSING ? 0 : 1, 1, 0);
    Require((result == 0) == valid);
    Require(lua_gettop(state) == 1);
    Require(committed == (valid ? 1 : 0));
    if (valid) Require(lua_tointeger(state, -1) == expected);
    else {
        ++rejected;
        Require(lua_type(state, -1) == LUA_TSTRING);
        lua_settop(state, 0);
        lua_pushcfunction(state, ToInt);
        lua_pushnumber(state, 7);
        Require(lua_pcall(state, 1, 1, 0) == 0 && lua_tointeger(state, -1) == 7);
        ++recoveries;
    }
}

template<class Function> static void RangeFailure(Function function)
{
    bool caught = false;
    try { function(); } catch (const std::range_error&) { caught = true; }
    Require(caught);
}
template<class Function> static void SizeFailure(Function function)
{
    bool caught = false;
    try { function(); } catch (const std::bad_array_new_length&) { caught = true; }
    Require(caught);
}

int main(int argc, char** argv)
{
    Require(argc == 4 && sizeof(void*) == 8 && sizeof(int) == 4 && sizeof(lua_Integer) == 8);
    FILE* input = std::fopen(argv[1], "rb");
    FILE* output = std::fopen(argv[2], "wb");
    Require(input && output);
    char magic[8]; std::uint32_t records = 0;
    Require(std::fread(magic, 1, 8, input) == 8 && std::memcmp(magic, "ZNRW0001", 8) == 0);
    Require(std::fread(&records, sizeof(records), 1, input) == 1);
    for (std::uint32_t i = 0; i < records; ++i) {
        unsigned char kind = 0, target = 0; std::uint64_t bits = 0;
        Require(std::fread(&kind, 1, 1, input) == 1 && std::fread(&target, 1, 1, input) == 1);
        Require(std::fread(&bits, sizeof(bits), 1, input) == 1);
        if (kind == 0) {
            std::int64_t value;
            std::memcpy(&value, &bits, sizeof(value));
            Target(target, value, output);
        } else { Require(kind == 1); Target(target, bits, output); }
    }
    Require(std::fgetc(input) == EOF);
    std::fclose(input); Require(std::fclose(output) == 0);
    FILE* hashes = std::fopen(argv[3], "wb");
    Require(hashes != NULL);
    Require(std::fwrite(V1_IndexToHash, sizeof(V1_IndexToHash), 1, hashes) == 1);
    Require(std::fclose(hashes) == 0);

    const std::size_t maximum = (std::numeric_limits<std::size_t>::max)();
    Require(CvChecked::AddBytes(maximum, 0) == maximum);
    Require(CvChecked::MultiplyBytes(maximum, 0) == 0);
    Require(CvChecked::MultiplyBytes(maximum, 1) == maximum);
    Require(CvChecked::Array2DBytes(2, 3, 4, 8) == 40);
    Require(CvChecked::Array2DBytes(0, maximum, 4, 8) == 0);
    SizeFailure([&] { CvChecked::AddBytes(maximum, 1); });
    SizeFailure([&] { CvChecked::MultiplyBytes(maximum, 2); });
    SizeFailure([&] { CvChecked::Array2DBytes(maximum, 2, 4, 8); });
    Require(CvChecked::CountProduct(-3, 7) == -21);
    Require(CvChecked::CountProduct(2147483647, 1) == 2147483647);
    Require(CvChecked::CountProduct((-2147483647 - 1), 1) == (-2147483647 - 1));
    RangeFailure([] { CvChecked::CountProduct(2147483647, 2); });
    RangeFailure([] { CvChecked::CountProduct((-2147483647 - 1), 2); });
    Require(CvChecked::Integer<int>(std::size_t(0)) - 1 == -1);
    Require(CvChecked::Integer<int>(std::size_t(1)) - 1 == 0);

    FAutoVariable<std::vector<int>, TestOwner> tracked;
    tracked.m_value.push_back(5);
    const std::size_t tooLarge = std::size_t(0xffffffffu) + 1;
    // A nonexistent element is rejected by native-size bounds before wire narrowing.
    bool badIndex = false;
    try { tracked.setAt(tooLarge, 8); } catch (const std::out_of_range&) { badIndex = true; } Require(badIndex);
    badIndex = false;
    try { tracked.insert(tooLarge, 8); } catch (const std::out_of_range&) { badIndex = true; } Require(badIndex);
    badIndex = false;
    try { tracked.erase(tooLarge); } catch (const std::out_of_range&) { badIndex = true; } Require(badIndex);
    RangeFailure([&] { tracked.resize(tooLarge); });
    RangeFailure([&] { tracked.resize(tooLarge, 8); });
    Require(tracked.m_owner.touches == 0 && tracked.m_commands.empty() && tracked.m_value == std::vector<int>{5});
    tracked.setAt(0, 5); Require(tracked.m_owner.touches == 0);
    tracked.setAt(0, 8); tracked.insert(1, 9); tracked.erase(0); tracked.resize(3); tracked.resize(4, 7);
    Require(tracked.m_value == std::vector<int>({9, 0, 0, 7}));
    Require(tracked.m_owner.touches == 5 && tracked.m_commands.size() == 5);
    const unsigned int commandIndices[] = {0, 1, 0, 3, 4};
    const unsigned char commandTypes[] = {2, 1, 0, 5, 6};
    for (std::size_t i = 0; i < 5; ++i) {
        Require(tracked.m_commands[i].index == commandIndices[i] && tracked.m_commands[i].command == commandTypes[i]);
    }
    Require(sizeof(tracked.m_commands[0].index) == 4 && sizeof(tracked.m_commands[0].command) == 1);

    CvDatabaseUtility database; int** array = NULL;
    database.Initialize2DArray(array, 2, 3, -9);
    Require(array != NULL && array[1] - array[0] == 3);
    for (std::size_t r = 0; r < 2; ++r) for (std::size_t c = 0; c < 3; ++c) Require(array[r][c] == -9);
    array[1][2] = 17; Require(array[0][2] == -9 && array[1][2] == 17);
    database.SafeDelete2DArray(array); Require(array == NULL);
    SizeFailure([&] { database.Initialize2DArray(array, maximum, 2, 0); });
    Require(array == NULL);
    database.Initialize2DArray(array, 0, 3, 0); Require(array == NULL);
    database.Initialize2DArray(array, 1, 1, 123); Require(array[0][0] == 123);
    database.SafeDelete2DArray(array); Require(array == NULL);

    lua_Integer analog = 2147483648LL; bool valid = true;
    FLua::Details::ArgValidator<int>::Validate(analog, valid);
    Require(!valid && FLua::errors == 1);
    analog = -2147483647LL - 1; valid = true;
    FLua::Details::ArgValidator<int>::Validate(analog, valid);
    Require(valid && FLua::Details::FromLuaAnalog<int>::Convert(analog) == (-2147483647 - 1));
    analog = 2147483647; valid = true;
    FLua::Details::ArgValidator<const int>::Validate(analog, valid);
    Require(valid && FLua::Details::FromLuaAnalog<const int>::Convert(analog) == 2147483647);

    lua_State* state = luaL_newstate(); Require(state != NULL);
    for (lua_CFunction function : {ToInt, CheckInt, OptInt}) {
        for (double value : {-2147483648.0, -1.0, 0.0, 1.0, 2147483647.0})
            LuaCase(state, function, NUMBER, value, NULL, true, static_cast<lua_Integer>(value));
        for (double value : {-2147483649.0, 2147483648.0, 4294967295.0, 1e100, -1e100,
                             std::numeric_limits<double>::infinity(), -std::numeric_limits<double>::infinity(),
                             std::numeric_limits<double>::quiet_NaN()})
            LuaCase(state, function, NUMBER, value, NULL, false, 0);
        LuaCase(state, function, STRING, 0, " 42 ", true, 42);
        LuaCase(state, function, STRING, 0, "2147483648", false, 0);
    }
    for (InputKind kind : {BOOLEAN, NIL, MISSING}) {
        LuaCase(state, ToInt, kind, 0, NULL, true, 0);
        LuaCase(state, CheckInt, kind, 0, NULL, false, 0);
        LuaCase(state, OptInt, kind, 0, NULL, kind != BOOLEAN, -7);
    }
    LuaCase(state, ToInt, STRING, 0, "invalid", true, 0);
    LuaCase(state, CheckInt, STRING, 0, "invalid", false, 0);
    for (double value : {0.0, 1.0, 2147483648.0, 4294967295.0})
        LuaCase(state, CheckUInt, NUMBER, value, NULL, true, static_cast<lua_Integer>(value));
    for (double value : {-1.0, -0.75, 4294967296.0, 1e100, std::numeric_limits<double>::quiet_NaN()})
        LuaCase(state, CheckUInt, NUMBER, value, NULL, false, 0);
    LuaCase(state, ToNative, NUMBER, -9223372036854775808.0, NULL, true, (std::numeric_limits<lua_Integer>::min)());
    LuaCase(state, ToNative, NUMBER, 9223372036854775808.0, NULL, false, 0);
    LuaCase(state, ToNative, NUMBER, std::nextafter(-9223372036854775808.0, -1e100), NULL, false, 0);
    // Within one provider the adapter must keep its integer-conversion rounding.
    for (double value : {-42.75, -1.5, -0.5, 0.5, 1.5, 42.75}) {
        lua_settop(state, 0); lua_pushnumber(state, value);
        const lua_Integer native = lua_tointeger(state, -1);
        LuaCase(state, ToInt, NUMBER, value, NULL, true, native);
    }
    lua_close(state);
    std::printf("{\"status\":\"PASS\",\"scope\":\"NUMERIC_AND_EXTRACTED_SDK_COMPONENTS_ONLY\","
                "\"records\":%u,\"checks\":%lu,\"lua_cases\":%lu,\"lua_rejections\":%lu,\"lua_recoveries\":%lu,"
                "\"notification_entries\":%llu}\n", records, checks, luaCases, rejected, recoveries,
                static_cast<unsigned long long>(sizeof(V1_IndexToHash) / sizeof(V1_IndexToHash[0])));
    return 0;
}
