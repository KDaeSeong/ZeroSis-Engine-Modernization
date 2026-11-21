// Template for the source-shaped LocalSdkSession boundary regression.
// The verifier replaces the two sentinels with exact bodies extracted from
// Source/Host/LocalSdkSession.h before compilation.
#include <cstdio>
#include <functional>
#include <memory>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

using PlayerTypes = int;
using MissionTypes = int;
enum { MAX_PLAYERS = 64 };

int g_currentThread = 1;
int g_playerCreated = 0, g_playerDestroyed = 0;
int g_unitCreated = 0, g_unitDestroyed = 0;
int g_missionCreated = 0, g_missionDestroyed = 0;
int g_gameReads = 0, g_contextReads = 0, g_selectionReads = 0;

unsigned long GetCurrentThreadId() { return static_cast<unsigned long>(g_currentThread); }

struct Lock {
    bool held = true;
    bool HeldByCurrentThread() const { return held; }
};

struct SelectionSnapshot {
    std::vector<std::pair<PlayerTypes, int>> values;
    int size() const { return static_cast<int>(values.size()); }
    const std::pair<PlayerTypes, int>& front() const { return values.front(); }
};

struct Selection {
    std::vector<std::pair<PlayerTypes, int>> rows;
    SelectionSnapshot Snapshot() const { ++g_selectionReads; return SelectionSnapshot{rows}; }
};

struct HostState {
    unsigned long gameThread = 1;
    Lock gameLock;
    Selection localSelection;
};

struct ICvMissionInfo1 {
    explicit ICvMissionInfo1(const char* sourceType) : value(sourceType) { ++g_missionCreated; }
    ~ICvMissionInfo1() { ++g_missionDestroyed; }
    const char* GetType() const { return value; }
    const char* value;
};

struct ICvUnit1 {
    ICvUnit1(int sourceOwner, int sourceID, bool isDelayed, bool isBusy)
        : owner(sourceOwner), id(sourceID), delayed(isDelayed), busy(isBusy) { ++g_unitCreated; }
    ~ICvUnit1() { ++g_unitDestroyed; }
    int GetOwner() const { return owner; }
    int GetID() const { return id; }
    bool IsDelayedDeathExported() const { return delayed; }
    bool IsBusy() const { return busy; }
    int owner, id;
    bool delayed, busy;
};

struct PlayerConfig {
    bool exists = true, human = true, alive = true, activeTurn = true;
    bool unitExists = true, delayed = false, busy = false;
    int unitOwner = 0, unitID = 17;
};

struct ICvPlayer1 {
    explicit ICvPlayer1(PlayerConfig& sourceConfig) : config(sourceConfig) { ++g_playerCreated; }
    ~ICvPlayer1() { ++g_playerDestroyed; }
    bool IsHuman() const { return config.human; }
    bool IsAlive() const { return config.alive; }
    bool IsTurnActive() const { return config.activeTurn; }
    ICvUnit1* GetUnit(int) { return config.unitExists ? new ICvUnit1(config.unitOwner, config.unitID,
                                                                       config.delayed, config.busy) : nullptr; }
    PlayerConfig& config;
};

struct ICvGame1 {
    bool multiplayer = false;
    int activePlayer = 0;
    PlayerConfig player;
    bool IsGameMultiPlayer() { ++g_gameReads; return multiplayer; }
    PlayerTypes GetActivePlayer() { ++g_gameReads; return activePlayer; }
    ICvPlayer1* GetPlayer(PlayerTypes owner) {
        ++g_gameReads;
        if (!player.exists || owner != activePlayer) return nullptr;
        return new ICvPlayer1(player);
    }
};

struct ICvGameContext3 {
    int missionID = 21;
    bool missionInfoExists = true;
    std::string missionType = "MISSION_FOUND";
    int GetInfoTypeForString(const char* name, bool) {
        ++g_contextReads;
        if (std::string(name) != "MISSION_FOUND") throw std::runtime_error("wrong mission lookup");
        return missionID;
    }
    ICvMissionInfo1* GetMissionInfo(MissionTypes) {
        ++g_contextReads;
        return missionInfoExists ? new ICvMissionInfo1(missionType.c_str()) : nullptr;
    }
};

struct ICvNetMessageHandler1 {
    int calls = 0;
    PlayerTypes owner = -1;
    int unitID = -1, mission = -1, data1 = 0, data2 = 0, flags = -1;
    bool shift = true;
    void ResponsePushMission(PlayerTypes p, int unit, MissionTypes m, int a, int b, int f, bool s) {
        ++calls; owner = p; unitID = unit; mission = m; data1 = a; data2 = b; flags = f; shift = s;
    }
};

class SessionFixture {
public:
    SessionFixture(HostState& host, ICvNetMessageHandler1& receiver, ICvGame1& game, ICvGameContext3& context)
        : host_(host) {
        // EXTRACTED_PUSH_MISSION_LAMBDA
    }
    void Push(int unitID, MissionTypes mission, int data1, int data2, int flags, bool shift) {
        pushMission_(unitID, mission, data1, data2, flags, shift);
    }
    // EXTRACTED_REQUIRE_COMMAND_OWNER
private:
    HostState& host_;
    std::function<void(int, MissionTypes, int, int, int, bool)> pushMission_;
};

namespace {
int checks = 0;
void Require(bool value, const char* message) {
    ++checks;
    if (!value) throw std::runtime_error(message);
}

struct Case {
    HostState host;
    ICvNetMessageHandler1 receiver;
    ICvGame1 game;
    ICvGameContext3 context;
    int targetUnit = 17, action = 21, argument1 = -1, argument2 = -1, missionFlags = 0;
    bool shift = false;
    Case() { host.localSelection.rows.push_back({0, 17}); game.player.unitOwner = 0; game.player.unitID = 17; }
    void Invoke() {
        SessionFixture session(host, receiver, game, context);
        session.Push(targetUnit, action, argument1, argument2, missionFlags, shift);
    }
    void Balanced() const {
        Require(g_playerCreated == g_playerDestroyed, "Player adapter lifetime leaked");
        Require(g_unitCreated == g_unitDestroyed, "Unit adapter lifetime leaked");
        Require(g_missionCreated == g_missionDestroyed, "Mission-info adapter lifetime leaked");
    }
};

void ResetCounters() {
    g_playerCreated = g_playerDestroyed = g_unitCreated = g_unitDestroyed = 0;
    g_missionCreated = g_missionDestroyed = g_gameReads = g_contextReads = g_selectionReads = 0;
    g_currentThread = 1;
}

template<class Mutate>
void Reject(Mutate mutate, const char* message) {
    ResetCounters();
    Case c; mutate(c);
    bool threw = false;
    try { c.Invoke(); } catch (const std::exception&) { threw = true; }
    Require(threw, message);
    Require(c.receiver.calls == 0, "Rejected founding input reached SDK receiver");
    c.Balanced();
}

void TestOwnerGuardPrecedesAllSDKReads() {
    ResetCounters();
    Case c; g_currentThread = 2;
    bool threw = false; try { c.Invoke(); } catch (const std::logic_error&) { threw = true; }
    Require(threw && c.receiver.calls == 0, "Wrong-thread command was accepted");
    Require(g_gameReads == 0 && g_contextReads == 0 && g_selectionReads == 0,
            "Wrong-thread guard ran after SDK or selection access");
    c.Balanced();

    ResetCounters();
    Case unlocked; unlocked.host.gameLock.held = false;
    threw = false; try { unlocked.Invoke(); } catch (const std::logic_error&) { threw = true; }
    Require(threw && unlocked.receiver.calls == 0, "Unlocked command was accepted");
    Require(g_gameReads == 0 && g_contextReads == 0 && g_selectionReads == 0,
            "Owner-lock guard ran after SDK or selection access");
    unlocked.Balanced();
}

void TestUnsupportedSessionAndMissionInputs() {
    Reject([](Case& c) { c.game.multiplayer = true; }, "Multiplayer founding mission accepted");
    Reject([](Case& c) { c.context.missionID = -1; }, "Missing MISSION_FOUND rules row accepted");
    Reject([](Case& c) { c.context.missionInfoExists = false; }, "Null MISSION_FOUND info accepted");
    Reject([](Case& c) { c.context.missionType = "MISSION_MOVE_TO"; }, "Mismatched mission rules type accepted");
    Reject([](Case& c) { c.context.missionID = 22; }, "Non-FOUND mission identity accepted");
    Reject([](Case& c) { c.targetUnit = -1; }, "Negative unit ID accepted");
    Reject([](Case& c) { c.argument1 = 0; }, "Found data1 override accepted");
    Reject([](Case& c) { c.argument2 = 0; }, "Found data2 override accepted");
    Reject([](Case& c) { c.missionFlags = 1; }, "Found flags override accepted");
    Reject([](Case& c) { c.shift = true; }, "Found shift override accepted");
}

void TestLivePlayerAndOwnedUnitGuards() {
    Reject([](Case& c) { c.game.activePlayer = -1; }, "Invalid active player accepted");
    Reject([](Case& c) { c.game.player.exists = false; }, "Missing active player accepted");
    Reject([](Case& c) { c.game.player.human = false; }, "Non-human active player accepted");
    Reject([](Case& c) { c.game.player.alive = false; }, "Dead active player accepted");
    Reject([](Case& c) { c.game.player.activeTurn = false; }, "Inactive turn accepted");
    Reject([](Case& c) { c.game.player.unitExists = false; }, "Missing target unit accepted");
    Reject([](Case& c) { c.game.player.unitID = 18; }, "Stale unit identity accepted");
    Reject([](Case& c) { c.game.player.unitOwner = 1; }, "Foreign unit accepted");
    Reject([](Case& c) { c.game.player.delayed = true; }, "Pending-death unit accepted");
    Reject([](Case& c) { c.game.player.busy = true; }, "Busy unit accepted");
}

void TestExactSelectedUnitAndSuccessfulTuple() {
    Reject([](Case& c) { c.host.localSelection.rows.clear(); }, "Empty selection accepted");
    Reject([](Case& c) { c.host.localSelection.rows.push_back({0, 18}); }, "Multiple selection accepted");
    Reject([](Case& c) { c.host.localSelection.rows[0] = {1, 17}; }, "Foreign selected owner accepted");
    Reject([](Case& c) { c.host.localSelection.rows[0] = {0, 18}; }, "Wrong selected unit accepted");

    ResetCounters();
    Case c; c.Invoke();
    Require(c.receiver.calls == 1, "Valid FOUND mission did not call the SDK receiver exactly once");
    Require(c.receiver.owner == 0 && c.receiver.unitID == 17 && c.receiver.mission == 21 &&
            c.receiver.data1 == -1 && c.receiver.data2 == -1 && c.receiver.flags == 0 && !c.receiver.shift,
            "Valid FOUND mission tuple changed in transport");
    c.Balanced();
}
}

int main() {
    try {
        TestOwnerGuardPrecedesAllSDKReads();
        TestUnsupportedSessionAndMissionInputs();
        TestLivePlayerAndOwnedUnitGuards();
        TestExactSelectedUnitAndSuccessfulTuple();
        std::printf("LOCAL_FOUND_SESSION_GUARDS_PASS checks=%d GAMECORE_LOADED=false SDK_LOADER_USED=false\n", checks);
        return 0;
    } catch (const std::exception& error) {
        std::fprintf(stderr, "LOCAL_FOUND_SESSION_GUARDS_FAIL checks=%d reason=%s\n", checks, error.what());
        return 1;
    }
}
