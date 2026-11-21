#pragma once

#include "MenuOptionsContract.h"
#include <windows.h>
#include <cstdint>
#include <vector>

namespace ZeroSisHost {

// A private preference file in an explicitly owned, already existing runtime
// directory. Never pass a retail game/configuration/MODS/save directory here.
// One exclusive process lock serializes read/replace and rejects hardlinks or
// reparse points. Existing unknown/corrupt data is never silently overwritten.
class MenuOptionsStore final {
public:
    explicit MenuOptionsStore(const std::wstring& ownedDirectory):directory_(ownedDirectory) {
        if(directory_.size()<3 || directory_[1]!=L':' || directory_[2]!=L'\\' ||
           directory_.find(L'/')!=std::wstring::npos || directory_.find(L"\\..")!=std::wstring::npos ||
           directory_.find(L"\\.\\")!=std::wstring::npos || directory_.back()==L'\\')
            throw std::invalid_argument("Menu options store needs a canonical absolute owned directory");
        CheckDirectories();
        path_=directory_+L"\\menu-options.zssettings";
        pending_=directory_+L"\\menu-options.pending";
        const auto lockPath=directory_+L"\\menu-options.lock";
        lock_=CreateFileW(lockPath.c_str(),GENERIC_READ|GENERIC_WRITE,0,nullptr,OPEN_ALWAYS,
                         FILE_ATTRIBUTE_NORMAL|FILE_FLAG_OPEN_REPARSE_POINT,nullptr);
        if(lock_==INVALID_HANDLE_VALUE)throw std::runtime_error("Private menu options are locked by another session");
        try {RequireRegular(lock_);Read();}catch(...){CloseHandle(lock_);lock_=INVALID_HANDLE_VALUE;throw;}
    }
    ~MenuOptionsStore(){if(lock_!=INVALID_HANDLE_VALUE)CloseHandle(lock_);}
    MenuOptionsStore(const MenuOptionsStore&)=delete;
    MenuOptionsStore& operator=(const MenuOptionsStore&)=delete;
    const std::wstring& Path() const noexcept {return path_;}
    // 0 means absent. Read never migrates bytes; only WriteAtomic publishes V3.
    int SchemaVersion() const noexcept {return schemaVersion_;}
    MenuOptionsValues Read() {
        CheckDirectories();bool exists=false;const auto bytes=ReadBytes(path_,&exists);
        MenuOptionsValues value=exists?MenuOptionsValues::Decode(bytes):MenuOptionsValues{};
        observed_=bytes;existed_=exists;schemaVersion_=exists?MenuOptionsValues::SchemaVersion(bytes):0;return value;
    }
    void WriteAtomic(const MenuOptionsValues& value) {
        const auto bytes=MenuOptionsValues::Encode(value);const int publishedVersion=MenuOptionsValues::SchemaVersion(bytes);auto published=bytes;CheckDirectories();
        bool exists=false;
        if(ReadBytes(path_,&exists)!=observed_ || exists!=existed_)
            throw std::runtime_error("Private menu options changed outside their owned transaction");
        // CREATE_NEW refuses to reuse another task's pending data.
        HANDLE file=CreateFileW(pending_.c_str(),GENERIC_WRITE,0,nullptr,CREATE_NEW,
                                FILE_ATTRIBUTE_NORMAL|FILE_FLAG_OPEN_REPARSE_POINT,nullptr);
        if(file==INVALID_HANDLE_VALUE)throw std::runtime_error("Cannot allocate private menu option transaction file");
        bool created=true;
        try {
            RequireRegular(file);DWORD written=0;
            if(!WriteFile(file,bytes.data(),static_cast<DWORD>(bytes.size()),&written,nullptr) ||
               written!=bytes.size() || !FlushFileBuffers(file))
                throw std::runtime_error("Cannot flush private menu options");
            CloseHandle(file);file=INVALID_HANDLE_VALUE;
            CheckDirectories();bool currentExists=false;
            if(ReadBytes(path_,&currentExists)!=observed_ || currentExists!=existed_)
                throw std::runtime_error("Private menu options changed before atomic commit");
            if(!MoveFileExW(pending_.c_str(),path_.c_str(),MOVEFILE_REPLACE_EXISTING|MOVEFILE_WRITE_THROUGH))
                throw std::runtime_error("Cannot atomically commit private menu options");
            created=false;
            // No fallible work after successful publication: an exception here
            // would falsely promise callers that old persisted bytes survived.
            observed_.swap(published);existed_=true;schemaVersion_=publishedVersion;
        }catch(...) {
            if(file!=INVALID_HANDLE_VALUE)CloseHandle(file);
            if(created)DeleteFileW(pending_.c_str());
            throw;
        }
    }
private:
    static void RequireRegular(HANDLE file) {
        BY_HANDLE_FILE_INFORMATION info{};
        if(GetFileType(file)!=FILE_TYPE_DISK || !GetFileInformationByHandle(file,&info) ||
           (info.dwFileAttributes&(FILE_ATTRIBUTE_REPARSE_POINT|FILE_ATTRIBUTE_DIRECTORY)) ||
           info.nNumberOfLinks!=1)
            throw std::runtime_error("Private menu options reject reparse points, directories and hardlinks");
    }
    void CheckDirectories() const {
        for(std::size_t end=3;;){
            const auto next=directory_.find(L'\\',end);
            const auto current=directory_.substr(0,next==std::wstring::npos?directory_.size():next);
            const auto attrs=GetFileAttributesW(current.c_str());
            if(attrs==INVALID_FILE_ATTRIBUTES || !(attrs&FILE_ATTRIBUTE_DIRECTORY) || attrs&FILE_ATTRIBUTE_REPARSE_POINT)
                throw std::runtime_error("Private menu option directory is missing or a reparse point");
            if(next==std::wstring::npos)break;
            end=next+1;
        }
    }
    static std::string ReadBytes(const std::wstring& path,bool* exists) {
        HANDLE file=CreateFileW(path.c_str(),GENERIC_READ,FILE_SHARE_READ,nullptr,OPEN_EXISTING,
                                FILE_ATTRIBUTE_NORMAL|FILE_FLAG_OPEN_REPARSE_POINT,nullptr);
        if(file==INVALID_HANDLE_VALUE){
            if(GetLastError()!=ERROR_FILE_NOT_FOUND)throw std::runtime_error("Cannot read private menu options");
            *exists=false;return {};
        }
        try {
            RequireRegular(file);LARGE_INTEGER size{};
            if(!GetFileSizeEx(file,&size) || size.QuadPart<1 || size.QuadPart>512)
                throw std::runtime_error("Private menu option file size is invalid");
            std::string bytes(static_cast<std::size_t>(size.QuadPart),'\0');DWORD count=0;
            if(!ReadFile(file,&bytes[0],static_cast<DWORD>(bytes.size()),&count,nullptr) || count!=bytes.size())
                throw std::runtime_error("Cannot completely read private menu options");
            CloseHandle(file);*exists=true;return bytes;
        }catch(...){CloseHandle(file);throw;}
    }
    std::wstring directory_,path_,pending_;
    HANDLE lock_=INVALID_HANDLE_VALUE;
    std::string observed_;
    bool existed_=false;
    int schemaVersion_=0;
};
}
