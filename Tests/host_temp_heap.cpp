#include "HostTempHeap.h"
#include <cstdio>
#include <cstring>
#include <stdexcept>
#include <vector>

namespace {
using ZeroSisHost::HostTempHeap;
int checks=0;

void Require(bool condition,const char* message){
    ++checks;
    if(!condition)throw std::runtime_error(message);
}

template<typename Exception,typename Function>
void RequireThrows(Function&& function,const char* message){
    bool caught=false;
    try{function();}
    catch(const Exception&){caught=true;}
    Require(caught,message);
}

using HostHeapExport=TempHeap* (__cdecl*)();

HostHeapExport ResolveExport(){
    HMODULE module=GetModuleHandleW(nullptr);
    Require(module!=nullptr,"Main executable module is unavailable");
    FARPROC address=GetProcAddress(module,"GetTempHeap");
    Require(address!=nullptr,"GetTempHeap executable export is missing");
    HostHeapExport result=nullptr;
    static_assert(sizeof(result)==sizeof(address),"Windows function pointer width differs");
    std::memcpy(&result,&address,sizeof(result));
    return result;
}

class OwnerCleanup final {
public:
    HostTempHeap owner;
    bool active=false;
    std::vector<byte*> leases;

    void Start(){owner.Start();active=true;}
    byte* Allocate(unsigned bytes){
        TempHeap* heap=HostTempHeap::Get();
        Require(heap!=nullptr,"Owner heap is unavailable");
        byte* memory=heap->Allocate(bytes);
        if(memory)leases.push_back(memory);
        return memory;
    }
    void DeAllocate(byte* memory){
        Require(active && memory!=nullptr,"Cannot release an untracked heap lease");
        TempHeap* heap=HostTempHeap::Get();
        Require(heap!=nullptr,"Owner heap disappeared before lease release");
        heap->DeAllocate(memory);
        for(auto item=leases.begin();item!=leases.end();++item){
            if(*item==memory){leases.erase(item);return;}
        }
        throw std::logic_error("Test lease tracking differs");
    }
    void Close(){owner.Close();active=false;leases.clear();}
    ~OwnerCleanup(){
        if(!active)return;
        TempHeap* heap=HostTempHeap::Get();
        if(heap){
            for(byte* memory:leases){
                try{heap->DeAllocate(memory);}catch(...){ }
            }
        }
        try{owner.Close();}catch(...){ }
    }
    OwnerCleanup()=default;
    OwnerCleanup(const OwnerCleanup&)=delete;
    OwnerCleanup& operator=(const OwnerCleanup&)=delete;
};

void TestSessionLifecycle(){
    OwnerCleanup first;
    OwnerCleanup second;
    const HostHeapExport exported=ResolveExport();
    Require(exported()==nullptr,"Export did not return null before session start");
    Require(ZeroSisHost::HostTempHeap::Get()==nullptr,"Host owner was non-null before session start");
    RequireThrows<std::runtime_error>([]{(void)GetTempHeap();},"SDK provider accepted a null host heap");

    first.Start();
    TempHeap* firstHeap=first.owner.Get();
    Require(firstHeap!=nullptr && exported()==firstHeap,"Executable export did not return the active SDK heap");
    Require(GetTempHeap()==firstHeap,"SDK provider did not resolve the active host heap");
    RequireThrows<std::logic_error>([&]{first.Start();},"A started owner accepted a second Start");
    Require(HostTempHeap::Get()==firstHeap,"Rejected repeated Start changed the active owner");

    RequireThrows<std::logic_error>([&]{second.Start();},"A second simultaneous owner was accepted");
    Require(HostTempHeap::Get()==firstHeap,
        "Rejected second owner replaced the active heap");
    Require(GetTempHeap()==firstHeap,"Provider stopped resolving the first owner after conflict");

    TempHeap* providerHeap=GetTempHeap();
    byte* lease=providerHeap->Allocate(37);
    Require(lease!=nullptr && providerHeap->OwnsAllocation(lease),"Provider allocation did not use the host arena");
    for(unsigned i=0;i<37;++i)lease[i]=static_cast<byte>(i*13+0x80);
    first.leases.push_back(lease);
    RequireThrows<std::logic_error>([&]{first.Close();},"Close accepted an outstanding allocation");
    Require(first.owner.Get()==firstHeap && HostTempHeap::Get()==firstHeap,
        "Failed Close detached the active owner");
    for(unsigned i=0;i<37;++i)Require(lease[i]==static_cast<byte>(i*13+0x80),"Failed Close damaged outstanding memory");
    first.DeAllocate(lease);

    byte* zero=providerHeap->Allocate(0);
    Require(zero!=nullptr,"Zero-byte allocation did not create a lease");
    first.leases.push_back(zero);
    RequireThrows<std::logic_error>([&]{first.Close();},"Close accepted a zero-byte lease");
    Require(first.owner.Get()==firstHeap && exported()==firstHeap,
        "Zero-byte lease Close failure changed the owner");
    first.DeAllocate(zero);

    first.Close();
    Require(HostTempHeap::Get()==nullptr && exported()==nullptr,"Successful Close did not clear the export");
    RequireThrows<std::runtime_error>([]{(void)GetTempHeap();},"SDK provider returned a closed heap");
    first.Close();

    first.Start();
    TempHeap* restarted=HostTempHeap::Get();
    Require(restarted!=nullptr && exported()==restarted,"Same owner could not restart after Close");
    first.Close();
    Require(exported()==nullptr,"Restarted owner did not close cleanly");

    second.Start();
    TempHeap* nextSession=GetTempHeap();
    Require(nextSession!=nullptr && exported()==nextSession,"Next owner session did not start");
    byte* nextLease=nextSession->Allocate(9);
    Require(nextLease!=nullptr && nextSession->OwnsAllocation(nextLease),"Next session SDK allocation failed");
    nextSession->DeAllocate(nextLease);
    second.Close();
    Require(HostTempHeap::Get()==nullptr && exported()==nullptr,"Next session did not close cleanly");
}
}

int main(){
    try{
        TestSessionLifecycle();
        std::printf("HOST_TEMP_HEAP_PASS checks=%d GETPROC_EXPORT=true PROVIDER_ROUNDTRIP=true GAMECORE_LOADED=false\n",checks);
        return 0;
    }catch(const std::exception& error){
        std::fprintf(stderr,"HOST_TEMP_HEAP_FAIL checks=%d reason=%s\n",checks,error.what());
        return 1;
    }
}
