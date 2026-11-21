#include "NativeSaveArchive.h"

namespace {
struct DeleteHandleProbe final {
    bool active=false,exclusive=false,sameHandle=false,renameBlocked=false,writerBlocked=false;
    unsigned opens=0,reads=0,dispositions=0;HANDLE file=INVALID_HANDLE_VALUE;std::wstring path;
} deleteProbe;
struct ReplacementProbe final {
    bool active=false,sourceExclusive=false,failRollback=false;
    unsigned renames=0,disposals=0,flushes=0,failRename=0,failDispose=0,failFlush=0;
    std::vector<unsigned char> collision;std::string crash;
    void (*journalObservation)(void*)=nullptr;void* observationState=nullptr;
    bool holdStageReopen=false;HANDLE heldStage=INVALID_HANDLE_VALUE;
} replaceProbe;
void ReplacementCrash(const char* phase){
    if(replaceProbe.active && replaceProbe.crash==phase){
        std::fflush(nullptr);TerminateProcess(GetCurrentProcess(),91);std::abort();
    }
}
HANDLE WINAPI CatalogTestCreateFileW(LPCWSTR path,DWORD access,DWORD sharing,LPSECURITY_ATTRIBUTES security,
        DWORD creation,DWORD flags,HANDLE templateFile){
    const auto value=::CreateFileW(path,access,sharing,security,creation,flags,templateFile);
    if(deleteProbe.active && std::wstring(path).find(L".zssave")!=std::wstring::npos){
        ++deleteProbe.opens;deleteProbe.file=value;deleteProbe.path=path;
        deleteProbe.exclusive=access==(GENERIC_READ|DELETE) && sharing==0 && creation==OPEN_EXISTING &&
            (flags&FILE_FLAG_OPEN_REPARSE_POINT)!=0;
    }
    if(replaceProbe.active && std::wstring(path).find(L".zssave")!=std::wstring::npos && creation==OPEN_EXISTING)
        replaceProbe.sourceExclusive=access==(GENERIC_READ|DELETE) && sharing==0 &&
            (flags&FILE_FLAG_OPEN_REPARSE_POINT)!=0;
    return value;
}
BOOL WINAPI CatalogTestReadFile(HANDLE file,LPVOID buffer,DWORD count,LPDWORD read,LPOVERLAPPED overlap){
    if(deleteProbe.active && file==deleteProbe.file)++deleteProbe.reads;
    return ::ReadFile(file,buffer,count,read,overlap);
}
BOOL WINAPI CatalogTestSetFileInformationByHandle(HANDLE file,FILE_INFO_BY_HANDLE_CLASS kind,LPVOID info,DWORD bytes){
    if(deleteProbe.active && kind==FileDispositionInfo){
        ++deleteProbe.dispositions;deleteProbe.sameHandle=file==deleteProbe.file && deleteProbe.reads>0;
        const auto moved=deleteProbe.path+L".owned-race";
        const BOOL renamed=::MoveFileExW(deleteProbe.path.c_str(),moved.c_str(),0);
        deleteProbe.renameBlocked=!renamed && GetLastError()==ERROR_SHARING_VIOLATION;
        if(renamed)::MoveFileExW(moved.c_str(),deleteProbe.path.c_str(),0);
        const HANDLE writer=::CreateFileW(deleteProbe.path.c_str(),GENERIC_WRITE|DELETE,
            FILE_SHARE_READ|FILE_SHARE_WRITE|FILE_SHARE_DELETE,nullptr,OPEN_EXISTING,FILE_ATTRIBUTE_NORMAL,nullptr);
        deleteProbe.writerBlocked=writer==INVALID_HANDLE_VALUE && GetLastError()==ERROR_SHARING_VIOLATION;
        if(writer!=INVALID_HANDLE_VALUE)::CloseHandle(writer);
    }
    if(replaceProbe.active && kind==FileRenameInfo){
        ++replaceProbe.renames;
        if(replaceProbe.renames==2 && !replaceProbe.collision.empty()){
            const auto* rename=static_cast<const FILE_RENAME_INFO*>(info);
            const std::wstring path(rename->FileName,rename->FileNameLength/sizeof(wchar_t));
            const HANDLE foreign=::CreateFileW(path.c_str(),GENERIC_WRITE,0,nullptr,CREATE_NEW,FILE_ATTRIBUTE_NORMAL,nullptr);
            if(foreign==INVALID_HANDLE_VALUE)throw std::runtime_error("Cannot inject own collision file");
            DWORD written=0;const BOOL okay=::WriteFile(foreign,replaceProbe.collision.data(),static_cast<DWORD>(replaceProbe.collision.size()),&written,nullptr);
            const BOOL flushed=::FlushFileBuffers(foreign);::CloseHandle(foreign);
            if(!okay || written!=replaceProbe.collision.size() || !flushed)throw std::runtime_error("Cannot persist own collision file");
        }
        if(replaceProbe.renames==replaceProbe.failRename || (replaceProbe.renames==3 && replaceProbe.failRollback)){
            SetLastError(ERROR_ACCESS_DENIED);return FALSE;
        }
    }
    if(replaceProbe.active && kind==FileDispositionInfo){
        ++replaceProbe.disposals;if(replaceProbe.disposals==replaceProbe.failDispose){SetLastError(ERROR_ACCESS_DENIED);return FALSE;}
    }
    const BOOL result=::SetFileInformationByHandle(file,kind,info,bytes);
    if(result && replaceProbe.active){
        if(kind==FileRenameInfo)ReplacementCrash(replaceProbe.renames==1?"old":"new");
        if(kind==FileDispositionInfo)ReplacementCrash(replaceProbe.disposals==1?"old-cleanup":"journal-cleanup");
    }
    return result;
}
BOOL WINAPI CatalogTestFlushFileBuffers(HANDLE file){
    if(replaceProbe.active){
        ++replaceProbe.flushes;
        if(replaceProbe.flushes==replaceProbe.failFlush){SetLastError(ERROR_WRITE_FAULT);return FALSE;}
    }
    const BOOL result=::FlushFileBuffers(file);
    if(result && replaceProbe.active && replaceProbe.flushes==2 && replaceProbe.journalObservation)
        replaceProbe.journalObservation(replaceProbe.observationState);
    if(result && replaceProbe.active)ReplacementCrash(replaceProbe.flushes==1?"stage":"journal");
    return result;
}
BOOL WINAPI CatalogTestCloseHandle(HANDLE file){
    wchar_t path[32768]{};
    const bool inspect=replaceProbe.active && replaceProbe.holdStageReopen && replaceProbe.heldStage==INVALID_HANDLE_VALUE;
    const DWORD count=inspect?::GetFinalPathNameByHandleW(file,path,32768,0):0;
    const BOOL result=::CloseHandle(file);
    if(result && inspect && count && count<32768){
        const std::wstring name(path,count);
        if(name.size()>=6 && name.substr(name.size()-6)==L".stage")
            replaceProbe.heldStage=::CreateFileW(path,GENERIC_READ,FILE_SHARE_READ,nullptr,OPEN_EXISTING,FILE_FLAG_OPEN_REPARSE_POINT,nullptr);
    }
    return result;
}
}
#define CreateFileW CatalogTestCreateFileW
#define ReadFile CatalogTestReadFile
#define SetFileInformationByHandle CatalogTestSetFileInformationByHandle
#define FlushFileBuffers CatalogTestFlushFileBuffers
#define CloseHandle CatalogTestCloseHandle
#include "NativeSaveCatalog.h"
#undef CloseHandle
#undef FlushFileBuffers
#undef SetFileInformationByHandle
#undef ReadFile
#undef CreateFileW
#include <winioctl.h>
#include <werapi.h>
#include <atomic>
#include <cstdio>
#include <thread>

using ZeroSisHost::NativeSaveArchive;
using ZeroSisHost::NativeSaveCatalog;
using ZeroSisHost::UiSaveMenuHeader;

namespace {
int checks=0;
void Require(bool value,const char* message){++checks;if(!value)throw std::runtime_error(message);}
template<class Function> void Rejects(Function&& function,const char* message){
    bool caught=false;try{function();}catch(const std::exception&){caught=true;}Require(caught,message);
}
std::wstring Wide(const char* value){
    const int count=MultiByteToWideChar(CP_UTF8,MB_ERR_INVALID_CHARS,value,-1,nullptr,0);
    if(count<2)throw std::invalid_argument("Expected an existing unique fixture directory");
    std::vector<wchar_t> text(static_cast<std::size_t>(count));
    if(MultiByteToWideChar(CP_UTF8,MB_ERR_INVALID_CHARS,value,-1,text.data(),count)!=count)
        throw std::runtime_error("Fixture directory conversion failed");
    return std::wstring(text.data());
}
NativeSaveArchive Archive(unsigned seed){
    NativeSaveArchive archive;archive.turn=100+static_cast<int>(seed);archive.elapsed=200+static_cast<int>(seed);archive.activePlayer=0;
    for(unsigned at=0;at<NativeSaveArchive::SectionCount();++at){
        const unsigned kind=at<5?at+1:(at<5+MAX_TEAMS?NativeSaveArchive::Team:NativeSaveArchive::Player);
        const unsigned index=at<5?0:(at<5+MAX_TEAMS?at-5:at-5-MAX_TEAMS);
        archive.sections.push_back({kind,index,{0,static_cast<unsigned char>(seed),static_cast<unsigned char>(at),128,255}});
    }
    return archive;
}
UiSaveMenuHeader Header(const NativeSaveArchive& archive){
    UiSaveMenuHeader header;header.playerCivilization=1;header.gameSpeed=2;header.startEra=3;
    header.turnNumber=archive.elapsed;header.difficulty=4;header.worldSize=5;header.currentEra=6;
    header.gameType=static_cast<int>(GAME_SINGLE_PLAYER);header.mapScript="fixture-map.lua";
    header.leaderName="Fixture leader";header.civilizationName="Fixture civilization";return header;
}
unsigned Temporaries(const std::wstring& directory){
    WIN32_FIND_DATAW data{};HANDLE search=FindFirstFileW((directory+L"\\*.tmp-*").c_str(),&data);
    if(search==INVALID_HANDLE_VALUE){Require(GetLastError()==ERROR_FILE_NOT_FOUND,"Temporary scan failed");return 0;}
    unsigned count=0;do{++count;}while(FindNextFileW(search,&data));
    const auto error=GetLastError();FindClose(search);Require(error==ERROR_NO_MORE_FILES,"Temporary scan interrupted");return count;
}
void MakeDirectory(const std::wstring& path){Require(CreateDirectoryW(path.c_str(),nullptr)!=FALSE,"Cannot create an owned fixture directory");}
void MakeJunction(const std::wstring& alias,const std::wstring& target){
    MakeDirectory(alias);
    HANDLE file=CreateFileW(alias.c_str(),GENERIC_WRITE,0,nullptr,OPEN_EXISTING,
        FILE_FLAG_BACKUP_SEMANTICS|FILE_FLAG_OPEN_REPARSE_POINT,nullptr);
    Require(file!=INVALID_HANDLE_VALUE,"Cannot open owned junction fixture");
    struct Buffer final {
        DWORD tag;WORD length,reserved,substituteOffset,substituteLength,printOffset,printLength;wchar_t path[1];
    };
    const auto substitute=L"\\??\\"+target;
    const auto substituteBytes=substitute.size()*sizeof(wchar_t),printBytes=target.size()*sizeof(wchar_t);
    std::vector<unsigned char> bytes(offsetof(Buffer,path)+substituteBytes+sizeof(wchar_t)+printBytes+sizeof(wchar_t));
    auto* buffer=reinterpret_cast<Buffer*>(bytes.data());buffer->tag=IO_REPARSE_TAG_MOUNT_POINT;
    buffer->length=static_cast<WORD>(bytes.size()-8);buffer->substituteOffset=0;
    buffer->substituteLength=static_cast<WORD>(substituteBytes);buffer->printOffset=static_cast<WORD>(substituteBytes+sizeof(wchar_t));
    buffer->printLength=static_cast<WORD>(printBytes);
    std::memcpy(buffer->path,substitute.data(),substituteBytes);
    std::memcpy(reinterpret_cast<unsigned char*>(buffer->path)+buffer->printOffset,target.data(),printBytes);
    DWORD returned=0;const BOOL result=DeviceIoControl(file,FSCTL_SET_REPARSE_POINT,bytes.data(),static_cast<DWORD>(bytes.size()),nullptr,0,&returned,nullptr);
    const auto error=GetLastError();CloseHandle(file);
    if(!result){RemoveDirectoryW(alias.c_str());throw std::runtime_error("Owned junction setup failed: "+std::to_string(error));}
    Require(true,"Owned junction created");
}
void TestNames(){
    Require(NativeSaveCatalog::DecodeName("ordinary name")==L"ordinary name","Ordinary save name differs");
    const std::string korean="\xED\x95\x9C\xEA\xB8\x80 \xEC\xA0\x80\xEC\x9E\xA5";
    Require(NativeSaveCatalog::DecodeName(korean)==L"\uD55C\uAE00 \uC800\uC7A5","Korean save name differs");
    std::string scalar32;for(unsigned at=0;at<32;++at)scalar32+="\xF0\x9F\x8F\x9B";
    Require(NativeSaveCatalog::DecodeName(scalar32).size()==64,"Supplementary Unicode scalar count differs");
    Rejects([&]{NativeSaveCatalog::DecodeName(scalar32+"A");},"33-scalar save name accepted");
    const std::vector<std::string> invalid={""," ","..",".hidden","trailing."," leading","trailing ","../escape","a/b","a\\b",
        "C:drive","a<b","a>b","a|b","a?b","a*b","a\"b","CON","con.txt","NUL","aux","PRN","COM1","lpt9.txt",
        "CONIN$","CONOUT$",std::string("COM")+"\xC2\xB9",std::string("a\0b",3),"a\n","\xC0\xAF","\xED\xA0\x80","\xF4\x90\x80\x80"};
    for(const auto& value:invalid)Rejects([&]{NativeSaveCatalog::DecodeName(value);},"Unsafe save name accepted");
}
void TestModificationTimeComparison(){
    static_assert(noexcept(NativeSaveCatalog::CompareModificationTimes(0,0,0,0)),
        "File-time comparison must not throw across the UI boundary");
    const auto maximum=std::numeric_limits<std::uint32_t>::max();
    struct Case final {std::uint32_t firstHigh,firstLow,secondHigh,secondLow;int expected;};
    const Case cases[]={
        {0,0,0,0,0},
        {maximum,maximum,maximum,maximum,0},
        {0,0,0,1,-1},
        {0,0x7FFFFFFFu,0,0x80000000u,-1},
        {0,maximum,1,0,-1},
        {0x7FFFFFFFu,maximum,0x80000000u,0,-1},
        {maximum,0,maximum,maximum,-1},
        {0,0,maximum,maximum,-1},
        {0x00200000u,0,0x00200000u,1,-1},
        {0x01DC0000u,0x10203040u,0x01DC0000u,0x10203041u,-1},
        {0x01DC0000u,maximum,0x01DC0001u,0,-1}
    };
    for(const auto& value:cases){
        const auto actual=NativeSaveCatalog::CompareModificationTimes(value.firstHigh,value.firstLow,
            value.secondHigh,value.secondLow);
        Require(actual==value.expected,"Unsigned native file-time boundary or low-word precision differs");
        const FILETIME first{static_cast<DWORD>(value.firstLow),static_cast<DWORD>(value.firstHigh)};
        const FILETIME second{static_cast<DWORD>(value.secondLow),static_cast<DWORD>(value.secondHigh)};
        Require(actual==static_cast<int>(::CompareFileTime(&first,&second)),"Native file-time order differs from Win32");
        Require(NativeSaveCatalog::CompareModificationTimes(value.secondHigh,value.secondLow,
            value.firstHigh,value.firstLow)==-value.expected,"Reversed native file-time order differs");
    }
    const ZeroSisHost::UiSaveMenuFile empty{};
    Require(empty.modificationTimeHigh==0 && empty.modificationTimeLow==0,"Empty saved-game raw time is not zero initialized");
}
void SetWriteTime(const std::wstring& path,const FILETIME& time){
    const auto value=CreateFileW(path.c_str(),FILE_WRITE_ATTRIBUTES|FILE_READ_ATTRIBUTES,FILE_SHARE_READ,nullptr,
        OPEN_EXISTING,FILE_ATTRIBUTE_NORMAL|FILE_FLAG_OPEN_REPARSE_POINT,nullptr);
    Require(value!=INVALID_HANDLE_VALUE,"Cannot open an owned file-time fixture");
    struct File final {HANDLE value;~File(){CloseHandle(value);}} file{value};
    Require(SetFileTime(value,nullptr,nullptr,&time)!=FALSE,"Cannot set the owned fixture write time");
    FILETIME observed{};
    Require(GetFileTime(value,nullptr,nullptr,&observed)!=FALSE,"Cannot read the owned fixture write time");
    Require(observed.dwHighDateTime==time.dwHighDateTime && observed.dwLowDateTime==time.dwLowDateTime,
        "Owned fixture write time lost raw FILETIME precision");
}
void TestModificationTimeCatalog(const std::wstring& directory){
    const auto session=directory+L"\\filetime-session";MakeDirectory(session);
    NativeSaveCatalog catalog(session);const auto archive=Archive(7);const auto bytes=archive.Encode();
    const auto earlierPath=catalog.WriteNew("earlier",archive,Header(archive));
    const auto laterPath=catalog.WriteNew("later",archive,Header(archive));
    const auto beforeEarlier=catalog.Find(earlierPath),beforeLater=catalog.Find(laterPath);
    Require(beforeEarlier.header && beforeLater.header,"Owned file-time fixtures lack their original cached headers");
    const FILETIME earlier{0x10203040u,0x01DC0000u},later{0x10203041u,0x01DC0000u};
    Require((beforeEarlier.modificationTimeHigh!=earlier.dwHighDateTime || beforeEarlier.modificationTimeLow!=earlier.dwLowDateTime) &&
        (beforeLater.modificationTimeHigh!=later.dwHighDateTime || beforeLater.modificationTimeLow!=later.dwLowDateTime),
        "File-time fixtures did not change the original recorded write times");
    SetWriteTime(earlierPath,earlier);SetWriteTime(laterPath,later);
    const auto first=catalog.Find(earlierPath),second=catalog.Find(laterPath);
    Require(first.modificationTimeHigh==earlier.dwHighDateTime && first.modificationTimeLow==earlier.dwLowDateTime,
        "Find lost the earlier fixture's exact FILETIME words");
    Require(second.modificationTimeHigh==later.dwHighDateTime && second.modificationTimeLow==later.dwLowDateTime,
        "Find lost the later fixture's exact FILETIME words");
    Require(!first.header && !second.header,"Write-time-only changes retained stale cached SDK headers");
    Require(first.modificationTime==second.modificationTime,"One-tick fixture times unexpectedly have different second-resolution labels");
    Require(NativeSaveCatalog::CompareModificationTimes(second.modificationTimeHigh,second.modificationTimeLow,
        first.modificationTimeHigh,first.modificationTimeLow)==1,"Original newest-first order lost a one-tick difference above 2^53");
    const auto files=catalog.List();Require(files.size()==2,"File-time catalog contains unexpected entries");
    const auto listedEarlier=std::find_if(files.begin(),files.end(),[&](const ZeroSisHost::UiSaveMenuFile& file){return file.fileName==first.fileName;});
    const auto listedLater=std::find_if(files.begin(),files.end(),[&](const ZeroSisHost::UiSaveMenuFile& file){return file.fileName==second.fileName;});
    Require(listedEarlier!=files.end(),"List omitted the earlier file-time fixture");
    Require(listedLater!=files.end(),"List omitted the later file-time fixture");
    Require(listedEarlier->modificationTimeHigh==earlier.dwHighDateTime && listedEarlier->modificationTimeLow==earlier.dwLowDateTime &&
        !listedEarlier->header,"List changed the earlier raw time or revived stale SDK metadata");
    Require(listedLater->modificationTimeHigh==later.dwHighDateTime && listedLater->modificationTimeLow==later.dwLowDateTime &&
        !listedLater->header,"List changed the later raw time or revived stale SDK metadata");
    catalog.ObserveWrittenSave(earlierPath,Header(archive));catalog.ObserveWrittenSave(laterPath,Header(archive));
    const auto observedEarlier=catalog.Find(earlierPath),observedLater=catalog.Find(laterPath);
    Require(observedEarlier.header && observedEarlier.modificationTimeHigh==earlier.dwHighDateTime &&
        observedEarlier.modificationTimeLow==earlier.dwLowDateTime,"Re-observing an SDK header changed the earlier raw write time");
    Require(observedLater.header && observedLater.modificationTimeHigh==later.dwHighDateTime &&
        observedLater.modificationTimeLow==later.dwLowDateTime,"Re-observing an SDK header changed the later raw write time");
    Require(NativeSaveArchive::Read(earlierPath)==bytes,"File-time catalog operations changed earlier serialized V1 bytes");
    Require(NativeSaveArchive::Read(laterPath)==bytes,"File-time catalog operations changed later serialized V1 bytes");
}
void TestLoadHandoff(const std::wstring& directory){
    const auto begin=checks;
    const auto session=directory+L"\\load-handoff";MakeDirectory(session);
    const auto first=Archive(71),second=Archive(72);const auto bytes=first.Encode();
    NativeSaveCatalog catalog(session);
    const auto path=catalog.WriteNew("chosen",first,Header(first));
    const auto listed=catalog.Find(path);
    const auto manifest=first.sections[0].bytes;
    const auto sealed=catalog.ReadLoadArchive(listed.fileName,listed,manifest);
    Require(!!sealed,"Observed owned archive was not sealed");
    Require(sealed->Encode()==bytes,"Sealed archive changed original V1 bytes");
    Require(NativeSaveArchive::Read(path)==bytes,"Load observation changed its source file");
    for(unsigned field=0;field<11;++field){
        auto forged=listed;auto header=std::make_shared<UiSaveMenuHeader>(*listed.header);
        switch(field){
            case 0:++header->playerCivilization;break;case 1:++header->gameSpeed;break;
            case 2:++header->startEra;break;case 3:++header->turnNumber;break;
            case 4:++header->difficulty;break;case 5:++header->worldSize;break;
            case 6:++header->currentEra;break;case 7:++header->gameType;break;
            case 8:header->mapScript+='x';break;case 9:header->leaderName+='x';break;
            case 10:header->civilizationName+='x';break;
        }
        forged.header=std::move(header);
        Rejects([&]{catalog.ReadLoadArchive(listed.fileName,forged,manifest);},"Forged preview header accepted for load");
    }
    for(unsigned field=0;field<9;++field){
        auto forged=listed;
        switch(field){
            case 0:forged.fileName+=".other";break;case 1:forged.modificationTime+='x';break;
            case 2:forged.modificationTimeHigh^=1;break;case 3:forged.modificationTimeLow^=1;break;
            case 4:forged.observedFileIdentity[0]^=1;break;case 5:forged.observedFileIdentity[1]^=1;break;
            case 6:forged.observedFileIdentity[2]^=1;break;case 7:forged.observedChecksum[0]^=1;break;
            case 8:forged.header.reset();break;
        }
        Rejects([&]{catalog.ReadLoadArchive(listed.fileName,forged,manifest);},"Altered immutable catalog observation accepted");
    }
    Rejects([&]{catalog.ReadLoadArchive(listed.fileName,listed,{});},"Empty bundle identity accepted");
    Rejects([&]{catalog.ReadLoadArchive(listed.fileName,listed,std::vector<unsigned char>(16385,1));},"Oversized bundle identity accepted");
    auto wrongBundle=manifest;wrongBundle[0]^=1;
    Rejects([&]{catalog.ReadLoadArchive(listed.fileName,listed,wrongBundle);},"Another bundle accepted");
    const auto unknownPath=session+L"\\unobserved.zssave";
    NativeSaveArchive::WriteAtomic(unknownPath,bytes);
    const auto unknown=catalog.Find(unknownPath);
    Rejects([&]{catalog.ReadLoadArchive(unknown.fileName,unknown,manifest);},"Unobserved preview was invented for load");
    // Preserve time, bytes and preview, but replace the file identity. A fresh
    // header observation must not bless an already queued stale listing.
    NativeSaveArchive::WriteAtomic(path,bytes);
    const HANDLE replacement=CreateFileW(path.c_str(),FILE_WRITE_ATTRIBUTES,FILE_SHARE_READ|FILE_SHARE_WRITE|FILE_SHARE_DELETE,
        nullptr,OPEN_EXISTING,FILE_ATTRIBUTE_NORMAL,nullptr);
    Require(replacement!=INVALID_HANDLE_VALUE,"Cannot open own replacement fixture");
    const FILETIME originalTime{listed.modificationTimeLow,listed.modificationTimeHigh};
    Require(SetFileTime(replacement,nullptr,nullptr,&originalTime)!=FALSE,"Cannot retain replacement fixture timestamp");
    Require(CloseHandle(replacement)!=FALSE,"Cannot close replacement fixture");
    catalog.ObserveWrittenSave(path,Header(first));const auto replaced=catalog.Find(path);
    Require(replaced.observedFileIdentity!=listed.observedFileIdentity && replaced.observedChecksum==listed.observedChecksum &&
        replaced.modificationTimeHigh==listed.modificationTimeHigh && replaced.modificationTimeLow==listed.modificationTimeLow,
        "Replacement fixture did not isolate file identity");
    Rejects([&]{catalog.ReadLoadArchive(listed.fileName,listed,manifest);},"Same-time same-content replacement bypassed stale listing rejection");
    const auto resealed=catalog.ReadLoadArchive(replaced.fileName,replaced,manifest);
    Require(resealed->Encode()==bytes,"Fresh replacement observation could not seal its unchanged bytes");
    NativeSaveArchive::WriteAtomic(path,second.Encode());
    Rejects([&]{catalog.ReadLoadArchive(replaced.fileName,replaced,manifest);},"Changed save content bypassed validation");
    Require(sealed->Encode()==bytes && resealed->Encode()==bytes,"A path replacement changed immutable handoff content");
    Require(DeleteFileW(path.c_str())!=FALSE,"Cannot delete own disposable load fixture");
    Rejects([&]{catalog.ReadLoadArchive(replaced.fileName,replaced,manifest);},"Deleted source could be reopened for load");
    Require(sealed->Encode()==bytes,"Deleted source invalidated the sealed in-memory handoff");
    Require(checks-begin==39,"Load handoff assertion count changed");
}
void TestCatalog(const std::wstring& directory){
    const auto session=directory+L"\\owned-session";MakeDirectory(session);
    const auto first=Archive(1),second=Archive(2);const auto firstBytes=first.Encode();
    auto catalog=std::make_shared<NativeSaveCatalog>(session);
    Require(catalog->List().empty(),"New session unexpectedly has saved games");
    Require(catalog->NameAvailable("new"),"Fresh name unavailable");
    Require(!catalog->NameAvailable("../escape"),"Traversal name available");
    const std::string korean="\xED\x95\x9C\xEA\xB8\x80 \xEC\xA0\x80\xEC\x9E\xA5";
    const auto path=catalog->WriteNew(korean,first,Header(first));
    Require(path==session+L"\\\uD55C\uAE00 \uC800\uC7A5.zssave","Korean archive path differs");
    Require(NativeSaveArchive::Read(path)==firstBytes,"Named V1 archive differs from the supplied SDK envelope");
    Require(!catalog->NameAvailable(korean),"Existing name still available");
    Rejects([&]{catalog->WriteNew(korean,second,Header(second));},"Named save overwrote an existing archive");
    Require(NativeSaveArchive::Read(path)==firstBytes,"Duplicate name changed the original archive");
    const auto preview=catalog->Find(path);
    Require(preview.header && preview.header->turnNumber==first.elapsed && preview.header->currentEra==6 &&
        preview.header->leaderName=="Fixture leader" && preview.fileName==ZeroSisHost::Utf8(path) && !preview.modificationTime.empty(),
        "Recorded stock header or real modification date differs");
    const auto ascii=catalog->WriteNew("CaseSensitiveCheck",first,Header(first));
    Require(!catalog->NameAvailable("casesensitivecheck"),"Windows case alias treated as a fresh save name");
    Rejects([&]{catalog->WriteNew("casesensitivecheck",second,Header(second));},"Case alias overwrote an existing archive");
    Require(NativeSaveArchive::Read(ascii)==firstBytes,"Case alias changed the original archive");
    const auto legacy=session+L"\\earlier-checkpoint.zssave";NativeSaveArchive::WriteAtomic(legacy,second.Encode());
    Require(!catalog->Find(legacy).header,"Unknown older archive received a fabricated SDK header");
    catalog->ObserveWrittenSave(legacy,Header(second));Require(catalog->Find(legacy).header!=nullptr,"Observed original save header missing");
    auto wrong=Header(second);++wrong.turnNumber;
    Rejects([&]{catalog->ObserveWrittenSave(legacy,wrong);},"Header with a different SDK turn accepted");
    Require(NativeSaveArchive::Read(legacy)==second.Encode(),"Rejected metadata observation modified archive bytes");
    NativeSaveArchive::WriteAtomic(legacy,firstBytes);
    Require(!catalog->Find(legacy).header,"Replaced file retained stale SDK preview metadata");
    const auto outside=directory+L"\\outside-session.zssave";NativeSaveArchive::WriteAtomic(outside,firstBytes);
    Rejects([&]{catalog->Find(outside);},"Catalog read an archive outside its owned session");
    Rejects([&]{catalog->Find(session+L"\\..\\outside-session.zssave");},"Catalog accepted a traversal preview path");
    Rejects([&]{catalog->Find(session+L"\\earlier-checkpoint.zssave:stream");},"Catalog accepted an alternate data stream");
    Require(NativeSaveArchive::Read(outside)==firstBytes,"Outside-session fixture changed");
    const auto hardlink=session+L"\\hard-alias.zssave";
    Require(CreateHardLinkW(hardlink.c_str(),path.c_str(),nullptr)!=FALSE,"Cannot create owned hardlink fixture");
    Rejects([&]{catalog->Find(path);},"Catalog accepted a multiply linked save");
    Rejects([&]{catalog->List();},"Catalog listed a hardlink alias");
    Require(DeleteFileW(hardlink.c_str())!=FALSE,"Cannot remove owned hardlink fixture");
    const auto junction=directory+L"\\session-alias";MakeJunction(junction,session);
    Rejects([&]{NativeSaveCatalog redirected(junction);},"Catalog accepted a junction session root");
    Require(RemoveDirectoryW(junction.c_str())!=FALSE,"Cannot remove owned junction fixture");
    const auto directorySave=session+L"\\directory-alias.zssave";MakeJunction(directorySave,session);
    Rejects([&]{catalog->List();},"Catalog followed a directory reparse entry as a native save");
    Require(RemoveDirectoryW(directorySave.c_str())!=FALSE,"Cannot remove owned catalog reparse fixture");
    Rejects([&]{NativeSaveCatalog relative(L"relative\\session");},"Catalog accepted a relative session root");
    Rejects([&]{NativeSaveCatalog alias(session+L"\\.");},"Catalog accepted a dot session alias");
    Rejects([&]{NativeSaveCatalog alias(session+L" ");},"Catalog accepted a trailing-space session alias");
    const auto nested=session+L"\\nested";MakeDirectory(nested);
    Rejects([&]{catalog->Find(nested+L"\\other.zssave");},"Catalog accepted nested-session archives");
    Require(RemoveDirectoryW(nested.c_str())!=FALSE,"Cannot remove owned nested fixture");
    auto malformed=first;malformed.flags=4;
    Rejects([&]{catalog->WriteNew("malformed",malformed,Header(first));},"Malformed V1 archive published");
    Require(catalog->NameAvailable("malformed"),"Malformed archive created a destination");
    Require(Temporaries(session)==0,"Named save checks left an owned temporary file");
    const auto rowCount=catalog->List().size();Require(rowCount==3,"Catalog file list includes unexpected paths");
    const auto moved=session+L"-moved";
    Require(!MoveFileExW(session.c_str(),moved.c_str(),0),"Pinned session directory was renamed during catalog ownership");
    Require(GetFileAttributesW(session.c_str())!=INVALID_FILE_ATTRIBUTES,"Pinned session path disappeared");
    std::vector<wchar_t> shortPath(32768);const auto shortCount=GetShortPathNameW(session.c_str(),shortPath.data(),static_cast<DWORD>(shortPath.size()));
    const bool hasShortAlias=shortCount && shortCount<shortPath.size() && std::wstring(shortPath.data(),shortCount)!=session;
    if(hasShortAlias)
        Rejects([&]{NativeSaveCatalog alias(std::wstring(shortPath.data(),shortCount));},"Catalog accepted a short-path directory alias");
    else
        Require(!shortCount || (shortCount<shortPath.size() && std::wstring(shortPath.data(),shortCount)==session),
            "Short-path resolution returned a truncated or ambiguous directory alias");
    std::printf("NATIVE_SAVE_CATALOG_SHORT_PATH_ALIAS applicable=%s\n",hasShortAlias?"true":"false");
    ZeroSisHost::UiSaveMenuCatalog snapshot;snapshot.nameAvailable=[catalog](const std::string& name){return catalog->NameAvailable(name);};
    catalog.reset();Require(snapshot.nameAvailable("retained-callback"),"Immutable catalog callback lost its filesystem owner");
}
void TestLongReadBoundary(const std::wstring& directory){
    std::wstring path=directory+L"\\";
    path.append(239-path.size(),L'x');MakeDirectory(path);
    NativeSaveCatalog catalog(path);const auto archive=Archive(9);
    Require(catalog.NameAvailable("short"),"Readable final native path was disabled");
    const std::string longName(32,'n');
    Require(!catalog.NameAvailable(longName),"Current reader's overlong final path was offered as loadable");
    Rejects([&]{catalog.WriteNew(longName,archive,Header(archive));},"Unloadable overlong final path published");
    Require(catalog.List().empty(),"Rejected overlong name left a save");
    const auto readable=catalog.WriteNew("short",archive,Header(archive));
    Require(readable.size()<MAX_PATH && NativeSaveArchive::Read(readable)==archive.Encode(),
        "Long temporary path failed to commit a destination that the existing reader can reopen");
}
void RewriteOwned(const std::wstring& path,const std::vector<unsigned char>& bytes,const FILETIME& time){
    const HANDLE value=CreateFileW(path.c_str(),GENERIC_READ|GENERIC_WRITE,0,nullptr,OPEN_EXISTING,
        FILE_ATTRIBUTE_NORMAL|FILE_FLAG_OPEN_REPARSE_POINT,nullptr);
    Require(value!=INVALID_HANDLE_VALUE,"Cannot open owned delete-mutation fixture");
    struct File final {HANDLE value;~File(){CloseHandle(value);}} file{value};
    Require(bytes.size()<=MAXDWORD,"Owned mutation fixture exceeds one bounded write");DWORD written=0;
    Require(WriteFile(value,bytes.data(),static_cast<DWORD>(bytes.size()),&written,nullptr)!=FALSE && written==bytes.size(),
        "Cannot replace owned fixture bytes in place");
    Require(SetEndOfFile(value)!=FALSE,"Cannot truncate owned mutation fixture");
    Require(FlushFileBuffers(value)!=FALSE,"Cannot flush owned mutation fixture");
    Require(SetFileTime(value,nullptr,nullptr,&time)!=FALSE,"Cannot preserve owned mutation fixture raw time");
}
void TestDeleteListed(const std::wstring& directory){
    const auto begin=checks;
    const auto session=directory+L"\\delete-listed";MakeDirectory(session);
    const auto archive=Archive(81),other=Archive(82);const auto bytes=archive.Encode(),otherBytes=other.Encode();
    const auto manifest=archive.sections[0].bytes;
    NativeSaveCatalog catalog(session);
    const auto path=catalog.WriteNew("chosen",archive,Header(archive));
    const auto keep=catalog.WriteNew("keep",other,Header(other));
    const FILETIME baseline{0x10203040u,0x01DC0000u};SetWriteTime(path,baseline);
    catalog.ObserveWrittenSave(path,Header(archive));const auto listed=catalog.Find(path);
    const auto rejectPreserving=[&](const ZeroSisHost::UiSaveMenuFile& candidate,
            const std::vector<unsigned char>& bundle,const char* reason){
        Rejects([&]{catalog.DeleteListed(candidate,bundle);},reason);
        Require(NativeSaveArchive::Read(path)==bytes,"Rejected delete changed the chosen owned save");
        Require(NativeSaveArchive::Read(keep)==otherBytes,"Rejected delete changed a different owned save");
    };
    Require(listed.header && catalog.List().size()==2,"Delete fixtures are not listed with observed metadata");
    for(unsigned field=0;field<11;++field){
        auto forged=listed;auto header=std::make_shared<UiSaveMenuHeader>(*listed.header);
        switch(field){
            case 0:++header->playerCivilization;break;case 1:++header->gameSpeed;break;
            case 2:++header->startEra;break;case 3:++header->turnNumber;break;
            case 4:++header->difficulty;break;case 5:++header->worldSize;break;
            case 6:++header->currentEra;break;case 7:++header->gameType;break;
            case 8:header->mapScript+="-forged";break;case 9:header->leaderName+="-forged";break;
            case 10:header->civilizationName+="-forged";break;
        }
        forged.header=header;rejectPreserving(forged,manifest,"Delete accepted forged preview metadata");
    }
    for(unsigned field=0;field<8;++field){
        auto forged=listed;
        switch(field){
            case 0:forged.modificationTime+="-forged";break;
            case 1:++forged.modificationTimeHigh;break;case 2:++forged.modificationTimeLow;break;
            case 3:++forged.observedFileIdentity[0];break;case 4:++forged.observedFileIdentity[1];break;
            case 5:++forged.observedFileIdentity[2];break;case 6:forged.observedChecksum[0]^=1;break;
            case 7:forged.header.reset();break;
        }
        rejectPreserving(forged,manifest,"Delete accepted a forged immutable file observation");
    }
    auto wrongManifest=manifest;wrongManifest[0]^=1;
    rejectPreserving(listed,wrongManifest,"Delete accepted another bundle manifest");
    rejectPreserving(listed,{},"Delete accepted an empty bundle manifest");
    rejectPreserving(listed,std::vector<unsigned char>(16385,0),"Delete accepted an unbounded bundle manifest");
    const auto external=directory+L"\\owned-outside-delete.zssave";
    NativeSaveArchive::WriteAtomic(external,bytes);
    for(const auto& bad:std::vector<std::string>{ZeroSisHost::Utf8(external),"relative.zssave",
            ZeroSisHost::Utf8(session+L"\\..\\owned-outside-delete.zssave"),listed.fileName+"/child",
            std::string("bad\0path",8),"\xC0\xAF"}){
        auto forged=listed;forged.fileName=bad;rejectPreserving(forged,manifest,"Delete accepted a path outside its exact listed role");
    }
    auto caseAlias=listed;caseAlias.fileName.replace(caseAlias.fileName.size()-13,6,"CHOSEN");
    rejectPreserving(caseAlias,manifest,"Delete accepted a case alias of the exact listed UTF-8 path");
    Require(NativeSaveArchive::Read(external)==bytes,"Rejected external path delete changed an owned outside fixture");
    const auto unknownPath=session+L"\\unobserved.zssave";NativeSaveArchive::WriteAtomic(unknownPath,bytes);
    auto unknown=catalog.Find(unknownPath);unknown.header=listed.header;
    rejectPreserving(unknown,manifest,"Delete accepted a file without a catalog header observation");
    Require(NativeSaveArchive::Read(unknownPath)==bytes,"Unobserved file was deleted");
    Require(DeleteFileW(unknownPath.c_str())!=FALSE,"Cannot remove owned unobserved fixture");
    const HANDLE reader=CreateFileW(path.c_str(),GENERIC_READ,FILE_SHARE_READ,nullptr,OPEN_EXISTING,FILE_ATTRIBUTE_NORMAL,nullptr);
    Require(reader!=INVALID_HANDLE_VALUE,"Cannot lock an owned delete fixture");
    rejectPreserving(listed,manifest,"Delete ignored an existing read lock");
    Require(CloseHandle(reader)!=FALSE,"Cannot release owned read lock");
    Require(SetFileAttributesW(path.c_str(),FILE_ATTRIBUTE_READONLY)!=FALSE,"Cannot mark owned fixture read-only");
    catalog.ObserveWrittenSave(path,Header(archive));const auto readonly=catalog.Find(path);
    rejectPreserving(readonly,manifest,"Delete removed an explicitly observed read-only file");
    Require(SetFileAttributesW(path.c_str(),FILE_ATTRIBUTE_NORMAL)!=FALSE,"Cannot restore owned fixture attributes");
    catalog.ObserveWrittenSave(path,Header(archive));
    const auto alias=session+L"\\hardlink.zssave";
    Require(CreateHardLinkW(alias.c_str(),path.c_str(),nullptr)!=FALSE,"Cannot create an owned delete hardlink");
    rejectPreserving(listed,manifest,"Delete accepted a hardlinked listed save");
    Require(NativeSaveArchive::Read(alias)==bytes,"Hardlink rejection changed the linked fixture");
    Require(DeleteFileW(alias.c_str())!=FALSE,"Cannot remove owned delete hardlink");
    const auto preserved=session+L"\\preserved.zssave";
    Require(MoveFileExW(path.c_str(),preserved.c_str(),0)!=FALSE,"Cannot preserve own junction replacement source");
    MakeJunction(path,session);
    Rejects([&]{catalog.DeleteListed(listed,manifest);},"Delete followed a replacement reparse entry");
    Require(NativeSaveArchive::Read(preserved)==bytes && NativeSaveArchive::Read(keep)==otherBytes,
        "Reparse rejection changed preserved fixture files");
    Require(RemoveDirectoryW(path.c_str())!=FALSE,"Cannot remove owned delete reparse fixture");
    Require(MoveFileExW(preserved.c_str(),path.c_str(),0)!=FALSE,"Cannot restore own listed fixture path");
    const FILETIME oneTick{baseline.dwLowDateTime+1,baseline.dwHighDateTime};SetWriteTime(path,oneTick);
    catalog.ObserveWrittenSave(path,Header(archive));const auto retimed=catalog.Find(path);
    Require(retimed.modificationTime==listed.modificationTime && retimed.modificationTimeLow!=listed.modificationTimeLow,
        "Delete timestamp fixture did not isolate a raw FILETIME tick");
    rejectPreserving(listed,manifest,"Delete accepted a stale raw FILETIME observation");
    SetWriteTime(path,baseline);catalog.ObserveWrittenSave(path,Header(archive));
    auto changed=archive;changed.sections.back().bytes[1]^=1;const auto changedBytes=changed.Encode();
    RewriteOwned(path,changedBytes,baseline);catalog.ObserveWrittenSave(path,Header(archive));
    const auto changedListing=catalog.Find(path);
    Require(changedListing.observedFileIdentity==listed.observedFileIdentity &&
        changedListing.modificationTimeHigh==listed.modificationTimeHigh && changedListing.modificationTimeLow==listed.modificationTimeLow &&
        changedListing.observedChecksum!=listed.observedChecksum,"Delete content fixture did not isolate checksum");
    Rejects([&]{catalog.DeleteListed(listed,manifest);},"Delete accepted changed content with the same ID and raw timestamp");
    Require(NativeSaveArchive::Read(path)==changedBytes,"Rejected checksum mismatch changed the current file");
    auto corrupt=bytes;corrupt[80]^=1;RewriteOwned(path,corrupt,baseline);
    Rejects([&]{catalog.DeleteListed(listed,manifest);},"Delete accepted an archive with invalid checksum bytes");
    Require(NativeSaveArchive::Read(path)==corrupt,"Rejected corrupt archive was deleted or changed");
    RewriteOwned(path,bytes,baseline);catalog.ObserveWrittenSave(path,Header(archive));
    NativeSaveArchive::WriteAtomic(path,bytes);SetWriteTime(path,baseline);catalog.ObserveWrittenSave(path,Header(archive));
    const auto replaced=catalog.Find(path);
    Require(replaced.observedFileIdentity!=listed.observedFileIdentity && replaced.observedChecksum==listed.observedChecksum &&
        replaced.modificationTimeHigh==listed.modificationTimeHigh && replaced.modificationTimeLow==listed.modificationTimeLow,
        "Delete replacement fixture did not isolate file identity");
    rejectPreserving(listed,manifest,"Delete accepted a replacement with identical bytes and raw timestamp");
    deleteProbe=DeleteHandleProbe{};deleteProbe.active=true;
    try{catalog.DeleteListed(replaced,manifest);}catch(...){deleteProbe.active=false;throw;}
    deleteProbe.active=false;
    Require(deleteProbe.opens==1 && deleteProbe.exclusive,"Delete reopened its path or failed to request one exclusive READ+DELETE handle");
    Require(deleteProbe.dispositions==1 && deleteProbe.sameHandle,"Delete disposition did not use the validated read handle");
    Require(deleteProbe.renameBlocked && deleteProbe.writerBlocked,"Delete allowed rename or writer replacement before disposition");
    Require(GetFileAttributesW(path.c_str())==INVALID_FILE_ATTRIBUTES && GetLastError()==ERROR_FILE_NOT_FOUND,
        "Successful owned save disposition did not remove its exact path");
    Require(catalog.List().size()==1 && catalog.NameAvailable("chosen"),"Successful delete did not refresh the catalog namespace");
    Require(NativeSaveArchive::Read(keep)==otherBytes,"Successful deletion changed a different save");
    Rejects([&]{catalog.DeleteListed(replaced,manifest);},"Repeated delete was accepted");
    Require(NativeSaveArchive::Read(keep)==otherBytes,"Repeated deletion changed a different save");
    const auto recreated=catalog.WriteNew("chosen",archive,Header(archive));
    Rejects([&]{catalog.DeleteListed(replaced,manifest);},"Stale delete removed a newly created same-name save");
    Require(NativeSaveArchive::Read(recreated)==bytes && NativeSaveArchive::Read(keep)==otherBytes,
        "Stale duplicate delete changed the new save or its sibling");
    Require(NativeSaveArchive::Read(external)==bytes,"Delete tests changed an outside-session fixture");
    std::printf("NATIVE_SAVE_CATALOG_DELETE_LISTED_PASS checks=%d same_exclusive_handle=true\n",checks-begin);
}
void TestConcurrentCollision(const std::wstring& directory){
    const auto session=directory+L"\\concurrent-session";MakeDirectory(session);
    NativeSaveCatalog left(session),right(session);std::atomic<unsigned> ready{0},won{0},rejected{0};std::atomic<bool> go{false};
    const auto first=Archive(11),second=Archive(12);
    const auto writer=[&](NativeSaveCatalog& catalog,const NativeSaveArchive& archive){
        ++ready;while(!go.load())SwitchToThread();
        try{catalog.WriteNew("one-name",archive,Header(archive));++won;}
        catch(const std::exception&){++rejected;}
    };
    std::thread a(writer,std::ref(left),std::cref(first)),b(writer,std::ref(right),std::cref(second));
    while(ready.load()!=2)SwitchToThread();go=true;a.join();b.join();
    Require(won.load()==1 && rejected.load()==1,"Two competing named saves did not produce exactly one winner");
    const auto bytes=NativeSaveArchive::Read(session+L"\\one-name.zssave");
    Require(bytes==first.Encode() || bytes==second.Encode(),"Concurrent winner is partial or has mixed bytes");
    Require(left.List().size()==1,"Concurrent destination has aliases");
    Require(Temporaries(session)==0,"Concurrent failed writer retained a temporary");
}
}
#include "owned_save_replace_transaction_fixture.h"
int main(int argc,char** argv){
    try{
        const UINT faultMode=SEM_FAILCRITICALERRORS|SEM_NOGPFAULTERRORBOX|SEM_NOOPENFILEERRORBOX;
        SetErrorMode(faultMode);
        Require((GetErrorMode()&faultMode)==faultMode,"Cannot suppress native-save test critical-error UI");
        Require(SUCCEEDED(WerSetFlags(WER_FAULT_REPORTING_NO_UI)),"Cannot suppress native-save test Windows fault-reporting UI");
        std::printf("NATIVE_SAVE_CATALOG_FAULT_UI_SUPPRESSED WER_NO_UI=true\n");
        std::fflush(stdout);
        if(argc!=2 && argc!=4)throw std::invalid_argument("Expected a unique owned fixture directory");
        const auto directory=Wide(argv[1]);
        Require(directory.size()<220,"Fixture root is too long for the ordinary-reader boundary case");
        if(argc==4){
            const std::string command=argv[2],phase=argv[3];
            if(phase!="stage" && phase!="journal" && phase!="old" && phase!="new" && phase!="old-cleanup" && phase!="journal-cleanup")
                throw std::invalid_argument("Unknown bounded own-process interruption phase");
            if(command=="--replace-crash"){ReplacementCrashWrite(directory,phase);return 2;}
            if(command=="--replace-recover"){ReplacementCrashRecover(directory,phase);return 0;}
            throw std::invalid_argument("Unknown owned replacement fixture command");
        }
        TestNames();TestModificationTimeComparison();TestCatalog(directory);TestModificationTimeCatalog(directory);
        TestLongReadBoundary(directory);TestConcurrentCollision(directory);TestLoadHandoff(directory);TestDeleteListed(directory);
        TestListedReplacement(directory);
        std::printf("NATIVE_SAVE_CATALOG_PASS checks=%d GAMECORE_LOADED=false RETAIL_SAVES_TOUCHED=false\n",checks);return 0;
    }catch(const std::exception& error){
        std::fprintf(stderr,"NATIVE_SAVE_CATALOG_FAIL checks=%d reason=%s\n",checks,error.what());return 1;
    }
}
