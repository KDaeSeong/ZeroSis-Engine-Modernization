#include "SdkWorldBuilderIncludes.h"
#include <atomic>
#include <thread>
// Fault allocator lives in the test executable; all production objects are unchanged.
namespace { thread_local long long faultIndex=-1;thread_local bool faultHit=false; }
void* operator new(size_t n){if(faultIndex>=0 && faultIndex--==0){faultIndex=-1;faultHit=true;throw std::bad_alloc();}void* p=std::malloc(n?n:1);if(!p)throw std::bad_alloc();return p;}
void* operator new[](size_t n){return ::operator new(n);}
void operator delete(void* p) noexcept {std::free(p);}
void operator delete[](void* p) noexcept {::operator delete(p);}
void operator delete(void* p,size_t) noexcept {::operator delete(p);}
void operator delete[](void* p,size_t) noexcept {::operator delete(p);}
static unsigned checks=0;
#define CHECK(x) do{++checks;if(!(x)){std::fprintf(stderr,"FAIL|%u|%d|%s\n",checks,__LINE__,#x);std::exit(2);}}while(0)
typedef CvWorldBuilderMapTypeDesc::TypeMap TypeMap;
typedef CvWorldBuilderMapTypeDesc::String TypeString;
static std::vector<char> Snapshot(const CvWorldBuilderMapTypeGroup& g){std::vector<char> b(g.GetSerializedSize()+1);g.Serialize(&b[0]);b.resize(g.GetSerializedSize());return b;}
static std::vector<char> Snapshot(const TypeMap& m){std::vector<char> b(m.GetSerializedSize()+1);m.Serialize(&b[0]);b.resize(m.GetSerializedSize());return b;}
template<class F>static void Reject(F operation){bool rejected=false;try{operation();}catch(const std::invalid_argument&){rejected=true;}CHECK(rejected);}
static void Boundaries(){
    CvWorldBuilderMapTypeGroup g;g.Add("saved");std::vector<char> old=Snapshot(g);g=g;CHECK(old==Snapshot(g));
    g.Add(NULL);g.Remove(NULL);CHECK(!g.Contains(NULL));CHECK(old==Snapshot(g));
    const char* malformed[]={"\x05" "abc","\x01" "ab","\x02" "a\0\0","\xff\0"};const uint lengths[]={4,3,4,2};
    for(unsigned i=0;i<4;++i){Reject([&]{g.Deserialize(malformed[i],lengths[i]);});CHECK(old==Snapshot(g));}
    Reject([&]{g.Deserialize(NULL,1);});Reject([&]{g.Serialize(NULL);});CHECK(old==Snapshot(g));
    std::vector<char> valid;valid.push_back(static_cast<char>(255));valid.insert(valid.end(),255,'x');valid.push_back(0);
    for(uint i=1;i<valid.size();++i){Reject([&]{g.Deserialize(&valid[0],i);});CHECK(old==Snapshot(g));}
    g.Deserialize(&valid[0],static_cast<uint>(valid.size()));CHECK(g.Contains(std::string(255,'x').c_str()));g.Deserialize(NULL,0);CHECK(g.GetSerializedSize()==0);
    TypeMap m;m.Add("saved_type");const std::vector<char> before=Snapshot(m);char noTerminator[3]={'a','b','c'};
    Reject([&]{m.Deserialize(noTerminator,3);});CHECK(before==Snapshot(m));Reject([&]{m.Deserialize(NULL,1);});CHECK(before==Snapshot(m));
    Reject([&]{m.Serialize(NULL);});CHECK(before==Snapshot(m));m.Deserialize(NULL,0);CHECK(m.Size()==0);
    char mix[]={'a',0,'b'};m.Add("kept");const std::vector<char> kept=Snapshot(m);Reject([&]{m.Deserialize(mix,3);});CHECK(kept==Snapshot(m));
    uint out=99;CHECK(!m.FindType("absent",out) && out==99);CHECK(static_cast<const char*>(m.Get(UINT_MAX))==NULL);
    std::printf("BOUNDARIES|truncated_records|state_preserved|self_assignment\n");
}
static void Faults(){
    unsigned failures=0,successes=0;
    for(unsigned kind=0;kind<6;++kind){bool finished=false;
        for(unsigned index=0;index<64 && !finished;++index){
            CvWorldBuilderMapTypeGroup group,other;group.Add("original");other.Add("replacement");
            TypeMap types;types.Add("original_type");TypeString value("original_string");
            const std::vector<char> savedGroup=Snapshot(group),savedTypes=Snapshot(types),replacement=Snapshot(other);
            char unique[128];::sprintf_s(unique,sizeof(unique),"A_unique_long_type_for_allocation_test_%u_%u",kind,index);
            std::vector<char> wire(unique,unique+std::strlen(unique)+1);
            faultIndex=index;faultHit=false;bool failed=false;
            try{switch(kind){case 0:group.Add(unique);break;case 1:group=other;break;
                case 2:group.Deserialize(&replacement[0],static_cast<uint>(replacement.size()));break;
                case 3:types.Add(unique);break;case 4:types.Deserialize(&wire[0],wire.size());break;case 5:value=unique;break;}}
            catch(const std::bad_alloc&){failed=true;}
            faultIndex=-1;CHECK(failed==faultHit);
            if(failed){++failures;CHECK(Snapshot(group)==savedGroup);CHECK(Snapshot(types)==savedTypes);CHECK(std::strcmp(value,"original_string")==0);}
            else{++successes;finished=true;switch(kind){case 0:CHECK(group.Contains(unique));break;case 1:case 2:CHECK(group.Contains("replacement"));break;
                case 3:CHECK(types.Size()==2 && std::strcmp(types.Get(1),unique)==0);break;case 4:CHECK(types.Size()==1 && std::strcmp(types.Get(0),unique)==0);break;case 5:CHECK(std::strcmp(value,unique)==0);break;}}
        }CHECK(finished);
    }
    std::printf("FAULTS|%u|%u\n",failures,successes);
}
static void Workers(){
    // Concurrent independent objects share only the synchronized intern palette.
    std::atomic<unsigned> successes(0);std::thread workers[4];
    for(unsigned worker=0;worker<4;++worker)workers[worker]=std::thread([&]{for(unsigned i=0;i<1024;++i){
        char text[48];::sprintf_s(text,sizeof(text),"shared_parallel_type_%u",i%97);TypeString a(text),b(text);TypeMap m;m.Add(text);
        CvWorldBuilderMapTypeGroup g;g.Add(text);CvWorldBuilderMapTypeGroup copy(g);
        if(a==b && std::strcmp(m.Get(0),a)==0 && copy.Contains(text))++successes;
    }});
    for(unsigned i=0;i<4;++i)workers[i].join();CHECK(successes==4096);std::printf("WORKERS|4|4096\n");
}
int main(){SetErrorMode(SEM_FAILCRITICALERRORS|SEM_NOGPFAULTERRORBOX);Boundaries();Faults();Workers();std::printf("PASS|%u\n",checks);return 0;}
