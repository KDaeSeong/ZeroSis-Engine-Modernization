#pragma once
#include "../Presentation/BitmapRenderer.h"
#include "MenuFrontEndGridLayout.h"
#include <algorithm>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <fstream>
#include <functional>
#include <map>
#include <memory>
#include <limits>
#include <stdexcept>
#include <string>
#include <vector>

namespace ZeroSisHost {
enum class MenuFrontEndPage : std::uint32_t { Main=0,SinglePlayer=1,ExitConfirm=2 };
enum class MenuFrontEndTextAlign { Left,Center,Right };

// Original atlas sprites and GlyphGen data, sealed by menu_frontend_assets.py.
// Anchor/line metrics remain a source-derived candidate, not retail pixel proof.
class MenuFrontEndAssets final {
public:
    using Scene=ZeroSisPresentation::Scene;
    struct Control final {std::uint32_t page=0;std::uint64_t key=0,spriteKey=0;float x=0,y=0,width=0,height=0;std::string name,textKey;};
    struct Color final {float r,g,b,a;};
    struct Glyph final {int a,b,c,originX,originY,u,v,width,height;};
    struct Layer final {std::uint32_t texture=0;Color color{1,1,1,1};};
    struct Font final {int lineAdvance=0,baseline=0;float border=0;std::vector<Layer> layers;std::map<std::uint32_t,Glyph> glyphs;};
    struct NamedTexture final {std::uint32_t index=0,width=0,height=0;};
    struct InlineIcon final {std::uint32_t textureIndex=0;int u=0,v=0,width=0,height=0,advance=0,originx=0,originy=0;};
    struct StylePiece final {unsigned column=0,row=0;float source[4]{};};
    struct Style final {unsigned kind=0,texture=0;float width=0,height=0,stepX=0,stepY=0;std::vector<StylePiece> pieces;};
    struct OptionControl final {std::uint32_t key=0;float x=0,y=0,width=0,height=0;std::string textKey;};

    static std::shared_ptr<const MenuFrontEndAssets> Load(const std::wstring& directory){
        if(directory.empty())throw std::runtime_error("Original front-end asset directory is empty");
        auto result=std::make_shared<MenuFrontEndAssets>();std::wstring error;
        const wchar_t* names[]={L"background",L"MainMenu",L"SinglePlayer",L"ExitConfirm",L"hover"};
        Scene* scenes[]={&result->background_,&result->pages_[0],&result->pages_[1],&result->pages_[2],&result->hover_};
        for(std::size_t index=0;index<5;++index){
            if(!ZeroSisPresentation::LoadScenePacket(directory+L"\\"+names[index]+L".packet",scenes[index],&error))
                throw std::runtime_error("Cannot load original front-end scene packet");
            if(scenes[index]->width!=1920 || scenes[index]->height!=1080 || !scenes[index]->hits.empty() ||
               !scenes[index]->scrolls.empty() || !scenes[index]->pixelHits.indices.empty() || !scenes[index]->pixelHits.keys.empty())
                throw std::runtime_error("Original front-end packet has an invalid viewport or unowned input region");
        }
        for(auto* scene:scenes){
            if(scene->textures.size()!=result->background_.textures.size())throw std::runtime_error("Original front-end texture banks differ");
            for(std::size_t index=0;index<scene->textures.size();++index)
                if(scene->textures[index].path!=result->background_.textures[index].path)
                    throw std::runtime_error("Original front-end texture identities differ");
        }
        std::ifstream stream(directory+L"\\frontend.bin",std::ios::binary|std::ios::ate);
        if(!stream)throw std::runtime_error("Original front-end glyph bank is unavailable");
        const auto length=stream.tellg();if(length<=0 || length>8*1024*1024)throw std::runtime_error("Original front-end glyph bank exceeds its bound");
        std::vector<unsigned char> bytes(static_cast<std::size_t>(length));stream.seekg(0);
        if(!stream.read(reinterpret_cast<char*>(bytes.data()),static_cast<std::streamsize>(bytes.size())))
            throw std::runtime_error("Original front-end glyph bank read is incomplete");
        if(bytes.size()>=8 && !std::memcmp(bytes.data(),"ZSMFE002",8)){
            Scene extension;
            if(!ZeroSisPresentation::LoadScenePacket(directory+L"\\extension.packet",&extension,&error) ||
               !ZeroSisPresentation::LoadScenePacket(directory+L"\\options_chrome.packet",&result->optionsChrome_,&error))
                throw std::runtime_error("Cannot load original front-end extension packets");
            if(extension.width!=1920 || extension.height!=1080 || !extension.sprites.empty() || !extension.hits.empty() ||
               !extension.scrolls.empty() || !extension.pixelHits.indices.empty() || !extension.pixelHits.keys.empty() ||
               extension.textures.size()<result->background_.textures.size() || extension.textures.size()>64 ||
               result->optionsChrome_.width!=1920 || result->optionsChrome_.height!=1080 || !result->optionsChrome_.hits.empty() ||
               !result->optionsChrome_.scrolls.empty() || !result->optionsChrome_.pixelHits.indices.empty() || !result->optionsChrome_.pixelHits.keys.empty() ||
               result->optionsChrome_.textures.size()!=extension.textures.size())
                throw std::runtime_error("Invalid original front-end extension inventory");
            for(std::size_t i=0;i<extension.textures.size();++i){
                if(result->optionsChrome_.textures[i].path!=extension.textures[i].path ||
                   (i<result->background_.textures.size() && result->background_.textures[i].path!=extension.textures[i].path))
                    throw std::runtime_error("Original front-end extension changed the sealed V1 texture prefix");
            }
            for(auto* scene:scenes)scene->textures=extension.textures;
        }
        result->ReadBank(bytes,result->background_.textures.size());return result;
    }

    // Kept public for the SDK-free byte parser/scene fixture. Load() additionally
    // verifies the actual retained scene/texture bank before exposing the asset.
    void ReadBank(const std::vector<unsigned char>& bytes,std::size_t textureCount){
        const bool extended=bytes.size()>=8 && !std::memcmp(bytes.data(),"ZSMFE002",8);
        Reader reader(bytes);reader.Magic(extended?"ZSMFE002":"ZSMFE001");
        std::vector<Control> controls;std::map<unsigned,Font> fonts;std::map<std::string,Font> faces;
        const auto controlCount=reader.U32();if(controlCount<10 || controlCount>64 || !textureCount || textureCount>64)throw std::runtime_error("Invalid original front-end inventory bound");
        for(std::uint32_t index=0;index<controlCount;++index){
            Control row;row.page=reader.U32();row.key=reader.U64();row.spriteKey=reader.U64();row.x=reader.Float();row.y=reader.Float();
            row.width=reader.Float();row.height=reader.Float();row.name=reader.String();row.textKey=reader.String();
            if(row.page>2 || !row.spriteKey || row.name.empty() || row.width<=0 || row.height<=0 || row.x<0 || row.y<0 ||
               row.x+row.width>1920 || row.y+row.height>1080)throw std::runtime_error("Original front-end control escapes its viewport");
            for(const auto& prior:controls)if(prior.page==row.page && (prior.name==row.name || (row.key && prior.key==row.key)))
                throw std::runtime_error("Original front-end control identity is duplicated");
            controls.push_back(std::move(row));
        }
        const auto fontCount=reader.U32();
        if((!extended && fontCount!=3) || (extended && fontCount!=6 && fontCount!=7))
            throw std::runtime_error("Original front-end requires its exact font face inventory");
        for(unsigned index=0;index<fontCount;++index){
            const unsigned size=reader.U32();const auto style=extended?reader.String():std::string("Shadow");
            const auto face=FaceKey(size,style);Font font;font.lineAdvance=reader.I32();font.baseline=reader.I32();font.border=reader.Float();
            const auto layers=reader.U32(),glyphs=reader.U32();
            if((size!=14 && size!=18 && size!=20 && size!=22 && size!=24) || (!extended && (size==14 || size==18)) ||
               (size==14 && style!="Shadow") || faces.count(face) ||
               (style!="Base" && style!="Shadow" && style!="SoftShadow") || font.lineAdvance<=0 || font.lineAdvance>100 ||
               font.baseline<0 || font.baseline>100 || font.border<0 || font.border>16 || layers<1 || layers>3 || glyphs<100 || glyphs>100000)
                throw std::runtime_error("Original front-end font metrics are malformed");
            for(std::uint32_t n=0;n<layers;++n){
                Layer layer;layer.texture=reader.U32();layer.color={reader.Float(),reader.Float(),reader.Float(),reader.Float()};
                if(layer.texture>=textureCount || !ValidColor(layer.color))throw std::runtime_error("Original front-end font layer escapes its atlas bank");
                font.layers.push_back(layer);
            }
            for(std::uint32_t n=0;n<glyphs;++n){
                const auto cp=reader.U32();Glyph glyph{reader.I32(),reader.I32(),reader.I32(),reader.I32(),reader.I32(),reader.I32(),reader.I32(),reader.I32(),reader.I32()};
                if(cp>0x10ffff || (cp>=0xd800 && cp<=0xdfff) || font.glyphs.count(cp) || glyph.u<0 || glyph.v<0 ||
                   glyph.width<0 || glyph.height<0 || glyph.width>256 || glyph.height>256 || glyph.a< -256 || glyph.a>256 ||
                   glyph.b< -256 || glyph.b>256 || glyph.c< -256 || glyph.c>256 || glyph.originX< -256 || glyph.originX>256 || glyph.originY< -256 || glyph.originY>256)
                    throw std::runtime_error("Original front-end glyph is malformed");
                font.glyphs.emplace(cp,glyph);
            }
            if(style=="Shadow" && size!=18)fonts.emplace(size,font);
            faces.emplace(face,std::move(font));
        }
        std::map<std::string,NamedTexture> textures;std::map<std::string,Style> styles;
        std::map<std::string,InlineIcon> icons;std::map<std::string,OptionControl> optionControls;
        std::map<std::string,std::vector<Color>> colorSets;
        if(extended){
            if(faces.size()!=fontCount || !faces.count("18:Base") || !faces.count("18:Shadow") || !faces.count("20:Shadow") ||
               !faces.count("20:SoftShadow") || !faces.count("22:Shadow") || !faces.count("24:Shadow") ||
               (fontCount==7 && !faces.count("14:Shadow")))
                throw std::runtime_error("Original extended font faces differ");
            auto count=reader.U32();if(!count || count>64)throw std::runtime_error("Invalid named texture inventory");
            for(unsigned i=0;i<count;++i){auto name=reader.String();NamedTexture row{reader.U32(),reader.U32(),reader.U32()};
                if(name.empty() || textures.count(name) || row.index>=textureCount || !row.width || !row.height || row.width>8192 || row.height>8192)
                    throw std::runtime_error("Invalid named original texture");textures.emplace(std::move(name),row);}
            count=reader.U32();if(!count || count>64)throw std::runtime_error("Invalid original style inventory");
            for(unsigned i=0;i<count;++i){auto name=reader.String();Style row;row.kind=reader.U32();row.texture=reader.U32();
                row.width=reader.Float();row.height=reader.Float();row.stepX=reader.Float();row.stepY=reader.Float();const auto pieces=reader.U32();
                if(name.empty() || styles.count(name) || row.kind>3 || row.texture>=textureCount || !Bounds(0,0,row.width,row.height) ||
                   pieces<1 || pieces>9 || row.stepX<0 || row.stepY<0 || row.stepX>4096 || row.stepY>4096)
                    throw std::runtime_error("Invalid original style descriptor");
                for(unsigned n=0;n<pieces;++n){StylePiece piece;piece.column=reader.U32();piece.row=reader.U32();
                    for(auto& value:piece.source)value=reader.Float();
                    if(piece.column>2 || piece.row>2 || piece.source[0]<0 || piece.source[1]<0 ||
                       !Bounds(piece.source[0],piece.source[1],piece.source[2]-piece.source[0],piece.source[3]-piece.source[1]))
                        throw std::runtime_error("Invalid original style slice");
                    for(const auto& prior:row.pieces)if(prior.column==piece.column && prior.row==piece.row)
                        throw std::runtime_error("Duplicate original style slice");row.pieces.push_back(piece);}
                styles.emplace(std::move(name),std::move(row));
            }
            count=reader.U32();if(!count || count>1024)throw std::runtime_error("Invalid original inline icon inventory");
            for(unsigned i=0;i<count;++i){auto name=reader.String();InlineIcon row{reader.U32(),reader.I32(),reader.I32(),reader.I32(),reader.I32(),reader.I32(),reader.I32(),reader.I32()};
                if(name.compare(0,5,"ICON_") || icons.count(name) || row.textureIndex>=textureCount || row.u<0 || row.v<0 ||
                   row.width<=0 || row.height<=0 || row.width>256 || row.height>256 || row.advance<0 || row.advance>256 ||
                   row.originx< -256 || row.originx>256 || row.originy< -256 || row.originy>256)
                    throw std::runtime_error("Invalid original inline icon");icons.emplace(std::move(name),row);}
            count=reader.U32();if(count!=13)throw std::runtime_error("Original options control inventory differs");
            for(unsigned i=0;i<count;++i){auto name=reader.String();OptionControl row;row.key=reader.U32();row.x=reader.Float();row.y=reader.Float();
                row.width=reader.Float();row.height=reader.Float();row.textKey=reader.String();
                if(name.empty() || optionControls.count(name) || !row.key || !Bounds(row.x,row.y,row.width,row.height) ||
                   row.x<0 || row.y<0 || row.x+row.width>1920 || row.y+row.height>1080)
                    throw std::runtime_error("Invalid original options geometry");optionControls.emplace(std::move(name),row);}
            count=reader.U32();if(!count || count>1024)throw std::runtime_error("Invalid original color set inventory");
            for(unsigned i=0;i<count;++i){auto name=reader.String();auto layers=reader.U32();if(name.empty() || colorSets.count(name) || !layers || layers>8)
                    throw std::runtime_error("Invalid original color set");std::vector<Color> colors;
                for(unsigned n=0;n<layers;++n){Color color{reader.Float(),reader.Float(),reader.Float(),reader.Float()};
                    if(!ValidColor(color))throw std::runtime_error("Invalid original color layer");colors.push_back(color);}colorSets.emplace(std::move(name),std::move(colors));}
        }
        reader.End();controls_=std::move(controls);fonts_=std::move(fonts);faces_=std::move(faces);
        namedTextures_=std::move(textures);styles_=std::move(styles);icons_=std::move(icons);optionControls_=std::move(optionControls);colorSets_=std::move(colorSets);extended_=extended;
    }

    Scene Background()const{return background_;}
    Scene Page(MenuFrontEndPage page)const{
        const auto index=static_cast<std::uint32_t>(page);if(index>2)throw std::runtime_error("Unknown original front-end page");return pages_[index];
    }
    const std::vector<Control>& Controls()const{return controls_;}
    const std::map<unsigned,Font>& Fonts()const{return fonts_;}
    bool Extended()const noexcept{return extended_;}
    const Font& FontFace(unsigned size,const std::string& style="Shadow")const{
        const auto found=faces_.find(FaceKey(size,style));if(found==faces_.end())throw std::runtime_error("Original font face is unavailable");return found->second;
    }
    bool HasFontFace(unsigned size,const std::string& style="Shadow")const{return faces_.count(FaceKey(size,style))!=0;}
    const std::map<std::string,InlineIcon>& Icons()const noexcept{return icons_;}
    const InlineIcon& Icon(const std::string& name)const{return icons_.at(name);}
    const NamedTexture& TextureNamed(const std::string& basename)const{
        auto name=basename;for(auto& c:name)if(c>='A' && c<='Z')c=static_cast<char>(c-'A'+'a');return namedTextures_.at(name);
    }
    bool HasTextureNamed(const std::string& basename)const{
        auto name=basename;for(auto& c:name)if(c>='A' && c<='Z')c=static_cast<char>(c-'A'+'a');return namedTextures_.count(name)!=0;
    }
    const OptionControl& OptionsControl(const std::string& name)const{return optionControls_.at(name);}
    const std::vector<Color>& ColorSet(const std::string& name)const{return colorSets_.at(name);}
    Scene OptionsChrome()const{
        if(!extended_)throw std::runtime_error("Original options assets are unavailable");auto scene=Background();
        scene.sprites.insert(scene.sprites.end(),optionsChrome_.sprites.begin(),optionsChrome_.sprites.end());return scene;
    }
    static bool Enabled(MenuFrontEndPage page,std::uint64_t key,bool hasCurrentSetup,bool hasOptions=false){
        return page==MenuFrontEndPage::Main?(key==1 || key==3 || (key==4 && hasOptions)):
            page==MenuFrontEndPage::SinglePlayer?(key==11 || (key==10 && hasCurrentSetup)):(key==20 || key==21);
    }
    Scene BuildPage(MenuFrontEndPage page,bool hasCurrentSetup,std::uint64_t hovered,
                    const std::function<std::wstring(const std::string&)>& labels,const std::wstring& startLabel,bool hasOptions=false)const{
        auto scene=Page(page);
        for(const auto& control:controls_){
            if(control.page!=static_cast<std::uint32_t>(page))continue;
            const bool enabled=Enabled(page,control.key,hasCurrentSetup,hasOptions && extended_);
            if(!enabled)Rect(scene,0,control.x,control.y,control.width,control.height,{0,0,0,0.42f});
            else{
                scene.hits.push_back({control.key,{control.x,control.y,control.x+control.width,control.y+control.height}});
                if(hovered==control.key && page!=MenuFrontEndPage::ExitConfirm)Hover(scene,control.key,control.x,control.y,control.width,control.height);
            }
            const auto label=page==MenuFrontEndPage::SinglePlayer && control.key==10?startLabel:
                control.textKey.empty()?std::wstring():labels(control.textKey);
            if(!label.empty())Text(scene,control.key,label,control.x,control.y,control.width,control.height,
                MenuFrontEndTextAlign::Center,page==MenuFrontEndPage::ExitConfirm?24:22,{1,1,1,enabled?1.0f:0.4f});
        }
        return scene;
    }

    void Rect(Scene& scene,std::uint64_t key,float x,float y,float width,float height,Color color)const{
        if(!Bounds(x,y,width,height) || !ValidColor(color))throw std::runtime_error("Invalid front-end rectangle");
        ZeroSisPresentation::Sprite sprite{};sprite.controlKey=key;sprite.textureIndex=ZeroSisPresentation::kSolidRectangleTexture;
        Set(sprite.sourceRect,0,0,1,1);Set(sprite.targetRect,x,y,x+width,y+height);Set(sprite.clipRect,0,0,1920,1080);
        Set(sprite.tintRGBA,color.r,color.g,color.b,color.a);scene.sprites.push_back(sprite);
    }
    void Texture(Scene& scene,std::uint64_t key,std::uint32_t texture,const float source[4],const float target[4],Color color={1,1,1,1})const{
        if(texture>=scene.textures.size() || !ValidColor(color) || !Bounds(source[0],source[1],source[2]-source[0],source[3]-source[1]) ||
           !Bounds(target[0],target[1],target[2]-target[0],target[3]-target[1]))throw std::runtime_error("Invalid front-end texture bank index or bounds");
        ZeroSisPresentation::Sprite sprite{};sprite.controlKey=key;sprite.textureIndex=texture;
        std::copy(source,source+4,sprite.sourceRect);std::copy(target,target+4,sprite.targetRect);Set(sprite.clipRect,0,0,1920,1080);
        Set(sprite.tintRGBA,color.r,color.g,color.b,color.a);scene.sprites.push_back(sprite);
    }
    void Grid(Scene& scene,std::uint64_t key,const std::string& sourceStyle,float x,float y,float width,float height,unsigned state=0)const{
        if(!Bounds(x,y,width,height) || state>3)throw std::runtime_error("Invalid original style request");const auto& style=styles_.at(sourceStyle);
        const auto targets=BuildMenuFrontEndGridLayout(style.kind,style.pieces,x,y,width,height);std::size_t index=0;
        for(const auto& piece:style.pieces){float source[4]={piece.source[0]+state*style.stepX,piece.source[1]+state*style.stepY,
                piece.source[2]+state*style.stepX,piece.source[3]+state*style.stepY};
            const auto& target=targets[index++];
            if(target[2]>target[0] && target[3]>target[1])Texture(scene,key,style.texture,source,target.data());
        }
        if(sourceStyle=="GenericPullDown"){
            const auto& arrow=TextureNamed("corner16.dds");const float source[]={0.0f,state==1?16.0f:0.0f,16.0f,state==1?32.0f:16.0f};
            const float target[]={x+width-19,y+height-19,x+width-3,y+height-3};Texture(scene,key,arrow.index,source,target);
        }
    }
    void StyleButton(Scene& scene,std::uint64_t key,const std::string& sourceStyle,float x,float y,float width,float height,
        const std::wstring& label,bool enabled=true,bool hovered=false)const{
        Grid(scene,key,sourceStyle,x,y,width,height,enabled?(hovered?1:0):3);
        if(!enabled)Rect(scene,0,x,y,width,height,{0,0,0,.4f});
        if(!label.empty())Text(scene,key,label,x,y,width,height,MenuFrontEndTextAlign::Center,height<=32?18:22,{1,1,1,enabled?1.0f:.4f});
        if(enabled)scene.hits.push_back({key,{x,y,x+width,y+height}});
    }
    void GlyphRun(Scene& scene,std::uint64_t key,const std::vector<std::uint32_t>& scalars,float penX,float baselineY,const float clip[4],
        unsigned fontPx,const std::string& style="Shadow",Color tint={1,1,1,1},bool replaceBaseInk=false)const{
        const auto& font=FontFace(fontPx,style);
        if(!std::isfinite(penX) || !std::isfinite(baselineY) || !Bounds(clip[0],clip[1],clip[2]-clip[0],clip[3]-clip[1]) || !ValidColor(tint) ||
           scalars.size()>100000)throw std::runtime_error("Invalid original glyph run");
        for(const auto cp:scalars)if(cp>0x10ffff || (cp>=0xd800 && cp<=0xdfff))throw std::runtime_error("Invalid Unicode scalar in original glyph run");
        for(auto layer=font.layers.rbegin();layer!=font.layers.rend();++layer){float pen=penX;
            for(const auto cp:scalars){auto found=font.glyphs.find(cp);if(found==font.glyphs.end())found=font.glyphs.find('?');
                if(found==font.glyphs.end())throw std::runtime_error("Original glyph fallback is absent");const auto& glyph=found->second;
                if(glyph.width>0 && glyph.height>0){ZeroSisPresentation::Sprite sprite{};sprite.controlKey=key;sprite.textureIndex=layer->texture;
                    Set(sprite.sourceRect,float(glyph.u),float(glyph.v),float(glyph.u+glyph.width),float(glyph.v+glyph.height));
                    const float dx=pen+glyph.a+glyph.originX-font.border,dy=baselineY-glyph.originY-font.border;
                    Set(sprite.targetRect,dx,dy,dx+glyph.width,dy+glyph.height);std::copy(clip,clip+4,sprite.clipRect);
                    if(replaceBaseInk){
                        const auto ink=&*layer==&font.layers.front()?tint:layer->color;
                        Set(sprite.tintRGBA,ink.r,ink.g,ink.b,layer->color.a*tint.a);
                    }else Set(sprite.tintRGBA,layer->color.r*tint.r,layer->color.g*tint.g,layer->color.b*tint.b,layer->color.a*tint.a);
                    scene.sprites.push_back(sprite);}
                pen+=glyph.a+glyph.b+glyph.c;}
        }
    }
    void DrawInlineIcon(Scene& scene,std::uint64_t key,const std::string& name,float penX,float baselineY,const float clip[4],Color tint={1,1,1,1})const{
        const auto& icon=Icon(name);
        if(!std::isfinite(penX) || !std::isfinite(baselineY) || !Bounds(clip[0],clip[1],clip[2]-clip[0],clip[3]-clip[1]) || !ValidColor(tint))
            throw std::runtime_error("Invalid original inline icon request");
        ZeroSisPresentation::Sprite sprite{};sprite.controlKey=key;sprite.textureIndex=icon.textureIndex;
        Set(sprite.sourceRect,float(icon.u),float(icon.v),float(icon.u+icon.width),float(icon.v+icon.height));
        const float dx=penX+icon.originx,dy=baselineY-icon.originy;Set(sprite.targetRect,dx,dy,dx+icon.width,dy+icon.height);
        std::copy(clip,clip+4,sprite.clipRect);Set(sprite.tintRGBA,tint.r,tint.g,tint.b,tint.a);scene.sprites.push_back(sprite);
    }
    void Hover(Scene& scene,std::uint64_t key,float x,float y,float width,float height)const{
        for(auto sprite:hover_.sprites){
            sprite.controlKey=key;
            sprite.targetRect[0]=x+sprite.targetRect[0]*width/320;sprite.targetRect[2]=x+sprite.targetRect[2]*width/320;
            sprite.targetRect[1]=y+sprite.targetRect[1]*height/45;sprite.targetRect[3]=y+sprite.targetRect[3]*height/45;
            scene.sprites.push_back(sprite);
        }
    }
    void Button(Scene& scene,std::uint64_t key,float x,float y,float width,float height,const std::wstring& label,bool enabled=true,bool hovered=false)const{
        // ZoomButton's nine-slice already exists in original page packets. Extra
        // results/replay controls reuse the same source button sprite group.
        const auto& main=pages_[0];const auto& control=Find(MenuFrontEndPage::Main,"SinglePlayerButton");
        for(auto sprite:main.sprites){
            if(sprite.controlKey!=control.spriteKey)continue;
            sprite.controlKey=key;
            sprite.targetRect[0]=x+(sprite.targetRect[0]-control.x)*width/control.width;
            sprite.targetRect[2]=x+(sprite.targetRect[2]-control.x)*width/control.width;
            sprite.targetRect[1]=y+(sprite.targetRect[1]-control.y)*height/control.height;
            sprite.targetRect[3]=y+(sprite.targetRect[3]-control.y)*height/control.height;
            scene.sprites.push_back(sprite);
        }
        if(enabled && hovered)Hover(scene,key,x,y,width,height);
        Text(scene,key,label,x,y,width,height,MenuFrontEndTextAlign::Center,22,{1,1,1,enabled?1.0f:0.38f});
        if(enabled)scene.hits.push_back({key,{x,y,x+width,y+height}});
    }
    const Control& Find(MenuFrontEndPage page,const std::string& name)const{
        for(const auto& row:controls_)if(row.page==static_cast<std::uint32_t>(page) && row.name==name)return row;
        throw std::runtime_error("Original front-end control is unavailable");
    }
    void Text(Scene& scene,std::uint64_t key,const std::wstring& text,float x,float y,float width,float height,
              MenuFrontEndTextAlign align=MenuFrontEndTextAlign::Left,unsigned fontPx=22,Color tint={1,1,1,1},
              const std::string& style="Shadow",const std::string& colorSet="")const{
        const auto found=faces_.find(FaceKey(fontPx,style));if(found==faces_.end() || !ValidColor(tint) || !Bounds(x,y,width,height))
            throw std::runtime_error("Invalid original front-end text request");
        const auto& font=found->second;const auto* colors=colorSet.empty()?nullptr:&ColorSet(colorSet);
        std::vector<std::vector<std::uint32_t>> lines(1);float advance=0;
        for(std::size_t index=0;index<text.size();++index){
            std::uint32_t cp=static_cast<std::uint32_t>(text[index]);
            if(cp>=0xd800 && cp<=0xdbff){
                if(index+1>=text.size())throw std::runtime_error("Unpaired UTF-16 front-end text");
                const auto low=static_cast<std::uint32_t>(text[++index]);if(low<0xdc00 || low>0xdfff)throw std::runtime_error("Unpaired UTF-16 front-end text");
                cp=0x10000+((cp-0xd800)<<10)+(low-0xdc00);
            }else if(cp>=0xdc00 && cp<=0xdfff)throw std::runtime_error("Unpaired UTF-16 front-end text");
            if(cp=='\r' || cp=='\n'){
                if(cp=='\r' && index+1<text.size() && text[index+1]=='\n')++index;
                lines.emplace_back();advance=0;continue;
            }
            auto glyph=font.glyphs.find(cp);if(glyph==font.glyphs.end()){cp='?';glyph=font.glyphs.find(cp);}
            if(glyph==font.glyphs.end())throw std::runtime_error("Original front-end font fallback is absent");
            const float next=static_cast<float>(glyph->second.a+glyph->second.b+glyph->second.c);
            if(advance+next>width && !lines.back().empty()){lines.emplace_back();advance=0;}
            lines.back().push_back(cp);advance+=next;
        }
        const float firstY=y+(std::max)(0.0f,(height-lines.size()*font.lineAdvance)/2);
        for(std::size_t line=0;line<lines.size();++line){
            float lineWidth=0;for(auto cp:lines[line]){const auto& glyph=font.glyphs.at(cp);lineWidth+=glyph.a+glyph.b+glyph.c;}
            const float firstX=x+(align==MenuFrontEndTextAlign::Center?(width-lineWidth)/2:align==MenuFrontEndTextAlign::Right?width-lineWidth:0);
            for(auto layer=font.layers.rbegin();layer!=font.layers.rend();++layer){
                float pen=firstX;
                for(auto cp:lines[line]){
                    const auto& glyph=font.glyphs.at(cp);
                    if(glyph.width>0 && glyph.height>0){
                        ZeroSisPresentation::Sprite sprite{};sprite.controlKey=key;sprite.textureIndex=layer->texture;
                        Set(sprite.sourceRect,float(glyph.u),float(glyph.v),float(glyph.u+glyph.width),float(glyph.v+glyph.height));
                        const float drawX=pen+glyph.a+glyph.originX-font.border;
                        const float drawY=firstY+line*font.lineAdvance+font.baseline-glyph.originY-font.border;
                        Set(sprite.targetRect,drawX,drawY,drawX+glyph.width,drawY+glyph.height);Set(sprite.clipRect,x,y,x+width,y+height);
                        const auto layerIndex=static_cast<std::size_t>(font.layers.rend()-layer-1);
                        const auto ink=colors?(*colors)[(std::min)(layerIndex,colors->size()-1)]:layer->color;
                        Set(sprite.tintRGBA,ink.r*tint.r,ink.g*tint.g,ink.b*tint.b,ink.a*tint.a);
                        scene.sprites.push_back(sprite);
                    }
                    pen+=glyph.a+glyph.b+glyph.c;
                }
            }
        }
    }

private:
    class Reader final {
        const std::vector<unsigned char>& data_;std::size_t cursor_=0;
    public:
        explicit Reader(const std::vector<unsigned char>& data):data_(data){}
        void Magic(const char* text){if(data_.size()<8 || std::memcmp(data_.data(),text,8))throw std::runtime_error("Unknown original front-end asset format");cursor_=8;}
        std::uint32_t U32(){if(data_.size()-cursor_<4)throw std::runtime_error("Truncated original front-end asset");std::uint32_t value;std::memcpy(&value,data_.data()+cursor_,4);cursor_+=4;return value;}
        std::uint64_t U64(){const auto low=U32();return low|(std::uint64_t(U32())<<32);}
        int I32(){return static_cast<std::int32_t>(U32());}
        float Float(){const auto raw=U32();float value;std::memcpy(&value,&raw,4);if(!std::isfinite(value))throw std::runtime_error("Nonfinite original front-end asset geometry");return value;}
        std::string String(){const auto size=U32();if(size>512 || size>data_.size()-cursor_)throw std::runtime_error("Invalid original front-end text key");std::string value(reinterpret_cast<const char*>(data_.data()+cursor_),size);cursor_+=size;if(value.find('\0')!=std::string::npos)throw std::runtime_error("Embedded zero in original front-end key");return value;}
        void End(){if(cursor_!=data_.size())throw std::runtime_error("Original front-end asset has trailing bytes");}
    };
    static bool ValidColor(Color value){return std::isfinite(value.r)&&std::isfinite(value.g)&&std::isfinite(value.b)&&std::isfinite(value.a)&&value.r>=0&&value.r<=1&&value.g>=0&&value.g<=1&&value.b>=0&&value.b<=1&&value.a>=0&&value.a<=1;}
    static std::string FaceKey(unsigned size,const std::string& style){return std::to_string(size)+":"+style;}
    static bool Bounds(float x,float y,float w,float h){return std::isfinite(x)&&std::isfinite(y)&&std::isfinite(w)&&std::isfinite(h)&&w>0&&h>0&&std::abs(x)<100000&&std::abs(y)<100000&&w<100000&&h<100000;}
    static void Set(float* values,float a,float b,float c,float d){values[0]=a;values[1]=b;values[2]=c;values[3]=d;}
    Scene background_{},pages_[3]{},hover_{},optionsChrome_{};std::vector<Control> controls_;std::map<unsigned,Font> fonts_;
    std::map<std::string,Font> faces_;std::map<std::string,NamedTexture> namedTextures_;std::map<std::string,Style> styles_;
    std::map<std::string,InlineIcon> icons_;std::map<std::string,OptionControl> optionControls_;
    std::map<std::string,std::vector<Color>> colorSets_;bool extended_=false;
};
}
