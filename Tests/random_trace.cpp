#include <cstdint>
#include <cstddef>
#include <cstdio>
#include <cstring>
#include <fcntl.h>
#include <io.h>

#ifdef ZEROSIS_REFERENCE_BUILD
#include "sdk_numeric_reference.h"
using TestedRandom = SdkNumericReference;
using Snapshot = ReferenceSnapshot;
static_assert(sizeof(void*) == 4 && sizeof(std::size_t) == 4);
#else
#include "Numerics/CvCompatibleRandom.h"
using TestedRandom = zerosis::numerics::CvCompatibleRandom;
using Snapshot = zerosis::numerics::RandomSnapshot;
static_assert(sizeof(void*) == 8 && sizeof(std::size_t) == 8);
#endif

// Windows x64 uses LLP64: pointers grow, but unsigned long remains 32 bits.
static_assert(sizeof(unsigned long) == 4 && sizeof(unsigned int) == 4);
static_assert(sizeof(unsigned short) == 2 && sizeof(bool) == 1);

namespace {
bool output_ok = true;

void word(std::uint32_t value) {
    unsigned char bytes[4]{};
    for (unsigned i = 0; i < 4; ++i) {
        bytes[i] = static_cast<unsigned char>((value >> (i * 8)) & 255u);
    }
    output_ok = std::fwrite(bytes, 1, 4, stdout) == 4 && output_ok;
}

void record(std::uint32_t phase, std::uint32_t bound, std::uint32_t result,
            const TestedRandom& random, std::uint32_t index = 0) {
    word(phase); word(bound); word(result); word(random.getSeed());
    word(random.getCallCount()); word(random.getResetCount());
    word(random.isSynchronous() ? 1u : 0u); word(index);
}
}

int main() {
    if (_setmode(_fileno(stdout), _O_BINARY) == -1) return 2;

    TestedRandom random;
    record(1, 0, 0, random);
    TestedRandom sync_false(false);
    TestedRandom sync_true(true);
    record(2, 0, 0, sync_false);
    record(3, 0, 0, sync_true);
    random.init(UINT32_C(0xffffffff));
    auto draw = random.get(0);
    record(4, 0, draw, random);
    draw = random.get(1);
    record(5, 1, draw, random);
    random.reset(17);
    record(6, 0, 0, random);
    random.reseed(8);
    record(7, 0, 0, random);
    random.restore_numeric(Snapshot{UINT32_C(0xffffffff), UINT32_C(0xffffffff), UINT32_C(0xffffffff), false});
    draw = random.get(0);
    record(8, 0, draw, random);
    random.reseed(0);
    record(9, 0, 0, random);
    TestedRandom copy(random);
    copy.get(37);
    record(10, 37, copy != random ? 1u : 0u, copy);
    copy.restore_numeric(Snapshot{random.getSeed(), 123, 456, true});
    record(11, 0, copy == random ? 1u : 0u, copy);

    TestedRandom sweep;
    sweep.init(UINT32_C(0x12345678));
    for (std::uint32_t bound = 0; bound < 65536; ++bound) {
        draw = sweep.get(static_cast<std::uint16_t>(bound));
        record(20, bound, draw, sweep, bound);
    }

    for (std::uint32_t seed_index = 0; seed_index < 1024; ++seed_index) {
        TestedRandom sequence;
        sequence.init((seed_index * UINT32_C(2654435761)) ^ UINT32_C(0xa5a5a5a5));
        for (std::uint32_t draw_index = 0; draw_index < 128; ++draw_index) {
            const auto bound = static_cast<std::uint16_t>((seed_index * 131u + draw_index * 997u) & 65535u);
            draw = sequence.get(bound);
            record(30, bound, draw, sequence, seed_index * 128u + draw_index);
        }
    }

    TestedRandom floats;
    floats.init(UINT32_C(0x87654321));
    for (std::uint32_t index = 0; index < 1024; ++index) {
        const float value = floats.getFloat();
        std::uint32_t bits = 0;
        static_assert(sizeof(bits) == sizeof(value));
        std::memcpy(&bits, &value, sizeof(bits));
        record(40, 65535, bits, floats, index);
    }
    return output_ok && std::fflush(stdout) == 0 ? 0 : 3;
}
