#pragma once
#include "OriginalFogPackage.h"
#include <cctype>
#include <cmath>
#include <initializer_list>
#include <locale>
#include <map>
#include <set>
#include <sstream>

namespace ZeroSisPresentation { namespace OriginalWater {
enum class AssetRole:std::uint32_t {WaterDepthColour=1,WaterBumps,WaterSky,RiverAlpha,RiverDiffuse,RiverRough,RiverSmooth,
    CoastWave,RiverbankDiffuse,RiverbankEndcap1,RiverbankEndcap2,RiverbankHeight,GenericRiverbankDiffuse,GenericRiverbankSpecular,
    CoastStyles,Spline01Water,Spline01Surf,Spline01Beach,Spline02Water,Spline02Surf,Spline02Beach,Spline03Water,Spline03Surf,Spline03Beach,CoastSchema};
using Texture=OriginalFog::Texture;
using TextureFormat=OriginalFog::TextureFormat;
struct CoastBand {double height=0,offset=0;unsigned character=65535,terrainType=65535;};
struct CoastStyle {std::string name;double highSmoothing=0,lowSmoothing=0;CoastBand highBeach,lowBeach,waterline;};
struct SplinePoint {double x=0,y=0,z=0;};
struct CoastProfile {AssetRole role=AssetRole::Spline01Water;std::string name;std::vector<SplinePoint> points;};
struct Asset {AssetRole role=AssetRole::WaterDepthColour;std::string name;unsigned blobIndex=0;std::size_t offset=0,bytes=0;Texture texture;};
struct WaterPackage {std::vector<unsigned char> bytes;std::vector<Asset> assets;std::vector<CoastStyle> styles;std::vector<CoastProfile> profiles;};
inline void Require(bool value,const char* message){if(!value)throw std::invalid_argument(message);}
inline const char* RoleName(unsigned role){
    static const char* const names[]={"waterdepthcolor.dds","waterbumps.dds","watersky.dds","river_alpha.dds","river_diffuse.dds",
        "river_rough.dds","river_smooth.dds","wave_coastline_01.dds","riverbank_d.dds","riverbank_d_endcap1.dds","riverbank_d_endcap2.dds",
        "riverbank_h.dds","generic_riverbank_d.dds","generic_riverbank_s.dds","coaststyles.xml","coastcharacterspline_01_water.txt",
        "coastcharacterspline_01_surf.txt","coastcharacterspline_01_beach.txt","coastcharacterspline_02_water.txt","coastcharacterspline_02_surf.txt",
        "coastcharacterspline_02_beach.txt","coastcharacterspline_03_water.txt","coastcharacterspline_03_surf.txt","coastcharacterspline_03_beach.txt","civ5coaststyleschema.xsd"};
    Require(role>=1 && role<=25,"Invalid water asset role");return names[role-1];
}
inline const char* StyleName(unsigned index){
    static const char* const names[]={"Default","Grass","GrassHill","Plains","PlainsHill","Snow","SnowHill","Desert","DesertHill","Tundra","TundraHill","Mountain","DefaultShallows"};
    Require(index<13,"Invalid coast style index");return names[index];
}
namespace Detail {
inline bool Space(char c){return c==' ' || c=='\t' || c=='\r' || c=='\n';}
inline std::string Lower(std::string text){for(auto& c:text)if(c>='A' && c<='Z')c=static_cast<char>(c-'A'+'a');return text;}
inline double Decimal(const std::string& text,double minimum,double maximum){
    Require(!text.empty() && text.size()<=64,"Unbounded coast decimal");std::size_t cursor=0;
    if(text[cursor]=='+' || text[cursor]=='-')++cursor;
    unsigned digits=0;while(cursor<text.size() && text[cursor]>='0' && text[cursor]<='9'){++cursor;++digits;}
    if(cursor<text.size() && text[cursor]=='.'){++cursor;while(cursor<text.size() && text[cursor]>='0' && text[cursor]<='9'){++cursor;++digits;}}
    Require(digits>0,"Invalid coast decimal mantissa");
    if(cursor<text.size() && (text[cursor]=='e' || text[cursor]=='E')){
        ++cursor;if(cursor<text.size() && (text[cursor]=='+' || text[cursor]=='-'))++cursor;unsigned exponentDigits=0;
        while(cursor<text.size() && text[cursor]>='0' && text[cursor]<='9'){++cursor;++exponentDigits;}
        Require(exponentDigits>0,"Invalid coast decimal exponent");
    }
    Require(cursor==text.size(),"Invalid coast decimal characters");
    std::istringstream stream(text);stream.imbue(std::locale::classic());double result=0;stream>>result;
    Require(!stream.fail() && std::isfinite(result) && result>=minimum && result<=maximum,"Nonfinite/out-of-range coast decimal");return result;
}
inline unsigned Integer(const std::string& text){
    Require(!text.empty() && text.size()<=5,"Unbounded coast integer");unsigned result=0;
    for(char c:text){Require(c>='0' && c<='9',"Invalid coast unsigned integer");result=result*10+unsigned(c-'0');}
    Require(result<=65535,"Coast integer exceeds bound");return result;
}
inline std::string XmlText(const unsigned char* raw,std::size_t count){
    Require(count>0 && count<=16384,"Unbounded coast XML");std::string text(reinterpret_cast<const char*>(raw),count);
    Require(std::all_of(text.begin(),text.end(),[](char c){const auto value=static_cast<unsigned char>(c);return value>0 && value<128;}),"Coast XML must be bounded ASCII");
    const auto lower=Lower(text);Require(lower.find("<!doctype")==std::string::npos && lower.find("<!entity")==std::string::npos,"Forbidden coast DTD/entity");return text;
}
struct XmlTag {std::string name;bool closing=false,selfClosing=false;std::map<std::string,std::string> attributes;};
class XmlReader {
    std::string text_;std::size_t cursor_=0;
    void Spaces(){while(cursor_<text_.size() && Space(text_[cursor_]))++cursor_;}
    bool Starts(const char* value)const{return text_.compare(cursor_,std::strlen(value),value)==0;}
    std::string Name(){
        const auto start=cursor_;
        while(cursor_<text_.size()){
            const auto c=text_[cursor_];if(!((c>='a'&&c<='z')||(c>='A'&&c<='Z')||(c>='0'&&c<='9')||c=='_'||c==':'||c=='-'||c=='.'))break;++cursor_;
        }
        Require(cursor_>start && cursor_-start<=64,"Invalid coast XML name");return text_.substr(start,cursor_-start);
    }
public:
    explicit XmlReader(std::string text):text_(std::move(text)){}
    XmlTag Next(){
        for(;;){
            Spaces();Require(cursor_<text_.size(),"Truncated coast XML");
            if(Starts("<!--")){const auto end=text_.find("-->",cursor_+4);Require(end!=std::string::npos,"Truncated coast XML comment");cursor_=end+3;continue;}
            if(cursor_==0 && Starts("<?xml")){const auto end=text_.find("?>",cursor_+5);Require(end!=std::string::npos,"Truncated coast XML declaration");cursor_=end+2;continue;}
            break;
        }
        Require(text_[cursor_++]=='<',"Unexpected coast XML text");XmlTag tag;
        if(cursor_<text_.size() && text_[cursor_]=='/'){tag.closing=true;++cursor_;}tag.name=Name();
        for(;;){
            Spaces();Require(cursor_<text_.size(),"Truncated coast XML tag");
            if(text_[cursor_]=='>'){++cursor_;return tag;}
            if(text_[cursor_]=='/'){++cursor_;Require(!tag.closing && cursor_<text_.size() && text_[cursor_++]=='>',"Invalid coast XML self close");tag.selfClosing=true;return tag;}
            Require(!tag.closing && tag.attributes.size()<8,"Invalid bounded coast XML attributes");const auto name=Name();Spaces();
            Require(cursor_<text_.size() && text_[cursor_++]=='=',"Invalid coast XML attribute assignment");Spaces();
            Require(cursor_<text_.size() && text_[cursor_++]=='\"',"Coast XML attribute must be quoted");const auto start=cursor_;
            while(cursor_<text_.size() && text_[cursor_]!='\"'){Require(text_[cursor_]!='<' && text_[cursor_]!='&',"Coast XML entities/markup are unsupported");++cursor_;}
            Require(cursor_<text_.size() && cursor_-start<=128,"Unbounded coast XML attribute value");
            Require(tag.attributes.emplace(name,text_.substr(start,cursor_-start)).second,"Duplicate coast XML attribute");++cursor_;
        }
    }
    void End(){Spaces();Require(cursor_==text_.size(),"Trailing coast XML data");}
};
inline void Attributes(const XmlTag& tag,std::initializer_list<const char*> names){
    Require(tag.attributes.size()==names.size(),"Unexpected coast XML attribute count");
    for(const auto* name:names)Require(tag.attributes.count(name)==1,"Missing coast XML attribute");
}
inline void Tag(const XmlTag& tag,const char* name,bool closing=false,bool selfClosing=false){
    Require(tag.name==name && tag.closing==closing && tag.selfClosing==selfClosing,"Unexpected coast XML structure");
}
inline void NamespaceList(const XmlTag& tag,const char* name){
    Tag(tag,name);Attributes(tag,{"xmlns:xsi","xsi:noNamespaceSchemaLocation"});
    Require(tag.attributes.at("xmlns:xsi")=="http://www.w3.org/2001/XMLSchema-instance" &&
        tag.attributes.at("xsi:noNamespaceSchemaLocation")=="Civ5CoastStyleSchema.xsd","Unexpected coast schema reference");
}
inline CoastBand Band(const XmlTag& tag,const char* name,bool terrain){
    Tag(tag,name,false,true);if(terrain)Attributes(tag,{"Height","Offset","Character","TerrainType"});else Attributes(tag,{"Height","Offset","Character"});
    CoastBand result;result.height=Decimal(tag.attributes.at("Height"),0,1);result.offset=Decimal(tag.attributes.at("Offset"),0,128);
    result.character=Integer(tag.attributes.at("Character"));Require(result.character<9 || result.character==65535,"Invalid coast character reference");
    if(terrain)result.terrainType=Integer(tag.attributes.at("TerrainType"));return result;
}
}
inline std::vector<CoastStyle> ParseCoastStyles(const unsigned char* raw,std::size_t count){
    Detail::XmlReader reader(Detail::XmlText(raw,count));auto tag=reader.Next();Detail::Tag(tag,"CoastRoot");Detail::Attributes(tag,{});
    Detail::NamespaceList(reader.Next(),"SplineCharacterList");
    for(unsigned i=0;i<9;++i){tag=reader.Next();Detail::Tag(tag,"SplineCharacter",false,true);Detail::Attributes(tag,{"Filename"});
        Require(Detail::Lower(tag.attributes.at("Filename"))==RoleName(16+i),"Noncanonical ordered coast character path");}
    tag=reader.Next();Detail::Tag(tag,"SplineCharacterList",true);Detail::Attributes(tag,{});
    Detail::NamespaceList(reader.Next(),"CoastStyleList");std::vector<CoastStyle> result;
    for(unsigned i=0;i<13;++i){
        tag=reader.Next();Detail::Tag(tag,"CoastStyle");Detail::Attributes(tag,{"type"});CoastStyle style;style.name=tag.attributes.at("type");
        Require(style.name==StyleName(i),"Noncanonical ordered coast style");tag=reader.Next();Detail::Tag(tag,"SmoothingOffset",false,true);Detail::Attributes(tag,{"HighSide","LowSide"});
        style.highSmoothing=Detail::Decimal(tag.attributes.at("HighSide"),0,128);style.lowSmoothing=Detail::Decimal(tag.attributes.at("LowSide"),0,128);
        style.highBeach=Detail::Band(reader.Next(),"HighBeach",true);style.lowBeach=Detail::Band(reader.Next(),"LowBeach",true);
        style.waterline=Detail::Band(reader.Next(),"Waterline",false);tag=reader.Next();Detail::Tag(tag,"CoastStyle",true);Detail::Attributes(tag,{});result.push_back(std::move(style));
    }
    tag=reader.Next();Detail::Tag(tag,"CoastStyleList",true);Detail::Attributes(tag,{});tag=reader.Next();Detail::Tag(tag,"CoastRoot",true);Detail::Attributes(tag,{});reader.End();return result;
}
inline CoastProfile ParseCoastProfile(const unsigned char* raw,std::size_t count,AssetRole role,const std::string& name){
    Require(count>0 && count<=8192,"Unbounded coast profile");std::string text(reinterpret_cast<const char*>(raw),count);
    Require(std::all_of(text.begin(),text.end(),[](char c){const auto v=static_cast<unsigned char>(c);return v>0 && v<128;}),"Coast profile must be ASCII");
    CoastProfile result;result.role=role;result.name=name;std::size_t cursor=0;
    const auto spaces=[&](){while(cursor<text.size() && Detail::Space(text[cursor]))++cursor;};
    while(true){
        spaces();if(cursor==text.size())break;Require(text[cursor++]=='[' && result.points.size()<100,"Invalid bounded coast point");
        double values[3]{};
        for(unsigned i=0;i<3;++i){
            spaces();const auto start=cursor;while(cursor<text.size() && text[cursor]!=',' && text[cursor]!=']' && !Detail::Space(text[cursor]))++cursor;
            values[i]=Detail::Decimal(text.substr(start,cursor-start),i? -64.0:0.0,i?64.0:400.0);spaces();
            Require(cursor<text.size() && text[cursor++]==(i==2?']':','),"Coast point delimiter differs");
        }
        Require(values[2]==0 && (result.points.empty() || result.points.back().x>values[0]),"Coast profile must descend X with Z=0");
        result.points.push_back({values[0],values[1],values[2]});
        Require(cursor==text.size() || Detail::Space(text[cursor]),"Coast point must end at whitespace");
    }
    Require(result.points.size()==100 && result.points.front().x==400 && result.points.back().x==0,"Coast profile count/endpoints differ");return result;
}
inline const Asset& FindAsset(const WaterPackage& package,AssetRole role){
    const auto number=static_cast<unsigned>(role);Require(number>=1 && number<=package.assets.size(),"Missing water asset role");
    const auto& asset=package.assets[number-1];Require(asset.role==role,"Water asset role differs");return asset;
}
inline const unsigned char* AssetData(const WaterPackage& package,const Asset& asset){
    Require(asset.bytes>0 && asset.offset<=package.bytes.size() && asset.bytes<=package.bytes.size()-asset.offset,"Water asset outside package");return package.bytes.data()+asset.offset;
}
inline WaterPackage DecodePackage(std::vector<unsigned char> bytes,const std::string& expectedSha){
    Require(bytes.size()>=20 && bytes.size()<=16u*1024u*1024u,"Water package exceeds size bound");
    Require(expectedSha.size()==64 && OriginalTerrain::Sha256Hex(bytes.data(),bytes.size())==expectedSha,"Water package outer SHA256 differs");
    WaterPackage result;result.bytes=std::move(bytes);const auto& raw=result.bytes;std::size_t cursor=0;
    const auto take=[&](std::size_t count){Require(count<=raw.size()-cursor,"Truncated water package");const auto* p=raw.data()+cursor;cursor+=count;return p;};
    const auto u32=[&](){return OriginalFog::Word(take(4));};
    Require(std::memcmp(take(8),"ZSWATER1",8)==0 && u32()==1 && u32()==25,"Unknown water package format/count");const auto blobCount=u32();
    Require(blobCount>0 && blobCount<=25,"Unbounded water blob count");std::vector<bool> seen(blobCount,false);unsigned nextBlob=0;
    for(unsigned index=1;index<=25;++index){
        const auto role=u32(),size=u32(),blob=u32();Require(role==index && size>0 && size<=64 && blob<blobCount,"Invalid ordered water descriptor");
        const auto* p=take(size);const std::string name(reinterpret_cast<const char*>(p),size);Require(name==RoleName(role),"Noncanonical water asset name");
        if(!seen[blob]){Require(blob==nextBlob++,"Water blob first-reference order differs");seen[blob]=true;}
        Asset asset;asset.role=static_cast<AssetRole>(role);asset.name=name;asset.blobIndex=blob;result.assets.push_back(std::move(asset));
    }
    Require(nextBlob==blobCount,"Water blob is unreferenced");struct Blob {std::size_t offset,bytes;};std::vector<Blob> blobs;std::set<std::string> hashes;
    for(unsigned i=0;i<blobCount;++i){
        const auto count=u32();const auto* digest=take(32);Require(count>0 && count<=5u*1024u*1024u,"Unbounded water blob");
        const auto offset=cursor;const auto* p=take(count);const auto hash=OriginalTerrain::Sha256(p,count);
        Require(std::memcmp(hash.data(),digest,32)==0 && hashes.emplace(reinterpret_cast<const char*>(digest),32).second,"Water blob SHA/uniqueness differs");
        blobs.push_back({offset,count});
    }
    Require(cursor==raw.size(),"Water package has trailing data");
    for(auto& asset:result.assets){
        const auto& blob=blobs[asset.blobIndex];asset.offset=blob.offset;asset.bytes=blob.bytes;const auto* p=AssetData(result,asset);const auto role=static_cast<unsigned>(asset.role);
        if(role<=14){
            asset.texture=OriginalFog::DecodeTexture(p,asset.bytes,asset.offset);
            const auto expected=(role==1 || role==2 || role==3 || role==4 || role==7)?TextureFormat::Bgra8:role==5?TextureFormat::Bc1:TextureFormat::Bc3;
            Require(asset.texture.format==expected,"Water role DDS codec differs");
        }else if(role==15)result.styles=ParseCoastStyles(p,asset.bytes);
        else if(role<=24)result.profiles.push_back(ParseCoastProfile(p,asset.bytes,asset.role,asset.name));
        else{
            const auto xml=Detail::XmlText(p,asset.bytes);Require(xml.find("<xs:schema")!=std::string::npos && xml.find("</xs:schema>")!=std::string::npos,"Invalid coast schema reference");
        }
    }
    Require(result.styles.size()==13 && result.profiles.size()==9,"Water coast definitions incomplete");return result;
}
}}
