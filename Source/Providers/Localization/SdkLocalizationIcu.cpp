#include "SdkLocalizationIcu.h"
#include <climits>
#include <cmath>
#include <limits>
#include <memory>
#include <vector>
#include <unicode/unum.h>
#include <unicode/ustring.h>

namespace ZeroSisLocalization {
namespace {
IcuResult Failure(UErrorCode code, int offset = -1) { return { false, static_cast<int>(code), offset }; }

bool FromUtf8(const char* input, size_t length, std::vector<UChar>& converted, int32_t& count, UErrorCode& status) {
    if ((!input && length) || length >= static_cast<size_t>(INT32_MAX)) {
        status = U_ILLEGAL_ARGUMENT_ERROR; return false;
    }
    u_strFromUTF8(NULL, 0, &count, input ? input : "", static_cast<int32_t>(length), &status);
    if (status != U_BUFFER_OVERFLOW_ERROR && U_FAILURE(status)) return false;
    if (count < 0 || count == INT32_MAX) { status = U_INDEX_OUTOFBOUNDS_ERROR; return false; }
    converted.resize(static_cast<size_t>(count) + 1);
    status = U_ZERO_ERROR;
    u_strFromUTF8(converted.data(), count + 1, &count, input ? input : "", static_cast<int32_t>(length), &status);
    return U_SUCCESS(status);
}

IcuResult ToUtf8(const UChar* input, int32_t length, int warning, std::string& output) {
    int32_t count = 0; UErrorCode status = U_ZERO_ERROR;
    u_strToUTF8(NULL, 0, &count, input, length, &status);
    if (status != U_BUFFER_OVERFLOW_ERROR && U_FAILURE(status)) return Failure(status);
    if (count < 0 || count == INT32_MAX) return Failure(U_INDEX_OUTOFBOUNDS_ERROR);
    std::vector<char> buffer(static_cast<size_t>(count) + 1);
    status = U_ZERO_ERROR;
    u_strToUTF8(buffer.data(), count + 1, &count, input, length, &status);
    if (U_FAILURE(status)) return Failure(status);
    std::string candidate(buffer.data(), static_cast<size_t>(count));
    output.swap(candidate);
    return { true, warning, -1 };
}
}

IcuResult FormatNumeric(const char* locale, NumericStyle style, const NumericValue& value,
                        const std::string& pattern, std::string& output) {
    if (!locale) return Failure(U_ILLEGAL_ARGUMENT_ERROR);
    UNumberFormatStyle icuStyle;
    bool ruleBased = false;
    switch (style) {
    case NumericStyle::Decimal: icuStyle = UNUM_DECIMAL; break;
    case NumericStyle::Pattern: icuStyle = UNUM_PATTERN_DECIMAL; break;
    case NumericStyle::Percent: icuStyle = UNUM_PERCENT; break;
    case NumericStyle::Currency: icuStyle = UNUM_CURRENCY; break;
    case NumericStyle::Roman: icuStyle = UNUM_NUMBERING_SYSTEM; ruleBased = true; break;
    case NumericStyle::Spellout: icuStyle = UNUM_SPELLOUT; ruleBased = true; break;
    case NumericStyle::Ordinal: icuStyle = UNUM_ORDINAL; ruleBased = true; break;
    default: return Failure(U_ILLEGAL_ARGUMENT_ERROR);
    }
    double real = value.real;
    if (!value.isInteger && !std::isfinite(real)) {
        // Original rule-based spellout recurses to stack exhaustion on NaN.
        // For decimal formats, the original VC9 formatter renders infinity as
        // NaN as well. Preserve that observable text without entering the unsafe
        // rule-based path or relying on the modern CRT's infinity spelling.
        if (ruleBased) return Failure(U_ILLEGAL_ARGUMENT_ERROR);
        real = std::numeric_limits<double>::quiet_NaN();
    }
    UErrorCode status = U_ZERO_ERROR;
    std::vector<UChar> pattern16;
    int32_t patternLength = 0;
    if (style == NumericStyle::Pattern && !FromUtf8(pattern.data(), pattern.size(), pattern16, patternLength, status))
        return Failure(status);
    UParseError parse = {};
    std::unique_ptr<UNumberFormat, decltype(&unum_close)> formatter(
        unum_open(icuStyle, pattern16.empty() ? NULL : pattern16.data(), patternLength, locale, &parse, &status), &unum_close);
    if (U_FAILURE(status) || !formatter) return Failure(U_FAILURE(status) ? status : U_MEMORY_ALLOCATION_ERROR, parse.offset);
    const int warning = static_cast<int>(status);
    if (style == NumericStyle::Roman) {
        const UChar rules[] = { '%', 'r', 'o', 'm', 'a', 'n', '-', 'u', 'p', 'p', 'e', 'r', 0 };
        status = U_ZERO_ERROR;
        unum_setTextAttribute(formatter.get(), UNUM_DEFAULT_RULESET, rules, -1, &status);
        if (U_FAILURE(status)) return Failure(status);
    }
    auto formatInto = [&](UChar* target, int32_t capacity) -> int32_t {
        status = U_ZERO_ERROR;
        return value.isInteger ? unum_formatInt64(formatter.get(), value.integer, target, capacity, NULL, &status) :
            unum_formatDouble(formatter.get(), real, target, capacity, NULL, &status);
    };
    // ICU44 rule-based formatting of INT64_MIN can return a different required
    // length between a zero-capacity preflight and the following call. Start
    // with real storage, and honor any later overflow size instead of assuming
    // that one preflight makes the next call infallible.
    UChar local[128];
    int32_t count = formatInto(local, 128);
    if (U_SUCCESS(status)) return ToUtf8(local, count, warning, output);
    if (status != U_BUFFER_OVERFLOW_ERROR) return Failure(status);
    std::vector<UChar> buffer;
    for (unsigned attempt = 0; attempt < 3; ++attempt) {
        if (count < 0 || count == INT32_MAX) return Failure(U_INDEX_OUTOFBOUNDS_ERROR);
        buffer.resize(static_cast<size_t>(count) + 1);
        count = formatInto(buffer.data(), count + 1);
        if (U_SUCCESS(status)) return ToUtf8(buffer.data(), count, warning, output);
        if (status != U_BUFFER_OVERFLOW_ERROR) return Failure(status);
    }
    return Failure(U_INTERNAL_PROGRAM_ERROR);
}

IcuResult TransformTextCase(const char* locale, TextCase operation, const char* input, size_t length, std::string& output) {
    if (!locale) return Failure(U_ILLEGAL_ARGUMENT_ERROR);
    UErrorCode status = U_ZERO_ERROR;
    std::vector<UChar> input16; int32_t inputLength = 0;
    if (!FromUtf8(input, length, input16, inputLength, status)) return Failure(status);
    auto transform = [&](UChar* target, int32_t capacity, UErrorCode& result) -> int32_t {
        switch (operation) {
        case TextCase::Upper: return u_strToUpper(target, capacity, input16.data(), inputLength, locale, &result);
        case TextCase::Lower: return u_strToLower(target, capacity, input16.data(), inputLength, locale, &result);
        case TextCase::Title: return u_strToTitle(target, capacity, input16.data(), inputLength, NULL, locale, &result);
        default: result = U_ILLEGAL_ARGUMENT_ERROR; return 0;
        }
    };
    status = U_ZERO_ERROR;
    int32_t count = transform(NULL, 0, status);
    if (status != U_BUFFER_OVERFLOW_ERROR && U_FAILURE(status)) return Failure(status);
    if (count < 0 || count == INT32_MAX) return Failure(U_INDEX_OUTOFBOUNDS_ERROR);
    std::vector<UChar> result(static_cast<size_t>(count) + 1);
    status = U_ZERO_ERROR;
    count = transform(result.data(), count + 1, status);
    if (U_FAILURE(status)) return Failure(status);
    return ToUtf8(result.data(), count, static_cast<int>(status), output);
}
}
