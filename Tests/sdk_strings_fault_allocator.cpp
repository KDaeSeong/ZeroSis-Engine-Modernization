// Test executable only: production provider objects are linked unchanged.
#include <new>
#include <cstdlib>
namespace { long long remaining=-1; bool triggered=false; long long live=0; }
void* operator new(size_t size) {
    if(remaining>=0 && remaining--==0) { triggered=true;remaining=-1;throw std::bad_alloc(); }
    void* p=std::malloc(size?size:1);if(!p)throw std::bad_alloc();++live;return p;
}
void* operator new[](size_t size) { return ::operator new(size); }
void operator delete(void* p) noexcept { if(p) { --live;std::free(p); } }
void operator delete[](void* p) noexcept { ::operator delete(p); }
void operator delete(void* p,size_t) noexcept { ::operator delete(p); }
void operator delete[](void* p,size_t) noexcept { ::operator delete(p); }
void ArmStringsFault(long long index) { remaining=index;triggered=false; }
bool DisarmStringsFault() { remaining=-1;return triggered; }
long long LiveStringsAllocations() { return live; }
