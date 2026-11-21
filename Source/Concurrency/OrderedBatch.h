#pragma once

#include <algorithm>
#include <atomic>
#include <cstddef>
#include <cstdint>
#include <exception>
#include <functional>
#include <memory>
#include <optional>
#include <stdexcept>
#include <thread>
#include <type_traits>
#include <utility>
#include <vector>

namespace zerosis::concurrency {

namespace detail {
struct CancellationState {
    std::atomic_bool requested{false};
    std::shared_ptr<const CancellationState> parent;
    explicit CancellationState(std::shared_ptr<const CancellationState> value = {}) : parent(std::move(value)) {}
};
} // namespace detail

class CancellationToken {
public:
    CancellationToken() = default;
    bool requested() const noexcept {
        for (auto state = signal_.get(); state != nullptr; state = state->parent.get())
            if (state->requested.load(std::memory_order_acquire)) return true;
        return false;
    }
private:
    friend class CancellationSource;
    explicit CancellationToken(std::shared_ptr<const detail::CancellationState> signal) : signal_(std::move(signal)) {}
    std::shared_ptr<const detail::CancellationState> signal_;
};

class CancellationSource {
public:
    explicit CancellationSource(CancellationToken parent = {})
        : signal_(std::make_shared<detail::CancellationState>(std::move(parent.signal_))) {}
    CancellationToken token() const { return CancellationToken(signal_); }
    void request() noexcept { signal_->requested.store(true, std::memory_order_release); }
private:
    std::shared_ptr<detail::CancellationState> signal_;
};

struct BatchStamp {
    std::uint64_t session;
    std::uint64_t revision;
    std::uint64_t batch;
    std::uint32_t turn;
    std::uint32_t phase;
};
inline bool operator==(const BatchStamp& a, const BatchStamp& b) noexcept {
    return a.session == b.session && a.revision == b.revision && a.batch == b.batch
        && a.turn == b.turn && a.phase == b.phase;
}

template<class Input> struct Job { std::uint64_t id; Input input; };
template<class Output> struct JobResult { std::uint64_t id; Output value; };
enum class BatchStatus { ready, cancelled, failed };

template<class Output> struct BatchResult {
    BatchStamp stamp;
    BatchStatus status = BatchStatus::failed;
    std::vector<JobResult<Output>> rows;
    std::exception_ptr error;
    std::size_t workers_started = 0;
    std::size_t jobs_started = 0;
    std::size_t jobs_completed = 0;
};

namespace detail {
struct ThreadGroup {
    std::vector<std::thread> threads;
    ~ThreadGroup() { join(); }
    void join() { for (auto& thread : threads) if (thread.joinable()) thread.join(); }
};
} // namespace detail

// A bounded synchronous batch, not a persistent pool or a game-state commit API.
// Input must own its values (no game/Lua/DB pointers). Each operation copy must be
// pure with respect to game state, and must finish or cooperate with cancellation.
// Invalid/setup inputs throw before launch. Worker/launch failure discards all rows.
// Completion order and scheduling metrics are deliberately not game-state inputs.
template<class Input, class Operation,
         class Output = std::invoke_result_t<Operation&, const Input&, const CancellationToken&>>
BatchResult<Output> evaluate_ordered(BatchStamp stamp, std::vector<Job<Input>> jobs,
                                    std::size_t worker_count, Operation operation,
                                    CancellationToken cancellation = {}) {
    static_assert(!std::is_reference_v<Output> && !std::is_void_v<Output>, "Return an owned value");
    static_assert(std::is_copy_constructible_v<Operation>, "One operation copy per worker is required");
    if (worker_count == 0 || worker_count > 64) throw std::invalid_argument("Worker count must be 1..64");
    std::sort(jobs.begin(), jobs.end(), [](const auto& a, const auto& b) { return a.id < b.id; });
    for (std::size_t i = 1; i < jobs.size(); ++i) {
        if (jobs[i - 1].id == jobs[i].id) throw std::invalid_argument("Duplicate job id");
    }
    BatchResult<Output> result{stamp};
    if (cancellation.requested()) { result.status = BatchStatus::cancelled; return result; }
    if (jobs.empty()) { result.status = BatchStatus::ready; return result; }
    worker_count = std::min(worker_count, jobs.size());
    std::vector<std::optional<Output>> slots(jobs.size());
    std::vector<std::exception_ptr> errors(jobs.size());
    std::vector<Operation> operations(worker_count, operation);
    std::atomic_size_t next{0}, started{0}, completed{0};
    CancellationSource batch_cancellation(cancellation);
    const auto worker_token = batch_cancellation.token();
    // Declared after everything referenced by threads; joins before those values die.
    detail::ThreadGroup group;
    group.threads.reserve(worker_count);
    const auto worker = [&](Operation& execute) {
        while (!worker_token.requested()) {
            const auto index = next.fetch_add(1, std::memory_order_relaxed);
            if (index >= jobs.size()) break;
            if (worker_token.requested()) break;
            started.fetch_add(1, std::memory_order_relaxed);
            try {
                slots[index].emplace(std::invoke(execute, std::as_const(jobs[index].input), worker_token));
                completed.fetch_add(1, std::memory_order_relaxed);
            } catch (...) {
                errors[index] = std::current_exception();
                batch_cancellation.request();
            }
        }
    };
    try {
        for (std::size_t index = 0; index < worker_count; ++index) {
            group.threads.emplace_back([&, index] { worker(operations[index]); });
        }
    } catch (...) {
        result.error = std::current_exception();
        batch_cancellation.request();
    }
    result.workers_started = group.threads.size();
    group.join();
    result.jobs_started = started.load(std::memory_order_relaxed);
    result.jobs_completed = completed.load(std::memory_order_relaxed);
    for (const auto& error : errors) {
        if (error && !result.error) result.error = error; // Lowest failed job ID among completed workers.
    }
    if (result.error) return result; // failed, no partial rows exposed
    if (cancellation.requested()) { result.status = BatchStatus::cancelled; return result; }
    result.rows.reserve(jobs.size());
    for (std::size_t index = 0; index < jobs.size(); ++index) {
        if (!slots[index]) throw std::logic_error("Missing completed job result");
        result.rows.push_back({jobs[index].id, std::move(*slots[index])});
    }
    result.status = BatchStatus::ready;
    return result;
}

} // namespace zerosis::concurrency
