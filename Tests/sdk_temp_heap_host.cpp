// Test-only executable host export. Allocation methods come from the SDK or
// candidate library, never from this adapter. The real engine must own this heap.
#include "SdkTempHeapIncludes.h"
static volatile LONG returnNull=0;
extern "C" void ZeroSisSdkTempHeapReturnNull(bool enabled) { InterlockedExchange(&returnNull,enabled?1:0); }
extern "C" __declspec(dllexport) TempHeap* ZeroSisSdkTempHeapHost() {
    if(InterlockedCompareExchange(&returnNull,0,0))return NULL;
    static TempHeap heap;
    return &heap;
}
#ifdef _WIN64
#pragma comment(linker,"/EXPORT:GetTempHeap=ZeroSisSdkTempHeapHost")
#else
#pragma comment(linker,"/EXPORT:GetTempHeap=_ZeroSisSdkTempHeapHost")
#endif
