#pragma once
#include <cstddef>
#include <stdexcept>

namespace ZeroSisGlobalsLifecycle {
// Every access requires the shared ZeroSisHostBinding::ProcessGate lease.
// This coordinates lifecycle mutations, not ordinary game calls/borrowers.
enum class Phase { Idle, Starting, Ready, Stopping, CleanupPending };

class Controller {
public:
    constexpr Controller() noexcept : phase_(Phase::Idle), owner_(nullptr), host_(nullptr), next_(0) {}
    Controller(const Controller&) = delete;
    Controller& operator=(const Controller&) = delete;

    Phase GetPhase() const noexcept { return phase_; }
    bool IsIdle() const noexcept { return phase_ == Phase::Idle; }
    void* Host() const noexcept { return host_; }
    std::size_t NextCleanupStep() const noexcept { return next_; }

    void EnterHost(void* host) {
        if (phase_ != Phase::Starting || host_ || !host)
            throw std::logic_error("Invalid GameCore host initialization boundary");
        // The matching cleanup is required even if InitGlobals throws part way.
        host_ = host;
    }

    template<class Start, class Cleanup>
    void Initialize(void* owner, Start start, Cleanup cleanup) {
        if (!owner || !IsIdle()) throw std::logic_error("GameCore is already active or requires cleanup");
        owner_ = owner;
        host_ = nullptr;
        next_ = 0;
        phase_ = Phase::Starting;
        try {
            start();
            phase_ = Phase::Ready;
        } catch (...) {
            // Preserve the initialization exception; pending cleanup is visible
            // in the state and blocks new initialization, rebinding and unload.
            try { Drain(cleanup); } catch (...) {}
            throw;
        }
    }

    template<class Cleanup>
    void Uninitialize(void* owner, Cleanup cleanup) {
        if (IsIdle()) return;
        if (owner_ != owner || (phase_ != Phase::Ready && phase_ != Phase::CleanupPending))
            throw std::logic_error("Invalid GameCore shutdown boundary");
        Drain(cleanup);
    }

    template<class Action>
    void CleanupStep(std::size_t index, Action action) {
        if (phase_ != Phase::Stopping || index > next_)
            throw std::logic_error("Invalid GameCore cleanup sequence");
        if (index < next_) return;
        action();
        ++next_; // A throwing step is retried; completed steps are not repeated.
    }

private:
    template<class Cleanup> void Drain(Cleanup cleanup) {
        phase_ = Phase::Stopping;
        try { cleanup(); }
        catch (...) { phase_ = Phase::CleanupPending; throw; }
        owner_ = nullptr;
        host_ = nullptr;
        next_ = 0;
        phase_ = Phase::Idle;
    }
    Phase phase_;
    void* owner_;
    void* host_;
    std::size_t next_;
};

inline Controller& ProcessState() { static Controller state; return state; }
}
