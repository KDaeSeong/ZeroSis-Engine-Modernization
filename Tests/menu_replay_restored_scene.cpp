#include <functional>
#include <iomanip>
#include "menu_frontend_scene_fixture.h"
#include "MenuReplayPresentation.h"
#include "../Source/Presentation/SceneLineContract.h"
#define main old_sdk_writer_fixture_main
#include "menu_replay_fixture.cpp"
#undef main
static void Check(bool value,const char* why){++checks;if(!value)throw std::runtime_error(why);}
static void SceneCheck(const Scene& scene){
    Check(scene.width==1920 && scene.height==1080 && scene.textures.size()<=64 && scene.sprites.size()<500000,"Restored replay scene viewport/bank/budget changed");
    std::set<std::uint64_t> keys;unsigned back=0;const auto original=MenuReplayOriginalLayout::At();
    for(const auto& hit:scene.hits){Check(keys.insert(hit.controlKey).second,"Restored replay input key repeated");
        Check(hit.controlKey==35 || hit.controlKey>=MenuReplayView::KeyBase,"Restored replay captured an unowned input key");
        Check(hit.bounds[0]>=0 && hit.bounds[1]>=0 && hit.bounds[2]<=1920 && hit.bounds[3]<=1080,"Restored replay input escaped viewport");
        if(hit.controlKey==35){++back;Check(hit.bounds[0]==original.back.x && hit.bounds[1]==original.back.y && hit.bounds[2]==original.back.Right() && hit.bounds[3]==original.back.Bottom(),"Restored Back footer differs from original XML anchor");}}
    Check(back==1,"Restored replay must expose exactly one lifecycle-owned Back control");
    for(const auto& sprite:scene.sprites){Check(sprite.textureIndex==ZeroSisPresentation::kSolidRectangleTexture || sprite.textureIndex<scene.textures.size(),"Restored replay texture escaped actual bank");
        for(float value:sprite.targetRect)Check(std::isfinite(value),"Restored replay geometry nonfinite");
        Check(sprite.clipRect[2]>sprite.clipRect[0] && sprite.clipRect[3]>sprite.clipRect[1],"Restored replay emitted an empty or reversed scissor");
        for(float value:sprite.tintRGBA)Check(value>=0 && value<=1,"Restored replay tint invalid");}
    for(const auto& scroll:scene.scrolls)Check(scroll.controlKey==0 || scroll.controlKey==MenuReplayView::LegendScrollKey || scroll.controlKey==MenuReplayView::MessageScrollKey ||
        scroll.controlKey==MenuReplayView::TurnScrollKey,"Replay exposed an unowned scroll surface");
    std::wstring lineError;Check(ZeroSisPresentation::ValidateSceneLines(scene,&lineError),"Actual replay line geometry violates production rendering contract");
}
static bool Has(const Scene& scene,std::uint64_t key){for(const auto& hit:scene.hits)if(hit.controlKey==key)return true;return false;}
static bool SameInput(const Scene& first,const Scene& second){
    const auto same=[](const std::vector<ZeroSisPresentation::HitRecord>& a,const std::vector<ZeroSisPresentation::HitRecord>& b){
        if(a.size()!=b.size())return false;
        for(std::size_t i=0;i<a.size();++i){if(a[i].controlKey!=b[i].controlKey)return false;
            for(unsigned j=0;j<4;++j)if(a[i].bounds[j]!=b[i].bounds[j])return false;}
        return true;
    };
    return same(first.hits,second.hits) && same(first.scrolls,second.scrolls);
}
static MenuReplayBounds ScrollThumb(const Scene& scene,std::uint64_t key){
    float left=1920,top=1080,right=0,bottom=0;
    for(const auto& sprite:scene.sprites)if(sprite.controlKey==key){
        left=(std::min)(left,sprite.targetRect[0]);top=(std::min)(top,sprite.targetRect[1]);
        right=(std::max)(right,sprite.targetRect[2]);bottom=(std::max)(bottom,sprite.targetRect[3]);}
    Check(right>left && bottom>top,"Actual original legend shuttle geometry was not emitted");
    return {left,top,right-left,bottom-top};
}
static MenuReplayBounds LegendThumb(const Scene& scene){return ScrollThumb(scene,MenuReplayView::LegendSeekKey);}
static std::vector<const ZeroSisPresentation::SceneLine*> DataLines(const Scene& scene){
    std::vector<const ZeroSisPresentation::SceneLine*> lines;const auto bounds=MenuReplayOriginalLayout::At().graph;
    for(const auto& line:scene.lines)if(line.width==1 && line.clipRect[0]==bounds.x && line.clipRect[1]==bounds.y && line.clipRect[2]==bounds.Right() && line.clipRect[3]==bounds.Bottom())lines.push_back(&line);
    return lines;
}
static std::vector<const ZeroSisPresentation::SceneLine*> PointerLines(const Scene& scene){
    std::vector<const ZeroSisPresentation::SceneLine*> lines;
    for(const auto& line:scene.lines){const bool gray=line.tintRGBA[0]==90/255.0f && line.tintRGBA[1]==90/255.0f && line.tintRGBA[2]==90/255.0f && line.tintRGBA[3]==90/255.0f;
        const bool red=line.tintRGBA[0]==1 && line.tintRGBA[1]==0 && line.tintRGBA[2]==0 && line.tintRGBA[3]==1;
        if(line.width==1 && line.clipRect[0]==0 && line.clipRect[1]==0 && line.clipRect[2]==1920 && line.clipRect[3]==1080 && (gray || red))lines.push_back(&line);}
    return lines;
}
static void CheckPointerLines(const Scene& scene,const MenuReplayView& view){
    const auto expected=view.PointerGuides();const auto actual=PointerLines(scene);const auto graph=MenuReplayOriginalLayout::At().graph;
    Check(actual.size()==(expected.visible?4u:0u),"Replay pointer guide visibility differs from its original graph panel policy");
    if(!expected.visible)return;
    for(std::size_t i=0;i<4;++i){const auto& a=*actual[i];const auto& b=expected.lines[i];
        Check(a.start[0]==graph.x+b.startX && a.start[1]==graph.y+b.startY && a.end[0]==graph.x+b.endX && a.end[1]==graph.y+b.endY,
            "Replay pointer guide changed source relative endpoints or XML line order");
        for(unsigned color=0;color<4;++color)Check(a.tintRGBA[color]==b.rgba[color]/255.0f,"Replay pointer guide changed original RGBA bytes");}
}
static std::size_t CheckGraphLines(const Scene& scene,const MenuReplayDocument& document,std::size_t dataSet,const std::set<std::size_t>& hidden={}){
    const auto expected=BuildMenuReplayGraphGeometry(document,dataSet);const auto actual=DataLines(scene);
    const auto bounds=MenuReplayOriginalLayout::At().graph;std::size_t at=0;
    for(const auto& series:expected.series){if(hidden.count(static_cast<std::size_t>(series.playerIndex)))continue;
        for(const auto& line:series.lines){Check(at<actual.size(),"Original sampled graph line was omitted from the production Scene");const auto& rendered=*actual[at++];
            Check(rendered.start[0]==bounds.x+line.startX && rendered.start[1]==bounds.y+line.startY &&
                rendered.end[0]==bounds.x+line.endX && rendered.end[1]==bounds.y+line.endY,
                "Graph Scene changed source sample order or original integer line coordinates");}}
    Check(at==actual.size(),"Graph Scene emitted extra data markers or connection segments");return at;
}
static void Select(MenuReplayView& view,const MenuFrontEndAssets& assets,std::uint64_t key){
    ZeroSisPresentation::BitmapInputEvent event{};event.kind=ZeroSisPresentation::BitmapInputKind::ControlClick;event.controlKey=MenuReplayView::KeyBase+12;
    Check(view.Input(event),"Replay source selector did not open");const auto popup=view.Scene(assets);SceneCheck(popup);
    Check(Has(popup,key) && !Has(popup,MenuReplayView::SeekKey),"Source selector popup did not isolate its input");
    event.controlKey=key;Check(view.Input(event),"Replay source selector choice was not routed");
}
static void Packet(const Scene& scene,const std::wstring& path){
    std::ofstream file(path,std::ios::binary);auto word=[&](std::uint32_t n){file.write(reinterpret_cast<const char*>(&n),4);};
    file.write("ZSUPIX02",8);word(scene.width);word(scene.height);word(static_cast<std::uint32_t>(scene.textures.size()));
    word(static_cast<std::uint32_t>(scene.sprites.size()));word(static_cast<std::uint32_t>(scene.hits.size()));word(static_cast<std::uint32_t>(scene.scrolls.size()));
    for(const auto& texture:scene.textures){const auto text=Narrow(texture.path);word(static_cast<std::uint32_t>(text.size()));file.write(text.data(),static_cast<std::streamsize>(text.size()));}
    for(const auto& sprite:scene.sprites){word(sprite.textureIndex);file.write(reinterpret_cast<const char*>(&sprite.controlKey),8);file.write(reinterpret_cast<const char*>(sprite.sourceRect),64);}
    for(const auto& hit:scene.hits){file.write(reinterpret_cast<const char*>(&hit.controlKey),8);file.write(reinterpret_cast<const char*>(hit.bounds),16);}Check(bool(file),"Restored scene packet write failed");
    for(const auto& scroll:scene.scrolls){file.write(reinterpret_cast<const char*>(&scroll.controlKey),8);file.write(reinterpret_cast<const char*>(scroll.bounds),16);}Check(bool(file),"Restored scene scroll packet write failed");
    std::ofstream lines(path+L".lines.json");lines<<std::setprecision(std::numeric_limits<float>::max_digits10);
    lines<<"{\"schema\":\"zerosis.scene_line.diagnostic.v1\",\"lines\":[";bool comma=false;
    for(const auto& line:scene.lines){if(comma)lines<<',';comma=true;lines<<"{\"beforeSprite\":"<<line.beforeSprite<<",\"width\":"<<line.width<<",\"start\":["<<line.start[0]<<','<<line.start[1]<<"],\"end\":["<<line.end[0]<<','<<line.end[1]<<"],\"rgba\":[";
        for(unsigned i=0;i<4;++i){if(i)lines<<',';lines<<line.tintRGBA[i];}lines<<"],\"clip\":[";for(unsigned i=0;i<4;++i){if(i)lines<<',';lines<<line.clipRect[i];}lines<<"]}";}
    lines<<"]}\n";Check(bool(lines),"Diagnostic actual line record write failed");
}
int wmain(int argc,wchar_t** argv){try{
    if(argc!=4)throw std::runtime_error("Expected immutable V3 assets, actual labels/palette, owned output directory");
    const auto assets=MenuFrontEndAssets::Load(argv[1]);Check(assets->Extended() && assets->Icons().size()==148 && assets->HasFontFace(14,"Shadow"),"Actual V3 faces/icon inventory missing");
    const auto metadata=Read(argv[2]);std::size_t cursor=0;
    auto text=[&](){const auto length=U32(metadata,cursor);if(length>4096 || length>metadata.size()-cursor)throw std::runtime_error("Restoration fixture text bound");
        std::string value(reinterpret_cast<const char*>(metadata.data()+cursor),length);cursor+=length;return value.empty()?std::wstring():Widen(value);};
    MenuReplayLabels labels;labels.title=text();labels.map=text();labels.graphs=text();labels.messages=text();labels.playPause=text();
    labels.turn=text();labels.noGraphData=text();labels.terrainReference=text();labels.unsupportedReplay=text();labels.back=text();
    MenuReplayPalette palette;const auto count=U32(metadata,cursor);Check(count==2,"Actual writer fixture roster differs");
    for(unsigned i=0;i<count;++i){float rgba[8];Check(metadata.size()-cursor>=sizeof(rgba),"Actual fixture colors truncated");std::memcpy(rgba,metadata.data()+cursor,sizeof(rgba));cursor+=sizeof(rgba);
        palette.playerPrimary.push_back({rgba[0],rgba[1],rgba[2],.8f});palette.playerSecondary.push_back({rgba[4],rgba[5],rgba[6],1});
        palette.messagePrimary.push_back({rgba[0],rgba[1],rgba[2],1});palette.messageSecondary.push_back({rgba[4],rgba[5],rgba[6],1});}
    const auto names=U32(metadata,cursor);for(unsigned i=0;i<names;++i){const auto name=Narrow(text());palette.dataSetLabels[name]=text();}
    const auto rich=U32(metadata,cursor);for(unsigned i=0;i<rich;++i){const auto name=Narrow(text());float rgba[4];Check(metadata.size()-cursor>=sizeof(rgba),"Actual rich colors missing");
        std::memcpy(rgba,metadata.data()+cursor,sizeof(rgba));cursor+=sizeof(rgba);palette.richColors[name]={rgba[0],rgba[1],rgba[2],rgba[3]};}
    Check(palette.richColors.size()==221,"Actual original color inventory differs");
    MenuReplayCalendarCatalog calendar;
    auto countRows=U32(metadata,cursor);for(unsigned i=0;i<countRows;++i){const auto id=U32(metadata,cursor);calendar.calendars[static_cast<int>(id)]=Narrow(text());}
    countRows=U32(metadata,cursor);for(unsigned i=0;i<countRows;++i){const auto id=U32(metadata,cursor);const auto name=Narrow(text());calendar.gameSpeeds[static_cast<int>(id)]=name;
        auto& increments=calendar.speedTurns[name];const auto n=U32(metadata,cursor);for(unsigned j=0;j<n;++j){const auto months=U32(metadata,cursor),turns=U32(metadata,cursor);increments.push_back({months,turns});}}
    countRows=U32(metadata,cursor);for(unsigned i=0;i<countRows;++i)calendar.monthNames.push_back(text());
    countRows=U32(metadata,cursor);for(unsigned i=0;i<countRows;++i)calendar.seasonNames.push_back(text());
    calendar.weeksPerMonth=static_cast<int>(U32(metadata,cursor));calendar.hiddenStartTurnOffset=static_cast<int>(U32(metadata,cursor));
    std::map<std::string,std::wstring> numberTemplates;
    countRows=U32(metadata,cursor);for(unsigned i=0;i<countRows;++i){const auto key=Narrow(text());numberTemplates[key]=text();}
    const auto number=[numberTemplates](const char* key,std::int64_t value){
        auto result=numberTemplates.at(key);const auto begin=result.find(L"{1_"),end=result.find(L'}',begin);
        if(begin==std::wstring::npos || end==std::wstring::npos)throw std::runtime_error("Unexpected actual single-integer localization template");
        result.replace(begin,end-begin+1,std::to_wstring(value));return result;
    };
    calendar.localizeNumber=number;palette.calendar=std::make_shared<const MenuReplayCalendar>(calendar);
    labels.turnCounter=[number](int turn){return number("TXT_KEY_TP_TURN_COUNTER",turn);};
    struct Civilization final {MenuReplayPalette::LegendIcon icon;std::string label;};
    std::map<int,Civilization> civilizations;
    countRows=U32(metadata,cursor);for(unsigned i=0;i<countRows;++i){const auto id=U32(metadata,cursor);Civilization civ;
        civ.icon.portrait=U32(metadata,cursor);civ.icon.columns=U32(metadata,cursor);civ.icon.rows=U32(metadata,cursor);civ.icon.texture=Narrow(text());const auto caption=text();civ.label=caption.empty()?std::string():Narrow(caption);
        civilizations.emplace(static_cast<int>(id),std::move(civ));}
    const int firstCivilization=static_cast<int>(U32(metadata,cursor)),secondCivilization=static_cast<int>(U32(metadata,cursor));
    float originalCaptionRgba[4];Check(metadata.size()-cursor>=sizeof(originalCaptionRgba),"Actual civilization color oracle missing");
    std::memcpy(originalCaptionRgba,metadata.data()+cursor,sizeof(originalCaptionRgba));cursor+=sizeof(originalCaptionRgba);const auto originalCaption=text();
    std::vector<MenuReplayGraphColor> actualGraphCatalog;
    countRows=U32(metadata,cursor);for(unsigned i=0;i<countRows;++i){const auto name=Narrow(text());double rgba[4];
        Check(metadata.size()-cursor>=sizeof(rgba),"Actual double-precision graph color catalog truncated");std::memcpy(rgba,metadata.data()+cursor,sizeof(rgba));cursor+=sizeof(rgba);
        actualGraphCatalog.push_back({name,rgba[0],rgba[1],rgba[2],rgba[3]});}
    std::vector<std::pair<std::string,std::string>> graphRoster;
    countRows=U32(metadata,cursor);for(unsigned i=0;i<countRows;++i){const auto primary=Narrow(text()),secondary=Narrow(text());graphRoster.emplace_back(primary,secondary);}
    const auto graphSelection=SelectMenuReplayGraphColors(actualGraphCatalog,graphRoster);
    Check(graphSelection.size()==2 && graphSelection[0].type=="COLOR_PLAYER_WHITE" && graphSelection[1].type=="COLOR_PLAYER_DARK_PINK",
        "Actual recorded color roster no longer matches the original Lua unique-color golden");
    for(const auto& color:graphSelection)palette.graphColors.push_back({static_cast<float>(color.r),static_cast<float>(color.g),static_cast<float>(color.b),static_cast<float>(color.a)});
    for(const int id:{firstCivilization,secondCivilization}){palette.legendIcons.push_back(civilizations.at(id).icon);palette.playerLabels.push_back(civilizations.at(id).label);}
    Check(cursor==metadata.size() && calendar.calendars.size()==7 && calendar.gameSpeeds.size()==4,"Actual replay catalog metadata differs");
    Check(palette.calendar->ShortDate(0,2,-4000,4).text==L"3840 BC" && palette.calendar->ShortDate(4,2,-4000,4).text==L"TXT_KEY_SEASON_WINTER, 3999 BC",
        "Missing actual stock season localization blocked DEFAULT or did not show the original raw key");
    auto seed=Seed();seed.m_listReplayMessages[0].m_strText="[COLOR_YELLOW]Recorded[ENDCOLOR] [ICON_GOLD] \xea\xb0\x80\xeb\x82\x98 [NEWLINE] actual writer order turn 9 before turn 7.\r\n[COLOR:80:180:255:255]blue[/COLOR] [UNKNOWN] literal \xf0\x9f\x98\x80";
    seed.m_listPlayerInfo[0].m_eCivilization=firstCivilization;seed.m_listPlayerInfo[1].m_eCivilization=secondCivilization;
    seed.m_listReplayMessages[1].m_strText=std::string(2000,'A');FDataStream source;seed.write(source);const auto raw=source.bytes;
    MenuReplayView view(raw,labels,palette);Check(view.Available(),"Exact SDK writer stream did not parse");
    const auto messages=view.Scene(*assets);SceneCheck(messages);Check(!Has(messages,MenuReplayView::KeyBase+7),"Hidden map option remained clickable");
    Check(view.RichMessages() && view.RichMessages()->PageCount()>1 && view.RichMessages()->Block(0).text.Original()==seed.m_listReplayMessages[0].m_strText,"Source rich paragraph/order did not survive actual rendering");
    Check(view.RichMessages()->Block(0).text.Prefix()=="9 - ","Messages were sorted away from original vector order");
    std::size_t icons=0;for(const auto& run:view.RichMessages()->Block(0).text.Runs())if(run.kind==MenuReplayRichText::Kind::Icon)++icons;
    Check(icons==1,"Actual original icon font tag was not recognized");
    ZeroSisPresentation::BitmapInputEvent event{};event.kind=ZeroSisPresentation::BitmapInputKind::ControlClick;event.controlKey=MenuReplayView::KeyBase+7;
    Check(!view.Input(event),"Closed source selector accepted a hidden menu choice");
    const auto messageMaximum=view.MessageViewport()->Maximum(MenuReplayOriginalLayout::At().text.height);
    event.controlKey=MenuReplayView::KeyBase+11;Check(view.Input(event) && view.MessageOffset()>0 && view.MessageOffset()<messageMaximum,"Message arrow did not scroll the continuous source stack");
    const auto scrolledMessages=view.Scene(*assets);SceneCheck(scrolledMessages);const auto messageThumb=ScrollThumb(scrolledMessages,MenuReplayView::MessageSeekKey);
    const auto oldMessageOffset=view.MessageOffset();
    event.controlKey=MenuReplayView::MessageSeekKey;event.kind=ZeroSisPresentation::BitmapInputKind::ControlDrag;
    event.pointerPressId=1;event.pointerPressY=messageThumb.y+messageThumb.height*.5f;event.logicalY=event.pointerPressY;
    Check(view.Input(event) && view.MessageOffset()==oldMessageOffset && view.ScrollDragging(),"Message shuttle jumped at its original thumb center");
    event.logicalY=1000;Check(view.Input(event) && view.MessageOffset()==messageMaximum,"Continuous message scrollbar did not reach the original stack end");
    Check(SameInput(scrolledMessages,view.Scene(*assets)),"Message drag changed native input geometry before capture release");
    event.logicalY=std::numeric_limits<float>::quiet_NaN();Check(!view.Input(event),"Message scrollbar accepted nonfinite input");
    Check(view.PointerCapture(false) && !view.ScrollDragging(),"Message capture cancellation did not release its transient gesture");
    event={};event.kind=ZeroSisPresentation::BitmapInputKind::Scroll;event.controlKey=MenuReplayView::MessageScrollKey;event.scrollDelta=-.5f;
    Check(view.Input(event) && std::abs(view.MessageOffset()-(messageMaximum-.5))<1e-8,"Message wheel rounded a fractional source stack offset into pages");
    SceneCheck(view.Scene(*assets));
    Select(view,*assets,MenuReplayView::KeyBase+7);const auto map=view.Scene(*assets);SceneCheck(map);
    const auto mapThumb=ScrollThumb(map,MenuReplayView::SeekKey);Check(mapThumb.width==32 && mapThumb.height==32,"Original map Slider32 shuttle dimensions changed");
    event={};event.kind=ZeroSisPresentation::BitmapInputKind::ControlClick;event.controlKey=MenuReplayView::SeekKey;event.logicalX=1210;
    Check(view.Input(event) && view.Timeline()->Turn()==9 && view.Timeline()->Frame().plots[1].cityOwner==-1,"Original 500px Map slider did not apply recorded final events");
    event.kind=ZeroSisPresentation::BitmapInputKind::ControlDrag;event.logicalX=710;Check(view.Input(event) && view.Timeline()->Turn()==7,"Original Map slider drag did not restore first frame");
    Check(view.PointerCapture(false),"Map drag capture did not end before playback");
    event.kind=ZeroSisPresentation::BitmapInputKind::ControlClick;event.controlKey=MenuReplayView::KeyBase+1;Check(view.Input(event) && view.Advance(.25) && view.Timeline()->Turn()==8,"Recorded four-frame playback failed");
    Check(view.Input(event) && !view.Advance(1),"Paused map playback advanced");
    const auto middleMap=view.Scene(*assets);const auto middleThumb=ScrollThumb(middleMap,MenuReplayView::SeekKey);
    event={};event.kind=ZeroSisPresentation::BitmapInputKind::ControlDrag;event.controlKey=MenuReplayView::SeekKey;
    event.pointerPressId=2;event.pointerPressX=middleThumb.x+16;event.logicalX=event.pointerPressX;
    Check(view.Input(event) && view.Timeline()->Turn()==8,"Map thumb down re-quantized its existing source turn");
    event.logicalX+=1;Check(view.Input(event) && view.Timeline()->Turn()==8 && SameInput(middleMap,view.Scene(*assets)),"Map drag lost capture geometry or original floor policy");
    event.kind=ZeroSisPresentation::BitmapInputKind::ControlClick;Check(view.Input(event) && !view.ScrollDragging(),"Map release did not retire its physical press");
    event.pointerPressId=3;event.logicalX=710+16+468*.4f;
    Check(view.Input(event) && view.Timeline()->Turn()==7,"Map slider rounded to nearest instead of the original floor callback");
    // Original TurnSlider WheelSteps=10 on the recorded 7..9 interval: each
    // message is one binary32 10% step from the re-seeded turn fraction.
    const auto wheelMap=view.Scene(*assets);SceneCheck(wheelMap);const auto sliderBounds=MenuReplayOriginalLayout::At().slider;
    Check(wheelMap.scrolls.size()==1 && wheelMap.scrolls[0].controlKey==MenuReplayView::TurnScrollKey &&
        wheelMap.scrolls[0].bounds[0]==sliderBounds.x && wheelMap.scrolls[0].bounds[1]==sliderBounds.y &&
        wheelMap.scrolls[0].bounds[2]==sliderBounds.Right() && wheelMap.scrolls[0].bounds[3]==sliderBounds.Bottom(),"Original TurnSlider wheel surface differs from its slider");
    ZeroSisPresentation::BitmapInputEvent mapWheel{};mapWheel.kind=ZeroSisPresentation::BitmapInputKind::Scroll;mapWheel.controlKey=MenuReplayView::TurnScrollKey;
    mapWheel.scrollDelta=48;Check(view.Input(mapWheel) && view.Timeline()->Turn()==7,"Forward wheel escaped the original short-replay floor stall");
    event={};event.kind=ZeroSisPresentation::BitmapInputKind::ControlClick;event.controlKey=MenuReplayView::SeekKey;event.logicalX=1210;
    Check(view.Input(event) && view.Timeline()->Turn()==9,"Map slider setup for wheel failed");
    mapWheel.scrollDelta=-4800;Check(view.Input(mapWheel) && view.Timeline()->Turn()==8,"Wheel magnitude was not one original step per message");
    mapWheel.scrollDelta=-48;Check(view.Input(mapWheel) && view.Timeline()->Turn()==7,"Backward wheel differs from the original slider");
    Check(view.Input(mapWheel) && view.Timeline()->Turn()==7,"Clamped wheel at the first turn was not consumed");
    mapWheel.scrollDelta=std::numeric_limits<float>::quiet_NaN();Check(!view.Input(mapWheel) && view.Timeline()->Turn()==7,"Nonfinite wheel delta moved the replay");
    mapWheel.scrollDelta=-48;
    Select(view,*assets,MenuReplayView::KeyBase+8);const auto graph=view.Scene(*assets);SceneCheck(graph);
    Check(!view.Input(mapWheel) && view.Timeline()->Turn()==7,"Hidden map TurnSlider consumed graph wheel input");
    CheckPointerLines(graph,view);Check(PointerLines(graph).empty(),"Replay drew guides before any valid pointer sample");
    event={};event.kind=ZeroSisPresentation::BitmapInputKind::PointerMove;event.logicalX=1019.25f;event.logicalY=552.5f;
    Check(view.Input(event),"Zero-key graph pointer coordinates did not request a redraw");
    const auto hoverGraph=view.Scene(*assets);SceneCheck(hoverGraph);CheckPointerLines(hoverGraph,view);
    Check(SameInput(graph,hoverGraph) && DataLines(hoverGraph).size()==DataLines(graph).size(),"Pointer guides captured input or changed recorded graph data");
    Check(!view.Input(event),"Stationary pointer sampling requested an identical graph repaint");
    Check(!view.PointerCapture(false) && view.PointerGuides().visible,"Ordinary no-capture polling cleared valid pointer guides");
    event.logicalX=660;Check(view.Input(event) && !view.PointerGuides().visible,"Exact graph edge did not hide original strict-inner-bounds guides");
    event.logicalX=1019.25f;Check(view.Input(event),"Pointer guides did not reappear inside the graph");
    event.controlKey=35;event.logicalX=600;event.logicalY=820;
    Check(view.Input(event) && !view.PointerGuides().visible,"Lifecycle Back hover bypassed graph pointer hiding");
    event.controlKey=0;event.logicalX=1019.25f;event.logicalY=552.5f;Check(view.Input(event),"Graph re-entry did not restore pointer guides");
    event.logicalY=std::numeric_limits<float>::quiet_NaN();Check(view.Input(event) && !view.PointerGuides().visible,"Invalid physical pointer sample retained a visible guide");
    event.logicalY=552.5f;Check(view.Input(event),"Finite pointer sample did not recover the graph guide");
    SceneCheck(view.Scene(*assets));
    const auto dates=view.GraphDates();Check(!dates[0].available && !dates[1].available && dates[2].text==L"3720 BC" && dates[3].text==L"3680 BC" && dates[4].text==L"3640 BC",
        "Actual replay calendar/startYear/gameSpeed/turn fields did not bind to all five padded date ticks");
    Check(palette.playerLabels[0].find("[COLOR:")==0 && !originalCaption.empty(),"Actual first civilization caption lost its original color marker fixture");
    const auto& legendFont=assets->FontFace(14,"Shadow");const auto& firstCaptionGlyph=legendFont.glyphs.at(static_cast<std::uint32_t>(originalCaption.front()));
    bool originalCaptionInk=false;const auto legendBounds=MenuReplayOriginalLayout::At().graphLegend;
    for(const auto& sprite:graph.sprites)if(sprite.textureIndex==legendFont.layers[0].texture && sprite.clipRect[0]==legendBounds.x+36 && sprite.clipRect[1]==legendBounds.y+14 &&
        sprite.sourceRect[0]==firstCaptionGlyph.u && sprite.sourceRect[1]==firstCaptionGlyph.v &&
        std::abs(sprite.tintRGBA[0]-originalCaptionRgba[0])<1e-6f && std::abs(sprite.tintRGBA[1]-originalCaptionRgba[1])<1e-6f &&
        std::abs(sprite.tintRGBA[2]-originalCaptionRgba[2])<1e-6f && std::abs(sprite.tintRGBA[3]-originalCaptionRgba[3])<1e-6f)originalCaptionInk=true;
    Check(originalCaptionInk,"Original localized rich civilization name printed color tags or multiplied its exact ink by Beige");
    bool selectedLegendColor=false,selectedGraphColor=false;
    for(const auto& line:graph.lines)if(line.tintRGBA[0]==palette.graphColors[1].r && line.tintRGBA[1]==palette.graphColors[1].g && line.tintRGBA[2]==palette.graphColors[1].b){
        if(line.width==2 && line.start[0]==legendBounds.x+40 && line.start[1]==legendBounds.y+32+8)selectedLegendColor=true;
        if(line.width==1 && line.clipRect[0]==MenuReplayOriginalLayout::At().graph.x)selectedGraphColor=true;
    }
    Check(selectedLegendColor && selectedGraphColor,"Recorded original unique graph palette did not bind to legend and width-one data lines");
    const auto originalLineCount=CheckGraphLines(graph,view.Timeline()->Document(),0);Check(originalLineCount>0,"Original sampled source graph emitted no lines");
    event={};event.kind=ZeroSisPresentation::BitmapInputKind::ControlClick;event.controlKey=MenuReplayView::KeyBase+0x1000;
    Check(view.Input(event),"Visible graph legend callback missing");const auto hiddenFirst=view.Scene(*assets);
    Check(CheckGraphLines(hiddenFirst,view.Timeline()->Document(),0,{0})<originalLineCount,"Hidden graph series still rendered");Check(view.Input(event),"Graph series could not be restored");
    event.controlKey=MenuReplayView::KeyBase+13;Check(view.Input(event),"Original Graph dataset dropdown did not open");SceneCheck(view.Scene(*assets));
    event.controlKey=MenuReplayView::KeyBase+0x2001;Check(view.Input(event),"Actual dataset dropdown choice missing");SceneCheck(view.Scene(*assets));
    event.controlKey=MenuReplayView::SeekKey;event.logicalX=800;Check(!view.Input(event) && !view.Advance(1),"Hidden map control consumed graph input");event.controlKey=35;Check(!view.Input(event),"Replay consumed lifecycle Back control");
    Check(view.Timeline()->Document().rawBytes==raw && source.bytes==raw,"Rendered menu changed the original replay bytes");
    const auto directory=std::wstring(argv[3]);Packet(messages,directory+L"\\restored_messages.packet");Packet(map,directory+L"\\restored_map.packet");Packet(hoverGraph,directory+L"\\restored_graph.packet");
    std::size_t maximumSprites=0,maximumPages=0,maximumLines=0,maximumRawPoints=0;
    {
        auto maximum=Seed();maximum.m_listReplayMessages.assign(100000,CvReplayMessage{});maximum.m_listReplayMessages.back().m_strText=std::string(1024*1024,'A');
        FDataStream maximumRaw;maximum.write(maximumRaw);MenuReplayView longView(maximumRaw.bytes,labels,palette);Check(longView.Available(),"Many empty messages/max original paragraph did not parse");
        auto current=longView.Scene(*assets);SceneCheck(current);maximumPages=longView.RichMessages()->PageCount();maximumSprites=current.sprites.size();
        Check(maximumPages>100 && longView.RichMessages()->Blocks().size()==1 && longView.RichMessages()->Block(0).messageIndex==99999,"Empty records produced phantom message pages");
        event={};event.kind=ZeroSisPresentation::BitmapInputKind::ControlDrag;event.controlKey=MenuReplayView::MessageSeekKey;event.logicalY=1000;Check(longView.Input(event),"Long paragraph continuous stack end seek missing");
        current=longView.Scene(*assets);SceneCheck(current);maximumSprites=(std::max)(maximumSprites,current.sprites.size());
        const auto& viewport=*longView.MessageViewport();const auto viewportHeight=MenuReplayOriginalLayout::At().text.height;
        const auto visible=viewport.Visible(longView.MessageOffset(),viewportHeight);
        Check(longView.MessageOffset()==viewport.Maximum(viewportHeight) && visible.last==viewport.RowCount() && visible.first<visible.last &&
            longView.RichMessages()->Block(0).text.Original()==maximum.m_listReplayMessages.back().m_strText,"Maximum raw paragraph was omitted or mutated at its continuous stack end");
        Check(longView.Timeline()->Document().rawBytes==maximumRaw.bytes,"Maximum replay raw bytes changed");
    }
    {
        auto bounds=Seed();bounds.m_iFinalTurn=bounds.m_iInitialTurn+1023;bounds.m_listReplayMessages.clear();bounds.m_listPlayerInfo.resize(64);
        bounds.m_listPlayerInfo[0].m_strCustomLeaderName=std::string(50000,'A');bounds.m_listPlayerInfo[1].m_strCustomLeaderName="\xf0\x9f\x98\x80";
        bounds.m_listPlayerDataSets.assign(64,CvReplayInfo::TurnDataSets(1));for(auto& player:bounds.m_listPlayerDataSets)for(unsigned turn=0;turn<1024;++turn)player[0][turn]=(turn&1)?INT_MAX:INT_MIN;
        for(auto& plot:bounds.m_listPlots){const auto state=plot.begin()->second;plot.clear();plot[static_cast<unsigned>(bounds.m_iFinalTurn)]=state;}
        MenuReplayPalette boundPalette=palette;
        boundPalette.playerLabels[0]=bounds.m_listPlayerInfo[0].m_strCustomLeaderName;
        boundPalette.playerLabels[1]=bounds.m_listPlayerInfo[1].m_strCustomLeaderName;
        FDataStream boundRaw;bounds.write(boundRaw);MenuReplayView boundView(boundRaw.bytes,labels,boundPalette);Check(boundView.Available(),"Maximum graph input did not parse");
        SceneCheck(boundView.Scene(*assets));Select(boundView,*assets,MenuReplayView::KeyBase+8);const auto current=boundView.Scene(*assets);SceneCheck(current);maximumSprites=(std::max)(maximumSprites,current.sprites.size());
        std::size_t points=0;for(const auto& player:boundView.Timeline()->Document().players)points+=player.dataSets[0].size();
        maximumRawPoints=points;maximumLines=CheckGraphLines(current,boundView.Timeline()->Document(),0);
        Check(points==65536 && maximumLines==6400 && current.lines.size()<=ZeroSisPresentation::kMaxSceneLines && current.sprites.size()<300000,
            "Original 100-segment-per-player graph changed raw records or exceeded the production line bound");
        Check(boundView.Timeline()->Document().players[0].leaderName.size()==50000 && boundView.Timeline()->Document().players[1].leaderName=="\xf0\x9f\x98\x80" && boundView.Timeline()->Document().rawBytes==boundRaw.bytes,"Bounded legend changed raw long/supplementary player names");
        event={};event.kind=ZeroSisPresentation::BitmapInputKind::ControlClick;event.controlKey=MenuReplayView::KeyBase+0x1000+63;Check(!boundView.Input(event),"Hidden legend page consumed another player's toggle");
        Check(current.scrolls.size()==1 && current.scrolls[0].controlKey==MenuReplayView::LegendScrollKey && Has(current,MenuReplayView::LegendSeekKey),"Original graph legend scroll viewport/slider missing");
        event.kind=ZeroSisPresentation::BitmapInputKind::ControlDrag;event.controlKey=MenuReplayView::LegendSeekKey;event.logicalY=1000;
        Check(boundView.Input(event) && boundView.LegendOffset()==1666,"Legend slider did not reach the exact original stack lower bound");
        Check(boundView.LegendDragging() && SameInput(current,boundView.Scene(*assets)),"Captured legend drag changed native input geometry before release");
        Check(boundView.PointerCapture(false) && !boundView.LegendDragging(),"Native capture release/cancel did not commit the new legend input geometry");
        const auto last=boundView.Scene(*assets);SceneCheck(last);Check(Has(last,MenuReplayView::KeyBase+0x1000+63) && !Has(last,MenuReplayView::KeyBase+0x1000),"Legend viewport left hidden-row callbacks active");
        event.kind=ZeroSisPresentation::BitmapInputKind::ControlClick;event.controlKey=MenuReplayView::KeyBase+0x1000+63;Check(boundView.Input(event),"Final visible legend checkbox did not toggle its recorded series");
        event.kind=ZeroSisPresentation::BitmapInputKind::Scroll;event.controlKey=MenuReplayView::LegendScrollKey;event.scrollDelta=-100000;
        Check(boundView.Input(event) && boundView.LegendOffset()==0,"Legend wheel did not clamp to exact original upper stack bound");
        event.scrollDelta=std::numeric_limits<float>::quiet_NaN();Check(!boundView.Input(event),"Legend wheel accepted nonfinite input");
        event.kind=ZeroSisPresentation::BitmapInputKind::ControlDrag;event.controlKey=MenuReplayView::LegendSeekKey;event.logicalY=std::numeric_limits<float>::infinity();Check(!boundView.Input(event),"Legend slider accepted nonfinite coordinates");
        event={};event.kind=ZeroSisPresentation::BitmapInputKind::KeyDown;event.virtualKey=0x23;Check(boundView.Input(event) && boundView.LegendOffset()==1666,"Legend keyboard End did not select final original scroll extent");
        Select(boundView,*assets,MenuReplayView::KeyBase+7);event.kind=ZeroSisPresentation::BitmapInputKind::Scroll;event.controlKey=MenuReplayView::LegendScrollKey;event.scrollDelta=-32;
        Check(!boundView.Input(event),"Hidden graph legend consumed Map wheel input");
    }
    {
        auto scrolling=Seed();scrolling.m_listPlayerInfo.resize(16);scrolling.m_listPlayerDataSets.resize(16);
        FDataStream scrollingRaw;scrolling.write(scrollingRaw);MenuReplayView drag(scrollingRaw.bytes,labels,palette);
        Select(drag,*assets,MenuReplayView::KeyBase+8);SceneCheck(drag.Scene(*assets));std::uint64_t press=100;
        for(const float start:{0.0f,65.0f,130.0f}){
            event={};event.kind=ZeroSisPresentation::BitmapInputKind::Scroll;event.controlKey=MenuReplayView::LegendScrollKey;event.scrollDelta=start-drag.LegendOffset();drag.Input(event);
            const auto before=drag.Scene(*assets);const auto thumb=LegendThumb(before);const auto travel=344-thumb.height;
            Check(travel>0 && std::abs(drag.LegendOffset()-start)<.001f,"16-player legend fixture did not reach source scroll position");
            event={};event.kind=ZeroSisPresentation::BitmapInputKind::ControlDrag;event.controlKey=MenuReplayView::LegendSeekKey;
            event.pointerPressId=++press;event.pointerPressY=thumb.y+thumb.height*.5f;event.logicalY=event.pointerPressY;
            Check(drag.Input(event) && drag.LegendDragging() && std::abs(drag.LegendOffset()-start)<.001f,"Native down at thumb center changed its source offset");
            event.logicalY+=3;Check(drag.Input(event),"Native drag move was not routed");
            const auto expected=(std::min)(130.0f,start+3*130/travel);
            Check(std::abs(drag.LegendOffset()-expected)<.002f && SameInput(before,drag.Scene(*assets)),"Native drag travel or input-geometry retention differs from rendered shuttle");
            event.kind=ZeroSisPresentation::BitmapInputKind::ControlClick;Check(drag.Input(event) && !drag.LegendDragging(),"Native release Click did not end its original drag gesture");
            const auto after=drag.Scene(*assets);SceneCheck(after);
            if(expected!=start)Check(!SameInput(before,after),"Released legend retained stale checkbox positions");
            const auto nextThumb=LegendThumb(after);const float old=drag.LegendOffset();
            event={};event.kind=ZeroSisPresentation::BitmapInputKind::ControlDrag;event.controlKey=MenuReplayView::LegendSeekKey;
            event.pointerPressId=++press;event.pointerPressY=nextThumb.y+nextThumb.height*.25f;event.logicalY=event.pointerPressY-2;
            Check(drag.Input(event) && std::abs(drag.LegendOffset()-(std::max)(0.0f,old-2*130/(344-nextThumb.height)))<.002f,
                "Coalesced first native drag lost the original down-coordinate movement or reused another gesture anchor");
            const auto captured=drag.Scene(*assets);event.kind=ZeroSisPresentation::BitmapInputKind::ControlClick;event.controlKey=35;
            Check(drag.Input(event) && !drag.LegendDragging(),"Release on lifecycle Back escaped a captured scrollbar gesture");
            Check(drag.Timeline()->Document().rawBytes==scrollingRaw.bytes,"Legend gesture changed raw replay history");
            SceneCheck(captured);SceneCheck(drag.Scene(*assets));
        }
    }
    {
        auto hiddenPalette=palette;hiddenPalette.initiallyHiddenPlayers.insert(1);
        MenuReplayView minor(raw,labels,hiddenPalette);Select(minor,*assets,MenuReplayView::KeyBase+8);const auto hidden=minor.Scene(*assets);SceneCheck(hidden);
        const auto& checkbox=assets->TextureNamed("checkbox.dds");bool unchecked=false;
        for(const auto& sprite:hidden.sprites)if(sprite.controlKey==MenuReplayView::KeyBase+0x1001 && sprite.textureIndex==checkbox.index && sprite.sourceRect[1]==0)unchecked=true;
        Check(unchecked && CheckGraphLines(hidden,minor.Timeline()->Document(),0,{1})<originalLineCount,"Original minor-civilization default hidden series/unchecked control was not bound");
        event={};event.kind=ZeroSisPresentation::BitmapInputKind::ControlClick;event.controlKey=MenuReplayView::KeyBase+0x1001;
        Check(minor.Input(event) && DataLines(minor.Scene(*assets)).size()==originalLineCount,"Default hidden recorded minor series could not be enabled");
        event.controlKey=MenuReplayView::KeyBase+0x1000;Check(minor.Input(event),"First series did not hide");
        event.controlKey=MenuReplayView::KeyBase+0x1001;Check(minor.Input(event),"Second series did not hide");
        const auto allHidden=minor.Scene(*assets);SceneCheck(allHidden);
        Check(DataLines(allHidden).empty() && BuildMenuReplayGraphGeometry(minor.Timeline()->Document(),0).hasData && allHidden.lines.size()==hidden.lines.size()-DataLines(hidden).size(),
            "Hiding every series changed the original graph data/scale or left data lines visible");
        event={};event.kind=ZeroSisPresentation::BitmapInputKind::PointerMove;event.logicalX=800;event.logicalY=450;
        Check(minor.Input(event) && minor.PointerGuides().visible,"All-hidden series incorrectly suppressed source pointer guides");CheckPointerLines(minor.Scene(*assets),minor);
        Check(minor.Timeline()->Document().rawBytes==raw,"Minor-series presentation changed replay raw metadata");
    }
    {
        auto empty=Seed();for(auto& player:empty.m_listPlayerDataSets)for(auto& history:player)history.clear();
        FDataStream bytes;empty.write(bytes);MenuReplayView noData(bytes.bytes,labels,palette);Select(noData,*assets,MenuReplayView::KeyBase+8);
        const auto before=noData.Scene(*assets);Check(DataLines(before).empty(),"No-data pointer fixture retained graph samples");
        event={};event.kind=ZeroSisPresentation::BitmapInputKind::PointerMove;event.logicalX=800;event.logicalY=450;
        Check(noData.Input(event) && noData.PointerGuides().visible,"No-data graph incorrectly suppressed original mouse guides");
        const auto shown=noData.Scene(*assets);SceneCheck(shown);CheckPointerLines(shown,noData);Check(SameInput(before,shown),"No-data guides changed the input contract");
        const auto noDataTexture=assets->FontFace(20,"Shadow").layers.front().texture;
        std::size_t firstNoDataGlyph=shown.sprites.size();
        for(std::size_t i=0;i<shown.sprites.size();++i)if(shown.sprites[i].textureIndex==noDataTexture){firstNoDataGlyph=i;break;}
        Check(firstNoDataGlyph<shown.sprites.size(),"Actual original NoGraphData label glyphs were missing");
        for(const auto* line:PointerLines(shown))Check(line->beforeSprite<=firstNoDataGlyph,"Pointer guide was painted above the later source NoGraphData label");
        event.kind=ZeroSisPresentation::BitmapInputKind::ControlClick;event.controlKey=MenuReplayView::KeyBase+12;Check(noData.Input(event),"No-data source popup did not open");
        event.kind=ZeroSisPresentation::BitmapInputKind::PointerMove;event.controlKey=0;event.logicalX=900;
        Check(noData.Input(event) && noData.PointerGuides().visible,"Open source popup added an unsupported guide visibility condition");CheckPointerLines(noData.Scene(*assets),noData);
        Check(noData.Timeline()->Document().rawBytes==bytes.bytes,"Pointer guides changed empty-data raw replay bytes");
    }
    std::set<std::string> actualAtlasNames;
    for(const auto& civ:civilizations){
        auto iconSeed=Seed();iconSeed.m_listPlayerInfo[0].m_eCivilization=civ.first;MenuReplayPalette iconPalette=palette;iconPalette.legendIcons[0]=civ.second.icon;iconPalette.playerLabels[0]=civ.second.label;
        FDataStream iconRaw;iconSeed.write(iconRaw);MenuReplayView iconView(iconRaw.bytes,labels,iconPalette);Select(iconView,*assets,MenuReplayView::KeyBase+8);
        const auto rendered=iconView.Scene(*assets);SceneCheck(rendered);const auto& atlas=assets->TextureNamed(civ.second.icon.texture);bool portrait=false;
        const float u=float((civ.second.icon.portrait%civ.second.icon.columns)*32),v=float((civ.second.icon.portrait/civ.second.icon.columns)*32);
        for(const auto& sprite:rendered.sprites)if(sprite.textureIndex==atlas.index && sprite.sourceRect[0]==u && sprite.sourceRect[1]==v && sprite.sourceRect[2]==u+32 && sprite.sourceRect[3]==v+32)portrait=true;
        Check(portrait && iconView.Timeline()->Document().rawBytes==iconRaw.bytes,"Actual recorded civilization icon crop was omitted or changed the raw history");actualAtlasNames.insert(civ.second.icon.texture);
    }
    Check(actualAtlasNames.size()==10,"Actual original civilization atlas coverage narrowed");
    auto invalid=raw;invalid[0]=3;MenuReplayView unsupported(invalid,labels,palette);Check(!unsupported.Available(),"Unknown wrapper was accepted");SceneCheck(unsupported.Scene(*assets));
    std::cout<<"{\"status\":\"PASS_SDK_FREE_REPLAY_ORIGINAL_LAYOUT_RICHTEXT_SCENE_INPUT_AND_BOUNDS\",\"checks\":"<<checks
        <<",\"actual_assets\":true,\"synthetic_fixture_history\":true,\"recorded_graph_points\":"<<maximumRawPoints<<",\"original_sampled_data_lines\":"<<maximumLines
        <<",\"maximum_scene_sprites\":"<<maximumSprites<<",\"maximum_text_bytes\":1048576,\"legacy_layout_catalog_pages\":"<<maximumPages<<",\"continuous_message_scroll_bound\":true,\"map_source_floor_bound\":true"
        <<",\"original_civilization_atlases\":"<<actualAtlasNames.size()<<",\"five_date_ticks_bound\":true,\"original_legend_scroll_input\":true"
        <<",\"original_four_pointer_guides_bound\":true,\"zero_key_pointer_and_no_capture_regression\":true"
        <<",\"native_host_sdk_window_gpu_executed\":false}"<<std::endl;return 0;
}catch(const std::exception& error){std::cerr<<error.what()<<std::endl;return 1;}}
