#include "SdkStringIncludes.h"
#include <stdexcept>
void ArmStringsFault(long long);
bool DisarmStringsFault();
long long LiveStringsAllocations();
static unsigned checks=0;
#define CHECK(x) do { ++checks;if(!(x)) { std::fprintf(stderr,"FAIL|%u|%d|%s\n",checks,__LINE__,#x);std::exit(2); } } while(0)
class ProbeA:public FStringA { public:using FStringA::GetBuffer;using FStringA::ReleaseBuffer;using FStringA::SetLength;using FStringA::Reallocate;using FStringA::IsLocked; };
class ProbeW:public FStringW { public:using FStringW::GetBuffer;using FStringW::ReleaseBuffer;using FStringW::SetLength;using FStringW::Reallocate;using FStringW::IsLocked; };
template<class F> static void Reject(F operation) {
    bool rejected=false;try { operation(); }catch(const std::exception&) { rejected=true; }CHECK(rejected);
}
template<class S,class C> static void CheckValue(const S& value,const std::basic_string<C>& expected) {
    CHECK(value.GetLength()==static_cast<int>(expected.size()));
    CHECK(!std::memcmp(value.c_str(),expected.c_str(),(expected.size()+1)*sizeof(C)));
}
static void Boundaries() {
    ProbeA a;ProbeW w;a.Copy(6,"abcdef");w.Copy(6,L"abcdef");
    Reject([&]{a.SetLength(static_cast<size_t>(INT_MAX)+1);});Reject([&]{w.SetLength(static_cast<size_t>(-1));});
    Reject([&]{a.Reallocate(2);});Reject([&]{w.Reallocate(2);});
    Reject([&]{a.SetAt(6,INT_MAX,"x");});Reject([&]{w.SetAt(6,INT_MAX,L"x");});
    Reject([&]{a.Copy(6,a.c_str()+3);});Reject([&]{w.Copy(6,w.c_str()+3);});
    Reject([&]{a.GetBuffer(-1);});Reject([&]{w.GetBuffer(-1);});
    CheckValue(a,std::string("abcdef"));CheckValue(w,std::wstring(L"abcdef"));
    a.Copy(3,a.c_str()+1);w.Copy(3,w.c_str()+1);CheckValue(a,std::string("bcd"));CheckValue(w,std::wstring(L"bcd"));
    a.Reserve(1);w.Reserve(1);CheckValue(a,std::string("bcd"));CheckValue(w,std::wstring(L"bcd"));
    char* buffer=a.GetBuffer(32);wchar_t* wbuffer=w.GetBuffer(32);
    Reject([&]{a.GetBuffer(1);});Reject([&]{w.GetBuffer(1);});
    Reject([&]{a.SetAt(0,1,"x");});Reject([&]{w.SetAt(0,1,L"x");});
    std::memcpy(buffer,"new",4);std::memcpy(wbuffer,L"new",4*sizeof(wchar_t));a.ReleaseBuffer();w.ReleaseBuffer();
    CheckValue(a,std::string("new"));CheckValue(w,std::wstring(L"new"));
    a.GetBuffer(1);w.GetBuffer(1);
    Reject([&]{a.ReleaseBuffer(static_cast<size_t>(INT_MAX)+1);});Reject([&]{w.ReleaseBuffer(static_cast<size_t>(INT_MAX)+1);});
    CHECK(!a.IsLocked() && !w.IsLocked());CheckValue(a,std::string("new"));CheckValue(w,std::wstring(L"new"));
    // GetBuffer(0) must not lend the global empty singleton for writable access.
    ProbeA empty,other;char* writable=empty.GetBuffer(0);writable[0]='x';writable[1]=0;empty.ReleaseBuffer();
    CheckValue(empty,std::string("x"));CheckValue(other,std::string());
    // A missing NUL is bounded by actual capacity, never an unbounded strlen.
    buffer=a.GetBuffer(31);const FStringA::FStringAData* data=reinterpret_cast<const FStringA::FStringAData*>(buffer)-1;
    std::memset(buffer,'k',static_cast<size_t>(data->m_iAllocLength)+1);const int capacity=data->m_iAllocLength;a.ReleaseBuffer();
    CheckValue(a,std::string(static_cast<size_t>(capacity),'k'));
    FStringW path(L"C:\\dir\\file.ext");path.ExtractFileTitle(path);CheckValue(path,std::wstring(L"file.ext"));
    FStringA formatted("%s/%d");formatted.Format(formatted.c_str(),"self",9);CheckValue(formatted,std::string("self/9"));
    std::string longText(16384,'z');formatted.Format("%s",longText.c_str());CheckValue(formatted,longText);
    std::printf("BOUNDARIES|16_rejections|alias|reserve|locks|empty_owner|bounded_release|long_format\n");
}
static void Streams() {
    FMemoryStream encoded;FStringA payload("a\0b",3);encoded<<payload;
    unsigned rejected=0;
    for(unsigned n=0;n<encoded.GetEOF();++n) {
        FMemoryStream truncated(static_cast<int>(n),encoded.GetBuf());FStringA destination("preserved");
        Reject([&]{truncated>>destination;});CheckValue(destination,std::string("preserved"));++rejected;
    }
    FMemoryStream invalid;invalid<<0xffffffffu;invalid.Rewind();FStringA destination("preserved");
    Reject([&]{invalid>>destination;});CheckValue(destination,std::string("preserved"));++rejected;
    for(unsigned size=0;size<7;++size) {
        char data[7]={};FMemoryStream fixed(static_cast<int>(size),data);
        Reject([&]{fixed<<payload;});++rejected;
    }
    std::printf("STREAM_REJECTIONS|%u\n",rejected);
}
static void Faults() {
    unsigned failures=0,successes=0;
    for(unsigned kind=0;kind<15;++kind) {
        bool success=false;
        for(unsigned index=0;index<16 && !success;++index) {
            const long long beforeScope=LiveStringsAllocations();bool failed=false,injected=false;
            {
                const std::string large(4096,'k');const std::wstring wideLarge(4096,0xd55c);
                FStringA a("abcdefghijklmnopqrstuvwxyz12345");FStringW w(L"abcdefghijklmnopqrstuvwxyz12345");
                const std::string savedA(a.c_str(),static_cast<size_t>(a.GetLength()));const std::wstring savedW(w.c_str(),static_cast<size_t>(w.GetLength()));
                const char* oldA=a.c_str();const wchar_t* oldW=w.c_str();std::wstring converted(L"unchanged");
                FStringW wide(wideLarge);FMemoryStream stream;FStringA saved(large);stream<<saved;stream.Rewind();
                const long long beforeOperation=LiveStringsAllocations();ArmStringsFault(index);
                try {
                    switch(kind) {
                    case 0:a.Copy(static_cast<int>(large.size()),large.data());break;
                    case 1:w.Copy(static_cast<int>(wideLarge.size()),wideLarge.data());break;
                    case 2:a+=a;break;
                    case 3:w+=w;break;
                    case 4:a.Copy(20,a.c_str()+1);break;
                    case 5:a.Reserve(4096);break;
                    case 6:w.Reserve(4096);break;
                    case 7:a.Format("%s:%d",large.c_str(),17);break;
                    case 8:wide.CopyToUTF8(&a);break;
                    case 9:converted=CvStringUtils::FromUTF8ToUTF16(large);break;
                    case 10:stream>>a;break;
                    case 11:{ FStringA::FBuffer access(a,4096);std::memcpy(static_cast<char*>(access),"done",5);break; }
                    case 12:{ FStringW::FBuffer access(w,4096);std::memcpy(static_cast<wchar_t*>(access),L"done",5*sizeof(wchar_t));break; }
                    case 13:{ FStringA copy(a);CHECK(copy.GetLength()==31);break; }
                    case 14:w.Copy(20,w.c_str()+1);break;
                    }
                }catch(const std::bad_alloc&) { failed=true; }
                injected=DisarmStringsFault();CHECK(failed==injected);
                if(failed) {
                    ++failures;CHECK(LiveStringsAllocations()==beforeOperation);
                    CHECK(a.c_str()==oldA && w.c_str()==oldW);CheckValue(a,savedA);CheckValue(w,savedW);CHECK(converted==L"unchanged");
                } else {
                    ++successes;success=true;
                    if(kind==0 || kind==10)CheckValue(a,large);
                    if(kind==1)CheckValue(w,wideLarge);
                    if(kind==2)CheckValue(a,savedA+savedA);
                    if(kind==3)CheckValue(w,savedW+savedW);
                    if(kind==4)CheckValue(a,savedA.substr(1,20));
                    if(kind==5)CheckValue(a,savedA);
                    if(kind==6)CheckValue(w,savedW);
                    if(kind==7)CheckValue(a,large+":17");
                    if(kind==8) { CHECK(a.GetLength()==12288);for(int k=0;k<4096;++k)CHECK(!std::memcmp(a.c_str()+k*3,"\xed\x95\x9c",3)); }
                    if(kind==9)CHECK(converted==std::wstring(4096,L'k'));
                    if(kind==11)CheckValue(a,std::string("done"));
                    if(kind==12)CheckValue(w,std::wstring(L"done"));
                    if(kind==14)CheckValue(w,savedW.substr(1,20));
                }
            }
            CHECK(LiveStringsAllocations()==beforeScope);
        }
        CHECK(success);
    }
    std::printf("FAULTS|%u|%u|15_operations\n",failures,successes);
}
int main() {
    Boundaries();Streams();Faults();std::printf("PASS|%u\n",checks);return 0;
}
