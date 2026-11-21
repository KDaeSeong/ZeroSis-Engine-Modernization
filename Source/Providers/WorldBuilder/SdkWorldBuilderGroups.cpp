#include "SdkWorldBuilderIncludes.h"
#include <memory>

namespace {
void ValidateGroup(const char* data,uint size) {
    if(!data && size)throw std::invalid_argument("Null WorldBuilder group input");
    size_t offset=0;
    while(offset<size){const size_t length=static_cast<unsigned char>(data[offset]);
        if(length+2>size-offset || data[offset+1+length]!=0 || std::memchr(data+offset+1,0,length))
            throw std::invalid_argument("Malformed WorldBuilder group entry");
        offset+=length+2;
    }
}
}

CvWorldBuilderMapTypeGroup::CvWorldBuilderMapTypeGroup():m_szBuffer(NULL),m_uiBufferSize(0) {}
CvWorldBuilderMapTypeGroup::CvWorldBuilderMapTypeGroup(const CvWorldBuilderMapTypeGroup& other):m_szBuffer(NULL),m_uiBufferSize(0) {
    Deserialize(other.m_szBuffer,other.m_uiBufferSize);
}
CvWorldBuilderMapTypeGroup::~CvWorldBuilderMapTypeGroup(){delete[] m_szBuffer;}
const CvWorldBuilderMapTypeGroup& CvWorldBuilderMapTypeGroup::operator=(const CvWorldBuilderMapTypeGroup& other){
    if(this!=&other)Deserialize(other.m_szBuffer,other.m_uiBufferSize);return *this;
}
bool CvWorldBuilderMapTypeGroup::Contains(const char* name) const {
    if(!name || !*name)return false;
    for(size_t offset=0;offset<m_uiBufferSize;offset+=static_cast<unsigned char>(m_szBuffer[offset])+2u)
        if(std::strcmp(name,m_szBuffer+offset+1)==0)return true;
    return false;
}
void CvWorldBuilderMapTypeGroup::Add(const char* name) {
    if(!name || !*name)return;
    const size_t length=std::strlen(name);if(length>255 || Contains(name))return;
    if(length+2>std::numeric_limits<uint>::max()-m_uiBufferSize)throw std::length_error("WorldBuilder group too large");
    const uint size=m_uiBufferSize+static_cast<uint>(length+2);std::unique_ptr<char[]> replacement(new char[size]);
    if(m_uiBufferSize)std::memcpy(replacement.get(),m_szBuffer,m_uiBufferSize);
    replacement[m_uiBufferSize]=static_cast<char>(length);std::memcpy(replacement.get()+m_uiBufferSize+1,name,length+1);
    delete[] m_szBuffer;m_szBuffer=replacement.release();m_uiBufferSize=size;
}
void CvWorldBuilderMapTypeGroup::Remove(const char* name) {
    if(!name || !*name)return;
    for(size_t offset=0;offset<m_uiBufferSize;offset+=static_cast<unsigned char>(m_szBuffer[offset])+2u){
        if(std::strcmp(name,m_szBuffer+offset+1)!=0)continue;
        const size_t recordSize=static_cast<unsigned char>(m_szBuffer[offset])+2u;
        const uint size=m_uiBufferSize-static_cast<uint>(recordSize);
        // The search name may alias the old buffer; do not use it after mutation.
        std::memmove(m_szBuffer+offset,m_szBuffer+offset+recordSize,m_uiBufferSize-offset-recordSize);m_uiBufferSize=size;
        if(!size)Clear();return;
    }
}
void CvWorldBuilderMapTypeGroup::Clear(){delete[] m_szBuffer;m_szBuffer=NULL;m_uiBufferSize=0;}
void CvWorldBuilderMapTypeGroup::Serialize(void* output) const {
    if(!output && m_uiBufferSize)throw std::invalid_argument("Null WorldBuilder group output");
    if(m_uiBufferSize)std::memmove(output,m_szBuffer,m_uiBufferSize);
}
void CvWorldBuilderMapTypeGroup::Deserialize(const void* input,uint size) {
    const char* data=static_cast<const char*>(input);ValidateGroup(data,size);
    std::unique_ptr<char[]> candidate(size?new char[size]:NULL);if(size)std::memcpy(candidate.get(),data,size);
    delete[] m_szBuffer;m_szBuffer=candidate.release();m_uiBufferSize=size;
}
