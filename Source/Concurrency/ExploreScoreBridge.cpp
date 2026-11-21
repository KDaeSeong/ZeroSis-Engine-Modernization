#include "ExploreScoreBridge.h"

#include "ExplorePlotScores.h"
#include "OrderedBatch.h"

#include <algorithm>
#include <array>
#include <chrono>
#include <cstdint>
#include <exception>
#include <memory>
#include <mutex>
#include <thread>
#include <vector>

namespace {
using namespace zerosis::concurrency;

struct InvocationState {
    std::mutex mutex;
    std::vector<std::thread::id> threads;
    std::uint32_t active_jobs = 0;
    std::uint32_t maximum_overlapping_jobs = 0;

    std::uint32_t Enter() {
        std::lock_guard<std::mutex> lock(mutex);
        const auto current = std::this_thread::get_id();
        const auto found = std::find(threads.begin(), threads.end(), current);
        std::uint32_t id = 0;
        if (found == threads.end()) {
            threads.push_back(current);
            id = static_cast<std::uint32_t>(threads.size());
        } else {
            id = static_cast<std::uint32_t>(std::distance(threads.begin(), found)) + 1;
        }
        ++active_jobs;
        maximum_overlapping_jobs = (std::max)(maximum_overlapping_jobs, active_jobs);
        return id;
    }

    void Leave() noexcept {
        std::lock_guard<std::mutex> lock(mutex);
        --active_jobs;
    }
};

struct WorkerScore {
    std::int32_t score;
    std::uint32_t worker_id;
};

class ExploreScoreOperation {
public:
    explicit ExploreScoreOperation(std::shared_ptr<InvocationState> state) : state_(std::move(state)) {}

    WorkerScore operator()(const ExplorePlotScoreInput& input, const CancellationToken&) const {
        const auto id = state_->Enter();
        struct LeaveOnExit {
            InvocationState& state;
            ~LeaveOnExit() { state.Leave(); }
        } leave{*state_};
        return {score_explore_plot(input), id};
    }

private:
    std::shared_ptr<InvocationState> state_;
};

bool CopyInput(const ZeroSisExploreScoreInput& source, ExplorePlotScoreInput& target) noexcept {
    if (source.domain > 2) return false;
    // Civ V maps are far smaller; this bound rejects malformed ABI values and
    // keeps all nine distance-adjusted score terms comfortably inside int32.
    const auto valid_distance = [](std::int32_t distance) noexcept {
        return distance >= 0 && distance <= 1000000;
    };
    target.domain = source.domain == 0 ? ExploreDomain::land
                  : source.domain == 1 ? ExploreDomain::sea : ExploreDomain::unsupported;
    for (std::size_t i = 0; i < target.plots.size(); ++i) {
        const auto& from = source.plots[i];
        auto& to = target.plots[i];
        const auto expected = kExplorePlotOffsetOrder[i];
        if (from.offset_x != expected[0] || from.offset_y != expected[1] ||
            !valid_distance(from.distance_from_origin)) return false;
        to.offset_x = from.offset_x;
        to.offset_y = from.offset_y;
        to.exists = from.exists != 0;
        to.is_center_plot = from.is_center_plot != 0;
        to.revealed = from.revealed != 0;
        to.adjacent_revealed = from.adjacent_revealed != 0;
        to.distance_from_origin = from.distance_from_origin;
        to.origin_can_see_candidate = from.origin_can_see_candidate != 0;
        to.water = from.water != 0;
        to.mountain = from.mountain != 0;
        to.hills = from.hills != 0;
        to.has_feature = from.has_feature != 0;
        to.feature_impassable = from.feature_impassable != 0;
        to.feature_see_through_change_positive = from.feature_see_through_change_positive != 0;
        for (std::size_t neighbor = 0; neighbor < to.adjacent_plots.size(); ++neighbor) {
            if (!valid_distance(from.adjacent_plots[neighbor].distance_from_origin)) return false;
            to.adjacent_plots[neighbor] = {
                from.adjacent_plots[neighbor].exists != 0,
                from.adjacent_plots[neighbor].revealed != 0,
                from.adjacent_plots[neighbor].distance_from_origin,
            };
        }
    }
    return true;
}
} // namespace

extern "C" int32_t ZeroSisEvaluateExploreScores(const ZeroSisExploreScoreInput* inputs,
                                                 const std::uint32_t count,
                                                 const std::uint32_t worker_count,
                                                 std::int32_t* scores,
                                                 ZeroSisExploreBatchMetrics* metrics) {
    if (metrics == nullptr) return 1;
    *metrics = {};
    if ((count != 0 && (inputs == nullptr || scores == nullptr)) ||
        (worker_count != 1 && worker_count != 2 && worker_count != 4)) return 1;

    const auto started = std::chrono::steady_clock::now();
    try {
        std::vector<Job<ExplorePlotScoreInput>> jobs;
        jobs.reserve(count);
        for (std::uint32_t index = 0; index < count; ++index) {
            ExplorePlotScoreInput input;
            if (!CopyInput(inputs[index], input)) return 1;
            jobs.push_back({index, std::move(input)});
        }

        auto invocation = std::make_shared<InvocationState>();
        const BatchStamp stamp{0, 0, 0, 0, 0};
        const auto result = evaluate_ordered(stamp, std::move(jobs), worker_count,
                                             ExploreScoreOperation(invocation));
        if (result.status != BatchStatus::ready || result.rows.size() != count) return 2;
        for (std::uint32_t index = 0; index < count; ++index) {
            if (result.rows[index].id != index) return 2;
            if (result.rows[index].value.worker_id == 0 || result.rows[index].value.worker_id > 64) return 2;
        }
        metrics->workers_started = static_cast<std::uint32_t>(result.workers_started);
        metrics->jobs_started = static_cast<std::uint32_t>(result.jobs_started);
        metrics->jobs_completed = static_cast<std::uint32_t>(result.jobs_completed);
        {
            std::lock_guard<std::mutex> lock(invocation->mutex);
            metrics->worker_threads_used = static_cast<std::uint32_t>(invocation->threads.size());
            metrics->maximum_overlapping_jobs = invocation->maximum_overlapping_jobs;
            for (std::uint32_t i = 0; i < metrics->worker_threads_used; ++i)
                metrics->worker_ids[i] = i + 1;
        }
        metrics->worker_batch_us = static_cast<std::uint64_t>(
            std::chrono::duration_cast<std::chrono::microseconds>(
                std::chrono::steady_clock::now() - started).count());
        for (std::uint32_t index = 0; index < count; ++index)
            scores[index] = result.rows[index].value.score;
        return 0;
    } catch (...) {
        metrics->worker_batch_us = static_cast<std::uint64_t>(
            std::chrono::duration_cast<std::chrono::microseconds>(
                std::chrono::steady_clock::now() - started).count());
        return 2;
    }
}
