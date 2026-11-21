// Independent authored paragraph geometry and real immutable line-catalog tests.
#include "MenuReplayMessageViewport.h"
#include "MenuReplayScrollModel.h"
#include <array>
#include <cstdio>
#include <limits>
#include <memory>
#include <type_traits>

using namespace ZeroSisHost;
static unsigned checks=0;
static std::size_t largeRows=0,largeLegacyPages=0,largeVisibleAtoms=0;
static void Check(bool value,const char* why){++checks;if(!value)throw std::runtime_error(why);}
template<class Action>static void Reject(Action action){bool failed=false;try{action();}catch(const std::invalid_argument&){failed=true;}Check(failed,"Invalid viewport geometry was accepted");}
static MenuFrontEndAssets::Font Face(int advance=5,int line=10,int baseline=7){
    MenuFrontEndAssets::Font font;font.lineAdvance=line;font.baseline=baseline;
    for(std::uint32_t scalar=32;scalar<127;++scalar)
        font.glyphs.emplace(scalar,MenuFrontEndAssets::Glyph{0,advance,0,0,baseline,0,0,advance,baseline});
    return font;
}
static MenuReplayTextCatalog Catalog(){MenuReplayTextCatalog catalog;catalog.icons["ICON_TALL"]={0,0,0,8,30,9,0,24};return catalog;}
static MenuReplayDocument SmallDocument(){
    MenuReplayDocument document;document.rawBytes={1,9,2,8,3,7,4,6};
    document.messages={{9,0,-1,"A[NEWLINE]B",{}},{1,0,-1,"",{}},{1,0,-1,"[ICON_TALL]",{}},{2,0,-1,"",{}},{7,0,-1,"B",{}}};
    return document;
}
static void ExactAuthoredGeometry(){
    const auto document=SmallDocument();const auto font=Face();const auto catalog=Catalog();
    MenuReplayMessagePages pages(document,font,catalog,{},{});MenuReplayMessageViewport viewport(pages);
    Check(pages.Blocks().size()==3 && pages.Rows().size()==4,"Empty source records became visible paragraphs");
    Check(pages.Block(0).messageIndex==0 && pages.Block(1).messageIndex==2 && pages.Block(2).messageIndex==4,"Original vector order was replaced by turn order");
    // Each normal line is10px. A two-line paragraph has20+5+5+1=31px.
    // The tall icon independently requires24px above baseline+6px below=30px.
    // Its paragraph is41px; the final one-line paragraph is21px; tail is63px.
    const double tops[]={0,15,31,72},ends[]={15,31,72,93};
    for(std::size_t index=0;index<4;++index){
        Check(viewport.RowTop(index)==tops[index] && viewport.RowEnd(index)==ends[index],"Authored5/5/stack1 paragraph spacing or30px icon extent changed");
    }
    Check(viewport.ContentHeight()==156 && viewport.Maximum(405)==0 && viewport.Maximum(20)==136,"Stock63px bottom instance or short-content extent changed");
    struct Example final {double offset,height;std::size_t first,last;};
    const Example examples[]={{0,20,0,2},{15,16,1,2},{31,41,2,3},{72,21,3,4},{93,63,4,4},{14.5,.25,0,1},{14.999,.002,0,2},{500,20,4,4},{-500,20,0,2}};
    for(const auto& example:examples){const auto range=viewport.Visible(example.offset,example.height);
        Check(range.first==example.first && range.last==example.last,"Exact/fractional/tail viewport boundaries selected the wrong rows");}
    // Independent brute rectangle intersections over the explicit source
    // geometry above, rather than another prefix/binary-search implementation.
    for(unsigned sample=0;sample<700;++sample){
        const double height=.25+(sample%61)*.5,requested=-3+sample*.25;
        const double maximum=(std::max)(0.0,156-height),top=(std::max)(0.0,(std::min)(maximum,requested));
        std::size_t first=4,last=4;bool found=false;
        for(std::size_t candidate=0;candidate<4;++candidate)if(ends[candidate]>top && tops[candidate]<top+height){
            if(!found){first=candidate;found=true;}last=candidate+1;
        }
        const auto selected=viewport.Visible(requested,height);
        Check(selected.first==first && selected.last==last,"Continuous clipping differs from independent source rectangles");
    }
    const double fractional=10.25;
    auto firstLine=pages.Block(0).layout.Place(0,0,static_cast<float>(viewport.RowTop(0)+pages.Rows()[0].before-fractional));
    auto secondLine=pages.Block(0).layout.Place(1,0,static_cast<float>(viewport.RowTop(1)+pages.Rows()[1].before-fractional));
    Check(!firstLine.empty() && firstLine[0].baseline==1.75f && secondLine[0].baseline==11.75f,"Fractional offset was rounded before line placement");
    const auto iconLine=pages.Block(1).layout.Place(0,0,static_cast<float>(viewport.RowTop(2)+pages.Rows()[2].before-fractional));
    bool tall=false;for(const auto& placement:iconLine)if(placement.kind==MenuReplayRichText::Kind::Icon){
        Check(placement.baseline==49.75f && placement.baseline-24==25.75f,"Icon ascent was confused with line/paragraph top");tall=true;
    }
    Check(tall && document.rawBytes==std::vector<unsigned char>({1,9,2,8,3,7,4,6}) && document.messages[0].text=="A[NEWLINE]B","Source history/paragraph text was changed by indexing");
    bool topRejected=false,endRejected=false;
    try{viewport.RowTop(4);}catch(const std::out_of_range&){topRejected=true;}
    try{viewport.RowEnd(4);}catch(const std::out_of_range&){endRejected=true;}
    Check(topRejected && endRejected,"Invalid row index escaped owned vectors");
}
static void EmptyAndLifetime(){
    MenuReplayDocument empty;empty.messages.resize(100000);const auto face=Face();MenuReplayTextCatalog catalog;
    MenuReplayMessagePages emptyPages(empty,face,catalog,{},{});MenuReplayMessageViewport viewport(emptyPages);
    Check(viewport.RowCount()==0 && viewport.ContentHeight()==63 && viewport.Maximum(405)==0,"100k empty records manufactured rows or lost the stock tail");
    auto range=viewport.Visible(100000,20);Check(range.first==0 && range.last==0 && viewport.Clamp(100000,20)==43,"Empty-tail-only scroll produced a text row");
    MenuReplayMessageViewport noTail(emptyPages,0);Check(noTail.ContentHeight()==0 && noTail.Visible(0,405).last==0,"Explicit zero-tail empty content divided by zero");
    std::unique_ptr<MenuReplayMessagePages> ownedPages;std::unique_ptr<MenuReplayMessageViewport> detached;
    {
        auto temporaryDocument=SmallDocument();auto temporaryFont=Face();auto temporaryCatalog=Catalog();
        ownedPages=std::make_unique<MenuReplayMessagePages>(temporaryDocument,temporaryFont,temporaryCatalog,std::vector<MenuReplayTextColor>{},std::vector<MenuReplayTextColor>{});
        detached=std::make_unique<MenuReplayMessageViewport>(*ownedPages);
        temporaryDocument.messages.clear();temporaryFont.glyphs.clear();temporaryCatalog.icons.clear();
    }
    Check(ownedPages->Block(0).text.Original()=="A[NEWLINE]B" && ownedPages->Block(1).layout.Place(0,0,0).size()==5,"Line catalog borrowed destroyed source/font/icon data");
    const auto copied=*detached;ownedPages.reset();detached.reset();
    Check(copied.RowCount()==4 && copied.ContentHeight()==156 && copied.RowTop(2)==31 && copied.Visible(15,16).first==1,"Viewport index borrowed destroyed row catalog storage");
    static_assert(!std::is_move_constructible<MenuReplayMessagePages>::value,"Paragraph layout ownership contract changed");
}
static void MaximumParagraph(){
    MenuReplayDocument document;document.rawBytes={11,22,33,44};document.messages.resize(100000);
    document.messages.back().turn=9;document.messages.back().text=std::string(1024*1024,'A');
    const auto rawBefore=document.rawBytes;const auto face=Face(1,4,3);MenuReplayTextCatalog catalog;
    // Wide synthetic lines deliberately hit the actual4096-atom line limit.
    // (1048576 raw scalars + four prefix scalars) form256 full lines +4.
    MenuReplayMessagePages pages(document,face,catalog,{},{},2000000);MenuReplayMessageViewport viewport(pages);
    Check(pages.Blocks().size()==1 && pages.Block(0).messageIndex==99999 && pages.Rows().size()==257,"1MiB/100k-empty input lost actual source rows");
    Check(pages.Block(0).text.Atoms().size()==1048580 && pages.Block(0).layout.Lines().back().last-pages.Block(0).layout.Lines().back().first==4,"Maximum raw paragraph atom coverage changed");
    Check(viewport.ContentHeight()==1102 && viewport.Maximum(405)==697 && viewport.RowTop(123)==497,"Independent257*4+5+6+63 source extent differs");
    const auto middle=viewport.Visible(500.5,405);Check(middle.first==123 && middle.last==226,"Fractional midpoint was clipped to a legacy page or rounded");
    Check(pages.LastRow(0)==8 && pages.PageCount()==33 && middle.first>pages.LastRow(0),"Fixture did not cross the actual32768-atom legacy page split");
    std::size_t atoms=0;for(auto selected=middle.first;selected<middle.last;++selected){const auto& line=pages.Block(0).layout.Lines()[selected];atoms+=line.last-line.first;}
    Check(atoms==421888 && atoms>32768,"Continuous range was truncated to the old page atom budget");
    const auto bottom=viewport.Visible(697,405);Check(bottom.first==173 && bottom.last==257 && viewport.RowEnd(256)==1039,"Bottom scroll omitted the final paragraph/rows");
    const auto almost=viewport.Visible(696.5,405);Check(almost.first==172 && almost.last==257,"Half-pixel bottom offset did not expose the expected partial row");
    const auto continuous=MenuReplayScrollModel::FloatContinuous(.5,viewport.Maximum(405));
    const auto center=viewport.Visible(continuous,405);Check(continuous==348.5 && center.first==85 && center.last==188,"Normalized message scroll was rounded to a page");
    const auto& finalRow=pages.Rows().back();const auto finalBottom=viewport.RowTop(256)+finalRow.before+finalRow.height-697;
    Check(finalBottom==336 && 405-finalBottom==69,"Last glyph row did not leave bottom5+stack1+tail63 below it");
    Check(pages.Block(0).text.Original()==document.messages.back().text && document.rawBytes==rawBefore,"Maximum paragraph/raw history was changed");
    largeRows=pages.Rows().size();largeLegacyPages=pages.PageCount();largeVisibleAtoms=atoms;
}
static void InvalidAndRepresentability(){
    auto document=SmallDocument();const auto face=Face();const auto catalog=Catalog();MenuReplayMessagePages pages(document,face,catalog,{},{});
    const double nan=(std::numeric_limits<double>::quiet_NaN)(),infinity=(std::numeric_limits<double>::infinity)();
    Reject([&]{MenuReplayMessageViewport invalid(pages,nan);});Reject([&]{MenuReplayMessageViewport invalid(pages,infinity);});
    Reject([&]{MenuReplayMessageViewport invalid(pages,-1);});Reject([&]{MenuReplayMessageViewport invalid(pages,4097);});
    MenuReplayMessageViewport viewport(pages);
    for(const double height:{0.0,-1.0,32769.0,nan,infinity}){
        Reject([&]{viewport.Maximum(height);});Reject([&]{viewport.Visible(0,height);});
    }
    Reject([&]{viewport.Clamp(nan,405);});Reject([&]{viewport.Visible(infinity,405);});
    Check(viewport.Clamp(-(std::numeric_limits<double>::max)(),20)==0 && viewport.Clamp((std::numeric_limits<double>::max)(),20)==136,"Finite off-track offset did not clamp");
    // Fault injection is restricted to a new owned non-const synthetic catalog.
    // It tests the index boundary; no production source, immutable input, user
    // document or live cache is modified.
    auto& rows=const_cast<std::vector<MenuReplayMessagePages::Row>&>(pages.Rows());const auto original=rows;
    const auto checkBad=[&](float before,float height,float after){rows=original;rows[0].before=before;rows[0].height=height;rows[0].after=after;
        Reject([&]{MenuReplayMessageViewport invalid(pages);});};
    checkBad(-1,10,0);checkBad(0,0,0);checkBad(0,-1,0);checkBad(0,10,-1);
    checkBad(0,(std::numeric_limits<float>::quiet_NaN)(),0);checkBad(0,(std::numeric_limits<float>::infinity)(),0);
    rows.assign(1,original[0]);rows[0].before=rows[0].after=0;rows[0].height=(std::numeric_limits<float>::max)();
    Reject([&]{MenuReplayMessageViewport lostTail(pages);});
    MenuReplayMessageViewport huge(pages,0);Reject([&]{huge.Maximum(405);});Reject([&]{huge.Visible(0,405);});
    rows.push_back(original[0]);Reject([&]{MenuReplayMessageViewport lostRow(pages,0);});
    rows=original;MenuReplayMessageViewport restored(pages);Check(restored.ContentHeight()==156,"Owned malformed fixture was not restored after fault tests");
}
int main(){try{
    ExactAuthoredGeometry();EmptyAndLifetime();MaximumParagraph();InvalidAndRepresentability();
    std::printf("{\"status\":\"PASS_SDK_FREE_MESSAGE_CONTINUOUS_VIEWPORT\",\"checks\":%u,\"maximum_source_rows\":%zu,\"legacy_pages_crossed\":%zu,\"synthetic_visible_atoms_beyond_legacy_budget\":%zu,\"native_host_sdk_window_gpu_executed\":false}\n",checks,largeRows,largeLegacyPages,largeVisibleAtoms);return 0;
}catch(const std::exception& error){std::fprintf(stderr,"%s\n",error.what());return 1;}}
