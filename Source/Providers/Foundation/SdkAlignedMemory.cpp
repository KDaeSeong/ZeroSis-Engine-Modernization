#include "SdkFoundationIncludes.h"
#include <cerrno>

// This provider owns allocations in the shared /MD CRT domain. A future engine
// allocator must preserve ownership/free pairing; no legacy host heap is bound.
void* FireMallocAlignedNoTracking(size_t size,size_t alignment,const char*,int) {
    if(alignment&(alignment-1)) { errno=EINVAL; return NULL; }
    // VC9 accepts alignment zero as its native default and returns a freeable
    // block for size zero. Normalize before calling the newer CRT.
    if(!alignment)alignment=sizeof(void*);
    if(!size)size=1;
    const size_t actualAlignment=alignment<sizeof(void*)?sizeof(void*):alignment;
    if(size>static_cast<size_t>(-1)-actualAlignment-sizeof(void*)) { errno=ENOMEM; return NULL; }
    return _aligned_malloc(size,alignment);
}
void FireFreeAlignedNoTracking(void* memory) { _aligned_free(memory); }
