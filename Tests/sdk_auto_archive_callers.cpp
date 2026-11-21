// Actual generated SDK templates, linked to the candidate provider. No GameCore host.
#include "SdkAutoArchiveIncludes.h"
#include <process.h>
#include <memory>

static __declspec(thread) long allocationCountdown = -1;
static __declspec(thread) unsigned int allocationAttempts = 0;
void* operator new(size_t bytes) {
    if (allocationCountdown >= 0) {
        ++allocationAttempts;
        if (allocationCountdown-- == 0) throw std::bad_alloc();
    }
    void* result = malloc(bytes ? bytes : 1);
    if (!result) throw std::bad_alloc();
    return result;
}
void operator delete(void* pointer) noexcept { free(pointer); }
void operator delete(void* pointer, size_t) noexcept { free(pointer); }
void* operator new[](size_t bytes) { return ::operator new(bytes); }
void operator delete[](void* pointer) noexcept { ::operator delete(pointer); }
void operator delete[](void* pointer, size_t) noexcept { ::operator delete(pointer); }

static unsigned int checks = 0;
static void require(bool value) {
    ++checks;
    if (!value) { fprintf(stderr, "FAILED|%u\n", checks); throw std::runtime_error("caller check failed"); }
}

struct ThrowValue {
    static long countdown;
    static int live;
    int value;
    static void step() { if (countdown >= 0 && countdown-- == 0) throw std::runtime_error("value operation fault"); }
    ThrowValue(): value(0) { step(); ++live; }
    explicit ThrowValue(int v): value(v) { step(); ++live; }
    ThrowValue(const ThrowValue& other): value(other.value) { step(); ++live; }
    ~ThrowValue() { --live; }
    ThrowValue& operator=(const ThrowValue& other) { value = other.value; step(); return *this; }
    bool operator==(const ThrowValue& other) const { return value == other.value; }
    bool operator!=(const ThrowValue& other) const { return value != other.value; }
};
long ThrowValue::countdown = -1;
int ThrowValue::live = 0;
FDataStream& operator<<(FDataStream& stream, const ThrowValue& value) { return stream << value.value; }
FDataStream& operator>>(FDataStream& stream, ThrowValue& value) { return stream >> value.value; }

template<class Owner> struct Container: FAutoArchiveClassContainer<Owner> {
    explicit Container(Owner& owner): FAutoArchiveClassContainer<Owner>(owner) {}
    size_t count() const { return this->m_contents.size(); }
};
// The archive stores a reference without invoking owner methods in its constructor.
#pragma warning(push)
#pragma warning(disable:4355)
struct Owner {
    Container<Owner> archive;
    Owner(): archive(*this) {}
    std::string debugDump(const FAutoVariableBase&) const { return "CALLER_OWNER"; }
    std::string stackTraceRemark(const FAutoVariableBase&) const { return "CALLER_REMARK"; }
};
#pragma warning(pop)
typedef FAutoVariable<int, Owner> Scalar;
template<class T> using Vector = FAutoVariable<std::vector<T>, Owner>;

static void lifecycle() {
    unsigned int faults = 0, cleanups = 0, bounds = 0;
    {
        Owner owner;
        Scalar* a = new Scalar("life_first", owner.archive, 10);
        Vector<int>* b = new Vector<int>("life_vector", owner.archive);
        Scalar* c = new Scalar("life_last", owner.archive, 30);
        const std::string* stable = &c->name();
        b->push_back(3); delete a;
        require(b->name() == "life_vector" && c->name() == "life_last" && &c->name() == stable);
        delete b; require(owner.archive.count() == 1 && !owner.archive.hasDeltas());
        Scalar replacement("replacement", owner.archive, 44);
        require(replacement.name() == "replacement" && c->name() == "life_last");
        owner.archive.setVariableName(replacement, "replacement");
        bool refused = false;
        try { owner.archive.setVariableName(replacement, "different"); } catch (const std::invalid_argument&) { refused = true; ++faults; }
        require(refused && replacement.name() == "replacement");
        owner.archive.remove(replacement); refused = false;
        try { replacement.name(); } catch (const std::logic_error&) { refused = true; ++faults; }
        require(refused); owner.archive.add(replacement); require(replacement.name() == "replacement");
        delete c; cleanups += 3;
    }
    for (unsigned int kind = 0; kind != 4; ++kind) {
        Owner owner; ThrowValue value(9); const int alive = ThrowValue::live;
        ThrowValue::countdown = 0; bool failed = false;
        try {
            if (kind == 0) { FAutoVariable<ThrowValue, Owner> variable("default", owner.archive); }
            if (kind == 1) { FAutoVariable<ThrowValue, Owner> variable("default_track", owner.archive, true); }
            if (kind == 2) { FAutoVariable<ThrowValue, Owner> variable("copied", owner.archive, value); }
            if (kind == 3) { FAutoVariable<ThrowValue, Owner> variable("copied_track", owner.archive, value, true); }
        } catch (const std::runtime_error&) { failed = true; ++faults; }
        ThrowValue::countdown = -1;
        require(failed && ThrowValue::live == alive && owner.archive.count() == 0 && !owner.archive.hasDeltas()); ++cleanups;
    }
    for (long failAt = 0; failAt != 9; ++failAt) {
        Owner owner; ThrowValue::countdown = failAt; bool failed = false;
        try { Vector<ThrowValue> variable("vector_ctor", owner.archive, size_t(9), false); }
        catch (const std::runtime_error&) { failed = true; ++faults; }
        ThrowValue::countdown = -1;
        require(failed && ThrowValue::live == 0 && owner.archive.count() == 0 && !owner.archive.hasDeltas()); ++cleanups;
    }
    // Allocation failures in registration/name interning must unwind a base ctor too.
    unsigned int registrationFailures = 0;
    for (long failAt = 0; failAt != 32; ++failAt) {
        Owner owner; const std::string name(128, static_cast<char>('A' + failAt)); bool failed = false;
        allocationCountdown = failAt; allocationAttempts = 0;
        try { Scalar variable(name, owner.archive, 7); } catch (const std::bad_alloc&) { failed = true; }
        allocationCountdown = -1;
        require(owner.archive.count() == 0 && !owner.archive.hasDeltas());
        if (!failed) { require(allocationAttempts == static_cast<unsigned int>(failAt)); break; }
        ++registrationFailures; ++cleanups;
        require(failAt != 31);
    }
    // Archive-first destruction: make its old storage unreadable before deleting variables.
    SYSTEM_INFO info; GetSystemInfo(&info);
    void* page = VirtualAlloc(NULL, info.dwPageSize, MEM_RESERVE | MEM_COMMIT, PAGE_READWRITE); require(page != NULL);
    Owner* owner = new(page)Owner;
    Scalar* scalar = new Scalar("orphan_scalar", owner->archive, 1);
    Vector<int>* vector = new Vector<int>("orphan_vector", owner->archive); vector->push_back(2);
    owner->~Owner(); DWORD oldProtection = 0;
    require(VirtualProtect(page, info.dwPageSize, PAGE_NOACCESS, &oldProtection) != FALSE);
    delete scalar; delete vector; require(VirtualFree(page, 0, MEM_RELEASE) != FALSE); cleanups += 2;
    {
        Owner own; Vector<int> values("bounds", own.archive, size_t(3), false);
        const size_t badIndices[] = {3, 4, size_t(UINT_MAX) + 1, size_t(-1)};
        for (size_t i = 0; i != 4; ++i) for (unsigned int op = 0; op != 4; ++op) {
            if (op == 3 && badIndices[i] == 3) continue; // end insertion is legal.
            bool failed = false;
            try {
                if (op == 0) (void)values[badIndices[i]];
                if (op == 1) values.setAt(badIndices[i], 9);
                if (op == 2) values.erase(badIndices[i]);
                if (op == 3) values.insert(badIndices[i], 9);
            } catch (const std::out_of_range&) { failed = true; ++bounds; }
            require(failed && values.size() == 3 && !own.archive.hasDeltas());
        }
        bool failed = false;
        try { Vector<int> huge("too_large", own.archive, size_t(UINT_MAX) + 1, false); }
        catch (const std::range_error&) { failed = true; ++bounds; }
        require(failed && own.archive.count() == 1);
    }
    require(ThrowValue::live == 0);
    printf("{\"mode\":\"lifecycle\",\"checks\":%u,\"constructor_and_name_faults\":%u,\"registration_allocation_failures\":%u,\"lifetime_cleanups\":%u,\"bounds_rejections\":%u,\"protected_owner_pages\":1,\"base_bytes\":%u,\"scalar_bytes\":%u,\"vector_bytes\":%u}\n",
        checks, faults, registrationFailures, cleanups, bounds, static_cast<unsigned int>(sizeof(FAutoVariableBase)),
        static_cast<unsigned int>(sizeof(Scalar)), static_cast<unsigned int>(sizeof(Vector<int>)));
}

template<class T> static T value(int n) { return T(n); }
template<> bool value<bool>(int n) { return n != 99; }
template<class T> static std::vector<T> inputValues() {
    std::vector<T> result; result.push_back(value<T>(3)); result.push_back(value<T>(5)); result.push_back(value<T>(7)); return result;
}
template<class T> static const std::vector<T>& contents(const Vector<T>& vector) { return static_cast<const std::vector<T>&>(vector); }
static bool same(const FMemoryStream& a, const FMemoryStream& b) {
    return a.GetEOF() == b.GetEOF() && (!a.GetEOF() || memcmp(a.GetBuf(), b.GetBuf(), a.GetEOF()) == 0);
}
template<class T> static void expectedDelta(FMemoryStream& stream, unsigned int variant, const std::vector<T>& original) {
    stream << (variant ? 1u : 0u);
    if (variant == 1) stream << 1u << original;
    if (variant == 2) stream << 0u << 12;
}
template<class T> static void apply(Vector<T>& vector, unsigned int op, const std::vector<T>& input, FMemoryStream& load) {
    const T item = value<T>(99);
    if (op == 0) vector.setAt(1, item);
    if (op == 1) vector.insert(1, item);
    if (op == 2) vector.push_back(item);
    if (op == 3) vector.clear();
    if (op == 4) vector.erase(1);
    if (op == 5) vector.resize(9);
    if (op == 6) vector.resize(9, item);
    if (op == 7) vector.resize(1);
    if (op == 8) vector = input;
    if (op == 9) vector = contents(vector);
    if (op == 10) vector.push_back(vector[0]);
    if (op == 11) vector.insert(vector.size(), vector[0]);
    if (op == 12) vector.resize(9, vector[0]);
    if (op == 13) vector.load(load);
    if (op == 14) vector.loadDelta(load);
}
template<class T> static void model(std::vector<T>& vector, unsigned int op, const std::vector<T>& input) {
    const T item = value<T>(99);
    if (op == 0) vector[1] = item;
    if (op == 1) vector.insert(vector.begin() + 1, item);
    if (op == 2) vector.push_back(item);
    if (op == 3) vector.clear();
    if (op == 4) vector.erase(vector.begin() + 1);
    if (op == 5) vector.resize(9);
    if (op == 6) vector.resize(9, item);
    if (op == 7) vector.resize(1);
    if (op == 8 || op == 13 || op == 14) vector = input;
    if (op == 10 || op == 11) { const T first = vector[0]; vector.push_back(first); }
    if (op == 12) { const T first = vector[0]; vector.resize(9, first); }
}
struct MutationStats { unsigned int rejected, succeeded; MutationStats(): rejected(0), succeeded(0) {} };
template<class T> static MutationStats mutations(bool throwingValues) {
    MutationStats stats;
    for (unsigned int op = 0; op != 15; ++op) for (unsigned int variant = 0; variant != 3; ++variant) {
        bool completed = false;
        for (long failAt = 0; failAt != 256; ++failAt) {
            Owner owner; Scalar sentinel("sentinel", owner.archive, 4); Vector<T> vector("mutations", owner.archive);
            vector.dirtyGet() = inputValues<T>();
            if (variant == 1) vector.push_back(value<T>(6));
            if (variant == 2) sentinel = 12;
            const std::vector<T> original(contents(vector)); std::vector<T> expected(original); const std::vector<T> input(2, value<T>(71));
            model(expected, op, input);
            FMemoryStream source, before; source << input; source.Rewind(); expectedDelta(before, variant, original);
            const int live = ThrowValue::live; bool failed = false;
            allocationAttempts = 0;
            if (throwingValues) ThrowValue::countdown = failAt; else allocationCountdown = failAt;
            try { apply(vector, op, input, source); }
            catch (const std::bad_alloc&) { failed = true; require(!throwingValues); }
            catch (const std::runtime_error&) { failed = true; require(throwingValues); }
            allocationCountdown = -1; ThrowValue::countdown = -1;
            if (failed) {
                ++stats.rejected; require(contents(vector) == original && ThrowValue::live == live);
                FMemoryStream pending; std::vector<std::pair<std::string,std::string> > stacks;
                owner.archive.saveDelta(pending, stacks); require(same(pending, before));
            } else {
                require(contents(vector) == expected); require(owner.archive.hasDeltas() == (op != 14 || variant != 0));
                if (!throwingValues) require(allocationAttempts == static_cast<unsigned int>(failAt));
                ++stats.succeeded; completed = true; break;
            }
        }
        require(completed);
    }
    return stats;
}
static void mutationTests() {
    const MutationStats integers = mutations<int>(false);
    const MutationStats booleans = mutations<bool>(false);
    const MutationStats customAlloc = mutations<ThrowValue>(false);
    const MutationStats customValues = mutations<ThrowValue>(true);
    require(ThrowValue::live == 0);
    unsigned int readFailures = 0;
    for (int endian = 0; endian != 3; ++endian) for (unsigned int variant = 0; variant != 3; ++variant)
        for (unsigned int delta = 0; delta != 2; ++delta) for (unsigned int bytes = 0; bytes != 12; ++bytes) {
            Owner owner; Scalar sentinel("sentinel", owner.archive, 4); Vector<int> vector("short_read", owner.archive);
            vector.dirtyGet() = inputValues<int>();
            if (variant == 1) vector.push_back(6); if (variant == 2) sentinel = 12;
            const std::vector<int> original(contents(vector)); FMemoryStream before; expectedDelta(before, variant, original);
            FMemoryStream valid; valid.SetDesiredEndianNess(static_cast<FEndian::EEndianness>(endian)); valid << 2u << 71 << 72;
            FMemoryStream truncated(static_cast<int>(bytes), valid.GetBuf(), false);
            truncated.SetDesiredEndianNess(static_cast<FEndian::EEndianness>(endian)); bool rejected = false;
            try { if (delta) vector.loadDelta(truncated); else vector.load(truncated); }
            catch (const std::exception&) { rejected = true; ++readFailures; }
            require(rejected && contents(vector) == original);
            FMemoryStream pending; std::vector<std::pair<std::string,std::string> > stacks; owner.archive.saveDelta(pending, stacks);
            require(same(pending, before));
        }
    // Normal scalar edits must not clone the full vector. Capacity may grow but values remain stable.
    Owner owner; Vector<int> many("growth", owner.archive); allocationCountdown = LONG_MAX; allocationAttempts = 0;
    for (unsigned int i = 0; i != 4096; ++i) many.push_back(static_cast<int>(i));
    const unsigned int growthAllocations = allocationAttempts; allocationCountdown = -1;
    require(many.size() == 4096 && growthAllocations < 64);
    for (unsigned int i = 0; i != 4096; ++i) require(many[i] == static_cast<int>(i));
    printf("{\"mode\":\"mutations\",\"checks\":%u,\"operation_kinds\":15,\"pending_variants\":3,\"integer_allocation_failures\":%u,\"bool_allocation_failures\":%u,\"custom_allocation_failures\":%u,\"custom_value_failures\":%u,\"successful_mutations\":%u,\"truncated_vector_reads\":%u,\"growth_pushes\":4096,\"growth_allocations\":%u}\n",
        checks, integers.rejected, booleans.rejected, customAlloc.rejected, customValues.rejected,
        integers.succeeded + booleans.succeeded + customAlloc.succeeded + customValues.succeeded, readFailures, growthAllocations);
}

struct Worker { HANDLE start, ready; volatile LONG* readyCount; unsigned int id; bool passed; const std::string* common; unsigned int completed; };
static unsigned int __stdcall worker(void* argument) {
    Worker& w = *static_cast<Worker*>(argument);
    try {
        if (InterlockedIncrement(w.readyCount) == 8 && !SetEvent(w.ready)) return 7;
        if (WaitForSingleObject(w.start, 30000) != WAIT_OBJECT_0) return 1;
        for (unsigned int i = 0; i != 512; ++i) {
            Owner owner; char unique[64]; sprintf_s(unique, "worker_%u_name_%u", w.id, i % 16);
            std::unique_ptr<Scalar> a, b;
            if (w.id % 2) { b.reset(new Scalar(unique, owner.archive, 2)); a.reset(new Scalar("concurrent_common", owner.archive, 1)); }
            else { a.reset(new Scalar("concurrent_common", owner.archive, 1)); b.reset(new Scalar(unique, owner.archive, 2)); }
            if (a->name() != "concurrent_common" || b->name() != unique) return 2;
            if (!w.common) w.common = &a->name();
            if (&a->name() != w.common) return 3;
            b.reset(); if (a->name() != "concurrent_common" || owner.archive.count() != 1) return 4;
            a.reset(); if (owner.archive.count() != 0 || owner.archive.hasDeltas()) return 5;
            ++w.completed;
        }
        w.passed = true; return 0;
    } catch (...) { return 6; }
}
static void concurrency() {
    HANDLE start = CreateEventW(NULL, TRUE, FALSE, NULL); require(start != NULL);
    HANDLE ready = CreateEventW(NULL, TRUE, FALSE, NULL); require(ready != NULL); volatile LONG readyCount = 0;
    Worker workers[8] = {}; HANDLE handles[8] = {};
    for (unsigned int i = 0; i != 8; ++i) {
        workers[i].start = start; workers[i].ready = ready; workers[i].readyCount = &readyCount; workers[i].id = i;
        handles[i] = reinterpret_cast<HANDLE>(_beginthreadex(NULL, 0, worker, &workers[i], 0, NULL)); require(handles[i] != NULL);
    }
    require(WaitForSingleObject(ready, 30000) == WAIT_OBJECT_0 && readyCount == 8);
    require(SetEvent(start) != FALSE);
    require(WaitForMultipleObjects(8, handles, TRUE, 30000) == WAIT_OBJECT_0);
    for (unsigned int i = 0; i != 8; ++i) {
        DWORD exitCode = 99; require(GetExitCodeThread(handles[i], &exitCode) && exitCode == 0);
        require(workers[i].passed && workers[i].completed == 512 && workers[i].common == workers[0].common);
        require(CloseHandle(handles[i]) != FALSE);
    }
    require(CloseHandle(start) != FALSE); require(CloseHandle(ready) != FALSE);
    printf("{\"mode\":\"concurrency\",\"checks\":%u,\"workers\":8,\"owner_lifetimes\":4096,\"named_variable_lifetimes\":8192,\"first_pool_use_concurrent\":true,\"shared_name_pointer_equal\":true}\n", checks);
}
int main(int argc, char** argv) {
    SetErrorMode(SEM_FAILCRITICALERRORS | SEM_NOGPFAULTERRORBOX);
    try {
        require(argc == 2);
        if (!strcmp(argv[1], "lifecycle")) lifecycle();
        else if (!strcmp(argv[1], "mutations")) mutationTests();
        else if (!strcmp(argv[1], "concurrency")) concurrency();
        else require(false);
        return 0;
    } catch (const std::exception& error) {
        allocationCountdown = -1; ThrowValue::countdown = -1;
        fprintf(stderr, "EXCEPTION|%s\n", error.what()); return 1;
    }
}
