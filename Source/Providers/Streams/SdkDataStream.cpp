#include "SdkStreamIncludes.h"
#include <stdexcept>
#include <memory>

FEndian::EEndianness FEndian::ms_eTargetEndianness = FEndian::ENDIAN_LITTLE;
FEndian::EEndianness FEndian::GetEndianness() { return ENDIAN_LITTLE; }
FDataStream::FDataStream() : m_bEnableCB(true),m_eEndianness(FEndian::ENDIAN_LITTLE),m_uiBytesRead(0),m_uiPosition(0) {}
FDataStream::~FDataStream() {}
unsigned int FDataStream::GetBytesUsed() const { return m_uiBytesRead; }
unsigned int FDataStream::GetPosition() const { return m_uiPosition; }
void FDataStream::SetPosition(unsigned int position) {
    if (position > GetEOF()) throw std::out_of_range("SDK stream seek past end");
    Rewind(); Skip(position);
}
void FDataStream::Truncate() {}
void FDataStream::Flush() {}
unsigned int FDataStream::GetEOF() const { return 0; }
unsigned int FDataStream::GetSizeLeft() const {
    const unsigned int eof=GetEOF(), position=GetPosition();
    if (position > eof) throw std::out_of_range("Invalid SDK stream position");
    return eof-position;
}
void FDataStream::CopyToMem(void*) {}
void FDataStream::RaiseException(std::exception& error) const { throw error; }

namespace {
template<class T> void writeScalar(FDataStream& s, const T& value, bool swap) {
    T copy=value;
    if (swap && s.GetDesiredEndianNess()!=FEndian::ENDIAN_LITTLE) {
        unsigned char* bytes=reinterpret_cast<unsigned char*>(&copy);
        std::reverse(bytes,bytes+sizeof(T));
    }
    if (s.WriteIt(sizeof(T),&copy)!=sizeof(T)) throw std::runtime_error("Short SDK stream write");
}
template<class T> void readScalar(FDataStream& s, T& value, bool swap) {
    T copy;
    if (s.ReadIt(sizeof(T),&copy)!=sizeof(T)) throw std::runtime_error("Short SDK stream read");
    if (swap && s.GetDesiredEndianNess()!=FEndian::ENDIAN_LITTLE) {
        unsigned char* bytes=reinterpret_cast<unsigned char*>(&copy);
        std::reverse(bytes,bytes+sizeof(T));
    }
    value=copy;
}
unsigned int stringCount(size_t count) {
    if (count > INT_MAX) throw std::length_error("SDK string exceeds int32 count");
    return static_cast<unsigned int>(count);
}
template<class C> unsigned int writeText(FDataStream& s, const C* text, size_t length) {
    const unsigned int count=stringCount(length);
    if (count > UINT_MAX/sizeof(C)) throw std::length_error("SDK string byte count overflow");
    s << count;
    const unsigned int byteCount=static_cast<unsigned int>(count*sizeof(C));
    if (s.WriteIt(byteCount,text)!=byteCount) throw std::runtime_error("Short SDK string write");
    return count;
}
template<class C> unsigned int readText(FDataStream& s, std::basic_string<C>& text) {
    unsigned int count=0; s >> count;
    if (count > INT_MAX || count > UINT_MAX/sizeof(C)) throw std::length_error("Invalid SDK string count");
    const unsigned int byteCount=static_cast<unsigned int>(count*sizeof(C));
    if (byteCount > s.GetSizeLeft()) throw std::out_of_range("SDK string extends past end");
    std::basic_string<C> next(count,C());
    if (byteCount && s.ReadIt(byteCount,&next[0])!=byteCount) throw std::runtime_error("Short SDK string read");
    text.swap(next);
    return count;
}
}

// Reference evidence: UINT64 and GUID remain native-order even for big-endian
// streams; signed INT64 swaps. Wide string payloads also remain native-order.
#define SDK_SCALAR(Type, Swap) \
    void FDataStream::Write(const Type& value) { writeScalar(*this,value,Swap); } \
    void FDataStream::Read(Type& value) { readScalar(*this,value,Swap); }
SDK_SCALAR(char,false)
SDK_SCALAR(unsigned char,false)
SDK_SCALAR(INT16,true)
SDK_SCALAR(UINT16,true)
SDK_SCALAR(WCHAR,true)
SDK_SCALAR(INT32,true)
SDK_SCALAR(UINT32,true)
SDK_SCALAR(unsigned long,true)
SDK_SCALAR(INT64,true)
SDK_SCALAR(UINT64,false)
SDK_SCALAR(float,true)
SDK_SCALAR(double,true)
SDK_SCALAR(GUID,false)
#undef SDK_SCALAR
void FDataStream::Write(const bool& value) { const unsigned char byte=value?1:0; writeScalar(*this,byte,false); }
void FDataStream::Read(bool& value) {
    unsigned char byte=0; readScalar(*this,byte,false);
    if (byte>1) throw std::invalid_argument("Noncanonical SDK boolean");
    value=byte!=0;
}

#define SDK_ARRAY(Type) \
    void FDataStream::Write(int count,const Type* values) { \
        if (count<0 || (count && !values)) throw std::invalid_argument("Invalid SDK array"); \
        for (int i=0;i<count;++i) Write(values[i]); } \
    void FDataStream::Read(int count,Type* values) { \
        if (count<0 || (count && !values)) throw std::invalid_argument("Invalid SDK array"); \
        for (int i=0;i<count;++i) Read(values[i]); }
SDK_ARRAY(INT16)
SDK_ARRAY(UINT16)
SDK_ARRAY(WCHAR)
SDK_ARRAY(INT32)
SDK_ARRAY(UINT32)
SDK_ARRAY(unsigned long)
SDK_ARRAY(INT64)
SDK_ARRAY(UINT64)
SDK_ARRAY(float)
SDK_ARRAY(double)
SDK_ARRAY(GUID)
SDK_ARRAY(std::string)
SDK_ARRAY(std::wstring)
#undef SDK_ARRAY

unsigned int FDataStream::WriteString(const char* value) {
    if (!value) throw std::invalid_argument("Null SDK string");
    return writeText(*this,value,strlen(value));
}
unsigned int FDataStream::WriteString(const wchar* value) {
    if (!value) throw std::invalid_argument("Null SDK wide string");
    return writeText(*this,value,wcslen(value));
}
#define SDK_STRING(Type) \
    unsigned int FDataStream::WriteString(const Type& value) { return writeText(*this,value.data(),value.size()); } \
    unsigned int FDataStream::ReadString(Type& value) { return readText(*this,value); } \
    void FDataStream::Write(const Type& value) { WriteString(value); } \
    void FDataStream::Read(Type& value) { ReadString(value); } \
    unsigned int FDataStream::WriteString(int count,const Type* values) { \
        if (count<0 || (count && !values)) throw std::invalid_argument("Invalid SDK string array"); \
        unsigned int total=0; for(int i=0;i<count;++i) { const unsigned int n=WriteString(values[i]); \
            if(n>UINT_MAX-total) throw std::length_error("SDK string total overflow"); total+=n; } return total; } \
    unsigned int FDataStream::ReadString(int count,Type* values) { \
        if (count<0 || (count && !values)) throw std::invalid_argument("Invalid SDK string array"); \
        unsigned int total=0; for(int i=0;i<count;++i) { const unsigned int n=ReadString(values[i]); \
            if(n>UINT_MAX-total) throw std::length_error("SDK string total overflow"); total+=n; } return total; }
SDK_STRING(std::string)
SDK_STRING(std::wstring)
#undef SDK_STRING
unsigned int FDataStream::ReadString(char* value) {
    if (!value) throw std::invalid_argument("Null SDK string output");
    std::string text; const unsigned int count=readText(*this,text);
    memcpy(value,text.c_str(),text.size()+1); return count;
}
unsigned int FDataStream::ReadString(wchar* value) {
    if (!value) throw std::invalid_argument("Null SDK wide output");
    std::wstring text; const unsigned int count=readText(*this,text);
    memcpy(value,text.c_str(),(text.size()+1)*sizeof(wchar)); return count;
}
char* FDataStream::ReadString() {
    std::string text; readText(*this,text); std::unique_ptr<char[]> copy(new char[text.size()+1]);
    memcpy(copy.get(),text.c_str(),text.size()+1); return copy.release();
}
wchar* FDataStream::ReadWideString() {
    std::wstring text; readText(*this,text); std::unique_ptr<wchar[]> copy(new wchar[text.size()+1]);
    memcpy(copy.get(),text.c_str(),(text.size()+1)*sizeof(wchar)); return copy.release();
}
FDataStream& operator<<(FDataStream& to,FDataStream& from) {
    if (&to==&from) throw std::invalid_argument("Cannot stream into itself");
    while (!from.AtEnd()) { unsigned char byte=0; from>>byte; to<<byte; }
    return to;
}
FDataStream& operator>>(FDataStream& from,FDataStream& to) { to<<from; return from; }
