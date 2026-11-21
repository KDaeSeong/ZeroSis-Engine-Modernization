#pragma once
#include "MenuReplayData.h"
#include "MenuFrontEndAssets.h"

namespace ZeroSisHost {
using MenuReplayTextColor=MenuFrontEndAssets::Color;
struct MenuReplayTextIcon final {
    std::uint32_t textureIndex=0;int u=0,v=0,width=0,height=0,advance=0,originx=0,originy=0;
};
struct MenuReplayTextCatalog final {
    std::map<std::string,MenuReplayTextColor> colors;
    std::map<std::string,MenuReplayTextIcon> icons;
    // Exact ColorAtlas.xml Gray_Chat; the original Lua leaves NO_PLAYER here.
    MenuReplayTextColor defaultColor{200.0f/255,200.0f/255,150.0f/255,1};
};
struct MenuReplayMessageInk final {MenuReplayTextColor color;bool contrastOverlay=false;};
inline MenuReplayMessageInk OriginalReplayMessageInk(int player,const std::vector<MenuReplayTextColor>& primary,
    const std::vector<MenuReplayTextColor>& secondary,MenuReplayTextColor defaultColor){
    auto selected=defaultColor;
    if(player>=0){
        if(static_cast<std::size_t>(player)<primary.size() && static_cast<std::size_t>(player)<secondary.size()){
            selected=secondary[static_cast<std::size_t>(player)];
            if((selected.r==1 && selected.g==1 && selected.b==1) || (selected.r==0 && selected.g==0 && selected.b==0))
                selected=primary[static_cast<std::size_t>(player)];
        }else selected={1,1,200.0f/255,1};
    }
    selected.a=1;
    const float light=((std::max)({selected.r,selected.g,selected.b})+(std::min)({selected.r,selected.g,selected.b}))/2;
    return {selected,player>=0 && light<.4f};
}

class MenuReplayRichText final {
public:
    enum class Kind { Text,Icon,Newline,Style,Tab };
    struct Run final {
        Kind kind=Kind::Text;std::uint32_t begin=0,end=0;bool prefix=false,explicitColor=false;
        MenuReplayTextColor color{1,1,1,1};std::string icon;
    };
    struct Atom final {
        Kind kind=Kind::Text;std::uint32_t run=0,begin=0,end=0,scalar=0;
    };
    struct SourceSpan final {
        const char* bytes=nullptr;std::size_t count=0;
        const char* data() const noexcept{return bytes;}
        std::size_t size() const noexcept{return count;}
    };
    MenuReplayRichText(const std::string& source,int turn,const MenuReplayTextCatalog& catalog,MenuReplayTextColor base)
        :original_(source),prefix_(std::to_string(turn)+" - "){
        if(source.size()>1024u*1024u || !MenuReplayReadDetail::Utf8(source))
            throw std::invalid_argument("Replay paragraph is outside its original UTF-8 source bound");
        Add(Kind::Text,0,prefix_.size(),true,base,false);
        // Pair color markers first. Unmatched and over-depth markers remain
        // literal, so a malformed message cannot silently lose source text.
        struct Token final {std::size_t begin=0,end=0;Kind kind=Kind::Text;bool push=false,pop=false,paired=false;std::size_t depth=0;MenuReplayTextColor color{};std::string icon;};
        std::vector<Token> tokens;std::vector<std::size_t> open;
        std::size_t at=0;
        while(at<original_.size()){
            if(original_[at]!='['){++at;continue;}
            const auto limit=(std::min)(original_.size(),at+257);std::size_t close=at+1;
            while(close<limit && original_[close]!=']' && original_[close]!='[')++close;
            if(close==limit || original_[close]=='['){at=close;continue;}
            const auto name=original_.substr(at+1,close-at-1);Token token;token.begin=at;token.end=close+1;
            if(name=="ENDCOLOR" || name=="/COLOR"){
                token.pop=true;token.kind=Kind::Style;
                if(!open.empty()){auto& start=tokens[open.back()];open.pop_back();token.paired=start.paired=start.depth<16;}
            }else if(name=="NEWLINE")token.kind=Kind::Newline;
            else if(name=="TAB")token.kind=Kind::Tab;
            else if(name.compare(0,6,"COLOR_")==0){const auto found=catalog.colors.find(name);
                if(found!=catalog.colors.end()){token.push=true;token.kind=Kind::Style;token.color=found->second;}}
            else if(name.compare(0,6,"COLOR:")==0 && NumericColor(name,token.color)){token.push=true;token.kind=Kind::Style;}
            const auto iconName=name=="BULLET"?std::string("ICON_BULLET"):name;
            if(token.kind==Kind::Text && catalog.icons.count(iconName)){token.kind=Kind::Icon;token.icon=iconName;}
            if(token.push){token.depth=open.size();open.push_back(tokens.size());}
            tokens.push_back(std::move(token));at=close+1;
        }
        unclosedColors_=open.size();std::vector<MenuReplayTextColor> colors;
        std::size_t start=0;
        auto flush=[&](std::size_t end){if(end>start)Add(Kind::Text,start,end,false,colors.empty()?base:colors.back(),!colors.empty());};
        for(const auto& token:tokens){
            if(token.kind==Kind::Text || (token.kind==Kind::Style && !token.paired)){++unsupportedTokens_;continue;}
            flush(token.begin);
            Add(token.kind,token.begin,token.end,false,colors.empty()?base:colors.back(),!colors.empty(),token.icon);
            if(token.push)colors.push_back(token.color);else if(token.pop)colors.pop_back();
            start=token.end;
        }
        flush(original_.size());ExpandAtoms();
    }
    const std::string& Original() const noexcept{return original_;}
    const std::string& Prefix() const noexcept{return prefix_;}
    const std::vector<Run>& Runs() const noexcept{return runs_;}
    const std::vector<Atom>& Atoms() const noexcept{return atoms_;}
    std::size_t UnsupportedTokens() const noexcept{return unsupportedTokens_;}
    std::size_t UnclosedColors() const noexcept{return unclosedColors_;}
    SourceSpan Source(const Run& run) const {
        const auto& raw=run.prefix?prefix_:original_;
        if(run.begin>run.end || run.end>raw.size())throw std::out_of_range("Replay source span escaped its owned text");
        return {raw.data()+run.begin,static_cast<std::size_t>(run.end-run.begin)};
    }
private:
    static bool NumericColor(const std::string& name,MenuReplayTextColor& value){
        unsigned channels[4]{};std::size_t at=6;
        for(unsigned part=0;part<4;++part){if(at>=name.size())return false;unsigned number=0,digits=0;
            while(at<name.size() && name[at]>='0' && name[at]<='9'){
                number=number*10+static_cast<unsigned>(name[at++]-'0');if(++digits>3 || number>255)return false;}
            if(!digits)return false;channels[part]=number;
            if(part<3){if(at>=name.size() || name[at++]!=':')return false;}else if(at!=name.size())return false;}
        value={channels[0]/255.0f,channels[1]/255.0f,channels[2]/255.0f,channels[3]/255.0f};return true;
    }
    void Add(Kind kind,std::size_t begin,std::size_t end,bool prefix,MenuReplayTextColor color,bool explicitColor,const std::string& icon={}){
        if(end<=begin)return;
        runs_.push_back({kind,static_cast<std::uint32_t>(begin),static_cast<std::uint32_t>(end),prefix,explicitColor,color,icon});
    }
    static std::uint32_t Scalar(const std::string& text,std::size_t& at){
        const auto first=static_cast<unsigned char>(text[at++]);std::uint32_t scalar=first;unsigned count=0;
        if(first>=0xf0){scalar=first&7u;count=3;}else if(first>=0xe0){scalar=first&15u;count=2;}else if(first>=0xc0){scalar=first&31u;count=1;}
        for(unsigned i=0;i<count;++i)scalar=(scalar<<6)|(static_cast<unsigned char>(text[at++])&63u);return scalar;
    }
    void ExpandAtoms(){
        for(std::size_t index=0;index<runs_.size();++index){const auto& run=runs_[index];if(run.kind==Kind::Style)continue;
            if(run.kind!=Kind::Text){atoms_.push_back({run.kind,static_cast<std::uint32_t>(index),run.begin,run.end,0});continue;}
            const auto& text=run.prefix?prefix_:original_;std::size_t at=run.begin;
            while(at<run.end){const auto begin=at;const auto scalar=Scalar(text,at);Kind kind=Kind::Text;
                if(scalar=='\r'){if(at<run.end && text[at]=='\n')++at;kind=Kind::Newline;}
                else if(scalar=='\n')kind=Kind::Newline;else if(scalar=='\t')kind=Kind::Tab;
                atoms_.push_back({kind,static_cast<std::uint32_t>(index),static_cast<std::uint32_t>(begin),static_cast<std::uint32_t>(at),scalar});}
        }
    }
    std::string original_,prefix_;std::vector<Run> runs_;std::vector<Atom> atoms_;std::size_t unsupportedTokens_=0,unclosedColors_=0;
};

class MenuReplayParagraphLayout final {
public:
    using Font=MenuFrontEndAssets::Font;using Kind=MenuReplayRichText::Kind;
    struct Line final {std::size_t first=0,last=0;float width=0,ascent=0,height=0;bool emergencyWrap=false;};
    struct Placement final {Kind kind=Kind::Text;std::uint32_t scalar=0;float x=0,baseline=0;std::size_t atom=0;};
    MenuReplayParagraphLayout(const MenuReplayRichText& text,const Font& face,const MenuReplayTextCatalog& catalog,float width)
        :text_(text),face_(face),catalog_(catalog){
        if(!std::isfinite(width) || width<=0 || face.lineAdvance<=0 || face.baseline<0 || !face.glyphs.count('?'))
            throw std::invalid_argument("Replay paragraph requires bounded original glyph metrics");
        const auto& atoms=text.Atoms();std::size_t first=0;
        while(first<atoms.size()){
            std::size_t at=first,lastWord=first;float pen=0,widthAtWord=0;bool hard=false;
            while(at<atoms.size()){
                if(atoms[at].kind==Kind::Newline){hard=true;break;}
                const float advance=Advance(atoms[at]);
                if(at>first && (pen+advance>width || at-first>=4096))break;
                pen+=advance;++at;
                if(atoms[at-1].kind==Kind::Tab || atoms[at-1].scalar==' ' || atoms[at-1].scalar==0x3000){lastWord=at;widthAtWord=pen;}
            }
            const bool emergency=at-first>=4096;
            if(!hard && at<atoms.size() && lastWord>first && !emergency){at=lastWord;pen=widthAtWord;}
            if(at==first && !hard){++at;pen=Advance(atoms[first]);}
            Line line{first,at,pen,static_cast<float>(face.baseline),static_cast<float>(face.lineAdvance),emergency};
            float below=static_cast<float>(face.lineAdvance-face.baseline);
            for(auto i=first;i<at;++i){float above=0,under=0;
                if(atoms[i].kind==Kind::Icon){const auto& icon=catalog.icons.at(text.Runs()[atoms[i].run].icon);
                    above=static_cast<float>(icon.originy);under=static_cast<float>(icon.height-icon.originy);}
                else if(atoms[i].kind==Kind::Text){const auto& glyph=Glyph(atoms[i].scalar);if(glyph.width && glyph.height){
                    above=glyph.originY+face.border;under=glyph.height-glyph.originY-face.border;}}
                line.ascent=(std::max)(line.ascent,above);below=(std::max)(below,under);}
            line.height=(std::max)(line.height,line.ascent+below);lines_.push_back(line);
            first=hard?at+1:at;
            if(hard && first==atoms.size())lines_.push_back({first,first,0,float(face.baseline),float(face.lineAdvance),false});
        }
    }
    const std::vector<Line>& Lines() const noexcept{return lines_;}
    std::vector<Placement> Place(std::size_t lineIndex,float x,float top) const {
        const auto& line=lines_.at(lineIndex);std::vector<Placement> result;float pen=x;
        for(auto i=line.first;i<line.last;++i){const auto& atom=text_.Atoms()[i];
            if(atom.kind==Kind::Text)result.push_back({Kind::Text,face_.glyphs.count(atom.scalar)?atom.scalar:std::uint32_t('?'),pen,top+line.ascent,i});
            else if(atom.kind==Kind::Icon)result.push_back({Kind::Icon,0,pen,top+line.ascent,i});
            pen+=Advance(atom);}
        return result;
    }
private:
    const MenuFrontEndAssets::Glyph& Glyph(std::uint32_t scalar) const {const auto found=face_.glyphs.find(scalar);return found==face_.glyphs.end()?face_.glyphs.at('?'):found->second;}
    float Advance(const MenuReplayRichText::Atom& atom) const {
        if(atom.kind==Kind::Icon)return static_cast<float>(catalog_.icons.at(text_.Runs()[atom.run].icon).advance);
        if(atom.kind==Kind::Tab){const auto& space=Glyph(' ');return static_cast<float>(4*(space.a+space.b+space.c));}
        if(atom.kind==Kind::Newline)return 0;const auto& glyph=Glyph(atom.scalar);return static_cast<float>(glyph.a+glyph.b+glyph.c);
    }
    const MenuReplayRichText& text_;const Font& face_;const MenuReplayTextCatalog& catalog_;std::vector<Line> lines_;
};

class MenuReplayMessagePages final {
public:
    struct Paragraph final {
        std::size_t messageIndex=0;MenuReplayMessageInk ink;MenuReplayRichText text;MenuReplayParagraphLayout layout;
        Paragraph(const Paragraph&)=delete;Paragraph& operator=(const Paragraph&)=delete;
        Paragraph(Paragraph&&)=delete;Paragraph& operator=(Paragraph&&)=delete;
        Paragraph(std::size_t index,const MenuReplayMessage& source,const MenuFrontEndAssets::Font& font,
            const MenuReplayTextCatalog& catalog,MenuReplayMessageInk color,float width)
            :messageIndex(index),ink(color),text(source.text,source.turn,catalog,color.color),layout(text,font,catalog,width){}
    };
    struct Row final {std::size_t paragraph=0,line=0;float before=0,height=0,after=0;};
    MenuReplayMessagePages(const MenuReplayMessagePages&)=delete;MenuReplayMessagePages& operator=(const MenuReplayMessagePages&)=delete;
    MenuReplayMessagePages(MenuReplayMessagePages&&)=delete;MenuReplayMessagePages& operator=(MenuReplayMessagePages&&)=delete;
    MenuReplayMessagePages(const MenuReplayDocument& document,const MenuFrontEndAssets::Font& font,
        const MenuReplayTextCatalog& catalog,const std::vector<MenuReplayTextColor>& primary,
        const std::vector<MenuReplayTextColor>& secondary,float width=890,float pageHeight=405,std::size_t pageAtomBudget=32768)
        :font_(font),catalog_(catalog),pageHeight_(pageHeight){
        if(!std::isfinite(pageHeight) || pageHeight<=0)throw std::invalid_argument("Replay message viewport is invalid");
        if(!pageAtomBudget || pageAtomBudget>32768)throw std::invalid_argument("Replay message page atom bound is invalid");
        paragraphs_.reserve(document.messages.size());
        // Original ReplayViewer loops ipairs(Messages); it does not re-sort text.
        for(std::size_t index=0;index<document.messages.size();++index){const auto& message=document.messages[index];if(message.text.empty())continue;
            auto paragraph=std::make_unique<Paragraph>(index,message,font_,catalog_,OriginalReplayMessageInk(message.player,primary,secondary,catalog_.defaultColor),width);
            const auto paragraphIndex=paragraphs_.size();const auto& lines=paragraph->layout.Lines();
            for(std::size_t line=0;line<lines.size();++line)rows_.push_back({paragraphIndex,line,line?0.0f:5.0f,lines[line].height,line+1==lines.size()?6.0f:0.0f});
            paragraphs_.push_back(std::move(paragraph));}
        starts_.push_back(0);float used=0;std::size_t atomsUsed=0;
        for(std::size_t row=0;row<rows_.size();++row){const auto height=rows_[row].before+rows_[row].height+rows_[row].after;
            const auto& line=Block(rows_[row].paragraph).layout.Lines()[rows_[row].line];const auto atoms=line.last-line.first;
            if(height>pageHeight || atoms>pageAtomBudget)throw std::invalid_argument("Replay line exceeds its bounded page");
            if(used>0 && (used+height>pageHeight || atomsUsed+atoms>pageAtomBudget)){starts_.push_back(row);used=0;atomsUsed=0;}
            used+=height;atomsUsed+=atoms;}
    }
    std::size_t PageCount() const noexcept{return starts_.size();}
    std::size_t FirstRow(std::size_t page) const{return starts_.at(page);}
    std::size_t LastRow(std::size_t page) const{return page+1<starts_.size()?starts_[page+1]:rows_.size();}
    const std::vector<Row>& Rows() const noexcept{return rows_;}
    const Paragraph& Block(std::size_t index) const{return *paragraphs_.at(index);}
    const std::vector<std::unique_ptr<Paragraph>>& Blocks() const noexcept{return paragraphs_;}
    float PageHeight() const noexcept{return pageHeight_;}
private:
    // Paragraph layouts keep references to these owned copies, never to the
    // caller's transient asset/catalog objects or a previously closed window.
    MenuFrontEndAssets::Font font_;MenuReplayTextCatalog catalog_;
    std::vector<std::unique_ptr<Paragraph>> paragraphs_;std::vector<Row> rows_;std::vector<std::size_t> starts_;float pageHeight_=405;
};
}
