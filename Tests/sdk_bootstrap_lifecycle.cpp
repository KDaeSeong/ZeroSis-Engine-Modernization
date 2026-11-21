#include "ZeroSisBootstrap.h"
#include <atomic>
#include <cstdio>
#include <cstdlib>
#include <stdexcept>
#include <thread>
#include <vector>

namespace {
std::atomic<unsigned> checks{0};
void Check(bool condition, unsigned line) {
    ++checks;
    if (!condition) { std::printf("FAIL|%u|%lu\n", line, GetLastError()); std::fflush(stdout); std::exit(2); }
}
#define CHECK(c) Check(!!(c), __LINE__)
using ZeroSisBootstrap::Phase;
HMODULE Module() { return GetModuleHandleW(nullptr); }
enum class Fault { None, Timer, Symbols, SymbolsThrow, ContextNull, ContextOOM, ContextException, ContextCleanup, SymbolsCleanup, TimerCleanup };

class Host final : public ZeroSisBootstrap::Backend {
public:
    Fault fault = Fault::None, secondFault = Fault::None;
    bool timer = false, symbols = false;
    unsigned contextObjects = 0, starts = 0, creations = 0, destructions = 0, requests = 0, releases = 0;
    int value = 1729;
    ZeroSisBootstrap::Lifecycle* recursive = nullptr;
    bool Take(Fault valueToTake) noexcept {
        if (fault != valueToTake) return false;
        fault = secondFault; secondFault = Fault::None;
        SetLastError(ERROR_SUCCESS);
        return true;
    }
    bool BeginTimer() noexcept override {
        ++requests;
        CHECK(!timer && !symbols && !contextObjects);
        if (Take(Fault::Timer)) return false;
        timer = true;
        return true;
    }
    bool EndTimer() noexcept override {
        CHECK(timer && !symbols && !contextObjects);
        if (Take(Fault::TimerCleanup)) return false;
        timer = false; ++releases;
        return true;
    }
    bool BeginSymbols(HMODULE module) override {
        CHECK(module == Module() && timer && !symbols && !contextObjects);
        symbols = true; ++starts;
        if (Take(Fault::Symbols)) return false;
        if (Take(Fault::SymbolsThrow)) throw std::bad_alloc();
        if (recursive) {
            CHECK(recursive->Start(*this, module) == nullptr);
            CHECK(recursive->LastError() == ERROR_BUSY && recursive->State() == Phase::Starting);
            CHECK(!recursive->Shutdown());
        }
        return true;
    }
    bool EndSymbols() noexcept override {
        CHECK(symbols && timer && !contextObjects);
        if (Take(Fault::SymbolsCleanup)) return false;
        symbols = false;
        return true;
    }
    void* CreateContext() override {
        CHECK(timer && symbols && !contextObjects);
        ++creations; contextObjects = 2;
        if (Take(Fault::ContextNull)) return nullptr;
        if (Take(Fault::ContextOOM)) throw std::bad_alloc();
        if (Take(Fault::ContextException)) throw std::runtime_error("injected context failure");
        contextObjects = 4;
        std::this_thread::yield();
        return &value;
    }
    bool DestroyContext() noexcept override {
        CHECK(timer && symbols && contextObjects);
        if (Take(Fault::ContextCleanup)) return false;
        if (recursive) {
            CHECK(!recursive->Shutdown());
            CHECK(recursive->State() == Phase::Stopping);
        }
        contextObjects = 0; ++destructions;
        return true;
    }
    bool Empty() const { return !timer && !symbols && !contextObjects; }
};

void ConcurrentAndRepeated() {
    ZeroSisBootstrap::Lifecycle lifecycle;
    Host host;
    CHECK(lifecycle.Shutdown());
    CHECK(lifecycle.Start(host, nullptr) == nullptr && host.requests == 0);
    std::vector<std::thread> workers;
    for (unsigned i = 0; i < 8; ++i) workers.emplace_back([&] {
        for (unsigned j = 0; j < 32; ++j) CHECK(lifecycle.Start(host, Module()) == &host.value);
    });
    for (auto& worker : workers) worker.join();
    CHECK(host.requests == 1 && host.starts == 1 && host.creations == 1);
    CHECK(lifecycle.State() == Phase::Ready && lifecycle.LastError() == ERROR_SUCCESS);
    Host another;
    CHECK(lifecycle.Start(another, Module()) == nullptr && another.Empty());
    CHECK(lifecycle.Shutdown());
    CHECK(lifecycle.Shutdown());
    CHECK(host.Empty() && host.destructions == 1 && host.releases == 1);
    CHECK(lifecycle.Start(another, Module()) == &another.value);
    CHECK(lifecycle.Shutdown() && another.Empty());
    std::printf("CONCURRENCY|8|256_start_calls|one_context\n");
}

void FailureRecovery() {
    unsigned cases = 0;
    for (Fault fault : {Fault::Timer, Fault::Symbols, Fault::SymbolsThrow, Fault::ContextNull, Fault::ContextOOM, Fault::ContextException}) {
        ZeroSisBootstrap::Lifecycle lifecycle;
        Host host; host.fault = fault;
        CHECK(lifecycle.Start(host, Module()) == nullptr);
        CHECK(lifecycle.LastError() != ERROR_SUCCESS);
        CHECK(lifecycle.State() == Phase::Empty && host.Empty());
        CHECK(lifecycle.Start(host, Module()) == &host.value);
        CHECK(lifecycle.Shutdown() && host.Empty());
        ++cases;
    }
    for (Fault fault : {Fault::ContextCleanup, Fault::SymbolsCleanup, Fault::TimerCleanup}) {
        ZeroSisBootstrap::Lifecycle lifecycle;
        Host host;
        CHECK(lifecycle.Start(host, Module()) == &host.value);
        host.fault = fault;
        CHECK(!lifecycle.Shutdown() && lifecycle.LastError() != ERROR_SUCCESS);
        CHECK(lifecycle.State() == Phase::CleanupRequired && !host.Empty());
        CHECK(lifecycle.Start(host, Module()) == nullptr && !host.Empty());
        CHECK(lifecycle.Shutdown() && host.Empty());
        CHECK(lifecycle.Start(host, Module()) == &host.value);
        CHECK(lifecycle.Shutdown() && host.Empty());
        ++cases;
    }
    for (Fault cleanup : {Fault::ContextCleanup, Fault::SymbolsCleanup, Fault::TimerCleanup}) {
        ZeroSisBootstrap::Lifecycle lifecycle;
        Host host; host.fault = Fault::ContextOOM; host.secondFault = cleanup;
        CHECK(lifecycle.Start(host, Module()) == nullptr);
        CHECK(lifecycle.LastError() == ERROR_NOT_ENOUGH_MEMORY);
        CHECK(lifecycle.State() == Phase::CleanupRequired && !host.Empty());
        CHECK(lifecycle.Shutdown() && host.Empty());
        CHECK(lifecycle.Start(host, Module()) == &host.value);
        CHECK(lifecycle.Shutdown() && host.Empty());
        ++cases;
    }
    ZeroSisBootstrap::Lifecycle lifecycle;
    Host recursive; recursive.recursive = &lifecycle;
    CHECK(lifecycle.Start(recursive, Module()) == &recursive.value);
    CHECK(lifecycle.Shutdown() && recursive.Empty());
    std::printf("FAILURES|%u|reverse_cleanup|retained_ownership|explicit_retry\n", cases);
    std::printf("REENTRANCY|startup_and_shutdown_rejected_without_deadlock\n");
}
}

int main() {
    ConcurrentAndRepeated(); FailureRecovery();
    std::printf("PASS|%u\n", checks.load());
    return 0;
}
