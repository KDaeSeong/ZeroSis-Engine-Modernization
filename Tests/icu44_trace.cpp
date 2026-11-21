#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <malloc.h>
#include <vector>
#include <thread>
#include <atomic>
#include <limits>
#include <unicode/uclean.h>
#include <unicode/udata.h>
#include <unicode/unum.h>
#include <unicode/ustring.h>
#include "localization_numeric_cases.h"
#include "SdkLocalizationIcu.h"

static unsigned checks = 0;
#define CHECK(x) do { ++checks; if (!(x)) { std::fprintf(stderr, "FAIL|%u|%d|%s\n", checks, __LINE__, #x); std::exit(2); } } while (0)

static void Emit(const char* label, const std::string& value) {
    std::printf("TEXT|%s|bytes=%zu|", label, value.size());
    for (size_t i = 0; i < value.size(); ++i) std::printf("%02x", static_cast<unsigned char>(value[i]));
    std::printf("\n");
}

static ZeroSisLocalization::NumericStyle Style(unsigned index) {
    using ZeroSisLocalization::NumericStyle;
    const NumericStyle styles[] = { NumericStyle::Decimal, NumericStyle::Decimal, NumericStyle::Decimal, NumericStyle::Decimal,
        NumericStyle::Pattern, NumericStyle::Pattern, NumericStyle::Percent, NumericStyle::Currency,
        NumericStyle::Roman, NumericStyle::Spellout, NumericStyle::Ordinal };
    CHECK(index < sizeof(styles) / sizeof(styles[0]));
    return styles[index];
}
static std::string Pattern(unsigned index) { return index == 4 ? "#,##0.00" : index == 5 ? "(0.00)" : ""; }

static void Numbers() {
    using namespace ZeroSisLocalization;
    for (unsigned i = 0; i < 11; ++i) {
        std::string integer, real;
        const IcuResult first = FormatNumeric("en_US", Style(i), NumericValue::FromInteger(12345), Pattern(i), integer);
        CHECK(first.succeeded);
        CHECK(FormatNumeric("en_US", Style(i), NumericValue::FromReal(1.25), Pattern(i), real).succeeded);
        std::printf("FORMAT|%u|status=%s\n", i, u_errorName(static_cast<UErrorCode>(first.status)));
        Emit("integer", integer); Emit("float", real);
    }
}

static void Case() {
    using namespace ZeroSisLocalization;
    struct Input { const char* value; const char* locale; const char* upper; const char* lower; };
    const Input cases[] = { { "hEllo", "en_US", "HELLO", "hello" }, { "\xc3\x9f", "de_DE", "SS", "\xc3\x9f" },
        { "iI\xc4\xb0\xc4\xb1", "tr_TR", "\xc4\xb0I\xc4\xb0I", "i\xc4\xb1i\xc4\xb1" },
        { "\xed\x95\x9c\xea\xb8\x80", "ko_KR", "\xed\x95\x9c\xea\xb8\x80", "\xed\x95\x9c\xea\xb8\x80" },
        { "\xce\xa3 \xcf\x83 \xcf\x82", "el_GR", "\xce\xa3 \xce\xa3 \xce\xa3", "\xcf\x83 \xcf\x83 \xcf\x82" },
        { "hello world", "en_US", "HELLO WORLD", "hello world" } };
    for (unsigned i = 0; i < sizeof(cases) / sizeof(cases[0]); ++i) {
        for (unsigned op = 0; op < 3; ++op) {
            std::string output("unchanged");
            const IcuResult result = TransformTextCase(cases[i].locale, static_cast<TextCase>(op), cases[i].value, std::strlen(cases[i].value), output);
            std::printf("CASE|%u|%u|%s|%s\n", i, op, cases[i].locale, u_errorName(static_cast<UErrorCode>(result.status)));
            if (result.succeeded) { CHECK(op < 2); CHECK(output == (op == 0 ? cases[i].upper : cases[i].lower)); Emit("case", output); }
            else { CHECK(op == 2 && result.status == U_MISSING_RESOURCE_ERROR); CHECK(output == "unchanged"); }
        }
    }
}

static void NumericCorpus() {
    using namespace LocalizationNumericCases;
    using namespace ZeroSisLocalization;
    const std::vector<Input> values = Values();
    unsigned rejected = 0;
    for (unsigned lang = 0; lang < sizeof(Locales) / sizeof(Locales[0]); ++lang) {
        for (unsigned style = 0; style < 11; ++style) {
            for (unsigned i = 0; i < values.size(); ++i) {
                const Input& input = values[i]; std::string output("unchanged");
                const NumericValue number = input.kind == Integer || input.kind == Integer64 ?
                    NumericValue::FromInteger(input.integer) : NumericValue::FromReal(input.real);
                const IcuResult result = FormatNumeric(Locales[lang], Style(style), number, Pattern(style), output);
                if (UnsafeRuleBased(style, input)) {
                    CHECK(!result.succeeded && result.status == U_ILLEGAL_ARGUMENT_ERROR); CHECK(output == "unchanged"); ++rejected; continue;
                }
                if (!result.succeeded) std::printf("FORMAT_FAILURE|%u|%u|%u|status=%s|offset=%d\n", lang, style, i, u_errorName(static_cast<UErrorCode>(result.status)), result.parseOffset);
                CHECK(result.succeeded);
                std::printf("NUMERIC|%u|%u|%u|", lang, style, i);
                for (size_t b = 0; b < output.size(); ++b) std::printf("%02x", static_cast<unsigned char>(output[b]));
                std::printf("\n");
            }
        }
    }
    std::printf("NONFINITE_RULE_REJECTED|%u\n", rejected); CHECK(rejected == 48);
}

static void BoundariesAndThreads() {
    using namespace ZeroSisLocalization;
    const NumericValue number = NumericValue::FromInteger(12345);
    std::string output("keep");
    CHECK(!FormatNumeric(NULL, NumericStyle::Decimal, number, "", output).succeeded && output == "keep");
    CHECK(!FormatNumeric("en_US", static_cast<NumericStyle>(-1), number, "", output).succeeded && output == "keep");
    CHECK(!FormatNumeric("en_US", NumericStyle::Pattern, number, "#..0", output).succeeded && output == "keep");
    CHECK(!FormatNumeric("en_US", NumericStyle::Pattern, number, "\xff", output).succeeded && output == "keep");
    CHECK(!TransformTextCase(NULL, TextCase::Upper, "a", 1, output).succeeded && output == "keep");
    CHECK(!TransformTextCase("en_US", TextCase::Upper, NULL, 1, output).succeeded && output == "keep");
    CHECK(!TransformTextCase("en_US", TextCase::Upper, "a", static_cast<size_t>(INT32_MAX), output).succeeded && output == "keep");
    CHECK(!TransformTextCase("en_US", TextCase::Upper, "\xff", 1, output).succeeded && output == "keep");
    CHECK(!TransformTextCase("en_US", static_cast<TextCase>(-1), "a", 1, output).succeeded && output == "keep");
    output = "#,##0.00"; CHECK(FormatNumeric("en_US", NumericStyle::Pattern, number, output, output).succeeded && output == "12,345.00");
    output = "aB"; CHECK(TransformTextCase("en_US", TextCase::Upper, output.data(), output.size(), output).succeeded && output == "AB");
    CHECK(TransformTextCase("en_US", TextCase::Upper, "a\0b", 3, output).succeeded && output == std::string("A\0B", 3));
    CHECK(TransformTextCase("en_US", TextCase::Upper, NULL, 0, output).succeeded && output.empty());
    output.assign(16384, 'a'); CHECK(TransformTextCase("en_US", TextCase::Upper, output.data(), output.size(), output).succeeded && output == std::string(16384, 'A'));
    const std::string longPattern = "'" + std::string(1024, 'X') + "'0.00";
    CHECK(FormatNumeric("en_US", NumericStyle::Pattern, NumericValue::FromInteger(12), longPattern, output).succeeded);
    CHECK(output == std::string(1024, 'X') + "12.00");
    CHECK(FormatNumeric("en_US", NumericStyle::Pattern, number, "'\xed\x95\x9c\xea\xb8\x80'#,##0.00", output).succeeded);
    CHECK(output == "\xed\x95\x9c\xea\xb8\x80" "12,345.00");
    const char* emoji = "a\xf0\x9f\x99\x82" "b";
    CHECK(TransformTextCase("en_US", TextCase::Upper, emoji, std::strlen(emoji), output).succeeded);
    CHECK(output == "A\xf0\x9f\x99\x82" "B");
    std::printf("DYNAMIC_AND_UNICODE_BOUNDARIES|PASS\n");
    std::atomic<unsigned> failures(0), completed(0);
    std::vector<std::thread> workers;
    for (unsigned thread = 0; thread < 4; ++thread) workers.emplace_back([&]() {
        for (unsigned i = 0; i < 256; ++i) {
            std::string text;
            if (!FormatNumeric("en_US", NumericStyle::Currency, number, "", text).succeeded || text != "$12,345.00") ++failures;
            if (!TransformTextCase("tr_TR", TextCase::Upper, "i", 1, text).succeeded || text != "\xc4\xb0") ++failures;
            ++completed;
        }
    });
    for (auto& worker : workers) worker.join();
    CHECK(failures == 0); CHECK(completed == 1024);
    std::printf("CONCURRENT_FORMATS|%u|failures=%u\n", completed.load() * 2, failures.load());
}

int wmain(int argc, wchar_t** argv) {
    if (argc != 2) return 1;
    std::setvbuf(stdout, NULL, _IONBF, 0);
    FILE* input = NULL;
    CHECK(_wfopen_s(&input, argv[1], L"rb") == 0 && input);
    CHECK(_fseeki64(input, 0, SEEK_END) == 0);
    const __int64 length = _ftelli64(input);
    CHECK(length > 32 && length < 128 * 1024 * 1024);
    CHECK(_fseeki64(input, 0, SEEK_SET) == 0);
    void* data = _aligned_malloc(static_cast<size_t>(length), 16);
    CHECK(data != NULL);
    CHECK(std::fread(data, 1, static_cast<size_t>(length), input) == static_cast<size_t>(length));
    CHECK(std::fclose(input) == 0);
    UErrorCode status = U_ZERO_ERROR;
    udata_setFileAccess(UDATA_NO_FILES, &status);
    CHECK(U_SUCCESS(status));
    udata_setCommonData(data, &status);
    CHECK(U_SUCCESS(status));
    u_init(&status);
    CHECK(U_SUCCESS(status));
    UVersionInfo version;
    u_getVersion(version);
    std::printf("ICU|%u.%u.%u.%u|data_bytes=%lld\n", version[0], version[1], version[2], version[3], length);
    Numbers(); Case(); NumericCorpus(); BoundariesAndThreads();
    u_cleanup();
    _aligned_free(data);
    std::printf("PASS|%u\n", checks);
    return 0;
}
