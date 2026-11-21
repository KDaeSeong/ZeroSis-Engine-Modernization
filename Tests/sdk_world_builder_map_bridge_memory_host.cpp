// Reuse the sealed x86 reference transport. VC9 required return statements
// after its aborting Unsupported() helper; modern /W4 diagnoses those returns.
// This suppression covers only that test transport, never production code.
#pragma warning(push)
#pragma warning(disable:4702)
#include "sdk_world_builder_map_file_host.cpp"
#pragma warning(pop)
#include "sdk_world_builder_map_bridge_fault_host.h"

MapIoControl mapIo;
namespace {
class FaultMapFile:public MemoryFile {
public:
    FaultMapFile(){++mapIo.live;}
    ~FaultMapFile(){--mapIo.live;}
    uint GetLength()const override{
        if(mapIo.fault==MapIoFault::LengthThrow)throw std::runtime_error("Injected length failure");
        return mapIo.fault==MapIoFault::LengthZero?0:MemoryFile::GetLength();
    }
    uint Read(void* dest,uint length)override{
        if(GetPosition()>=mapIo.failAfter){
            if(mapIo.fault==MapIoFault::ReadZero)return 0;
            if(mapIo.fault==MapIoFault::ReadOver)return length+1;
            if(mapIo.fault==MapIoFault::ReadThrow)throw std::runtime_error("Injected read failure");
        }
        return MemoryFile::Read(dest,std::min(length,mapIo.chunk));
    }
    uint Write(const void* src,uint length)override{
        if(GetPosition()>=mapIo.failAfter){
            if(mapIo.fault==MapIoFault::WriteZero)return 0;
            if(mapIo.fault==MapIoFault::WriteOver)return length+1;
            if(mapIo.fault==MapIoFault::WriteThrow)throw std::runtime_error("Injected write failure");
        }
        return MemoryFile::Write(src,std::min(length,mapIo.chunk));
    }
    FileErr Close()override{
        ++mapIo.closed;MemoryFile::Close();
        if(mapIo.fault==MapIoFault::CloseThrow)throw std::runtime_error("Injected close failure");
        return mapIo.fault==MapIoFault::CloseBad?FILE_BADNAME:FILE_OK;
    }
};
class FaultMapFileSystem:public MemoryFileSystem {
public:
    FIFile* Create(const wchar* path,FIFile::OpenMode mode,dword flags,uint size)override{
        ++mapIo.created;
        if(mapIo.fault==MapIoFault::CreateNull)return NULL;
        if(mapIo.fault==MapIoFault::CreateThrow)throw std::runtime_error("Injected create failure");
        FaultMapFile* file=new FaultMapFile;
        if(mapIo.fault!=MapIoFault::CreateClosed)file->Open(path,mode,flags,size);
        return file;
    }
};
}
void InstallFaultMapFileHost(){static FaultMapFileSystem host;FIFileSystem::SetInstance(&host);}
