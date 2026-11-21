#include "SdkWorldBuilderIncludes.h"
#include <map>
#include <mutex>

namespace {
// Case-insensitive type identity uses ASCII folding, preserving the spelling
// first inserted. UTF-8 bytes outside ASCII retain their exact identity.
const char* InternType(const char* text) {
    if(!text)return NULL;
    struct Palette { std::mutex mutex;std::map<std::string,std::string> values; };
    static Palette palette;
    std::string key(text);
    for(size_t i=0;i<key.size();++i)if(key[i]>='A' && key[i]<='Z')key[i]=static_cast<char>(key[i]-'A'+'a');
    std::lock_guard<std::mutex> guard(palette.mutex);
    const std::map<std::string,std::string>::iterator found=palette.values.find(key);
    if(found!=palette.values.end())return found->second.c_str();
    return palette.values.emplace(key,std::string(text)).first->second.c_str();
}
size_t AddSize(size_t lhs,size_t rhs) {
    if(rhs>std::numeric_limits<size_t>::max()-lhs)throw std::length_error("WorldBuilder type data too large");
    return lhs+rhs;
}
}

CvWorldBuilderMapTypeDesc::CvWorldBuilderMapTypeDesc() {}
CvWorldBuilderMapTypeDesc::String::String(const char* text):m_sz(InternType(text)) {}
const char* CvWorldBuilderMapTypeDesc::String::operator=(const char* text) {m_sz=InternType(text);return m_sz;}

bool CvWorldBuilderMapTypeDesc::TypeMap::FindType(const char* text,uint& result) const {
    const String sought(text);
    for(size_t i=0;i<asTypes.size();++i)if(asTypes[i]==sought){result=static_cast<uint>(i);return true;}
    return false;
}
const size_t CvWorldBuilderMapTypeDesc::TypeMap::GetSerializedSize() const {
    size_t total=0;
    for(size_t i=0;i<asTypes.size();++i){const char* s=asTypes[i];total=AddSize(total,s?AddSize(std::strlen(s),1):1);}
    return total;
}
const CvWorldBuilderMapTypeDesc::String& CvWorldBuilderMapTypeDesc::TypeMap::Get(uint index) const {
    static const String invalid;
    return index<asTypes.size()?asTypes[index]:invalid;
}
uint CvWorldBuilderMapTypeDesc::TypeMap::Add(const char* text) {return Add(String(text));}
uint CvWorldBuilderMapTypeDesc::TypeMap::Add(const String& text) {
    if(asTypes.size()>=std::numeric_limits<uint>::max())throw std::length_error("Too many WorldBuilder types");
    const uint index=static_cast<uint>(asTypes.size());asTypes.push_back(text);return index;
}
void CvWorldBuilderMapTypeDesc::TypeMap::Serialize(void* output) const {
    if(!output && !asTypes.empty())throw std::invalid_argument("Null WorldBuilder type output");
    char* next=static_cast<char*>(output);
    for(size_t i=0;i<asTypes.size();++i){const char* s=asTypes[i];const size_t length=s?std::strlen(s):0;
        if(length)std::memcpy(next,s,length);next[length]=0;next+=length+1;}
}
void CvWorldBuilderMapTypeDesc::TypeMap::Deserialize(void* input,size_t size) {
    if(!input && size)throw std::invalid_argument("Null WorldBuilder type input");
    TypeArray candidate;const char* next=static_cast<const char*>(input);size_t remaining=size;
    while(remaining){
        const char* end=static_cast<const char*>(std::memchr(next,0,remaining));
        if(!end)throw std::invalid_argument("Unterminated WorldBuilder type");
        if(candidate.size()>=std::numeric_limits<uint>::max())throw std::length_error("Too many WorldBuilder types");
        candidate.push_back(String(next));const size_t consumed=static_cast<size_t>(end-next)+1;next+=consumed;remaining-=consumed;
    }
    asTypes.swap(candidate);
}
