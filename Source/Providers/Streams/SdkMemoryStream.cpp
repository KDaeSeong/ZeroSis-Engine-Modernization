#include "SdkStreamIncludes.h"
#include <stdexcept>
#include <cstdint>

namespace {
unsigned int length(const char* first, const char* last) {
    if (!first) return 0;
    const size_t count = static_cast<size_t>(last - first);
    if (count > UINT_MAX) throw std::length_error("SDK stream exceeds uint32 length");
    return static_cast<unsigned int>(count);
}
void requireBuffer(unsigned int count, const void* data) {
    if (count && !data) throw std::invalid_argument("Null SDK stream buffer");
}
}

FMemoryStream::FMemoryStream() : FMemoryStream(2u, 0u, true, false) {}
FMemoryStream::FMemoryStream(bool grow) : FMemoryStream(2u, 0u, grow, false) {}
FMemoryStream::FMemoryStream(bool grow, bool minimal) : FMemoryStream(2u, 0u, grow, minimal) {}
FMemoryStream::FMemoryStream(uint pool, uint tag, bool grow, bool minimal)
    : m_pStart(nullptr), m_pData(nullptr), m_pStop(nullptr), m_pEndOfBuffer(nullptr),
      m_bRealloc(grow), m_bReallocMin(minimal), m_uMemoryPool(pool), m_uMemoryTag(tag) {}
FMemoryStream::FMemoryStream(int size, const void* data) : FMemoryStream(size,data,false,false) {}
FMemoryStream::FMemoryStream(int size, const void* data, bool grow) : FMemoryStream(size,data,grow,false) {}
FMemoryStream::FMemoryStream(int size, const void* data, bool grow, bool minimal)
    : FMemoryStream(size,data,2u,0u,grow,minimal) {}
FMemoryStream::FMemoryStream(int size, const void* data, uint pool, uint tag, bool grow, bool minimal)
    : FMemoryStream(pool,tag,grow,minimal) { Init(size,data,grow,minimal); }
FMemoryStream::FMemoryStream(const FMemoryStream& other)
    : FMemoryStream(other.m_uMemoryPool,other.m_uMemoryTag,true,other.m_bReallocMin) {
    WriteIt(other.GetEOF(),other.GetBuf());
}
FMemoryStream::~FMemoryStream() { Uninit(); }

void FMemoryStream::Init(int size, const void* data, bool grow) {
    if (size < 0) throw std::length_error("Negative SDK stream length");
    if (size && !data && !grow) throw std::invalid_argument("Fixed SDK stream needs storage");
    // grow=true adopts the supplied malloc-compatible storage, as the SDK does.
    // Allocate before discarding the old state so allocation failure is atomic.
    char* next = const_cast<char*>(static_cast<const char*>(data));
    const uintptr_t incoming=reinterpret_cast<uintptr_t>(next);
    const uintptr_t current=reinterpret_cast<uintptr_t>(m_pStart);
    if (m_bRealloc && next && m_pStart && incoming>current && incoming-current<length(m_pStart,m_pEndOfBuffer))
        throw std::invalid_argument("Cannot adopt interior of owned SDK stream buffer");
    if (!next && size) {
        next = static_cast<char*>(malloc(static_cast<size_t>(size)));
        if (!next) throw std::bad_alloc();
    }
    if (next && next == m_pStart) {
        // Re-adopting a live buffer must not free it or enlarge its allocation.
        if (static_cast<unsigned int>(size) > length(m_pStart,m_pEndOfBuffer))
            throw std::length_error("SDK stream reinitialization exceeds storage");
    } else {
        Uninit();
    }
    m_bRealloc = grow;
    m_pStart = m_pData = next;
    m_pStop = m_pEndOfBuffer = next ? next + size : nullptr;
    m_uiPosition = m_uiBytesRead = 0;
}
void FMemoryStream::Init(int size, const void* data, bool grow, bool minimal) {
    Init(size,data,grow); m_bReallocMin = minimal;
}
void FMemoryStream::Uninit() {
    if (m_bRealloc) free(m_pStart);
    m_pStart = m_pData = m_pStop = m_pEndOfBuffer = nullptr;
    m_uiPosition = m_uiBytesRead = 0;
}
void FMemoryStream::Grow(uint additional) {
    if (!m_bRealloc) return;
    const unsigned int capacity = length(m_pStart,m_pEndOfBuffer);
    const unsigned int used = GetEOF();
    if (additional > UINT_MAX - capacity) throw std::length_error("SDK stream growth overflow");
    const uint64_t required = static_cast<uint64_t>(capacity) + additional;
    const uint64_t proposed = m_bReallocMin && additional ? required : static_cast<uint64_t>(capacity)*2;
    const unsigned int nextSize = static_cast<unsigned int>(std::min<uint64_t>(UINT_MAX,std::max(required,proposed)));
    if (nextSize <= capacity) return;
    char* next = static_cast<char*>(malloc(nextSize));
    if (!next) throw std::bad_alloc();
    if (used) memcpy(next,m_pStart,used);
    free(m_pStart);
    m_pStart = next; m_pData = next + m_uiPosition; m_pStop = next + used; m_pEndOfBuffer = next + nextSize;
}
unsigned int FMemoryStream::ReadIt(unsigned int count, void* data) {
    requireBuffer(count,data);
    if (count > GetSizeLeft()) throw std::out_of_range("SDK stream read past end");
    if (count) { memcpy(data,m_pData,count); m_pData += count; }
    m_uiPosition += count; m_uiBytesRead += count;
    return count;
}
unsigned int FMemoryStream::WriteIt(unsigned int count, const void* data) {
    requireBuffer(count,data);
    if (count > UINT_MAX - m_uiPosition) throw std::length_error("SDK stream write overflow");
    const unsigned int required = m_uiPosition + count;
    const unsigned int capacity = length(m_pStart,m_pEndOfBuffer);
    // Own-buffer copies must survive growth, and overlapping copies use memmove.
    const uintptr_t address = reinterpret_cast<uintptr_t>(data);
    const uintptr_t base = reinterpret_cast<uintptr_t>(m_pStart);
    const bool internal = count && m_pStart && address >= base && address-base < capacity;
    const size_t sourceOffset = internal ? address-base : 0;
    if (internal && count > capacity-sourceOffset) throw std::out_of_range("SDK stream source range");
    if (required > capacity) {
        if (!m_bRealloc) throw std::out_of_range("Fixed SDK stream write past end");
        Grow(required-capacity);
    }
    if (count) {
        memmove(m_pData,internal ? m_pStart+sourceOffset : data,count);
        m_pData += count;
        if (m_pData > m_pStop) m_pStop = m_pData;
    }
    m_uiPosition = required; m_uiBytesRead += count;
    return count;
}
void FMemoryStream::Skip(unsigned int count) {
    if (count > GetSizeLeft()) throw std::out_of_range("SDK stream skip past end");
    if (count) m_pData += count;
    m_uiPosition += count; m_uiBytesRead += count;
}
void FMemoryStream::Rewind() { m_pData=m_pStart; m_uiPosition=m_uiBytesRead=0; }
bool FMemoryStream::AtEnd() const { return m_uiPosition >= GetEOF(); }
void FMemoryStream::FastFwd() { m_pData=m_pStop; m_uiPosition=m_uiBytesRead=GetEOF(); }
void FMemoryStream::Truncate() { m_pStop=m_pStart; Rewind(); }
unsigned int FMemoryStream::GetEOF() const { return length(m_pStart,m_pStop); }
void FMemoryStream::CopyToMem(void* data) {
    const unsigned int count=GetSizeLeft(); requireBuffer(count,data);
    if (count) memmove(data,m_pData,count);
}
char* FMemoryStream::GetBuf() { return m_pStart; }
const char* FMemoryStream::GetBuf() const { return m_pStart; }
FMemoryStream& FMemoryStream::operator=(const FMemoryStream& other) {
    if (this == &other) return *this;
    const unsigned int size=other.GetEOF();
    if (!m_bRealloc && size > length(m_pStart,m_pEndOfBuffer))
        throw std::out_of_range("Fixed SDK stream assignment past end");
    // Prepare owned bytes first; preserve destination options and endianness.
    if (m_bRealloc) {
        FMemoryStream prepared(m_uMemoryPool,m_uMemoryTag,true,m_bReallocMin);
        prepared.WriteIt(size,other.GetBuf());
        std::swap(m_pStart,prepared.m_pStart); std::swap(m_pData,prepared.m_pData);
        std::swap(m_pStop,prepared.m_pStop); std::swap(m_pEndOfBuffer,prepared.m_pEndOfBuffer);
        m_uiPosition=m_uiBytesRead=size;
    } else {
        Truncate(); WriteIt(size,other.GetBuf());
    }
    return *this;
}
