#pragma once
#include <array>
#include <cstdint>
#include <stdexcept>
#include <string>
#include <vector>

namespace ZeroSisHost {
// Plain version-12 Civ5Map framing used by the existing SDK's Save(...,false).
// This never accepts an SDK save envelope or treats a campaign as a map.
struct MenuMapDocument final {
    std::uint32_t width=0,height=0,flags=0;
    std::string name,worldType;
    static MenuMapDocument Read(const std::vector<unsigned char>& bytes){
        if(bytes.size()<46 || bytes.size()>64u*1024u*1024u || bytes[0]!=12)
            throw std::invalid_argument("Only bounded plain version-12 Civ5Map files are supported");
        std::size_t at=1;
        const auto word=[&](){
            if(bytes.size()-at<4)throw std::invalid_argument("Truncated map header");
            std::uint32_t value=0;for(unsigned n=0;n<4;++n)value|=std::uint32_t(bytes[at++])<<(8*n);
            return value;
        };
        const auto text=[&](std::size_t size){
            if(size>bytes.size()-at)throw std::invalid_argument("Map section exceeds file bounds");
            std::string value(reinterpret_cast<const char*>(bytes.data()+at),size);at+=size;return value;
        };
        MenuMapDocument result;result.width=word();result.height=word();
        if(!result.width || !result.height || std::uint64_t(result.width)*result.height>32768 || bytes[at++]>32)
            throw std::invalid_argument("Map dimensions or playable slots exceed SDK capacity");
        result.flags=word();std::array<std::uint32_t,7> sizes{};for(auto& size:sizes)size=word();
        for(unsigned n=0;n<7;++n){
            const auto section=text(sizes[n]);
            if(n<4 && !section.empty() && section.back()!='\0')throw std::invalid_argument("Unterminated map type table");
            if(n==5)result.name=section;
        }
        result.worldType=text(word());
        if(!result.worldType.empty() && result.worldType.back()=='\0')result.worldType.pop_back();
        if(result.worldType.find('\0')!=std::string::npos || result.worldType.size()>64)
            throw std::invalid_argument("Invalid map world type");
        if(!result.name.empty() && result.name.back()=='\0')result.name.pop_back();
        if(result.name.find('\0')!=std::string::npos || result.name.size()>1024)
            throw std::invalid_argument("Invalid map title");
        if(bytes.size()-at!=std::size_t(result.width)*result.height*8)
            throw std::invalid_argument("Plain map plots are truncated or have trailing bytes");
        return result;
    }
};
}
