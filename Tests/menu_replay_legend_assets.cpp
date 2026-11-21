#include "menu_frontend_scene_fixture.h"
#include <tuple>
static unsigned checks=0;
static void Check(bool value,const char* reason){++checks;if(!value)throw std::runtime_error(reason);}
template<class F>static void Reject(F fn){try{fn();}catch(const std::exception&){Check(true,"rejection");return;}Check(false,"Malformed asset accepted");}
static void Word(std::vector<unsigned char>& bytes,std::size_t offset,std::uint32_t value){std::memcpy(bytes.data()+offset,&value,4);}
static void SameFont(const MenuFrontEndAssets::Font& a,const MenuFrontEndAssets::Font& b){
    Check(a.lineAdvance==b.lineAdvance && a.baseline==b.baseline && a.border==b.border,"Preserved font metrics changed");
    Check(a.layers.size()==b.layers.size() && a.glyphs.size()==b.glyphs.size(),"Preserved font inventory changed");
    for(std::size_t i=0;i<a.layers.size();++i){const auto& x=a.layers[i];const auto& y=b.layers[i];
        Check(x.texture==y.texture && x.color.r==y.color.r && x.color.g==y.color.g && x.color.b==y.color.b && x.color.a==y.color.a,"Preserved font layer changed");}
    for(const auto& row:a.glyphs){const auto& x=row.second;const auto& y=b.glyphs.at(row.first);
        Check(std::tie(x.a,x.b,x.c,x.originX,x.originY,x.u,x.v,x.width,x.height)==
              std::tie(y.a,y.b,y.c,y.originX,y.originY,y.u,y.v,y.width,y.height),"Preserved font glyph changed");}
}
static std::vector<std::size_t> FontOffsets(const std::vector<unsigned char>& data,std::size_t& countOffset){
    std::size_t pos=8;const auto controls=U32(data,pos);
    for(unsigned n=0;n<controls;++n){pos+=36;for(unsigned k=0;k<2;++k){const auto length=U32(data,pos);pos+=length;}}
    countOffset=pos;const auto count=U32(data,pos);std::vector<std::size_t> result;
    for(unsigned n=0;n<count;++n){result.push_back(pos);U32(data,pos);const auto style=U32(data,pos);pos+=style+12;
        const auto layers=U32(data,pos),glyphs=U32(data,pos);pos+=20*layers+40*glyphs;
        Check(pos<=data.size(),"Fixture font slice exceeded bank");}
    return result;
}
int wmain(int argc,wchar_t** argv){
    try{
        if(argc!=4)throw std::runtime_error("Expected immutable V3, V2 and V1 directories");
        auto v3=MenuFrontEndAssets::Load(argv[1]),v2=MenuFrontEndAssets::Load(argv[2]),v1=MenuFrontEndAssets::Load(argv[3]);
        Check(v3->Extended() && v2->Extended() && !v1->Extended(),"Bank version compatibility changed");
        Check(v1->Fonts().size()==3 && v2->Fonts().size()==3 && v3->Fonts().size()==4,"Legacy font lookup contract changed");
        Check(v3->HasFontFace(14) && !v2->HasFontFace(14) && !v1->HasFontFace(14),"Optional 14px capability differs");
        Check(!v3->HasFontFace(14,"Base") && !v3->HasFontFace(19),"Unsealed font face exposed");
        for(const auto& face:std::vector<std::pair<unsigned,std::string>>{{18,"Base"},{18,"Shadow"},{20,"Shadow"},{20,"SoftShadow"},{22,"Shadow"},{24,"Shadow"}})
            SameFont(v2->FontFace(face.first,face.second),v3->FontFace(face.first,face.second));
        Check(v3->Icons().size()==148 && v2->Icons().size()==148,"Original inline icons changed");
        const auto& font=v3->FontFace(14);
        Check(font.glyphs.size()==17320 && font.lineAdvance==17 && font.baseline==17 && font.border==0.5f && font.layers.size()==2,"Actual current 14px metrics differ");
        for(std::uint32_t cp=0xac00;cp<=0xd7a3;++cp)Check(font.glyphs.count(cp)!=0,"Modern Hangul glyph is missing");
        for(const auto& row:font.glyphs){const auto& g=row.second;Check(g.u+g.width<=2048 && g.v+g.height<=3132,"Full font source rectangle escaped its actual atlas");}
        const auto& a=font.glyphs.at('A');const auto& h=font.glyphs.at(0xd7a3);
        Check(a.u==1440 && a.v==2138 && a.a== -2 && a.b==15 && a.c== -2 && a.width==16 && a.height==19,"Actual current Latin source glyph differs");
        Check(h.u==884 && h.v==1017 && h.width==17 && h.height==20,"Full-coverage final Hangul glyph differs");
        Check(font.layers[0].color.r==1 && font.layers[0].color.g==1 && font.layers[0].color.b==200/255.0f && font.layers[0].color.a==1 &&
              font.layers[1].color.r==0 && font.layers[1].color.g==0 && font.layers[1].color.b==0 && font.layers[1].color.a==200/255.0f,"Original legend colors differ");
        const char* names[]={"CivSymbolsColor256.dds","CivSymbolsColor32_DLC_01.dds","CivSymbolsColor32_DLC_02.dds","CivSymbolsColor32_DLC_03.dds",
            "CivSymbolsColor32_DLC_04.dds","CivSymbolsColor32_DLC_D.dds","CivSymbolsColor32_DLC_Korea.dds","CivSymbolsColor32_Exp2.dds",
            "CivSymbolsColor32_Expansion.dds","CivSymbols_Color32_Shared.dds","bar300x2.dds","CheckBox.dds"};
        auto scene=v3->Background();Check(scene.textures.size()<=64,"Legend texture bank exceeds renderer contract");
        for(const auto* name:names){Check(v3->HasTextureNamed(name),"Original legend named texture is absent");const auto& row=v3->TextureNamed(name);
            Check(row.index<scene.textures.size(),"Named texture index escaped bank");const auto dds=Read(scene.textures[row.index].path);std::size_t at=12;
            Check(dds.size()>=128 && !std::memcmp(dds.data(),"DDS ",4),"Named legend texture is not DDS");
            const auto height=U32(dds,at),width=U32(dds,at);Check(width==row.width && height==row.height,"Named texture source dimensions differ");}
        Check(v3->HasTextureNamed("CIVSYMBOLSCOLOR32_EXP2.DDS") && !v2->HasTextureNamed("CivSymbolsColor32_Exp2.dds") && !v1->HasTextureNamed("CheckBox.dds"),"Named texture optional lookup changed");
        Check(!v3->HasTextureNamed("unknown.dds"),"Unknown named texture was exposed");
        Check(v3->TextureNamed("bar300x2.dds").index==7 && v3->TextureNamed("CheckBox.dds").index==32,"Existing exact control atlases lost stable indices");
        const float clip[]={536,369,634,386};const auto before=scene.sprites.size();
        v3->GlyphRun(scene,901,{65,0xd7a3},536,386,clip,14);
        Check(scene.sprites.size()==before+4 && scene.sprites[before].textureIndex==font.layers[1].texture &&
              scene.sprites[before+2].textureIndex==font.layers[0].texture,"Original shadow draw order differs");
        Check(scene.sprites[before].targetRect[0]==535.5f && scene.sprites[before].targetRect[1]==371.5f,"Actual 14px ABC/origin/border convention changed");
        for(std::size_t i=before;i<scene.sprites.size();++i)Check(std::equal(clip,clip+4,scene.sprites[i].clipRect),"Legend glyph clip changed");
        const MenuFrontEndAssets::Color selectedInk{0.1f,0.25f,1.0f,0.4f};
        auto defaultInk=v3->Background(),explicitLegacyInk=v3->Background(),replacedInk=v3->Background();
        const auto inkStart=defaultInk.sprites.size();
        v3->GlyphRun(defaultInk,903,{65,0xd7a3},536,386,clip,14,"Shadow",selectedInk);
        v3->GlyphRun(explicitLegacyInk,903,{65,0xd7a3},536,386,clip,14,"Shadow",selectedInk,false);
        v3->GlyphRun(replacedInk,903,{65,0xd7a3},536,386,clip,14,"Shadow",selectedInk,true);
        Check(defaultInk.sprites.size()==explicitLegacyInk.sprites.size() && defaultInk.sprites.size()==replacedInk.sprites.size(),"Explicit ink changed glyph count");
        for(std::size_t i=0;i<defaultInk.sprites.size();++i){const auto& aSprite=defaultInk.sprites[i];const auto& bSprite=explicitLegacyInk.sprites[i];
            Check(aSprite.textureIndex==bSprite.textureIndex && aSprite.controlKey==bSprite.controlKey &&
                std::memcmp(aSprite.sourceRect,bSprite.sourceRect,64)==0,"Default glyph output differs from explicit legacy tint bytes");}
        for(std::size_t i=inkStart;i<replacedInk.sprites.size();++i){const auto& aSprite=defaultInk.sprites[i];const auto& ink=replacedInk.sprites[i];
            Check(aSprite.textureIndex==ink.textureIndex && aSprite.controlKey==ink.controlKey &&
                std::memcmp(aSprite.sourceRect,ink.sourceRect,48)==0,"Explicit glyph ink changed source UV, target or clip bytes");
            const bool base=i>=inkStart+2;
            Check(ink.tintRGBA[0]==(base?selectedInk.r:0) && ink.tintRGBA[1]==(base?selectedInk.g:0) &&
                ink.tintRGBA[2]==(base?selectedInk.b:0) && ink.tintRGBA[3]==(base?selectedInk.a:font.layers[1].color.a*selectedInk.a),
                "Explicit glyph ink failed exact selected RGB or original shadow alpha");}
        Check(defaultInk.sprites[inkStart+2].tintRGBA[2]==font.layers[0].color.b*selectedInk.b &&
            replacedInk.sprites[inkStart+2].tintRGBA[2]!=defaultInk.sprites[inkStart+2].tintRGBA[2],"Explicit ink still multiplies original Beige");
        auto text=v3->Background();v3->Text(text,902,L"A\uac00\ud7a3",536,369,98,17,MenuFrontEndTextAlign::Left,14,{1,1,1,1},"Shadow","Beige_Black_Alpha");
        Check(text.sprites.size()==v3->Background().sprites.size()+6,"Full-coverage source-style legend text failed");
        Reject([&]{auto copy=v3->Background();v3->GlyphRun(copy,0,{0xd800},0,0,clip,14);});
        Reject([&]{auto copy=v3->Background();v3->Text(copy,0,std::wstring(1,wchar_t(0xd800)),0,0,100,20,MenuFrontEndTextAlign::Left,14);});
        auto missing=v3->Background();const auto count=missing.sprites.size();v3->GlyphRun(missing,0,{0x10ffff},0,0,clip,14);
        Check(missing.sprites.size()==count+2,"Missing scalar fallback differs");
        const auto raw=Read(std::wstring(argv[1])+L"\\frontend.bin");std::size_t countOffset=0;const auto offsets=FontOffsets(raw,countOffset);
        Check(offsets.size()==7,"Sealed font count differs");
        auto malformed=raw;Word(malformed,countOffset,8);Reject([&]{MenuFrontEndAssets candidate;candidate.ReadBank(malformed,scene.textures.size());});
        malformed=raw;Word(malformed,offsets.back(),18);Reject([&]{MenuFrontEndAssets candidate;candidate.ReadBank(malformed,scene.textures.size());});
        malformed=raw;malformed[offsets.back()+8]='B';Reject([&]{MenuFrontEndAssets candidate;candidate.ReadBank(malformed,scene.textures.size());});
        malformed=raw;Word(malformed,offsets.back()+12+6+12,0);Reject([&]{MenuFrontEndAssets candidate;candidate.ReadBank(malformed,scene.textures.size());});
        malformed=raw;malformed.push_back(0);Reject([&]{MenuFrontEndAssets candidate;candidate.ReadBank(malformed,scene.textures.size());});
        auto legacy=Read(std::wstring(argv[3])+L"\\frontend.bin");std::size_t pos=8;const auto controls=U32(legacy,pos);
        for(unsigned n=0;n<controls;++n){pos+=36;for(unsigned k=0;k<2;++k){const auto length=U32(legacy,pos);pos+=length;}}
        pos+=4;Word(legacy,pos,14);Reject([&]{MenuFrontEndAssets candidate;candidate.ReadBank(legacy,v1->Background().textures.size());});
        std::printf("{\"status\":\"PASS_ORIGINAL_REPLAY_LEGEND_FONT_ASSETS_CXX14\",\"checks\":%u,\"glyphs\":17320,\"modern_hangul\":11172,\"texture_bank\":%zu,\"native_execution\":false,\"sdk_loaded\":false,\"host_or_sdk_or_window_executed\":false,\"gpu_execution\":false}\n",checks,scene.textures.size());return 0;
    }catch(const std::exception& error){std::fprintf(stderr,"%s\n",error.what());return 1;}
}
