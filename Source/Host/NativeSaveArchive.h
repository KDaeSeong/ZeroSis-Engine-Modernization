#pragma once
#include "HostFiles.h"
#include "NativeSaveEnvelope.h"
#include <algorithm>
#include <cstdint>
#include <limits>

namespace ZeroSisHost {
class NativeSaveTransaction final {
public:
    explicit NativeSaveTransaction(const std::wstring& path):destination_(path){
        static volatile LONG sequence=0;
        for(unsigned attempt=0;attempt<128;++attempt){
            temporary_=path+L".tmp-"+std::to_wstring(GetCurrentProcessId())+L"-"+
                std::to_wstring(static_cast<unsigned long>(InterlockedIncrement(&sequence)));
            file_=CreateFileW(temporary_.c_str(),GENERIC_WRITE,0,nullptr,CREATE_NEW,FILE_ATTRIBUTE_NORMAL,nullptr);
            if(file_!=INVALID_HANDLE_VALUE){owned_=true;return;}
            const DWORD error=GetLastError();
            if(error!=ERROR_FILE_EXISTS && error!=ERROR_ALREADY_EXISTS)
                throw std::runtime_error("Cannot create native save transaction");
        }
        throw std::runtime_error("Native save temporary name collision");
    }
    ~NativeSaveTransaction(){
        if(file_!=INVALID_HANDLE_VALUE)CloseHandle(file_);
        if(owned_)DeleteFileW(temporary_.c_str());
    }
    NativeSaveTransaction(const NativeSaveTransaction&)=delete;
    NativeSaveTransaction& operator=(const NativeSaveTransaction&)=delete;
    HANDLE Get() const noexcept {return file_;}
    void Commit(){
        if(!FlushFileBuffers(file_))throw std::runtime_error("Cannot flush native save transaction");
        if(!CloseHandle(file_))throw std::runtime_error("Cannot close native save transaction");
        file_=INVALID_HANDLE_VALUE;
        if(!MoveFileExW(temporary_.c_str(),destination_.c_str(),MOVEFILE_REPLACE_EXISTING|MOVEFILE_WRITE_THROUGH))
            throw std::runtime_error("Cannot commit native save transaction");
        owned_=false;
    }
private:
    std::wstring destination_,temporary_;
    HANDLE file_=INVALID_HANDLE_VALUE;
    bool owned_=false;
};

static_assert(static_cast<unsigned>(MAX_TEAMS)==NativeSaveEnvelope::TeamSlots &&
    static_cast<unsigned>(MAX_PLAYERS)==NativeSaveEnvelope::PlayerSlots,
    "SDK slot counts must match the native V1 envelope");

// Platform digest and atomic persistence retain the existing archive API.
struct NativeSaveArchive : NativeSaveEnvelope {
    static std::array<unsigned char,32> Digest(const unsigned char* bytes,std::size_t size){
        struct Hash {
            BCRYPT_ALG_HANDLE algorithm=nullptr;BCRYPT_HASH_HANDLE value=nullptr;
            ~Hash(){if(value)BCryptDestroyHash(value);if(algorithm)BCryptCloseAlgorithmProvider(algorithm,0);}
        } hash;
        if(BCryptOpenAlgorithmProvider(&hash.algorithm,BCRYPT_SHA256_ALGORITHM,nullptr,0)!=0 ||
           BCryptCreateHash(hash.algorithm,&hash.value,nullptr,0,nullptr,0,0)!=0)
            throw std::runtime_error("Save digest initialization failed");
        while(size){
            const auto count=static_cast<ULONG>(std::min<std::size_t>(size,1024*1024));
            if(BCryptHashData(hash.value,const_cast<unsigned char*>(bytes),count,0)!=0)
                throw std::runtime_error("Save digest input failed");
            bytes+=count;size-=count;
        }
        std::array<unsigned char,32> result{};
        if(BCryptFinishHash(hash.value,result.data(),static_cast<ULONG>(result.size()),0)!=0)
            throw std::runtime_error("Save digest completion failed");
        return result;
    }
    std::vector<unsigned char> Encode() const {
        return NativeSaveEnvelope::Encode(&NativeSaveArchive::Digest);
    }
    static NativeSaveArchive Decode(const std::vector<unsigned char>& bytes){
        NativeSaveArchive result;
        static_cast<NativeSaveEnvelope&>(result)=NativeSaveEnvelope::Decode(bytes,&NativeSaveArchive::Digest);
        return result;
    }
    static std::vector<unsigned char> Read(const std::wstring& path){
        ReadFileHandle file(path);LARGE_INTEGER size;
        if(!GetFileSizeEx(file.Get(),&size) || size.QuadPart<80 ||
           static_cast<unsigned long long>(size.QuadPart)>std::numeric_limits<std::size_t>::max())
            throw std::runtime_error("Invalid native save file size");
        std::vector<unsigned char> bytes(static_cast<std::size_t>(size.QuadPart));std::size_t at=0;
        while(at<bytes.size()){
            const auto count=static_cast<DWORD>(std::min<std::size_t>(bytes.size()-at,1024*1024));
            const DWORD read=file.Read(bytes.data()+at,count);
            if(!read)throw std::runtime_error("Native save file was truncated");
            at+=read;
        }
        return bytes;
    }
    static void WriteAtomic(const std::wstring& path,const std::vector<unsigned char>& bytes){
        Decode(bytes); // Do not publish an incomplete or malformed envelope.
        NativeSaveTransaction file(path);
        std::size_t at=0;
        while(at<bytes.size()){
            const auto count=static_cast<DWORD>(std::min<std::size_t>(bytes.size()-at,1024*1024));DWORD written=0;
            if(!WriteFile(file.Get(),bytes.data()+at,count,&written,nullptr) || !written || written>count)
                throw std::runtime_error("Native save file write failed");
            at+=written;
        }
        file.Commit();
        if(Read(path)!=bytes)throw std::runtime_error("Persisted native save bytes differ");
    }
};
}
