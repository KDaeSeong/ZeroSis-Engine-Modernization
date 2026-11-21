// Actual SDK map Save/Load/Preview linked to the native filesystem provider.
#include "map_fixture_bridge.h"
#include "SdkWorldBuilderMapBridge.h"
#include "sdk_filesystem_faults.h"

static std::vector<byte> DiskRead(const std::wstring& path) {
    HANDLE h=CreateFileW(path.c_str(),GENERIC_READ,FILE_SHARE_READ|FILE_SHARE_DELETE,nullptr,OPEN_EXISTING,FILE_ATTRIBUTE_NORMAL,nullptr);
    CHECK(h!=INVALID_HANDLE_VALUE);LARGE_INTEGER size{};CHECK(GetFileSizeEx(h,&size));CHECK(size.QuadPart<1000000);
    std::vector<byte> data(static_cast<size_t>(size.QuadPart));DWORD got=0;
    CHECK(ReadFile(h,data.data(),static_cast<DWORD>(data.size()),&got,nullptr));CHECK(got==data.size());CHECK(CloseHandle(h));return data;
}
int wmain(int argc,wchar_t** argv) {
    (void)&Dump;(void)&SourceTypes;(void)&SemanticHash;
    CHECK(argc==2);const std::wstring root=argv[1],path=root+L"\\native_map.Civ5Map";
    CvWorldBuilderMapTypeDesc types;Types(types);
    std::unique_ptr<CvWorldBuilderMap> source(new CvWorldBuilderMap);
    std::memset(source->m_aiCityStateInfluence,0,sizeof(source->m_aiCityStateInfluence));Populate(*source);
    const auto before=ZeroSisWorldBuilder::SaveMapBytes(*source,types,true);
    CHECK(source->Save(path.c_str(),types,true));CHECK(DiskRead(path)==before);
    CHECK(CvWorldBuilderMap::PreviewPlayableCivCount(path.c_str())==2);
    std::unique_ptr<CvWorldBuilderMap> loaded(new CvWorldBuilderMap);
    CHECK(loaded->Load(path.c_str(),types,true));CHECK(ZeroSisWorldBuilder::SaveMapBytes(*loaded,types,true)==before);
    source->SetStartYear(-1999);const auto changed=ZeroSisWorldBuilder::SaveMapBytes(*source,types,true);
    CHECK(changed!=before);
    unsigned failures=0;
    for(const auto fault:{FsFault::Open,FsFault::Write,FsFault::WriteZero,FsFault::WriteOver,FsFault::Flush,FsFault::Close,FsFault::Commit}) {
        FaultFileApi api;ZeroSisFileSystem::NativeFileSystem fs(api);FIFileSystem::SetInstance(&fs);
        api.fault=fault;api.chunk=7;api.failAfter=(fault==FsFault::Write || fault==FsFault::WriteZero || fault==FsFault::WriteOver)?2:0;
        CHECK(!source->Save(path.c_str(),types,true));CHECK(DiskRead(path)==before);
        CHECK(api.live==0);FIFileSystem::SetInstance(nullptr);++failures;
    }
    for(const auto fault:{FsFault::Open,FsFault::Read,FsFault::ReadZero,FsFault::ReadOver,FsFault::Close}) {
        FaultFileApi api;ZeroSisFileSystem::NativeFileSystem fs(api);FIFileSystem::SetInstance(&fs);
        api.fault=fault;api.chunk=7;api.failAfter=fault==FsFault::Open || fault==FsFault::Close?0:2;
        CHECK(!source->Load(path.c_str(),types,true));CHECK(ZeroSisWorldBuilder::SaveMapBytes(*source,types,true)==changed);
        CHECK(api.live==0);FIFileSystem::SetInstance(nullptr);++failures;
    }
    CHECK(source->Save(path.c_str(),types,true));CHECK(DiskRead(path)==changed);
    CHECK(loaded->Load(path.c_str(),types,true));CHECK(ZeroSisWorldBuilder::SaveMapBytes(*loaded,types,true)==changed);
    const auto retained=ZeroSisWorldBuilder::SaveMapBytes(*loaded,types,true);
    FaultFileApi api;ZeroSisFileSystem::NativeFileSystem fs(api);FIFileSystem::SetInstance(&fs);api.chunk=3;
    CHECK(loaded->Load(path.c_str(),types,true));CHECK(loaded->Save(path.c_str(),types,true));CHECK(DiskRead(path)==retained);
    CHECK(!api.live);FIFileSystem::SetInstance(nullptr);
    std::printf("MAP_NATIVE_IO|%u_failure_cases|file_and_object_preserved|3_byte_chunks\n",failures);
    std::printf("PASS|%u\n",checks);return 0;
}
