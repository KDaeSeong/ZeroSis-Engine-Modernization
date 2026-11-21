#include "SdkWorldBuilderModData.h"
#include <malloc.h>
#include <atomic>
#include <thread>
namespace {thread_local long long fault=-1;thread_local bool hit=false;std::atomic<long long> live(0);}
static bool Fail(){if(fault>=0 && fault--==0){fault=-1;hit=true;return true;}return false;}
void* operator new(size_t n){if(Fail())throw std::bad_alloc();void* p=std::malloc(n?n:1);if(!p)throw std::bad_alloc();++live;return p;}
void* operator new[](size_t n){return ::operator new(n);}
void operator delete(void* p)noexcept{if(p){--live;std::free(p);}}
void operator delete[](void* p)noexcept{::operator delete(p);}
void operator delete(void* p,size_t)noexcept{::operator delete(p);}
void operator delete[](void* p,size_t)noexcept{::operator delete(p);}
// Test-only allocator seam, matching the production Foundation allocation/free
// domain. The exact mod-data production objects are linked unchanged.
void* FireMallocAlignedNoTracking(size_t n,size_t align,const char*,int){if(Fail())return NULL;void* p=_aligned_malloc(n?n:1,align?align:sizeof(void*));if(p)++live;return p;}
void FireFreeAlignedNoTracking(void* p){if(p){--live;_aligned_free(p);}}
static unsigned checks=0;
#define CHECK(x) do{++checks;if(!(x)){std::fprintf(stderr,"FAIL|%u|%d|%s\n",checks,__LINE__,#x);std::exit(2);}}while(0)
static std::vector<unsigned char> Snapshot(const CvWorldBuilderMapModData& value){std::vector<unsigned char> bytes(value.GetSerializedSize());value.Serialize(bytes.data());return bytes;}
static void Fixture(CvWorldBuilderMapModData& m){
    m.m_kMapModData.AddField("flag",true);m.m_kMapModData.AddField("number",1.25f);m.m_kMapModData.AddField("text","saved");
    for(unsigned i=0;i<10;++i){char name[32];::sprintf_s(name,sizeof(name),"field_%u",i);ModEnum& e=m.m_kMapModData.AddEnumField(name,0);
        for(unsigned j=0;j<10;++j){char member[32];::sprintf_s(member,sizeof(member),"member_%u_%u",i,j);e.AddMember(member);}}
    m.m_kPlotModData.AddField("plot",false);m.InitDataEntries(3);
}
template<class F>static void Reject(F call){bool rejected=false;try{call();}catch(const std::exception&){rejected=true;}CHECK(rejected);}
static void Boundaries(){
    CvWorldBuilderMapModData m;Fixture(m);const std::vector<unsigned char> before=Snapshot(m);
    for(size_t n=0;n<before.size();++n){Reject([&]{ZeroSisWorldBuilder::DeserializeModData(m,before.data(),n);});CHECK(before==Snapshot(m));}
    std::vector<unsigned char> trailing(before);trailing.push_back(0);Reject([&]{ZeroSisWorldBuilder::DeserializeModData(m,trailing.data(),trailing.size());});CHECK(before==Snapshot(m));
    for(size_t offset=0;offset<8;++offset){std::vector<unsigned char> bad(before);bad[offset]=255;Reject([&]{ZeroSisWorldBuilder::DeserializeModData(m,bad.data(),bad.size());});CHECK(before==Snapshot(m));}
    const size_t invalidRefs[]={8,12,40,44,168,636};
    for(size_t offset:invalidRefs){std::vector<unsigned char> bad(before);std::memset(bad.data()+offset,255,4);
        Reject([&]{ZeroSisWorldBuilder::DeserializeModData(m,bad.data(),bad.size());});CHECK(before==Snapshot(m));}
    std::vector<unsigned char> noTerminator(before);noTerminator.back()='x';
    Reject([&]{ZeroSisWorldBuilder::DeserializeModData(m,noTerminator.data(),noTerminator.size());});CHECK(before==Snapshot(m));
    Reject([&]{ZeroSisWorldBuilder::DeserializeModData(m,NULL,0);});Reject([&]{m.InitDataEntries(UINT_MAX);});CHECK(before==Snapshot(m));
    Reject([&]{m.GetPlotDataEntry(3);});Reject([&]{m.GetPlotDataEntry(UINT_MAX);});
    Reject([&]{m.GetMapDataEntry().SetField(UINT_MAX,true);});CHECK(before==Snapshot(m));
    ModEnum unbound;Reject([&]{unbound.AddMember("invalid");});CHECK(unbound.GetMemberCount()==0);
    // A default enum/string value is defined on fresh allocation; no stale heap
    // bytes are exposed through valid getters before callers overwrite them.
    CHECK(m.GetMapDataEntry().GetFieldAsBool(0));CHECK(m.GetMapDataEntry().GetFieldAsFloat(1)==1.25f);CHECK(std::strcmp(m.GetMapDataEntry().GetFieldAsString(2),"saved")==0);
    ModDataEntry entry=m.GetMapDataEntry();const char* alias=entry.GetFieldAsString(2);entry.SetField(2,alias);CHECK(std::strcmp(entry.GetFieldAsString(2),"saved")==0);CHECK(!entry.IsFieldDefaultValue(2));
    m.ResetTypes();CHECK(m.GetSerializedSize()==24);m.InitDataEntries(0);CHECK(m.m_kMapModData.GetFieldCount()==0);
    std::printf("BOUNDARIES|%u_truncations|state_preserved|fresh_defaults|alias\n",static_cast<unsigned>(before.size()));
}
static void Faults(){unsigned failures=0,successes=0;
    CvWorldBuilderMapModData targetSource;Fixture(targetSource);targetSource.GetMapDataEntry().SetField(2,"incoming");const std::vector<unsigned char> incoming=Snapshot(targetSource);
    for(unsigned kind=0;kind<9;++kind){bool success=false;
        for(unsigned index=0;index<512 && !success;++index){const long long beforeScope=live.load();
            {CvWorldBuilderMapModData m;Fixture(m);const std::vector<unsigned char> before=Snapshot(m);const long long operationLive=live.load();
             fault=index;hit=false;bool failed=false;
             try{switch(kind){case 0:m.m_kMapModData.AddField("new_bool",true);break;case 1:m.m_kMapModData.AddField("new_float",2.5f);break;
                case 2:m.m_kMapModData.AddField("new_string","new_value");break;case 3:m.m_kMapModData.AddEnumField("new_enum",-2);break;
                case 4:const_cast<ModEnum*>(m.m_kMapModData.GetFieldEnumType(3))->AddMember("new_member");break;
                case 5:m.GetMapDataEntry().SetField(2,"new_value");break;case 6:m.InitDataEntries(20);break;
                case 7:ZeroSisWorldBuilder::DeserializeModData(m,incoming.data(),incoming.size());break;
                case 8:m.Deserialize(incoming.data());break;}}
             catch(const std::bad_alloc&){failed=true;}fault=-1;CHECK(failed==hit);
             if(failed){++failures;CHECK(live.load()==operationLive);CHECK(before==Snapshot(m));CHECK(std::strcmp(m.GetMapDataEntry().GetFieldAsString(2),"saved")==0);}
             else{++successes;success=true;switch(kind){case 0:case 1:case 2:case 3:CHECK(m.m_kMapModData.GetFieldCount()==14);break;
                case 4:CHECK(m.m_kMapModData.GetFieldEnumType(3)->GetMemberCount()==11);break;case 5:CHECK(std::strcmp(m.GetMapDataEntry().GetFieldAsString(2),"new_value")==0);break;
                case 6:CHECK(!m.GetPlotDataEntry(19).GetFieldAsBool(0));break;case 7:case 8:CHECK(Snapshot(m)==incoming);break;}}
            }CHECK(live.load()==beforeScope);
        }CHECK(success);
    }
    std::printf("FAULTS|%u|%u\n",failures,successes);
}
static void Workers(){std::atomic<unsigned> calls(0);std::thread workers[4];
    for(unsigned i=0;i<4;++i)workers[i]=std::thread([&]{for(unsigned j=0;j<64;++j){CvWorldBuilderMapModData m;m.m_kMapModData.AddField("value",static_cast<float>(j));m.InitDataEntries(0);
        std::vector<unsigned char> bytes=Snapshot(m);CvWorldBuilderMapModData copy;ZeroSisWorldBuilder::DeserializeModData(copy,bytes.data(),bytes.size());if(copy.GetMapDataEntry().GetFieldAsFloat(0)==static_cast<float>(j))++calls;}});
    for(unsigned i=0;i<4;++i)workers[i].join();CHECK(calls==256);std::printf("WORKERS|4|256\n");
}
int main(){SetErrorMode(SEM_FAILCRITICALERRORS|SEM_NOGPFAULTERRORBOX);setvbuf(stdout,NULL,_IONBF,0);const long long baseline=live.load();Boundaries();Faults();Workers();CHECK(live.load()==baseline);std::printf("PASS|%u\n",checks);return 0;}
