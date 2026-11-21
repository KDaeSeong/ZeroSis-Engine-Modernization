#include <cstdint>
#include <cstdio>
#include <cstring>
#include <exception>
#include <limits>
#include <vector>
#include <fcntl.h>
#include <io.h>

#include "Numerics/CvCompatibleCrc32.h"
static_assert(sizeof(void*) == 8 && sizeof(std::size_t) == 8);

static bool read_u32(FILE* input, std::uint32_t& value) {
    unsigned char bytes[4];
    if (std::fread(bytes, 1, 4, input) != 4) return false;
    value = std::uint32_t(bytes[0]) | (std::uint32_t(bytes[1]) << 8)
        | (std::uint32_t(bytes[2]) << 16) | (std::uint32_t(bytes[3]) << 24);
    return true;
}

static bool write_u32(std::uint32_t value) {
    const unsigned char bytes[4] = {static_cast<unsigned char>(value), static_cast<unsigned char>(value >> 8),
        static_cast<unsigned char>(value >> 16), static_cast<unsigned char>(value >> 24)};
    return std::fwrite(bytes, 1, 4, stdout) == 4;
}

static std::uint32_t calculate(const unsigned char* data, std::size_t length, std::uint32_t seed) {
    return zerosis::numerics::CvCompatibleCrc32{}.calculate(data, length, seed);
}

int main(int argc, char** argv) {
    if (argc != 2 || _setmode(_fileno(stdout), _O_BINARY) == -1) return 2;
    FILE* input = nullptr;
    if (fopen_s(&input, argv[1], "rb") || !input) return 3;
    int result = 0;
    try {
        char magic[8];
        std::uint32_t count = 0;
        if (std::fread(magic, 1, 8, input) != 8 || std::memcmp(magic, "ZCRC0001", 8) != 0
            || !read_u32(input, count) || count > 100000) { std::fclose(input); return 4; }
        for (std::uint32_t index = 0; index < count; ++index) {
            std::uint32_t id, seed, length, split;
            if (!read_u32(input, id) || !read_u32(input, seed) || !read_u32(input, length)
                || !read_u32(input, split) || length > 1048576 || split > length) {
                result = 5; break;
            }
            // Keep a valid address even for an empty block; no undocumented SDK null call.
            std::vector<unsigned char> bytes(static_cast<std::size_t>(length) + 1);
            if (std::fread(bytes.data(), 1, length, input) != length) { result = 6; break; }
            const auto direct = calculate(bytes.data(), length, seed);
            const auto partial = calculate(bytes.data(), split, seed);
            const auto chained = calculate(bytes.data() + split, length - split, partial);
            if (!write_u32(id) || !write_u32(seed) || !write_u32(length)
                || !write_u32(direct) || !write_u32(chained)) { result = 7; break; }
        }
        if (result == 0 && (std::fgetc(input) != EOF || std::ferror(input))) result = 8;
    } catch (const std::exception&) { result = 9; }
    std::fclose(input);
    if (std::fflush(stdout) != 0) return 10;
    return result;
}
