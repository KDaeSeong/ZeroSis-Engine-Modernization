#pragma once

#include <cstdint>
#include <limits>

namespace zerosis::numerics {

// Numeric state only. This is not a Civ V save record or a replacement CvRandom ABI.
struct RandomSnapshot {
    std::uint32_t seed;
    std::uint32_t calls;
    std::uint32_t resets;
    bool synchronous;
};

// Preserves the installed BNW SDK's release-mode arithmetic and numeric counters.
// Logging, stack histories, FDataStream and engine thread checks need host adapters.
// Instances belong to one state-owning thread; this class is not thread safe.
class CvCompatibleRandom final {
public:
    CvCompatibleRandom() noexcept { reset(); }

    // Both values select the synchronous constructor in the original SDK.
    // The argument controls debug stack logging there, not the synchronous flag.
    explicit CvCompatibleRandom(bool /*extended_callstack_debugging*/) noexcept
        : state_{0, 0, 0, true} {}

    void init(std::uint32_t seed) noexcept { reset(seed); }

    void reset(std::uint32_t seed = 0) noexcept {
        state_.seed = seed;
        ++state_.resets; // Deliberately retains calls and wraps modulo 2^32.
    }

    void reseed(std::uint32_t seed) noexcept { reset(seed); }

    std::uint16_t get(std::uint16_t bound) noexcept {
        ++state_.calls;
        const auto next = static_cast<std::uint32_t>(
            static_cast<std::uint64_t>(state_.seed) * UINT64_C(1103515245) + UINT64_C(12345));
        const auto upper = (next >> 16) & UINT32_C(65535);
        const auto value = static_cast<std::uint16_t>(
            (static_cast<std::uint64_t>(upper) * bound) / UINT64_C(65536));
        state_.seed = next; // A zero bound still consumes a draw, matching the SDK.
        return value;
    }

    float getFloat() noexcept {
        return static_cast<float>(get(UINT16_C(65535))) / 65535.0f;
    }

    std::uint32_t getSeed() const noexcept { return state_.seed; }
    std::uint32_t getCallCount() const noexcept { return state_.calls; }
    std::uint32_t getResetCount() const noexcept { return state_.resets; }
    bool isSynchronous() const noexcept { return state_.synchronous; }

    RandomSnapshot numeric_snapshot() const noexcept { return state_; }
    void restore_numeric(RandomSnapshot state) noexcept { state_ = state; }

    // CvRandom compares the seed only. Full numeric state comparisons are explicit.
    bool operator==(const CvCompatibleRandom& other) const noexcept {
        return state_.seed == other.state_.seed;
    }
    bool operator!=(const CvCompatibleRandom& other) const noexcept { return !(*this == other); }

private:
    RandomSnapshot state_{0, 0, 0, false};
};

static_assert(std::numeric_limits<std::uint32_t>::digits == 32);
static_assert(std::numeric_limits<std::uint16_t>::digits == 16);
static_assert(sizeof(float) == 4 && std::numeric_limits<float>::is_iec559);

} // namespace zerosis::numerics
