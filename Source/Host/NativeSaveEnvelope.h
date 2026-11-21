#pragma once

// Native-host V1 envelope only; retail payloads remain opaque section bytes.
// The caller supplies SHA-256 and owns every platform or file operation.
#include <array>
#include <climits>
#include <cstddef>
#include <cstring>
#include <stdexcept>
#include <utility>
#include <vector>

namespace ZeroSisHost {
static_assert(CHAR_BIT==8 && sizeof(unsigned)==4 && sizeof(int)==4,
    "Native V1 requires eight-bit bytes and 32-bit integer fields");

struct NativeSaveSection {
    unsigned kind=0,index=0;
    std::vector<unsigned char> bytes;
};
struct NativeSaveEnvelope {
    static constexpr unsigned TeamSlots=64u;
    static constexpr unsigned PlayerSlots=64u;
    enum Kind : unsigned {Bundle=1,Pregame=2,Game=3,Map=4,Supporting=5,Team=6,Player=7};
    unsigned flags=0;
    int turn=0,elapsed=0,activePlayer=0;
    std::vector<NativeSaveSection> sections;

    static unsigned SectionCount() noexcept {return 5+TeamSlots+PlayerSlots;}
    void Validate() const {
        if(flags>3 || turn<0 || elapsed<0 || activePlayer<0 || activePlayer>=static_cast<int>(PlayerSlots) || sections.size()!=SectionCount())
            throw std::invalid_argument("Invalid native save metadata or section count");
        for(unsigned i=0;i<SectionCount();++i){
            const auto& section=sections[i];
            const unsigned kind=i<5?i+1:(i<5+TeamSlots?Team:Player);
            const unsigned index=i<5?0:(i<5+TeamSlots?i-5:i-5-TeamSlots);
            if(section.kind!=kind || section.index!=index || section.bytes.empty() || section.bytes.size()>INT_MAX)
                throw std::invalid_argument("Invalid native save section layout");
        }
    }
    template<class DigestFunction>
    std::vector<unsigned char> Encode(DigestFunction digestFunction) const {
        Validate();
        const unsigned char magic[16]={'Z','E','R','O','S','I','S','_','S','A','V','E','_','V','1',0};
        std::vector<unsigned char> output(magic,magic+16);
        Put(output,1);Put(output,flags);Put(output,static_cast<unsigned>(turn));
        Put(output,static_cast<unsigned>(elapsed));Put(output,static_cast<unsigned>(activePlayer));
        Put(output,TeamSlots);Put(output,PlayerSlots);Put(output,SectionCount());
        for(const auto& section:sections){
            Put(output,section.kind);Put(output,section.index);Put(output,static_cast<unsigned>(section.bytes.size()));
            output.insert(output.end(),section.bytes.begin(),section.bytes.end());
        }
        const std::array<unsigned char,32> digest=digestFunction(output.data(),output.size());output.insert(output.end(),digest.begin(),digest.end());
        return output;
    }
    template<class DigestFunction>
    static NativeSaveEnvelope Decode(const std::vector<unsigned char>& bytes,DigestFunction digestFunction){
        const unsigned char magic[16]={'Z','E','R','O','S','I','S','_','S','A','V','E','_','V','1',0};
        if(bytes.size()<80 || std::memcmp(bytes.data(),magic,16)!=0)
            throw std::invalid_argument("Invalid native save header");
        const std::size_t end=bytes.size()-32;
        const std::array<unsigned char,32> digest=digestFunction(bytes.data(),end);
        if(std::memcmp(digest.data(),bytes.data()+end,digest.size())!=0)
            throw std::invalid_argument("Native save checksum differs");
        std::size_t at=16;
        const auto get=[&](){
            if(at>end || end-at<4)throw std::invalid_argument("Truncated native save field");
            const unsigned value=static_cast<unsigned>(bytes[at]) | (static_cast<unsigned>(bytes[at+1])<<8) |
                (static_cast<unsigned>(bytes[at+2])<<16) | (static_cast<unsigned>(bytes[at+3])<<24);
            at+=4;return value;
        };
        if(get()!=1)throw std::invalid_argument("Unsupported native save version");
        NativeSaveEnvelope result;result.flags=get();
        const unsigned turn=get(),elapsed=get(),active=get();
        if(turn>INT_MAX || elapsed>INT_MAX || active>=PlayerSlots)
            throw std::invalid_argument("Native save counters exceed their SDK fields");
        result.turn=static_cast<int>(turn);result.elapsed=static_cast<int>(elapsed);result.activePlayer=static_cast<int>(active);
        if(get()!=TeamSlots || get()!=PlayerSlots || get()!=SectionCount())
            throw std::invalid_argument("Native save slot configuration differs");
        result.sections.reserve(SectionCount());
        for(unsigned i=0;i<SectionCount();++i){
            NativeSaveSection section;section.kind=get();section.index=get();const unsigned size=get();
            if(!size || size>INT_MAX || size>end-at)throw std::invalid_argument("Native save section extends beyond its payload");
            section.bytes.assign(bytes.data()+at,bytes.data()+at+size);at+=size;
            result.sections.push_back(std::move(section));
        }
        if(at!=end)throw std::invalid_argument("Native save has trailing section data");
        result.Validate();return result;
    }
private:
    static void Put(std::vector<unsigned char>& bytes,unsigned value){
        for(unsigned shift=0;shift<32;shift+=8)bytes.push_back(static_cast<unsigned char>(value>>shift));
    }
};
}
