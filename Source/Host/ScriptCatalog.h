#pragma once
#include <cstdint>
#include <map>
#include <stdexcept>
#include <string>
#include <vector>

namespace ZeroSisHost {
struct ScriptFile {std::string path,origin,contents;};
class ScriptCatalog {
public:
    ScriptCatalog(const ScriptCatalog&)=delete;
    ScriptCatalog& operator=(const ScriptCatalog&)=delete;
    explicit ScriptCatalog(const std::vector<unsigned char>& bytes){
        Reader reader(bytes);
        if(reader.Text(8)!="ZSSCRIP1")throw std::runtime_error("Invalid script catalog version");
        const auto count=reader.Word();if(!count || count>8192)throw std::runtime_error("Invalid script catalog count");
        for(std::uint32_t index=0;index<count;++index){
            ScriptFile file;file.path=reader.String(512);file.origin=reader.String(512);file.contents=reader.String(8*1024*1024);
            if(Key(file.path.c_str())!=file.path || Key(file.origin.c_str())!=file.origin)
                throw std::runtime_error("Noncanonical script catalog path");
            if(!files_.emplace(file.path,std::move(file)).second)throw std::runtime_error("Duplicate script catalog path");
        }
        if(!reader.Done())throw std::runtime_error("Trailing script catalog bytes");
        for(const auto& row:files_){
            const auto& file=row.second;Alias(file.path,&file);Alias(file.origin,&file);
            const auto name=file.path.substr(file.path.find_last_of('/')+1);
            auto entry=names_.emplace(name,&file);if(!entry.second)entry.first->second=nullptr;
        }
    }
    static std::string Key(const char* name){
        if(!name || !*name)throw std::invalid_argument("Script file name missing");
        std::string key(name);if(key.size()>512)throw std::invalid_argument("Script path is too long");
        for(char& c:key){if(c=='\\')c='/';if(c>='A'&&c<='Z')c=static_cast<char>(c-'A'+'a');
            if(static_cast<unsigned char>(c)<32 || c==':' || c=='%' || c=='*' || c=='?')throw std::invalid_argument("Invalid script file path");}
        if(key.front()=='/' || key.back()=='/' || key.find("//")!=std::string::npos)throw std::invalid_argument("Invalid script file path");
        std::size_t at=0;
        while(at<key.size()){
            const auto end=key.find('/',at);const auto part=key.substr(at,end==std::string::npos?end:end-at);
            if(part=="." || part=="..")throw std::invalid_argument("Invalid script file path");
            if(end==std::string::npos)break;at=end+1;
        }
        if(key.size()<4 || key.compare(key.size()-4,4,".lua")!=0)key+=".lua";
        if(key.size()>512)throw std::invalid_argument("Script path is too long");return key;
    }
    const ScriptFile* Resolve(const char* name) const{
        const auto key=Key(name);const auto found=aliases_.find(key);if(found!=aliases_.end())return found->second;
        if(key.find('/')!=std::string::npos)return nullptr;
        const auto simple=names_.find(key);if(simple==names_.end())return nullptr;
        if(!simple->second)throw std::runtime_error("Ambiguous script file name");return simple->second;
    }
    std::size_t Size() const noexcept{return files_.size();}
    const std::map<std::string,ScriptFile>& Files() const noexcept{return files_;}
private:
    void Alias(const std::string& key,const ScriptFile* file){
        const auto inserted=aliases_.emplace(key,file);
        if(!inserted.second && inserted.first->second!=file)throw std::runtime_error("Conflicting script path alias");
    }
    class Reader {
    public:
        explicit Reader(const std::vector<unsigned char>& bytes):bytes_(bytes){
            if(bytes.size()>64*1024*1024)throw std::runtime_error("Script catalog is too large");
        }
        std::uint32_t Word(){
            const auto raw=Text(4);std::uint32_t value=0;
            for(unsigned i=0;i<4;++i)value|=static_cast<std::uint32_t>(static_cast<unsigned char>(raw[i]))<<(8*i);return value;
        }
        std::string String(std::size_t limit){const auto length=Word();if(length>limit)throw std::runtime_error("Script catalog field is too large");return Text(length);}
        std::string Text(std::size_t length){
            if(length>bytes_.size()-position_)throw std::runtime_error("Truncated script catalog");
            if(!length)return {};std::string value(reinterpret_cast<const char*>(bytes_.data()+position_),length);position_+=length;return value;
        }
        bool Done() const noexcept{return position_==bytes_.size();}
    private:const std::vector<unsigned char>& bytes_;std::size_t position_=0;
    };
    std::map<std::string,ScriptFile> files_;
    std::map<std::string,const ScriptFile*> aliases_,names_;
};
}
