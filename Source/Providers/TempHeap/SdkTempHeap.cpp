#include "SdkTempHeapIncludes.h"

namespace {
const LONG kWriter = 1L << TempHeap::HeapLock::eWriteShift;
const LONG kMaxLeases = kWriter - 1;

LONG ReadWord(volatile LONG& word) { return InterlockedCompareExchange(&word, 0, 0); }
void Pause() { if (!SwitchToThread()) Sleep(0); }

class Writer {
public:
    explicit Writer(volatile LONG& word, bool wait) : word_(word) {
        while (InterlockedCompareExchange(&word_, kWriter, 0) != 0) {
            if (!wait) throw std::logic_error("TempHeap lifecycle has outstanding operations");
            Pause();
        }
    }
    ~Writer() { InterlockedExchange(&word_, 0); }
private:
    Writer(const Writer&);
    Writer& operator=(const Writer&);
    volatile LONG& word_;
};

bool AcquireLease(volatile LONG& word) {
    for (;;) {
        const LONG observed = ReadWord(word);
        if (observed & kWriter) { Pause(); continue; }
        if (observed < 0 || observed >= kMaxLeases) return false;
        if (InterlockedCompareExchange(&word, observed + 1, observed) == observed) return true;
    }
}

void ReleaseLease(volatile LONG& word, volatile LONG& offset) {
    for (;;) {
        const LONG observed = ReadWord(word);
        if (observed <= 0 || observed >= kWriter)
            throw std::logic_error("TempHeap release has no matching lease");
        // Transfer the final lease directly to the writer. Publishing zero first
        // would let a reader enter before the offset is reset. Only the thread
        // that wins this CAS owns the reset; seeing a writer bit is insufficient.
        const LONG replacement = observed == 1 ? kWriter : observed - 1;
        if (InterlockedCompareExchange(&word, replacement, observed) != observed) continue;
        if (replacement == kWriter) {
            InterlockedExchange(&offset, 0);
            InterlockedExchange(&word, 0);
        }
        return;
    }
}

// LONG stores the SDK's unsigned 32-bit offset bits. Do not overflow a signed
// expression or narrow a native pointer when the offset crosses 2 GiB.
LONG OffsetBits(uint value) { LONG bits; static_assert(sizeof(bits) == sizeof(value), "SDK offset width"); memcpy(&bits, &value, sizeof(bits)); return bits; }

typedef TempHeap* (__cdecl* HostHeapProc)();
HostHeapProc BindHostHeap() {
    HMODULE host = GetModuleHandleW(NULL);
    FARPROC address = host ? GetProcAddress(host, "GetTempHeap") : NULL;
    if (!address) throw std::runtime_error("Engine host must export GetTempHeap");
    HostHeapProc callback;
    static_assert(sizeof(callback) == sizeof(address), "Windows procedure pointer width");
    memcpy(&callback, &address, sizeof(callback));
    return callback;
}
}

TempHeap::TempHeap() : m_pMemHead(NULL), m_uiCurrentOffset(0), m_uiCapacity(0), m_dwFlags(0) {}
// The SDK has an explicit Startup/Shutdown lifecycle; its destructor is a no-op.
TempHeap::~TempHeap() {}

uint TempHeap::Startup(const uint bytes, byte* memory) {
    Writer writer(m_Lock.m_uiLock, false);
    if (m_pMemHead) throw std::logic_error("TempHeap requires Shutdown before another Startup");
    if (memory && (reinterpret_cast<ULONG_PTR>(memory) & 15))
        throw std::invalid_argument("TempHeap borrowed memory must be 16-byte aligned");
    byte* allocated = memory ? memory : static_cast<byte*>(FireMallocAlignedNoTracking(bytes, 4096, __FILE__, __LINE__));
    if (!allocated) return 0;
    m_pMemHead = allocated;
    m_uiCapacity = bytes;
    m_uiCurrentOffset = 0;
    m_dwFlags = memory ? 0 : eOwnsMemory;
    return bytes;
}

void TempHeap::Shutdown() {
    // The owner must stop new requests and return all leases before shutdown.
    // Waiting preserves the original SDK's outstanding-allocation contract.
    Writer writer(m_Lock.m_uiLock, true);
    if (m_dwFlags & eOwnsMemory) FireFreeAlignedNoTracking(m_pMemHead);
    m_pMemHead = NULL;
    m_uiCurrentOffset = 0;
    m_uiCapacity = 0;
    m_dwFlags = 0;
}

byte* TempHeap::Allocate(const uint bytes) {
    if (bytes > UINT_MAX - 15 || !AcquireLease(m_Lock.m_uiLock)) return NULL;
    const uint rounded = (bytes + 15) & ~15U;
    if (m_pMemHead) {
        for (;;) {
            const LONG bits = ReadWord(m_uiCurrentOffset);
            const uint offset = static_cast<uint>(bits);
            if (offset > m_uiCapacity || rounded > m_uiCapacity - offset) break;
            if (InterlockedCompareExchange(&m_uiCurrentOffset, OffsetBits(offset + rounded), bits) == bits)
                return m_pMemHead + static_cast<size_t>(offset);
        }
    }
    // A failed reservation owns a temporary lease too. Its final release must
    // reset the arena just like a successful allocation's final release.
    ReleaseLease(m_Lock.m_uiLock, m_uiCurrentOffset);
    return NULL;
}

void TempHeap::DeAllocate(const byte* memory) {
    if (!memory) return;
    const ULONG_PTR start = reinterpret_cast<ULONG_PTR>(m_pMemHead);
    const ULONG_PTR address = reinterpret_cast<ULONG_PTR>(memory);
    // Accept a zero-byte lease at one-past-end even though OwnsAllocation uses
    // the SDK's half-open range. The raw-pointer API cannot detect every double
    // return while other leases exist; callers must retain correct ownership.
    if (!start || address < start || address - start > m_uiCapacity || ((address - start) & 15))
        throw std::invalid_argument("TempHeap release is outside the arena or misaligned");
    ReleaseLease(m_Lock.m_uiLock, m_uiCurrentOffset);
}

BOOL TempHeap::OwnsAllocation(const byte* memory) const {
    const ULONG_PTR start = reinterpret_cast<ULONG_PTR>(m_pMemHead);
    const ULONG_PTR address = reinterpret_cast<ULONG_PTR>(memory);
    return start && address >= start && address - start < m_uiCapacity;
}

TempHeap* GetTempHeap() {
    static const HostHeapProc callback = BindHostHeap();
    TempHeap* heap = callback();
    if (!heap) throw std::runtime_error("Engine host GetTempHeap returned null");
    return heap;
}
