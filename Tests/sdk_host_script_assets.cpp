#include "HostServices.h"
#include "ScriptMetadata.h"
#include "host_script_utility_fixture.h"
#include <fstream>
#include <cstdio>
#include <cstdlib>
#include <new>
using namespace ZeroSisHost;
static unsigned checks=0;
static void Check(bool ok,const char* expression,int line){++checks;if(!ok){std::fprintf(stderr,"SCRIPT_ASSETS_FAILED line=%d %s\n",line,expression);std::exit(1);}}
#define CHECK(value) Check((value),#value,__LINE__)
template<class F> static void Reject(F operation){bool failed=false;try{operation();}catch(const std::exception&){failed=true;}CHECK(failed);}
static thread_local int allocationBudget=-1;
static long long allocations=0;
void* operator new(std::size_t size){
    if(allocationBudget>=0 && allocationBudget--==0){allocationBudget=-1;throw std::bad_alloc();}
    void* value=std::malloc(size?size:1);if(!value)throw std::bad_alloc();++allocations;return value;
}
void operator delete(void* value) noexcept{if(value){--allocations;std::free(value);}}
void* operator new[](std::size_t size){return ::operator new(size);}
void operator delete[](void* value) noexcept{::operator delete(value);}
void operator delete(void* value,std::size_t) noexcept{::operator delete(value);}
void operator delete[](void* value,std::size_t) noexcept{::operator delete(value);}
static std::vector<unsigned char> Load(const wchar_t* path){
    std::ifstream input(path,std::ios::binary);if(!input)throw std::runtime_error("Cannot read script catalog input");
    return {std::istreambuf_iterator<char>(input),std::istreambuf_iterator<char>()};
}
static bool Execute(ScriptSystem& scripts,lua_State* state,const char* source){return scripts.Execute(state,source,std::strlen(source));}
static void Word(std::vector<unsigned char>& out,unsigned value){for(unsigned i=0;i<4;++i)out.push_back(static_cast<unsigned char>(value>>(i*8)));}
static std::vector<unsigned char> Encode(const std::vector<ScriptFile>& files){
    const char header[]="ZSSCRIP1";std::vector<unsigned char> data(header,header+8);Word(data,static_cast<unsigned>(files.size()));
    for(const auto& file:files)for(const auto* text:{&file.path,&file.origin,&file.contents}){
        Word(data,static_cast<unsigned>(text->size()));data.insert(data.end(),text->begin(),text->end());
    }return data;
}
static unsigned CatalogFailures(const std::vector<unsigned char>& input){
    unsigned failures=0;auto invalid=[&](const std::vector<unsigned char>& bytes){Reject([&]{ScriptCatalog catalog(bytes);});++failures;};
    for(std::size_t size=0;size<12;++size)invalid({input.begin(),input.begin()+size});
    auto value=input;value[0]='X';invalid(value);value=input;value.push_back(0);invalid(value);
    value=input;for(unsigned i=8;i<12;++i)value[i]=0;invalid(value);for(unsigned i=8;i<12;++i)value[i]=255;invalid(value);
    const std::vector<ScriptFile> one={{"maps/a.lua","assets/maps/a.lua","return true"}};
    auto bytes=Encode(one);for(std::size_t size=12;size<bytes.size();++size)invalid({bytes.begin(),bytes.begin()+size});
    invalid(Encode({one[0],one[0]}));
    for(const char* path:{"/a.lua","../a.lua","x/../a.lua","c:/a.lua","MAPS/a.lua","a//b.lua","a/./b.lua","a/","a%w.lua"})
        invalid(Encode({{path,"assets/a.lua",""}}));
    invalid(Encode({{"a.lua",std::string("assets/a\0b.lua",14),""}}));
    invalid(Encode({{"a.lua","assets/shared.lua",""},{"b.lua","assets/shared.lua",""}}));
    invalid(Encode({{"a.lua","assets/a.lua",""},{"b.lua","a.lua",""}}));
    ScriptCatalog ambiguous(Encode({{"a/shared.lua","assets/a/shared.lua",""},{"b/shared.lua","assets/b/shared.lua",""}}));
    CHECK(ambiguous.Resolve("a/shared") && ambiguous.Resolve("b/shared.lua"));Reject([&]{ambiguous.Resolve("shared");});
    unsigned allocationFailures=0;const auto baseline=allocations;bool allocationSuccess=false;
    for(int point=0;point<2048;++point){
        bool failed=false;allocationBudget=point;
        try{ScriptCatalog catalog(input);CHECK(catalog.Size()>0);}catch(const std::bad_alloc&){failed=true;}
        allocationBudget=-1;CHECK(allocations==baseline);if(!failed){allocationSuccess=true;break;}++allocationFailures;
    }
    CHECK(allocationSuccess && allocationFailures>20);std::printf("SCRIPT_CATALOG_ALLOCATION_FAILURES=%u\n",allocationFailures);return failures;
}
static void Includes(){
    ScriptSystem scripts;
    scripts.RegisterFile("a.lua","trace=(trace or '')..'A'; include('b'); trace=trace..'a'");
    scripts.RegisterFile("b.lua","trace=trace..'B'; include('c.lua')");scripts.RegisterFile("c.lua","trace=trace..'C'");
    scripts.RegisterFile("bom.lua",std::string("\xef\xbb\xbf")+"bom_value=19");
    scripts.RegisterFile("cycle/a.lua","include('cycle/b')");scripts.RegisterFile("cycle/b.lua","include('cycle/A.lua')");
    auto* state=scripts.CreateLuaThread("includes");lua_pushinteger(state,671);const int base=lua_gettop(state);
    CHECK(scripts.LoadFile(state,"A") && scripts.LoadFile(state,"a.lua"));CHECK(Execute(scripts,state,"assert(trace=='ABCaABCa')"));
    CHECK(scripts.LoadFile(state,"bom") && Execute(scripts,state,"assert(bom_value==19)"));
    CHECK(!scripts.LoadFile(state,"cycle/a") && std::strstr(scripts.LastError(),"Circular"));
    scripts.RegisterFile("cycle/b.lua","fixed=73");CHECK(scripts.LoadFile(state,"cycle/a"));CHECK(Execute(scripts,state,"assert(fixed==73)"));
    CHECK(!Execute(scripts,state,"include('missing')"));CHECK(!Execute(scripts,state,"include(nil)"));
    CHECK(!Execute(scripts,state,"include('bad\\000name')"));CHECK(!Execute(scripts,state,"include('a',true)"));
    CHECK(!Execute(scripts,state,"include('../a')"));CHECK(!Execute(scripts,state,"include('c:/a')"));
    CHECK(Execute(scripts,state,"include('a',false)"));
    scripts.RegisterFile("bad.lua","local =");CHECK(!Execute(scripts,state,"include('bad')"));
    scripts.RegisterFile("bad.lua","error('nested source failure')");CHECK(!Execute(scripts,state,"include('bad')"));
    scripts.RegisterFile("bad.lua","recovered=91");CHECK(Execute(scripts,state,"include('bad'); assert(recovered==91)"));
    CHECK(lua_gettop(state)==base && lua_tointeger(state,-1)==671);
    Reject([&]{scripts.RegisterFile(std::string("a\0b",3),"");});
    unsigned failures=0;const auto baseline=allocations;bool reachedSuccess=false;
    for(int point=0;point<64;++point){
        allocationBudget=point;const bool ok=scripts.LoadFile(state,"a");allocationBudget=-1;
        CHECK(allocations==baseline && lua_gettop(state)==base && scripts.IsQuiescent());
        if(ok){reachedSuccess=true;break;}++failures;CHECK(scripts.LoadFile(state,"a"));
    }
    CHECK(reachedSuccess && failures>2);std::printf("SCRIPT_INCLUDE_CPP_FAILURES=%u\n",failures);
}
struct LuaAllocation {
    int budget=-1;std::size_t blocks=0;
    static void* Allocate(void* data,void* pointer,std::size_t oldSize,std::size_t newSize){
        auto& memory=*static_cast<LuaAllocation*>(data);
        if(!newSize){if(pointer){std::free(pointer);--memory.blocks;}return nullptr;}
        if(newSize>oldSize && memory.budget>=0){if(memory.budget==0)return nullptr;--memory.budget;}
        void* value=std::realloc(pointer,newSize);if(value && !pointer)++memory.blocks;return value;
    }
};
static void IncludeLuaFailures(){
    unsigned failures=0;bool reachedSuccess=false;
    for(int point=0;point<512;++point){
        LuaAllocation memory;
        {ScriptSystem scripts(LuaAllocation::Allocate,&memory);
            scripts.RegisterFile("a.lua","include('b'); include('c'); final_value=57");
            scripts.RegisterFile("b.lua","local t={1,2,3}; assert(t[3]==3)");scripts.RegisterFile("c.lua","local text=string.rep('x',256); assert(#text==256)");
            auto* vm=scripts.CreateLuaThread("include allocation");lua_pushinteger(vm,992);memory.budget=point;
            const bool ok=scripts.LoadFile(vm,"a");memory.budget=-1;
            CHECK(lua_gettop(vm)==1 && lua_tointeger(vm,1)==992 && scripts.IsQuiescent());
            if(ok)reachedSuccess=true;
            else{++failures;CHECK(scripts.LoadFile(vm,"a"));}
            CHECK(Execute(scripts,vm,"assert(final_value==57)"));CHECK(scripts.Close());
        }
        CHECK(memory.blocks==0);if(reachedSuccess)break;
    }
    CHECK(reachedSuccess && failures>10);std::printf("SCRIPT_INCLUDE_LUA_FAILURES=%u\n",failures);
}
static ScriptSystem* registeringSystem=nullptr;static unsigned failedFinalizers=0;
static int FailedRegistrationFinalizer(lua_State*){
    CHECK(registeringSystem && !registeringSystem->IsQuiescent() && !registeringSystem->Close());
    bool value=true;CHECK(!registeringSystem->CallHook("event",nullptr,value) && value);++failedFinalizers;return 0;
}
static void Libraries(){
    auto scripts=std::make_shared<ScriptSystem>();auto state=std::make_shared<HostState>("C:\\fixture\\",nullptr,nullptr,scripts);
    EngineServices engine(state);ScriptUtilityFixture library;
    Reject([&]{scripts->BindGameLibraries(&library,&engine);});
    {GameCall game(*state);
        Reject([&]{scripts->BindGameLibraries(nullptr,&engine);});
        auto* early=scripts->CreateLuaThread("pre-binding");Reject([&]{scripts->BindGameLibraries(&library,&engine);});scripts->FreeLuaThread(early);
        scripts->BindGameLibraries(&library,&engine);Reject([&]{scripts->BindGameLibraries(&library,&engine);});
    }
    CHECK(scripts->GameLibrariesBound());Reject([&]{scripts->CreateLuaThread("unlocked");});CHECK(!scripts->Close());
    {GameCall game(*state);
        library.registration=[&](lua_State* lua){CHECK(lua_gettop(lua)==0 && engine.HasGameCoreLock());
            CHECK(!scripts->Close());Reject([&]{scripts->CreateLuaThread("registration reentry");});
            lua_pushinteger(lua,902);lua_setglobal(lua,"FixtureLibraryValue");
        };
        auto* vm=scripts->CreateLuaThread("registered");CHECK(Execute(*scripts,vm,"assert(FixtureLibraryValue==902)"));scripts->FreeLuaThread(vm);
        library.registration=[](lua_State*){throw std::runtime_error("library registration C++ failure");};
        Reject([&]{scripts->CreateLuaThread("cpp failure");});CHECK(scripts->ThreadCount()==0 && scripts->IsQuiescent());
        registeringSystem=scripts.get();
        library.registration=[](lua_State* lua){
            lua_newuserdata(lua,1);lua_newtable(lua);lua_pushcfunction(lua,FailedRegistrationFinalizer);
            lua_setfield(lua,-2,"__gc");lua_setmetatable(lua,-2);lua_setglobal(lua,"retained_failed_registration");
            luaL_error(lua,"library registration Lua failure");
        };
        Reject([&]{scripts->CreateLuaThread("lua failure");});
        CHECK(failedFinalizers==1 && scripts->ThreadCount()==0 && scripts->IsQuiescent() && !scripts->IsClosed());registeringSystem=nullptr;
        library.registration=[](lua_State* lua){lua_pushboolean(lua,1);lua_setglobal(lua,"RegistrationRecovered");};
        vm=scripts->CreateLuaThread("retry");CHECK(Execute(*scripts,vm,"assert(RegistrationRecovered)"));
        CHECK(scripts->Close() && !scripts->GameLibrariesBound() && scripts->ThreadCount()==0);
    }
    CHECK(library.registrations==4 && library.destroys==0);
    std::puts("SCRIPT_LIBRARY_BINDING_PASS FAILED_REGISTRATION_VM_PUBLISHED=false BORROWED_UTILITY_DESTROYED=false");
}
static unsigned Installed(const std::shared_ptr<const ScriptCatalog>& catalog){
    ScriptSystem scripts(nullptr,nullptr,catalog);unsigned maps=0;
    for(const auto& row:catalog->Files()){
        const auto& file=row.second;std::uint64_t hash=14695981039346656037ull;
        for(unsigned char byte:file.contents)hash=(hash^byte)*1099511628211ull;
        CHECK(catalog->Resolve(file.path.c_str())==&file && catalog->Resolve(file.origin.c_str())==&file);
        CHECK(catalog->Resolve(file.path.substr(file.path.find_last_of('/')+1).c_str())==&file);
        std::printf("SCRIPT_FILE path=%s bytes=%zu fnv=%016llx\n",file.path.c_str(),file.contents.size(),static_cast<unsigned long long>(hash));
        if(file.path.compare(0,5,"maps/")==0){
            const auto metadata=ReadMapScriptMetadata(scripts,file.path.c_str());
            CHECK(!metadata.name.empty() && !metadata.description.empty() && scripts.ThreadCount()==0);
            std::printf("MAP_METADATA path=%s name=%s description=%s options=%u\n",file.path.c_str(),metadata.name.c_str(),metadata.description.c_str(),metadata.customOptions);++maps;
        }
    }
    CHECK(!catalog->Resolve("missing.lua"));return maps;
}
int wmain(int argc,wchar_t** argv){
    try{
        if(argc!=2)throw std::invalid_argument("Expected the script catalog path");
        const auto bytes=Load(argv[1]);const auto malformed=CatalogFailures(bytes);
        Includes();IncludeLuaFailures();Libraries();auto catalog=std::make_shared<ScriptCatalog>(bytes);const auto maps=Installed(catalog);
        CHECK(GetModuleHandleW(L"CvGameCoreDLL_Expansion2_x64.dll")==nullptr);
        std::printf("HOST_SCRIPT_ASSETS_PASS checks=%u files=%zu maps=%u MALFORMED_CASES=%u GAMECORE_LOADED=false\n",checks,catalog->Size(),maps,malformed);return 0;
    }catch(const std::exception& error){std::fprintf(stderr,"SCRIPT_ASSETS_UNEXPECTED: %s\n",error.what());return 1;}
}
