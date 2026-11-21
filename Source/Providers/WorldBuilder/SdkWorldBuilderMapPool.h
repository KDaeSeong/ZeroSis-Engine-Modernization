#pragma once
#include "SdkWorldBuilderMapIncludes.h"

// Access declarations do not add SDK fields. Native pool bytes are never a
// portable file representation; the file bridge must encode fields explicitly.
struct ZeroSisWorldBuilderMapPoolAccess {
    template<class H> static H Handle(word value) { return H(value); }
    template<class T,uint N> static std::vector<byte> Allocated(const CvWorldBuilderMapElementAllocator<T,N>& p) {
        if(p.m_uiSize>65535u || ((p.m_uiSize!=0)!=(p.m_aData!=NULL)))throw std::logic_error("Invalid WorldBuilder pool storage");
        std::vector<byte> used(p.m_uiSize,1);
        int next=p.m_iFreeList;
        while(next!=-1){
            if(next<0 || static_cast<uint>(next)>=p.m_uiSize || !used[next])throw std::logic_error("Invalid WorldBuilder pool free chain");
            used[next]=0;next=p.m_aData[next].iNextFreeEntry;
        }
        return used;
    }
    template<class T,uint N> static typename CvWorldBuilderMapElementAllocator<T,N>::Handle Allocate(CvWorldBuilderMapElementAllocator<T,N>& p) {
        // The SDK's public allocator doubles to 65536, which truncates a 16-bit
        // handle. This map-owned boundary caps growth before calling that code.
        if(p.m_iFreeList<0){
            if(p.m_uiSize>=65535u)return CvWorldBuilderMapElementAllocator<T,N>::Handle::InvalidHandle();
            const uint next=p.m_uiSize?std::min(p.m_uiSize*2u,65535u):std::min(N,65535u);
            if(!p.Grow(next))return CvWorldBuilderMapElementAllocator<T,N>::Handle::InvalidHandle();
        }
        return p.Alloc();
    }
    template<class T,uint N> static T* At(CvWorldBuilderMapElementAllocator<T,N>& p,word index) { return p[Handle<typename CvWorldBuilderMapElementAllocator<T,N>::Handle>(index)]; }
};
