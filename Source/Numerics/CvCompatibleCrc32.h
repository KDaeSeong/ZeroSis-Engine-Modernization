#pragma once

#include <array>
#include <cstddef>
#include <cstdint>
#include <stdexcept>

namespace zerosis::numerics {

// Raw reflected CRC32 state, matching SDK FCRC::Calc with its default polynomial.
// No final complement. This is a checksum, not an identity or security primitive.
// No game globals, mutable table, file I/O, allocation, or legacy FCRC ABI.
class CvCompatibleCrc32 final {
public:
    static constexpr std::uint32_t initial_state = UINT32_C(0xffffffff);

    std::uint32_t calculate(const void* data, std::size_t length,
                            std::uint32_t state = initial_state) const {
        if (length != 0 && data == nullptr) {
            throw std::invalid_argument("CRC input is null with a nonzero length");
        }
        const auto* bytes = static_cast<const unsigned char*>(data);
        for (std::size_t index = 0; index < length; ++index) {
            state = (state >> 8) ^ table_[(state ^ bytes[index]) & UINT32_C(0xff)];
        }
        return state;
    }

    // Explicit little-endian 32-bit value encoding; never checksum struct padding.
    std::uint32_t append_le32(std::uint32_t value, std::uint32_t state = initial_state) const {
        const std::array<unsigned char, 4> bytes{{
            static_cast<unsigned char>(value), static_cast<unsigned char>(value >> 8),
            static_cast<unsigned char>(value >> 16), static_cast<unsigned char>(value >> 24)}};
        return calculate(bytes.data(), bytes.size(), state);
    }

private:
    inline static constexpr std::array<std::uint32_t, 256> table_ = []() constexpr {
        std::array<std::uint32_t, 256> table{};
        for (std::size_t index = 0; index < table.size(); ++index) {
            auto state = static_cast<std::uint32_t>(index);
            for (unsigned bit = 0; bit < 8; ++bit) {
                state = (state >> 1) ^ ((state & 1) ? UINT32_C(0xedb88320) : 0);
            }
            table[index] = state;
        }
        return table;
    }();
};

} // namespace zerosis::numerics
