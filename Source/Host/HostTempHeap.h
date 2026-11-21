#pragma once
#include "SdkHostIncludes.h"
// FTempHeap's Windows atomics and dynamic host lookup use these SDK switches.
// Keep them local to this header instead of changing unrelated SDK declarations.
#pragma push_macro("_WINPC")
#pragma push_macro("FXS_IS_DLL")
#ifndef _WINPC
#define _WINPC
#endif
#ifndef FXS_IS_DLL
#define FXS_IS_DLL
#endif
#include <FireWorks/FTempHeap.h>
#pragma pop_macro("FXS_IS_DLL")
#pragma pop_macro("_WINPC")

namespace ZeroSisHost {
// The arena belongs to the host session, not a DLL static. GameCore's existing
// provider methods operate on this exact SDK layout through the exported pointer.
class HostTempHeap final {
    class Heap final : public TempHeap {
    public:
        bool IsIdle() noexcept {return InterlockedCompareExchange(&m_Lock.m_uiLock,0,0)==0;}
    } heap_;
public:
    ~HostTempHeap(){if(started_)std::terminate();}
    HostTempHeap()=default;
    HostTempHeap(const HostTempHeap&)=delete;
    HostTempHeap& operator=(const HostTempHeap&)=delete;
    void Start(){
        if(started_)throw std::logic_error("Host temporary heap is already started");
        constexpr unsigned capacity=16*1024*1024;
        if(heap_.Startup(capacity,nullptr)!=capacity)throw std::bad_alloc();
        TempHeap* expected=nullptr;
        if(!Current().compare_exchange_strong(expected,&heap_)){
            heap_.Shutdown();throw std::logic_error("Another host session owns the temporary heap");
        }
        started_=true;
    }
    void Close(){
        if(!started_)return;
        // The caller has already stopped/unloaded GameCore. Refuse outstanding
        // leases rather than blocking forever or freeing memory still in use.
        if(!heap_.IsIdle())throw std::logic_error("Host temporary heap still has outstanding allocations");
        TempHeap* expected=&heap_;
        if(!Current().compare_exchange_strong(expected,nullptr))throw std::logic_error("Host temporary heap owner differs");
        heap_.Shutdown();started_=false;
    }
    static TempHeap* Get() noexcept {return Current().load();}
private:
    static std::atomic<TempHeap*>& Current(){static std::atomic<TempHeap*> current{nullptr};return current;}
    bool started_=false;
};
}
extern "C" __declspec(dllexport) inline TempHeap* ZeroSisNativeHostTempHeap() noexcept {return ZeroSisHost::HostTempHeap::Get();}
#pragma comment(linker,"/EXPORT:GetTempHeap=ZeroSisNativeHostTempHeap")
