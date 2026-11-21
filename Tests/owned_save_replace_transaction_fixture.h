#pragma once
// Included only by the standalone native catalog fixture, never by the Host.
namespace {
unsigned replacementChecks=0;
void RCheck(bool value,const char* message){++replacementChecks;if(!value)throw std::runtime_error(message);}
template<class F> void RReject(F&& function,const char* message){
    bool rejected=false;try{function();}catch(const std::exception&){rejected=true;}RCheck(rejected,message);
}
NativeSaveArchive RArchive(unsigned seed){auto archive=Archive(seed);archive.sections[0].bytes={91,92,93,94};return archive;}
struct RSession final {
    std::wstring directory,path;NativeSaveArchive before=RArchive(60),after=RArchive(61);
    std::unique_ptr<NativeSaveCatalog> catalog;ZeroSisHost::UiSaveMenuFile listed;
    RSession(const std::wstring& parent,const std::wstring& label):directory(parent+L"\\replacement-"+label){
        RCheck(CreateDirectoryW(directory.c_str(),nullptr)!=FALSE,"Cannot create replacement fixture");
        catalog.reset(new NativeSaveCatalog(directory));path=catalog->WriteNew("existing",before,Header(before));listed=catalog->Find(path);
        RCheck(static_cast<bool>(listed.header),"Replacement fixture has no observed header");
    }
    NativeSaveCatalog::ReplacementResult Replace(){return catalog->WriteListedReplacement(listed,after,Header(after),before.sections[0].bytes);}
};
struct RScope final {
    RScope(){replaceProbe=ReplacementProbe{};replaceProbe.active=true;}
    ~RScope(){replaceProbe.active=false;if(replaceProbe.heldStage!=INVALID_HANDLE_VALUE){CloseHandle(replaceProbe.heldStage);replaceProbe.heldStage=INVALID_HANDLE_VALUE;}}
};
std::vector<unsigned char> RReadHandle(HANDLE file){
    LARGE_INTEGER size{},zero{};RCheck(GetFileSizeEx(file,&size)!=FALSE && size.QuadPart>=0 && size.QuadPart<=16384,"Invalid owned probe file size");
    RCheck(SetFilePointerEx(file,zero,nullptr,FILE_BEGIN)!=FALSE,"Cannot seek owned probe file");
    std::vector<unsigned char> bytes(static_cast<std::size_t>(size.QuadPart));DWORD read=0;
    RCheck(ReadFile(file,bytes.data(),static_cast<DWORD>(bytes.size()),&read,nullptr)!=FALSE && read==bytes.size(),"Cannot read owned probe file");return bytes;
}
std::vector<unsigned char> RRead(const std::wstring& path){
    const HANDLE file=CreateFileW(path.c_str(),GENERIC_READ,FILE_SHARE_READ,nullptr,OPEN_EXISTING,FILE_FLAG_OPEN_REPARSE_POINT,nullptr);
    RCheck(file!=INVALID_HANDLE_VALUE,"Cannot read bounded owned evidence");
    try{auto bytes=RReadHandle(file);CloseHandle(file);return bytes;}catch(...){CloseHandle(file);throw;}
}
void RWrite(const std::wstring& path,const std::vector<unsigned char>& bytes){
    const HANDLE file=CreateFileW(path.c_str(),GENERIC_READ|GENERIC_WRITE,0,nullptr,OPEN_EXISTING,FILE_FLAG_OPEN_REPARSE_POINT,nullptr);
    RCheck(file!=INVALID_HANDLE_VALUE,"Cannot open owned evidence for injected mutation");
    DWORD written=0;const BOOL okay=WriteFile(file,bytes.data(),static_cast<DWORD>(bytes.size()),&written,nullptr);
    const BOOL flushed=FlushFileBuffers(file);CloseHandle(file);
    RCheck(okay && written==bytes.size() && flushed,"Cannot inject owned file mutation");
}
std::wstring RStage(const std::wstring& directory){
    WIN32_FIND_DATAW data{};HANDLE search=FindFirstFileW((directory+L"\\.zerosis-replace-v1-*.stage").c_str(),&data);
    RCheck(search!=INVALID_HANDLE_VALUE,"Missing pending replacement stage");const std::wstring name=data.cFileName;
    const BOOL more=FindNextFileW(search,&data);const DWORD error=GetLastError();FindClose(search);
    RCheck(!more && error==ERROR_NO_MORE_FILES,"Ambiguous pending replacement stage");return directory+L"\\"+name;
}
void RRemoveOwned(const std::wstring& path,const std::vector<unsigned char>& expected){
    const HANDLE file=CreateFileW(path.c_str(),GENERIC_READ|DELETE,0,nullptr,OPEN_EXISTING,FILE_FLAG_OPEN_REPARSE_POINT,nullptr);
    RCheck(file!=INVALID_HANDLE_VALUE,"Cannot open owned collision fixture for cleanup");
    try{
        BY_HANDLE_FILE_INFORMATION info{};RCheck(GetFileInformationByHandle(file,&info)!=FALSE && info.nNumberOfLinks==1 &&
            !(info.dwFileAttributes&(FILE_ATTRIBUTE_DIRECTORY|FILE_ATTRIBUTE_REPARSE_POINT|FILE_ATTRIBUTE_READONLY)),"Unsafe owned collision fixture");
        RCheck(RReadHandle(file)==expected,"Owned collision fixture content changed");
        FILE_DISPOSITION_INFO disposal{};disposal.DeleteFile=TRUE;
        RCheck(SetFileInformationByHandle(file,FileDispositionInfo,&disposal,sizeof(disposal))!=FALSE,"Cannot clean own collision fixture");
    }catch(...){CloseHandle(file);throw;}
    CloseHandle(file);
}
void RObserveActiveJournal(void* state){
    auto& s=*static_cast<RSession*>(state);
    RReject([&]{NativeSaveCatalog reject(s.directory);},"Constructor crossed another active exclusive journal");
    RReject([&]{s.catalog->List();},"List crossed active exclusive journal");
    RReject([&]{s.catalog->PrepareForMutation();},"Generic mutation crossed active exclusive journal");
    RReject([&]{s.catalog->WriteNew("forbidden",s.after,Header(s.after));},"Write-new crossed active exclusive journal");
    RReject([&]{s.catalog->DeleteListed(s.listed,s.before.sections[0].bytes);},"Delete crossed active exclusive journal");
}
void TestListedReplacement(const std::wstring& directory){
    {
        RSession s(directory,L"success");NativeSaveCatalog::ReplacementResult result;
        {RScope scope;replaceProbe.journalObservation=RObserveActiveJournal;replaceProbe.observationState=&s;
            result=s.Replace();RCheck(replaceProbe.sourceExclusive,"Replacement source did not use an exclusive read/delete handle");}
        RCheck(result.committed && !result.recoveryRequired && result.path==s.path && result.recoveryPath.empty(),"Replacement success result differs");
        RCheck(NativeSaveArchive::Read(s.path)==s.after.Encode(),"Replacement content differs");
        const auto listed=s.catalog->Find(s.path);
        RCheck(listed.header && listed.header->turnNumber==s.after.elapsed && listed.observedFileIdentity!=s.listed.observedFileIdentity,"Replacement catalog header/identity differs");
        RCheck(s.catalog->ReadLoadArchive(listed.fileName,listed,s.after.sections[0].bytes)->Encode()==s.after.Encode(),"Replacement cannot be loaded through immutable observation");
        RCheck(!s.catalog->NameAvailable("existing"),"Replacement lost the original name");
        s.catalog->DeleteListed(listed,s.after.sections[0].bytes);RCheck(s.catalog->List().empty(),"Replacement cannot be deleted through current observation");
    }
    for(unsigned kind=0;kind<8;++kind){
        RSession s(directory,L"reject-"+std::to_wstring(kind));auto listed=s.listed;auto bundle=s.before.sections[0].bytes;
        if(kind==0)listed.header.reset();
        if(kind==1)++listed.observedFileIdentity[2];
        if(kind==2)listed.observedChecksum[0]^=1;
        if(kind==3)++listed.modificationTimeHigh;
        if(kind==4)listed.modificationTime+=" changed";
        if(kind==5){auto changed=std::make_shared<UiSaveMenuHeader>(*listed.header);++changed->turnNumber;listed.header=changed;}
        if(kind==6)listed.fileName+=".alias";
        if(kind==7)bundle[0]^=1;
        RReject([&]{s.catalog->WriteListedReplacement(listed,s.after,Header(s.after),bundle);},"Forged replacement observation accepted");
        RCheck(NativeSaveArchive::Read(s.path)==s.before.Encode(),"Rejected replacement changed the original");
    }
    {
        RSession s(directory,L"readonly");RCheck(SetFileAttributesW(s.path.c_str(),FILE_ATTRIBUTE_READONLY)!=FALSE,"Cannot mark owned source read-only");
        RReject([&]{s.Replace();},"Read-only replacement source accepted");
        RCheck(SetFileAttributesW(s.path.c_str(),FILE_ATTRIBUTE_NORMAL)!=FALSE,"Cannot restore owned source attributes");
        RCheck(NativeSaveArchive::Read(s.path)==s.before.Encode(),"Read-only rejection changed original");
    }
    {
        RSession s(directory,L"lock");HANDLE reader=CreateFileW(s.path.c_str(),GENERIC_READ,FILE_SHARE_READ,nullptr,OPEN_EXISTING,0,nullptr);
        RCheck(reader!=INVALID_HANDLE_VALUE,"Cannot hold shared source reader");
        RReject([&]{s.Replace();},"Shared-reader source was not exclusive");CloseHandle(reader);
        RCheck(NativeSaveArchive::Read(s.path)==s.before.Encode(),"Lock rejection changed original");
    }
    for(unsigned kind=0;kind<4;++kind){
        RSession s(directory,L"rollback-"+std::to_wstring(kind));
        {RScope scope;if(kind<2)replaceProbe.failFlush=kind+1;else replaceProbe.failRename=kind-1;
            RReject([&]{s.Replace();},"Injected precommit/rollback failure was reported as success");}
        RCheck(NativeSaveArchive::Read(s.path)==s.before.Encode(),"Uncommitted failure did not preserve original");
        RCheck(s.catalog->Find(s.path).header!=nullptr,"Restored original lost known catalog header");
        RCheck(GetFileAttributesW((s.directory+L"\\.zerosis-replace-v1.journal").c_str())==INVALID_FILE_ATTRIBUTES,"Restored failure retained journal");
    }
    for(unsigned disposal=1;disposal<=2;++disposal){
        RSession s(directory,L"committed-cleanup-"+std::to_wstring(disposal));NativeSaveCatalog::ReplacementResult result;
        {RScope scope;replaceProbe.failDispose=disposal;result=s.Replace();}
        RCheck(result.committed && result.recoveryRequired,"Committed cleanup failure lost commit state");
        RCheck(result.recoveryPath==s.directory+L"\\.zerosis-replace-v1.journal" &&
            GetFileAttributesW(result.recoveryPath.c_str())!=INVALID_FILE_ATTRIBUTES,"Committed recovery path does not name retained evidence");
        RCheck(NativeSaveArchive::Read(s.path)==s.after.Encode(),"Committed cleanup failure lost new archive");
        NativeSaveCatalog recovered(s.directory);const auto listed=recovered.Find(s.path);
        RCheck(listed.header && listed.header->turnNumber==s.after.elapsed,"Committed recovery lost journaled header");
        RCheck(NativeSaveArchive::Read(s.path)==s.after.Encode(),"Committed recovery changed archive");
    }
    for(unsigned kind=0;kind<2;++kind){
        RSession s(directory,L"uncommitted-cleanup-"+std::to_wstring(kind));NativeSaveCatalog::ReplacementResult result;
        {RScope scope;replaceProbe.failDispose=1;if(kind==0)replaceProbe.failFlush=1;else replaceProbe.failRename=2;result=s.Replace();}
        RCheck(!result.committed && result.recoveryRequired,"Uncommitted cleanup failure lost recovery state");
        RCheck(GetFileAttributesW(result.recoveryPath.c_str())!=INVALID_FILE_ATTRIBUTES,"Uncommitted recovery path does not name retained evidence");
        RCheck(NativeSaveArchive::Read(s.path)==s.before.Encode(),"Uncommitted cleanup failure changed original");
        if(kind==0)RReject([&]{NativeSaveCatalog reject(s.directory);},"Unjournaled cleanup evidence was silently discarded");
        else {NativeSaveCatalog recovered(s.directory);RCheck(recovered.Find(s.path).header!=nullptr,"Restored cleanup recovery lost header");}
    }
    {
        RSession s(directory,L"stage-reopen-sharing");NativeSaveCatalog::ReplacementResult result;
        {RScope scope;replaceProbe.holdStageReopen=true;result=s.Replace();
            RCheck(replaceProbe.heldStage!=INVALID_HANDLE_VALUE,"Did not inject actual shared reader after stage writer close");
            RCheck(!result.committed && result.recoveryRequired,"Failed stage reopen lost recovery-required state");
            RCheck(result.recoveryPath.find(L".stage")!=std::wstring::npos &&
                GetFileAttributesW(result.recoveryPath.c_str())!=INVALID_FILE_ATTRIBUTES,"Stage reopen recovery path does not name existing evidence");
            RCheck(GetFileAttributesW((s.directory+L"\\.zerosis-replace-v1.journal").c_str())==INVALID_FILE_ATTRIBUTES,"Stage reopen failure published a journal");
            RCheck(NativeSaveArchive::Read(s.path)==s.before.Encode(),"Stage reopen failure changed original archive");
            RReject([&]{s.catalog->PrepareForMutation();},"Stage reopen orphan did not block later mutation");
            RReject([&]{NativeSaveCatalog reject(s.directory);},"Stage reopen orphan did not block constructor");
        }
        RCheck(NativeSaveArchive::Read(s.path)==s.before.Encode(),"Releasing injected reader changed original archive");
    }
    {
        RSession s(directory,L"foreign");const auto foreign=RArchive(80).Encode();NativeSaveCatalog::ReplacementResult result;
        {RScope scope;replaceProbe.collision=foreign;result=s.Replace();}
        RCheck(!result.committed && result.recoveryRequired,"Foreign collision did not require recovery");
        RCheck(NativeSaveArchive::Read(s.path)==foreign,"Foreign target was overwritten");
        RCheck(NativeSaveArchive::Read(result.recoveryPath)==s.before.Encode(),"Foreign collision lost original recovery file");
        RReject([&]{s.catalog->List();},"List crossed unresolved foreign collision");
        RReject([&]{s.catalog->WriteNew("new",s.after,Header(s.after));},"Write-new crossed unresolved transaction");
        RReject([&]{s.catalog->DeleteListed(s.listed,s.before.sections[0].bytes);},"Delete crossed unresolved transaction");
        RReject([&]{s.catalog->PrepareForMutation();},"Generic mutation preparation crossed unresolved transaction");
        RReject([&]{NativeSaveCatalog reject(s.directory);},"Constructor crossed unresolved foreign collision");
        RRemoveOwned(s.path,foreign);NativeSaveCatalog recovered(s.directory);
        RCheck(NativeSaveArchive::Read(s.path)==s.before.Encode(),"Collision remediation did not restore original");
        RCheck(recovered.Find(s.path).header!=nullptr,"Rollback recovery lost known old header");
    }
    for(unsigned corruption=0;corruption<6;++corruption){
        RSession s(directory,L"corrupt-"+std::to_wstring(corruption));NativeSaveCatalog::ReplacementResult result;
        {RScope scope;replaceProbe.failRename=2;replaceProbe.failRollback=true;result=s.Replace();}
        RCheck(!result.committed && result.recoveryRequired,"Unrestorable failure did not preserve recovery state");
        const auto journal=s.directory+L"\\.zerosis-replace-v1.journal";auto bytes=RRead(journal);
        if(corruption==0){bytes[0]^=1;RWrite(journal,bytes);}
        if(corruption==1){bytes[60]='/';const auto hash=NativeSaveArchive::Digest(bytes.data(),bytes.size()-32);std::copy(hash.begin(),hash.end(),bytes.end()-32);RWrite(journal,bytes);}
        if(corruption==2){const auto stage=RStage(s.directory);auto changed=RRead(stage);changed.back()^=1;RWrite(stage,changed);}
        if(corruption==3){const auto stage=RStage(s.directory);RCheck(SetFileAttributesW(stage.c_str(),FILE_ATTRIBUTE_READONLY)!=FALSE,"Cannot mark own stage read-only");}
        if(corruption==4){
            unsigned size=0;for(unsigned at=0;at<4;++at)size|=static_cast<unsigned>(bytes[56+at])<<(8*at);
            RCheck(60+size+12<bytes.size(),"Cannot locate journal root identity fixture");bytes[60+size]^=1;
            const auto hash=NativeSaveArchive::Digest(bytes.data(),bytes.size()-32);std::copy(hash.begin(),hash.end(),bytes.end()-32);RWrite(journal,bytes);
        }
        if(corruption==5){bytes.resize(16385,0);RWrite(journal,bytes);}
        RReject([&]{NativeSaveCatalog reject(s.directory);},"Corrupt/path-forged/changed/read-only recovery evidence accepted");
        RCheck(NativeSaveArchive::Read(result.recoveryPath)==s.before.Encode(),"Recovery rejection changed original evidence");
        if(corruption==3)RCheck(SetFileAttributesW(RStage(s.directory).c_str(),FILE_ATTRIBUTE_NORMAL)!=FALSE,"Cannot restore own fixture attributes");
    }
    {
        RSession s(directory,L"orphan");const auto orphan=s.directory+L"\\.zerosis-replace-v1-00000000000000000000000000000000.stage";
        HANDLE file=CreateFileW(orphan.c_str(),GENERIC_WRITE,0,nullptr,CREATE_NEW,FILE_ATTRIBUTE_NORMAL,nullptr);
        RCheck(file!=INVALID_HANDLE_VALUE,"Cannot create own orphan evidence");CloseHandle(file);
        RReject([&]{NativeSaveCatalog reject(s.directory);},"Untracked private stage was silently deleted");
        RCheck(GetFileAttributesW(orphan.c_str())!=INVALID_FILE_ATTRIBUTES,"Untracked evidence was removed");
        RCheck(NativeSaveArchive::Read(s.path)==s.before.Encode(),"Orphan rejection changed original");
    }
    std::printf("NATIVE_SAVE_REPLACEMENT_PASS checks=%u ATOMIC=false GAMECORE_LOADED=false RETAIL_SAVES_TOUCHED=false\n",replacementChecks);
}
void ReplacementCrashWrite(const std::wstring& directory,const std::string& phase){
    NativeSaveCatalog catalog(directory);const auto old=RArchive(60),next=RArchive(61);
    const auto path=catalog.WriteNew("existing",old,Header(old));const auto listed=catalog.Find(path);
    RScope scope;replaceProbe.crash=phase;
    catalog.WriteListedReplacement(listed,next,Header(next),old.sections[0].bytes);
    throw std::runtime_error("Requested own process interruption did not occur");
}
void ReplacementCrashRecover(const std::wstring& directory,const std::string& phase){
    const bool orphan=phase=="stage";bool rejected=false;
    try{NativeSaveCatalog catalog(directory);catalog.List();}catch(const std::exception&){rejected=true;if(!orphan)throw;}
    RCheck(rejected==orphan,"Interrupted-stage orphan was not preserved fail-closed");
    const auto expected=RArchive((phase=="new" || phase=="old-cleanup" || phase=="journal-cleanup")?61:60);
    RCheck(NativeSaveArchive::Read(directory+L"\\existing.zssave")==expected.Encode(),"Process-restart recovery archive differs");
    std::printf("NATIVE_SAVE_REPLACEMENT_RECOVERY_PASS phase=%s orphan_preserved=%s ATOMIC=false\n",phase.c_str(),orphan?"true":"false");
}
}
