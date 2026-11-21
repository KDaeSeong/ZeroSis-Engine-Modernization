#pragma once

#include "Concurrency/OrderedBatch.h"
#include <limits>

namespace zerosis::state {

using concurrency::BatchResult;
using concurrency::BatchStamp;
using concurrency::BatchStatus;
using concurrency::CancellationToken;

struct StateEpoch {
    std::uint64_t session = 1;
    std::uint64_t revision = 0;
    std::uint32_t turn = 0;
    std::uint32_t phase = 0;
};

enum class RequestPhase { pending, preparing, committed, discarded };
enum class CommitCode {
    committed, already_finalized, foreign_request, wrong_thread, busy,
    stale, cancelled, not_ready, malformed_result, validation_failed,
    preparation_failed, revision_exhausted
};
struct CommitReport {
    CommitCode code;
    std::exception_ptr error;
};

// Only for deeply owned value state. The constructor, prepare function and state
// copies must not mutate external state. Not an adapter for in-place CvCity/CvUnit.
// All owner access is confined to its creating thread; requests are immutable
// snapshots except for an atomic, observable terminal phase. No persistence ABI.
template<class State> class VersionedState final {
    static_assert(std::is_copy_constructible_v<State>, "State must support independent value copies");
    static_assert(std::is_nothrow_destructible_v<State>, "State destruction must not throw");
    struct Identity {};
    struct Control {
        std::weak_ptr<const Identity> owner;
        BatchStamp stamp;
        std::shared_ptr<const State> snapshot;
        std::vector<std::uint64_t> jobs;
        CancellationToken cancellation;
        std::atomic<RequestPhase> phase{RequestPhase::pending};
        Control(const std::shared_ptr<const Identity>& identity, BatchStamp value,
                std::shared_ptr<const State> state, std::vector<std::uint64_t> ids, CancellationToken token)
            : owner(identity), stamp(value), snapshot(std::move(state)), jobs(std::move(ids)), cancellation(std::move(token)) {}
    };

public:
    class Request {
    public:
        Request() = default;
        BatchStamp stamp() const { return control().stamp; }
        std::shared_ptr<const State> snapshot() const { return control().snapshot; }
        const std::vector<std::uint64_t>& job_ids() const { return control().jobs; }
        CancellationToken cancellation() const { return control().cancellation; }
        RequestPhase phase() const { return control().phase.load(std::memory_order_acquire); }
        explicit operator bool() const noexcept { return static_cast<bool>(control_); }
    private:
        friend class VersionedState;
        explicit Request(std::shared_ptr<Control> value) : control_(std::move(value)) {}
        const Control& control() const {
            if (!control_) throw std::logic_error("Empty state request");
            return *control_;
        }
        std::shared_ptr<Control> control_;
    };

    explicit VersionedState(State initial, StateEpoch epoch = {})
        : owner_thread_(std::this_thread::get_id()), identity_(std::make_shared<const Identity>()),
          live_(std::make_shared<const State>(std::move(initial))), epoch_(epoch) {
        if (epoch_.session == 0) throw std::invalid_argument("Session generation zero is reserved");
    }
    VersionedState(const VersionedState&) = delete;
    VersionedState& operator=(const VersionedState&) = delete;
    VersionedState(VersionedState&&) = delete;
    VersionedState& operator=(VersionedState&&) = delete;

    std::shared_ptr<const State> snapshot() const { require_owner(); return live_; }
    StateEpoch epoch() const { require_owner(); return epoch_; }

    Request begin(std::vector<std::uint64_t> job_ids, CancellationToken cancellation = {}) {
        require_mutation();
        if (job_ids.empty()) throw std::invalid_argument("A state request requires jobs");
        std::sort(job_ids.begin(), job_ids.end());
        if (std::adjacent_find(job_ids.begin(), job_ids.end()) != job_ids.end())
            throw std::invalid_argument("Duplicate expected job id");
        if (batch_counter_ == maximum) throw std::overflow_error("Batch identity exhausted");
        const BatchStamp stamp{epoch_.session, epoch_.revision, batch_counter_ + 1, epoch_.turn, epoch_.phase};
        auto request = std::make_shared<Control>(identity_, stamp, live_, std::move(job_ids), std::move(cancellation));
        ++batch_counter_; // Allocation failed -> neither identity nor state was advanced.
        return Request(std::move(request));
    }

    // Returns false for an unchanged context. A real change invalidates old work.
    bool set_context(std::uint32_t turn, std::uint32_t phase) {
        require_mutation();
        if (epoch_.turn == turn && epoch_.phase == phase) return false;
        require_revision_space();
        epoch_.turn = turn;
        epoch_.phase = phase;
        ++epoch_.revision;
        return true;
    }

    void replace(State replacement) {
        require_mutation();
        require_revision_space();
        BusyScope scope(busy_);
        auto next = std::make_shared<const State>(std::move(replacement));
        live_.swap(next);
        ++epoch_.revision;
    }

    void new_session(State replacement, std::uint32_t turn = 0, std::uint32_t phase = 0) {
        require_mutation();
        if (epoch_.session == maximum) throw std::overflow_error("Session generation exhausted");
        BusyScope scope(busy_);
        auto next = std::make_shared<const State>(std::move(replacement));
        live_.swap(next);
        epoch_ = StateEpoch{epoch_.session + 1, 0, turn, phase};
        // The batch counter is never reset, including across session changes.
    }

    // Prepare edits an independent candidate and returns bool. All expected IDs
    // are checked here; domain rules/entity generations remain prepare's contract.
    // By-value results support an explicit owned handoff. They must not hold
    // shared mutable payloads. Rejected requests are terminal; retry by reissuing.
    template<class Output, class Prepare>
    CommitReport commit(const Request& request, BatchResult<Output> result, Prepare prepare) {
        static_assert(std::is_same_v<std::invoke_result_t<Prepare&, State&, const std::vector<concurrency::JobResult<Output>>&>, bool>,
                      "Prepare must return bool and edit only its candidate");
        if (std::this_thread::get_id() != owner_thread_) return {CommitCode::wrong_thread, {}};
        if (busy_) return {CommitCode::busy, {}};
        auto control = request.control_;
        if (!control || control->owner.lock() != identity_) return {CommitCode::foreign_request, {}};
        if (control->phase.load(std::memory_order_acquire) != RequestPhase::pending)
            return {CommitCode::already_finalized, {}};
        const auto reject = [&](CommitCode code, std::exception_ptr error = {}) {
            control->phase.store(RequestPhase::discarded, std::memory_order_release);
            return CommitReport{code, std::move(error)};
        };
        const auto& issued = control->stamp;
        if (issued.session != epoch_.session || issued.revision != epoch_.revision || issued.turn != epoch_.turn
            || issued.phase != epoch_.phase || control->snapshot != live_) return reject(CommitCode::stale);
        if (control->cancellation.requested()) return reject(CommitCode::cancelled);
        if (!(result.stamp == issued)) return reject(CommitCode::malformed_result);
        if (result.status != BatchStatus::ready) return reject(CommitCode::not_ready);
        if (result.error || result.rows.size() != control->jobs.size()) return reject(CommitCode::malformed_result);
        for (std::size_t i = 0; i < result.rows.size(); ++i)
            if (result.rows[i].id != control->jobs[i]) return reject(CommitCode::malformed_result);
        if (epoch_.revision == maximum) return reject(CommitCode::revision_exhausted);
        BusyScope scope(busy_);
        control->phase.store(RequestPhase::preparing, std::memory_order_release);
        try {
            State candidate = *live_;
            if (!std::invoke(prepare, candidate, std::as_const(result.rows))) return reject(CommitCode::validation_failed);
            auto next = std::make_shared<const State>(std::move(candidate));
            // Linearization decision: cancellation observed here aborts. A later
            // cancellation cannot roll back a state already published below.
            if (control->cancellation.requested()) return reject(CommitCode::cancelled);
            live_.swap(next); // noexcept, then only nonthrowing metadata updates
            ++epoch_.revision;
            control->phase.store(RequestPhase::committed, std::memory_order_release);
            return {CommitCode::committed, {}};
        } catch (...) {
            return reject(CommitCode::preparation_failed, std::current_exception());
        }
    }

private:
    struct BusyScope {
        bool& flag;
        explicit BusyScope(bool& value) : flag(value) { flag = true; }
        ~BusyScope() { flag = false; }
        BusyScope(const BusyScope&) = delete;
        BusyScope& operator=(const BusyScope&) = delete;
    };
    static constexpr std::uint64_t maximum = (std::numeric_limits<std::uint64_t>::max)();
    void require_owner() const {
        if (std::this_thread::get_id() != owner_thread_) throw std::logic_error("State belongs to another thread");
    }
    void require_mutation() const {
        require_owner();
        if (busy_) throw std::logic_error("Reentrant state mutation");
    }
    void require_revision_space() const {
        if (epoch_.revision == maximum) throw std::overflow_error("State revision exhausted");
    }
    const std::thread::id owner_thread_;
    const std::shared_ptr<const Identity> identity_;
    std::shared_ptr<const State> live_;
    StateEpoch epoch_;
    std::uint64_t batch_counter_ = 0;
    bool busy_ = false;
};

} // namespace zerosis::state
