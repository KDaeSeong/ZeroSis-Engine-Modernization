#include "MenuReplayText.h"
#include "MenuReplayLayout.h"
#include <iostream>
#include <set>
#include <type_traits>
using namespace ZeroSisHost;
static_assert(!std::is_move_constructible<MenuReplayMessagePages>::value,"Owned layout references must not move");
static_assert(!std::is_move_constructible<MenuReplayMessagePages::Paragraph>::value,"Owned paragraph references must not move");
static unsigned checks=0;
static void Check(bool value,const char* why){++checks;if(!value)throw std::runtime_error(why);}
template<class F>static void Reject(F function){bool rejected=false;try{function();}catch(const std::exception&){rejected=true;}Check(rejected,"Malformed rich text was accepted");}
static MenuFrontEndAssets::Font Face(){MenuFrontEndAssets::Font font;font.lineAdvance=22;font.baseline=17;
    for(std::uint32_t cp=32;cp<127;++cp)font.glyphs.emplace(cp,MenuFrontEndAssets::Glyph{0,6,0,0,15,0,0,5,18});
    font.glyphs.emplace(0xac00,MenuFrontEndAssets::Glyph{0,18,0,0,17,0,0,18,18});return font;}
static void Coverage(const MenuReplayRichText& text){
    std::string reconstructed;std::size_t end=0;
    for(const auto& run:text.Runs())if(!run.prefix){Check(run.begin==end && run.end>run.begin,"Raw source spans are not an exact partition");
        const auto span=text.Source(run);Check(span.data()==text.Original().data()+run.begin,"Source span copied or borrowed foreign text");
        reconstructed.append(span.data(),span.size());end=run.end;}
    Check(reconstructed==text.Original() && end==text.Original().size(),"Color/icon/newline source bytes were lost");
}
static std::size_t PageCoverage(const MenuReplayMessagePages& pages){
    std::size_t rows=0,atoms=0;
    for(std::size_t page=0;page<pages.PageCount();++page){Check(pages.FirstRow(page)==rows,"Replay page has a gap or repeated row");
        Check(pages.LastRow(page)>=rows,"Replay page is reversed");std::size_t pageAtoms=0;float height=0;
        for(auto row=pages.FirstRow(page);row<pages.LastRow(page);++row){const auto& line=pages.Rows()[row];const auto& block=pages.Block(line.paragraph);
            const auto& placed=block.layout.Lines()[line.line];pageAtoms+=placed.last-placed.first;height+=line.before+line.height+line.after;++rows;}
        Check(pageAtoms<=32768 && height<=405,"Replay page exceeds atom or physical viewport bounds");atoms+=pageAtoms;
    }
    Check(rows==pages.Rows().size(),"Replay page omitted final rows");return atoms;
}
int main(){try{
    auto face=Face();MenuReplayTextCatalog catalog;catalog.colors["COLOR_RED"]={1,0,0,1};catalog.colors["COLOR_BLUE"]={0,0,1,1};
    catalog.icons["ICON_GOLD"]={2,10,20,24,24,25,0,19};catalog.icons["ICON_BULLET"]={2,0,0,8,8,10,0,7};
    {
        const std::string raw="plain [COLOR_RED]red[COLOR_BLUE]blue[ENDCOLOR]red[ENDCOLOR] [ICON_GOLD][NEWLINE]next\r\nlast[TAB]x[BULLET]";
        MenuReplayRichText text(raw,9,catalog,catalog.defaultColor);Coverage(text);Check(text.UnsupportedTokens()==0 && text.UnclosedColors()==0,"Balanced original markers were not recognized");
        bool red=false,blue=false,icon=false;unsigned newline=0;for(const auto& run:text.Runs()){
            if(run.kind==MenuReplayRichText::Kind::Text && run.explicitColor){red|=run.color.r==1;blue|=run.color.b==1;}
            if(run.kind==MenuReplayRichText::Kind::Icon)icon=true;}
        for(const auto& atom:text.Atoms())if(atom.kind==MenuReplayRichText::Kind::Newline)++newline;
        Check(red && blue && icon && newline==2,"Nested colors/icons or explicit newline/CRLF failed");
        MenuReplayParagraphLayout layout(text,face,catalog,60);Check(layout.Lines().size()>4,"Actual advances did not wrap the paragraph");
        std::size_t previous=0;for(const auto& line:layout.Lines()){Check(line.first>=previous,"Paragraph wraps reordered source scalars");previous=line.last;}
    }
    {
        const std::string raw="a[COLOR_RED]unclosed [COLOR_BLUE]balanced[ENDCOLOR] [COLOR_UNKNOWN]x[ICON_NOT_REAL][ENDCOLOR][ENDCOLOR]tail[unfinished";
        MenuReplayRichText text(raw,7,catalog,catalog.defaultColor);Coverage(text);Check(text.UnsupportedTokens()>=3,"Unknown/unmatched markers did not remain literal");
        MenuReplayRichText unclosed("[COLOR_RED]not closed",7,catalog,catalog.defaultColor);Coverage(unclosed);
        Check(unclosed.UnclosedColors()==1 && unclosed.Runs().size()==2 && !unclosed.Runs()[1].explicitColor,"Unclosed opening marker was hidden or applied");
        MenuReplayRichText numeric("[COLOR:1:2:3:120]x[/COLOR] [COLOR:256:0:0:255]literal",0,catalog,catalog.defaultColor);Coverage(numeric);
        Check(numeric.UnsupportedTokens()==1,"Invalid numeric color did not remain literal");
        std::string nested;for(unsigned i=0;i<33;++i)nested+="[COLOR_RED]";nested+='x';for(unsigned i=0;i<33;++i)nested+="[ENDCOLOR]";
        MenuReplayRichText deep(nested,0,catalog,catalog.defaultColor);Coverage(deep);Check(deep.UnsupportedTokens()==34,"Over-depth markup did not stay literal");
    }
    {
        const std::string raw="\xea\xb0\x80\xf0\x9f\x98\x80";MenuReplayRichText text(raw,0,catalog,catalog.defaultColor);Coverage(text);
        Check(text.Atoms().size()==6 && text.Atoms()[4].scalar==0xac00 && text.Atoms()[5].scalar==0x1f600,"UTF-8 Korean/supplementary scalar was split");
        MenuReplayParagraphLayout layout(text,face,catalog,6);std::size_t emoji=0;
        for(std::size_t line=0;line<layout.Lines().size();++line)for(const auto& place:layout.Place(line,0,0))if(text.Atoms()[place.atom].scalar==0x1f600){Check(place.scalar=='?',"Missing glyph did not use original question mark");++emoji;}
        Check(emoji==1 && text.Original()==raw,"Supplementary raw source was lost or duplicated at wrap");
        Reject([&]{MenuReplayRichText bad(std::string("\xed\xa0\x80",3),0,catalog,catalog.defaultColor);});
        Reject([&]{MenuReplayRichText bad(std::string(1024*1024+1,'a'),0,catalog,catalog.defaultColor);});
    }
    {
        const std::vector<MenuReplayTextColor> primary{{.1f,.1f,.1f,1},{.7f,.2f,.1f,1}};
        const std::vector<MenuReplayTextColor> secondary{{1,1,1,1},{.2f,.8f,.3f,1}};
        auto neutral=OriginalReplayMessageInk(-1,primary,secondary,catalog.defaultColor);Check(neutral.color.r==200.0f/255 && !neutral.contrastOverlay,"NO_PLAYER original Gray_Chat changed");
        auto dark=OriginalReplayMessageInk(0,primary,secondary,catalog.defaultColor);Check(dark.color.r==.1f && dark.contrastOverlay,"Original dark-primary white contrast overlay missing");
        auto colored=OriginalReplayMessageInk(1,primary,secondary,catalog.defaultColor);Check(colored.color.g==.8f && !colored.contrastOverlay,"Original non-neutral secondary selection changed");
    }
    {
        MenuReplayDocument doc;doc.messages={{9,0,-1,"first",{}},{7,0,-1,"second",{}},{7,0,-1,"",{}}};
        MenuReplayMessagePages pages(doc,face,catalog,{},{});Check(pages.Blocks().size()==2 && pages.Block(0).text.Original()=="first" && pages.Block(1).messageIndex==1,"Original message vector order/empty skip changed");
        PageCoverage(pages);MenuReplayDocument empty;empty.messages.resize(100000);MenuReplayMessagePages none(empty,face,catalog,{},{});
        Check(none.PageCount()==1 && none.Rows().empty() && none.Blocks().empty(),"Empty paragraphs produced duplicate pages");PageCoverage(none);
    }
    {
        std::unique_ptr<MenuReplayMessagePages> detached;
        {auto temporaryFont=Face();MenuReplayTextCatalog temporaryCatalog=catalog;MenuReplayDocument temporaryDoc;
            temporaryDoc.messages={{0,0,-1,"[ICON_GOLD]after caller destruction",{}}};
            detached=std::make_unique<MenuReplayMessagePages>(temporaryDoc,temporaryFont,temporaryCatalog,
                std::vector<MenuReplayTextColor>{},std::vector<MenuReplayTextColor>{});}
        PageCoverage(*detached);const auto placed=detached->Block(0).layout.Place(0,10,10);
        Check(!placed.empty() && placed[0].x==10 && detached->Block(0).text.Original()=="[ICON_GOLD]after caller destruction",
            "Cached rich paragraph borrowed a destroyed font/catalog/document");
    }
    std::size_t maximumPages=0;
    {
        MenuReplayDocument doc;doc.messages.resize(100000);doc.messages.back().text=std::string(1024*1024,'A');doc.messages.back().turn=42;
        const auto original=doc.messages.back().text;MenuReplayMessagePages pages(doc,face,catalog,{},{});
        Check(pages.Blocks().size()==1 && pages.Block(0).messageIndex==99999,"Many empty records changed the single original paragraph index");
        Check(PageCoverage(pages)==original.size()+5,"Maximum single paragraph was truncated between pages");maximumPages=pages.PageCount();
        Check(maximumPages>300 && pages.Block(0).text.Original()==original && doc.messages.back().text==original,"Maximum raw source changed");
    }
    {
        auto zero=face;zero.lineAdvance=1;zero.baseline=1;for(auto& glyph:zero.glyphs){glyph.second.a=0;glyph.second.b=0;glyph.second.c=0;glyph.second.width=0;glyph.second.height=0;}
        MenuReplayDocument doc;doc.messages={{0,0,-1,std::string(100000,'A'),{}}};MenuReplayMessagePages pages(doc,zero,catalog,{},{});
        Check(pages.PageCount()>=4 && PageCoverage(pages)==100004,"Zero-advance glyphs evaded scene budget or lost data");
    }
    const auto layout=MenuReplayOriginalLayout::At();Check(layout.frame.x==480 && layout.frame.y==262 && layout.main.x==500 && layout.main.y==320,"Original sibling panel anchors changed");
    Check(layout.graph.x==660 && layout.graph.y==375 && layout.graph.width==720 && layout.map.width==920 && layout.slider.width==500,"Original graph/map/slider offsets changed");
    Check(layout.back.x==519 && layout.back.y==805.5f && layout.back.width==150,"Original source-derived Back footer changed");
    Reject([]{MenuReplayOriginalLayout::At(800,600);});
    std::cout<<"{\"status\":\"PASS_SDK_FREE_REPLAY_RICHTEXT_LAYOUT_SOURCE_COVERAGE\",\"checks\":"<<checks
        <<",\"maximum_message_bytes\":1048576,\"maximum_message_pages\":"<<maximumPages<<",\"empty_records\":100000,\"native_host_sdk_window_gpu_executed\":false}"<<std::endl;
    return 0;
}catch(const std::exception& error){std::cerr<<error.what()<<std::endl;return 1;}}
