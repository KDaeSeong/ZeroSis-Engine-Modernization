#pragma once
#include "MenuMapDocument.h"
#include "UiMapMenuContract.h"
#include <windows.h>
#include <bcrypt.h>
#include <cstdio>
#include <cstring>
#include <memory>
#include <algorithm>

namespace ZeroSisHost {
// Only this isolated session's Maps directory is writable. An SDK writer gets
// a fresh staging filename; it never receives a user's existing destination.
class NativeMapCatalog final {
    struct Handle final {
        HANDLE value=INVALID_HANDLE_VALUE;
        explicit Handle(HANDLE v):value(v){if(v==INVALID_HANDLE_VALUE)throw std::runtime_error("Cannot open an owned map file");}
        ~Handle(){CloseHandle(value);}
        Handle(const Handle&)=delete;Handle& operator=(const Handle&)=delete;
    };
public:
    explicit NativeMapCatalog(const std::wstring& sessionDirectory):directory_(sessionDirectory+L"\\Maps"){
        if(sessionDirectory.size()<3 || sessionDirectory[1]!=L':' || sessionDirectory[2]!=L'\\' ||
           sessionDirectory.find(L'/')!=std::wstring::npos || sessionDirectory.find(L"\\..")!=std::wstring::npos)
            throw std::invalid_argument("Map catalog requires an absolute owned session directory");
        for(std::size_t at=3;at<=sessionDirectory.size();++at)if(at==sessionDirectory.size() || sessionDirectory[at]==L'\\')Pin(sessionDirectory.substr(0,at));
        if(!CreateDirectoryW(FileApiPath(directory_).c_str(),nullptr) && GetLastError()!=ERROR_ALREADY_EXISTS)
            throw std::runtime_error("Cannot create the private map directory");
        Pin(directory_);
        lock_.reset(new Handle(CreateFileW(FileApiPath(directory_+L"\\.map.lock").c_str(),GENERIC_READ|GENERIC_WRITE,0,nullptr,OPEN_ALWAYS,
                                         FILE_ATTRIBUTE_NORMAL|FILE_FLAG_OPEN_REPARSE_POINT,nullptr)));
        Ordinary(lock_->value);
        if(GetFileAttributesW(FileApiPath(directory_+L"\\.map-replace.pending").c_str())!=INVALID_FILE_ATTRIBUTES)
            throw std::runtime_error("An interrupted map replacement requires recovery; its original files are preserved");
    }
    static std::wstring DecodeName(const std::string& name){
        if(name.empty() || name.size()>240 || name.front()==' ' || name.back()==' ' || name.back()=='.' ||
           name.find_first_of("\\/:*?\"<>|%")!=std::string::npos || name=="." || name=="..")
            throw std::invalid_argument("Map name is not a bounded Windows leaf name");
        for(unsigned char ch:name)if(ch<32)throw std::invalid_argument("Control character in map name");
        const int size=MultiByteToWideChar(CP_UTF8,MB_ERR_INVALID_CHARS,name.data(),static_cast<int>(name.size()),nullptr,0);
        if(size<=0 || size>100)throw std::invalid_argument("Map name is not bounded UTF-8");
        std::wstring result(static_cast<std::size_t>(size),L'\0');
        if(MultiByteToWideChar(CP_UTF8,MB_ERR_INVALID_CHARS,name.data(),static_cast<int>(name.size()),&result[0],size)!=size)
            throw std::invalid_argument("Map name conversion failed");
        auto stem=result.substr(0,result.find(L'.'));for(auto& ch:stem)if(ch>=L'a' && ch<=L'z')ch-=L'a'-L'A';
        if(stem==L"CON" || stem==L"PRN" || stem==L"AUX" || stem==L"NUL" ||
           (stem.size()==4 && (stem.substr(0,3)==L"COM" || stem.substr(0,3)==L"LPT") && stem[3]>=L'0' && stem[3]<=L'9'))
            throw std::invalid_argument("Reserved device name is not a map filename");
        return result;
    }
    bool NameAvailable(const std::string& name) const {
        const auto path=Path(name);const auto attrs=GetFileAttributesW(FileApiPath(path).c_str());
        if(attrs!=INVALID_FILE_ATTRIBUTES)return false;
        if(GetLastError()!=ERROR_FILE_NOT_FOUND)throw std::runtime_error("Cannot inspect private map destination");
        return true;
    }
    std::vector<UiMapMenuFile> List() const {
        std::vector<UiMapMenuFile> result;WIN32_FIND_DATAW data{};
        const HANDLE search=FindFirstFileW(FileApiPath(directory_+L"\\*.Civ5Map").c_str(),&data);
        if(search==INVALID_HANDLE_VALUE){if(GetLastError()==ERROR_FILE_NOT_FOUND)return result;throw std::runtime_error("Cannot enumerate private maps");}
        do{
            try{result.emplace_back(Read(directory_+L"\\"+data.cFileName));}
            catch(...){FindClose(search);throw;}
        }while(FindNextFileW(search,&data));
        const auto error=GetLastError();FindClose(search);
        if(error!=ERROR_NO_MORE_FILES)throw std::runtime_error("Private map enumeration was interrupted");
        std::sort(result.begin(),result.end(),[](const UiMapMenuFile& a,const UiMapMenuFile& b){return a.path<b.path;});
        return result;
    }
    using Writer=std::function<bool(const std::wstring&,const std::string&)>;
    UiMapMenuFile Save(const std::string& name,const std::shared_ptr<const UiMapMenuFile>& expected,const Writer& writer){
        if(!writer)throw std::invalid_argument("Map saving requires the actual SDK map writer");
        const auto destination=Path(name);std::unique_ptr<Handle> old;
        if(expected){
            if(expected->path!=Utf8(destination))throw std::invalid_argument("Overwrite name differs from its selected map");
            old.reset(new Handle(CreateFileW(FileApiPath(destination).c_str(),GENERIC_READ|DELETE,0,nullptr,OPEN_EXISTING,
                                           FILE_ATTRIBUTE_NORMAL|FILE_FLAG_OPEN_REPARSE_POINT,nullptr)));
            Match(*expected,Observe(old->value,destination));
        }else if(!NameAvailable(name))throw std::invalid_argument("A map already exists; explicit observed overwrite is required");
        const auto token=Token();const auto temporary=directory_+L"\\.map-"+token+L".stage";
        const auto recovery=directory_+L"\\.map-"+token+L".recovery";
        // Reserve with CREATE_NEW first. The SDK writer may only truncate this
        // exact private leaf after the reservation has been checked and closed.
        {Handle reserve(CreateFileW(FileApiPath(temporary).c_str(),GENERIC_WRITE,0,nullptr,CREATE_NEW,
                                   FILE_ATTRIBUTE_NORMAL|FILE_FLAG_OPEN_REPARSE_POINT,nullptr));Ordinary(reserve.value);}
        bool movedOld=false,published=false;std::unique_ptr<Handle> stage;
        try{
            const auto writerPath=temporary.size()>=MAX_PATH?FileApiPath(temporary):temporary;
            if(!writer(writerPath,name))throw std::runtime_error("SDK map serialization failed");
            stage.reset(new Handle(CreateFileW(FileApiPath(temporary).c_str(),GENERIC_READ|GENERIC_WRITE|DELETE,0,nullptr,OPEN_EXISTING,
                                              FILE_ATTRIBUTE_NORMAL|FILE_FLAG_OPEN_REPARSE_POINT,nullptr)));
            const auto next=Observe(stage->value,temporary);
            if(!FlushFileBuffers(stage->value))throw std::runtime_error("Cannot flush serialized map");
            if(old){
                const auto journal=directory_+L"\\.map-replace.pending";
                WriteJournal(journal,Utf8(destination)+"\n"+Utf8(temporary)+"\n"+Utf8(recovery)+"\n");
                Rename(old->value,recovery);movedOld=true;
            }
            Rename(stage->value,destination);published=true;
            const auto actual=Observe(stage->value,destination);
            if(actual.checksum!=next.checksum)throw std::runtime_error("Published map differs from its validated staging bytes");
            if(old)Drop(old->value);
            if(old && !DeleteFileW(FileApiPath(directory_+L"\\.map-replace.pending").c_str()))
                throw std::runtime_error("Map published but its replacement recovery record could not be removed");
            return actual;
        }catch(...){
            if(!published){
                bool restored=!movedOld;
                if(movedOld){try{Rename(old->value,destination);restored=true;}catch(...){}}
                if(restored){
                    if(stage){try{Drop(stage->value);}catch(...){}}
                    else DeleteFileW(FileApiPath(temporary).c_str());
                    if(movedOld)DeleteFileW(FileApiPath(directory_+L"\\.map-replace.pending").c_str());
                }
            }
            throw;
        }
    }
    void Delete(const UiMapMenuFile& expected){
        const auto path=Wide(expected.path);if(path!=Path(expected.name))throw std::invalid_argument("Map deletion target is not an owned catalog leaf");
        Handle file(CreateFileW(FileApiPath(path).c_str(),GENERIC_READ|DELETE,0,nullptr,OPEN_EXISTING,FILE_ATTRIBUTE_NORMAL|FILE_FLAG_OPEN_REPARSE_POINT,nullptr));
        Match(expected,Observe(file.value,path));Drop(file.value);
    }
private:
    // Keep public observations and namespace comparisons in canonical DOS
    // form. Only filesystem API arguments opt out of legacy MAX_PATH limits.
    static std::wstring FileApiPath(const std::wstring& canonical){return L"\\\\?\\"+canonical;}
    static BY_HANDLE_FILE_INFORMATION Ordinary(HANDLE file){
        BY_HANDLE_FILE_INFORMATION info{};
        if(!GetFileInformationByHandle(file,&info) || info.nNumberOfLinks!=1 ||
           info.dwFileAttributes&(FILE_ATTRIBUTE_DIRECTORY|FILE_ATTRIBUTE_REPARSE_POINT|FILE_ATTRIBUTE_READONLY))
            throw std::invalid_argument("Map file is not an exclusive ordinary writable leaf");
        return info;
    }
    void Pin(const std::wstring& path){
        std::unique_ptr<Handle> file(new Handle(CreateFileW(FileApiPath(path).c_str(),GENERIC_READ,FILE_SHARE_READ|FILE_SHARE_WRITE,nullptr,OPEN_EXISTING,
                                             FILE_FLAG_BACKUP_SEMANTICS|FILE_FLAG_OPEN_REPARSE_POINT,nullptr)));
        BY_HANDLE_FILE_INFORMATION info{};
        if(!GetFileInformationByHandle(file->value,&info) || !(info.dwFileAttributes&FILE_ATTRIBUTE_DIRECTORY) || info.dwFileAttributes&FILE_ATTRIBUTE_REPARSE_POINT)
            throw std::invalid_argument("Reparse point or non-directory in map catalog ancestry");
        pins_.emplace_back(std::move(file));
    }
    std::wstring Path(const std::string& name) const {return directory_+L"\\"+DecodeName(name)+L".Civ5Map";}
    static std::string Utf8(const std::wstring& value){
        const int count=WideCharToMultiByte(CP_UTF8,WC_ERR_INVALID_CHARS,value.data(),static_cast<int>(value.size()),nullptr,0,nullptr,nullptr);
        if(count<=0)throw std::invalid_argument("Invalid map UTF-16 path");
        std::string result(static_cast<std::size_t>(count),'\0');WideCharToMultiByte(CP_UTF8,WC_ERR_INVALID_CHARS,value.data(),static_cast<int>(value.size()),&result[0],count,nullptr,nullptr);return result;
    }
    static std::wstring Wide(const std::string& value){
        const int count=MultiByteToWideChar(CP_UTF8,MB_ERR_INVALID_CHARS,value.data(),static_cast<int>(value.size()),nullptr,0);
        if(count<=0)throw std::invalid_argument("Invalid map UTF-8 path");
        std::wstring result(static_cast<std::size_t>(count),L'\0');MultiByteToWideChar(CP_UTF8,MB_ERR_INVALID_CHARS,value.data(),static_cast<int>(value.size()),&result[0],count);return result;
    }
    UiMapMenuFile Read(const std::wstring& path) const {
        Handle file(CreateFileW(FileApiPath(path).c_str(),GENERIC_READ,FILE_SHARE_READ,nullptr,OPEN_EXISTING,FILE_ATTRIBUTE_NORMAL|FILE_FLAG_OPEN_REPARSE_POINT,nullptr));
        return Observe(file.value,path);
    }
    UiMapMenuFile Observe(HANDLE file,const std::wstring& path) const {
        const auto before=Ordinary(file);const auto size=(std::uint64_t(before.nFileSizeHigh)<<32)|before.nFileSizeLow;
        if(size<46 || size>64u*1024u*1024u)throw std::invalid_argument("Map file size is outside bounds");
        LARGE_INTEGER zero{};if(!SetFilePointerEx(file,zero,nullptr,FILE_BEGIN))throw std::runtime_error("Cannot seek private map");
        std::vector<unsigned char> bytes(static_cast<std::size_t>(size));DWORD count=0;
        if(!ReadFile(file,bytes.data(),static_cast<DWORD>(bytes.size()),&count,nullptr) || count!=bytes.size())throw std::runtime_error("Cannot read complete private map");
        const auto document=MenuMapDocument::Read(bytes);const auto after=Ordinary(file);
        if(before.dwVolumeSerialNumber!=after.dwVolumeSerialNumber || before.nFileIndexHigh!=after.nFileIndexHigh ||
           before.nFileIndexLow!=after.nFileIndexLow || before.nFileSizeHigh!=after.nFileSizeHigh || before.nFileSizeLow!=after.nFileSizeLow ||
           CompareFileTime(&before.ftLastWriteTime,&after.ftLastWriteTime)!=0)throw std::runtime_error("Map changed while cataloging");
        UiMapMenuFile result;result.path=Utf8(path);const auto leaf=path.substr(path.find_last_of(L'\\')+1);
        result.name=Utf8(leaf.substr(0,leaf.size()-8));result.worldType=document.worldType;result.width=document.width;result.height=document.height;
        result.bytes=size;result.identity={{before.dwVolumeSerialNumber,before.nFileIndexHigh,before.nFileIndexLow}};
        result.timeHigh=before.ftLastWriteTime.dwHighDateTime;result.timeLow=before.ftLastWriteTime.dwLowDateTime;
        result.checksum=Digest(bytes);
        FILETIME local{};SYSTEMTIME time{};
        if(!FileTimeToLocalFileTime(&before.ftLastWriteTime,&local) || !FileTimeToSystemTime(&local,&time))throw std::runtime_error("Cannot format private map timestamp");
        char stamp[32]{};std::snprintf(stamp,sizeof(stamp),"%04u-%02u-%02u %02u:%02u:%02u",time.wYear,time.wMonth,time.wDay,time.wHour,time.wMinute,time.wSecond);
        result.modificationTime=stamp;return result;
    }
    static void Match(const UiMapMenuFile& a,const UiMapMenuFile& b){
        if(a.path!=b.path || a.name!=b.name || a.bytes!=b.bytes || a.identity!=b.identity || a.checksum!=b.checksum ||
           a.timeHigh!=b.timeHigh || a.timeLow!=b.timeLow)throw std::invalid_argument("Selected map differs from its immutable catalog observation");
    }
    static std::array<unsigned char,32> Digest(const std::vector<unsigned char>& bytes){
        BCRYPT_ALG_HANDLE algorithm=nullptr;
        if(BCryptOpenAlgorithmProvider(&algorithm,BCRYPT_SHA256_ALGORITHM,nullptr,0)!=0)
            throw std::runtime_error("Cannot open map checksum provider");
        std::array<unsigned char,32> result{};
        const auto status=BCryptHash(algorithm,nullptr,0,const_cast<unsigned char*>(bytes.data()),
                                    static_cast<ULONG>(bytes.size()),result.data(),static_cast<ULONG>(result.size()));
        BCryptCloseAlgorithmProvider(algorithm,0);
        if(status!=0)throw std::runtime_error("Cannot compute map checksum");
        return result;
    }
    static void Rename(HANDLE file,const std::wstring& path){
        const auto native=FileApiPath(path);
        std::vector<unsigned char> bytes(sizeof(FILE_RENAME_INFO)+native.size()*sizeof(wchar_t));
        auto* info=reinterpret_cast<FILE_RENAME_INFO*>(bytes.data());info->ReplaceIfExists=FALSE;info->RootDirectory=nullptr;
        info->FileNameLength=static_cast<DWORD>(native.size()*sizeof(wchar_t));std::memcpy(info->FileName,native.data(),info->FileNameLength);
        if(!SetFileInformationByHandle(file,FileRenameInfo,info,static_cast<DWORD>(bytes.size())))throw std::runtime_error("Cannot publish private map without replacing an unobserved file");
    }
    static void Drop(HANDLE file){FILE_DISPOSITION_INFO value{};value.DeleteFile=TRUE;if(!SetFileInformationByHandle(file,FileDispositionInfo,&value,sizeof(value)))throw std::runtime_error("Cannot dispose owned map transaction leaf");}
    static std::wstring Token(){
        unsigned char random[16]{};if(BCryptGenRandom(nullptr,random,sizeof(random),BCRYPT_USE_SYSTEM_PREFERRED_RNG)!=0)throw std::runtime_error("Cannot allocate map transaction identity");
        std::wstring value;for(auto ch:random){value.push_back(L"0123456789abcdef"[ch>>4]);value.push_back(L"0123456789abcdef"[ch&15]);}return value;
    }
    static void WriteJournal(const std::wstring& path,const std::string& bytes){
        Handle file(CreateFileW(FileApiPath(path).c_str(),GENERIC_WRITE,0,nullptr,CREATE_NEW,FILE_ATTRIBUTE_NORMAL|FILE_FLAG_OPEN_REPARSE_POINT,nullptr));
        DWORD count=0;if(!WriteFile(file.value,bytes.data(),static_cast<DWORD>(bytes.size()),&count,nullptr) || count!=bytes.size() || !FlushFileBuffers(file.value))throw std::runtime_error("Cannot preserve map replacement recovery record");
    }
    std::wstring directory_;std::vector<std::unique_ptr<Handle>> pins_;std::unique_ptr<Handle> lock_;
};
}
