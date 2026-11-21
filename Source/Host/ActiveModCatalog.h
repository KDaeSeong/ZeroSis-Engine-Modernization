#pragma once
#include <map>
#include <stdexcept>
#include <string>
#include <vector>

namespace ZeroSisHost {
// A session activation declaration, not an inventory of installed mods or DLC.
// The caller owns the activation process; this immutable value only answers
// queries about that declared configuration.
class ActiveModCatalog final {
public:
    struct Entry {std::string id;int version;};
    explicit ActiveModCatalog(const std::vector<Entry>& entries){
        for(const auto& entry:entries){
            if(entry.version<1)throw std::invalid_argument("Active mod version must be positive");
            if(entry.id.find('\0')!=std::string::npos)throw std::invalid_argument("NUL in active mod identifier");
            if(!versions_.emplace(Key(entry.id.c_str()),entry.version).second)
                throw std::invalid_argument("A mod cannot have duplicate active versions");
        }
    }
    bool Contains(const char* id) const {return versions_.count(Key(id))!=0;}
    std::size_t Size() const noexcept {return versions_.size();}
private:
    static std::string Key(const char* id){
        if(!id)throw std::invalid_argument("Missing mod identifier");
        std::size_t size=0;while(size<37 && id[size])++size;
        if(size!=32 && size!=36)throw std::invalid_argument("Mod identifier must be a GUID");
        std::string key;key.reserve(32);
        for(std::size_t i=0;i<size;++i){
            const char value=id[i];
            if(size==36 && (i==8 || i==13 || i==18 || i==23)){
                if(value!='-')throw std::invalid_argument("Invalid mod GUID separator");
                continue;
            }
            if(value>='0' && value<='9')key+=value;
            else if(value>='a' && value<='f')key+=value;
            else if(value>='A' && value<='F')key+=static_cast<char>(value-'A'+'a');
            else throw std::invalid_argument("Invalid mod GUID digit");
        }
        return key;
    }
    std::map<std::string,int> versions_;
};
}
