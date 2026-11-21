#include "HostServices.h"
#include "GameDefinesDatabase.h"
#include <cstdio>
#include <cstdlib>
#include <cstring>

using namespace ZeroSisHost;

static unsigned checks = 0;
static void Check(bool value, int line) {
    ++checks;
    if (!value) {
        std::fprintf(stderr, "GAME_DEFINES_FAILED line=%d\n", line);
        std::exit(1);
    }
}
#define CHECK(value) Check((value), __LINE__)

struct Memory {
    int budget = -1;
    std::size_t bytes = 0, blocks = 0;
    static void* Allocate(void* context, void* pointer, std::size_t oldSize, std::size_t newSize) {
        auto& self = *static_cast<Memory*>(context);
        if (!newSize) {
            if (pointer) { self.bytes -= oldSize; --self.blocks; std::free(pointer); }
            return nullptr;
        }
        if (newSize > oldSize && self.budget >= 0 && self.budget-- == 0) {
            self.budget = -1;
            return nullptr;
        }
        void* result = std::realloc(pointer, newSize);
        if (result) {
            if (!pointer) ++self.blocks;
            self.bytes = self.bytes - oldSize + newSize;
        }
        return result;
    }
};

class DefinesRules final : public ScriptRules {
public:
    explicit DefinesRules(Database::Connection& database) : database_(database) {}
    void Install(lua_State* state) override { InstallGameDefines(state, database_); }
private:
    Database::Connection& database_;
};

static void Execute(ScriptSystem& scripts, lua_State* state, const char* source) {
    if (!scripts.Execute(state, source, std::strlen(source))) {
        std::fprintf(stderr, "%s\n", scripts.LastError());
        CHECK(false);
    }
    CHECK(lua_gettop(state) == 0);
}

static void CreateFixture(Database::Connection& database) {
    CHECK(database.ExecuteMultiple(
        "CREATE TABLE Defines(Name TEXT NOT NULL UNIQUE, Value);"
        "INSERT INTO Defines VALUES('POSTPROCESSED_ID', 41);"
        "INSERT INTO Defines VALUES('REAL_VALUE', -0.125);"
        "INSERT INTO Defines VALUES('TEXT_VALUE', CAST(x'610062' AS TEXT));"
        "INSERT INTO Defines VALUES('TEXT_NUMBER', '7');"
        "INSERT INTO Defines VALUES('NULL_VALUE', NULL);"));
}

int main() {
    try {
        Database::Connection database;
        CHECK(database.Open(":memory:", Database::OPEN_READWRITE | Database::OPEN_CREATE | Database::OPEN_FULLMUTEX));
        CreateFixture(database);

        ScriptSystem scripts;
        scripts.BindRules(std::make_shared<DefinesRules>(database));
        lua_State* first = scripts.CreateLuaThread("game-defines-first");
        Execute(scripts, first, R"lua(
assert(type(GameDefines)=='table')
assert(GameDefines.POSTPROCESSED_ID==41 and type(GameDefines.POSTPROCESSED_ID)=='number')
assert(GameDefines.REAL_VALUE==-0.125 and type(GameDefines.REAL_VALUE)=='number')
assert(GameDefines.TEXT_VALUE==string.char(97,0,98) and type(GameDefines.TEXT_VALUE)=='string')
assert(GameDefines.TEXT_NUMBER=='7' and type(GameDefines.TEXT_NUMBER)=='string' and GameDefines.TEXT_NUMBER~=7)
assert(GameDefines.NULL_VALUE==nil)
)lua");
        CHECK(database.StatementCount() == 0);

        // SQLite INTEGER values outside Lua 5.1's exact double range are
        // rejected rather than being silently rounded.
        CHECK(database.Execute("UPDATE Defines SET Value=9007199254740992 WHERE Name='POSTPROCESSED_ID'"));
        bool rangeFailed = false;
        try { scripts.CreateLuaThread("game-defines-integer-overflow"); }
        catch (const std::exception&) { rangeFailed = true; }
        CHECK(rangeFailed && scripts.ThreadCount() == 1 && database.StatementCount() == 0);
        CHECK(database.Execute("UPDATE Defines SET Value=41 WHERE Name='POSTPROCESSED_ID'"));

        // A VM keeps the values captured at its creation; a newly created VM
        // reads the changed live DB rows rather than a process-global cache.
        CHECK(database.Execute("UPDATE Defines SET Value=8080 WHERE Name='POSTPROCESSED_ID'"));
        Execute(scripts, first, "assert(GameDefines.POSTPROCESSED_ID==41)");
        scripts.FreeLuaThread(first);
        CHECK(scripts.ThreadCount() == 0 && database.StatementCount() == 0);

        lua_State* second = scripts.CreateLuaThread("game-defines-second");
        Execute(scripts, second, "assert(GameDefines.POSTPROCESSED_ID==8080)");
        scripts.FreeLuaThread(second);
        CHECK(scripts.ThreadCount() == 0 && database.StatementCount() == 0);

        // A missing Defines table must fail protected VM creation and release
        // its statement/snapshot; restoring the table must allow a clean retry.
        CHECK(database.Execute("DROP TABLE Defines"));
        bool failed = false;
        try {
            scripts.CreateLuaThread("game-defines-query-failure");
        } catch (const std::exception&) {
            failed = true;
        }
        CHECK(failed && scripts.ThreadCount() == 0 && database.StatementCount() == 0);

        CHECK(database.ExecuteMultiple(
            "CREATE TABLE Defines(Name TEXT NOT NULL UNIQUE, Value);"
            "INSERT INTO Defines VALUES('POSTPROCESSED_ID', 9090);"
            "INSERT INTO Defines VALUES('TEXT_NUMBER', '7');"
            "INSERT INTO Defines VALUES('NULL_VALUE', NULL);"));
        lua_State* recovered = scripts.CreateLuaThread("game-defines-recovered");
        Execute(scripts, recovered, "assert(GameDefines.POSTPROCESSED_ID==9090 and GameDefines.NULL_VALUE==nil)");
        scripts.FreeLuaThread(recovered);
        CHECK(scripts.ThreadCount() == 0 && database.StatementCount() == 0);

        CHECK(scripts.Close());

        // Fail each successive Lua allocator growth during VM creation. This
        // walks through GameDefines publication too; after every failed
        // creation, the same ScriptSystem must successfully create and retire
        // a VM before the next injected failure is attempted.
        unsigned createFailures = 0;
        bool reachedSuccessfulBudget = false;
        {
            Memory memory;
            ScriptSystem retryScripts(&Memory::Allocate, &memory);
            retryScripts.BindRules(std::make_shared<DefinesRules>(database));
            for (int n = 0; n < 2000; ++n) {
                memory.budget = n;
                bool allocationFailed = false;
                lua_State* candidate = nullptr;
                try { candidate = retryScripts.CreateLuaThread("game-defines-allocation-probe"); }
                catch (const std::exception&) { allocationFailed = true; }
                memory.budget = -1;
                if (allocationFailed) {
                    ++createFailures;
                    CHECK(retryScripts.ThreadCount() == 0 && memory.bytes == 0 && memory.blocks == 0);
                    CHECK(database.StatementCount() == 0);
                    candidate = retryScripts.CreateLuaThread("game-defines-allocation-retry");
                    Execute(retryScripts, candidate,
                        "assert(GameDefines.POSTPROCESSED_ID==9090 and GameDefines.TEXT_NUMBER=='7')");
                    retryScripts.FreeLuaThread(candidate);
                    CHECK(retryScripts.ThreadCount() == 0 && memory.bytes == 0 && memory.blocks == 0);
                    CHECK(database.StatementCount() == 0);
                    CHECK(n < 1999);
                    continue;
                }
                CHECK(candidate != nullptr);
                Execute(retryScripts, candidate,
                    "assert(GameDefines.POSTPROCESSED_ID==9090 and GameDefines.TEXT_NUMBER=='7')");
                retryScripts.FreeLuaThread(candidate);
                CHECK(retryScripts.ThreadCount() == 0 && memory.bytes == 0 && memory.blocks == 0);
                CHECK(database.StatementCount() == 0);
                reachedSuccessfulBudget = true;
                break;
            }
            CHECK(createFailures > 0 && reachedSuccessfulBudget);
            CHECK(retryScripts.Close() && memory.bytes == 0 && memory.blocks == 0);
        }
        database.Close();
        CHECK(database.ErrorCode() == -1);
        std::printf("HOST_GAME_DEFINES_PASS checks=%u GAMECORE_LOADED=false create_failures=%u\n", checks, createFailures);
        return 0;
    } catch (const std::exception& error) {
        std::fprintf(stderr, "GAME_DEFINES_EXCEPTION %s\n", error.what());
        return 1;
    }
}
