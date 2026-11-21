#include "sdk_world_builder_map_file_host.h"

std::vector<byte> worldMapFile;
bool worldMapTraceIO = false;
namespace {
void Unsupported() { std::fputs("UNEXPECTED_FILE_TRANSPORT_CALL\n",stderr);std::abort(); }
class MemoryFile : public FIFile {
    uint pos;bool opened;OpenMode mode;
public:
    MemoryFile() : pos(0),opened(false),mode(modeRead) {}
    virtual FileErr Open(const char*,OpenMode,dword,uint) { Unsupported();return FILE_BADNAME; }
    virtual FileErr Open(const wchar* name,OpenMode m,dword,uint) {
        if(!name || std::wcscmp(name,L"memory")) { Unsupported();return FILE_BADNAME; }
        pos=0;mode=m;opened=true;if(m==modeWrite)worldMapFile.clear();return FILE_OK;
    }
    virtual FileErr Close() { opened=false;return FILE_OK; }
    virtual const wchar_t* GetFileName() { return L"memory"; }
    virtual byte* GetViewCaret() const { return worldMapFile.empty()?NULL:&worldMapFile[0]+pos; }
    virtual byte* GetViewEnd() const { return worldMapFile.empty()?NULL:&worldMapFile[0]+worldMapFile.size(); }
    virtual byte* GetViewPtr() const { return worldMapFile.empty()?NULL:&worldMapFile[0]; }
    virtual uint GetLength() const { return static_cast<uint>(worldMapFile.size()); }
    virtual void SetLength(uint n) { worldMapFile.resize(n); }
    virtual bool IsOpen() const { return opened; }
    virtual bool IsMapped() const { return false; }
    virtual uint Seek(long off,SeekMode origin) {
        const __int64 base=origin==begin?0:origin==current?pos:worldMapFile.size();
        const __int64 next=base+off;
        if(next<0 || next>UINT_MAX)Unsupported();
        pos=static_cast<uint>(next);return pos;
    }
    virtual uint SeekToBegin() { return Seek(0,begin); }
    virtual uint SeekToEnd() { return Seek(0,end); }
    virtual uint GetPosition() { return pos; }
    virtual void Rewind() { pos=0; }
    virtual bool IsEOF() { return pos>=worldMapFile.size(); }
    virtual uint Read(void* dest,uint size) {
        const uint n=pos>=worldMapFile.size()?0:std::min(size,static_cast<uint>(worldMapFile.size()-pos));
        if(worldMapTraceIO)std::printf("IO|R|%u|%u|%u\n",pos,size,n);
        if(n)std::memcpy(dest,&worldMapFile[pos],n);pos+=n;return n;
    }
    virtual uint Write(const void* src,uint size) {
        if(!opened || mode==modeRead || size>UINT_MAX-pos)Unsupported();
        if(worldMapTraceIO)std::printf("IO|W|%u|%u\n",pos,size);
        if(size){if(worldMapFile.size()<pos+size)worldMapFile.resize(pos+size);std::memcpy(&worldMapFile[pos],src,size);}pos+=size;return size;
    }
    virtual uint Flush() { return 0; }
};
class MemoryFileSystem : public FIFileSystem {
public:
    virtual FIFile* Create(const char*,FIFile::OpenMode,dword,uint) { Unsupported();return NULL; }
    virtual FIFile* Create(const wchar* p,FIFile::OpenMode m,dword flags,uint size) {
        MemoryFile* f=new MemoryFile;if(p)f->Open(p,m,flags,size);return f;
    }
    virtual FileErr Delete(const char*) { Unsupported();return FILE_BADNAME; }
    virtual FileErr Delete(const wchar*) { Unsupported();return FILE_BADNAME; }
    virtual FileErr ReadAll(const char*,byte**,size_t*,dword) { Unsupported();return FILE_BADNAME; }
    virtual FileErr ReadAll(const wchar*,byte**,size_t*,dword) { Unsupported();return FILE_BADNAME; }
    virtual FileErr ReadAll(const char*,byte**,size_t*,dword,FIFile::Allocator&) { Unsupported();return FILE_BADNAME; }
    virtual FileErr ReadAll(const wchar*,byte**,size_t*,dword,FIFile::Allocator&) { Unsupported();return FILE_BADNAME; }
    virtual bool Exist(const char*) { Unsupported();return false; }
    virtual bool Exist(const wchar*) { Unsupported();return false; }
    virtual uint GetLength(const char*) { Unsupported();return 0; }
    virtual uint GetLength(const wchar*) { Unsupported();return 0; }
    virtual FFileTimestamp GetLastWriteTime(const char*) { Unsupported();FILETIME t={0,0};return FFileTimestamp(t); }
    virtual bool IsFileCatalogEnabled() { return false; }
    virtual FFileErrorHandler* GetErrorHandler() { Unsupported();return NULL; }
};
MemoryFileSystem& GetHost() { static MemoryFileSystem host;return host; }
}
extern "C" __declspec(dllexport) FIFileSystem* GetFileSystemMgr() { return &GetHost(); }
void InstallWorldMapFileHost() { FIFileSystem::SetInstance(&GetHost()); }
