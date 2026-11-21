// Linked only into a separate fault-injection DLL; never the production provider.
#include <new>
#include <cstdlib>
#include "sqlite3.h"
namespace {
thread_local long long remaining=-1;
thread_local unsigned long attempts=0;
thread_local bool injected=false;
thread_local int faultKind=0;
sqlite3_mem_methods original={};
bool failAllocation(int kind) noexcept {
    ++attempts;if(remaining<0)return false;
    if(remaining--==0) { injected=true;faultKind=kind;remaining=-1;return true; }return false;
}
void* sqliteMalloc(int size) { return size>0&&failAllocation(2)?NULL:original.xMalloc(size); }
void* sqliteRealloc(void* p,int size) { return size>0&&failAllocation(2)?NULL:original.xRealloc(p,size); }
}
void* operator new(size_t size) { if(failAllocation(1))throw std::bad_alloc();void* p=std::malloc(size?size:1);if(!p)throw std::bad_alloc();return p; }
void* operator new[](size_t size) { return ::operator new(size); }
void operator delete(void* p) noexcept { std::free(p); }
void operator delete[](void* p) noexcept { std::free(p); }
void operator delete(void* p,size_t) noexcept { std::free(p); }
void operator delete[](void* p,size_t) noexcept { std::free(p); }
extern "C" __declspec(dllexport) int ZeroSisDatabaseFaultInitialize() {
    const int rc=sqlite3_config(SQLITE_CONFIG_GETMALLOC,&original);if(rc!=SQLITE_OK)return rc;
    sqlite3_mem_methods methods=original;methods.xMalloc=sqliteMalloc;methods.xRealloc=sqliteRealloc;
    return sqlite3_config(SQLITE_CONFIG_MALLOC,&methods);
}
extern "C" __declspec(dllexport) void ZeroSisDatabaseFaultArm(long long index) { remaining=index;attempts=0;injected=false;faultKind=0; }
extern "C" __declspec(dllexport) unsigned long ZeroSisDatabaseFaultDisarm() { remaining=-1;return attempts; }
extern "C" __declspec(dllexport) bool ZeroSisDatabaseFaultTriggered() { return injected; }
extern "C" __declspec(dllexport) int ZeroSisDatabaseFaultKind() { return faultKind; }
