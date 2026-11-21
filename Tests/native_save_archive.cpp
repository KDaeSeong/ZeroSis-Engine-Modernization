#include "NativeSaveArchive.h"
#include <cstdio>
#include <stdexcept>
#include <string>
#include <vector>

using ZeroSisHost::NativeSaveArchive;
using ZeroSisHost::NativeSaveSection;

namespace {
int checks=0;

void Require(bool condition,const char* message){
    ++checks;
    if(!condition)throw std::runtime_error(message);
}

template<typename Exception,typename Function>
void RequireThrows(Function&& function,const char* message){
    bool caught=false;
    try{function();}
    catch(const Exception&){caught=true;}
    Require(caught,message);
}

NativeSaveArchive MakeArchive(unsigned seed){
    NativeSaveArchive archive;
    archive.flags=3;
    archive.turn=123+static_cast<int>(seed);
    archive.elapsed=234+static_cast<int>(seed);
    archive.activePlayer=static_cast<int>(seed%MAX_PLAYERS);
    for(unsigned i=0;i<NativeSaveArchive::SectionCount();++i){
        NativeSaveSection section;
        if(i<5){section.kind=i+1;section.index=0;}
        else if(i<5+MAX_TEAMS){section.kind=NativeSaveArchive::Team;section.index=i-5;}
        else{section.kind=NativeSaveArchive::Player;section.index=i-5-MAX_TEAMS;}
        section.bytes={0x00,0x80,0xFF,static_cast<unsigned char>(seed),static_cast<unsigned char>(i),0x00};
        archive.sections.push_back(section);
    }
    return archive;
}

void Put32(std::vector<unsigned char>& bytes,std::size_t offset,unsigned value){
    Require(offset+4<=bytes.size(),"Test field offset is outside byte vector");
    for(unsigned shift=0;shift<32;shift+=8)bytes[offset+shift/8]=static_cast<unsigned char>(value>>shift);
}

unsigned Get32(const std::vector<unsigned char>& bytes,std::size_t offset){
    Require(offset+4<=bytes.size(),"Test field offset is outside byte vector");
    return static_cast<unsigned>(bytes[offset])|(static_cast<unsigned>(bytes[offset+1])<<8)|
        (static_cast<unsigned>(bytes[offset+2])<<16)|(static_cast<unsigned>(bytes[offset+3])<<24);
}

void Reseal(std::vector<unsigned char>& bytes){
    Require(bytes.size()>=32,"Cannot seal a short test vector");
    const auto digest=NativeSaveArchive::Digest(bytes.data(),bytes.size()-32);
    std::copy(digest.begin(),digest.end(),bytes.end()-32);
}

std::vector<std::size_t> SectionOffsets(const std::vector<unsigned char>& bytes){
    std::vector<std::size_t> offsets;
    std::size_t at=48;
    for(unsigned i=0;i<NativeSaveArchive::SectionCount();++i){
        offsets.push_back(at);
        const unsigned size=Get32(bytes,at+8);
        at+=12+size;
    }
    Require(at==bytes.size()-32,"Test fixture section offsets differ");
    return offsets;
}

void RequireDecodeRejects(const std::vector<unsigned char>& bytes,const char* message){
    RequireThrows<std::invalid_argument>([&]{NativeSaveArchive::Decode(bytes);},message);
}

unsigned CountTemporaryFiles(const std::wstring& destination){
    const WIN32_FIND_DATAW patternData{};
    (void)patternData;
    const std::wstring pattern=destination+L".tmp-*";
    WIN32_FIND_DATAW data{};
    HANDLE search=FindFirstFileW(pattern.c_str(),&data);
    if(search==INVALID_HANDLE_VALUE){
        Require(GetLastError()==ERROR_FILE_NOT_FOUND,"Could not enumerate transaction siblings");
        return 0;
    }
    unsigned count=0;
    do{if(!(data.dwFileAttributes&FILE_ATTRIBUTE_DIRECTORY))++count;}
    while(FindNextFileW(search,&data));
    const DWORD error=GetLastError();
    FindClose(search);
    Require(error==ERROR_NO_MORE_FILES,"Temporary sibling enumeration failed");
    return count;
}

std::wstring ToWide(const char* value){
    const int count=MultiByteToWideChar(CP_ACP,0,value,-1,nullptr,0);
    if(count<=0)throw std::runtime_error("Cannot decode test path");
    std::wstring result(static_cast<std::size_t>(count),L'\0');
    if(MultiByteToWideChar(CP_ACP,0,value,-1,&result[0],count)!=count)
        throw std::runtime_error("Cannot decode test path");
    result.pop_back();
    return result;
}

void TestRoundTripAndMalformedArchives(){
    const auto original=MakeArchive(17);
    const auto encoded=original.Encode();
    const auto decoded=NativeSaveArchive::Decode(encoded);
    Require(decoded.flags==original.flags && decoded.turn==original.turn &&
        decoded.elapsed==original.elapsed && decoded.activePlayer==original.activePlayer,
        "Archive metadata roundtrip differs");
    Require(decoded.sections.size()==NativeSaveArchive::SectionCount(),"Archive section count differs");
    for(unsigned i=0;i<NativeSaveArchive::SectionCount();++i){
        const auto& before=original.sections[i];
        const auto& after=decoded.sections[i];
        Require(before.kind==after.kind && before.index==after.index && before.bytes==after.bytes,
            "Section or slot roundtrip differs");
    }
    bool sawHigh=false,sawNul=false;
    for(const auto& section:decoded.sections){
        for(unsigned char byte:section.bytes){if(byte>=0x80)sawHigh=true;if(byte==0)sawNul=true;}
    }
    Require(sawHigh && sawNul,"High bytes or embedded NUL were not preserved");

    auto checksum=encoded;
    checksum[60]^=0x40;
    RequireDecodeRejects(checksum,"Whole-archive checksum mutation was accepted");

    const auto offsets=SectionOffsets(encoded);
    std::vector<std::pair<std::string,std::vector<unsigned char>>> malformed;
    auto row=[&](const char* name){malformed.push_back(std::make_pair(std::string(name),encoded));return &malformed.back().second;};
    Put32(*row("unknown_version"),16,2);Reseal(malformed.back().second);
    Put32(*row("invalid_flags"),20,4);Reseal(malformed.back().second);
    Put32(*row("invalid_turn"),24,0x80000000u);Reseal(malformed.back().second);
    Put32(*row("invalid_elapsed"),28,0xFFFFFFFFu);Reseal(malformed.back().second);
    Put32(*row("invalid_active_player"),32,MAX_PLAYERS);Reseal(malformed.back().second);
    Put32(*row("missing_section"),44,NativeSaveArchive::SectionCount()-1);Reseal(malformed.back().second);
    Put32(*row("unknown_kind"),offsets[0],0xFFFFFFFFu);Reseal(malformed.back().second);
    Put32(*row("invalid_index"),offsets[0]+4,1);Reseal(malformed.back().second);
    auto* duplicate=row("duplicate_section");
    Put32(*duplicate,offsets[1],Get32(encoded,offsets[0]));
    Put32(*duplicate,offsets[1]+4,Get32(encoded,offsets[0]+4));
    Reseal(malformed.back().second);
    Put32(*row("zero_size"),offsets[0]+8,0);Reseal(malformed.back().second);
    Put32(*row("overflow_size"),offsets[0]+8,0xFFFFFFFFu);Reseal(malformed.back().second);

    auto truncated=encoded;
    truncated.erase(truncated.end()-33);
    Reseal(truncated);
    malformed.push_back(std::make_pair(std::string("truncated_payload"),std::move(truncated)));
    auto trailing=encoded;
    trailing.insert(trailing.end()-32,0xA5);
    Reseal(trailing);
    malformed.push_back(std::make_pair(std::string("trailing_data"),std::move(trailing)));
    for(const auto& item:malformed)RequireDecodeRejects(item.second,item.first.c_str());
    Require(malformed.size()==13,"Malformed archive case inventory differs");
}

void TestAtomicFileTransactions(const std::wstring& directory){
    const std::wstring destination=directory+L"\\save.bin";
    const auto first=MakeArchive(31).Encode();
    const auto second=MakeArchive(47).Encode();
    ZeroSisHost::NativeSaveArchive::WriteAtomic(destination,first);
    Require(NativeSaveArchive::Read(destination)==first,"Atomic initial readback differs");
    ZeroSisHost::NativeSaveArchive::WriteAtomic(destination,second);
    Require(NativeSaveArchive::Read(destination)==second,"Atomic replacement readback differs");
    Require(CountTemporaryFiles(destination)==0,"Successful commit left a temporary file");

    {
        ZeroSisHost::ReadFileHandle destinationLock(destination);
        RequireThrows<std::runtime_error>([&]{NativeSaveArchive::WriteAtomic(destination,first);},
            "Commit unexpectedly replaced a destination held without delete sharing");
        Require(NativeSaveArchive::Read(destination)==second,"Failed commit changed the old destination");
        Require(CountTemporaryFiles(destination)==0,"Failed commit did not remove its owned temporary");
    }

    {
        ZeroSisHost::NativeSaveTransaction interrupted(destination);
        const unsigned char abandoned[4]={0x00,0x80,0xFF,0x00};
        DWORD written=0;
        Require(WriteFile(interrupted.Get(),abandoned,sizeof(abandoned),&written,nullptr)!=FALSE &&
            written==sizeof(abandoned),"Could not write interrupted transaction fixture");
        Require(CountTemporaryFiles(destination)==1,"Transaction temporary was not created");
    }
    Require(NativeSaveArchive::Read(destination)==second,"Aborted transaction changed the old destination");
    Require(CountTemporaryFiles(destination)==0,"Aborted transaction did not remove its temporary");
}
}

int main(int argc,char** argv){
    try{
        if(argc!=2)throw std::invalid_argument("Expected a unique transaction test directory");
        const std::wstring directory=ToWide(argv[1]);
        TestRoundTripAndMalformedArchives();
        TestAtomicFileTransactions(directory);
        std::printf("NATIVE_SAVE_ARCHIVE_PASS checks=%d GAMECORE_LOADED=false\n",checks);
        return 0;
    }catch(const std::exception& error){
        std::fprintf(stderr,"NATIVE_SAVE_ARCHIVE_FAIL checks=%d reason=%s\n",checks,error.what());
        return 1;
    }
}
