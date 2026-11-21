#include "Concurrency/OrderedBatch.h"
#include "Numerics/CvCompatibleCrc32.h"
#include <array>
#include <chrono>
#include <condition_variable>
#include <cstdio>
#include <iostream>
#include <mutex>
#include <set>
#include <string>

using namespace zerosis::concurrency;
using zerosis::numerics::CvCompatibleCrc32;
static_assert(sizeof(void*) == 8 && sizeof(std::size_t) == 8);

static unsigned checks = 0;
static void require(bool condition, const char* label) {
    ++checks;
    if (!condition) throw std::runtime_error(label);
}
struct Payload { std::uint32_t index, seed; std::vector<unsigned char> bytes; };
static std::vector<Job<Payload>> make_jobs(std::uint32_t batch, std::size_t count = 64) {
    std::vector<Job<Payload>> jobs;
    for (std::size_t i = 0; i < count; ++i) {
        const auto index = static_cast<std::uint32_t>(i);
        Payload input{index, UINT32_C(0xa5a5a5a5) ^ ((batch + 1) * UINT32_C(1664525) + index * UINT32_C(1013904223)), {}};
        const auto length = (index * 37 + batch * 13) % 1025;
        for (std::uint32_t k = 0; k < length; ++k) {
            input.bytes.push_back(static_cast<unsigned char>(k * 73 + (k >> 3) * 19 + index * 7 + batch * 11));
        }
        jobs.push_back({static_cast<std::uint64_t>(batch) * 100000 + index, std::move(input)});
    }
    std::reverse(jobs.begin(), jobs.end()); // Caller order intentionally differs from canonical order.
    return jobs;
}
static std::uint32_t checksum(const Payload& input, const CancellationToken&) {
    return CvCompatibleCrc32{}.calculate(input.bytes.data(), input.bytes.size(), input.seed);
}

struct Probe {
    std::mutex mutex;
    std::condition_variable cv;
    std::size_t expected, arrived = 0, active = 0, peak = 0;
    std::int64_t next_finish;
    std::set<std::thread::id> ids;
    std::vector<std::uint32_t> first_completions;
    explicit Probe(std::size_t workers) : expected(workers), next_finish(static_cast<std::int64_t>(workers) - 1) {}
    void reverse_completion(std::uint32_t index) {
        if (index >= expected) return;
        std::unique_lock<std::mutex> lock(mutex);
        ++arrived;
        cv.notify_all();
        if (!cv.wait_for(lock, std::chrono::seconds(5), [&] { return arrived == expected && next_finish == index; }))
            throw std::runtime_error("Reverse completion gate timed out");
        first_completions.push_back(index);
        --next_finish;
        cv.notify_all();
    }
};
struct Activity {
    Probe& probe;
    explicit Activity(Probe& value) : probe(value) {
        std::lock_guard<std::mutex> lock(probe.mutex);
        ++probe.active;
        probe.peak = std::max(probe.peak, probe.active);
        probe.ids.insert(std::this_thread::get_id());
    }
    ~Activity() { std::lock_guard<std::mutex> lock(probe.mutex); --probe.active; }
    Activity(const Activity&) = delete;
    Activity& operator=(const Activity&) = delete;
};
static void write_record(FILE* file, std::uint32_t batch, std::uint32_t workers, const JobResult<std::uint32_t>& row) {
    const std::array<std::uint32_t, 4> fields{{batch, workers, static_cast<std::uint32_t>(row.id), row.value}};
    for (auto value : fields) {
        const unsigned char bytes[4] = {static_cast<unsigned char>(value), static_cast<unsigned char>(value >> 8),
            static_cast<unsigned char>(value >> 16), static_cast<unsigned char>(value >> 24)};
        if (std::fwrite(bytes, 1, 4, file) != 4) throw std::runtime_error("Trace write failed");
    }
}

static void failure_cases() {
    const BatchStamp stamp{17, 32, 51, 9, 2};
    for (auto workers : {std::size_t{0}, std::size_t{65}}) {
        bool rejected = false;
        try { evaluate_ordered(stamp, make_jobs(0), workers, checksum); }
        catch (const std::invalid_argument&) { rejected = true; }
        require(rejected, "invalid worker count accepted");
    }
    auto duplicate = make_jobs(0);
    duplicate[1].id = duplicate[0].id;
    bool rejected = false;
    try { evaluate_ordered(stamp, duplicate, 4, checksum); }
    catch (const std::invalid_argument&) { rejected = true; }
    require(rejected, "duplicate IDs accepted");

    auto empty = evaluate_ordered(stamp, std::vector<Job<Payload>>{}, 4, checksum);
    require(empty.status == BatchStatus::ready && empty.rows.empty() && empty.workers_started == 0, "empty batch failed");
    auto single = evaluate_ordered(stamp, make_jobs(0, 1), 64, checksum);
    require(single.status == BatchStatus::ready && single.rows.size() == 1 && single.workers_started == 1, "worker count not bounded by jobs");
    auto wide_ids = make_jobs(0, 2);
    wide_ids[0].id = UINT64_C(0xffffffffffffffff);
    wide_ids[1].id = UINT64_C(0x100000000);
    auto wide = evaluate_ordered(stamp, wide_ids, 2, checksum);
    require(wide.rows[0].id == UINT64_C(0x100000000) && wide.rows[1].id == UINT64_C(0xffffffffffffffff), "job IDs truncated");

    CancellationSource pre;
    pre.request();
    auto cancelled = evaluate_ordered(stamp, make_jobs(0), 4, checksum, pre.token());
    require(cancelled.status == BatchStatus::cancelled && cancelled.rows.empty()
            && cancelled.jobs_started == 0 && cancelled.workers_started == 0, "pre-cancel executed jobs");

    Probe failing(4);
    auto failure = evaluate_ordered(stamp, make_jobs(0), 4, [&](const Payload& input, const CancellationToken& token) {
        Activity activity(failing);
        if (input.index == 7) throw std::runtime_error("deliberate worker failure");
        return checksum(input, token);
    });
    require(failure.status == BatchStatus::failed && failure.rows.empty() && failure.error, "failure exposed partial rows");
    require(failing.active == 0, "failed batch returned before workers ended");
    bool same_error = false;
    try { std::rethrow_exception(failure.error); }
    catch (const std::runtime_error& error) { same_error = std::string(error.what()) == "deliberate worker failure"; }
    require(same_error, "worker exception lost");

    CancellationSource parent;
    Probe peer_failure(4);
    std::atomic_size_t peers_stopped{0};
    auto peer_result = evaluate_ordered(stamp, make_jobs(0), 4, [&](const Payload& input, const CancellationToken& token) {
        Activity activity(peer_failure);
        {
            std::unique_lock<std::mutex> lock(peer_failure.mutex);
            ++peer_failure.arrived;
            peer_failure.cv.notify_all();
            if (!peer_failure.cv.wait_for(lock, std::chrono::seconds(5), [&] { return peer_failure.arrived == 4; }))
                throw std::runtime_error("Peer failure gate timed out");
        }
        if (input.index == 0) throw std::runtime_error("cancel peers");
        const auto deadline = std::chrono::steady_clock::now() + std::chrono::seconds(5);
        while (!token.requested() && std::chrono::steady_clock::now() < deadline) std::this_thread::yield();
        if (!token.requested()) throw std::runtime_error("Peer failure was not propagated");
        peers_stopped.fetch_add(1, std::memory_order_relaxed);
        return checksum(input, token);
    }, parent.token());
    require(peer_result.status == BatchStatus::failed && peer_result.rows.empty()
            && peers_stopped.load() == 3 && peer_failure.active == 0, "failed worker did not cancel and drain peers");
    require(!parent.token().requested(), "batch failure cancelled the parent session");

    CancellationSource mid;
    Probe cancelling(4);
    std::size_t seen_cancel = 0;
    auto mid_result = evaluate_ordered(stamp, make_jobs(0), 4, [&](const Payload& input, const CancellationToken& token) {
        Activity activity(cancelling);
        {
            std::unique_lock<std::mutex> lock(cancelling.mutex);
            if (++cancelling.arrived == 4) { mid.request(); cancelling.cv.notify_all(); }
            if (!cancelling.cv.wait_for(lock, std::chrono::seconds(5), [&] { return token.requested(); }))
                throw std::runtime_error("Cancellation gate timed out");
            ++seen_cancel;
        }
        return checksum(input, token);
    }, mid.token());
    require(mid_result.status == BatchStatus::cancelled && mid_result.rows.empty(), "mid-flight cancel exposed results");
    require(mid_result.jobs_started == 4 && seen_cancel == 4 && cancelling.active == 0, "cancel did not drain workers");
    auto recovered = evaluate_ordered(stamp, make_jobs(1), 4, checksum);
    require(recovered.status == BatchStatus::ready && recovered.rows.size() == 64, "failure leaked into next batch");

    require(CvCompatibleCrc32{}.calculate(nullptr, 0, 123) == 123, "empty CRC changed seed");
    rejected = false;
    try { CvCompatibleCrc32{}.calculate(nullptr, 1); }
    catch (const std::invalid_argument&) { rejected = true; }
    require(rejected, "nonempty null CRC accepted");
    const unsigned char bytes[] = {0x78, 0x56, 0x34, 0x12};
    require(CvCompatibleCrc32{}.append_le32(UINT32_C(0x12345678)) == CvCompatibleCrc32{}.calculate(bytes, 4), "LE32 encoding mismatch");
}

int main(int argc, char** argv) {
    if (argc != 2) return 2;
    FILE* trace = nullptr;
    if (fopen_s(&trace, argv[1], "wb") || !trace) return 3;
    try {
        failure_cases();
        std::cout << "{\"scope\":\"ISOLATED_ORDERED_CRC_WORKERS_NOT_GAMECORE\",\"runs\":[";
        bool first = true;
        std::size_t records = 0;
        for (std::uint32_t batch = 0; batch < 24; ++batch) {
            std::vector<JobResult<std::uint32_t>> baseline;
            for (std::uint32_t workers : {1U, 2U, 4U}) {
                Probe probe(workers);
                const BatchStamp stamp{991, batch + 100, batch, batch, 7};
                const auto source = make_jobs(batch);
                auto result = evaluate_ordered(stamp, source, workers, [&](const Payload& input, const CancellationToken& token) {
                    Activity active(probe);
                    const auto value = checksum(input, token);
                    probe.reverse_completion(input.index);
                    return value;
                });
                require(result.status == BatchStatus::ready && result.rows.size() == source.size(), "valid batch failed");
                require(result.stamp == stamp, "batch identity changed");
                require(result.jobs_started == 64 && result.jobs_completed == 64, "job accounting mismatch");
                require(probe.active == 0 && probe.peak == workers && probe.ids.size() == workers, "worker overlap or join mismatch");
                require(probe.first_completions.size() == workers, "completion trace incomplete");
                for (std::uint32_t i = 0; i < workers; ++i)
                    require(probe.first_completions[i] == workers - 1 - i, "forced reverse completion failed");
                for (std::size_t i = 0; i < result.rows.size(); ++i) {
                    const auto& row = result.rows[i];
                    require(row.id == static_cast<std::uint64_t>(batch) * 100000 + i, "output order changed");
                    if (workers != 1) require(row.value == baseline[i].value, "worker count changed value");
                    write_record(trace, batch, workers, row);
                    ++records;
                }
                if (workers == 1) baseline = result.rows;
                if (!first) std::cout << ',';
                first = false;
                std::cout << "{\"batch\":" << batch << ",\"workers\":" << workers
                    << ",\"peak_inflight\":" << probe.peak << ",\"distinct_threads\":" << probe.ids.size()
                    << ",\"first_completion\":[";
                for (std::size_t i = 0; i < probe.first_completions.size(); ++i) {
                    if (i) std::cout << ',';
                    std::cout << probe.first_completions[i];
                }
                std::cout << "]}";
            }
        }
        if (std::fclose(trace) != 0) return 4;
        trace = nullptr;
        std::cout << "],\"checks_passed\":" << checks << ",\"records\":" << records << ",\"status\":\"PASS\"}\n";
        return 0;
    } catch (const std::exception& error) {
        if (trace) std::fclose(trace);
        std::cerr << "FAIL: " << error.what() << '\n';
        return 1;
    }
}
