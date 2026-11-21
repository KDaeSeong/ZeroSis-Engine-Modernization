#include "HostServices.h"
#include <thread>
#include <fstream>
#include <cstdio>
#include <cstdlib>
#include <new>

static thread_local int allocationBudget=-1;
static std::atomic<long long> allocations{0};
void* operator new(std::size_t size){
    if(allocationBudget>=0 && allocationBudget--==0){allocationBudget=-1;throw std::bad_alloc();}
    void* p=std::malloc(size?size:1);if(!p)throw std::bad_alloc();++allocations;return p;
}
void operator delete(void* p) noexcept{if(p){--allocations;std::free(p);}}
void* operator new[](std::size_t size){return ::operator new(size);}
void operator delete[](void* p) noexcept{::operator delete(p);}
void operator delete(void* p,std::size_t) noexcept{::operator delete(p);}
void operator delete[](void* p,std::size_t) noexcept{::operator delete(p);}
static std::atomic<unsigned> checks{0};
static void Check(bool ok,int line){++checks;if(!ok){std::fprintf(stderr,"MAP_AUDIO_FAILED line=%d\n",line);std::exit(1);}}
#define CHECK(value) Check((value),__LINE__)
template<class F> static void Reject(F operation){bool caught=false;try{operation();}catch(const std::exception&){caught=true;}CHECK(caught);}
using namespace ZeroSisHost;

static std::vector<unsigned char> Load(const wchar_t* path){
    std::ifstream input(path,std::ios::binary);CHECK(static_cast<bool>(input));
    return std::vector<unsigned char>(std::istreambuf_iterator<char>(input),std::istreambuf_iterator<char>());
}
static void PutWord(std::vector<unsigned char>& data,std::size_t at,std::uint32_t value){
    for(unsigned i=0;i<4;++i)data[at+i]=static_cast<unsigned char>(value>>(i*8));
}
static std::uint32_t Word(const std::vector<unsigned char>& data,std::size_t at){
    std::uint32_t value=0;for(unsigned i=0;i<4;++i)value|=static_cast<std::uint32_t>(data[at+i])<<(i*8);return value;
}

static unsigned CatalogFailures(const std::vector<unsigned char>& bytes){
    const auto baseline=allocations.load();unsigned failures=0;
    for(int point=0;point<1024;++point){
        bool failed=false;
        allocationBudget=point;
        try{AudioCatalog candidate(bytes);}catch(const std::bad_alloc&){failed=true;}
        allocationBudget=-1;
        CHECK(allocations==baseline);
        if(!failed)break;
        ++failures;
    }
    CHECK(failures>0 && failures<1023);return failures;
}
static unsigned Malformed(const std::vector<unsigned char>& bytes){
    unsigned cases=0;
    auto invalid=[&](std::vector<unsigned char> data){Reject([&]{AudioCatalog bad(data);});++cases;};
    for(std::size_t n=0;n<12;++n)invalid({bytes.begin(),bytes.begin()+n});
    std::size_t at=12;std::vector<std::size_t> boundaries;
    for(unsigned record=0;record<Word(bytes,8);++record)for(unsigned field=0;field<2;++field){
        const auto size=Word(bytes,at);boundaries.push_back(at);boundaries.push_back(at+4);boundaries.push_back(at+4+size-1);at+=4+size;
    }
    CHECK(at==bytes.size());
    for(auto end:boundaries)invalid({bytes.begin(),bytes.begin()+end});
    auto data=bytes;data[0]='X';invalid(data);
    data=bytes;PutWord(data,8,0);invalid(data);PutWord(data,8,65537);invalid(data);
    data=bytes;PutWord(data,12,0xffffffffu);invalid(data);
    data=bytes;data[16]='/';invalid(data);
    data=bytes;const auto xmlOffset=16+Word(data,12);PutWord(data,xmlOffset,0xffffffffu);invalid(data);
    data=bytes;data[xmlOffset+4]=0;invalid(data);
    data=bytes;data.push_back(1);invalid(data);
    // Repeat the first valid record under a two-entry header: duplicate name rejected.
    const auto firstEnd=xmlOffset+4+Word(bytes,xmlOffset);
    data.assign(bytes.begin(),bytes.begin()+12);PutWord(data,8,2);
    data.insert(data.end(),bytes.begin()+12,bytes.begin()+firstEnd);data.insert(data.end(),bytes.begin()+12,bytes.begin()+firstEnd);invalid(data);
    return cases;
}

static void Services(const std::shared_ptr<const AudioCatalog>& catalog){
    auto state=std::make_shared<HostState>("C:\\fixture\\",nullptr,catalog);EngineServices engine(state);
    UserInterface ui(state);const auto dirty=static_cast<InterfaceDirtyBits>(0);
    ui.setDirty(dirty,true);ui.setCycleSelectionCounter(99);engine.SetDone(true);
    engine.GetAudioTagIndex("ASSS_AMBIENCE_TUNDRA",AUDIOTAG_SOUNDSCAPE);
    Reject([&]{engine.DoMapSetup(1);});engine.InitGlobals();Reject([&]{engine.DoMapSetup(1);});
    CHECK(!ui.isDirty(dirty) && ui.getCycleSelectionCounter()==0 && !engine.GetDone() && state->missingAudioTags.empty());
    std::shared_ptr<const MapFrame> original;
    {
        GameCall call(*state);engine.DoMapSetup(0);CHECK(state->mapSurface.Snapshot()->dirtyPlots.empty());
        engine.DoMapSetup(20);original=state->mapSurface.Snapshot();CHECK(original->generation==2 && original->dirtyPlots.size()==20);
        for(int point=0;point<2;++point){
            bool failed=false;const auto live=allocations.load();allocationBudget=point;
            try{engine.DoMapSetup(40);}catch(const std::bad_alloc&){failed=true;}
            allocationBudget=-1;CHECK(failed && state->mapSurface.Snapshot()==original && allocations==live);
        }
        Reject([&]{engine.DoMapSetup(-1);});CHECK(state->mapSurface.Snapshot()==original);
        engine.DoMapSetup(5);CHECK(state->mapSurface.Snapshot()->generation==3 && original->dirtyPlots.size()==20);
    }
    std::thread wrongOwner([&]{GameCall call(*state);Reject([&]{engine.DoMapSetup(3);});
        Reject([&]{engine.InitGlobals();});Reject([&]{engine.UninitGlobals();});});wrongOwner.join();
    engine.UninitGlobals();CHECK(!state->mapSurface.Snapshot() && original->dirtyPlots.size()==20);
    engine.InitGlobals();{GameCall call(*state);engine.DoMapSetup(11);CHECK(state->mapSurface.Snapshot()->generation==4);}
    CHECK(engine.GetAudioTagIndex(nullptr,AUDIOTAG_SOUNDSCAPE)==-1 && engine.GetAudioTagIndex("",AUDIOTAG_SOUNDSCAPE)==-1);
    Reject([&]{engine.GetAudioTagIndex(catalog->Definition(0).tag.c_str(),AUDIOTAG_2DSCRIPT);});
    CHECK(engine.GetAudioTagIndex("ASSS_AMBIENCE_TUNDRA",AUDIOTAG_SOUNDSCAPE)==-1);
    std::vector<std::thread> readers;
    for(unsigned worker=0;worker<8;++worker)readers.emplace_back([&,worker]{
        for(unsigned n=0;n<512;++n){
            auto map=state->mapSurface.Snapshot();CHECK(map && map->generation>=4 && map->dirtyPlots.size()<=63);
            for(auto dirty:map->dirtyPlots)if(dirty!=1)std::exit(2);
            const int index=static_cast<int>((worker+n)%catalog->Size());const auto& definition=catalog->Definition(index);
            CHECK(engine.GetAudioTagIndex(definition.tag.c_str(),AUDIOTAG_SOUNDSCAPE)==index);
            CHECK(engine.GetAudioTagIndex("ASSS_AMBIENCE_TUNDRA",AUDIOTAG_SOUNDSCAPE)==-1);
        }
    });
    for(unsigned n=0;n<128;++n){GameCall call(*state);engine.DoMapSetup(static_cast<int>(n%64));CHECK(state->mapSurface.Snapshot()->generation==5+n);}
    for(auto& reader:readers)reader.join();
    CHECK(state->missingAudioTags.size()==1 && state->missingAudioTags.count("ASSS_AMBIENCE_TUNDRA")==1);
    engine.UninitGlobals();CHECK(!state->mapSurface.Snapshot() && original->generation==2 && original->dirtyPlots.size()==20);
    CHECK(catalog->Find("UNKNOWN_SOUND")==-1);Reject([&]{catalog->Definition(-1);});Reject([&]{catalog->Definition(static_cast<int>(catalog->Size()));});
}

int wmain(int argc,wchar_t** argv){
    try{
        CHECK(argc==2);const auto bytes=Load(argv[1]);const auto failures=CatalogFailures(bytes);const auto invalid=Malformed(bytes);
        auto catalog=std::make_shared<AudioCatalog>(bytes);CHECK(catalog->Size()==10);
        std::size_t cursor=12;
        for(int index=0;index<static_cast<int>(catalog->Size());++index){
            const auto& definition=catalog->Definition(index);CHECK(catalog->Find(definition.tag.c_str())==index);
            CHECK(definition.xml.find("<ScriptID>"+definition.tag+"</ScriptID>")!=std::string::npos);
            const auto tagSize=Word(bytes,cursor);cursor+=4;
            CHECK(definition.tag==std::string(reinterpret_cast<const char*>(bytes.data()+cursor),tagSize));cursor+=tagSize;
            const auto xmlSize=Word(bytes,cursor);cursor+=4;
            CHECK(definition.xml==std::string(reinterpret_cast<const char*>(bytes.data()+cursor),xmlSize));cursor+=xmlSize;
            std::uint64_t fingerprint=14695981039346656037ull;
            for(char byte:definition.xml)fingerprint=(fingerprint^static_cast<unsigned char>(byte))*1099511628211ull;
            std::printf("AUDIO_DEFINITION index=%d tag=%s xml_bytes=%zu xml_fnv=%016llx\n",index,definition.tag.c_str(),definition.xml.size(),fingerprint);
        }
        Services(catalog);
        CHECK(!GetModuleHandleW(L"CvGameCoreDLL_Expansion2_x64.dll"));
        std::printf("HOST_MAP_AUDIO_PASS checks=%u MAP_ALLOCATION_FAILURES=2 CATALOG_ALLOCATION_FAILURES=%u MALFORMED_CASES=%u MAP_RESIZES=128 READ_OPERATIONS=4096 AUDIO_LOOKUPS=8192 GAMECORE_LOADED=false\n",checks.load(),failures,invalid);
        return 0;
    }catch(const std::exception& error){allocationBudget=-1;std::fprintf(stderr,"MAP_AUDIO_ERROR: %s\n",error.what());return 1;}
}
