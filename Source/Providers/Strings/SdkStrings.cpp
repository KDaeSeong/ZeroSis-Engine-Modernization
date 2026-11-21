#include "SdkStringIncludes.h"
#include <stdexcept>

namespace {
template<class Data, class C> struct EmptyStorage { Data header; C terminator; };
EmptyStorage<FStringA::FStringAData,char> emptyA={{0,0,0,1},0};
EmptyStorage<FStringW::FStringWData,wchar_t> emptyW={{0,0,0,1},0};
static_assert(sizeof(FStringA)==sizeof(void*) && sizeof(FStringW)==sizeof(void*),"SDK vararg ABI");
static_assert(sizeof(FStringA::FStringAData)==12 && sizeof(FStringW::FStringWData)==12,"SDK data ABI");

template<class Data> size_t Capacity(const Data* data) {
    // FixedBuffer<N> stores N characters total, despite the header's comment
    // describing a capacity that excludes the terminator. Never write at N.
    const size_t count=static_cast<size_t>(data->m_iAllocLength);
    return data->m_bFixed && count ? count-1 : count;
}
size_t Rounded(size_t length,size_t quantum) {
    if(length>INT_MAX)throw std::length_error("SDK string length exceeds int32");
    return (length+quantum)/quantum*quantum-1;
}
template<class Data,class C> Data* Allocate(size_t capacity) {
    if(capacity>INT_MAX)throw std::length_error("SDK string capacity exceeds int32");
    byte* bytes=new byte[sizeof(Data)+(capacity+1)*sizeof(C)];
    Data* data=new(bytes) Data();
    data->m_iAllocLength=static_cast<int>(capacity);
    data->StringData()[0]=0;
    return data;
}
template<class C> const C* StableSource(const C* source,int first,int count,
        const C* current,size_t capacity,size_t length,std::vector<C>& snapshot) {
    const ULONG_PTR start=reinterpret_cast<ULONG_PTR>(current);
    const ULONG_PTR address=reinterpret_cast<ULONG_PTR>(source);
    if(address>=start && address-start<=(capacity+1)*sizeof(C)) {
        const size_t delta=static_cast<size_t>(address-start);
        if(delta%sizeof(C))throw std::out_of_range("Unaligned SDK string alias");
        const size_t offset=delta/sizeof(C)+static_cast<size_t>(first);
        if(offset>length+1 || static_cast<size_t>(count)>length+1-offset)
            throw std::out_of_range("SDK string alias exceeds initialized data");
        snapshot.assign(current+offset,current+offset+count);
        return snapshot.data();
    }
    return source+first;
}
}

FStringA::FStringAData* FStringA_GetStringInitData() { return &emptyA.header; }
FStringW::FStringWData* FStringW_GetStringInitData() { return &emptyW.header; }

// The original inline destructors delete a byte array. Preserve that allocator
// boundary and prepare replacements before releasing either heap or fixed data.
#define SDK_STRING_MEMORY(Class,Data,C,Quantum) \
void Class::AllocBuffer(size_t count) { \
    if(!count)return; \
    Data* next=Allocate<Data,C>(count); Data* old=GetData(); \
    m_pszString=next->StringData(); Release(old); } \
void Class::Reallocate(size_t count) { \
    if(!count)return; \
    Data* old=GetData(); \
    if(count<static_cast<size_t>(old->m_iDataLength))throw std::length_error("SDK string reserve would truncate"); \
    Data* next=Allocate<Data,C>(count); \
    std::memcpy(next->StringData(),m_pszString,(static_cast<size_t>(old->m_iDataLength)+1)*sizeof(C)); \
    next->m_iDataLength=old->m_iDataLength; m_pszString=next->StringData(); Release(old); } \
void Class::SetLength(size_t length) { \
    if(IsLocked())throw std::logic_error("SDK string buffer is locked"); \
    if(length>INT_MAX)throw std::length_error("SDK string length exceeds int32"); \
    if(!length && !GetData()->m_iDataLength)return; \
    if(length>Capacity(GetData()))Reallocate(Rounded(length,Quantum)); \
    m_pszString[length]=0;GetData()->m_iDataLength=static_cast<int>(length); } \
void Class::Reserve(int length) { \
    if(length<0)return; \
    if(IsLocked())throw std::logic_error("SDK string buffer is locked"); \
    if(static_cast<size_t>(length)>Capacity(GetData()))Reallocate(Rounded(static_cast<size_t>(length),Quantum)); } \
C* Class::GetBuffer(int length) { \
    if(length<0)throw std::length_error("Negative SDK string buffer length"); \
    if(IsLocked())throw std::logic_error("SDK string buffer is already locked"); \
    Reserve(std::max(1,length)); LockBuffer();return m_pszString; } \
void Class::ReleaseBuffer(size_t length) { \
    if(!IsLocked())return; \
    const size_t capacity=Capacity(GetData()); UnlockBuffer(); \
    if(length==static_cast<size_t>(-1)) { \
        length=0;while(length<capacity && m_pszString[length])++length; \
    } else if(length>capacity) { \
        m_pszString[GetData()->m_iDataLength]=0; \
        throw std::length_error("SDK string release exceeds capacity"); \
    } \
    m_pszString[length]=0;GetData()->m_iDataLength=static_cast<int>(length); } \
void Class::Copy(int length,const C* source,int first) { \
    if(length<0 || first<0 || source==m_pszString)return; \
    if(!length || !source) { Empty();return; } \
    if(IsLocked())throw std::logic_error("SDK string buffer is locked"); \
    std::vector<C> snapshot;const C* stable=StableSource(source,first,length,m_pszString,Capacity(GetData()),static_cast<size_t>(GetLength()),snapshot); \
    SetLength(static_cast<size_t>(length));std::memmove(m_pszString,stable,static_cast<size_t>(length)*sizeof(C));m_pszString[length]=0; } \
void Class::SetAt(int index,int length,const C* source,int first) { \
    if(index<0 || length<=0 || first<0 || !source)return; \
    if(IsLocked())throw std::logic_error("SDK string buffer is locked"); \
    if(index>GetLength())return; \
    if(length>INT_MAX-index)throw std::length_error("SDK string append exceeds int32"); \
    std::vector<C> snapshot;const C* stable=StableSource(source,first,length,m_pszString,Capacity(GetData()),static_cast<size_t>(GetLength()),snapshot); \
    const int next=std::max(GetLength(),index+length);SetLength(static_cast<size_t>(next)); \
    std::memmove(m_pszString+index,stable,static_cast<size_t>(length)*sizeof(C));m_pszString[next]=0; } \
int Class::Replace(C from,C to) { \
    if(IsLocked())throw std::logic_error("SDK string buffer is locked"); \
    int count=0;for(int i=0;i<GetLength();++i)if(m_pszString[i]==from) { m_pszString[i]=to;++count; }return count; }

SDK_STRING_MEMORY(FStringA,FStringAData,char,32)
SDK_STRING_MEMORY(FStringW,FStringWData,wchar_t,16)
#undef SDK_STRING_MEMORY

void FStringA::Format(LPCSTR format,...) {
    va_list args;va_start(args,format);
    try { FormatV(format,args); } catch(...) { va_end(args);throw; }
    va_end(args);
}
void FStringA::FormatV(LPCSTR format,va_list args) {
    if(!format) { Empty();return; }
    va_list measure;va_copy(measure,args);const int count=_vscprintf(format,measure);va_end(measure);
    if(count<0)throw std::invalid_argument("Invalid SDK string format");
    std::vector<char> buffer(static_cast<size_t>(count)+1);
    va_list write;va_copy(write,args);const int actual=vsprintf_s(buffer.data(),buffer.size(),format,write);va_end(write);
    if(actual<0 || actual>count)throw std::runtime_error("SDK string formatting failed");
    // Legacy Format releases a nul-terminated buffer, so embedded NUL truncates.
    Copy(static_cast<int>(std::strlen(buffer.data())),buffer.data());
}

void FStringW::ExtractFileTitle(FStringW& destination,wchar_t delimiter) const {
    // The original returns the complete basename including extension. Its
    // attempted in-place Left() is a no-op because Copy(self) does nothing.
    // Preserve this observed map-name contract instead of silently changing it.
    const int length=GetLength();int start=0;
    const wchar_t* separator=std::wcsrchr(m_pszString,delimiter);
    if(!separator && length)separator=std::wcschr(m_pszString,L':');
    if(separator)start=static_cast<int>(std::min(static_cast<size_t>(length),static_cast<size_t>(separator-m_pszString)+1));
    FStringW prepared(m_pszString+start,length-start);destination=prepared;
}

void FStringW::CopyToUTF8(FStringA* output) const { CopyToUTF8(m_pszString,output); }
void FStringW::CopyToUTF8(LPCWSTR source,FStringA* output) {
    if(!output)return;
    if(!source || !source[0]) { output->Empty();return; }
    const int count=WideCharToMultiByte(CP_UTF8,0,source,-1,NULL,0,NULL,NULL);
    if(!count)throw std::runtime_error("SDK UTF-8 sizing failed");
    std::vector<char> buffer(static_cast<size_t>(count));
    if(WideCharToMultiByte(CP_UTF8,0,source,-1,buffer.data(),count,NULL,NULL)!=count)
        throw std::runtime_error("SDK UTF-8 conversion failed");
    output->Copy(count-1,buffer.data());
}

std::wstring CvStringUtils::FromUTF8ToUTF16(const std::string& source) {
    // Original utility uses a nul-terminated Windows conversion (flags = 0),
    // including replacement of malformed input and truncation at embedded NUL.
    const int count=MultiByteToWideChar(CP_UTF8,0,source.c_str(),-1,NULL,0);
    if(!count)throw std::runtime_error("SDK UTF-16 sizing failed");
    std::wstring result(static_cast<size_t>(count),L'\0');
    if(MultiByteToWideChar(CP_UTF8,0,source.c_str(),-1,&result[0],count)!=count)
        throw std::runtime_error("SDK UTF-16 conversion failed");
    result.resize(static_cast<size_t>(count-1));return result;
}
