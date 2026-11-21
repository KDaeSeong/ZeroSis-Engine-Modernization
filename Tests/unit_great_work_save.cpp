#include "../Source/Serialization/UnitGreatWorkSave.h"
#include <array>
#include <cstddef>
#include <cstdint>
#include <exception>
#include <iostream>
#include <limits>
#include <memory>
#include <stdexcept>
#include <string>

// Portable policy tests only. Fake lookup and destination objects never open
// a database, SDK stream, game object, file, process, window or network.
namespace {
using ZeroSisSerialization::ResolveRequiredUnitGreatWorkHash;
using ZeroSisSerialization::UnitGreatWorkHashForSave;
struct Suite {
    std::size_t checks = 0, noWorkCases = 0, validCases = 0, failureCases = 0, literalWireSuffixes = 0;
    std::size_t shortCircuitCases = 0, exceptionCases = 0, hashValueCases = 0;
    std::size_t directExceptionControls = 0, directPointerEqual = 0, directPointerDifferent = 0;
    std::size_t propagatedPointerEqual = 0, propagatedPointerDifferent = 0;
    bool directExceptionContractPreserved = false;
    bool allFailureBodyCallsZero = true, allFailurePersistCallsZero = true, unchangedFailureDestinations = true;
    void Check(bool value, const char* message) {
        ++checks;
        if (!value) throw std::runtime_error(message);
    }
};
enum class Method : unsigned char { DatabaseReady, Prepare, Bind, Step, Type, Hash, Count };
constexpr std::size_t MethodCount = static_cast<std::size_t>(Method::Count);
constexpr char WorkType[] = "GREAT_WORK_LITERAL";
struct InjectedFailure final {
    Method method;
    std::uint32_t marker;
    std::shared_ptr<const std::uint32_t> identity;
    InjectedFailure(Method stage, std::uint32_t value) : method(stage), marker(value),
        identity(std::make_shared<const std::uint32_t>(value)) {}
};
struct CatalogInput {
    bool databaseReady = true, prepare = true, bind = true, step = true;
    const char* type = WorkType;
    std::uint32_t hash = 0x1234abcdu;
    Method throwAt = Method::Count;
    std::exception_ptr failure;
    std::array<unsigned char, 6> sentinel = {0x17,0x3b,0x5f,0x83,0xa7,0xcb};
};
bool SameInput(const CatalogInput& left, const CatalogInput& right) {
    return left.databaseReady == right.databaseReady && left.prepare == right.prepare && left.bind == right.bind &&
        left.step == right.step && left.type == right.type && left.hash == right.hash && left.throwAt == right.throwAt &&
        left.failure == right.failure && left.sentinel == right.sentinel;
}
struct FakeLookup {
    const CatalogInput& input;
    std::array<Method, MethodCount> order{};
    std::array<std::size_t, MethodCount> calls{};
    std::size_t total = 0;
    const char* hashedType = nullptr;
    explicit FakeLookup(const CatalogInput& source) : input(source) {}
    void Visit(Method method) {
        if (total == order.size()) throw std::logic_error("Lookup was called beyond the six-step contract");
        order[total++] = method; ++calls[static_cast<std::size_t>(method)];
        if (input.throwAt == method) std::rethrow_exception(input.failure);
    }
    bool DatabaseReady() { Visit(Method::DatabaseReady); return input.databaseReady; }
    bool Prepare() { Visit(Method::Prepare); return input.prepare; }
    bool Bind() { Visit(Method::Bind); return input.bind; }
    bool Step() { Visit(Method::Step); return input.step; }
    const char* Type() { Visit(Method::Type); return input.type; }
    std::uint32_t Hash(const char* type) { hashedType = type; Visit(Method::Hash); return input.hash; }
};
struct UnitInput {
    bool hasWork = true;
    std::int32_t tourism = -2;
    std::uint32_t missionCount = 0;
    std::array<unsigned char, 6> sentinel = {0xdc,0xba,0x98,0x76,0x54,0x32};
};
bool SameInput(const UnitInput& left, const UnitInput& right) {
    return left.hasWork == right.hasWork && left.tourism == right.tourism && left.missionCount == right.missionCount &&
        left.sentinel == right.sentinel;
}
struct Destination {
    std::array<unsigned char, 20> bytes = {
        0x31,0x72,0xb4,0xf6, 0xa5,0xa5,0xa5,0xa5,0xa5,0xa5,0xa5,0xa5,0xa5,0xa5,0xa5,0xa5, 0x91,0x52,0x13,0xd4};
    std::size_t bodyCalls = 0, persistCalls = 0, hashWords = 0;
};
using WireSuffix = std::array<unsigned char, 12>;
void PutWord(Destination& destination, std::size_t begin, std::uint32_t value) {
    for (unsigned byte = 0; byte < 4u; ++byte)
        destination.bytes[begin + byte] = static_cast<unsigned char>(value >> (byte * 8u));
}
template<class Resolver>
std::uint32_t SaveHarness(const UnitInput& source, Destination& destination, Resolver resolve) {
    // The harness deliberately models preflight before its first body emit.
    // It does not call CvUnit::write, an SDK stream, a database or a real file.
    const auto bodyWriter = [&](std::uint32_t hash) {
        ++destination.bodyCalls; ++destination.hashWords;
        PutWord(destination, 4, hash);
        PutWord(destination, 8, static_cast<std::uint32_t>(source.tourism));
        PutWord(destination, 12, source.missionCount);
    };
    const auto persist = [&] { ++destination.persistCalls; };
    const auto hash = UnitGreatWorkHashForSave(source.hasWork, resolve);
    bodyWriter(hash); persist();
    return hash;
}
std::uint32_t SaveWithLookup(const UnitInput& source, Destination& destination, FakeLookup& lookup,
        std::size_t& resolverCalls) {
    return SaveHarness(source, destination, [&] {
        ++resolverCalls;
        return ResolveRequiredUnitGreatWorkHash(lookup);
    });
}
void LookupPrefix(Suite& suite, const FakeLookup& lookup, std::size_t expectedCalls) {
    suite.Check(lookup.total == expectedCalls, "Lookup call count differs from the first failure boundary");
    for (std::size_t index = 0; index < MethodCount; ++index) {
        suite.Check(lookup.calls[index] == (index < expectedCalls ? 1u : 0u), "Lookup did not short-circuit exactly once");
        if (index < expectedCalls)
            suite.Check(lookup.order[index] == static_cast<Method>(index), "Lookup method order changed");
    }
    suite.Check(lookup.hashedType == (expectedCalls == MethodCount ? lookup.input.type : nullptr),
        "Hash did not receive exactly the Type pointer or ran before Type succeeded");
}
void UnchangedInput(Suite& suite, const UnitInput& source, const UnitInput& before) {
    suite.Check(SameInput(source, before), "The immutable unit-input sentinel changed");
}
void FailureDestination(Suite& suite, const UnitInput& source, const UnitInput& beforeSource,
        const Destination& destination, const Destination& beforeDestination) {
    suite.allFailureBodyCallsZero = suite.allFailureBodyCallsZero && destination.bodyCalls == 0u && destination.hashWords == 0u;
    suite.allFailurePersistCallsZero = suite.allFailurePersistCallsZero && destination.persistCalls == 0u;
    suite.unchangedFailureDestinations = suite.unchangedFailureDestinations && destination.bytes == beforeDestination.bytes;
    suite.Check(destination.bodyCalls == 0u && destination.hashWords == 0u, "A failed preflight called the body writer");
    suite.Check(destination.persistCalls == 0u, "A failed preflight called persistence");
    suite.Check(destination.bytes == beforeDestination.bytes, "A failed preflight changed the destination sentinel");
    UnchangedInput(suite, source, beforeSource);
}
void LiteralSuffix(Suite& suite, const Destination& destination, const WireSuffix& literal) {
    // Independent v9 field suffix only: one u32 hash, i32 tourism=-2 and a
    // zero mission count. This literal is not a complete serialized unit.
    for (std::size_t byte = 0; byte < literal.size(); ++byte)
        suite.Check(destination.bytes[4u + byte] == literal[byte], "The literal v9 hash/tourism/mission-count suffix differs");
    const std::array<unsigned char, 4> before = {0x31,0x72,0xb4,0xf6}, after = {0x91,0x52,0x13,0xd4};
    for (std::size_t byte = 0; byte < before.size(); ++byte)
        suite.Check(destination.bytes[byte] == before[byte] && destination.bytes[16u + byte] == after[byte],
            "Successful suffix output crossed its byte guards");
    suite.Check(destination.bodyCalls == 1u && destination.persistCalls == 1u && destination.hashWords == 1u,
        "A successful harness did not write exactly one hash word before one persistence call");
    ++suite.literalWireSuffixes;
}
void ValidLookupCase(Suite& suite, const CatalogInput input, const WireSuffix& literal) {
    const auto beforeInput = input; FakeLookup lookup(input);
    const UnitInput source; const auto beforeSource = source; Destination destination; std::size_t resolverCalls = 0;
    const auto actual = SaveWithLookup(source, destination, lookup, resolverCalls);
    suite.Check(actual == input.hash && resolverCalls == 1u, "A required valid hash was changed or resolved more than once");
    LookupPrefix(suite, lookup, MethodCount);
    suite.Check(SameInput(input, beforeInput), "The immutable fake catalog input changed on success");
    UnchangedInput(suite, source, beforeSource); LiteralSuffix(suite, destination, literal); ++suite.validCases;
}
void NoWork(Suite& suite) {
    CatalogInput config; config.databaseReady = config.prepare = config.bind = config.step = false;
    config.type = nullptr; config.hash = 0; config.throwAt = Method::DatabaseReady;
    config.failure = std::make_exception_ptr(InjectedFailure{Method::DatabaseReady, 0x1742u});
    const CatalogInput input = config, beforeInput = input; FakeLookup lookup(input);
    UnitInput unit; unit.hasWork = false; const UnitInput source = unit, beforeSource = source;
    Destination destination; std::size_t resolverCalls = 0;
    const auto actual = SaveWithLookup(source, destination, lookup, resolverCalls);
    suite.Check(actual == 0u && resolverCalls == 0u, "No-work save performed an unnecessary resolver call");
    LookupPrefix(suite, lookup, 0);
    suite.Check(SameInput(input, beforeInput), "No-work save changed the immutable fake catalog input");
    UnchangedInput(suite, source, beforeSource);
    LiteralSuffix(suite, destination, WireSuffix{0,0,0,0, 0xfe,0xff,0xff,0xff, 0,0,0,0}); ++suite.noWorkCases;
}
void RejectedLookupCase(Suite& suite, const CatalogInput input, std::size_t expectedCalls) {
    const auto beforeInput = input; FakeLookup lookup(input);
    const UnitInput source; const auto beforeSource = source; Destination destination; const auto beforeDestination = destination;
    std::size_t resolverCalls = 0; bool rejected = false;
    try { SaveWithLookup(source, destination, lookup, resolverCalls); }
    catch (const std::runtime_error&) { rejected = true; }
    suite.Check(rejected && resolverCalls == 1u, "A required lookup failure was accepted or retried");
    LookupPrefix(suite, lookup, expectedCalls);
    suite.Check(SameInput(input, beforeInput), "A rejected lookup changed the immutable fake catalog input");
    FailureDestination(suite, source, beforeSource, destination, beforeDestination);
    ++suite.failureCases; ++suite.shortCircuitCases;
}
void LookupFailures(Suite& suite) {
    CatalogInput database; database.databaseReady = false; RejectedLookupCase(suite, database, 1);
    CatalogInput prepare; prepare.prepare = false; RejectedLookupCase(suite, prepare, 2);
    CatalogInput bind; bind.bind = false; RejectedLookupCase(suite, bind, 3);
    CatalogInput step; step.step = false; RejectedLookupCase(suite, step, 4);
    CatalogInput nullType; nullType.type = nullptr; RejectedLookupCase(suite, nullType, 5);
    CatalogInput emptyType; emptyType.type = ""; RejectedLookupCase(suite, emptyType, 5);
    CatalogInput zeroHash; zeroHash.hash = 0; RejectedLookupCase(suite, zeroHash, 6);
}
void ExceptionPayload(Suite& suite, const InjectedFailure& actual, const InjectedFailure& expected) {
    // InjectedFailure is final, so this handler cannot accept a derived wrapper.
    suite.Check(actual.method == expected.method && actual.marker == expected.marker, "The original exception payload changed");
    suite.Check(actual.identity && expected.identity && actual.identity == expected.identity && *actual.identity == expected.marker,
        "The original shared exception identity token changed");
}
void DirectExceptionControl(Suite& suite) {
    // No policy helper is called. Observe this runtime's exception_ptr behavior
    // separately from the required final-type/payload/shared-token contract.
    const InjectedFailure marker{Method::Count, 0x6143ca27u}; const auto original = std::make_exception_ptr(marker);
    bool caught = false;
    try { std::rethrow_exception(original); }
    catch (...) {
        caught = true; const auto observed = std::current_exception();
        suite.Check(static_cast<bool>(observed), "Direct exception control did not capture the active exception");
        ++suite.directExceptionControls;
        if (observed == original) ++suite.directPointerEqual; else ++suite.directPointerDifferent;
        try { throw; }
        catch (const InjectedFailure& actual) { ExceptionPayload(suite, actual, marker); }
        catch (...) { suite.Check(false, "Direct exception control changed the exact final exception type"); }
        suite.directExceptionContractPreserved = true;
    }
    suite.Check(caught && suite.directExceptionControls == 1u && suite.directPointerEqual + suite.directPointerDifferent == 1u,
        "Direct exception control did not complete exactly once");
}
void PropagatedException(Suite& suite, const std::exception_ptr& original, const InjectedFailure& expected) {
    const auto observed = std::current_exception();
    suite.Check(static_cast<bool>(observed), "An injected exception is no longer active");
    // Pointer equality is observational; a permitted runtime copy can differ.
    if (observed == original) ++suite.propagatedPointerEqual; else ++suite.propagatedPointerDifferent;
    try { throw; }
    catch (const InjectedFailure& actual) { ExceptionPayload(suite, actual, expected); }
    catch (...) { suite.Check(false, "The original exception type changed"); }
}
void LookupExceptions(Suite& suite) {
    for (std::size_t index = 0; index < MethodCount; ++index) {
        const auto method = static_cast<Method>(index);
        const InjectedFailure marker{method, 0x61520000u + static_cast<std::uint32_t>(index)};
        CatalogInput config; config.throwAt = method; config.failure = std::make_exception_ptr(marker);
        const CatalogInput input = config, beforeInput = input; FakeLookup lookup(input);
        const UnitInput source; const auto beforeSource = source; Destination destination; const auto beforeDestination = destination;
        std::size_t resolverCalls = 0; bool rejected = false;
        try { SaveWithLookup(source, destination, lookup, resolverCalls); }
        catch (...) { rejected = true; PropagatedException(suite, input.failure, marker); }
        suite.Check(rejected && resolverCalls == 1u, "An injected lookup exception was swallowed or retried");
        LookupPrefix(suite, lookup, index + 1u);
        suite.Check(SameInput(input, beforeInput), "An exceptional lookup changed the immutable fake catalog input");
        FailureDestination(suite, source, beforeSource, destination, beforeDestination);
        ++suite.failureCases; ++suite.shortCircuitCases; ++suite.exceptionCases;
    }
}
void HashValues(Suite& suite) {
    for (std::uint32_t value = 0; value < 256u; ++value) {
        std::size_t noWorkCalls = 0;
        const auto absent = UnitGreatWorkHashForSave(false, [&] { ++noWorkCalls; return value; });
        suite.Check(absent == 0u && noWorkCalls == 0u, "A no-work branch evaluated its modest hash candidate");
        ++suite.noWorkCases;
        std::size_t requiredCalls = 0;
        if (value == 0u) {
            const UnitInput source; const auto beforeSource = source; Destination destination; const auto beforeDestination = destination;
            bool rejected = false;
            try { SaveHarness(source, destination, [&] { ++requiredCalls; return value; }); }
            catch (const std::runtime_error&) { rejected = true; }
            suite.Check(rejected && requiredCalls == 1u, "A direct zero hash was accepted or its callback was retried");
            FailureDestination(suite, source, beforeSource, destination, beforeDestination); ++suite.failureCases;
        } else {
            const auto required = UnitGreatWorkHashForSave(true, [&] { ++requiredCalls; return value; });
            suite.Check(required == value && requiredCalls == 1u, "A modest nonzero hash was changed or its callback was retried");
            ++suite.validCases;
        }
        ++suite.hashValueCases;
    }
}
void DirectResolverException(Suite& suite) {
    struct RuntimeThrowResolver {
        std::size_t& calls;
        const std::exception_ptr& failure;
        volatile bool& throwEnabled;
        std::uint32_t operator()() const {
            ++calls;
            if (throwEnabled) std::rethrow_exception(failure);
            return 1u;
        }
    };
    const InjectedFailure marker{Method::Count, 0xfedcba98u}; const auto original = std::make_exception_ptr(marker);
    const UnitInput source; const auto beforeSource = source; Destination destination; const auto beforeDestination = destination;
    std::size_t resolverCalls = 0; bool rejected = false; volatile bool throwEnabled = true;
    const RuntimeThrowResolver required{resolverCalls, original, throwEnabled};
    try {
        SaveHarness(source, destination, required);
    } catch (...) { rejected = true; PropagatedException(suite, original, marker); }
    suite.Check(rejected && resolverCalls == 1u, "A direct resolver exception was swallowed or retried");
    FailureDestination(suite, source, beforeSource, destination, beforeDestination); ++suite.failureCases; ++suite.exceptionCases;
    std::size_t absentCalls = 0;
    const RuntimeThrowResolver absent{absentCalls, original, throwEnabled};
    suite.Check(UnitGreatWorkHashForSave(false, absent) == 0u &&
        absentCalls == 0u, "A no-work branch evaluated a throwing resolver"); ++suite.noWorkCases;
}
void Run(Suite& suite) {
    DirectExceptionControl(suite);
    NoWork(suite);
    ValidLookupCase(suite, CatalogInput{}, WireSuffix{0xcd,0xab,0x34,0x12, 0xfe,0xff,0xff,0xff, 0,0,0,0});
    CatalogInput maximum; maximum.hash = (std::numeric_limits<std::uint32_t>::max)();
    ValidLookupCase(suite, maximum, WireSuffix{0xff,0xff,0xff,0xff, 0xfe,0xff,0xff,0xff, 0,0,0,0});
    LookupFailures(suite); LookupExceptions(suite); HashValues(suite); DirectResolverException(suite);
}
void Text(const std::string& value) {
    std::cout << '"';
    for (const char raw : value) {
        const auto ch = static_cast<unsigned char>(raw);
        if (ch == '"' || ch == '\\') std::cout << '\\';
        std::cout << (ch < 32u ? '?' : static_cast<char>(ch));
    }
    std::cout << '"';
}
const char* Boolean(bool value) { return value ? "true" : "false"; }
void Print(const Suite& suite, bool passed, const std::string& error) {
    std::cout << "{\"schema\":\"zerosis.unit_great_work_save_policy.v1\",\"status\":\""
        << (passed ? "PASS_UNIT_GREAT_WORK_SAVE_POLICY" : "FAIL_UNIT_GREAT_WORK_SAVE_POLICY")
        << "\",\"checks\":" << suite.checks << ",\"no_work_cases\":" << suite.noWorkCases
        << ",\"valid_cases\":" << suite.validCases << ",\"failure_cases\":" << suite.failureCases
        << ",\"literal_wire_suffixes\":" << suite.literalWireSuffixes
        << ",\"short_circuit_cases\":" << suite.shortCircuitCases << ",\"exception_cases\":" << suite.exceptionCases
        << ",\"hash_value_cases\":" << suite.hashValueCases
        << ",\"exception_identity_control\":{\"cases\":" << suite.directExceptionControls
        << ",\"pointer_equal\":" << suite.directPointerEqual << ",\"pointer_different\":" << suite.directPointerDifferent
        << ",\"type_payload_shared_token_preserved\":" << Boolean(suite.directExceptionContractPreserved)
        << ",\"policy_helpers_called\":false,\"pointer_equality_is_acceptance_condition\":false}"
        << ",\"propagated_exception_pointer_observations\":{\"equal\":" << suite.propagatedPointerEqual
        << ",\"different\":" << suite.propagatedPointerDifferent << ",\"pointer_equality_is_acceptance_condition\":false}"
        << ",\"required_exception_contract\":\"exact_final_type_payload_shared_identity_token\""
        << ",\"all_failure_body_calls_zero\":" << Boolean(suite.allFailureBodyCallsZero)
        << ",\"all_failure_persist_calls_zero\":" << Boolean(suite.allFailurePersistCallsZero)
        << ",\"unchanged_failure_destinations\":" << Boolean(suite.unchangedFailureDestinations)
        << ",\"fake_lookup_only\":true,\"test_writer_harness_only\":true,\"database_sdk_or_gamecore_executed\":false"
        << ",\"production_unit_write_executed\":false,\"real_database_executed\":false,\"real_file_persistence_executed\":false"
        << ",\"gamecore_loaded\":false,\"window_created\":false,\"game_accessed\":false,\"user_saves_accessed\":false"
        << ",\"complete_player_validated\":false,\"complete_save_validated\":false"
        << ",\"ruleset_compatibility_verified\":false,\"restore_approved\":false,\"full_engine_goal_complete\":false,\"error\":";
    Text(error); std::cout << "}\n";
}
} // namespace

int main() {
    static_assert(sizeof(void*) == 8, "Great work policy tests require x64");
    static_assert(sizeof(std::uint32_t) == 4 && sizeof(std::int32_t) == 4, "Great work wire words must be 32 bits");
    Suite suite; bool passed = false; std::string error;
    try { Run(suite); passed = true; }
    catch (const std::exception& failure) { error = failure.what(); }
    catch (...) { error = "Unexpected non-standard test exception"; }
    Print(suite, passed, error); return passed ? 0 : 1;
}
