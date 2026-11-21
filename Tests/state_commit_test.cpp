#include "State/VersionedState.h"
#include "Numerics/CvCompatibleCrc32.h"
#include <chrono>
#include <condition_variable>
#include <fstream>
#include <iostream>
#include <mutex>
#include <string>

using namespace zerosis::concurrency;
using namespace zerosis::state;
using zerosis::numerics::CvCompatibleCrc32;
static_assert(sizeof(void*) == 8 && sizeof(std::size_t) == 8);
static std::size_t checks = 0;
static std::vector<std::string> case_names;
static void require(bool value, const char* message) {
    ++checks;
    if (!value) throw std::runtime_error(message);
}
template<class Function> static void test_case(const char* name, Function test) {
    test();
    case_names.emplace_back(name);
}

struct Entity { std::uint64_t id; std::uint32_t generation, owner; std::int64_t value; };
struct World { std::vector<Entity> entities; std::uint64_t applied_jobs = 0; };
struct Evaluation { Entity input; std::int64_t delta; };
using Owner = VersionedState<World>;

static World initial_world(std::uint32_t scenario = 0) {
    World world;
    for (std::uint32_t index = 0; index < 8; ++index)
        world.entities.push_back({UINT64_C(0x100000000) + index + 1, 1, index % 4,
                                  100000 + static_cast<std::int64_t>(scenario) * 101 + index * 17});
    return world;
}
static Owner::Request issue(Owner& owner, CancellationToken cancellation = {}) {
    std::vector<std::uint64_t> ids;
    for (const auto& entity : owner.snapshot()->entities) ids.push_back(entity.id);
    std::reverse(ids.begin(), ids.end());
    return owner.begin(std::move(ids), cancellation);
}
static Evaluation evaluate(const Entity& entity, const CancellationToken&) {
    const CvCompatibleCrc32 crc;
    auto state = crc.append_le32(static_cast<std::uint32_t>(entity.id));
    state = crc.append_le32(static_cast<std::uint32_t>(entity.id >> 32), state);
    state = crc.append_le32(entity.generation, state);
    state = crc.append_le32(entity.owner, state);
    const auto bits = static_cast<std::uint64_t>(entity.value);
    state = crc.append_le32(static_cast<std::uint32_t>(bits), state);
    state = crc.append_le32(static_cast<std::uint32_t>(bits >> 32), state);
    return {entity, static_cast<std::int64_t>(state % 19) - 9};
}
static BatchResult<Evaluation> calculate(const Owner::Request& request, std::size_t workers = 1) {
    std::vector<Job<Entity>> jobs;
    for (const auto& entity : request.snapshot()->entities) jobs.push_back({entity.id, entity});
    std::reverse(jobs.begin(), jobs.end());
    return evaluate_ordered(request.stamp(), std::move(jobs), workers, evaluate, request.cancellation());
}
static bool prepare(World& candidate, const std::vector<JobResult<Evaluation>>& rows) {
    if (rows.size() > (std::numeric_limits<std::uint64_t>::max)() - candidate.applied_jobs) return false;
    for (const auto& row : rows) {
        auto entity = std::find_if(candidate.entities.begin(), candidate.entities.end(),
            [&](const Entity& value) { return value.id == row.id; });
        const auto& output = row.value;
        if (entity == candidate.entities.end() || row.id != output.input.id
            || entity->generation != output.input.generation || entity->owner != output.input.owner
            || entity->value != output.input.value || output.delta < -9 || output.delta > 9) return false;
        if ((output.delta > 0 && entity->value > (std::numeric_limits<std::int64_t>::max)() - output.delta)
            || (output.delta < 0 && entity->value < (std::numeric_limits<std::int64_t>::min)() - output.delta)) return false;
        entity->value += output.delta;
    }
    candidate.applied_jobs += static_cast<std::uint64_t>(rows.size());
    return true;
}
static void unchanged(Owner& owner, const std::shared_ptr<const World>& state, StateEpoch epoch) {
    const auto current = owner.epoch();
    require(owner.snapshot() == state, "live snapshot changed on rejection");
    require(current.session == epoch.session && current.revision == epoch.revision
        && current.turn == epoch.turn && current.phase == epoch.phase, "epoch changed on rejection");
}

template<class Change> static void malformed(Change change) {
    Owner owner(initial_world());
    const auto request = issue(owner);
    auto result = calculate(request);
    const auto before = owner.snapshot();
    const auto epoch = owner.epoch();
    change(result);
    unsigned called = 0;
    auto outcome = owner.commit(request, result, [&](World&, const auto&) { ++called; return true; });
    require(outcome.code == CommitCode::malformed_result && called == 0, "malformed result reached prepare");
    require(request.phase() == RequestPhase::discarded, "malformed request not terminal");
    unchanged(owner, before, epoch);
}

struct ThrowingState {
    int value;
    static bool fail_copy, fail_move;
    explicit ThrowingState(int initial = 0) : value(initial) {}
    ThrowingState(const ThrowingState& other) : value(other.value) { if (fail_copy) throw std::bad_alloc(); }
    ThrowingState(ThrowingState&& other) : value(other.value) { if (fail_move) throw std::runtime_error("injected move failure"); }
};
bool ThrowingState::fail_copy = false;
bool ThrowingState::fail_move = false;

static void rejection_cases() {
    test_case("commit_once_shared_request_and_immutable_snapshot", [] {
        Owner owner(initial_world());
        const auto request = issue(owner);
        const auto duplicate = request;
        const auto old_snapshot = request.snapshot();
        const auto result = calculate(request, 4);
        unsigned calls = 0;
        auto apply = [&](World& state, const auto& rows) { ++calls; return prepare(state, rows); };
        require(owner.commit(request, result, apply).code == CommitCode::committed, "valid result rejected");
        require(owner.epoch().revision == 1 && owner.snapshot()->applied_jobs == 8, "commit metadata wrong");
        require(request.phase() == RequestPhase::committed && duplicate.phase() == RequestPhase::committed, "request copies diverged");
        const auto committed = owner.snapshot();
        require(owner.commit(duplicate, result, apply).code == CommitCode::already_finalized && calls == 1, "result applied twice");
        require(owner.snapshot() == committed && old_snapshot->applied_jobs == 0, "old snapshot mutated");
    });
    test_case("foreign_owner_cannot_consume_request", [] {
        Owner first(initial_world()), other(initial_world());
        const auto request = issue(first);
        const auto result = calculate(request);
        require(other.commit(request, result, prepare).code == CommitCode::foreign_request, "foreign request accepted");
        require(request.phase() == RequestPhase::pending, "foreign owner consumed request");
        require(first.commit(request, result, prepare).code == CommitCode::committed, "origin owner lost request");
    });
    test_case("destroyed_owner_identity_cannot_be_reused", [] {
        Owner::Request orphan;
        { Owner gone(initial_world()); orphan = issue(gone); }
        Owner replacement(initial_world());
        require(replacement.commit(orphan, calculate(orphan), prepare).code == CommitCode::foreign_request, "expired identity accepted");
        require(orphan.snapshot()->entities.size() == 8, "orphan snapshot lifetime lost");
    });
    test_case("competing_result_becomes_stale_after_commit", [] {
        Owner owner(initial_world());
        const auto first = issue(owner), second = issue(owner);
        auto a = calculate(first), b = calculate(second);
        require(owner.commit(first, a, prepare).code == CommitCode::committed, "first commit failed");
        const auto current = owner.snapshot(); const auto epoch = owner.epoch();
        require(owner.commit(second, b, prepare).code == CommitCode::stale, "old revision accepted");
        unchanged(owner, current, epoch);
    });
    test_case("new_session_rejects_old_work", [] {
        Owner owner(initial_world()); const auto request = issue(owner); const auto result = calculate(request);
        owner.new_session(initial_world());
        require(owner.epoch().session == 2 && owner.epoch().revision == 0, "session transition wrong");
        const auto current = owner.snapshot(); const auto epoch = owner.epoch();
        require(owner.commit(request, result, prepare).code == CommitCode::stale, "old session accepted");
        unchanged(owner, current, epoch);
        require(issue(owner).stamp().batch > request.stamp().batch, "batch identity reused after session reset");
    });
    test_case("turn_phase_and_direct_replacement_invalidate_work", [] {
        for (unsigned mode = 0; mode < 3; ++mode) {
            Owner owner(initial_world()); const auto request = issue(owner); const auto result = calculate(request);
            if (mode == 0) owner.set_context(1, 0);
            if (mode == 1) owner.set_context(0, 1);
            if (mode == 2) owner.replace(initial_world());
            require(owner.commit(request, result, prepare).code == CommitCode::stale, "context change accepted old result");
            require(owner.snapshot()->applied_jobs == 0, "stale work had effects");
        }
    });
    test_case("unchanged_context_is_idempotent", [] {
        Owner owner(initial_world()); auto request = issue(owner);
        require(!owner.set_context(0, 0) && owner.epoch().revision == 0, "same context advanced revision");
        require(owner.commit(request, calculate(request), prepare).code == CommitCode::committed, "same context invalidated work");
    });
    test_case("all_stamp_fields_are_bound", [] {
        for (unsigned field = 0; field < 5; ++field) malformed([&](auto& result) {
            switch (field) {
                case 0: ++result.stamp.session; break;
                case 1: ++result.stamp.revision; break;
                case 2: ++result.stamp.batch; break;
                case 3: ++result.stamp.turn; break;
                default: ++result.stamp.phase; break;
            }
        });
    });
    test_case("missing_extra_duplicate_unsorted_unknown_jobs_rejected", [] {
        malformed([](auto& result) { result.rows.pop_back(); });
        malformed([](auto& result) { result.rows.push_back(result.rows.back()); });
        malformed([](auto& result) { result.rows[1].id = result.rows[0].id; });
        malformed([](auto& result) { std::swap(result.rows[0], result.rows[1]); });
        malformed([](auto& result) { ++result.rows.back().id; });
        malformed([](auto& result) { result.error = std::make_exception_ptr(std::runtime_error("unexpected error")); });
    });
    test_case("failed_and_cancelled_worker_results_are_not_applied", [] {
        for (const auto status : {BatchStatus::failed, BatchStatus::cancelled}) {
            Owner owner(initial_world()); auto request = issue(owner); auto result = calculate(request);
            result.status = status;
            const auto before = owner.snapshot(); const auto epoch = owner.epoch();
            require(owner.commit(request, result, prepare).code == CommitCode::not_ready, "unsuccessful worker result applied");
            unchanged(owner, before, epoch);
        }
    });
    test_case("domain_generation_owner_base_and_delta_rejected_atomically", [] {
        for (unsigned field = 0; field < 5; ++field) {
            Owner owner(initial_world()); const auto request = issue(owner); auto result = calculate(request);
            // Later row: preparation has already changed earlier candidate values.
            auto& output = result.rows[4].value;
            if (field == 0) ++output.input.generation;
            if (field == 1) ++output.input.owner;
            if (field == 2) ++output.input.value;
            if (field == 3) ++output.input.id;
            if (field == 4) output.delta = 10;
            const auto before = owner.snapshot(); const auto epoch = owner.epoch();
            require(owner.commit(request, result, prepare).code == CommitCode::validation_failed, "invalid domain result applied");
            unchanged(owner, before, epoch);
        }
    });
    test_case("prepare_exception_rolls_back_and_request_is_terminal", [] {
        Owner owner(initial_world()); auto request = issue(owner); auto result = calculate(request);
        const auto before = owner.snapshot(); const auto epoch = owner.epoch();
        auto rejected = owner.commit(request, result, [](World& state, const auto&) -> bool {
            state.entities[0].value = -123; throw std::runtime_error("injected prepare failure");
        });
        require(rejected.code == CommitCode::preparation_failed && rejected.error, "preparation exception lost");
        unchanged(owner, before, epoch);
        require(owner.commit(request, result, prepare).code == CommitCode::already_finalized, "failed request replayed");
        auto fresh = issue(owner);
        require(owner.commit(fresh, calculate(fresh), prepare).code == CommitCode::committed, "failure poisoned owner");
    });
    test_case("candidate_copy_and_publish_move_failure_preserve_state", [] {
        for (unsigned mode = 0; mode < 2; ++mode) {
            VersionedState<ThrowingState> owner(ThrowingState{7});
            auto request = owner.begin({1});
            BatchResult<int> result{request.stamp()}; result.status = BatchStatus::ready; result.rows.push_back({1, 1});
            const auto before = owner.snapshot();
            ThrowingState::fail_copy = mode == 0; ThrowingState::fail_move = mode == 1;
            auto outcome = owner.commit(request, result, [](ThrowingState& state, const auto&) { state.value = 99; return true; });
            ThrowingState::fail_copy = false; ThrowingState::fail_move = false;
            require(outcome.code == CommitCode::preparation_failed && outcome.error, "candidate failure accepted");
            require(owner.snapshot() == before && before->value == 7 && owner.epoch().revision == 0, "candidate failure changed live state");
        }
    });
    test_case("cancel_before_and_during_prepare_discards_candidate", [] {
        for (unsigned mode = 0; mode < 2; ++mode) {
            Owner owner(initial_world()); CancellationSource cancel;
            const auto request = issue(owner, cancel.token()); const auto result = calculate(request);
            const auto before = owner.snapshot(); const auto epoch = owner.epoch();
            unsigned called = 0;
            if (mode == 0) cancel.request();
            auto outcome = owner.commit(request, result, [&](World& state, const auto& rows) {
                ++called; prepare(state, rows); cancel.request(); return true;
            });
            require(outcome.code == CommitCode::cancelled && called == mode, "cancel decision wrong");
            unchanged(owner, before, epoch);
        }
    });
    test_case("another_thread_can_cancel_while_candidate_is_prepared", [] {
        Owner owner(initial_world()); CancellationSource cancel;
        const auto request = issue(owner, cancel.token()); const auto result = calculate(request);
        const auto before = owner.snapshot(); const auto epoch = owner.epoch();
        std::mutex mutex; std::condition_variable cv; bool entered = false, delivered = false;
        std::thread canceller([&] {
            std::unique_lock<std::mutex> lock(mutex);
            if (cv.wait_for(lock, std::chrono::seconds(5), [&] { return entered; })) {
                cancel.request(); delivered = true; cv.notify_all();
            }
        });
        auto outcome = owner.commit(request, result, [&](World& state, const auto& rows) {
            prepare(state, rows);
            std::unique_lock<std::mutex> lock(mutex); entered = true; cv.notify_all();
            return cv.wait_for(lock, std::chrono::seconds(5), [&] { return delivered; });
        });
        canceller.join();
        require(delivered && outcome.code == CommitCode::cancelled, "concurrent cancellation not observed");
        unchanged(owner, before, epoch);
    });
    test_case("late_cancel_cannot_undo_published_state", [] {
        Owner owner(initial_world()); CancellationSource cancel; auto request = issue(owner, cancel.token());
        auto result = calculate(request);
        require(owner.commit(request, result, prepare).code == CommitCode::committed, "pre-cancel commit failed");
        const auto committed = owner.snapshot(); cancel.request();
        require(owner.commit(request, result, prepare).code == CommitCode::already_finalized
            && owner.snapshot() == committed, "late cancel replayed or undid commit");
    });
    test_case("wrong_thread_cannot_commit_or_mutate_owner", [] {
        Owner owner(initial_world()); auto request = issue(owner); auto result = calculate(request);
        CommitCode code = CommitCode::committed; bool mutation_rejected = false;
        std::thread foreign([&] {
            code = owner.commit(request, result, prepare).code;
            try { owner.set_context(7, 1); } catch (const std::logic_error&) { mutation_rejected = true; }
        });
        foreign.join();
        require(code == CommitCode::wrong_thread && mutation_rejected && request.phase() == RequestPhase::pending, "wrong thread changed owner");
        require(owner.commit(request, result, prepare).code == CommitCode::committed, "wrong-thread rejection consumed request");
    });
    test_case("reentrant_commit_and_owner_mutation_rejected", [] {
        Owner owner(initial_world()); auto request = issue(owner); auto result = calculate(request);
        CommitCode inner = CommitCode::committed; bool mutation_rejected = false;
        auto outcome = owner.commit(request, result, [&](World& state, const auto& rows) {
            inner = owner.commit(request, result, prepare).code;
            try { owner.new_session(initial_world()); } catch (const std::logic_error&) { mutation_rejected = true; }
            return prepare(state, rows);
        });
        require(outcome.code == CommitCode::committed && inner == CommitCode::busy && mutation_rejected, "reentrancy guard failed");
        require(owner.epoch().session == 1 && owner.epoch().revision == 1, "reentrant state change leaked");
    });
    test_case("revision_and_session_exhaustion_do_not_wrap", [] {
        const auto maximum = (std::numeric_limits<std::uint64_t>::max)();
        Owner revision(initial_world(), StateEpoch{1, maximum, 0, 0});
        auto request = issue(revision);
        require(revision.commit(request, calculate(request), prepare).code == CommitCode::revision_exhausted, "revision wrapped at commit");
        bool blocked = false;
        try { revision.replace(initial_world()); } catch (const std::overflow_error&) { blocked = true; }
        require(blocked && revision.epoch().revision == maximum, "revision wrapped at replacement");
        revision.new_session(initial_world());
        require(revision.epoch().session == 2 && revision.epoch().revision == 0, "new epoch after exhaustion failed");
        Owner session(initial_world(), StateEpoch{maximum, 0, 0, 0}); const auto before = session.snapshot();
        blocked = false;
        try { session.new_session(initial_world()); } catch (const std::overflow_error&) { blocked = true; }
        require(blocked && session.snapshot() == before && session.epoch().session == maximum, "session wrapped");
    });
    test_case("invalid_request_issuance_has_no_effect", [] {
        Owner owner(initial_world());
        for (auto ids : {std::vector<std::uint64_t>{}, std::vector<std::uint64_t>{1, 1}}) {
            bool blocked = false;
            try { owner.begin(std::move(ids)); } catch (const std::invalid_argument&) { blocked = true; }
            require(blocked, "invalid expected job list accepted");
        }
        require(issue(owner).stamp().batch == 1 && owner.epoch().revision == 0, "invalid issue consumed identity");
        const Owner::Request empty;
        BatchResult<Evaluation> result{};
        require(owner.commit(empty, result, prepare).code == CommitCode::foreign_request, "empty request accepted");
    });
    test_case("scheduling_statistics_do_not_affect_state_decisions", [] {
        Owner owner(initial_world()); auto request = issue(owner); auto result = calculate(request);
        result.jobs_started = 0; result.jobs_completed = 999; result.workers_started = 64;
        require(owner.commit(request, result, prepare).code == CommitCode::committed, "diagnostic metrics affected deterministic state");
    });
}

static void write_u32(std::ofstream& stream, std::uint32_t value) {
    for (unsigned byte = 0; byte < 4; ++byte) stream.put(static_cast<char>(value >> (byte * 8)));
}
static void write_u64(std::ofstream& stream, std::uint64_t value) {
    for (unsigned byte = 0; byte < 8; ++byte) stream.put(static_cast<char>(value >> (byte * 8)));
}
int main(int argc, char** argv) {
    if (argc != 2) return 2;
    try {
        rejection_cases();
        std::ofstream trace(argv[1], std::ios::binary | std::ios::trunc);
        if (!trace) throw std::runtime_error("Cannot create trace");
        std::uint64_t committed = 0, records = 0;
        for (std::uint32_t scenario = 0; scenario < 24; ++scenario) {
            for (std::uint32_t workers : {1U, 2U, 4U}) {
                Owner owner(initial_world(scenario));
                for (std::uint32_t step = 0; step < 32; ++step) {
                    if (step == 16) owner.new_session(*owner.snapshot(), step, step % 3);
                    owner.set_context(step, step % 3);
                    if (step != 0 && step % 7 == 0) {
                        auto replacement = *owner.snapshot();
                        auto& entity = replacement.entities[(step / 7) % replacement.entities.size()];
                        ++entity.generation; entity.owner = (entity.owner + 1) % 4;
                        owner.replace(std::move(replacement));
                    }
                    const auto request = issue(owner); const auto result = calculate(request, workers);
                    require(result.status == BatchStatus::ready, "integrated worker calculation failed");
                    require(owner.commit(request, result, prepare).code == CommitCode::committed, "integrated commit failed");
                    const auto current = owner.snapshot(); const auto epoch = owner.epoch();
                    require(owner.commit(request, result, prepare).code == CommitCode::already_finalized, "integrated duplicate applied");
                    require(owner.snapshot() == current, "duplicate changed published state");
                    require(current->applied_jobs == static_cast<std::uint64_t>(step + 1) * 8, "effect count wrong");
                    ++committed;
                    for (const auto& entity : current->entities) {
                        write_u32(trace, scenario); write_u32(trace, workers); write_u32(trace, step);
                        write_u64(trace, epoch.session); write_u64(trace, epoch.revision);
                        write_u64(trace, entity.id); write_u64(trace, static_cast<std::uint64_t>(entity.value));
                        write_u64(trace, current->applied_jobs);
                        ++records;
                    }
                }
            }
        }
        trace.close();
        if (!trace) throw std::runtime_error("Trace write failed");
        std::cout << "{\"status\":\"PASS\",\"scope\":\"ISOLATED_VALUE_STATE_NOT_GAMECORE\",\"case_names\":[";
        for (std::size_t index = 0; index < case_names.size(); ++index) {
            if (index) std::cout << ',';
            std::cout << '\"' << case_names[index] << '\"';
        }
        std::cout << "],\"checks_passed\":" << checks << ",\"committed_batches\":" << committed
            << ",\"state_records\":" << records << ",\"scenarios\":24,\"steps\":32,\"workers\":[1,2,4]}\n";
        return 0;
    } catch (const std::exception& error) {
        std::cerr << "FAIL: " << error.what() << '\n';
        return 1;
    }
}
