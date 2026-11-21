// C++03 harness for the original v90 SDK binary. No engine startup or file CRC calls.
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fcntl.h>
#include <io.h>
typedef unsigned long dword; // FFireTypes.h:22
#include "FCrc32.h"
typedef char verify_pointer_width[sizeof(void*) == 4 ? 1 : -1];
typedef char verify_dword_width[sizeof(dword) == 4 ? 1 : -1];
typedef char verify_fcrc_size[sizeof(FCRC) == 1032 ? 1 : -1];

static bool read_u32(FILE* input, unsigned long& value) {
    unsigned char bytes[4];
    if (std::fread(bytes, 1, 4, input) != 4) return false;
    value = (unsigned long)bytes[0] | ((unsigned long)bytes[1] << 8)
        | ((unsigned long)bytes[2] << 16) | ((unsigned long)bytes[3] << 24);
    return true;
}
static bool write_u32(unsigned long value) {
    const unsigned char bytes[4] = {(unsigned char)value, (unsigned char)(value >> 8),
        (unsigned char)(value >> 16), (unsigned char)(value >> 24)};
    return std::fwrite(bytes, 1, 4, stdout) == 4;
}
int main(int argc, char** argv) {
    if (argc != 2 || _setmode(_fileno(stdout), _O_BINARY) == -1) return 2;
    FILE* input = NULL;
    if (fopen_s(&input, argv[1], "rb") || !input) return 3;
    char magic[8];
    unsigned long count = 0;
    if (std::fread(magic, 1, 8, input) != 8 || std::memcmp(magic, "ZCRC0001", 8) != 0
        || !read_u32(input, count) || count > 100000) { std::fclose(input); return 4; }
    int result = 0;
    for (unsigned long index = 0; index < count; ++index) {
        unsigned long id, seed, length, split;
        if (!read_u32(input, id) || !read_u32(input, seed) || !read_u32(input, length)
            || !read_u32(input, split) || length > 1048576 || split > length) { result = 5; break; }
        unsigned char* data = (unsigned char*)std::malloc(length + 1);
        if (!data) { result = 6; break; }
        if (std::fread(data, 1, length, input) != length) { std::free(data); result = 7; break; }
        const dword direct = g_CRC32.Calc(data, (int)length, seed);
        const dword partial = g_CRC32.Calc(data, (int)split, seed);
        const dword chained = g_CRC32.Calc(data + split, (int)(length - split), partial);
        std::free(data);
        if (!write_u32(id) || !write_u32(seed) || !write_u32(length)
            || !write_u32(direct) || !write_u32(chained)) { result = 8; break; }
    }
    if (result == 0 && (std::fgetc(input) != EOF || std::ferror(input))) result = 9;
    std::fclose(input);
    if (std::fflush(stdout) != 0) return 10;
    return result;
}
