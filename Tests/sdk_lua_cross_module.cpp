#include "lua.hpp"

#include <windows.h>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>

typedef int (__cdecl *PushEmptyTableFn)(lua_State*);
typedef int (__cdecl *CollectFn)(lua_State*, int);

static void Fail(const char* message, unsigned long code = 1) {
    std::fprintf(stderr, "LUA_CROSS_MODULE_FAILED %s code=0x%08lX\n", message, code);
    std::exit(1);
}

static std::string Quote(const char* value) {
    std::string result("\"");
    for (const char* p = value; *p; ++p) {
        if (*p == '\"') result += '\\';
        result += *p;
    }
    result += '\"';
    return result;
}

static int Child(const char* dllPath, const char* direction) {
    const int rounds = 32;
    HMODULE fixture = LoadLibraryA(dllPath);
    if (!fixture) Fail("LoadLibrary", GetLastError());
    PushEmptyTableFn pushEmpty = reinterpret_cast<PushEmptyTableFn>(GetProcAddress(fixture, "FixturePushEmptyTable"));
    CollectFn collect = reinterpret_cast<CollectFn>(GetProcAddress(fixture, "FixtureCollect"));
    if (!pushEmpty || !collect) Fail("GetProcAddress", GetLastError());

    lua_State* state = luaL_newstate();
    if (!state) Fail("luaL_newstate");
    luaL_openlibs(state);
    if (lua_gettop(state) != 0) Fail("initial Lua stack not empty");

    // Exercise ordinary public Lua calls across the module boundary before GC.
    lua_pushinteger(state, 0x531A);
    const int tokenOk = collect(state, 0);
    if (tokenOk != 1 || lua_tointeger(state, -1) != 0x531A)
        Fail("DLL could not read the shared VM stack");
    lua_pop(state, 1);

    if (std::strcmp(direction, "host-to-dll") == 0) {
        // EXE implementation allocates the empty table; DLL implementation's
        // collector must reclaim it after it becomes unreachable.
        for (int i = 0; i < rounds; ++i) {
            lua_createtable(state, 0, 0);
            lua_pop(state, 1);
            if (collect(state, 2) != 0) Fail("host-to-dll stack imbalance");
        }
    } else if (std::strcmp(direction, "dll-to-host") == 0) {
        // DLL implementation allocates the empty table; EXE implementation's
        // collector must reclaim it after the host drops the only reference.
        for (int i = 0; i < rounds; ++i) {
            if (pushEmpty(state) != 1 || lua_gettop(state) != 1 || !lua_istable(state, -1))
                Fail("FixturePushEmptyTable ABI or stack contract failed");
            lua_pop(state, 1);
            lua_gc(state, LUA_GCCOLLECT, 0);
            lua_gc(state, LUA_GCCOLLECT, 0);
            if (lua_gettop(state) != 0) Fail("dll-to-host stack imbalance");
        }
    } else {
        Fail("unknown child scenario");
    }

    lua_close(state);
    // Keep the provider DLL loaded until after the VM has been destroyed.
    FreeLibrary(fixture);
    std::puts("LUA_CROSS_MODULE_CHILD_PASS");
    return 0;
}

static bool RunChild(const char* executable, const char* dllPath, const char* direction,
                     unsigned long* exitCode) {
    std::string command = Quote(executable) + " --child " + Quote(dllPath) + " " + direction;
    STARTUPINFOA startup = {};
    startup.cb = sizeof(startup);
    PROCESS_INFORMATION process = {};
    if (!CreateProcessA(nullptr, &command[0], nullptr, nullptr, FALSE, CREATE_NO_WINDOW,
                        nullptr, nullptr, &startup, &process))
        return false;
    CloseHandle(process.hThread);
    const DWORD wait = WaitForSingleObject(process.hProcess, 30000);
    if (wait != WAIT_OBJECT_0) {
        TerminateProcess(process.hProcess, 0xE0000001UL);
        WaitForSingleObject(process.hProcess, INFINITE);
        *exitCode = 0xE0000001UL;
        CloseHandle(process.hProcess);
        return true;
    }
    const BOOL gotCode = GetExitCodeProcess(process.hProcess, exitCode);
    CloseHandle(process.hProcess);
    return gotCode != FALSE;
}

int main(int argc, char** argv) {
    SetErrorMode(SEM_FAILCRITICALERRORS|SEM_NOGPFAULTERRORBOX|SEM_NOOPENFILEERRORBOX);
    _set_abort_behavior(0,_WRITE_ABORT_MSG|_CALL_REPORTFAULT);
    if (argc == 4 && std::strcmp(argv[1], "--child") == 0)
        return Child(argv[2], argv[3]);
    if (argc != 2) {
        std::fprintf(stderr, "usage: sdk_lua_cross_module.exe <fixture-dll-path>\n");
        return 2;
    }

    char executable[MAX_PATH + 1] = {};
    const DWORD length = GetModuleFileNameA(nullptr, executable, MAX_PATH);
    if (length == 0 || length >= MAX_PATH) Fail("GetModuleFileName", GetLastError());

    unsigned long hostToDll = 0, dllToHost = 0;
    if (!RunChild(executable, argv[1], "host-to-dll", &hostToDll)) Fail("spawn host-to-dll child", GetLastError());
    if (!RunChild(executable, argv[1], "dll-to-host", &dllToHost)) Fail("spawn dll-to-host child", GetLastError());

    std::printf("LUA_CROSS_MODULE_RESULT fixture=%s export=FixturePushEmptyTable,FixtureCollect ", argv[1]);
    std::printf("rounds=32 host_to_dll=0x%08lX dll_to_host=0x%08lX GAMECORE_LOADED=false\n", hostToDll, dllToHost);
    // This is an evidence harness: a nonzero child result is recorded rather
    // than treated as a harness error, since static-link builds are expected to
    // reproduce the cross-module sentinel fault.
    return 0;
}
