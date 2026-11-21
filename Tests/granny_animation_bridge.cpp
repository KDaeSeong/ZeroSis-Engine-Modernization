#include "../Source/Animation/GrannyAnimationBridge.h"
#include <Windows.h>
#include <cmath>
#include <fstream>
#include <iostream>
#include <limits>
#include <sstream>
#include <string>
#include <thread>
#include <vector>

using GetVersionFn=uint32_t (__cdecl*)();
using OpenFn=int32_t (__cdecl*)(const wchar_t*,const wchar_t*,const wchar_t*,ZSGrannyBridge**);
using InfoFn=int32_t (__cdecl*)(ZSGrannyBridge*,uint32_t*,float*);
using NameFn=int32_t (__cdecl*)(ZSGrannyBridge*,uint32_t,wchar_t*,uint32_t,uint32_t*);
using CloseFn=int32_t (__cdecl*)(ZSGrannyBridge**);
using SampleFn=int32_t (__cdecl*)(ZSGrannyBridge*,uint32_t,float,float,uint32_t,uint32_t,ZSGrannySample*);
using ErrorFn=int32_t (__cdecl*)(wchar_t*,uint32_t,uint32_t*);
struct Reference { std::wstring name; float duration; float p[3],q[4],s[9]; };
static void require(bool ok,const char* message){if(!ok)throw std::runtime_error(message);}
static std::vector<Reference> read_reference(const wchar_t* path){
    std::ifstream in(path); require(in.good(),"cannot read t0 reference TSV"); std::vector<Reference> rows;std::string line;
    while(std::getline(in,line)){auto tab=line.find('\t');require(tab!=std::string::npos,"invalid reference row");Reference r{};
        r.name.assign(line.begin(),line.begin()+tab);std::istringstream values(line.substr(tab+1));values>>r.duration;
        for(float& v:r.p)values>>v;for(float& v:r.q)values>>v;for(float& v:r.s)values>>v;
        require(!values.fail(),"invalid numeric reference row");rows.push_back(r);}
    require(!rows.empty(),"empty t0 reference");return rows;
}
int wmain(int argc,wchar_t** argv){
    try {
        SetErrorMode(SEM_FAILCRITICALERRORS|SEM_NOGPFAULTERRORBOX|SEM_NOOPENFILEERRORBOX);
        HMODULE wer=LoadLibraryW(L"wer.dll"); if(wer){using WerFn=HRESULT (WINAPI*)(DWORD);auto f=reinterpret_cast<WerFn>(GetProcAddress(wer,"WerSetFlags"));if(f)f(1);FreeLibrary(wer);}
        require(argc==6,"usage: test dll gsd model animation t0.tsv");
        HMODULE dll=LoadLibraryW(argv[1]);require(dll!=nullptr,"LoadLibrary failed");
        auto version=reinterpret_cast<GetVersionFn>(GetProcAddress(dll,"ZSGrannyBridge_GetAbiVersion"));
        auto open=reinterpret_cast<OpenFn>(GetProcAddress(dll,"ZSGrannyBridge_Open"));
        auto info=reinterpret_cast<InfoFn>(GetProcAddress(dll,"ZSGrannyBridge_GetInfo"));
        auto name=reinterpret_cast<NameFn>(GetProcAddress(dll,"ZSGrannyBridge_GetTrackName"));
        auto sample=reinterpret_cast<SampleFn>(GetProcAddress(dll,"ZSGrannyBridge_Sample"));
        auto close=reinterpret_cast<CloseFn>(GetProcAddress(dll,"ZSGrannyBridge_Close"));
        auto lastError=reinterpret_cast<ErrorFn>(GetProcAddress(dll,"ZSGrannyBridge_GetLastError"));
        require(version&&open&&info&&name&&sample&&close&&lastError,"C ABI export missing");
        require(version()==ZS_GRANNY_BRIDGE_ABI_VERSION,"ABI version mismatch");
        wchar_t cwdBefore[32768]{},dllBefore[32768]{},cwdAfter[32768]{},dllAfter[32768]{};
        GetCurrentDirectoryW(32768,cwdBefore);DWORD db=GetDllDirectoryW(32768,dllBefore);
        if(db>=32768)throw std::runtime_error("loader directory unexpectedly oversized");
        ZSGrannyBridge* h=nullptr;int32_t openStatus=open(argv[2],argv[3],argv[4],&h);
        if(openStatus!=ZS_GRANNY_OK||!h){uint32_t n=0;lastError(nullptr,0,&n);std::vector<wchar_t> msg(n?n:2);lastError(msg.data(),static_cast<uint32_t>(msg.size()),&n);
            std::wcerr<<L"OPEN_STATUS="<<openStatus<<L" ERROR="<<msg.data()<<L"\n";throw std::runtime_error("open failed");}
        uint32_t count=0;float duration=0;require(info(h,&count,&duration)==ZS_GRANNY_OK&&count>0,"info failed");
        auto refs=read_reference(argv[5]);require(refs.size()==count,"t0 reference track count differs");
        uint32_t pelvis=UINT32_MAX;bool anyChanged=false;
        for(const auto& ref:refs){require(std::abs(duration-ref.duration)<1e-4f,"duration differs from x86 export");uint32_t expected=UINT32_MAX;
            for(uint32_t i=0;i<count;++i){uint32_t need=0;require(name(h,i,nullptr,0,&need)==ZS_GRANNY_BAD_VERSION_OR_SIZE&&need>1&&need<512,"name sizing failed");
                wchar_t text[512]{};require(name(h,i,text,512,&need)==ZS_GRANNY_OK,"name fetch failed");if(ref.name==text){expected=i;break;}}
            require(expected!=UINT32_MAX,"reference track not found");if(ref.name==L"Base HumanPelvis")pelvis=expected;
            ZSGrannySample out{};require(sample(h,expected,0,duration,1,sizeof(out),&out)==ZS_GRANNY_OK,"t0 sample failed");
            for(int i=0;i<3;++i)require(std::abs(out.position[i]-ref.p[i])<1e-4f,"t0 position differs");
            for(int i=0;i<4;++i)require(std::abs(out.orientation[i]-ref.q[i])<1e-4f,"t0 orientation differs");
            for(int i=0;i<9;++i)require(std::abs(out.scale_shear[i]-ref.s[i])<1e-4f,"t0 scale/shear differs");
            ZSGrannySample mid{};require(sample(h,expected,duration*0.5f,duration,1,sizeof(mid),&mid)==ZS_GRANNY_OK,"midpoint sample failed");
            bool changed=false;for(int i=0;i<3;++i)changed|=std::abs(mid.position[i]-out.position[i])>1e-6f;
            for(int i=0;i<4;++i)changed|=std::abs(mid.orientation[i]-out.orientation[i])>1e-6f;
            for(int i=0;i<9;++i)changed|=std::abs(mid.scale_shear[i]-out.scale_shear[i])>1e-6f;anyChanged|=changed;
            if(ref.name==L"Base HumanPelvis")require(changed,"Base HumanPelvis midpoint did not change");
        }
        require(pelvis!=UINT32_MAX&&anyChanged,"no changing animation track found");
        ZSGrannySample bad{};require(sample(h,pelvis,-1,duration,1,sizeof(bad),&bad)!=ZS_GRANNY_OK,"negative time accepted");
        require(bad.version==0&&bad.size==0,"failed call did not clear output");
        require(sample(h,pelvis,duration+0.01f,duration,1,sizeof(bad),&bad)!=ZS_GRANNY_OK,"out-of-range time accepted");
        require(sample(h,pelvis,0,duration+1,1,sizeof(bad),&bad)!=ZS_GRANNY_OK,"mismatched duration accepted");
        require(sample(h,pelvis,std::numeric_limits<float>::quiet_NaN(),duration,1,sizeof(bad),&bad)!=ZS_GRANNY_OK,"NaN time accepted");
        require(sample(h,pelvis,0,std::numeric_limits<float>::infinity(),1,sizeof(bad),&bad)!=ZS_GRANNY_OK,"infinite duration accepted");
        require(sample(h,count,0,duration,1,sizeof(bad),&bad)!=ZS_GRANNY_OK,"out-of-range track index accepted");
        require(sample(h,pelvis,0,duration,2,sizeof(bad),&bad)==ZS_GRANNY_BAD_VERSION_OR_SIZE,"bad version accepted");
        require(bad.version==0&&bad.size==0,"bad version output not cleared");
        struct Canary { uint32_t before; unsigned char tiny[8]; uint32_t after; } canary{0x12345678,{1,2,3,4,5,6,7,8},0x87654321};
        require(sample(h,pelvis,0,duration,1,sizeof(canary.tiny),reinterpret_cast<ZSGrannySample*>(canary.tiny))==ZS_GRANNY_BAD_VERSION_OR_SIZE,"short output buffer accepted");
        require(canary.before==0x12345678&&canary.after==0x87654321,"short output write crossed declared size");
        int32_t foreign=ZS_GRANNY_OK,foreignClose=ZS_GRANNY_OK,foreignOpen=ZS_GRANNY_OK;ZSGrannyBridge* foreignValue=h,*foreignNew=nullptr;
        std::thread worker([&]{foreignOpen=open(argv[2],argv[3],argv[4],&foreignNew);ZSGrannySample s{};foreign=sample(h,pelvis,0,duration,1,sizeof(s),&s);foreignClose=close(&foreignValue);});worker.join();
        require(foreignOpen==ZS_GRANNY_WRONG_THREAD&&foreignNew==nullptr,"foreign-thread open was not rejected before SDK use");
        require(foreign==ZS_GRANNY_WRONG_THREAD,"foreign thread was not rejected");
        require(foreignClose==ZS_GRANNY_WRONG_THREAD&&foreignValue==h,"foreign close was not rejected safely");
        ZSGrannyBridge* alias=h;require(close(&h)==ZS_GRANNY_OK&&h==nullptr,"close failed");require(close(&h)==ZS_GRANNY_OK,"idempotent close failed");
        require(sample(alias,pelvis,0,duration,1,sizeof(bad),&bad)==ZS_GRANNY_INVALID_ARGUMENT,"closed alias was accepted");
        ZSGrannyBridge* fake=reinterpret_cast<ZSGrannyBridge*>(static_cast<uintptr_t>(0x12345));require(sample(fake,0,0,duration,1,sizeof(bad),&bad)==ZS_GRANNY_INVALID_ARGUMENT,"invalid handle was dereferenced or accepted");
        require(close(&alias)==ZS_GRANNY_INVALID_ARGUMENT,"closed alias close was accepted");
        for(int i=0;i<2;++i){ZSGrannyBridge* again=nullptr;require(open(argv[2],argv[3],argv[4],&again)==ZS_GRANNY_OK&&again,"reopen failed");require(close(&again)==ZS_GRANNY_OK&&again==nullptr,"reopen close failed");}
        GetCurrentDirectoryW(32768,cwdAfter);DWORD da=GetDllDirectoryW(32768,dllAfter);
        require(std::wstring(cwdBefore)==cwdAfter&&db==da&&std::wstring(dllBefore)==dllAfter,"bridge changed process cwd or DLL directory");
        FreeLibrary(dll);std::cout<<"PASS_NATIVE_GRANNY_C_ABI_X64 tracks="<<count<<" curves="<<count*3<<" duration="<<duration<<"\n";return 0;
    } catch(const std::exception& e){std::cerr<<"FAIL: "<<e.what()<<"\n";return 1;}
}
