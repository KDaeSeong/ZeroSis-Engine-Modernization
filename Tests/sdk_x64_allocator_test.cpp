#include <cassert>
#include <cstddef>
#include <cstdint>
#include <cstdlib>
#include <iostream>
#include <limits>
#include <stdexcept>
#include <vector>
#include "FireWorks/FBatchAllocate.h"

static_assert(sizeof(void*) == 8 && sizeof(std::size_t) == 8);
static_assert(sizeof(AllocData::nX) == 4 && sizeof(AllocData::nY) == 4);
static std::size_t checks = 0, layouts = 0, high_allocations = 0, rejected_overflows = 0;
static std::uintptr_t lowest_address = (std::numeric_limits<std::uintptr_t>::max)(), highest_address = 0;
static void require(bool condition, const char* message) {
    ++checks;
    if (!condition) throw std::runtime_error(message);
}

struct TrackedBase : FAllocBase<0, 0> {
    std::size_t bytes = 0;
    void* Alloc(std::size_t count, AllocData* descriptors) {
        bytes = count;
        return FAllocBase<0, 0>::Alloc(count, descriptors);
    }
};
template<class Allocator> struct Visible : Allocator {
    std::uintptr_t start() const { return reinterpret_cast<std::uintptr_t>(this->m_pData); }
    std::size_t size() const { return this->bytes; }
};
struct ThreeWords { std::uint32_t value[3]; };
static_assert(sizeof(ThreeWords) == 12);
template<class T> static T sample(unsigned i) { return static_cast<T>((i * 17 + 13) % 101); }
template<> ThreeWords sample<ThreeWords>(unsigned i) { return {{i + 1, i * 3 + 7, i * 5 + 11}}; }
template<class T> static bool equal(T a, T b) { return a == b; }
template<> bool equal(ThreeWords a, ThreeWords b) {
    return a.value[0] == b.value[0] && a.value[1] == b.value[1] && a.value[2] == b.value[2];
}
template<class Allocation> static void address_checks(const Allocation& block) {
    require(block.start() > (std::numeric_limits<std::uint32_t>::max)(), "allocation was not above 4 GiB");
    if (block.start() < lowest_address) lowest_address = block.start();
    if (block.start() > highest_address) highest_address = block.start();
    ++high_allocations;
}
template<class Allocation, class T> static void inside(const Allocation& block, T* pointer, std::size_t count) {
    const auto value = reinterpret_cast<std::uintptr_t>(pointer);
    require(value >= block.start() && value <= block.start() + block.size(), "pointer outside allocation");
    require(count * sizeof(T) <= block.start() + block.size() - value, "array extends beyond allocation");
    require(value % alignof(T) == 0, "array misaligned");
}

template<class T> static void one_dimensional() {
    for (unsigned count : {0U, 1U, 2U, 3U, 7U, 16U, 31U, 257U}) {
        Visible<FAllocArrayType<T, TrackedBase>> block;
        T* data = nullptr;
        AllocData descriptor{&data, count, 0};
        block.Alloc(&descriptor);
        address_checks(block);
        inside(block, data, count);
        require(reinterpret_cast<std::uintptr_t>(data) % sizeof(T) == 0, "legacy size-alignment formula not preserved");
        require(block.size() == sizeof(T) * (static_cast<std::size_t>(count) + 1), "1D byte count wrong");
        for (unsigned i = 0; i < count; ++i) data[i] = sample<T>(i);
        for (unsigned i = 0; i < count; ++i) require(equal(data[i], sample<T>(i)), "1D round trip failed");
        block.Free();
        require(block.start() == 0, "base pointer not cleared after free");
        ++layouts;
    }
}
template<class T> static void two_dimensional() {
    for (unsigned rows : {0U, 1U, 2U, 7U, 31U}) {
        for (unsigned columns : {0U, 1U, 3U, 8U, 29U}) {
            // Public outer 1D array delegates Free() to the protected 2D/base chain.
            Visible<FAllocArrayType<unsigned char, FAllocArray2DType<T, TrackedBase>>> block;
            unsigned char* prefix = nullptr; T** table = nullptr;
            AllocData descriptors[] = {{&prefix, 3, 0}, {&table, rows, columns}};
            block.Alloc(descriptors);
            address_checks(block);
            inside(block, prefix, 3); inside(block, table, rows);
            const std::size_t expected = 4 + sizeof(T*) * (static_cast<std::size_t>(rows) + 1)
                + sizeof(T) * rows * (static_cast<std::size_t>(columns) + 1);
            require(block.size() == expected, "2D byte count wrong");
            prefix[0] = 19; prefix[1] = 47; prefix[2] = 83;
            for (unsigned x = 0; x < rows; ++x) {
                inside(block, table[x], columns);
                if (x != 0) require(table[x] == table[0] + static_cast<std::size_t>(x) * columns, "row stride wrong");
                for (unsigned y = 0; y < columns; ++y) table[x][y] = sample<T>(x * 97 + y);
            }
            for (unsigned x = 0; x < rows; ++x)
                for (unsigned y = 0; y < columns; ++y)
                    require(equal(table[x][y], sample<T>(x * 97 + y)), "2D rows overlapped or data changed");
            require(prefix[0] == 19 && prefix[1] == 47 && prefix[2] == 83, "2D write corrupted another allocation");
            block.Free();
            require(block.start() == 0, "2D chain did not free base storage");
            ++layouts;
        }
    }
}
static void mixed_composites() {
    using Mixed = Visible<FAllocArrayType<int, FAllocArrayType<bool,
                  FAllocArrayType<ThreeWords, FAllocArray2DType<double, TrackedBase>>>>>;
    for (unsigned iteration = 0; iteration < 64; ++iteration) {
        int* integers = nullptr; bool* flags = nullptr; ThreeWords* records = nullptr; double** matrix = nullptr;
        const unsigned a = iteration + 1, b = iteration % 13 + 1, c = iteration % 11 + 1;
        const unsigned rows = iteration % 7 + 1, columns = iteration % 9 + 1;
        AllocData descriptors[] = {{&integers, a, 0}, {&flags, b, 0}, {&records, c, 0}, {&matrix, rows, columns}};
        Mixed block;
        block.Alloc(descriptors);
        address_checks(block);
        inside(block, integers, a); inside(block, flags, b); inside(block, records, c); inside(block, matrix, rows);
        for (unsigned i = 0; i < a; ++i) integers[i] = static_cast<int>(i) - 15;
        for (unsigned i = 0; i < b; ++i) flags[i] = (i % 2) != 0;
        for (unsigned i = 0; i < c; ++i) records[i] = sample<ThreeWords>(i);
        for (unsigned x = 0; x < rows; ++x) {
            inside(block, matrix[x], columns);
            for (unsigned y = 0; y < columns; ++y) matrix[x][y] = x * 100.0 + y;
        }
        for (unsigned i = 0; i < a; ++i) require(integers[i] == static_cast<int>(i) - 15, "mixed int corrupted");
        for (unsigned i = 0; i < b; ++i) require(flags[i] == ((i % 2) != 0), "mixed bool corrupted");
        for (unsigned i = 0; i < c; ++i) require(equal(records[i], sample<ThreeWords>(i)), "mixed record corrupted");
        for (unsigned x = 0; x < rows; ++x)
            for (unsigned y = 0; y < columns; ++y) require(matrix[x][y] == x * 100.0 + y, "mixed double corrupted");
        block.Free();
        require(block.start() == 0, "mixed base not freed");
        ++layouts;
    }
}
template<class Action> static void overflow(Action action) {
    bool caught = false;
    try { action(); } catch (const std::bad_array_new_length&) { caught = true; }
    require(caught, "size overflow was not rejected");
    ++rejected_overflows;
}
static void overflow_cases() {
    const auto maximum = (std::numeric_limits<std::size_t>::max)();
    using namespace FBatchAllocateDetail;
    require(Add(maximum, 0) == maximum && Multiply(maximum, 1) == maximum, "maximum valid size rejected");
    require(Multiply(maximum, 0) == 0 && Multiply(0, maximum) == 0, "zero multiplication wrong");
    require(Add(UINT64_C(0x100000000), 7) == UINT64_C(0x100000007), "byte count truncated above 4 GiB");
    overflow([&] { (void)Add(maximum, 1); });
    overflow([&] { (void)Multiply(maximum, 2); });
    Visible<FAllocArrayType<int, TrackedBase>> array;
    int sentinel = 55; int* output = &sentinel; AllocData descriptor{&output, 1, 0};
    overflow([&] { array.Alloc(maximum, &descriptor); });
    require(array.start() == 0 && output == &sentinel && sentinel == 55, "overflow published an allocation");
    Visible<FAllocArrayType<int, FAllocArray2DType<double, TrackedBase>>> matrix;
    double** table = nullptr;
    const auto dimensions_max = (std::numeric_limits<unsigned>::max)();
    AllocData descriptors[] = {{&output, 1, 0}, {&table, dimensions_max, dimensions_max}};
    overflow([&] { matrix.Alloc(descriptors); });
    require(matrix.start() == 0 && output == &sentinel && table == nullptr, "2D overflow changed outputs");
    // Failure leaves the allocator usable for a subsequent valid request.
    descriptors[1].nX = 2; descriptors[1].nY = 3;
    matrix.Alloc(descriptors);
    address_checks(matrix);
    output[0] = 7; table[1][2] = 9.0;
    require(output[0] == 7 && table[1][2] == 9.0, "allocator failed after rejected overflow");
    matrix.Free();
}
int main() {
    try {
        one_dimensional<unsigned char>(); one_dimensional<unsigned>();
        one_dimensional<double>(); one_dimensional<ThreeWords>();
        two_dimensional<unsigned char>(); two_dimensional<unsigned>();
        two_dimensional<double>(); two_dimensional<ThreeWords>();
        mixed_composites(); overflow_cases();
        std::cout << "{\"status\":\"PASS\",\"scope\":\"SDK_HEADER_ALLOCATOR_ONLY\",\"pointer_bytes\":" << sizeof(void*)
                  << ",\"checks_passed\":" << checks << ",\"layout_cases\":" << layouts
                  << ",\"allocations_above_4g\":" << high_allocations
                  << ",\"rejected_overflows\":" << rejected_overflows
                  << ",\"lowest_address\":\"0x" << std::hex << lowest_address
                  << "\",\"highest_address\":\"0x" << highest_address << "\"}\n";
        return 0;
    } catch (const std::exception& error) {
        std::cerr << "FAIL: " << error.what() << '\n';
        return 1;
    }
}
