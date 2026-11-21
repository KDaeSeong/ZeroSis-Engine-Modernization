#pragma once
#include "NativeSaveArchive.h"
#include "UiSaveMenuContract.h"
#include <cstddef>
#include <map>
#include <type_traits>

namespace ZeroSisHost {

// Current-session native saves only. This service never scans retail saves or
// reloads SDK state to manufacture a preview header for an older archive.
class NativeSaveCatalog final {
public:
    struct ReplacementResult final {
        bool committed=false,recoveryRequired=false;
        std::wstring path,recoveryPath;
        const char* diagnostic="UNCOMMITTED";
    };
    explicit NativeSaveCatalog(std::wstring directory):directory_(std::move(directory)){
        if(directory_.size()<=3 || directory_[1]!=L':' || directory_[2]!=L'\\' ||
           !((directory_[0]>=L'A' && directory_[0]<=L'Z') || (directory_[0]>=L'a' && directory_[0]<=L'z')) ||
           directory_.back()==L'\\' || directory_.find(L'/')!=std::wstring::npos ||
           directory_.find(L'\0')!=std::wstring::npos || directory_.find(L':',2)!=std::wstring::npos)
            throw std::invalid_argument("Save catalog requires an exact local absolute session directory");
        std::size_t at=3;
        PinDirectory(directory_.substr(0,3));
        while(at<directory_.size()){
            const auto end=directory_.find(L'\\',at);
            const auto count=(end==std::wstring::npos?directory_.size():end)-at;
            const auto component=directory_.substr(at,count);
            if(component.empty() || component==L"." || component==L".." || component.back()==L'.' || component.back()==L' ')
                throw std::invalid_argument("Save catalog directory contains an alias component");
            PinDirectory(directory_.substr(0,at+count));
            if(end==std::wstring::npos)break;
            at=end+1;
        }
        VerifyDirectories();RecoverReplacement();
    }
    NativeSaveCatalog(const NativeSaveCatalog&)=delete;
    NativeSaveCatalog& operator=(const NativeSaveCatalog&)=delete;
    // Generic checkpoint writers must call this before touching archive bytes.
    void PrepareForMutation(){RecoverReplacement();}

    static std::wstring DecodeName(const std::string& name){
        if(name.empty() || name.size()>128)throw std::invalid_argument("Save name must contain one to 32 Unicode scalars");
        auto wide=Wide(name);unsigned scalars=0;
        for(std::size_t at=0;at<wide.size();++at){
            const auto value=static_cast<unsigned>(wide[at]);
            if(value>=0xD800 && value<=0xDBFF){
                if(at+1>=wide.size() || wide[at+1]<0xDC00 || wide[at+1]>0xDFFF)
                    throw std::invalid_argument("Save name contains an incomplete Unicode scalar");
                ++at;
            }else if(value>=0xDC00 && value<=0xDFFF)
                throw std::invalid_argument("Save name contains an incomplete Unicode scalar");
            else if(value<32 || (value>=127 && value<=159) ||
                    std::wstring(L"<>:\"/\\|?*").find(wide[at])!=std::wstring::npos)
                throw std::invalid_argument("Save name contains a path or control character");
            if(++scalars>32)throw std::invalid_argument("Save name exceeds the original edit-box bound");
        }
        if(wide.front()==L' ' || wide.front()==L'.' || wide.back()==L' ' || wide.back()==L'.')
            throw std::invalid_argument("Save name has an ambiguous leading or trailing character");
        auto device=wide.substr(0,wide.find(L'.'));
        for(auto& value:device)if(value>=L'a' && value<=L'z')value=static_cast<wchar_t>(value-L'a'+L'A');
        if(device==L"CON" || device==L"PRN" || device==L"AUX" || device==L"NUL" ||
           device==L"CONIN$" || device==L"CONOUT$" ||
           (device.size()==4 && (device.substr(0,3)==L"COM" || device.substr(0,3)==L"LPT") &&
            ((device[3]>=L'1' && device[3]<=L'9') || device[3]==0x00B9 || device[3]==0x00B2 || device[3]==0x00B3)))
            throw std::invalid_argument("Save name is a reserved Windows device");
        return wide;
    }
    bool NameAvailable(const std::string& name) const {
        RecoverReplacement();
        std::wstring wide;
        try{wide=DecodeName(name);}catch(const std::invalid_argument&){return false;}
        VerifyDirectories();
        const auto path=directory_+L"\\"+wide+L".zssave";
        // The existing restore reader still uses an unprefixed Win32 path.
        // Do not create a name that this published read path cannot reopen.
        if(path.size()>=MAX_PATH)return false;
        if(GetFileAttributesW(Extended(path).c_str())!=INVALID_FILE_ATTRIBUTES)return false;
        const DWORD error=GetLastError();
        if(error==ERROR_FILE_NOT_FOUND)return true;
        throw std::runtime_error("Cannot check the session save name without ambiguity");
    }
    std::vector<UiSaveMenuFile> List() const {
        RecoverReplacement();
        VerifyDirectories();WIN32_FIND_DATAW data{};
        HANDLE search=FindFirstFileW(Extended(directory_+L"\\*").c_str(),&data);
        if(search==INVALID_HANDLE_VALUE){
            if(GetLastError()==ERROR_FILE_NOT_FOUND)return {};
            throw std::runtime_error("Cannot enumerate the current session save catalog");
        }
        struct Search final {HANDLE value;~Search(){FindClose(value);}} close{search};
        std::vector<UiSaveMenuFile> result;
        do{
            const std::wstring name=data.cFileName;
            if(!HasExtension(name))continue;
            result.push_back(ReadEntry(directory_+L"\\"+name).file);
        }while(FindNextFileW(search,&data));
        if(GetLastError()!=ERROR_NO_MORE_FILES)throw std::runtime_error("Session save enumeration was interrupted");
        std::sort(result.begin(),result.end(),[](const UiSaveMenuFile& left,const UiSaveMenuFile& right){
            return left.fileName<right.fileName;
        });
        return result;
    }
    UiSaveMenuFile Find(const std::wstring& path) const {RecoverReplacement();return ReadEntry(path).file;}

    // Read through the same pinned, non-shared-write handle used for catalog
    // validation. Only immutable decoded bytes leave this boundary; restoring
    // the fresh SDK session never opens this pathname again.
    std::shared_ptr<const NativeSaveArchive> ReadLoadArchive(const std::string& path,
            const UiSaveMenuFile& listed,const std::vector<unsigned char>& bundleManifest) const {
        RecoverReplacement();
        if(path!=listed.fileName || !listed.header || bundleManifest.empty() || bundleManifest.size()>16384)
            throw std::invalid_argument("Load requires an observed listed save and exact bundle manifest");
        auto entry=ReadEntry(Wide(path));
        const auto& current=entry.file;
        if(!current.header || current.fileName!=listed.fileName ||
           current.modificationTime!=listed.modificationTime ||
           current.modificationTimeHigh!=listed.modificationTimeHigh || current.modificationTimeLow!=listed.modificationTimeLow ||
           current.observedFileIdentity!=listed.observedFileIdentity || current.observedChecksum!=listed.observedChecksum ||
           !SameHeader(*current.header,*listed.header))
            throw std::invalid_argument("Load source differs from its immutable catalog observation");
        entry.archive.Validate();
        ValidateHeader(entry.archive,*current.header);
        if(entry.archive.sections[0].bytes!=bundleManifest)
            throw std::invalid_argument("Load source belongs to another engine bundle");
        return std::make_shared<const NativeSaveArchive>(std::move(entry.archive));
    }

    // Validate and delete the observed private save through one exclusive
    // handle. No pathname is reopened between the immutable observation check
    // and disposition, so a replacement can never become the deletion target.
    void DeleteListed(const UiSaveMenuFile& listed,const std::vector<unsigned char>& exactBundleManifest){
        RecoverReplacement();
        if(!listed.header || exactBundleManifest.empty() || exactBundleManifest.size()>16384)
            throw std::invalid_argument("Delete requires an observed listed save and exact bundle manifest");
        const auto path=Wide(listed.fileName);
        VerifyDirectories();ValidateChildPath(path);
        const auto prefix=directory_+L"\\";
        const auto recorded=headers_.find(path);
        if(path.compare(0,prefix.size(),prefix)!=0 || Utf8(path)!=listed.fileName ||
           recorded==headers_.end() || recorded->first!=path)
            throw std::invalid_argument("Delete source is not an exact observed session save path");
        const HANDLE value=CreateFileW(Extended(path).c_str(),GENERIC_READ|DELETE,0,nullptr,OPEN_EXISTING,
            FILE_ATTRIBUTE_NORMAL|FILE_FLAG_OPEN_REPARSE_POINT,nullptr);
        if(value==INVALID_HANDLE_VALUE)throw std::runtime_error("Cannot exclusively open the listed save for deletion");
        Handle file(value);auto entry=ReadOpenedEntry(value,path);const auto& current=entry.file;
        if(!current.header || Utf8(FinalPath(value))!=listed.fileName || current.fileName!=listed.fileName ||
           current.modificationTime!=listed.modificationTime ||
           current.modificationTimeHigh!=listed.modificationTimeHigh || current.modificationTimeLow!=listed.modificationTimeLow ||
           current.observedFileIdentity!=listed.observedFileIdentity || current.observedChecksum!=listed.observedChecksum ||
           !SameHeader(*current.header,*listed.header))
            throw std::invalid_argument("Delete source differs from its immutable catalog observation");
        entry.archive.Validate();ValidateHeader(entry.archive,*current.header);
        if(entry.archive.sections[0].bytes!=exactBundleManifest)
            throw std::invalid_argument("Delete source belongs to another engine bundle");
        VerifyDirectories();
        const auto finalInfo=OrdinaryFile(value,path);
        if(!SameInfo(entry.info,finalInfo) || (finalInfo.dwFileAttributes&FILE_ATTRIBUTE_READONLY))
            throw std::invalid_argument("Delete source changed or is read-only");
        FILE_DISPOSITION_INFO disposal{};disposal.DeleteFile=TRUE;
        if(!SetFileInformationByHandle(value,FileDispositionInfo,&disposal,sizeof(disposal)))
            throw std::runtime_error("Cannot delete the exclusively validated listed save");
        headers_.erase(recorded);
    }

    // Two no-replace renames plus an independently flushed private journal.
    // This is recoverable across process interruption, not an atomic replace or
    // a claim about power-loss ordering of filesystem directory metadata.
    ReplacementResult WriteListedReplacement(const UiSaveMenuFile& listed,const NativeSaveArchive& archive,
            const UiSaveMenuHeader& header,const std::vector<unsigned char>& exactBundleManifest){
        RecoverReplacement();
        if(!listed.header || exactBundleManifest.empty() || exactBundleManifest.size()>16384)
            throw std::invalid_argument("Replacement requires a listed save and exact bundle manifest");
        const auto path=Wide(listed.fileName);ValidateChildPath(path);VerifyDirectories();
        const auto recorded=headers_.find(path);
        if(recorded==headers_.end() || recorded->first!=path || Utf8(path)!=listed.fileName)
            throw std::invalid_argument("Replacement source is not an exact observed catalog path");
        const HANDLE oldValue=CreateFileW(Extended(path).c_str(),GENERIC_READ|DELETE,0,nullptr,
            OPEN_EXISTING,FILE_ATTRIBUTE_NORMAL|FILE_FLAG_OPEN_REPARSE_POINT,nullptr);
        if(oldValue==INVALID_HANDLE_VALUE)throw std::runtime_error("Cannot exclusively open the replacement source");
        Handle oldFile(oldValue);auto old=ReadOpenedEntry(oldValue,path);
        if(!old.file.header || old.file.fileName!=listed.fileName || Utf8(FinalPath(oldValue))!=listed.fileName ||
           old.file.modificationTime!=listed.modificationTime ||
           old.file.modificationTimeHigh!=listed.modificationTimeHigh || old.file.modificationTimeLow!=listed.modificationTimeLow ||
           old.file.observedFileIdentity!=listed.observedFileIdentity || old.file.observedChecksum!=listed.observedChecksum ||
           !SameHeader(*old.file.header,*listed.header) || (old.info.dwFileAttributes&FILE_ATTRIBUTE_READONLY))
            throw std::invalid_argument("Replacement source differs from its immutable catalog observation");
        ValidateHeader(old.archive,*old.file.header);ValidateHeader(archive,header);
        if(old.archive.sections[0].bytes!=exactBundleManifest || archive.sections[0].bytes!=exactBundleManifest)
            throw std::invalid_argument("Replacement archive belongs to another engine bundle");
        const auto bytes=archive.Encode();NativeSaveArchive::Decode(bytes);
        Transaction transaction;transaction.target=path;transaction.old=RecordFor(old.info,old.bytes,*listed.header);
        transaction.bundle=NativeSaveArchive::Digest(exactBundleManifest.data(),exactBundleManifest.size());
        transaction.root=pins_.back().identity;transaction.token=TransactionToken();
        SetTransactionPaths(transaction);
        ReplacementResult complete{true,false,path,L"","REPLACED"};
        ReplacementResult committedPending{true,true,path,JournalPath(),"COMMITTED_CLEANUP_REQUIRES_RECOVERY"};
        ReplacementResult pending{false,true,path,transaction.recovery,"REPLACEMENT_REQUIRES_RECOVERY"};
        ReplacementResult rollbackPending{false,true,path,JournalPath(),"ORIGINAL_RESTORED_CLEANUP_REQUIRES_RECOVERY"};
        ReplacementResult stagePending{false,true,path,transaction.stage,"UNCOMMITTED_STAGE_REQUIRES_RECOVERY"};
        static_assert(std::is_nothrow_move_assignable<Record>::value,"Postcommit catalog handoff must not allocate");
        static_assert(std::is_nothrow_move_constructible<ReplacementResult>::value,"Postcommit result handoff must not allocate");
        const auto oldToRecovery=RenameBuffer(transaction.recovery),stageToTarget=RenameBuffer(path),oldToTarget=RenameBuffer(path);
        std::unique_ptr<Handle> stage,journal;bool oldMoved=false,committed=false,journalReady=false,stageIdentified=false,stageMayRemain=false;
        Identity stageIdentity{};
        try{
            stage=CreatePrivate(transaction.stage);
            stageMayRemain=true;
            stageIdentity=ID(OrdinaryFile(stage->value,transaction.stage));stageIdentified=true;
            WriteAndFlush(stage->value,bytes);
            const auto initial=OrdinaryFile(stage->value,transaction.stage);
            if(ReadBytes(stage->value)!=bytes)throw std::runtime_error("Replacement stage readback differs");
            // Settle the writing handle's FILETIME before the transaction can commit.
            stage.reset();stage=OpenPrivate(transaction.stage);
            if(!stage){stageMayRemain=false;throw std::runtime_error("Replacement stage disappeared before settling");}
            const auto settled=OrdinaryFile(stage->value,transaction.stage);
            if(!SameID(ID(initial),ID(settled)) || ReadBytes(stage->value)!=bytes)
                throw std::runtime_error("Replacement stage changed before journal publication");
            transaction.next=RecordFor(settled,bytes,header);
            const auto journalBytes=EncodeTransaction(transaction);
            journal=CreatePrivate(JournalPath());WriteAndFlush(journal->value,journalBytes);
            if(ReadBytes(journal->value)!=journalBytes)throw std::runtime_error("Replacement journal readback differs");
            journalReady=true;VerifyDirectories();
            if(!SameInfo(old.info,OrdinaryFile(oldValue,path)))throw std::runtime_error("Replacement source changed before rename");
            RenameExact(oldValue,oldToRecovery);oldMoved=true;
            RenameExact(stage->value,stageToTarget);committed=true;
            // No potentially allocating Record/header construction after commit.
            recorded->second=std::move(transaction.next);
            if(!SameInfo(recorded->second.info,OrdinaryFile(stage->value,path)))
                throw std::runtime_error("Committed replacement metadata requires recovery");
            if(!SameInfo(transaction.old.info,OrdinaryFile(oldValue,transaction.recovery)))
                throw std::runtime_error("Replacement recovery identity changed");
            Dispose(oldValue);Dispose(journal->value);
            return complete;
        }catch(...){
            if(committed)return committedPending;
            if(oldMoved){
                // A foreign occupant is never replaced, even to restore the original.
                if(!TryRename(oldValue,oldToTarget))return pending;
                try{
                    if(!SameInfo(transaction.old.info,OrdinaryFile(oldValue,path)))return rollbackPending;
                    if(stage){ValidateTransactionFile(stage->value,transaction.stage,transaction.next,transaction.bundle);Dispose(stage->value);}
                    if(journal)Dispose(journal->value);
                }catch(...){return rollbackPending;}
                throw;
            }
            // Until a fully verified journal exists, the original has never moved.
            // An unknown/corrupt stage is evidence, not a pathname to unlink.
            // Closing the writer does not prove its path disappeared. A failed
            // exclusive reopen can leave an owned stage held by another reader.
            if(!stage && stageMayRemain)return stagePending;
            try{
                if(stage){
                    const auto stageInfo=OrdinaryFile(stage->value,transaction.stage);
                    if(!stageIdentified || !SameID(ID(stageInfo),stageIdentity) ||
                       (stageInfo.dwFileAttributes&FILE_ATTRIBUTE_READONLY))throw std::runtime_error("Unknown replacement stage");
                    Dispose(stage->value);
                    stageMayRemain=false;
                }
                if(journal && !journalReady)Dispose(journal->value);
                else if(journalReady)Dispose(journal->value);
            }catch(...){return journal?rollbackPending:stagePending;}
            throw;
        }
    }

    // Original LoadMenu sorts newest first when UI.CompareFileTime returns 1.
    // Never merge the words through a Lua double, which loses low FILETIME bits.
    static int CompareModificationTimes(std::uint32_t firstHigh,std::uint32_t firstLow,
                                        std::uint32_t secondHigh,std::uint32_t secondLow) noexcept {
        const FILETIME first{static_cast<DWORD>(firstLow),static_cast<DWORD>(firstHigh)};
        const FILETIME second{static_cast<DWORD>(secondLow),static_cast<DWORD>(secondHigh)};
        return static_cast<int>(::CompareFileTime(&first,&second));
    }

    // V1 bytes are identical to ordinary checkpoints. An exclusive temporary
    // handle is renamed without replacement, so no close/rename alias gap can
    // overwrite another save. The destination is verified on that same handle.
    std::wstring WriteNew(const std::string& name,const NativeSaveArchive& archive,const UiSaveMenuHeader& header){
        const auto wide=DecodeName(name);
        if(!NameAvailable(name))throw std::invalid_argument("Session save name is used or outside the verified native load path bound");
        ValidateHeader(archive,header);
        const auto bytes=archive.Encode();NativeSaveArchive::Decode(bytes);
        const auto destination=directory_+L"\\"+wide+L".zssave";
        static volatile LONG sequence=0;
        std::wstring temporary;std::unique_ptr<Handle> file;
        for(unsigned attempt=0;attempt<128;++attempt){
            temporary=destination+L".tmp-"+std::to_wstring(GetCurrentProcessId())+L"-"+
                std::to_wstring(static_cast<unsigned long>(InterlockedIncrement(&sequence)));
            const HANDLE value=CreateFileW(Extended(temporary).c_str(),GENERIC_READ|GENERIC_WRITE|DELETE,0,nullptr,
                CREATE_NEW,FILE_ATTRIBUTE_NORMAL|FILE_FLAG_OPEN_REPARSE_POINT,nullptr);
            if(value!=INVALID_HANDLE_VALUE){file.reset(new Handle(value));break;}
            const DWORD error=GetLastError();
            if(error!=ERROR_FILE_EXISTS && error!=ERROR_ALREADY_EXISTS)throw std::runtime_error("Cannot create a named save transaction");
        }
        if(!file)throw std::runtime_error("Named save transaction name collision");
        bool committed=false;Record completed{};
        try{
            OrdinaryFile(file->value,temporary);
            std::size_t at=0;
            while(at<bytes.size()){
                const auto count=static_cast<DWORD>(std::min<std::size_t>(bytes.size()-at,1024*1024));DWORD written=0;
                if(!WriteFile(file->value,bytes.data()+at,count,&written,nullptr) || !written || written>count)
                    throw std::runtime_error("Named save transaction write failed");
                at+=written;
            }
            if(!FlushFileBuffers(file->value))throw std::runtime_error("Cannot flush a named save transaction");
            VerifyDirectories();
            const auto renamePath=Extended(destination);
            const auto nameBytes=renamePath.size()*sizeof(wchar_t);
            std::vector<unsigned char> buffer(offsetof(FILE_RENAME_INFO,FileName)+nameBytes+sizeof(wchar_t));
            auto* rename=reinterpret_cast<FILE_RENAME_INFO*>(buffer.data());
            rename->ReplaceIfExists=FALSE;rename->RootDirectory=nullptr;rename->FileNameLength=static_cast<DWORD>(nameBytes);
            std::memcpy(rename->FileName,renamePath.data(),nameBytes);
            if(!SetFileInformationByHandle(file->value,FileRenameInfo,rename,static_cast<DWORD>(buffer.size())))
                throw std::runtime_error("Cannot publish a new named save without replacement");
            committed=true;
            if(!FlushFileBuffers(file->value))throw std::runtime_error("Cannot flush the committed named save");
            const auto info=OrdinaryFile(file->value,destination);
            if(ReadBytes(file->value)!=bytes)throw std::runtime_error("Committed named save bytes differ");
            VerifyDirectories();
            completed=RecordFor(info,bytes,header);
        }catch(...){
            if(!committed){
                // Delete through the still-exclusive owned handle; never unlink
                // a pathname after another writer could have replaced it.
                FILE_DISPOSITION_INFO disposal{};disposal.DeleteFile=TRUE;
                if(!SetFileInformationByHandle(file->value,FileDispositionInfo,&disposal,sizeof(disposal)))
                    throw std::runtime_error("Cannot remove the owned failed named save transaction");
            }
            throw;
        }
        // Last-write timestamps may settle only when the writing handle closes.
        // Reopen with mutation denied and attach metadata only if the committed
        // file identity and validated archive checksum remain the same.
        file.reset();
        auto entry=ReadEntry(destination);
        if(!SameID(ID(completed.info),ID(entry.info)) || completed.checksum!=Checksum(entry.bytes))
            throw std::runtime_error("Committed named save changed before catalog handoff");
        headers_[destination]=RecordFor(entry.info,entry.bytes,header);
        return destination;
    }
    void ObserveWrittenSave(const std::wstring& path,const UiSaveMenuHeader& header){
        RecoverReplacement();
        auto entry=ReadEntry(path);ValidateHeader(entry.archive,header);
        headers_[path]=RecordFor(entry.info,entry.bytes,header);
    }
private:
    struct Handle final {
        explicit Handle(HANDLE input):value(input){}
        ~Handle(){if(value!=INVALID_HANDLE_VALUE)CloseHandle(value);}
        Handle(const Handle&)=delete;Handle& operator=(const Handle&)=delete;
        HANDLE value;
    };
    struct Identity final {DWORD volume,high,low;};
    struct DirectoryPin final {std::wstring path;std::unique_ptr<Handle> file;Identity identity;};
    struct Record final {BY_HANDLE_FILE_INFORMATION info;std::array<unsigned char,32> checksum;UiSaveMenuHeader header;};
    struct Entry final {UiSaveMenuFile file;BY_HANDLE_FILE_INFORMATION info;NativeSaveArchive archive;std::vector<unsigned char> bytes;};
    struct Transaction final {
        std::wstring target,stage,recovery;std::string token;
        Identity root{};Record old{},next{};std::array<unsigned char,32> bundle{};
    };
    struct Less final {
        bool operator()(const std::wstring& left,const std::wstring& right) const {
            return CompareStringOrdinal(left.c_str(),static_cast<int>(left.size()),right.c_str(),static_cast<int>(right.size()),TRUE)==CSTR_LESS_THAN;
        }
    };
    std::wstring JournalPath() const {return directory_+L"\\.zerosis-replace-v1.journal";}
    static std::string TransactionToken(){
        unsigned char random[16]{};
        if(BCryptGenRandom(nullptr,random,sizeof(random),BCRYPT_USE_SYSTEM_PREFERRED_RNG)!=0)
            throw std::runtime_error("Cannot allocate a private replacement identity");
        const char digits[]="0123456789abcdef";std::string token;token.reserve(32);
        for(const auto value:random){token.push_back(digits[value>>4]);token.push_back(digits[value&15]);}
        return token;
    }
    void SetTransactionPaths(Transaction& transaction) const {
        if(transaction.token.size()!=32 || transaction.token.find_first_not_of("0123456789abcdef")!=std::string::npos)
            throw std::invalid_argument("Invalid replacement journal token");
        ValidateChildPath(transaction.target);
        const auto name=transaction.target.substr(directory_.size()+1);
        if(directory_+L"\\"+DecodeName(Utf8(name.substr(0,name.size()-7)))+L".zssave"!=transaction.target)
            throw std::invalid_argument("Replacement target is not an exact bounded owned save name");
        transaction.stage=directory_+L"\\.zerosis-replace-v1-"+Wide(transaction.token)+L".stage";
        transaction.recovery=directory_+L"\\.zerosis-replace-v1-"+Wide(transaction.token)+L".recovery";
    }
    static std::unique_ptr<Handle> CreatePrivate(const std::wstring& path){
        const HANDLE value=CreateFileW(Extended(path).c_str(),GENERIC_READ|GENERIC_WRITE|DELETE,0,nullptr,
            CREATE_NEW,FILE_ATTRIBUTE_NORMAL|FILE_FLAG_OPEN_REPARSE_POINT,nullptr);
        if(value==INVALID_HANDLE_VALUE)throw std::runtime_error("Cannot create an exclusive private replacement file");
        try{return std::unique_ptr<Handle>(new Handle(value));}catch(...){CloseHandle(value);throw;}
    }
    static std::unique_ptr<Handle> OpenPrivate(const std::wstring& path){
        const HANDLE value=CreateFileW(Extended(path).c_str(),GENERIC_READ|DELETE,0,nullptr,
            OPEN_EXISTING,FILE_ATTRIBUTE_NORMAL|FILE_FLAG_OPEN_REPARSE_POINT,nullptr);
        if(value!=INVALID_HANDLE_VALUE){try{return std::unique_ptr<Handle>(new Handle(value));}catch(...){CloseHandle(value);throw;}}
        if(GetLastError()==ERROR_FILE_NOT_FOUND)return {};
        throw std::runtime_error("Private replacement file is locked or cannot be identified");
    }
    static void WriteAndFlush(HANDLE value,const std::vector<unsigned char>& bytes){
        std::size_t at=0;
        while(at<bytes.size()){
            const auto count=static_cast<DWORD>(std::min<std::size_t>(bytes.size()-at,1024*1024));DWORD written=0;
            if(!WriteFile(value,bytes.data()+at,count,&written,nullptr) || !written || written>count)
                throw std::runtime_error("Replacement private file write failed");
            at+=written;
        }
        if(!FlushFileBuffers(value))throw std::runtime_error("Replacement private file flush failed");
    }
    static std::vector<unsigned char> RenameBuffer(const std::wstring& path){
        const auto extended=Extended(path);const auto size=extended.size()*sizeof(wchar_t);
        std::vector<unsigned char> bytes(offsetof(FILE_RENAME_INFO,FileName)+size+sizeof(wchar_t));
        auto* value=reinterpret_cast<FILE_RENAME_INFO*>(bytes.data());
        value->ReplaceIfExists=FALSE;value->RootDirectory=nullptr;value->FileNameLength=static_cast<DWORD>(size);
        std::memcpy(value->FileName,extended.data(),size);return bytes;
    }
    static bool TryRename(HANDLE value,const std::vector<unsigned char>& bytes) noexcept {
        return SetFileInformationByHandle(value,FileRenameInfo,const_cast<unsigned char*>(bytes.data()),static_cast<DWORD>(bytes.size()))!=FALSE;
    }
    static void RenameExact(HANDLE value,const std::vector<unsigned char>& bytes){
        if(!TryRename(value,bytes))throw std::runtime_error("Replacement no-replace rename failed");
    }
    static void Dispose(HANDLE value){
        FILE_DISPOSITION_INFO disposal{};disposal.DeleteFile=TRUE;
        if(!SetFileInformationByHandle(value,FileDispositionInfo,&disposal,sizeof(disposal)))
            throw std::runtime_error("Replacement validated-handle cleanup failed");
    }
    static void PutWord(std::vector<unsigned char>& out,unsigned value){
        for(unsigned shift=0;shift<32;shift+=8)out.push_back(static_cast<unsigned char>(value>>shift));
    }
    static void PutText(std::vector<unsigned char>& out,const std::string& value){
        if(value.size()>1024 || value.find('\0')!=std::string::npos)throw std::invalid_argument("Replacement journal text exceeds its bound");
        if(!value.empty())Wide(value);
        PutWord(out,static_cast<unsigned>(value.size()));out.insert(out.end(),value.begin(),value.end());
    }
    static void PutRecord(std::vector<unsigned char>& out,const Record& record){
        const auto& i=record.info;const auto& h=record.header;
        for(const auto value:{i.dwVolumeSerialNumber,i.nFileIndexHigh,i.nFileIndexLow,i.dwFileAttributes,i.nNumberOfLinks,
                i.nFileSizeHigh,i.nFileSizeLow,i.ftLastWriteTime.dwHighDateTime,i.ftLastWriteTime.dwLowDateTime})PutWord(out,value);
        out.insert(out.end(),record.checksum.begin(),record.checksum.end());
        for(const auto value:{h.playerCivilization,h.gameSpeed,h.startEra,h.turnNumber,h.difficulty,h.worldSize,h.currentEra,h.gameType})
            PutWord(out,static_cast<unsigned>(value));
        PutText(out,h.mapScript);PutText(out,h.leaderName);PutText(out,h.civilizationName);
    }
    static std::vector<unsigned char> EncodeTransaction(const Transaction& transaction){
        const unsigned char magic[16]={'Z','S','R','E','P','L','A','C','E','_','V','1',0,0,0,0};
        std::vector<unsigned char> out(magic,magic+16);PutWord(out,1);
        PutText(out,transaction.token);
        const auto slash=transaction.target.find_last_of(L'\\');PutText(out,Utf8(transaction.target.substr(slash+1)));
        PutWord(out,transaction.root.volume);PutWord(out,transaction.root.high);PutWord(out,transaction.root.low);
        out.insert(out.end(),transaction.bundle.begin(),transaction.bundle.end());
        PutRecord(out,transaction.old);PutRecord(out,transaction.next);
        if(out.size()>16352)throw std::length_error("Replacement journal exceeds its bound");
        const auto digest=NativeSaveArchive::Digest(out.data(),out.size());out.insert(out.end(),digest.begin(),digest.end());return out;
    }
    Transaction DecodeTransaction(const std::vector<unsigned char>& bytes) const {
        const unsigned char magic[16]={'Z','S','R','E','P','L','A','C','E','_','V','1',0,0,0,0};
        if(bytes.size()<256 || bytes.size()>16384 || std::memcmp(bytes.data(),magic,16)!=0)
            throw std::invalid_argument("Corrupt or oversized replacement journal");
        const auto end=bytes.size()-32;const auto digest=NativeSaveArchive::Digest(bytes.data(),end);
        if(std::memcmp(digest.data(),bytes.data()+end,32)!=0)throw std::invalid_argument("Replacement journal checksum differs");
        std::size_t at=16;
        const auto word=[&](){
            if(at>end || end-at<4)throw std::invalid_argument("Truncated replacement journal field");
            unsigned value=0;for(unsigned shift=0;shift<32;shift+=8)value|=static_cast<unsigned>(bytes[at++])<<shift;return value;
        };
        const auto text=[&](){
            const auto size=word();if(size>1024 || size>end-at)throw std::invalid_argument("Unbounded replacement journal text");
            std::string value(bytes.begin()+at,bytes.begin()+at+size);at+=size;
            if(value.find('\0')!=std::string::npos)throw std::invalid_argument("Replacement journal contains a text alias");
            if(!value.empty())Wide(value);return value;
        };
        const auto record=[&](){
            Record value{};auto& i=value.info;auto& h=value.header;
            i.dwVolumeSerialNumber=word();i.nFileIndexHigh=word();i.nFileIndexLow=word();i.dwFileAttributes=word();i.nNumberOfLinks=word();
            i.nFileSizeHigh=word();i.nFileSizeLow=word();i.ftLastWriteTime.dwHighDateTime=word();i.ftLastWriteTime.dwLowDateTime=word();
            if(end-at<32)throw std::invalid_argument("Truncated replacement identity");
            std::copy(bytes.begin()+at,bytes.begin()+at+32,value.checksum.begin());at+=32;
            int* fields[]={&h.playerCivilization,&h.gameSpeed,&h.startEra,&h.turnNumber,&h.difficulty,&h.worldSize,&h.currentEra,&h.gameType};
            for(auto* field:fields){const auto scalar=word();static_assert(sizeof(scalar)==sizeof(*field),"Journal scalar width differs");std::memcpy(field,&scalar,sizeof(scalar));}
            h.mapScript=text();h.leaderName=text();h.civilizationName=text();
            if(i.nNumberOfLinks!=1 || (i.dwFileAttributes&(FILE_ATTRIBUTE_DIRECTORY|FILE_ATTRIBUTE_REPARSE_POINT|FILE_ATTRIBUTE_DEVICE|FILE_ATTRIBUTE_READONLY)))
                throw std::invalid_argument("Replacement journal describes a nonordinary file");
            return value;
        };
        if(word()!=1)throw std::invalid_argument("Unsupported replacement journal version");
        Transaction value;value.token=text();value.target=directory_+L"\\"+Wide(text());
        value.root={word(),word(),word()};if(!SameID(value.root,pins_.back().identity))throw std::invalid_argument("Replacement journal belongs to another root");
        if(end-at<32)throw std::invalid_argument("Truncated replacement bundle identity");
        std::copy(bytes.begin()+at,bytes.begin()+at+32,value.bundle.begin());at+=32;
        value.old=record();value.next=record();
        if(at!=end || SameID(ID(value.old.info),ID(value.next.info)))throw std::invalid_argument("Ambiguous replacement journal layout");
        SetTransactionPaths(value);return value;
    }
    void ValidateTransactionFile(HANDLE file,const std::wstring& path,const Record& record,
            const std::array<unsigned char,32>& bundle) const {
        const auto info=OrdinaryFile(file,path);
        if(!SameInfo(info,record.info) || (info.dwFileAttributes&FILE_ATTRIBUTE_READONLY))
            throw std::invalid_argument("Recovery file differs from its recorded identity or FILETIME");
        const auto bytes=ReadBytes(file);const auto archive=NativeSaveArchive::Decode(bytes);
        ValidateHeader(archive,record.header);
        const auto& manifest=archive.sections[0].bytes;
        if(Checksum(bytes)!=record.checksum || NativeSaveArchive::Digest(manifest.data(),manifest.size())!=bundle ||
           !SameInfo(info,OrdinaryFile(file,path)))throw std::invalid_argument("Recovery file checksum or bundle differs");
    }
    void RejectUntrackedReplacementFiles(const Transaction* transaction=nullptr) const {
        WIN32_FIND_DATAW data{};const HANDLE search=FindFirstFileW(Extended(directory_+L"\\.zerosis-replace-v1-*").c_str(),&data);
        if(search==INVALID_HANDLE_VALUE){
            if(GetLastError()!=ERROR_FILE_NOT_FOUND)throw std::runtime_error("Cannot check private replacement remnants");
            return;
        }
        struct Search final {HANDLE value;~Search(){FindClose(value);}} close{search};
        do{
            const auto path=directory_+L"\\"+data.cFileName;
            if(!transaction || (path!=transaction->stage && path!=transaction->recovery))
                throw std::runtime_error("Untracked replacement evidence requires manual recovery");
        }while(FindNextFileW(search,&data));
        if(GetLastError()!=ERROR_NO_MORE_FILES)throw std::runtime_error("Replacement remnant scan interrupted");
    }
    void RecoverReplacement() const {
        VerifyDirectories();auto journal=OpenPrivate(JournalPath());
        if(!journal){RejectUntrackedReplacementFiles();return;}
        const auto journalInfo=OrdinaryFile(journal->value,JournalPath());
        if(journalInfo.nFileSizeHigh || journalInfo.nFileSizeLow>16384 || journalInfo.nFileSizeLow<256 ||
           (journalInfo.dwFileAttributes&FILE_ATTRIBUTE_READONLY))throw std::runtime_error("Invalid replacement journal boundary");
        auto transaction=DecodeTransaction(ReadBytes(journal->value));
        RejectUntrackedReplacementFiles(&transaction);
        auto target=OpenPrivate(transaction.target),stage=OpenPrivate(transaction.stage),old=OpenPrivate(transaction.recovery);
        bool targetOld=false,targetNew=false;
        if(target){
            const auto id=ID(OrdinaryFile(target->value,transaction.target));
            targetOld=SameID(id,ID(transaction.old.info));targetNew=SameID(id,ID(transaction.next.info));
            if(!targetOld && !targetNew)throw std::runtime_error("Foreign recovery target preserved");
            ValidateTransactionFile(target->value,transaction.target,targetNew?transaction.next:transaction.old,transaction.bundle);
        }
        if(stage)ValidateTransactionFile(stage->value,transaction.stage,transaction.next,transaction.bundle);
        if(old)ValidateTransactionFile(old->value,transaction.recovery,transaction.old,transaction.bundle);
        if((targetOld && old) || (targetNew && stage) || (!target && !old))
            throw std::runtime_error("Ambiguous replacement state preserved");
        // All observed files were validated before the first recovery mutation.
        const auto rollback=RenameBuffer(transaction.target);
        headers_[transaction.target]=targetNew?transaction.next:transaction.old;
        if(!target){RenameExact(old->value,rollback);OrdinaryFile(old->value,transaction.target);}
        if(stage)Dispose(stage->value);
        if(old && targetNew)Dispose(old->value);
        if(!SameInfo(journalInfo,OrdinaryFile(journal->value,JournalPath())))throw std::runtime_error("Replacement journal changed during recovery");
        Dispose(journal->value);
    }
    static std::wstring Wide(const std::string& text){
        if(text.empty() || text.size()>static_cast<std::size_t>(INT_MAX) || text.find('\0')!=std::string::npos)
            throw std::invalid_argument("Save name is not bounded UTF-8 text");
        const int count=MultiByteToWideChar(CP_UTF8,MB_ERR_INVALID_CHARS,text.data(),static_cast<int>(text.size()),nullptr,0);
        if(!count)throw std::invalid_argument("Save name is not valid UTF-8");
        std::wstring result(static_cast<std::size_t>(count),L'\0');
        if(MultiByteToWideChar(CP_UTF8,MB_ERR_INVALID_CHARS,text.data(),static_cast<int>(text.size()),&result[0],count)!=count)
            throw std::invalid_argument("Save name Unicode conversion failed");
        return result;
    }
    static bool EqualPath(const std::wstring& left,const std::wstring& right){
        return left.size()<=static_cast<std::size_t>(INT_MAX) && right.size()<=static_cast<std::size_t>(INT_MAX) &&
            CompareStringOrdinal(left.c_str(),static_cast<int>(left.size()),right.c_str(),static_cast<int>(right.size()),TRUE)==CSTR_EQUAL;
    }
    static std::wstring Extended(const std::wstring& path){
        if(path.size()>32760)throw std::length_error("Session save path exceeds the Win32 Unicode bound");
        return L"\\\\?\\"+path;
    }
    static std::wstring FinalPath(HANDLE file){
        std::vector<wchar_t> path(32768);
        const DWORD count=GetFinalPathNameByHandleW(file,path.data(),static_cast<DWORD>(path.size()),FILE_NAME_NORMALIZED|VOLUME_NAME_DOS);
        if(!count || count>=path.size())throw std::runtime_error("Cannot resolve the exact session save path");
        std::wstring result(path.data(),count);
        if(result.compare(0,4,L"\\\\?\\")!=0)throw std::runtime_error("Session save path is outside the local DOS namespace");
        result.erase(0,4);
        if(result.size()>3 && result.back()==L'\\')result.pop_back();
        return result;
    }
    static BY_HANDLE_FILE_INFORMATION Info(HANDLE file){
        BY_HANDLE_FILE_INFORMATION info{};
        if(!GetFileInformationByHandle(file,&info))throw std::runtime_error("Cannot identify the current session save file");
        return info;
    }
    static Identity ID(const BY_HANDLE_FILE_INFORMATION& info){return {info.dwVolumeSerialNumber,info.nFileIndexHigh,info.nFileIndexLow};}
    static bool SameID(const Identity& left,const Identity& right){return left.volume==right.volume && left.high==right.high && left.low==right.low;}
    static bool SameInfo(const BY_HANDLE_FILE_INFORMATION& left,const BY_HANDLE_FILE_INFORMATION& right){
        return SameID(ID(left),ID(right)) && left.dwFileAttributes==right.dwFileAttributes && left.nNumberOfLinks==right.nNumberOfLinks &&
            left.nFileSizeHigh==right.nFileSizeHigh && left.nFileSizeLow==right.nFileSizeLow &&
            left.ftLastWriteTime.dwHighDateTime==right.ftLastWriteTime.dwHighDateTime && left.ftLastWriteTime.dwLowDateTime==right.ftLastWriteTime.dwLowDateTime;
    }
    void PinDirectory(const std::wstring& path){
        const HANDLE value=CreateFileW(Extended(path).c_str(),GENERIC_READ,FILE_SHARE_READ|FILE_SHARE_WRITE,nullptr,
            OPEN_EXISTING,FILE_FLAG_BACKUP_SEMANTICS|FILE_FLAG_OPEN_REPARSE_POINT,nullptr);
        if(value==INVALID_HANDLE_VALUE)throw std::runtime_error("Cannot pin a session save ancestor");
        DirectoryPin pin{path,std::unique_ptr<Handle>(new Handle(value)),ID(Info(value))};
        const auto info=Info(value);
        if(!(info.dwFileAttributes&FILE_ATTRIBUTE_DIRECTORY) || (info.dwFileAttributes&FILE_ATTRIBUTE_REPARSE_POINT) || !EqualPath(FinalPath(value),path))
            throw std::invalid_argument("Session save ancestor is a reparse point or path alias");
        pins_.push_back(std::move(pin));
    }
    void VerifyDirectories() const {
        for(const auto& pin:pins_){
            const auto info=Info(pin.file->value);
            if(!(info.dwFileAttributes&FILE_ATTRIBUTE_DIRECTORY) || (info.dwFileAttributes&FILE_ATTRIBUTE_REPARSE_POINT) ||
               !SameID(ID(info),pin.identity) || !EqualPath(FinalPath(pin.file->value),pin.path))
                throw std::runtime_error("Pinned session save ancestor changed identity");
        }
    }
    static BY_HANDLE_FILE_INFORMATION OrdinaryFile(HANDLE file,const std::wstring& path){
        const auto info=Info(file);
        const auto actual=FinalPath(file);
        if((info.dwFileAttributes&(FILE_ATTRIBUTE_DIRECTORY|FILE_ATTRIBUTE_REPARSE_POINT|FILE_ATTRIBUTE_DEVICE)) ||
           info.nNumberOfLinks!=1 || !EqualPath(actual,path))
            throw std::invalid_argument("Session save is a reparse point, hardlink or path alias: attributes="+
                std::to_string(info.dwFileAttributes)+" links="+std::to_string(info.nNumberOfLinks)+
                " expected="+Utf8(path)+" actual="+Utf8(actual));
        return info;
    }
    static bool HasExtension(const std::wstring& name){
        return name.size()>7 && EqualPath(name.substr(name.size()-7),L".zssave");
    }
    void ValidateChildPath(const std::wstring& path) const {
        const auto prefix=directory_+L"\\";
        if(path.size()<=prefix.size() || !EqualPath(path.substr(0,prefix.size()),prefix) || path.find(L'\0')!=std::wstring::npos)
            throw std::invalid_argument("Save preview path is outside its owned session");
        const auto name=path.substr(prefix.size());
        if(!HasExtension(name) || name.find_first_of(L"\\/:\"")!=std::wstring::npos || name==L"." || name==L"..")
            throw std::invalid_argument("Save preview path is not a direct native archive child");
    }
    static std::vector<unsigned char> ReadBytes(HANDLE file){
        LARGE_INTEGER size{};LARGE_INTEGER zero{};
        if(!GetFileSizeEx(file,&size) || size.QuadPart<80 ||
           static_cast<unsigned long long>(size.QuadPart)>std::numeric_limits<std::size_t>::max() ||
           !SetFilePointerEx(file,zero,nullptr,FILE_BEGIN))throw std::runtime_error("Invalid session save size or seek");
        std::vector<unsigned char> bytes(static_cast<std::size_t>(size.QuadPart));std::size_t at=0;
        while(at<bytes.size()){
            const auto count=static_cast<DWORD>(std::min<std::size_t>(bytes.size()-at,1024*1024));DWORD read=0;
            if(!ReadFile(file,bytes.data()+at,count,&read,nullptr) || !read || read>count)
                throw std::runtime_error("Session save changed during readback");
            at+=read;
        }
        return bytes;
    }
    static std::array<unsigned char,32> Checksum(const std::vector<unsigned char>& bytes){
        if(bytes.size()<80)throw std::invalid_argument("Session save is truncated");
        std::array<unsigned char,32> value{};std::copy(bytes.end()-32,bytes.end(),value.begin());return value;
    }
    static Record RecordFor(const BY_HANDLE_FILE_INFORMATION& info,const std::vector<unsigned char>& bytes,const UiSaveMenuHeader& header){
        return {info,Checksum(bytes),header};
    }
    static void ValidateHeader(const NativeSaveArchive& archive,const UiSaveMenuHeader& header){
        if(header.turnNumber!=archive.elapsed || header.gameType!=static_cast<int>(GAME_SINGLE_PLAYER))
            throw std::invalid_argument("Save preview header differs from its captured single-player archive");
    }
    static bool SameHeader(const UiSaveMenuHeader& left,const UiSaveMenuHeader& right){
        return left.playerCivilization==right.playerCivilization && left.gameSpeed==right.gameSpeed &&
            left.startEra==right.startEra && left.turnNumber==right.turnNumber && left.difficulty==right.difficulty &&
            left.worldSize==right.worldSize && left.currentEra==right.currentEra && left.gameType==right.gameType &&
            left.mapScript==right.mapScript && left.leaderName==right.leaderName && left.civilizationName==right.civilizationName;
    }
    static std::string ModificationTime(const FILETIME& time){
        FILETIME local{};SYSTEMTIME system{};
        if(!FileTimeToLocalFileTime(&time,&local) || !FileTimeToSystemTime(&local,&system))
            throw std::runtime_error("Cannot format the native save modification time");
        char text[32]{};
        std::snprintf(text,sizeof(text),"%04u-%02u-%02u %02u:%02u:%02u",static_cast<unsigned>(system.wYear),
            static_cast<unsigned>(system.wMonth),static_cast<unsigned>(system.wDay),static_cast<unsigned>(system.wHour),
            static_cast<unsigned>(system.wMinute),static_cast<unsigned>(system.wSecond));
        return text;
    }
    Entry ReadEntry(const std::wstring& path) const {
        VerifyDirectories();ValidateChildPath(path);
        const HANDLE value=CreateFileW(Extended(path).c_str(),GENERIC_READ,FILE_SHARE_READ,nullptr,OPEN_EXISTING,
            FILE_ATTRIBUTE_NORMAL|FILE_FLAG_OPEN_REPARSE_POINT,nullptr);
        if(value==INVALID_HANDLE_VALUE)throw std::runtime_error("Cannot open an ordinary owned session save");
        Handle file(value);return ReadOpenedEntry(value,path);
    }
    Entry ReadOpenedEntry(HANDLE value,const std::wstring& path) const {
        Entry entry;entry.info=OrdinaryFile(value,path);entry.bytes=ReadBytes(value);
        entry.archive=NativeSaveArchive::Decode(entry.bytes);
        if(!SameInfo(entry.info,OrdinaryFile(value,path)))throw std::runtime_error("Session save identity changed while cataloging");
        entry.file.fileName=Utf8(path);entry.file.modificationTime=ModificationTime(entry.info.ftLastWriteTime);
        entry.file.modificationTimeHigh=entry.info.ftLastWriteTime.dwHighDateTime;
        entry.file.modificationTimeLow=entry.info.ftLastWriteTime.dwLowDateTime;
        entry.file.observedFileIdentity={{entry.info.dwVolumeSerialNumber,entry.info.nFileIndexHigh,entry.info.nFileIndexLow}};
        entry.file.observedChecksum=Checksum(entry.bytes);
        const auto found=headers_.find(path);
        if(found!=headers_.end() && SameInfo(found->second.info,entry.info) && found->second.checksum==Checksum(entry.bytes))
            entry.file.header=std::make_shared<UiSaveMenuHeader>(found->second.header);
        VerifyDirectories();return entry;
    }
    std::wstring directory_;
    std::vector<DirectoryPin> pins_;
    mutable std::map<std::wstring,Record,Less> headers_;
};

}
