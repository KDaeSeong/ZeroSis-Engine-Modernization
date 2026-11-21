#include "SdkWorldBuilderModDataWire.h"
#include <cstring>
#include <limits>
#include <stdexcept>
#include <utility>

namespace ZeroSisWorldBuilder {
namespace {
struct Reader {
    const unsigned char* input;std::size_t size,offset;
    Reader(const void* p,std::size_t n):input(static_cast<const unsigned char*>(p)),size(n),offset(0){if(!p)throw std::invalid_argument("Null map mod-data input");}
    void Require(std::size_t n) const {if(n>size-offset)throw std::invalid_argument("Truncated map mod-data");}
    std::uint32_t Word(){Require(4);const unsigned char* p=input+offset;offset+=4;return std::uint32_t(p[0])|(std::uint32_t(p[1])<<8)|(std::uint32_t(p[2])<<16)|(std::uint32_t(p[3])<<24);}
    std::uint32_t Count(std::size_t width){const std::uint32_t n=Word();if(n>std::numeric_limits<std::uint32_t>::max()/width)throw std::length_error("Mod-data allocation size overflows SDK width");Require(std::size_t(n)*width);return n;}
};
ModSchema ReadSchema(Reader& r){
    ModSchema s;const std::uint32_t count=r.Word(),enums=r.Word();
    if(count>std::numeric_limits<std::uint32_t>::max()/12)throw std::length_error("Too many map mod-data fields");
    r.Require(std::size_t(count)*12);
    s.fields.reserve(count);for(std::uint32_t i=0;i<count;++i){ModField f={r.Word(),r.Word(),r.Word()};s.fields.push_back(f);}
    // Every enum needs at least its 4-byte member count. Check before allocating.
    if(enums>std::numeric_limits<std::uint32_t>::max()-3u)throw std::length_error("Too many map mod-data enums");
    if(enums>(r.size-r.offset)/4)throw std::invalid_argument("Truncated map mod-data enums");
    s.enums.reserve(enums);for(std::uint32_t i=0;i<enums;++i){const std::uint32_t n=r.Count(4);std::vector<std::uint32_t> values;values.reserve(n);
        for(std::uint32_t j=0;j<n;++j)values.push_back(r.Word());s.enums.push_back(std::move(values));}
    return s;
}
void RequireString(const ModDocument& d,std::uint32_t offset){
    if(offset>=d.strings.size() || !std::memchr(d.strings.data()+offset,0,d.strings.size()-offset))
        throw std::invalid_argument("Invalid map mod-data string reference");
}
void ValidateSchema(const ModDocument& d,const ModSchema& s){
    if(s.fields.size()>std::numeric_limits<std::uint32_t>::max()/12 || s.enums.size()>std::numeric_limits<std::uint32_t>::max()-3u)
        throw std::length_error("Map mod-data schema too large");
    for(const ModField& f:s.fields){RequireString(d,f.name);if(f.type==2)RequireString(d,f.value);
        else if(f.type>=3 && std::size_t(f.type-3)>=s.enums.size())throw std::invalid_argument("Invalid map mod-data enum reference");}
    for(const std::vector<std::uint32_t>& values:s.enums){
        if(values.size()>std::numeric_limits<std::uint32_t>::max()/4)throw std::length_error("Map mod-data enum too large");
        for(std::uint32_t value:values)RequireString(d,value);}
}
void AppendWord(std::vector<unsigned char>& out,std::uint32_t word){for(unsigned i=0;i<4;++i)out.push_back(static_cast<unsigned char>(word>>(8*i)));}
void AppendSchema(std::vector<unsigned char>& out,const ModSchema& s){
    AppendWord(out,static_cast<std::uint32_t>(s.fields.size()));AppendWord(out,static_cast<std::uint32_t>(s.enums.size()));
    for(const ModField& f:s.fields){AppendWord(out,f.type);AppendWord(out,f.name);AppendWord(out,f.value);}
    for(const std::vector<std::uint32_t>& values:s.enums){AppendWord(out,static_cast<std::uint32_t>(values.size()));for(std::uint32_t v:values)AppendWord(out,v);}
}
}
void ValidateModDocument(const ModDocument& d){
    if(d.strings.size()>std::numeric_limits<std::uint32_t>::max() || d.values.size()>std::numeric_limits<std::uint32_t>::max()/4)
        throw std::length_error("Map mod-data storage too large");
    if(!d.strings.empty() && d.strings.back()!=0)throw std::invalid_argument("Unterminated map mod-data string buffer");
    ValidateSchema(d,d.map);ValidateSchema(d,d.plot);
    // Schemas may be serialized before InitDataEntries, so an absent data array
    // is legal. The full map loader must separately validate the plot count.
    for(std::size_t i=0;i<d.values.size();++i){
        const ModField* field=NULL;
        if(i<d.map.fields.size())field=&d.map.fields[i];
        else if(!d.plot.fields.empty())field=&d.plot.fields[(i-d.map.fields.size())%d.plot.fields.size()];
        if(field && field->type==2)RequireString(d,d.values[i]);
    }
}
ModDocument ReadModDocument(const void* bytes,std::size_t size,bool exact){
    Reader r(bytes,size);ModDocument d;d.map=ReadSchema(r);d.plot=ReadSchema(r);
    const std::uint32_t count=r.Count(4);d.values.reserve(count);for(std::uint32_t i=0;i<count;++i)d.values.push_back(r.Word());
    const std::uint32_t stringBytes=r.Count(1);d.strings.resize(stringBytes);
    if(stringBytes)std::memcpy(d.strings.data(),r.input+r.offset,stringBytes);r.offset+=stringBytes;
    if(exact && r.offset!=size)throw std::invalid_argument("Trailing map mod-data bytes");
    ValidateModDocument(d);return d;
}
std::vector<unsigned char> WriteModDocument(const ModDocument& d){
    ValidateModDocument(d);std::vector<unsigned char> out;AppendSchema(out,d.map);AppendSchema(out,d.plot);
    AppendWord(out,static_cast<std::uint32_t>(d.values.size()));for(std::uint32_t value:d.values)AppendWord(out,value);
    AppendWord(out,static_cast<std::uint32_t>(d.strings.size()));out.insert(out.end(),d.strings.begin(),d.strings.end());return out;
}
}
