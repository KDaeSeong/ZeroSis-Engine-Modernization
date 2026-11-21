#pragma once
#include <cstddef>
#include <cstdint>
#include <string>

// Internal implementation API. The owning Localization runtime must initialize
// ICU with its owned ICU44 data before calls and wait for calls before cleanup.
namespace ZeroSisLocalization {
enum class NumericStyle { Decimal, Pattern, Percent, Currency, Roman, Spellout, Ordinal };
enum class TextCase { Upper, Lower, Title };
struct NumericValue {
    bool isInteger;
    int64_t integer;
    double real;
    static NumericValue FromInteger(int64_t value) { return { true, value, 0 }; }
    static NumericValue FromReal(double value) { return { false, 0, value }; }
};
struct IcuResult {
    bool succeeded;
    int status;
    int parseOffset;
};

// Owns a separate formatter per call. Failed calls preserve output; allocation
// failures propagate to the owning SDK boundary. No global locale is changed.
IcuResult FormatNumeric(const char* locale, NumericStyle style, const NumericValue& value,
                        const std::string& pattern, std::string& output);
IcuResult TransformTextCase(const char* locale, TextCase operation, const char* input,
                            size_t length, std::string& output);
}
