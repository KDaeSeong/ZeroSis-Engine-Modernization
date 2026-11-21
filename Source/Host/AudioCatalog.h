#pragma once
#include <cstdint>
#include <cstring>
#include <map>
#include <stdexcept>
#include <string>
#include <vector>

namespace ZeroSisHost {
struct AudioDefinition {std::string tag,xml;};
class AudioCatalog {
public:
    explicit AudioCatalog(const std::vector<unsigned char>& bytes) {
        Reader input(bytes);
        if(input.Text(8)!="ZSAUDIO1")throw std::runtime_error("Invalid audio catalog version");
        const std::uint32_t count=input.Word();
        if(!count || count>65536)throw std::runtime_error("Invalid audio catalog count");
        for(std::uint32_t i=0;i<count;++i){
            AudioDefinition entry;entry.tag=input.String(256);entry.xml=input.String(1024*1024);
            if(entry.tag.empty() || entry.tag.find_first_not_of("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_")!=std::string::npos)
                throw std::runtime_error("Invalid audio catalog tag");
            if(entry.xml.empty() || entry.xml.find('\0')!=std::string::npos)throw std::runtime_error("Invalid audio definition payload");
            if(!byName_.emplace(entry.tag,static_cast<int>(i)).second)throw std::runtime_error("Duplicate audio catalog tag");
            definitions_.push_back(std::move(entry));
        }
        if(!input.Done())throw std::runtime_error("Trailing audio catalog bytes");
    }
    int Find(const char* tag) const {
        if(!tag || !*tag)return -1;
        const auto found=byName_.find(tag);return found==byName_.end()?-1:found->second;
    }
    const AudioDefinition& Definition(int index) const {
        if(index<0 || static_cast<std::size_t>(index)>=definitions_.size())throw std::out_of_range("Audio definition index");
        return definitions_[static_cast<std::size_t>(index)];
    }
    std::size_t Size() const noexcept{return definitions_.size();}
private:
    class Reader {
    public:
        explicit Reader(const std::vector<unsigned char>& bytes):bytes_(bytes){
            if(bytes.size()>16*1024*1024)throw std::runtime_error("Audio catalog is too large");
        }
        std::uint32_t Word(){
            const auto value=Text(4);std::uint32_t result=0;
            for(unsigned i=0;i<4;++i)result|=static_cast<std::uint32_t>(static_cast<unsigned char>(value[i]))<<(i*8);
            return result;
        }
        std::string String(std::size_t limit){const auto size=Word();if(size>limit)throw std::runtime_error("Audio field is too large");return Text(size);}
        std::string Text(std::size_t size){
            if(size>bytes_.size()-position_)throw std::runtime_error("Truncated audio catalog");
            if(!size)return {};
            std::string result(reinterpret_cast<const char*>(bytes_.data()+position_),size);position_+=size;return result;
        }
        bool Done() const noexcept{return position_==bytes_.size();}
    private:const std::vector<unsigned char>& bytes_;std::size_t position_=0;
    };
    std::vector<AudioDefinition> definitions_;
    std::map<std::string,int> byName_;
};
}
