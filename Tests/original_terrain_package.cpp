#include "OriginalTerrainPackage.h"
#include "OriginalTerrainBinding.h"
#include <cstdio>
#include <fstream>
#include <limits>
#include <sstream>

using namespace ZeroSisPresentation::OriginalTerrain;
namespace {
unsigned checks=0;
void Require(bool value){++checks;if(!value)throw std::runtime_error("Original terrain package regression");}
std::vector<unsigned char> Read(const std::string& path){
    std::ifstream stream(path,std::ios::binary|std::ios::ate);Require(stream.good());
    const auto count=stream.tellg();Require(count>=0 && count<=128*1024*1024);
    std::vector<unsigned char> bytes(static_cast<std::size_t>(count));stream.seekg(0);
    if(!bytes.empty())stream.read(reinterpret_cast<char*>(bytes.data()),static_cast<std::streamsize>(bytes.size()));
    Require(stream.good());return bytes;
}
void Vectors(const std::string& filename){
    Require(Sha256Hex(nullptr,0)=="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855");
    const unsigned char abc[]={'a','b','c'};
    Require(Sha256Hex(abc,3)=="ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad");
    std::vector<unsigned char> million(1000000,static_cast<unsigned char>('a'));
    Require(Sha256Hex(million.data(),million.size())=="cdc76e5c9914fb9281a1c7e284d73e67f1809a48a497200e046d39ccc7112cd0");
    std::ifstream stream(filename);Require(stream.good());
    unsigned count=0;stream>>count;Require(count==12);
    for(unsigned item=0;item<count;++item){
        unsigned size=0;std::string expected;stream>>size>>expected;Require(stream.good() && size<=1024);
        std::vector<unsigned char> input(size);
        for(unsigned i=0;i<size;++i)input[i]=static_cast<unsigned char>((i*37+size)%256);
        Require(Sha256Hex(input.data(),input.size())==expected);
    }
}
void Actual(const std::string& filename,const std::string& metadata){
    auto package=DecodePackage(Read(filename),PackageSha256);
    Require(package.rows.size()==41 && package.textures.size()==72 && package.bytes.size()==112874723);
    std::ifstream stream(metadata);Require(stream.good());
    unsigned rowCount=0,textureCount=0,expanded=0;std::string outer;
    stream>>rowCount>>textureCount>>expanded>>outer;
    Require(rowCount==41 && textureCount==72 && expanded==47 && outer==PackageSha256);
    unsigned actualExpanded=0;
    for(unsigned i=0;i<rowCount;++i){
        unsigned row=0,continent=0,legacy=0,scale=0,projection=0,diffuse=0,height=0,specular=0;
        stream>>row>>continent>>legacy>>scale>>projection>>diffuse>>height>>specular;Require(stream.good());
        const auto& parsed=package.rows[i];unsigned parsedScale=0;std::memcpy(&parsedScale,&parsed.scale,sizeof(parsedScale));
        Require(parsed.row==row && parsed.continent==continent && parsed.legacyId==legacy && parsedScale==scale &&
            parsed.projection==projection && parsed.diffuse==diffuse && parsed.height==height && parsed.specular==specular);
        actualExpanded+=parsed.projection?3u:1u;
    }
    Require(actualExpanded==47 && package.rows[8].height==DeclaredMissingTexture && package.rows[0].specular==NullTexture);
    for(unsigned i=0;i<textureCount;++i){
        unsigned index=0,width=0,height=0,mips=0;std::size_t offset=0,bytes=0;std::string hash,name;
        stream>>index>>offset>>bytes>>width>>height>>mips>>hash>>name;Require(stream.good() && index==i);
        const auto& parsed=package.textures[i];Require(parsed.name==name && parsed.offset==offset && parsed.bytes==bytes &&
            parsed.width==width && parsed.height==height && parsed.mips==mips && offset+bytes<=package.bytes.size());
        Require(Sha256Hex(package.bytes.data()+offset,bytes)==hash);
    }
    std::size_t offset=0,bytes=0;std::string hash;stream>>offset>>bytes>>hash;Require(stream.good());
    Require(offset==package.libraryOffset && bytes==package.libraryBytes && bytes==27595584 && offset+bytes==package.bytes.size());
    Require(Sha256Hex(package.bytes.data()+offset,bytes)==hash && hash==
        "86faac1e80634b0031a9df98889682fbc17ddc72341fc68fbf5b33e7ce4c1c7a");
}
unsigned Fixtures(const std::string& directory){
    std::ifstream stream(directory+"/cases.txt");Require(stream.good());
    unsigned count=0;stream>>count;Require(count>=35 && count<100);
    for(unsigned i=0;i<count;++i){
        unsigned accepted=0;std::string hash,name;stream>>accepted>>hash>>name;Require(stream.good() && accepted<=1);
        bool rejected=false;
        try{auto value=DecodePackage(Read(directory+"/"+name),hash);Require(!value.rows.empty());}
        catch(const std::invalid_argument&){rejected=true;}
        Require(rejected==(accepted==0));
    }
    return count;
}
}
int main(int argc,char** argv){
    try{
        Require(argc==5);Vectors(argv[3]);Actual(argv[1],argv[2]);const auto cases=Fixtures(argv[4]);
        std::printf("PASS_ORIGINAL_TERRAIN_PACKAGE checks=%u fixtures=%u real_rows=41 real_textures=72 expanded=47\n",checks,cases);return 0;
    }catch(const std::exception& ex){std::fprintf(stderr,"FAIL: %s\n",ex.what());return 1;}
}
