#pragma once
#include <vector>
#include <cstring>
#include <float.h>

namespace LocalizationNumericCases {
enum Kind { Integer, Integer64, Float, Double };
struct Input {
    Kind kind;
    __int64 integer;
    double real;
    Input(Kind k, __int64 i, double r) : kind(k), integer(i), real(r) {}
};
static const char* const Formats[] = { "{1}", "{1_Num}", "{1: number}", "{1_Num:number}",
    "{1_Num:number #,##0.00}", "{1_Num:number(0.00)}", "{1_Num:percent}", "{1_Num:currency}",
    "{1_Num:roman}", "{1_Num:spellout}", "{1_Num:ordinal}" };
static const char* const Locales[] = { "en_US", "ko_KR" };
static bool UnsafeRuleBased(unsigned style, const Input& input) {
    return style >= 8 && (input.kind == Float || input.kind == Double) && !_finite(input.real);
}
static std::vector<Input> Values() {
    std::vector<Input> out;
    const int ints[] = { (-2147483647 - 1), -1000000, -12345, -2, -1, 0, 1, 2, 10, 1000, 12345, 2147483647 };
    for (unsigned i = 0; i < sizeof(ints) / sizeof(ints[0]); ++i) out.push_back(Input(Integer, ints[i], 0));
    const __int64 longs[] = { (-9223372036854775807i64 - 1), -9007199254740993i64, -4294967296i64, -1, 0, 1,
        2147483648i64, 4294967296i64, 9007199254740991i64, 9007199254740992i64, 9007199254740993i64, 9223372036854775807i64 };
    for (unsigned i = 0; i < sizeof(longs) / sizeof(longs[0]); ++i) out.push_back(Input(Integer64, longs[i], 0));
    const unsigned floatBits[] = { 0, 0x80000000u, 0x3f800000u, 0xbf800000u, 0x3fa00000u, 0x3f808f5cu,
        0x38d1b717u, 0x4b800001u, 0x4f800000u, 0x71800000u, 0x7f800000u, 0x7fc00000u, 0xff800000u, 0xffc00000u };
    for (unsigned i = 0; i < sizeof(floatBits) / sizeof(floatBits[0]); ++i) {
        float value; std::memcpy(&value, &floatBits[i], sizeof(value));
        out.push_back(Input(Float, 0, static_cast<double>(value)));
    }
    const double reals[] = { 0.0, -0.0, -1.25, -0.0001, 0.0001, 0.5, 1.005, 1.23456789012345, 1.0e10, 1.0e30,
        -1.0e30, 9007199254740992.0 };
    for (unsigned i = 0; i < sizeof(reals) / sizeof(reals[0]); ++i) out.push_back(Input(Double, 0, reals[i]));
    const unsigned __int64 doubleBits[] = { 0x7ff0000000000000ui64, 0xfff0000000000000ui64, 0x7ff8000000000000ui64, 0xfff8000000000000ui64 };
    for (unsigned i = 0; i < sizeof(doubleBits) / sizeof(doubleBits[0]); ++i) {
        double value; std::memcpy(&value, &doubleBits[i], sizeof(value)); out.push_back(Input(Double, 0, value));
    }
    return out;
}
}
