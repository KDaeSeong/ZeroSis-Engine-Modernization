#pragma once
#include "SdkHostIncludes.h"
#include <bcrypt.h>
#include <array>
#include <set>
#include <sstream>
#pragma comment(lib,"bcrypt.lib")

namespace ZeroSisHost {
#if defined(ZEROSIS_SHARED_LUA_RUNTIME)
constexpr const char* HostBundleVersion="ZEROSIS_HOST_BUNDLE_V4";
constexpr unsigned HostBundleFileCount=10;
#else
constexpr const char* HostBundleVersion="ZEROSIS_HOST_BUNDLE_V3";
constexpr unsigned HostBundleFileCount=9;
#endif
constexpr unsigned HostTerrainFileCount=
#if defined(ZEROSIS_WORLD_TERRAIN)
    1;
#else
    0;
#endif
inline std::string Utf8(const std::wstring& text) {
    if(text.size()>static_cast<std::size_t>(INT_MAX))throw std::length_error("Path is too long");
    const int size=WideCharToMultiByte(CP_UTF8,WC_ERR_INVALID_CHARS,text.data(),static_cast<int>(text.size()),nullptr,0,nullptr,nullptr);
    if(size==0 && !text.empty())throw std::runtime_error("Invalid Unicode path");
    std::string out(static_cast<std::size_t>(size),'\0');
    if(size && WideCharToMultiByte(CP_UTF8,WC_ERR_INVALID_CHARS,text.data(),static_cast<int>(text.size()),&out[0],size,nullptr,nullptr)!=size)
        throw std::runtime_error("Path conversion failed");
    return out;
}
inline std::wstring ExecutableDirectory() {
    std::vector<wchar_t> buffer(32768);
    const DWORD count=GetModuleFileNameW(nullptr,buffer.data(),static_cast<DWORD>(buffer.size()));
    if(!count || count>=buffer.size())throw std::runtime_error("Cannot locate the native host executable");
    std::wstring path(buffer.data(),count);const auto split=path.find_last_of(L"\\/");
    if(split==std::wstring::npos)throw std::runtime_error("Host executable path is not absolute");
    return path.substr(0,split);
}
class ReadFileHandle {
public:
    explicit ReadFileHandle(const std::wstring& path) {
        handle_=CreateFileW(path.c_str(),GENERIC_READ,FILE_SHARE_READ,nullptr,OPEN_EXISTING,FILE_ATTRIBUTE_NORMAL,nullptr);
        if(handle_==INVALID_HANDLE_VALUE)throw std::runtime_error("Cannot open bundle file: "+Utf8(path));
    }
    ~ReadFileHandle(){if(handle_!=INVALID_HANDLE_VALUE)CloseHandle(handle_);}
    ReadFileHandle(const ReadFileHandle&)=delete;
    ReadFileHandle& operator=(const ReadFileHandle&)=delete;
    HANDLE Get() const noexcept{return handle_;}
    void Seek(LONGLONG at) {
        LARGE_INTEGER offset;offset.QuadPart=at;
        if(!SetFilePointerEx(handle_,offset,nullptr,FILE_BEGIN))throw std::runtime_error("Bundle file seek failed");
    }
    DWORD Read(void* data,DWORD size){DWORD n=0;if(!ReadFile(handle_,data,size,&n,nullptr))throw std::runtime_error("Bundle file read failed");return n;}
private:HANDLE handle_=INVALID_HANDLE_VALUE;
};
inline std::string FileSha256(ReadFileHandle& file) {
    struct Hash {
        BCRYPT_ALG_HANDLE algorithm=nullptr;BCRYPT_HASH_HANDLE hash=nullptr;
        ~Hash(){if(hash)BCryptDestroyHash(hash);if(algorithm)BCryptCloseAlgorithmProvider(algorithm,0);}
    } h;
    if(BCryptOpenAlgorithmProvider(&h.algorithm,BCRYPT_SHA256_ALGORITHM,nullptr,0)!=0 || BCryptCreateHash(h.algorithm,&h.hash,nullptr,0,nullptr,0,0)!=0)
        throw std::runtime_error("SHA-256 initialization failed");
    file.Seek(0);std::array<unsigned char,65536> buffer{};
    for(;;){const DWORD n=file.Read(buffer.data(),static_cast<DWORD>(buffer.size()));if(!n)break;
        if(BCryptHashData(h.hash,buffer.data(),n,0)!=0)throw std::runtime_error("SHA-256 input failed");}
    std::array<unsigned char,32> hash{};
    if(BCryptFinishHash(h.hash,hash.data(),static_cast<ULONG>(hash.size()),0)!=0)throw std::runtime_error("SHA-256 completion failed");
    const char* hex="0123456789abcdef";std::string result;
    for(auto byte:hash){result.push_back(hex[byte>>4]);result.push_back(hex[byte&15]);}
    return result;
}
inline void VerifyAmd64(ReadFileHandle& file,bool dll) {
    unsigned char dos[64]{};file.Seek(0);
    if(file.Read(dos,sizeof(dos))!=sizeof(dos) || dos[0]!='M' || dos[1]!='Z')throw std::runtime_error("Bundle module has no DOS header");
    const DWORD offset=static_cast<DWORD>(dos[60])|(static_cast<DWORD>(dos[61])<<8)|(static_cast<DWORD>(dos[62])<<16)|(static_cast<DWORD>(dos[63])<<24);
    LARGE_INTEGER size;
    if(!GetFileSizeEx(file.Get(),&size) || size.QuadPart<26 || offset>static_cast<ULONGLONG>(size.QuadPart-26))throw std::runtime_error("Invalid PE header offset");
    unsigned char pe[26]{};file.Seek(offset);
    if(file.Read(pe,sizeof(pe))!=sizeof(pe) || std::memcmp(pe,"PE\0\0",4)!=0 || pe[4]!=0x64 || pe[5]!=0x86 || pe[24]!=0x0b || pe[25]!=0x02)
        throw std::runtime_error("Bundle module is not AMD64 PE32+");
    if(((pe[23]&0x20)!=0)!=dll)throw std::runtime_error("Bundle module EXE/DLL kind differs");
}
// PE32 IL-only assemblies can execute in the x64 CLR. A PE32 native image or
// an assembly with 32BITREQUIRED must never pass this distinct dependency gate.
inline void VerifyAnyCpuManaged(ReadFileHandle& file) {
    LARGE_INTEGER size{};IMAGE_DOS_HEADER dos{};file.Seek(0);
    if(!GetFileSizeEx(file.Get(),&size) || file.Read(&dos,sizeof(dos))!=sizeof(dos) ||
       dos.e_magic!=IMAGE_DOS_SIGNATURE || dos.e_lfanew<0 ||
       static_cast<LONGLONG>(dos.e_lfanew)+static_cast<LONGLONG>(sizeof(IMAGE_NT_HEADERS32))>size.QuadPart)
        throw std::runtime_error("Managed assembly has an invalid DOS header");
    IMAGE_NT_HEADERS32 nt{};file.Seek(dos.e_lfanew);
    if(file.Read(&nt,sizeof(nt))!=sizeof(nt) || nt.Signature!=IMAGE_NT_SIGNATURE ||
       nt.FileHeader.Machine!=IMAGE_FILE_MACHINE_I386 || !(nt.FileHeader.Characteristics&IMAGE_FILE_DLL) ||
       nt.OptionalHeader.Magic!=IMAGE_NT_OPTIONAL_HDR32_MAGIC || nt.FileHeader.SizeOfOptionalHeader!=sizeof(IMAGE_OPTIONAL_HEADER32) ||
       nt.FileHeader.NumberOfSections==0 || nt.FileHeader.NumberOfSections>96 ||
       nt.OptionalHeader.NumberOfRvaAndSizes<=IMAGE_DIRECTORY_ENTRY_COM_DESCRIPTOR)
        throw std::runtime_error("Managed dependency is not a bounded PE32 assembly");
    const auto clr=nt.OptionalHeader.DataDirectory[IMAGE_DIRECTORY_ENTRY_COM_DESCRIPTOR];
    if(clr.Size<20 || !clr.VirtualAddress)throw std::runtime_error("Managed dependency lacks a CLR header");
    for(unsigned i=0;i<nt.FileHeader.NumberOfSections;++i){
        IMAGE_SECTION_HEADER section{};
        file.Seek(static_cast<LONGLONG>(dos.e_lfanew)+sizeof(nt)+static_cast<LONGLONG>(i)*sizeof(section));
        if(file.Read(&section,sizeof(section))!=sizeof(section))throw std::runtime_error("Truncated managed PE section table");
        if(clr.VirtualAddress<section.VirtualAddress)continue;
        const auto offset=static_cast<ULONGLONG>(clr.VirtualAddress)-section.VirtualAddress;
        if(offset+20>section.SizeOfRawData)continue;
        if(static_cast<ULONGLONG>(section.PointerToRawData)+offset+20>static_cast<ULONGLONG>(size.QuadPart))break;
        std::array<DWORD,5> header{};file.Seek(static_cast<LONGLONG>(section.PointerToRawData)+static_cast<LONGLONG>(offset));
        if(file.Read(header.data(),sizeof(header))!=sizeof(header) || header[0]<20 ||
           !(header[4]&1u) || (header[4]&(2u|0x10u|0x20000u)))
            throw std::runtime_error("Managed dependency is not IL-only AnyCPU");
        return;
    }
    throw std::runtime_error("Managed dependency CLR header is outside its file");
}
class VerifiedBundle {
public:
    explicit VerifiedBundle(std::wstring directory):directory_(std::move(directory)) {
        ReadFileHandle manifest(directory_+L"\\bundle.manifest");
        std::array<char,16385> text{};const DWORD count=manifest.Read(text.data(),static_cast<DWORD>(text.size()));
        if(count==text.size())throw std::runtime_error("Bundle manifest is too large");
        std::istringstream input(std::string(text.data(),count));std::string line;
        auto readLine=[&](){if(!std::getline(input,line))return false;if(!line.empty()&&line.back()=='\r')line.pop_back();return true;};
        if(!readLine() || line!=HostBundleVersion)throw std::runtime_error("Invalid bundle manifest version");
        std::set<std::string> required={"ZeroSisHost_x64.exe","CvGameCoreDLL_Expansion2_x64.dll","ZeroSisDatabase_x64.dll","ZeroSisLocalization_x64.dll","rules.db","localization.db","icudt44l.dat","audio-catalog.bin","script-catalog.bin"};
#if defined(ZEROSIS_SHARED_LUA_RUNTIME)
        required.insert("ZeroSisLua51_x64.dll");
#endif
        std::set<std::string> optional;
#if defined(ZEROSIS_WORLD_TERRAIN)
        required.insert("terrain-assets.bin");
        optional.insert("unit-assets.bin");
        const std::set<std::string> animationFiles={"ZeroSisGrannyAnimationBridge.dll","Firaxis.Framework.dll",
            "Firaxis.Framework.Granny.dll","Firaxis.Framework.FirePlace.dll","Firaxis.Framework.Granny.Implx64.dll",
            "ZeroSisHost_x64.exe.config","unitmodels_stringdatabase.gsd","Warrior.gr2","Warrior_V2.gr2","Warrior_V4.gr2","Warrior_IdleA.gr2"};
        optional.insert(animationFiles.begin(),animationFiles.end());
#endif
        while(readLine()) {
            const auto separator=line.find('|');if(separator==std::string::npos)throw std::runtime_error("Invalid bundle manifest entry");
            const std::string name=line.substr(0,separator),hash=line.substr(separator+1);
            const bool allowed=required.erase(name)==1 || optional.erase(name)==1;
            if(!allowed || hash.size()!=64 || hash.find_first_not_of("0123456789abcdef")!=std::string::npos)
                throw std::runtime_error("Unexpected, duplicate or invalid bundle manifest entry");
            const std::wstring wide(name.begin(),name.end());
            std::unique_ptr<ReadFileHandle> file(new ReadFileHandle(directory_+L"\\"+wide));
            if(FileSha256(*file)!=hash)throw std::runtime_error("Bundle hash differs: "+name);
            if(name=="Firaxis.Framework.dll" || name=="Firaxis.Framework.Granny.dll" || name=="Firaxis.Framework.FirePlace.dll")VerifyAnyCpuManaged(*file);
            else if(name.size()>4 && name.substr(name.size()-4)==".dll")VerifyAmd64(*file,true);
            if(name=="ZeroSisHost_x64.exe")VerifyAmd64(*file,false);
            if(name=="unit-assets.bin"){
                unitAssetsPath_=directory_+L"\\"+wide;
                std::array<unsigned char,12> header{};file->Seek(0);
                if(file->Read(header.data(),static_cast<DWORD>(header.size()))!=header.size())throw std::runtime_error("Truncated unit package header");
                const bool v1=std::memcmp(header.data(),"ZSUNIT01\1\0\0\0",12)==0;
                unitAnimation_=std::memcmp(header.data(),"ZSUNIT02\2\0\0\0",12)==0;
                if(!v1&&!unitAnimation_)throw std::runtime_error("Unsupported unit package version");
            }
            pins_.push_back(std::move(file));
        }
        if(!required.empty())throw std::runtime_error("Bundle manifest is incomplete");
#if defined(ZEROSIS_WORLD_TERRAIN)
        for(const auto& name:animationFiles)if((optional.count(name)==0)!=unitAnimation_)
            throw std::runtime_error("Animated unit package and runtime dependency closure disagree");
#endif
    }
    const std::wstring& Directory() const noexcept{return directory_;}
    const std::wstring& UnitAssetsPath() const noexcept{return unitAssetsPath_;}
    bool UnitAnimation() const noexcept{return unitAnimation_;}
    unsigned FileCount() const noexcept{return static_cast<unsigned>(pins_.size());}
    // Pins deny modification/deletion until module shutdown and DB close finish.
private:
    std::wstring directory_;
    std::wstring unitAssetsPath_;
    bool unitAnimation_=false;
    std::vector<std::unique_ptr<ReadFileHandle>> pins_;
};
inline std::wstring NewSessionDirectory(const VerifiedBundle& bundle) {
    const std::wstring root=bundle.Directory()+L"\\sessions";
    if(!CreateDirectoryW(root.c_str(),nullptr) && GetLastError()!=ERROR_ALREADY_EXISTS)throw std::runtime_error("Cannot create native session root");
    const DWORD attributes=GetFileAttributesW(root.c_str());
    if(attributes==INVALID_FILE_ATTRIBUTES || !(attributes&FILE_ATTRIBUTE_DIRECTORY) || (attributes&FILE_ATTRIBUTE_REPARSE_POINT))throw std::runtime_error("Session root is not an ordinary directory");
    const wchar_t* hex=L"0123456789abcdef";
    for(int attempt=0;attempt<8;++attempt) {
        unsigned char random[16];if(BCryptGenRandom(nullptr,random,sizeof(random),BCRYPT_USE_SYSTEM_PREFERRED_RNG)!=0)throw std::runtime_error("Cannot create session identifier");
        std::wstring id;for(auto byte:random){id.push_back(hex[byte>>4]);id.push_back(hex[byte&15]);}
        const auto directory=root+L"\\"+id;
        if(CreateDirectoryW(directory.c_str(),nullptr))return directory;
        if(GetLastError()!=ERROR_ALREADY_EXISTS)throw std::runtime_error("Cannot create native session directory");
    }
    throw std::runtime_error("Native session identifier collision");
}
}
