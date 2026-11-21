#pragma once
#if defined(ZEROSIS_UI_WINDOW_PRESENTATION)
#include "GameCoreSession.h"
#include "InteractiveGameSession.h"
#include "EconomicOverviewSmokeFixture.h"
#include "SdkStateSnapshot.h"
#include "../Presentation/BitmapWindow.h"
#include "../Presentation/BitmapEditorInput.h"
#include "../Presentation/WorldViewRenderer.h"
#if defined(ZEROSIS_WORLD_TERRAIN)
#include "../Presentation/WorldTerrainRenderer.h"
#endif
#include <chrono>
#include <sstream>
#include <iterator>

namespace ZeroSisHost {
namespace InteractiveGameDetail {
constexpr std::uint64_t kNotificationPanelKeyBase=1ull<<50;
inline std::uint64_t NotificationPanelKey(std::uint64_t local){
    if(!local || local>=(1ull<<32))throw std::out_of_range("NotificationPanel control key exceeds its private input namespace");
    return kNotificationPanelKeyBase+local;
}
constexpr std::uint64_t kTopPanelKeyBase=1ull<<51;
constexpr std::uint64_t kActionInfoPanelKeyBase=1ull<<52;
inline std::uint64_t ActionInfoPanelKey(std::uint64_t local){
    if(!local || local>=(1ull<<32))throw std::out_of_range("ActionInfoPanel control key exceeds its private input namespace");
    return kActionInfoPanelKeyBase+local;
}
inline std::uint64_t TopPanelKey(std::uint64_t local){
    if(!local || local>=(1ull<<32))throw std::out_of_range("TopPanel control key exceeds its private input namespace");
    return kTopPanelKeyBase+local;
}
inline std::wstring Wide(const std::string& text){
    if(text.size()>static_cast<std::size_t>(INT_MAX))throw std::length_error("World text is too long");
    if(text.empty())return {};
    const int size=MultiByteToWideChar(CP_UTF8,MB_ERR_INVALID_CHARS,text.data(),static_cast<int>(text.size()),nullptr,0);
    if(size<=0)throw std::runtime_error("World text is not strict UTF-8");
    std::wstring result(static_cast<std::size_t>(size),L'\0');
    if(MultiByteToWideChar(CP_UTF8,MB_ERR_INVALID_CHARS,text.data(),static_cast<int>(text.size()),&result[0],size)!=size)
        throw std::runtime_error("World text conversion failed");return result;
}
inline void Write(const std::wstring& path,const std::string& bytes){
    struct Handle {HANDLE value=INVALID_HANDLE_VALUE;~Handle(){if(value!=INVALID_HANDLE_VALUE)CloseHandle(value);}} file;
    if(bytes.size()>32u*1024u*1024u)throw std::length_error("World frame metadata exceeds 32 MiB");
    file.value=CreateFileW(path.c_str(),GENERIC_WRITE,0,nullptr,CREATE_ALWAYS,FILE_ATTRIBUTE_NORMAL,nullptr);
    DWORD written=0;
    if(file.value==INVALID_HANDLE_VALUE || !WriteFile(file.value,bytes.data(),static_cast<DWORD>(bytes.size()),&written,nullptr) ||
       written!=bytes.size() || !FlushFileBuffers(file.value))throw std::runtime_error("Cannot persist world frame metadata");
}
inline ZeroSisPresentation::WorldView Present(const WorldViewState& state,int cameraX,int cameraY,const std::wstring& status,int selectedCity=-1){
    ZeroSisPresentation::WorldView result{};
    result.gridWidth=state.gridWidth;result.gridHeight=state.gridHeight;result.turn=state.turn;result.activePlayer=state.activePlayer;
    result.wrapX=state.wrapX;result.wrapY=state.wrapY;result.cameraX=cameraX;result.cameraY=cameraY;result.status=status;result.selectedCity=selectedCity;
    result.mapRandomSeed=state.mapRandomSeed;
    for(const auto& plot:state.plots)result.plots.push_back({plot.index,plot.x,plot.y,plot.revealed,plot.visible,
        plot.water,plot.hills,plot.mountain,plot.terrainType,plot.featureType,plot.improvementType,plot.routeType,
        plot.improvementPillaged,plot.routePillaged,Wide(plot.improvementName),Wide(plot.routeName),plot.continent,plot.terrainId,plot.naturalWonder,
        plot.lake,plot.riverW,plot.riverNW,plot.riverNE,plot.flowE,plot.flowSE,plot.flowSW});
    const auto appendUnits=[&](const std::vector<WorldViewState::Unit>& units){
        for(const auto& unit:units){
            ZeroSisPresentation::WorldViewUnit presented{unit.id,unit.owner,unit.x,unit.y,unit.moves,unit.damage,
                unit.selected,Wide(unit.name),unit.maxHitPoints,unit.hostile};
            presented.unitType=unit.unitType;presented.civilizationType=unit.civilizationType;
            presented.artStyleType=unit.artStyleType;presented.ownerEra=unit.ownerEra;
            presented.facingDirection=unit.facingDirection;presented.type=unit.type;
            presented.unitArtInfoTag=unit.unitArtInfoTag;presented.artStylePrefix=unit.artStylePrefix;
            presented.artStyleSuffix=unit.artStyleSuffix;presented.eraArtPrefix=unit.eraArtPrefix;
            presented.unitArtInfoCulturalVariation=unit.unitArtInfoCulturalVariation;
            presented.unitArtInfoEraVariation=unit.unitArtInfoEraVariation;presented.embarked=unit.embarked;
            result.units.push_back(std::move(presented));
        }
    };
    appendUnits(state.ownedUnits);appendUnits(state.visibleForeignUnits);
    for(const auto& city:state.visibleCities)result.cities.push_back({city.id,city.owner,city.x,city.y,Wide(city.name),city.rawName});
    return result;
}
inline std::string Metadata(const WorldViewState& state,const ZeroSisPresentation::Scene& scene,std::uint64_t generation,
                           const std::vector<InteractiveGameSession::UnitAction>& actions,int actionPage,const std::string& pixelFile,
                           bool originalUnitPanel){
    std::ostringstream output;output<<"{\"turn\":"<<state.turn<<",\"elapsed\":"<<state.elapsedTurns
        <<",\"activePlayer\":"<<state.activePlayer<<",\"gridWidth\":"<<state.gridWidth<<",\"gridHeight\":"<<state.gridHeight
        <<",\"generation\":"<<generation<<",\"originalUnitPanel\":"<<(originalUnitPanel?"true":"false")<<",\"units\":[";
    bool first=true;for(const auto& unit:state.ownedUnits){if(!first)output<<',';first=false;
        output<<"{\"id\":"<<unit.id<<",\"owner\":"<<unit.owner<<",\"x\":"<<unit.x<<",\"y\":"<<unit.y
            <<",\"moves\":"<<unit.moves<<",\"damage\":"<<unit.damage<<",\"maxHitPoints\":"<<unit.maxHitPoints
            <<",\"selected\":"<<(unit.selected?"true":"false")
            <<",\"unitTypeId\":"<<unit.unitType<<",\"unitType\":"<<UiSnapshotJson::Quote(unit.type)
            <<",\"unitArtInfoTag\":"<<UiSnapshotJson::Quote(unit.unitArtInfoTag)
            <<",\"unitArtInfoCulturalVariation\":"<<(unit.unitArtInfoCulturalVariation?"true":"false")
            <<",\"unitArtInfoEraVariation\":"<<(unit.unitArtInfoEraVariation?"true":"false")
            <<",\"civilizationType\":"<<unit.civilizationType<<",\"artStyleType\":"<<unit.artStyleType
            <<",\"artStylePrefix\":"<<UiSnapshotJson::Quote(unit.artStylePrefix)
            <<",\"artStyleSuffix\":"<<UiSnapshotJson::Quote(unit.artStyleSuffix)
            <<",\"ownerEra\":"<<unit.ownerEra<<",\"eraArtPrefix\":"<<UiSnapshotJson::Quote(unit.eraArtPrefix)
            <<",\"facingDirection\":"<<unit.facingDirection<<",\"embarked\":"<<(unit.embarked?"true":"false")<<'}';}
    output<<"],\"visibleForeignUnits\":[";first=true;
    for(const auto& unit:state.visibleForeignUnits){if(!first)output<<',';first=false;
        output<<"{\"id\":"<<unit.id<<",\"owner\":"<<unit.owner<<",\"x\":"<<unit.x<<",\"y\":"<<unit.y
            <<",\"damage\":"<<unit.damage<<",\"maxHitPoints\":"<<unit.maxHitPoints<<",\"hostile\":"<<(unit.hostile?"true":"false")
            <<",\"unitTypeId\":"<<unit.unitType<<",\"unitType\":"<<UiSnapshotJson::Quote(unit.type)
            <<",\"unitArtInfoTag\":"<<UiSnapshotJson::Quote(unit.unitArtInfoTag)
            <<",\"unitArtInfoCulturalVariation\":"<<(unit.unitArtInfoCulturalVariation?"true":"false")
            <<",\"unitArtInfoEraVariation\":"<<(unit.unitArtInfoEraVariation?"true":"false")
            <<",\"civilizationType\":"<<unit.civilizationType<<",\"artStyleType\":"<<unit.artStyleType
            <<",\"artStylePrefix\":"<<UiSnapshotJson::Quote(unit.artStylePrefix)
            <<",\"artStyleSuffix\":"<<UiSnapshotJson::Quote(unit.artStyleSuffix)
            <<",\"ownerEra\":"<<unit.ownerEra<<",\"eraArtPrefix\":"<<UiSnapshotJson::Quote(unit.eraArtPrefix)
            <<",\"facingDirection\":"<<unit.facingDirection<<",\"embarked\":"<<(unit.embarked?"true":"false")<<'}';}
    output<<"],\"cities\":[";first=true;for(const auto& city:state.visibleCities){if(!first)output<<',';first=false;
        output<<"{\"id\":"<<city.id<<",\"owner\":"<<city.owner<<",\"x\":"<<city.x<<",\"y\":"<<city.y
            <<",\"rawName\":"<<UiSnapshotJson::Quote(city.rawName)<<",\"displayName\":"<<UiSnapshotJson::Quote(city.name)<<'}';}
    output<<"],\"plots\":[";first=true;for(const auto& plot:state.plots){if(!first)output<<',';first=false;
        output<<"["<<plot.index<<','<<plot.x<<','<<plot.y<<','<<(plot.revealed?1:0)<<','<<(plot.visible?1:0)<<']';}
    output<<"],\"plotImprovements\":[";first=true;
    for(const auto& plot:state.plots)if(plot.visible && (plot.improvementType>=0 || plot.routeType>=0)){
        if(!first)output<<',';first=false;
        output<<'['<<plot.index<<','<<plot.improvementType<<','<<plot.routeType<<','<<(plot.improvementPillaged?1:0)
            <<','<<(plot.routePillaged?1:0)<<','<<UiSnapshotJson::Quote(plot.improvementName)<<','<<UiSnapshotJson::Quote(plot.routeName)<<']';
    }
    output<<"],\"unitActionPage\":"<<actionPage<<",\"unitActions\":[";first=true;
    for(std::size_t index=0;index<actions.size();++index){const auto& action=actions[index];if(!first)output<<',';first=false;
        output<<'['<<index<<','<<action.unit<<','<<action.mission<<','<<action.data1<<','<<action.data2<<','<<UiSnapshotJson::Quote(action.name)<<']';}
    output<<"],\"hits\":[";first=true;for(const auto& hit:scene.hits){if(!first)output<<',';first=false;
        output<<'['<<hit.controlKey;for(float value:hit.bounds)output<<','<<value;output<<']';}
    output<<"],\"pixelHitKeys\":[";first=true;for(const auto key:scene.pixelHits.keys){if(!first)output<<',';first=false;output<<key;}
    output<<"],\"pixelHitCount\":"<<scene.pixelHits.indices.size()<<",\"pixelHitFile\":"<<UiSnapshotJson::Quote(pixelFile)<<"}\n";return output.str();
}
inline void RetainPicking(const ZeroSisPresentation::Scene& scene,const std::wstring& path){
    std::string bytes="ZSTPICK1";
    const auto word=[&](std::uint32_t value){for(unsigned shift=0;shift<32;shift+=8)bytes.push_back(static_cast<char>((value>>shift)&255));};
    word(scene.width);word(scene.height);word(static_cast<std::uint32_t>(scene.pixelHits.keys.size()));
    for(const auto key:scene.pixelHits.keys){word(static_cast<std::uint32_t>(key));word(static_cast<std::uint32_t>(key>>32));}
    for(std::size_t start=0;start<scene.pixelHits.indices.size();){
        const auto index=scene.pixelHits.indices[start];std::size_t end=start+1;
        while(end<scene.pixelHits.indices.size()&&scene.pixelHits.indices[end]==index)++end;
        word(static_cast<std::uint32_t>(end-start));word(index);start=end;
    }
    Write(path,bytes);
}
inline bool PostClick(ZeroSisPresentation::BitmapWindow& window,const ZeroSisPresentation::Scene& scene,std::uint64_t key,bool right=false,bool shift=false){
    const auto post=[&](float lx,float ly){
        RECT client{};if(!GetClientRect(window.NativeHandle(),&client))throw std::runtime_error("Cannot inspect gameplay client bounds");
        const auto rect=ZeroSisPresentation::BitmapWindow::ComputeDisplayRect(static_cast<std::uint32_t>(client.right),static_cast<std::uint32_t>(client.bottom));
        const int x=static_cast<int>(rect.left+lx*(rect.right-rect.left)/1920.0f),y=static_cast<int>(rect.top+ly*(rect.bottom-rect.top)/1080.0f);
        const LPARAM point=static_cast<LPARAM>((static_cast<std::uint32_t>(y)&0xffffu)<<16 | (static_cast<std::uint32_t>(x)&0xffffu));
        const WPARAM modifiers=shift?MK_SHIFT:0;
        if(!PostMessageW(window.NativeHandle(),right?WM_RBUTTONDOWN:WM_LBUTTONDOWN,(right?MK_RBUTTON:MK_LBUTTON)|modifiers,point) ||
           !PostMessageW(window.NativeHandle(),right?WM_RBUTTONUP:WM_LBUTTONUP,modifiers,point))
            throw std::runtime_error("Cannot post the bounded gameplay smoke input");
        std::printf("INTERACTIVE_SMOKE_BUTTON=%llu|%llu|%u|%u\n",static_cast<unsigned long long>(window.SceneGeneration()),
            static_cast<unsigned long long>(key),right?5u:1u,shift?1u:0u);
        std::printf("INTERACTIVE_SMOKE_POSTED=%llu|%llu|%d|%d\n",static_cast<unsigned long long>(window.SceneGeneration()),static_cast<unsigned long long>(key),x,y);return true;
    };
    for(const auto& hit:scene.hits)if(hit.controlKey==key)
        return post((hit.bounds[0]+hit.bounds[2])*0.5f,(hit.bounds[1]+hit.bounds[3])*0.5f);
    const auto found=std::find(scene.pixelHits.keys.begin(),scene.pixelHits.keys.end(),key);
    if(found==scene.pixelHits.keys.end() || scene.pixelHits.indices.size()!=static_cast<std::size_t>(scene.width)*scene.height)return false;
    const auto index=static_cast<std::uint32_t>(found-scene.pixelHits.keys.begin()+1);
    // A 7x7 same-ID interior survives integer client-coordinate rounding. UI
    // rectangles are checked first, just as the native window does.
    for(unsigned y=3;y+3<scene.height;++y)for(unsigned x=3;x+3<scene.width;++x){
        if(scene.pixelHits.indices[static_cast<std::size_t>(y)*scene.width+x]!=index)continue;
        bool inside=true;for(int dy=-3;dy<=3&&inside;++dy)for(int dx=-3;dx<=3;++dx)
            if(scene.pixelHits.indices[static_cast<std::size_t>(static_cast<int>(y)+dy)*scene.width+static_cast<unsigned>(static_cast<int>(x)+dx)]!=index){inside=false;break;}
        if(!inside)continue;
        const float lx=static_cast<float>(x)+0.5f,ly=static_cast<float>(y)+0.5f;
        if(std::any_of(scene.hits.begin(),scene.hits.end(),[&](const ZeroSisPresentation::HitRecord& hit){
            return lx>=hit.bounds[0]-3 && lx<hit.bounds[2]+3 && ly>=hit.bounds[1]-3 && ly<hit.bounds[3]+3;}))continue;
        return post(lx,ly);
    }
    return false;
}
inline void EmitDecision(const char* marker,const std::array<int,12>& values){
    std::printf("%s=",marker);for(std::size_t i=0;i<values.size();++i)std::printf("%s%d",i?",":"",values[i]);std::puts("");
}
inline void PostTradeRouteWheel(ZeroSisPresentation::BitmapWindow& window,const ZeroSisPresentation::Scene& scene){
    if(scene.scrolls.size()!=1)throw std::runtime_error("TradeRoute smoke requires its sole original MainScroll target");
    const auto& hit=scene.scrolls.front();
    RECT client{};if(!GetClientRect(window.NativeHandle(),&client))throw std::runtime_error("Cannot inspect trade-route client bounds");
    const auto rect=ZeroSisPresentation::BitmapWindow::ComputeDisplayRect(static_cast<std::uint32_t>(client.right),static_cast<std::uint32_t>(client.bottom));
    POINT point{static_cast<LONG>(rect.left+(hit.bounds[0]+hit.bounds[2])*0.5f*(rect.right-rect.left)/1920.0f),
                static_cast<LONG>(rect.top+(hit.bounds[1]+hit.bounds[3])*0.5f*(rect.bottom-rect.top)/1080.0f)};
    if(!ClientToScreen(window.NativeHandle(),&point))throw std::runtime_error("Cannot map trade-route wheel target to screen coordinates");
    const LPARAM position=static_cast<LPARAM>((static_cast<std::uint32_t>(point.y)&0xffffu)<<16 | (static_cast<std::uint32_t>(point.x)&0xffffu));
    if(!PostMessageW(window.NativeHandle(),WM_MOUSEWHEEL,MAKEWPARAM(0,static_cast<WORD>(-WHEEL_DELTA)),position))
        throw std::runtime_error("Cannot post original trade-route wheel input");
    std::printf("INTERACTIVE_TRADE_ROUTE_WHEEL=%llu|%llu|-120\n",static_cast<unsigned long long>(window.SceneGeneration()),
        static_cast<unsigned long long>(hit.controlKey));
}
inline unsigned RejectPending(ZeroSisPresentation::BitmapWindow& window,bool& closeRequested,std::wstring& error,std::uint64_t pointerGeneration=0,
                              ZeroSisPresentation::BitmapEditorInputBuffer* editorInput=nullptr){
    std::vector<ZeroSisPresentation::BitmapInputEvent> rejected;unsigned pointers=0;
    if(!ZeroSisPresentation::DrainBitmapPreparationInputs(window,closeRequested,rejected,pointers,&error,
        pointerGeneration,editorInput))throw std::runtime_error(Utf8(error));
    for(const auto& input:rejected)
        std::printf("INTERACTIVE_STALE_INPUT_REJECTED=%llu\n",static_cast<unsigned long long>(input.sceneGeneration));
    return pointers;
}
inline void WaitForUiPacket(ZeroSisPresentation::BitmapWindow& window,unsigned sequence,bool& closeRequested,std::wstring& error,
                            ZeroSisPresentation::BitmapEditorInputBuffer* editorInput=nullptr){
    const auto input=GetStdHandle(STD_INPUT_HANDLE);
    if(input==INVALID_HANDLE_VALUE || GetFileType(input)!=FILE_TYPE_PIPE)
        throw std::runtime_error("Interactive UI needs the prepared launcher scene driver");
    const auto started=std::chrono::steady_clock::now();std::string reply;
    for(;;){
        // The persistent top bar is prepared before the first HWND is shown.
        // Later requests keep pumping the already owned gameplay window.
        if(window.NativeHandle()){
            if(!window.PumpMessages(&error))throw std::runtime_error(Utf8(error));
            RejectPending(window,closeRequested,error,0,editorInput);
            if(!window.IsOpen())closeRequested=true;
        }
        DWORD available=0;
        if(!PeekNamedPipe(input,nullptr,0,nullptr,&available,nullptr))
            throw std::runtime_error("Interactive UI scene driver disconnected");
        if(available){
            char byte=0;DWORD read=0;
            if(!ReadFile(input,&byte,1,&read,nullptr) || read!=1)throw std::runtime_error("Interactive UI scene acknowledgement failed");
            reply.push_back(byte);
            if(reply.size()>128)throw std::length_error("Interactive UI scene acknowledgement is too long");
            if(byte=='\n'){
                if(reply!="UI_READY|"+std::to_string(sequence)+"\n")throw std::runtime_error("Interactive UI scene driver reported a failed or mismatched revision");
                return;
            }
        }else MsgWaitForMultipleObjectsEx(0,nullptr,16,QS_ALLINPUT,MWMO_INPUTAVAILABLE);
        if(std::chrono::steady_clock::now()-started>std::chrono::seconds(60))
            throw std::runtime_error("Interactive UI asset preparation exceeded its finite deadline");
    }
}
}

// Persistent window loop, shared by manual --play and the finite posted-input
// smoke driver. No SDK calls occur in WndProc or while waiting for input.
inline InteractiveGameSession::LoadHandoff RunInteractiveGameLoop(Session& session,HostState& host,InteractiveGameSession& live,const std::wstring& directory,bool smoke,const std::wstring& checkpoint,const std::wstring& unitAssetsPath,bool unitAnimation=false,std::shared_ptr<const NativeSaveArchive> decodedArchive={}){
    using namespace ZeroSisPresentation;using namespace InteractiveGameDetail;
    if(decodedArchive && checkpoint.empty())throw std::invalid_argument("Decoded interactive restore requires its diagnostic source name");
    const std::wstring fogAssetsPath=[](){
        const DWORD count=GetEnvironmentVariableW(L"ZEROSIS_FOG_ASSETS",nullptr,0);
        if(!count)return std::wstring();
        if(count>32768)throw std::invalid_argument("Original fog asset path exceeds its bound");
        std::wstring value(count,L'\0');const DWORD copied=GetEnvironmentVariableW(L"ZEROSIS_FOG_ASSETS",&value[0],count);
        if(!copied || copied>=count)throw std::invalid_argument("Original fog asset path changed during capture");
        value.resize(copied);return value;
    }();
    const bool fogAnimation=!fogAssetsPath.empty()&&!smoke;
    const std::wstring waterAssetsPath=[](){
        const DWORD count=GetEnvironmentVariableW(L"ZEROSIS_WATER_ASSETS",nullptr,0);
        if(!count)return std::wstring();
        if(count>32768)throw std::invalid_argument("Original water asset path exceeds its bound");
        std::wstring value(count,L'\0');const DWORD copied=GetEnvironmentVariableW(L"ZEROSIS_WATER_ASSETS",&value[0],count);
        if(!copied || copied>=count)throw std::invalid_argument("Original water asset path changed during capture");
        value.resize(copied);return value;
    }();
    const bool waterAnimation=!waterAssetsPath.empty()&&!smoke;
    const std::wstring waterSurfaceAssetsPath=[](){
        const DWORD count=GetEnvironmentVariableW(L"ZEROSIS_WATER_SURFACE_ASSETS",nullptr,0);
        if(!count)return std::wstring();
        if(count>32768)throw std::invalid_argument("Water surface asset path exceeds its bound");
        std::wstring value(count,L'\0');const DWORD copied=GetEnvironmentVariableW(L"ZEROSIS_WATER_SURFACE_ASSETS",&value[0],count);
        if(!copied||copied>=count)throw std::invalid_argument("Water surface asset path changed during capture");
        value.resize(copied);return value;
    }();
    if(!waterSurfaceAssetsPath.empty()&&waterAssetsPath.empty())throw std::invalid_argument("Water surface mode requires its original water package");
    const std::wstring lightingAssetsPath=[](){
        const DWORD count=GetEnvironmentVariableW(L"ZEROSIS_LIGHTING_ASSETS",nullptr,0);
        if(!count)return std::wstring();
        if(count>32768)throw std::invalid_argument("Lighting asset path exceeds its bound");
        std::wstring value(count,L'\0');const DWORD copied=GetEnvironmentVariableW(L"ZEROSIS_LIGHTING_ASSETS",&value[0],count);
        if(!copied||copied>=count)throw std::invalid_argument("Lighting asset path changed during capture");
        value.resize(copied);return value;
    }();
    const std::wstring screenLightingAssetsPath=[](){
        const DWORD count=GetEnvironmentVariableW(L"ZEROSIS_SCREEN_LIGHT_ASSETS",nullptr,0);
        if(!count)return std::wstring();
        if(count>32768)throw std::invalid_argument("Screen light asset path exceeds its bound");
        std::wstring value(count,L'\0');const DWORD copied=GetEnvironmentVariableW(L"ZEROSIS_SCREEN_LIGHT_ASSETS",&value[0],count);
        if(!copied||copied>=count)throw std::invalid_argument("Screen light asset path changed during capture");
        value.resize(copied);return value;
    }();
    BitmapWindow window;Scene scene{};WorldViewState world;std::wstring error;
    struct MenuOptionsBindingGuard final {
        HostState& host;
        ~MenuOptionsBindingGuard(){host.applyMenuOptions={};}
    } menuOptionsBindingGuard{host};
#if defined(ZEROSIS_WORLD_TERRAIN)
    struct ReleasePresentation {~ReleasePresentation(){ReleaseWorldTerrainResources();}} releasePresentation;
#endif
    bool redraw=true,closeRequested=false,uiActive=false,mandatoryDecision=false,windowCreated=false;int cameraX=0,cameraY=0,selectedCity=-1;unsigned revision=0,uiRevision=0;
    WorldCameraZoom cameraZoom;
    int unitActionPage=0;std::vector<InteractiveGameSession::UnitAction> unitActions;
    bool unitPanelActive=false;std::vector<UiInputTarget> unitPanelTargets,unitPanelScrolls;
    bool topPanelActive=false;std::vector<UiInputTarget> topPanelTargets,topPanelScrolls;
    const char* topPanelOption=std::getenv("ZEROSIS_PLAY_TOP_PANEL");
    if(topPanelOption && std::strcmp(topPanelOption,"0")!=0 && std::strcmp(topPanelOption,"1")!=0)
        throw std::invalid_argument("TopPanel opt-in must be 0 or 1");
    const bool topPanelEnabled=topPanelOption && std::strcmp(topPanelOption,"1")==0;
    const char* saveMenuCaptureOption=std::getenv("ZEROSIS_SAVE_MENU_CAPTURE");
    if(saveMenuCaptureOption && std::strcmp(saveMenuCaptureOption,"0")!=0 && std::strcmp(saveMenuCaptureOption,"1")!=0)
        throw std::invalid_argument("SaveMenu capture opt-in must be 0 or 1");
    const bool saveMenuCaptureEnabled=saveMenuCaptureOption && std::strcmp(saveMenuCaptureOption,"1")==0;
    bool saveMenuCaptured=false;
    BitmapEditorInputBuffer deferredEditorInput;
    const char* actionInfoOption=std::getenv("ZEROSIS_PLAY_ACTION_INFO_PANEL");
    if(actionInfoOption && std::strcmp(actionInfoOption,"0")!=0 && std::strcmp(actionInfoOption,"1")!=0)
        throw std::invalid_argument("ActionInfoPanel opt-in must be 0 or 1");
    const bool actionInfoEnabled=actionInfoOption && std::strcmp(actionInfoOption,"1")==0;
    bool actionInfoActive=false;std::vector<UiInputTarget> actionInfoTargets,actionInfoScrolls;
    const char* notificationOption=std::getenv("ZEROSIS_PLAY_NOTIFICATION_PANEL");
    if(notificationOption && std::strcmp(notificationOption,"0")!=0 && std::strcmp(notificationOption,"1")!=0)
        throw std::invalid_argument("NotificationPanel opt-in must be 0 or 1");
    const bool notificationEnabled=notificationOption && std::strcmp(notificationOption,"1")==0;
    if(notificationEnabled && !actionInfoEnabled)throw std::invalid_argument("NotificationPanel requires its original ActionInfoPanel parent");
    bool notificationActive=false;std::vector<UiInputTarget> notificationTargets,notificationScrolls;
    unsigned notificationSmokeStage=0;int notificationSmokeId=-1;UiPopupKind notificationSmokeKind=UiPopupKind::Production;
    std::string notificationBeforeState;
    unsigned actionInfoUnitStage=0,actionInfoNotificationStage=0;
    UiPopupKind actionInfoNotificationKind=UiPopupKind::Production;
    std::string actionInfoBeforeState;
    unsigned topPanelSmokeStage=0;std::string topPanelBeforeState;
    const char* gameMenuOption=std::getenv("ZEROSIS_PLAY_GAME_MENU_SMOKE");
    if(gameMenuOption && std::strcmp(gameMenuOption,"0")!=0 && std::strcmp(gameMenuOption,"1")!=0)
        throw std::invalid_argument("GameMenu smoke must be 0 or 1");
    const bool gameMenuSmoke=smoke && gameMenuOption && std::strcmp(gameMenuOption,"1")==0;
    unsigned gameMenuSmokeStage=0;std::string gameMenuBeforeState;
    const char* tradeRouteOption=std::getenv("ZEROSIS_PLAY_TRADE_ROUTE_SMOKE");
    if(tradeRouteOption && std::strcmp(tradeRouteOption,"0")!=0 && std::strcmp(tradeRouteOption,"1")!=0)
        throw std::invalid_argument("TradeRoute smoke must be 0 or 1");
    const bool tradeRouteSmoke=smoke && tradeRouteOption && std::strcmp(tradeRouteOption,"1")==0;
    unsigned tradeRouteSmokeStage=0;std::string tradeRouteBeforeState,tradeRouteBeforeInventory;
    unsigned tradeRouteFixtureAwards=0;
    const char* economicOption=std::getenv("ZEROSIS_PLAY_ECONOMIC_OVERVIEW_SMOKE");
    if(economicOption && std::strcmp(economicOption,"0")!=0 && std::strcmp(economicOption,"1")!=0)
        throw std::invalid_argument("Economic overview smoke must be 0 or 1");
    const bool economicSmoke=smoke && economicOption && std::strcmp(economicOption,"1")==0;
    EconomicOverviewSmokeFixture economicScenario;
    const char* socialPolicyOption=std::getenv("ZEROSIS_PLAY_SOCIAL_POLICY_SMOKE");
    if(socialPolicyOption && std::strcmp(socialPolicyOption,"0")!=0 && std::strcmp(socialPolicyOption,"1")!=0)
        throw std::invalid_argument("SocialPolicy smoke must be 0 or 1");
    const bool socialPolicySmoke=smoke && socialPolicyOption && std::strcmp(socialPolicyOption,"1")==0;
    const char* tenetOption=std::getenv("ZEROSIS_PLAY_SOCIAL_POLICY_TENETS");
    if(tenetOption && std::strcmp(tenetOption,"0")!=0 && std::strcmp(tenetOption,"1")!=0)
        throw std::invalid_argument("Tenet smoke must be 0 or 1");
    const bool policyTenetSmoke=tenetOption && std::strcmp(tenetOption,"1")==0;
    if(policyTenetSmoke && !socialPolicySmoke)throw std::invalid_argument("Tenet smoke requires its isolated policy scenario");
    unsigned tenetStage=0;int selectedTenet=-1;
    std::string tenetBeforeState,tenetAfterState;
    SocialPolicySmokeFixture::Inventory tenetBefore{},tenetFreeFirst{},tenetFreeSecond{},tenetFunded{},tenetAfter{};
    unsigned socialPolicyStage=0;int socialPolicyBranch=-1,socialPolicyChoice=-1;
    std::string socialPolicyBeforeState,socialPolicyAfterState;
    SocialPolicySmokeFixture::Inventory socialPolicyBefore{},socialPolicyAfterBranch{},socialPolicyFunded{},socialPolicyAfter{};
    int smokeStage=0,smokeUnit=-1,targetX=-1,targetY=-1,initialTurn=-1;bool smokeMoved=false;
    int originX=-1,originY=-1;std::string leftSelectState;
    int cityFocusTarget=NO_CITY_AI_FOCUS_TYPE;bool cityAvoidTarget=false;
    int citySpecialistBuilding=-1,citySpecialistsBefore=0,citySpecialistDelta=0,cityWorkPlot=-1,cityBuyPlot=-1,cityBuyCost=-1,cityGoldBefore=-1;
    bool cityNoAutoTarget=false;
    bool purchaseCloseSmoke=false;
    int purchaseStep=0,purchaseItem=-1;
    constexpr int purchaseSelections[]={0,1};
    InteractiveGameSession::PurchaseObservation purchaseBefore{};
    const char* decisionOption=std::getenv("ZEROSIS_PLAY_DECISIONS_SMOKE");
    const bool decisions=smoke && decisionOption && std::strcmp(decisionOption,"1")==0;
    if(smoke && topPanelEnabled && !decisions)
        throw std::invalid_argument("TopPanel input smoke requires the ordinary city-founding decision scenario");
    if(smoke && actionInfoEnabled && !decisions)
        throw std::invalid_argument("ActionInfoPanel input smoke requires the ordinary city-founding decision scenario");
    if(tradeRouteSmoke && (!decisions || !topPanelEnabled))
        throw std::invalid_argument("TradeRoute input smoke requires the original TopPanel and city decision scenario");
    if(socialPolicySmoke && (!decisions || !topPanelEnabled || tradeRouteSmoke))
        throw std::invalid_argument("SocialPolicy input smoke requires its own TopPanel and city decision scenario");
    if(economicSmoke && (!decisions || !topPanelEnabled || tradeRouteSmoke || socialPolicySmoke))
        throw std::invalid_argument("Economic overview smoke requires its isolated TopPanel and city decision scenario");
    if(gameMenuSmoke && (!decisions || !topPanelEnabled || tradeRouteSmoke || socialPolicySmoke || economicSmoke))
        throw std::invalid_argument("GameMenu smoke requires its isolated TopPanel and city decision scenario");
    const char* treeOption=std::getenv("ZEROSIS_PLAY_RESEARCH_TREE_SMOKE");
    const bool researchTree=decisions && treeOption && std::strcmp(treeOption,"1")==0;
    const char* awardOption=std::getenv("ZEROSIS_PLAY_TECH_AWARD_SMOKE");
    const bool techAwardSmoke=decisions && awardOption && std::strcmp(awardOption,"1")==0;
    unsigned techAwardChoices=0;std::uint64_t lastTechAwardGeneration=0;
    const char* actionOption=std::getenv("ZEROSIS_PLAY_UNIT_ACTIONS_SMOKE");
    const bool actionSmoke=smoke && actionOption && std::strcmp(actionOption,"1")==0;
    int actionBefore=-1,actionMission=-1;bool actionSecondaryOpened=false;
    struct OriginalMissionSmoke final {
        const char* kind=nullptr;int owner=-1,unit=-1,turn=-1,action=-1,mission=-1,data1=-1;
        int x=-1,y=-1,plot=-1,citiesBefore=0,progressBefore=-1,expectedImprovement=-1;
        std::uint64_t key=0,generation=0;
    } originalMission;
    int originalSecondaryUnit=-1,originalSecondaryAction=-1;
    const char* workerOption=std::getenv("ZEROSIS_PLAY_WORKER_BUILD_SMOKE");
    const bool workerSmoke=decisions && workerOption && std::strcmp(workerOption,"1")==0;
    const bool originalUnitPanelCombinedSmoke=smoke && decisions && researchTree && actionSmoke && workerSmoke &&
        topPanelEnabled && actionInfoEnabled && notificationEnabled;
    const char* combatOption=std::getenv("ZEROSIS_PLAY_COMBAT_SMOKE");
    const bool combatSmoke=decisions && combatOption && std::strcmp(combatOption,"1")==0;
    const char* captureOption=std::getenv("ZEROSIS_PLAY_CITY_CAPTURE_SMOKE");
    const bool captureSmoke=decisions && captureOption && std::strcmp(captureOption,"1")==0;
    const char* warOption=std::getenv("ZEROSIS_PLAY_DECLARE_WAR_SMOKE");
    const bool warSmoke=decisions && warOption;
    const bool warRanged=warSmoke && std::strcmp(warOption,"range")==0;
    const bool naturalWorkerResearch=originalUnitPanelCombinedSmoke && !techAwardSmoke && !combatSmoke && !captureSmoke &&
        !warSmoke && !tradeRouteSmoke && !socialPolicySmoke && !economicSmoke && !gameMenuSmoke;
    if(naturalWorkerResearch)std::puts("INTERACTIVE_WORKER_RESEARCH_CONTRACT=1");
    if(naturalWorkerResearch)std::puts("INTERACTIVE_WORKER_POLICY_CONTRACT=1");
    if(naturalWorkerResearch)std::puts("INTERACTIVE_WORKER_PRODUCTION_CONTRACT=1");
    if(naturalWorkerResearch)std::puts("INTERACTIVE_WORKER_UNSTACK_CONTRACT=1");
    unsigned unitCycleStage=0;int unitCycleInitial=-1,unitCyclePrevious=-1;
    std::size_t unitCycleCameraCount=0;unsigned long unitCycleSeed=0;
    std::uint64_t unitCycleGeneration=0;std::vector<int> unitCycleReady;
    std::string unitCycleBefore;
    if(naturalWorkerResearch)std::puts("INTERACTIVE_UNIT_CYCLE_CONTRACT=1");
    if(warSmoke && ((!warRanged && std::strcmp(warOption,"move")!=0) || workerSmoke || combatSmoke || captureSmoke || techAwardSmoke || !checkpoint.empty()))
        throw std::invalid_argument("War confirmation needs its own fresh move or range smoke scenario");
    InteractiveGameSession::DeclareWarSmokeFixture warFixture{};
    unsigned warAttempt=0;std::size_t warCombatBefore=0;std::string warBeforeState;
    if(techAwardSmoke && (workerSmoke || combatSmoke || captureSmoke))
        throw std::invalid_argument("Research completion needs its own finite one-turn scenario");
    if(captureSmoke && (workerSmoke || combatSmoke || !checkpoint.empty()))
        throw std::invalid_argument("City capture needs a fresh, separate finite smoke scenario");
    InteractiveGameSession::CityCaptureSmokeFixture captureFixture{};int capturedCity=-1;
    std::uint64_t lastLeaderSmokeGeneration=0;unsigned leaderSmokeChoices=0;
    if(combatSmoke && (workerSmoke || !checkpoint.empty()))throw std::invalid_argument("Combat fixture needs a fresh, separate finite smoke scenario");
    int combatKind=0;std::size_t combatBefore=0;InteractiveGameSession::CombatSmokeFixture combatFixture{};
    int workerID=-1,workerBuild=-1,workerProgress=-1;bool decisionTurnChecked=false;
    InteractiveGameSession::BuildObservation workerBefore{};
    int decisionCity=-1,decisionUnit=-1,decisionTech=-1;std::array<int,12> decisionBefore{};
    std::array<int,12> workerResearchBefore{};int workerResearchTurn=-1,workerResearchTech=-1;
    int naturalAwardTurn=-1,naturalAwardTech=-1,nextResearchTech=-1;
    std::uint64_t naturalAwardGeneration=0,nextResearchGeneration=0;
    bool naturalAwardPending=false;std::vector<int> naturalAwardedTechnologies;
    std::string naturalAwardState;
    InteractiveGameSession::BuildObservation naturalAwardWorker{},nextResearchWorker{};
    unsigned naturalPolicyCycles=0,naturalPolicyCompleted=0;
    bool naturalPolicyPending=false;int naturalPolicyId=-1,naturalPolicyOwner=-1,naturalPolicyTurn=-1;
    std::uint64_t naturalPolicyGeneration=0;
    SocialPolicySmokeFixture::Inventory naturalPolicyBefore{},naturalPolicyAfter{};
    InteractiveGameSession::BuildObservation naturalPolicyWorker{};
    std::string naturalPolicyBeforeState,naturalPolicyAfterState;
    unsigned naturalProductionFinished=0,naturalProductionCycles=0,naturalProductionCompleted=0;
    bool naturalProductionPending=false;
    int naturalProductionTurn=-1,naturalProductionOwner=-1,naturalProductionUnit=-1,naturalProducedUnit=-1,naturalProductionResearch=-1;
    std::uint64_t naturalProductionGeneration=0,naturalProductionKey=0,naturalProductionBeforeGeneration=0;
    WorldViewState naturalProductionWorldBefore;
    std::wstring naturalProductionBeforeScene;
    InteractiveGameSession::ProductionObservation naturalProductionBeforeTurn{},naturalProductionBefore{};
    InteractiveGameSession::BuildObservation naturalProductionWorker{};
    std::array<int,12> naturalProductionResearchBefore{};
    std::string naturalProductionBeforeState;
    struct NaturalUnstackSmoke final {
        unsigned cycles=0,completed=0,commands=0;bool pending=false;
        int owner=-1,turn=-1,unit=-1,produced=-1,unitType=-1,fromPlot=-1,fromX=-1,fromY=-1,moves=-1;
        int toPlot=-1,toX=-1,toY=-1,mission=-1,research=-1;
        std::uint64_t generation=0,key=0;
        WorldViewState beforeWorld;std::wstring beforeScene;
        InteractiveGameSession::BuildObservation worker{};
        InteractiveGameSession::ProductionObservation production{};
        std::array<int,12> researchBefore{};
    } naturalUnstack;
    const auto sameBuildObservation=[](const InteractiveGameSession::BuildObservation& left,
                                      const InteractiveGameSession::BuildObservation& right){
        return std::array<int,10>{left.unit,left.plot,left.build,left.progress,left.time,left.improvement,left.expected,left.mission,left.missionBuild,left.moves}==
               std::array<int,10>{right.unit,right.plot,right.build,right.progress,right.time,right.improvement,right.expected,right.mission,right.missionBuild,right.moves};
    };
    // GetResearchLeft omits the player/city completion-cost modifiers and can
    // saturate at zero before ownership. Progress must still strictly increase
    // in that uncompleted state; only its already-zero remainder may stay zero.
    const auto naturalResearchRemainingAdvanced=[](int before,int after){return before>0?after<before:after==0;};
    const auto started=std::chrono::steady_clock::now();
    WorldView retainedView{};std::vector<Scene> retainedOverlays;
    auto lastAnimation=started;
    unsigned animationProbe=0;bool worldAnimationProved=false,uiAnimationProved=false;
    auto animationProbeStart=started;std::string animationStateBefore;
    session.WithCore([&](ICvGameContext3& context){
        std::puts("INTERACTIVE_ORIGINAL_UNIT_PANEL_CONTRACT=1");
        live.Begin(context,checkpoint,std::move(decodedArchive));world=WorldViewState::Capture(context,host);
        SdkStateSnapshot::Write(directory+L"\\play-initial-state.txt",SdkStateSnapshot::Capture(host));
        if(socialPolicySmoke)Write(directory+(policyTenetSmoke?L"\\tenet-initial-inventory.json":L"\\social-policy-initial-inventory.json"),
            SocialPolicySmokeFixture::Serialize(live.ObserveSocialPolicySmoke()));
        if(smoke)live.TraceCityGovernance("initial");
        live.SelectInitialReadyUnit(!checkpoint.empty());world=WorldViewState::Capture(context,host);
    });
    if(world.ownedUnits.empty())throw std::runtime_error("Interactive game has no controllable units");
    cameraX=world.ownedUnits.front().x;cameraY=world.ownedUnits.front().y;initialTurn=world.turn;
    for(const auto& unit:world.ownedUnits)if(unit.selected){cameraX=unit.x;cameraY=unit.y;break;}
    const auto publish=[&](){
        if(windowCreated && !window.IsOpen()){closeRequested=true;redraw=false;return;}
        if(window.NativeHandle() && !uiActive){
            if(!window.EnableTextInput(false,&error))throw std::runtime_error(Utf8(error));
            deferredEditorInput.Clear();
        }
        retainedOverlays.clear();
        InteractiveUiSession::Frame uiFrame;unitPanelActive=false;unitPanelTargets.clear();unitPanelScrolls.clear();
        InteractiveUiSession::Frame topFrame;topPanelActive=false;topPanelTargets.clear();topPanelScrolls.clear();
        InteractiveUiSession::Frame actionInfoFrame;actionInfoActive=false;actionInfoTargets.clear();actionInfoScrolls.clear();
        InteractiveUiSession::Frame notificationFrame;notificationActive=false;notificationTargets.clear();notificationScrolls.clear();
        if(!uiActive){
            session.WithCore([&](ICvGameContext3&){uiFrame=live.CaptureUnitPanel();});
            unitPanelActive=!uiFrame.snapshot.empty();
            if(unitPanelActive){unitPanelTargets=uiFrame.clicks;unitPanelScrolls=uiFrame.scrolls;}
            if(topPanelEnabled){
                session.WithCore([&](ICvGameContext3&){topFrame=live.CaptureTopPanel();});
                topPanelActive=!topFrame.snapshot.empty();
                if(!topPanelActive)throw std::runtime_error("Opted-in original TopPanel is not visible on the world screen");
                topPanelTargets=topFrame.clicks;topPanelScrolls=topFrame.scrolls;
                for(auto& target:topPanelTargets)target.key=TopPanelKey(target.key);
                for(auto& target:topPanelScrolls)target.key=TopPanelKey(target.key);
            }
            if(actionInfoEnabled){
                session.WithCore([&](ICvGameContext3&){actionInfoFrame=live.CaptureActionInfoPanel();});
                actionInfoActive=!actionInfoFrame.snapshot.empty();
                if(!actionInfoActive)throw std::runtime_error("Original ActionInfoPanel is absent from the world screen");
                actionInfoTargets=actionInfoFrame.clicks;actionInfoScrolls=actionInfoFrame.scrolls;
                for(auto& target:actionInfoTargets)target.key=ActionInfoPanelKey(target.key);
                for(auto& target:actionInfoScrolls)target.key=ActionInfoPanelKey(target.key);
            }
            if(notificationEnabled){
                session.WithCore([&](ICvGameContext3&){notificationFrame=live.CaptureNotificationPanel();});
                notificationActive=!notificationFrame.snapshot.empty();
                if(!notificationActive)throw std::runtime_error("Original NotificationPanel is absent from its world parent");
                notificationTargets=notificationFrame.clicks;notificationScrolls=notificationFrame.scrolls;
                for(auto& target:notificationTargets)target.key=NotificationPanelKey(target.key);
                for(auto& target:notificationScrolls)target.key=NotificationPanelKey(target.key);
            }
        }
        session.WithCore([&](ICvGameContext3& context){unitActions=live.AvailableUnitActions(context);});
        unitActionPage=std::min(unitActionPage,std::max(0,static_cast<int>((unitActions.size()+5)/6)-1));
        auto view=Present(world,cameraX,cameraY,live.Status(),selectedCity);view.unitActionPage=unitActionPage;view.tileWidth=cameraZoom.TileWidth();
        view.originalTopPanel=topPanelActive;
        view.originalActionInfoPanel=actionInfoActive;
        view.originalUnitPanel=unitPanelActive;
        view.terrainAssetsPath=ExecutableDirectory()+L"\\terrain-assets.bin";
        view.fogAssetsPath=fogAssetsPath;
        view.waterAssetsPath=waterAssetsPath;
        view.waterSurfaceAssetsPath=waterSurfaceAssetsPath;
        view.lightingAssetsPath=lightingAssetsPath;
        view.screenLightingAssetsPath=screenLightingAssetsPath;
        // Only render the package hashed and pinned by VerifiedBundle.
        view.unitAssetsPath=unitAssetsPath;
        view.animationSeconds=unitAnimation&&!smoke?std::chrono::duration<double>(std::chrono::steady_clock::now()-started).count():0.0;
        view.fogAnimationSeconds=fogAnimation?std::chrono::duration<double>(std::chrono::steady_clock::now()-started).count():0.0;
        view.waterAnimationSeconds=waterAnimation?std::chrono::duration<double>(std::chrono::steady_clock::now()-started).count():0.0;
        if(uiActive)session.WithCore([&](ICvGameContext3&){
            const auto kind=live.UiKind();view.fullScreenUi=live.HasCityView() || kind==UiPopupKind::LeaderHead || kind==UiPopupKind::SaveMenu || kind==UiPopupKind::LoadMenu;
            if(live.HasCityView()){
                if(!host.resolveCity)throw std::logic_error("CityView has no live city resolver");
                std::unique_ptr<ICvCity1> city(host.resolveCity(host.selectedCityOwner,host.selectedCityId));
                if(!city)throw std::logic_error("CityView background lost its selected SDK city");
                city->GetPosition(view.cameraX,view.cameraY);
            }
        });
        for(std::size_t index=0;index<unitActions.size();++index)view.unitActions.push_back({static_cast<int>(index),Wide(unitActions[index].name)});
        const std::wstring stem=smoke?L"play-scene-"+std::to_wstring(++revision):L"play-current";
        auto png=directory+L"\\"+stem+L".png";
        WorldViewProjection projection;
        if(!window.PrepareGpuFrame([&](ID3D11Device* device,ID3D11DeviceContext* context,
                                      ID3D11Texture2D* target,std::wstring* why){
            return RenderWorldViewToTexture(view,device,context,target,&scene,why,&projection);
        },&error))throw std::runtime_error(Utf8(error));
        // Color readback is diagnostic evidence only. Manual play retains the
        // world and every overlay in this private same-device GPU candidate.
        if(smoke && !window.CapturePreparedGpuFrame(png,&error))throw std::runtime_error(Utf8(error));
        const bool worldWheelEnabled=!uiActive && projection.ready && projection.mapWidth>0;
        const BitmapDisplayRect worldWheelViewport{0.0f,0.0f,static_cast<float>(projection.mapWidth),static_cast<float>(scene.height)};
#if defined(ZEROSIS_WORLD_TERRAIN)
        projection.frameGeneration=window.SceneGeneration()+1;
        session.WithCore([&](ICvGameContext3&){host.cityWorldProjection=std::move(projection);});
#endif
        std::wstring uiSnapshot,uiFolder;unsigned currentUi=0;
        if(uiActive || unitPanelActive){
            if(uiActive)session.WithCore([&](ICvGameContext3&){uiFrame=live.CaptureUi();});
            if(window.NativeHandle()){
                BitmapTextInputState textState{};
                if(!window.GetTextInputState(&textState,&error))throw std::runtime_error(Utf8(error));
                const bool sameEditor=uiFrame.textInputOwner && textState.enabled &&
                    textState.editorOwner==uiFrame.textInputOwner;
                if(sameEditor)deferredEditorInput.Bind(uiFrame.textInputOwner,textState.focusEpoch);
                else{
                    deferredEditorInput.Clear();
                    if(!window.EnableTextInput(false,&error))throw std::runtime_error(Utf8(error));
                }
            }
            if(!uiFrame.cityBackdrop.empty() && !uiFrame.economicBackdrop.empty())
                throw std::logic_error("A production scene cannot retain both city and economic backdrops");
            const bool economicBackdrop=!uiFrame.economicBackdrop.empty();
            if(!uiFrame.cityBackdrop.empty() || economicBackdrop){
                const unsigned backdropRevision=++uiRevision;
                const auto backdropSnapshot=directory+L"\\play-ui-"+std::to_wstring(backdropRevision)+L".json";
                const auto backdropFolder=directory+L"\\play-ui-"+std::to_wstring(backdropRevision);
                Write(backdropSnapshot,economicBackdrop?uiFrame.economicBackdrop:uiFrame.cityBackdrop);
                std::printf("INTERACTIVE_UI_SCENE_REQUEST=%u|%s|%s|%s\n",backdropRevision,
                    economicBackdrop?"economic-overview":"city-view",Utf8(backdropSnapshot).c_str(),Utf8(backdropFolder).c_str());std::fflush(stdout);
                WaitForUiPacket(window,backdropRevision,closeRequested,error);
                if(closeRequested){redraw=false;return;}
                Scene backdrop{};
                if(!LoadScenePacket(backdropFolder+L"\\scene.packet",&backdrop,&error) || backdrop.width!=1920 || backdrop.height!=1080)
                    throw std::runtime_error("Retained production backdrop has an invalid packet");
                backdrop.hits.clear();backdrop.scrolls.clear();
                if(!window.OverlayPreparedGpuFrame(backdrop,&error))throw std::runtime_error(Utf8(error));
                retainedOverlays.push_back(backdrop);
                if(smoke){
                if(backdrop.textures.size()>=0xfffffffeu)throw std::length_error("Production backdrop texture index overflow");
                Sprite worldBackground{};worldBackground.textureIndex=static_cast<std::uint32_t>(backdrop.textures.size());
                worldBackground.sourceRect[2]=worldBackground.targetRect[2]=worldBackground.clipRect[2]=1920.0f;
                worldBackground.sourceRect[3]=worldBackground.targetRect[3]=worldBackground.clipRect[3]=1080.0f;
                std::fill(std::begin(worldBackground.tintRGBA),std::end(worldBackground.tintRGBA),1.0f);
                backdrop.textures.push_back({png});backdrop.sprites.insert(backdrop.sprites.begin(),worldBackground);
                backdrop.hits.clear();backdrop.scrolls.clear();
                png=backdropFolder+(economicBackdrop?L"\\economic-backdrop.png":L"\\city-backdrop.png");
                if(!RenderToPng(backdrop,png,&error))throw std::runtime_error(Utf8(error));
                std::printf(economicBackdrop?"INTERACTIVE_ECONOMIC_BACKDROP=%u|%s\n":"INTERACTIVE_CITY_BACKDROP=%u|%s\n",backdropRevision,Utf8(png).c_str());
                }else std::printf(economicBackdrop?"INTERACTIVE_ECONOMIC_BACKDROP_GPU=%u\n":"INTERACTIVE_CITY_BACKDROP_GPU=%u\n",backdropRevision);
            }
            currentUi=++uiRevision;uiSnapshot=directory+L"\\play-ui-"+std::to_wstring(currentUi)+L".json";
            uiFolder=directory+L"\\play-ui-"+std::to_wstring(currentUi);
            Write(uiSnapshot,uiFrame.snapshot);
            std::printf("INTERACTIVE_UI_SCENE_REQUEST=%u|%s|%s|%s\n",currentUi,uiFrame.context.c_str(),Utf8(uiSnapshot).c_str(),Utf8(uiFolder).c_str());std::fflush(stdout);
            if(smoke && uiActive && smokeStage==7 && !PostMessageW(window.NativeHandle(),WM_CLOSE,0,0))
                throw std::runtime_error("Cannot post the UI preparation close regression input");
            WaitForUiPacket(window,currentUi,closeRequested,error,&deferredEditorInput);
            // Finish the outstanding driver acknowledgement, but do not apply
            // the packet or re-enable input after a deferred gameplay close.
            if(closeRequested){
                if(smoke && smokeStage==7){
                    if(!window.NativeHandle())throw std::runtime_error("UI preparation lost its deferred close window");
                    smokeStage=6;
                    std::printf("INTERACTIVE_PREPARE_CLOSE_RETAINED=%u|%llu\n",currentUi,static_cast<unsigned long long>(window.SceneGeneration()));
                    std::puts("INTERACTIVE_SMOKE_SEQUENCE=SELECT_MOVE_EXPLICIT_SKIP_END_TURN_SAVE_WM_CLOSE");
                }
                redraw=false;return;
            }
            session.WithCore([&](ICvGameContext3&){
                if(uiActive)live.VerifyUiSnapshot(uiFrame.snapshot,uiFrame.cityBackdrop,uiFrame.economicBackdrop);
                else live.VerifyUnitPanelSnapshot(uiFrame.snapshot);
            });
            Scene popup{};
            if(!LoadScenePacket(uiFolder+L"\\scene.packet",&popup,&error) || popup.width!=1920 || popup.height!=1080)
                throw std::runtime_error("Prepared interactive popup has an invalid packet or viewport");
            const auto validate=[](const std::vector<UiInputTarget>& targets,const std::vector<HitRecord>& hits){
                for(const auto& hit:hits)if(std::none_of(targets.begin(),targets.end(),[&](const UiInputTarget& target){return target.key==hit.controlKey;}))
                    throw std::runtime_error("Prepared interactive popup contains an unowned input target");
            };
            validate(uiFrame.clicks,popup.hits);validate(uiFrame.scrolls,popup.scrolls);
            if(popup.hits.empty())throw std::runtime_error("Active interactive popup has no original callback hit records");
            if(!window.OverlayPreparedGpuFrame(popup,&error))throw std::runtime_error(Utf8(error));
            retainedOverlays.push_back(popup);
            if(smoke){
            if(popup.textures.size()>=0xfffffffeu)throw std::length_error("Interactive popup texture index overflow");
            Sprite background{};background.controlKey=0;background.textureIndex=static_cast<std::uint32_t>(popup.textures.size());
            background.sourceRect[2]=background.targetRect[2]=background.clipRect[2]=1920.0f;
            background.sourceRect[3]=background.targetRect[3]=background.clipRect[3]=1080.0f;
            std::fill(std::begin(background.tintRGBA),std::end(background.tintRGBA),1.0f);
            popup.textures.push_back({png});popup.sprites.insert(popup.sprites.begin(),background);
            // Keep the independent software reference only for test evidence.
            if(!RenderToPng(popup,uiFolder+L"\\composed.png",&error))
                throw std::runtime_error(Utf8(error));
            }
            if(uiActive)scene=std::move(popup);
            else{
                // Retain depth-tested map picking. Original ConsumeMouse controls
                // and action buttons win in reverse draw order above the world.
                scene.hits.insert(scene.hits.end(),popup.hits.begin(),popup.hits.end());
                scene.scrolls.insert(scene.scrolls.end(),popup.scrolls.begin(),popup.scrolls.end());
            }
        }
        std::wstring topSnapshot,topFolder;unsigned currentTop=0;
        if(topPanelActive){
            currentTop=++uiRevision;topSnapshot=directory+L"\\play-ui-"+std::to_wstring(currentTop)+L".json";
            topFolder=directory+L"\\play-ui-"+std::to_wstring(currentTop);
            Write(topSnapshot,topFrame.snapshot);
            std::printf("INTERACTIVE_UI_SCENE_REQUEST=%u|top-panel|%s|%s\n",currentTop,
                Utf8(topSnapshot).c_str(),Utf8(topFolder).c_str());std::fflush(stdout);
            WaitForUiPacket(window,currentTop,closeRequested,error);
            if(closeRequested){redraw=false;return;}
            session.WithCore([&](ICvGameContext3&){live.VerifyTopPanelSnapshot(topFrame.snapshot);});
            Scene top{};
            if(!LoadScenePacket(topFolder+L"\\scene.packet",&top,&error) || top.width!=1920 || top.height!=1080 ||
               top.hits.empty() || !top.pixelHits.indices.empty())
                throw std::runtime_error("Original TopPanel has an invalid retained scene packet");
            const auto remapHits=[](std::vector<HitRecord>& hits,const std::vector<UiInputTarget>& targets){
                for(auto& hit:hits){
                    if(std::none_of(targets.begin(),targets.end(),[&](const UiInputTarget& target){return target.key==hit.controlKey;}))
                        throw std::runtime_error("TopPanel packet contains an unowned original input target");
                    hit.controlKey=TopPanelKey(hit.controlKey);
                }
            };
            remapHits(top.hits,topFrame.clicks);remapHits(top.scrolls,topFrame.scrolls);
            for(auto& sprite:top.sprites)if(sprite.controlKey)sprite.controlKey=TopPanelKey(sprite.controlKey);
            if(smoke && !window.CapturePreparedGpuFrame(topFolder+L"\\world-underlay.png",&error))
                throw std::runtime_error(Utf8(error));
            if(!window.OverlayPreparedGpuFrame(top,&error))throw std::runtime_error(Utf8(error));
            retainedOverlays.push_back(top);
            scene.hits.insert(scene.hits.end(),top.hits.begin(),top.hits.end());
            scene.scrolls.insert(scene.scrolls.end(),top.scrolls.begin(),top.scrolls.end());
            if(smoke){
                if(top.textures.size()>=0xfffffffeu)throw std::length_error("TopPanel texture index overflow");
                Sprite background{};background.textureIndex=static_cast<std::uint32_t>(top.textures.size());
                background.sourceRect[2]=background.targetRect[2]=background.clipRect[2]=1920.0f;
                background.sourceRect[3]=background.targetRect[3]=background.clipRect[3]=1080.0f;
                std::fill(std::begin(background.tintRGBA),std::end(background.tintRGBA),1.0f);
                top.textures.push_back({topFolder+L"\\world-underlay.png"});top.sprites.insert(top.sprites.begin(),background);
                if(!RenderToPng(top,topFolder+L"\\composed.png",&error))throw std::runtime_error(Utf8(error));
            }
        }
        std::wstring actionInfoSnapshot,actionInfoFolder;unsigned currentActionInfo=0;
        if(actionInfoActive){
            currentActionInfo=++uiRevision;
            actionInfoSnapshot=directory+L"\\play-ui-"+std::to_wstring(currentActionInfo)+L".json";
            actionInfoFolder=directory+L"\\play-ui-"+std::to_wstring(currentActionInfo);
            Write(actionInfoSnapshot,actionInfoFrame.snapshot);
            std::printf("INTERACTIVE_UI_SCENE_REQUEST=%u|action-info-panel|%s|%s\n",currentActionInfo,
                Utf8(actionInfoSnapshot).c_str(),Utf8(actionInfoFolder).c_str());std::fflush(stdout);
            WaitForUiPacket(window,currentActionInfo,closeRequested,error);
            if(closeRequested){redraw=false;return;}
            session.WithCore([&](ICvGameContext3&){live.VerifyActionInfoPanelSnapshot(actionInfoFrame.snapshot);});
            Scene panel{};
            if(!LoadScenePacket(actionInfoFolder+L"\\scene.packet",&panel,&error) || panel.width!=1920 || panel.height!=1080 ||
               !panel.pixelHits.indices.empty())
                throw std::runtime_error("Original ActionInfoPanel has an invalid retained scene packet");
            const auto remapHits=[](std::vector<HitRecord>& hits,const std::vector<UiInputTarget>& targets){
                for(auto& hit:hits){
                    if(std::none_of(targets.begin(),targets.end(),[&](const UiInputTarget& target){return target.key==hit.controlKey;}))
                        throw std::runtime_error("ActionInfoPanel packet contains an unowned original input target");
                    hit.controlKey=ActionInfoPanelKey(hit.controlKey);
                }
            };
            remapHits(panel.hits,actionInfoFrame.clicks);remapHits(panel.scrolls,actionInfoFrame.scrolls);
            for(auto& sprite:panel.sprites)if(sprite.controlKey)sprite.controlKey=ActionInfoPanelKey(sprite.controlKey);
            if(!window.OverlayPreparedGpuFrame(panel,&error))throw std::runtime_error(Utf8(error));
            retainedOverlays.push_back(panel);
            scene.hits.insert(scene.hits.end(),panel.hits.begin(),panel.hits.end());
            scene.scrolls.insert(scene.scrolls.end(),panel.scrolls.begin(),panel.scrolls.end());
        }
        std::wstring notificationSnapshot,notificationFolder;unsigned currentNotification=0;
        if(notificationActive){
            currentNotification=++uiRevision;
            notificationSnapshot=directory+L"\\play-ui-"+std::to_wstring(currentNotification)+L".json";
            notificationFolder=directory+L"\\play-ui-"+std::to_wstring(currentNotification);
            Write(notificationSnapshot,notificationFrame.snapshot);
            std::printf("INTERACTIVE_UI_SCENE_REQUEST=%u|notification-panel|%s|%s\n",currentNotification,
                Utf8(notificationSnapshot).c_str(),Utf8(notificationFolder).c_str());std::fflush(stdout);
            WaitForUiPacket(window,currentNotification,closeRequested,error);
            if(closeRequested){redraw=false;return;}
            session.WithCore([&](ICvGameContext3&){live.VerifyNotificationPanelSnapshot(notificationFrame.snapshot);});
            Scene panel{};
            if(!LoadScenePacket(notificationFolder+L"\\scene.packet",&panel,&error) || panel.width!=1920 || panel.height!=1080 ||
               !panel.pixelHits.indices.empty())
                throw std::runtime_error("Original NotificationPanel has an invalid retained scene packet");
            const auto remapHits=[](std::vector<HitRecord>& hits,const std::vector<UiInputTarget>& targets){
                for(auto& hit:hits){
                    if(std::none_of(targets.begin(),targets.end(),[&](const UiInputTarget& target){return target.key==hit.controlKey;}))
                        throw std::runtime_error("NotificationPanel packet contains an unowned original input target");
                    hit.controlKey=NotificationPanelKey(hit.controlKey);
                }
            };
            remapHits(panel.hits,notificationFrame.clicks);remapHits(panel.scrolls,notificationFrame.scrolls);
            for(auto& sprite:panel.sprites)if(sprite.controlKey)sprite.controlKey=NotificationPanelKey(sprite.controlKey);
            if(!window.OverlayPreparedGpuFrame(panel,&error))throw std::runtime_error(Utf8(error));
            retainedOverlays.push_back(panel);
            scene.hits.insert(scene.hits.end(),panel.hits.begin(),panel.hits.end());
            scene.scrolls.insert(scene.scrolls.end(),panel.scrolls.begin(),panel.scrolls.end());
        }
        if(!window.NativeHandle()){
            if(windowCreated){closeRequested=true;redraw=false;return;}
            if(!window.CreatePreparedGpuScene(scene,L"ZeroSis' Civilization - \uc804\ub7b5 \uc9c0\ub3c4",1280,720,!smoke,&error) ||
               !window.EnableGameplayInput(true,&error) ||
               !window.EnableProductionPointerInput(uiActive || unitPanelActive || topPanelActive || actionInfoActive || notificationActive || worldWheelEnabled,&error))throw std::runtime_error(Utf8(error));
            windowCreated=true;
            host.applyMenuOptions=[&window,&host](const MenuOptionsValues& value){
                return ApplyHostMenuOptions(host,window,value);
            };
            if(host.menuOptions){
                const auto committed=host.menuOptions->Committed();
                if(host.applyMenuOptions(committed)!=committed)
                    throw std::runtime_error("Private presentation options failed startup backend readback");
            }
        }else{
            RejectPending(window,closeRequested,error,0,&deferredEditorInput);
            if(closeRequested){redraw=false;return;}
            if(!window.EnableProductionPointerInput(uiActive || unitPanelActive || topPanelActive || actionInfoActive || notificationActive || worldWheelEnabled,&error))throw std::runtime_error(Utf8(error));
            const auto before=window.SceneGeneration();
            if(smoke && uiActive && !PostMessageW(window.NativeHandle(),WM_MOUSEMOVE,0,MAKELPARAM(-1,-1)))
                throw std::runtime_error("Cannot post the scene-transition pointer regression input");
            const bool closeDuringPublish=smoke && smokeStage==5 && checkpoint.empty();
            if(closeDuringPublish && !PostMessageW(window.NativeHandle(),WM_CLOSE,0,0))
                throw std::runtime_error("Cannot post the scene-transition close regression input");
            // Physical pointer events can arrive during scene preparation. Commit
            // once, retaining their original generation, then reject stale
            // commands while preserving the deferred save-and-close request.
            BitmapTextInputState textState{};
            if(!window.GetTextInputState(&textState,&error))throw std::runtime_error(Utf8(error));
            const bool sameEditor=uiFrame.textInputOwner && textState.enabled &&
                textState.editorOwner==uiFrame.textInputOwner;
            if(sameEditor)deferredEditorInput.Bind(uiFrame.textInputOwner,textState.focusEpoch);
            else deferredEditorInput.Clear();
            // A captured slider changes only visuals. The window itself checks
            // every input rectangle/key before retaining that capture/generation.
            const bool dragVisual=!smoke && uiActive && live.UiKind()==UiPopupKind::MenuOptions &&
                window.HasControlDragCapture() && window.RefreshPreparedGpuFrame(scene,&error);
            if(!dragVisual && !window.UpdatePreparedGpuSceneRetainingInput(scene,&error,
                sameEditor?uiFrame.textInputOwner:0,sameEditor?textState.focusEpoch:0))throw std::runtime_error(Utf8(error));
            const auto retainedPointers=RejectPending(window,closeRequested,error,before,&deferredEditorInput);
            if(smoke && uiActive){
                if(!retainedPointers || window.SceneGeneration()!=before+1)
                    throw std::runtime_error("Scene replacement lost its old-generation pointer input");
                std::printf("INTERACTIVE_SCENE_INPUT_RETAINED=%llu|%llu|%u\n",static_cast<unsigned long long>(before),
                    static_cast<unsigned long long>(window.SceneGeneration()),retainedPointers);
            }
            if(closeDuringPublish){
                if(!closeRequested || !window.NativeHandle())
                    throw std::runtime_error("Scene replacement did not retain the deferred close request");
                smokeStage=6;
                std::printf("INTERACTIVE_SCENE_CLOSE_RETAINED=%llu|%llu\n",static_cast<unsigned long long>(before),
                    static_cast<unsigned long long>(window.SceneGeneration()));
                std::puts("INTERACTIVE_SMOKE_SEQUENCE=SELECT_MOVE_EXPLICIT_SKIP_END_TURN_SAVE_WM_CLOSE");
            }
        }
        if(!window.SetWorldWheelViewport(worldWheelEnabled?&worldWheelViewport:nullptr,&error))throw std::runtime_error(Utf8(error));
        if(!worldWheelEnabled)cameraZoom.ResetWheelRemainder();
        if(!window.EnableControlDragInput(uiActive && live.UiKind()==UiPopupKind::MenuOptions,&error))
            throw std::runtime_error(Utf8(error));
        if(!window.EnableTextInput(uiActive && uiFrame.textInputEnabled,&error,uiActive?uiFrame.textInputOwner:0))
            throw std::runtime_error(Utf8(error));
        const std::string pixelFile=smoke&&!scene.pixelHits.indices.empty()?Utf8(stem)+".pick":"";
        if(!pixelFile.empty())RetainPicking(scene,directory+L"\\"+stem+L".pick");
        Write(directory+L"\\"+stem+L".json",Metadata(world,scene,window.SceneGeneration(),unitActions,unitActionPage,pixelFile,unitPanelActive));
        if(smoke && !window.CaptureFrame(directory+L"\\"+stem+L"-gpu.png",&error))throw std::runtime_error(Utf8(error));
        if(saveMenuCaptureEnabled && !saveMenuCaptured && uiActive && uiFrame.context=="save-menu"){
            const auto capture=directory+L"\\save-menu-native-gpu.png";
            if(!window.CaptureFrame(capture,&error))throw std::runtime_error(Utf8(error));
            saveMenuCaptured=true;
            std::printf("INTERACTIVE_SAVE_MENU_GPU_CAPTURE=%llu|%s\n",
                static_cast<unsigned long long>(window.SceneGeneration()),Utf8(capture).c_str());
        }
        BitmapFrameInfo frame{};if(!window.GetFrameInfo(&frame,&error))throw std::runtime_error(Utf8(error));
        std::printf("INTERACTIVE_GPU_WORLD_COMMITTED=%llu|%llu\n",
            static_cast<unsigned long long>(window.SceneGeneration()),
            static_cast<unsigned long long>(frame.deviceIdentity));
        std::printf("INTERACTIVE_GPU_SCENE_COMMITTED=%llu|%llu\n",
            static_cast<unsigned long long>(window.SceneGeneration()),
            static_cast<unsigned long long>(frame.deviceIdentity));
        std::printf("INTERACTIVE_WORLD_FRAME=%u|%llu|%d|%zu|%zu|%llu|%llu|%u|%u\n",revision,
            static_cast<unsigned long long>(window.SceneGeneration()),world.turn,world.ownedUnits.size(),scene.hits.size(),
            static_cast<unsigned long long>(frame.deviceIdentity),static_cast<unsigned long long>(frame.presentCount),
            frame.lastPresentOccluded?1u:0u,static_cast<unsigned>(frame.deviceKind));
        if(uiActive || unitPanelActive)std::printf("INTERACTIVE_UI_FRAME=%u|%llu|%d|%s|%llu|%llu|%s|%s\n",currentUi,
            static_cast<unsigned long long>(window.SceneGeneration()),world.turn,uiFrame.context.c_str(),
            static_cast<unsigned long long>(reinterpret_cast<std::uintptr_t>(window.NativeHandle())),
            static_cast<unsigned long long>(frame.deviceIdentity),Utf8(uiSnapshot).c_str(),Utf8(uiFolder).c_str());
        if(topPanelActive)std::printf("INTERACTIVE_TOP_PANEL_FRAME=%u|%llu|%d|%d|%llu|%llu|%s|%s\n",currentTop,
            static_cast<unsigned long long>(window.SceneGeneration()),world.turn,world.activePlayer,
            static_cast<unsigned long long>(reinterpret_cast<std::uintptr_t>(window.NativeHandle())),
            static_cast<unsigned long long>(frame.deviceIdentity),Utf8(topSnapshot).c_str(),Utf8(topFolder).c_str());
        if(actionInfoActive)std::printf("INTERACTIVE_ACTION_INFO_PANEL_FRAME=%u|%llu|%d|%d|%llu|%llu|%s|%s\n",currentActionInfo,
            static_cast<unsigned long long>(window.SceneGeneration()),world.turn,world.activePlayer,
            static_cast<unsigned long long>(reinterpret_cast<std::uintptr_t>(window.NativeHandle())),
            static_cast<unsigned long long>(frame.deviceIdentity),Utf8(actionInfoSnapshot).c_str(),Utf8(actionInfoFolder).c_str());
        if(notificationActive)std::printf("INTERACTIVE_NOTIFICATION_PANEL_FRAME=%u|%llu|%d|%d|%llu|%llu|%s|%s\n",currentNotification,
            static_cast<unsigned long long>(window.SceneGeneration()),world.turn,world.activePlayer,
            static_cast<unsigned long long>(reinterpret_cast<std::uintptr_t>(window.NativeHandle())),
            static_cast<unsigned long long>(frame.deviceIdentity),Utf8(notificationSnapshot).c_str(),Utf8(notificationFolder).c_str());
        retainedView=std::move(view);lastAnimation=std::chrono::steady_clock::now();
        redraw=false;
    };
    const auto refreshAnimation=[&](double seconds){
        // A detached view and already prepared UI sprites are sufficient for
        // a new pose. No Lua serialization, GameCore call, turn or RNG here.
        if(unitAnimation)retainedView.animationSeconds=seconds;
        if(fogAnimation)retainedView.fogAnimationSeconds=seconds;
        if(waterAnimation)retainedView.waterAnimationSeconds=seconds;
        Scene candidate{};
        if(!window.PrepareGpuFrame([&](ID3D11Device* device,ID3D11DeviceContext* context,
                                      ID3D11Texture2D* target,std::wstring* why){
            return RenderWorldViewToTexture(retainedView,device,context,target,&candidate,why,nullptr,false);
        },&error))throw std::runtime_error(Utf8(error));
        for(const auto& overlay:retainedOverlays)
            if(!window.OverlayPreparedGpuFrame(overlay,&error))throw std::runtime_error(Utf8(error));
        if(!retainedOverlays.empty()){
            candidate.hits=scene.hits;candidate.scrolls=scene.scrolls;candidate.pixelHits=scene.pixelHits;
        }
        const auto generation=window.SceneGeneration();
        if(!window.RefreshPreparedGpuFrame(candidate,&error) || window.SceneGeneration()!=generation)
            throw std::runtime_error("Animation refresh changed input generation or failed: "+Utf8(error));
        lastAnimation=std::chrono::steady_clock::now();
    };
    publish();
    // Gameplay WM_CLOSE retains the open HWND until this owner saves.
    // closeRequested suppresses commands while an ongoing turn settles.
    InteractiveGameSession::LoadHandoff loadHandoff;
    bool menuExitRequested=false;
    while(windowCreated){
        // The full decision scenario includes city management, two purchases,
        // research, capture and save/close. TradeRoute adds an AI turn and its
        // tab/sort/close roundtrips. The full HUD/tree/unit-action/build profile
        // also retains the same finite 900-second bound as its Python driver.
        // This is the whole-run wall-clock test bound;
        // per-scene and Lua instruction limits remain independently enforced.
        if(smoke && std::chrono::steady_clock::now()-started>std::chrono::seconds((tradeRouteSmoke || economicSmoke || gameMenuSmoke || originalUnitPanelCombinedSmoke)?900:(decisions?300:90)))throw std::runtime_error("Interactive posted-input smoke timed out");
        if(window.NativeHandle() && !window.PumpMessages(&error))throw std::runtime_error(Utf8(error));
        if(!window.IsOpen())closeRequested=true;
        std::vector<BitmapInputEvent> inputs,nativeInputs;
        BitmapTextInputState textState{};
        if(window.IsOpen()){
            if(!window.GetTextInputState(&textState,&error))throw std::runtime_error(Utf8(error));
            deferredEditorInput.Drain(textState.enabled?textState.editorOwner:0,textState.focusEpoch,inputs);
        }else deferredEditorInput.Clear();
        if(!window.DrainInputs(&nativeInputs,&error))throw std::runtime_error(Utf8(error));
        inputs.insert(inputs.end(),nativeInputs.begin(),nativeInputs.end());
        bool acted=false,wheelActed=false;
        session.WithCore([&](ICvGameContext3& context){
            for(const auto& input:inputs){
                if(input.kind==BitmapInputKind::CloseRequest){closeRequested=true;continue;}
                bool editorInput=false;
                if(input.editorOwner || input.kind==BitmapInputKind::TextInput){
                    BitmapTextInputState currentText{};
                    if(window.IsOpen() && window.GetTextInputState(&currentText,&error))
                        editorInput=currentText.enabled && input.editorOwner==live.UiTextInputOwner() &&
                            BitmapEditorInputBuffer::Matches(input,currentText.editorOwner,currentText.focusEpoch);
                    if(!editorInput){std::puts("INTERACTIVE_EDITOR_INPUT_REJECTED=OWNER_OR_FOCUS_CHANGED");continue;}
                }
                if((acted && !(wheelActed && input.kind==BitmapInputKind::WorldWheel)) ||
                   (closeRequested && !live.HasMandatoryUiDecision()) ||
                   (!editorInput && input.sceneGeneration!=window.SceneGeneration())){
                    std::printf("INTERACTIVE_STALE_INPUT_REJECTED=%llu\n",static_cast<unsigned long long>(input.sceneGeneration));continue;
                }
                if(uiActive){
                    if(input.kind==BitmapInputKind::WorldWheel){
                        cameraZoom.ResetWheelRemainder();
                        std::puts("INTERACTIVE_WORLD_WHEEL_REJECTED=UI_OWNS_INPUT");continue;
                    }
                    const auto inputUiKind=live.UiKind();
                    const char* inputUiContext=inputUiKind==UiPopupKind::ResearchTree?"research-tree":
                        inputUiKind==UiPopupKind::LoadMenu?"load-menu":
                        inputUiKind==UiPopupKind::Pantheon?"pantheon":
                        inputUiKind==UiPopupKind::SaveMenu?"save-menu":
                        inputUiKind==UiPopupKind::GameMenu?"game-menu":
                        inputUiKind==UiPopupKind::ExitConfirm?"exit-confirm":
                        inputUiKind==UiPopupKind::EconomicOverview?"economic-overview":
                        inputUiKind==UiPopupKind::TradeRoute?"trade-route":
                        inputUiKind==UiPopupKind::DeclareWar?"declare-war":
                        inputUiKind==UiPopupKind::GoodyHutReward?"goody-hut-reward":
                        inputUiKind==UiPopupKind::TechAward?"tech-award":
                        inputUiKind==UiPopupKind::Research?"research":inputUiKind==UiPopupKind::Production?"production":
                        inputUiKind==UiPopupKind::CityView?"city-view":inputUiKind==UiPopupKind::CityCapture?"city-capture":inputUiKind==UiPopupKind::LeaderHead?"diplomacy":"ranking";
                    const bool productionCommand=naturalWorkerResearch && naturalProductionPending && inputUiKind==UiPopupKind::Production;
                    const auto productionEventsBefore=productionCommand?host.Events().size():0;
                    const bool consumed=live.DispatchUi(input);
                    if(live.HasPendingLifecycle()){
                        if(live.HasPendingExit() || live.HasPendingLoad())throw std::logic_error("Lifecycle transition conflicts with load or exit");
                        loadHandoff=live.TakePendingLifecycle();acted=true;break;
                    }
                    std::printf("INTERACTIVE_UI_NATIVE_INPUT=%llu|%u|%llu|%u\n",static_cast<unsigned long long>(input.sceneGeneration),
                        static_cast<unsigned>(input.kind),static_cast<unsigned long long>(input.controlKey),consumed?1u:0u);
                    if(live.HasPendingExit()){
                        if(live.HasPendingLoad())throw std::logic_error("Confirmed exit cannot also load a save");
                        menuExitRequested=true;acted=true;break;
                    }
                    if(live.HasPendingLoad()){
                        loadHandoff=live.TakePendingLoad();acted=true;break;
                    }
                    if(productionCommand){
                        if(!consumed || smokeStage!=97 || input.kind!=BitmapInputKind::ControlClick ||
                           input.controlKey!=naturalProductionKey || input.sceneGeneration!=naturalProductionGeneration)
                            throw std::runtime_error("Natural production did not consume its exact original training callback");
                        const auto events=host.Events();std::string command;unsigned count=0;
                        for(std::size_t i=productionEventsBefore;i<events.size();++i)if(events[i].find("local-city-order:")==0){command=events[i];++count;}
                        const auto prefix="local-city-order:"+std::to_string(decisionCity)+":"+std::to_string(static_cast<int>(ORDER_TRAIN))+":"+
                            std::to_string(naturalProductionUnit)+":0:";
                        const int shift=command==prefix+"0:1"?0:command==prefix+"1:1"?1:-1;
                        if(count!=1 || shift<0)throw std::runtime_error("Original natural production callback did not deliver exactly its legal SDK training order");
                        std::printf("INTERACTIVE_WORKER_PRODUCTION_COMMAND=%u|%d|%d|%d|%d|%d|0|%d|1|%llu|%llu\n",
                            naturalProductionCycles,world.activePlayer,world.turn,decisionCity,static_cast<int>(ORDER_TRAIN),naturalProductionUnit,shift,
                            static_cast<unsigned long long>(input.sceneGeneration),static_cast<unsigned long long>(input.controlKey));
                    }
                    if(input.kind==BitmapInputKind::KeyDown)std::printf("INTERACTIVE_UI_NATIVE_KEY=%llu|%s|%u|%u|%u\n",
                        static_cast<unsigned long long>(input.sceneGeneration),inputUiContext,
                        static_cast<unsigned>(input.virtualKey),consumed?1u:0u,live.HasUi()?1u:0u);
                    if(BitmapEditorInputBuffer::IsTerminalAction(input,editorInput))acted=true;
                    if(consumed)redraw=true;continue;
                }
                if(input.kind==BitmapInputKind::WorldWheel){
                    if(closeRequested || live.HasUi() || live.IsAdvancing()){
                        cameraZoom.ResetWheelRemainder();
                        std::puts("INTERACTIVE_WORLD_WHEEL_REJECTED=NOT_SETTLED");continue;
                    }
                    const bool changed=cameraZoom.ApplyWheelDelta(input.wheelDelta);
                    std::printf("INTERACTIVE_WORLD_WHEEL=%llu|%d|%.1f|%u\n",
                        static_cast<unsigned long long>(input.sceneGeneration),static_cast<int>(input.wheelDelta),
                        static_cast<double>(cameraZoom.TileWidth()),changed?1u:0u);
                    if(changed){acted=true;wheelActed=true;redraw=true;}
                    continue;
                }
                if(input.kind==BitmapInputKind::Scroll)cameraZoom.ResetWheelRemainder();
                if(input.kind==BitmapInputKind::TextInput){
                    std::puts("INTERACTIVE_TEXT_INPUT_REJECTED=NO_ACTIVE_SAVE_MENU");continue;
                }
                if(notificationActive){
                    const auto& targets=input.kind==BitmapInputKind::Scroll?notificationScrolls:notificationTargets;
                    const bool panelTarget=std::any_of(targets.begin(),targets.end(),[&](const UiInputTarget& target){return target.key==input.controlKey;});
                    if(panelTarget || input.kind==BitmapInputKind::PointerMove){
                        auto routed=input;routed.controlKey=panelTarget?input.controlKey-kNotificationPanelKeyBase:0;
                        const auto cameraCount=host.cameraPresentations.size();
                        bool frameChanged=false;
                        const bool consumed=live.DispatchNotificationPanel(routed,&frameChanged);
                        if(host.cameraPresentations.size()>cameraCount){
                            const auto& focus=host.cameraPresentations.back();cameraX=focus.x;cameraY=focus.y;redraw=true;
                        }
                        std::printf("INTERACTIVE_NOTIFICATION_PANEL_INPUT=%llu|%u|%llu|%llu|%u\n",
                            static_cast<unsigned long long>(input.sceneGeneration),static_cast<unsigned>(input.kind),
                            static_cast<unsigned long long>(input.controlKey),static_cast<unsigned long long>(routed.controlKey),consumed?1u:0u);
                        if(frameChanged || (panelTarget && input.kind!=BitmapInputKind::PointerMove))redraw=true;
                        if(panelTarget){
                            if(input.kind==BitmapInputKind::ControlClick || input.kind==BitmapInputKind::ControlRightClick)acted=true;
                            continue;
                        }
                    }
                }
                if(actionInfoActive){
                    const auto& targets=input.kind==BitmapInputKind::Scroll?actionInfoScrolls:actionInfoTargets;
                    const bool panelTarget=std::any_of(targets.begin(),targets.end(),[&](const UiInputTarget& target){return target.key==input.controlKey;});
                    const bool enter=input.kind==BitmapInputKind::KeyDown && input.virtualKey==VK_RETURN;
                    if(panelTarget || enter || input.kind==BitmapInputKind::PointerMove){
                        auto routed=input;routed.controlKey=panelTarget?input.controlKey-kActionInfoPanelKeyBase:0;
                        if(enter){
                            for(const auto& target:actionInfoTargets)if(target.id=="EndTurnButton"){
                                if(routed.controlKey)throw std::runtime_error("ActionInfoPanel has duplicate EndTurnButton callbacks");
                                routed.controlKey=target.key-kActionInfoPanelKeyBase;
                            }
                            if(!routed.controlKey){acted=true;continue;}
                            routed.kind=BitmapInputKind::ControlClick;
                        }
                        const auto cameraCount=host.cameraPresentations.size();
                        bool frameChanged=false;
                        const bool consumed=live.DispatchActionInfoPanel(routed,&frameChanged);
                        if(host.cameraPresentations.size()>cameraCount){
                            const auto& focus=host.cameraPresentations.back();cameraX=focus.x;cameraY=focus.y;redraw=true;
                        }
                        std::printf("INTERACTIVE_ACTION_INFO_PANEL_INPUT=%llu|%u|%llu|%llu|%u|%u\n",
                            static_cast<unsigned long long>(input.sceneGeneration),static_cast<unsigned>(input.kind),
                            static_cast<unsigned long long>(input.controlKey),static_cast<unsigned long long>(routed.controlKey),consumed?1u:0u,enter?1u:0u);
                        if(frameChanged)redraw=true;
                        if(panelTarget || enter){
                            if(input.kind==BitmapInputKind::ControlClick || input.kind==BitmapInputKind::ControlRightClick || enter)acted=true;
                            continue;
                        }
                    }
                }
                if(topPanelActive){
                    const auto& targets=input.kind==BitmapInputKind::Scroll?topPanelScrolls:topPanelTargets;
                    const bool panelTarget=std::any_of(targets.begin(),targets.end(),[&](const UiInputTarget& target){return target.key==input.controlKey;});
                    if(panelTarget || input.kind==BitmapInputKind::PointerMove){
                        auto routed=input;routed.controlKey=panelTarget?input.controlKey-kTopPanelKeyBase:0;
                        bool frameChanged=false;
                        const bool consumed=live.DispatchTopPanel(routed,&frameChanged);
                        std::printf("INTERACTIVE_TOP_PANEL_INPUT=%llu|%u|%llu|%llu|%u\n",
                            static_cast<unsigned long long>(input.sceneGeneration),static_cast<unsigned>(input.kind),
                            static_cast<unsigned long long>(input.controlKey),static_cast<unsigned long long>(routed.controlKey),consumed?1u:0u);
                        if(frameChanged)redraw=true;
                        if(panelTarget){
                            if(input.kind==BitmapInputKind::ControlClick || input.kind==BitmapInputKind::ControlRightClick)acted=true;
                            continue;
                        }
                    }
                }
                if(unitPanelActive){
                    const auto& targets=input.kind==BitmapInputKind::Scroll?unitPanelScrolls:unitPanelTargets;
                    const bool panelTarget=std::any_of(targets.begin(),targets.end(),[&](const UiInputTarget& target){return target.key==input.controlKey;});
                    if(panelTarget || input.kind==BitmapInputKind::PointerMove){
                        auto routed=input;if(!panelTarget)routed.controlKey=0;
                        const auto cameraCount=host.cameraPresentations.size();
                        bool frameChanged=false;
                        const bool consumed=live.DispatchUnitPanel(routed,&frameChanged);
                        if(host.cameraPresentations.size()>cameraCount){
                            const auto& focus=host.cameraPresentations.back();cameraX=focus.x;cameraY=focus.y;redraw=true;
                        }
                        std::printf("INTERACTIVE_UNIT_PANEL_INPUT=%llu|%u|%llu|%u\n",static_cast<unsigned long long>(input.sceneGeneration),
                            static_cast<unsigned>(input.kind),static_cast<unsigned long long>(routed.controlKey),consumed?1u:0u);
                        if(panelTarget && (input.kind==BitmapInputKind::ControlClick || input.kind==BitmapInputKind::ControlRightClick))acted=true;
                        if(frameChanged)redraw=true;
                        // A retained ConsumeMouse region blocks the map even
                        // when it has no Lua callback of its own.
                        continue;
                    }
                }
                std::uint64_t key=input.controlKey;
                if(input.kind==BitmapInputKind::ControlRightClick){
                    bool consumed=false;int x=-1,y=-1;
                    for(const auto& plot:world.plots)if(key==WorldViewHitKey::Plot(plot.index) && plot.revealed){x=plot.x;y=plot.y;break;}
                    for(const auto& unit:world.ownedUnits)if(key==WorldViewHitKey::OwnedUnit(unit.id)){x=unit.x;y=unit.y;break;}
                    for(const auto& city:world.visibleCities)if(city.owner==world.activePlayer && key==WorldViewHitKey::OwnedCity(city.id)){x=city.x;y=city.y;break;}
                    const bool unstackCommand=naturalWorkerResearch && naturalUnstack.pending;
                    const auto unstackEventsBefore=unstackCommand?host.Events().size():0;
                    if(unstackCommand){
                        const auto selected=host.localSelection.Snapshot();
                        if(smokeStage!=98 || naturalUnstack.commands!=0 || input.modifiers!=0 || key!=naturalUnstack.key ||
                           input.sceneGeneration!=naturalUnstack.generation || world.turn!=naturalUnstack.turn ||
                           world.activePlayer!=naturalUnstack.owner || x!=naturalUnstack.toX || y!=naturalUnstack.toY ||
                           selected.size()!=1 || selected.front().first!=naturalUnstack.owner || selected.front().second!=naturalUnstack.unit ||
                           !live.IsProductionCivilianStack(context,naturalUnstack.unit,naturalUnstack.produced,decisionCity) ||
                           !live.IsVacantAdjacentMoveLegal(naturalUnstack.unit,x,y))
                            throw std::runtime_error("Natural civilian unstack lost its exact selected unit or legal posted destination");
                    }
                    if(x>=0 && host.interfaceMode==INTERFACEMODE_SELECTION)consumed=live.Move(x,y,(input.modifiers&1u)!=0);
                    std::printf("INTERACTIVE_WINDOW_INPUT=%llu|%u|%llu|%u\n",static_cast<unsigned long long>(input.sceneGeneration),
                        static_cast<unsigned>(input.kind),static_cast<unsigned long long>(key),consumed?1u:0u);
                    if(unstackCommand){
                        if(!consumed)throw std::runtime_error("Natural civilian unstack did not consume its original world right click");
                        const auto expected="local-push-mission:"+std::to_string(naturalUnstack.unit)+":"+std::to_string(naturalUnstack.mission)+":"+
                            std::to_string(x)+":"+std::to_string(y)+":0:0";
                        const auto events=host.Events();unsigned commands=0;
                        for(std::size_t i=unstackEventsBefore;i<events.size();++i)if(events[i].find("local-")==0){
                            // CvGame::update reports this empty local reminder queue;
                            // HostServices records it without dispatching a command.
                            if(events[i]=="local-turn-reminders-flush:0")continue;
                            if(events[i]!=expected)throw std::runtime_error("Natural civilian unstack delivered an unrelated local SDK command: "+events[i]);
                            ++commands;
                        }
                        if(commands!=1)throw std::runtime_error("Natural civilian unstack did not deliver exactly one original SDK move mission: expected "+
                            expected+", count="+std::to_string(commands));
                        ++naturalUnstack.commands;
                        std::printf("INTERACTIVE_WORKER_UNSTACK_COMMAND=%u|%d|%d|%d|%d|%d|%d|0|0|%llu|%llu\n",naturalUnstack.cycles,
                            naturalUnstack.owner,naturalUnstack.turn,naturalUnstack.unit,naturalUnstack.mission,x,y,
                            static_cast<unsigned long long>(input.sceneGeneration),static_cast<unsigned long long>(key));
                    }
                    acted=true;if(consumed)redraw=true;continue;
                }
                if(input.kind==BitmapInputKind::KeyDown){
                    if(input.virtualKey==VK_ESCAPE){
                        const bool consumed=live.OpenGameMenu();
                        std::printf("INTERACTIVE_GAME_MENU_WORLD_KEY=%llu|%u|%u\n",
                            static_cast<unsigned long long>(input.sceneGeneration),static_cast<unsigned>(input.virtualKey),consumed?1u:0u);
                        acted=true;if(consumed)redraw=true;continue;
                    }
                    // Match the original BNW WorldView keys; the zoom interval is candidate policy.
                    const bool zoomIn=input.virtualKey==VK_PRIOR || input.virtualKey==VK_OEM_PLUS;
                    const bool zoomOut=input.virtualKey==VK_NEXT || input.virtualKey==VK_OEM_MINUS;
                    if(zoomIn || zoomOut){
                        acted=true;
                        if(closeRequested || live.IsAdvancing()){
                            std::puts("INTERACTIVE_CAMERA_ZOOM_REJECTED=NOT_SETTLED");continue;
                        }
                        const bool changed=zoomIn?cameraZoom.ZoomIn():cameraZoom.ZoomOut();
                        std::printf("INTERACTIVE_CAMERA_ZOOM=%llu|%u|%.1f|%u\n",
                            static_cast<unsigned long long>(input.sceneGeneration),static_cast<unsigned>(input.virtualKey),
                            static_cast<double>(cameraZoom.TileWidth()),changed?1u:0u);
                        if(changed)redraw=true;
                        continue;
                    }
                    WorldViewAction action;
                    switch(input.virtualKey){
                        case VK_RETURN:action=WorldViewAction::EndTurn;break;
                        case VK_TAB:action=WorldViewAction::NextUnit;break;
                        case VK_SPACE:action=WorldViewAction::Skip;break;
                        case VK_F5:action=WorldViewAction::Save;break;
                        case VK_LEFT:action=WorldViewAction::PanLeft;break;
                        case VK_RIGHT:action=WorldViewAction::PanRight;break;
                        case VK_UP:action=WorldViewAction::PanUp;break;
                        case VK_DOWN:action=WorldViewAction::PanDown;break;
                        default:
                            std::printf("INTERACTIVE_WORLD_KEY_IGNORED=%llu|%u\n",
                                static_cast<unsigned long long>(input.sceneGeneration),static_cast<unsigned>(input.virtualKey));
                            continue;
                    }
                    key=WorldViewHitKey::Action(action);
                }
                if(input.kind!=BitmapInputKind::ControlClick && input.kind!=BitmapInputKind::KeyDown)continue;
                bool consumed=false;
                if(key!=WorldViewHitKey::Action(WorldViewAction::UnitActionsPrevious) && key!=WorldViewHitKey::Action(WorldViewAction::UnitActionsNext))unitActionPage=0;
                for(std::size_t index=0;index<unitActions.size();++index)if(key==WorldViewHitKey::UnitAction(static_cast<int>(index))){
                    consumed=live.PerformUnitAction(unitActions[index]);break;
                }
                for(const auto& unit:world.ownedUnits)if(key==WorldViewHitKey::OwnedUnit(unit.id)){
                    consumed=live.Select(unit.id);if(consumed){cameraX=unit.x;cameraY=unit.y;}break;
                }
                if(!consumed)for(const auto& plot:world.plots)if(key==WorldViewHitKey::Plot(plot.index)){
                    if(plot.revealed)consumed=live.SelectPlot(plot.x,plot.y);break;
                }
                if(!consumed)for(const auto& city:world.visibleCities)if(city.owner==world.activePlayer && key==WorldViewHitKey::OwnedCity(city.id)){
                    if(live.OpenCity(city.id)){selectedCity=city.id;cameraX=city.x;cameraY=city.y;consumed=true;
                        std::printf("INTERACTIVE_CITY_SELECTED=%d|%d|%d|%d\n",world.turn,city.id,city.x,city.y);}break;
                }
                if(key==WorldViewHitKey::Action(WorldViewAction::NextUnit)){
                    const auto ready=live.ReadyUnits();if(!ready.empty()){
                        int selected=-1;for(const auto& unit:world.ownedUnits)if(unit.selected)selected=unit.id;
                        auto next=std::find(ready.begin(),ready.end(),selected);if(next==ready.end() || ++next==ready.end())next=ready.begin();
                        consumed=live.Select(*next);for(const auto& unit:world.ownedUnits)if(unit.id==*next){cameraX=unit.x;cameraY=unit.y;}
                    }
                }else if(key==WorldViewHitKey::Action(WorldViewAction::Skip))consumed=live.Skip();
                else if(key==WorldViewHitKey::Action(WorldViewAction::Found))consumed=live.Found();
                else if(key==WorldViewHitKey::Action(WorldViewAction::Research))consumed=live.OpenResearch();
                else if(key==WorldViewHitKey::Action(WorldViewAction::Production))consumed=live.OpenProduction(selectedCity);
                else if(key==WorldViewHitKey::Action(WorldViewAction::EndTurn))consumed=live.EndTurn();
                else if(key==WorldViewHitKey::Action(WorldViewAction::Save)){
                    if(!live.IsAdvancing()){live.Save();consumed=true;}
                }else if(key==WorldViewHitKey::Action(WorldViewAction::Close)){closeRequested=true;consumed=true;}
                else if(key==WorldViewHitKey::Action(WorldViewAction::PanLeft)){cameraX=PanCameraCoordinate(cameraX,-3,world.gridWidth,world.wrapX);consumed=true;}
                else if(key==WorldViewHitKey::Action(WorldViewAction::PanRight)){cameraX=PanCameraCoordinate(cameraX,3,world.gridWidth,world.wrapX);consumed=true;}
                else if(key==WorldViewHitKey::Action(WorldViewAction::PanUp)){cameraY=PanCameraCoordinate(cameraY,3,world.gridHeight,world.wrapY);consumed=true;}
                else if(key==WorldViewHitKey::Action(WorldViewAction::PanDown)){cameraY=PanCameraCoordinate(cameraY,-3,world.gridHeight,world.wrapY);consumed=true;}
                else if(key==WorldViewHitKey::Action(WorldViewAction::UnitActionsPrevious) && unitActionPage>0){--unitActionPage;consumed=true;}
                else if(key==WorldViewHitKey::Action(WorldViewAction::UnitActionsNext) && (unitActionPage+1)*6<static_cast<int>(unitActions.size())){++unitActionPage;consumed=true;}
                std::printf("INTERACTIVE_WINDOW_INPUT=%llu|%u|%llu|%u\n",static_cast<unsigned long long>(input.sceneGeneration),
                    static_cast<unsigned>(input.kind),static_cast<unsigned long long>(key),consumed?1u:0u);
                acted=true;redraw=true;
            }
            if(loadHandoff.HasTransition() || menuExitRequested)return;
            if(live.Tick())redraw=true;
            if(!live.IsAdvancing() && live.UpdateUi())redraw=true;
            uiActive=live.HasUi();
            mandatoryDecision=live.HasMandatoryUiDecision();
            if(selectedCity>=0 && !live.HasCityView()){selectedCity=-1;redraw=true;}
            if(selectedCity>=0 && !live.OwnsCity(selectedCity)){selectedCity=-1;redraw=true;}
            if(redraw)world=WorldViewState::Capture(context,host);
        });
        if(menuExitRequested){
            // Return before Tick, UpdateUi, saving, or publishing another scene.
            // Stack-owned window/GPU resources die before HostRun unloads Core.
            deferredEditorInput.Clear();
            if(window.NativeHandle() && !window.EnableTextInput(false,&error))throw std::runtime_error(Utf8(error));
            if(smoke)throw std::logic_error("Existing interactive smoke cannot skip its input sequence through ExitConfirm");
            std::puts("INTERACTIVE_EXIT_GAME_LOOP_EXIT=CALLBACK_COMPLETE_NO_SAVE_NO_EXTRA_TICK");
            return {};
        }
        if(loadHandoff.HasTransition()){
            // Leave through the function boundary, so the owned HWND/COM/GPU
            // resources are gone before HostRun shuts down the old GameCore.
            // Loading discards the current play state; it is not WM_CLOSE's
            // separate save-on-close operation.
            deferredEditorInput.Clear();
            if(window.NativeHandle() && !window.EnableTextInput(false,&error))throw std::runtime_error(Utf8(error));
            if(smoke)throw std::logic_error("Existing interactive smoke cannot skip its input sequence through LoadMenu");
            std::puts("INTERACTIVE_LOAD_MENU_LOOP_EXIT=CALLBACK_COMPLETE_NO_SAVE_NO_EXTRA_TICK");
            return loadHandoff;
        }
        if(!window.IsOpen() && mandatoryDecision)
            throw std::runtime_error("Owned gameplay window was destroyed with an unresolved mandatory decision");
        if(closeRequested && !live.IsAdvancing() && !mandatoryDecision){
            session.WithCore([&](ICvGameContext3&){
                live.CloseUi();
                if(purchaseCloseSmoke){
                    if(live.HasUi() || host.popupVisible || host.cityScreenUp || host.cityScreenViewingMode ||
                       host.selectedCityId!=-1 || host.interfaceMode!=INTERFACEMODE_SELECTION)
                        throw std::logic_error("Closing nested purchase UI retained its city or purchase mode");
                    std::printf("INTERACTIVE_CITY_PURCHASE_CLOSE_VERIFIED=%d|%d|0|0|0\n",decisionCity,world.turn);
                }
                live.Save();SdkStateSnapshot::Write(directory+L"\\play-final-state.txt",SdkStateSnapshot::Capture(host));if(smoke)live.TraceCityGovernance("final");
            });
            std::printf("INTERACTIVE_PLAY_CLOSED=%d|NATIVE_CHECKPOINT_WRITTEN\n",world.turn);break;
        }
        if(redraw && (!closeRequested || mandatoryDecision))publish();
        if(closeRequested && !mandatoryDecision)continue;
        if((unitAnimation||fogAnimation||waterAnimation) && !redraw && !closeRequested && !live.IsAdvancing()){
            const auto now=std::chrono::steady_clock::now();
            const bool probe=smoke && inputs.empty() && ((!uiActive&&!worldAnimationProved) || (uiActive&&!uiAnimationProved));
            if(probe){
                if(!animationProbe){
                    animationProbeStart=now;
                    session.WithCore([&](ICvGameContext3&){animationStateBefore=SdkStateSnapshot::Capture(host);});
                    Write(directory+(uiActive?L"\\animation-ui-before.txt":L"\\animation-world-before.txt"),animationStateBefore);
                    animationProbe=1;
                }
                const double elapsed=std::chrono::duration<double>(now-animationProbeStart).count();
                if(elapsed>=0.25*animationProbe){
                    refreshAnimation(elapsed);
                    const std::wstring name=uiActive?L"ui":L"world";
                    if(!window.CaptureFrame(directory+L"\\animation-"+name+L"-"+std::to_wstring(animationProbe)+L".png",&error))
                        throw std::runtime_error(Utf8(error));
                    session.WithCore([&](ICvGameContext3&){
                        const auto observed=SdkStateSnapshot::Capture(host);
                        if(observed!=animationStateBefore)
                            throw std::runtime_error("Visual animation mutated game state");
                        if(animationProbe==3)Write(directory+(uiActive?L"\\animation-ui-after.txt":L"\\animation-world-after.txt"),observed);
                    });
                    std::printf("INTERACTIVE_ANIMATION_FRAME=%s|%u|%.9f|%llu|%d\n",uiActive?"ui":"world",animationProbe,
                        elapsed,static_cast<unsigned long long>(window.SceneGeneration()),world.turn);
                    if(++animationProbe==4){
                        (uiActive?uiAnimationProved:worldAnimationProved)=true;animationProbe=0;
                        // Stable t=0 restored without a new input generation.
                        refreshAnimation(0.0);
                        std::printf("INTERACTIVE_ANIMATION_STATE_UNCHANGED=%s\n",uiActive?"ui":"world");
                    }
                }
                if(animationProbe){MsgWaitForMultipleObjectsEx(0,nullptr,16,QS_ALLINPUT,MWMO_INPUTAVAILABLE);continue;}
            }else if(!smoke && now-lastAnimation>=std::chrono::milliseconds(unitAnimation?33:100)){
                refreshAnimation(std::chrono::duration<double>(now-started).count());
            }
        }
        if(smoke && inputs.empty() && !live.IsAdvancing()){
            std::uint64_t next=0;bool nextRight=false,nextShift=false;
            session.WithCore([&](ICvGameContext3& context){
                if(naturalAwardPending){
                    if(uiActive || smokeStage!=4 || world.turn!=naturalAwardTurn || world.activePlayer!=workerResearchBefore[2] ||
                       window.SceneGeneration()<=naturalAwardGeneration || !live.HasTechnology(naturalAwardTech) ||
                       live.CurrentResearch()==naturalAwardTech || SdkStateSnapshot::Capture(host)!=naturalAwardState ||
                       !sameBuildObservation(live.ObserveBuild(context,workerID,workerBuild),naturalAwardWorker))
                        throw std::runtime_error("Natural research award did not return through its original callback with unchanged SDK worker state");
                    const auto completed=live.ObserveResearch(naturalAwardTech,true);
                    if(completed[10]!=0)throw std::runtime_error("Owned technology retained unfinished research after its award");
                    std::printf("INTERACTIVE_WORKER_TECH_AWARD_RETURNED=%d|%d|%d|%llu|%d|1|%d\n",world.turn,world.activePlayer,
                        naturalAwardTech,static_cast<unsigned long long>(window.SceneGeneration()),live.CurrentResearch(),completed[10]);
                    naturalAwardPending=false;
                }
                if(originalMission.kind){
                    const auto& pending=originalMission;
                    if(world.activePlayer!=pending.owner || world.turn!=pending.turn || window.SceneGeneration()<=pending.generation)
                        throw std::runtime_error("Original unit mission observation lost its owner, turn or committed scene");
                    const auto unit=std::find_if(world.ownedUnits.begin(),world.ownedUnits.end(),[&](const WorldViewState::Unit& value){return value.id==pending.unit;});
                    int result1=-1,result2=-1;
                    if(std::strcmp(pending.kind,"found")==0){
                        const auto city=std::find_if(world.visibleCities.begin(),world.visibleCities.end(),[&](const WorldViewState::City& value){
                            return value.owner==pending.owner && value.x==pending.x && value.y==pending.y;
                        });
                        const auto count=std::count_if(world.visibleCities.begin(),world.visibleCities.end(),[&](const WorldViewState::City& value){return value.owner==pending.owner;});
                        if(unit!=world.ownedUnits.end() || city==world.visibleCities.end() || count!=pending.citiesBefore+1)
                            throw std::runtime_error("Original found callback did not consume its settler and add exactly its SDK city");
                        result1=city->id;result2=0;
                    }else if(std::strcmp(pending.kind,"skip")==0){
                        if(unit==world.ownedUnits.end())throw std::runtime_error("Original skip callback lost its SDK unit");
                        const auto ready=live.ReadyUnits();result1=live.UnitActivity(pending.unit);
                        result2=std::find(ready.begin(),ready.end(),pending.unit)!=ready.end()?1:0;
                        if(result1!=ACTIVITY_HOLD || result2)throw std::runtime_error("Original skip callback did not hold its unit and clear readiness");
                    }else if(std::strcmp(pending.kind,"build")==0){
                        const auto after=live.ObserveBuild(context,pending.unit,pending.data1);
                        if(after.plot!=pending.plot)
                            throw std::runtime_error("Original build callback changed its worker plot");
                        result1=after.progress;result2=after.improvement;
                        if(result1<=pending.progressBefore && result2!=pending.expectedImprovement)
                            throw std::runtime_error("Original build callback did not advance its actual SDK construction");
                    }else throw std::logic_error("Unknown original unit mission observation");
                    std::printf("INTERACTIVE_ORIGINAL_UNIT_MISSION_OBSERVED=%s|%d|%d|%d|%d|%d|%d|%llu|%llu|%llu|%d|%d\n",
                        pending.kind,pending.owner,pending.unit,pending.turn,pending.action,pending.mission,pending.data1,
                        static_cast<unsigned long long>(pending.key),static_cast<unsigned long long>(pending.generation),
                        static_cast<unsigned long long>(window.SceneGeneration()),result1,result2);
                    originalMission=OriginalMissionSmoke{};
                }
                const auto originalMissionButton=[&](const char* kind,int unitID,int mission,int data1)->bool{
                    if(uiActive || !unitPanelActive || originalMission.kind)
                        throw std::runtime_error("Original unit mission needs its current visible nonmodal panel");
                    const auto selected=host.localSelection.Snapshot();
                    const auto unit=std::find_if(world.ownedUnits.begin(),world.ownedUnits.end(),[&](const WorldViewState::Unit& value){return value.id==unitID && value.selected;});
                    if(selected.size()!=1 || selected.front().first!=world.activePlayer || selected.front().second!=unitID || unit==world.ownedUnits.end())
                        throw std::runtime_error("Original unit mission target has a stale or different selected unit");
                    const bool build=std::strcmp(kind,"build")==0,found=std::strcmp(kind,"found")==0;
                    const int action=build?live.OriginalUnitBuildAction(data1):live.OriginalUnitMissionAction(mission);
                    for(const auto& target:unitPanelTargets)if(!target.consumeMouseOnly && target.hasVoid1 && target.void1==action &&
                        (found?target.id=="BuildCityButton":(target.id=="UnitActionButton" || target.id=="RecommendedActionButton"))){next=target.key;break;}
                    const bool command=next!=0;
                    if(!command){
                        if(originalSecondaryUnit==unitID && originalSecondaryAction==action)
                            throw std::runtime_error("Original unit mission remains absent after opening its secondary actions");
                        for(const auto& target:unitPanelTargets)if(!target.consumeMouseOnly && target.id=="SecondaryButton"){next=target.key;break;}
                        if(!next)throw std::runtime_error("Original unit mission has neither an enabled registered action nor a secondary button");
                        originalSecondaryUnit=unitID;originalSecondaryAction=action;
                    }
                    std::printf("%s=%s|%d|%d|%d|%d|%d|%d|%llu|%llu\n",
                        command?"INTERACTIVE_ORIGINAL_UNIT_MISSION_TARGET":"INTERACTIVE_ORIGINAL_UNIT_MISSION_SECONDARY_TARGET",
                        kind,world.activePlayer,unitID,world.turn,action,mission,data1,
                        static_cast<unsigned long long>(next),static_cast<unsigned long long>(window.SceneGeneration()));
                    if(command){
                        originalMission.kind=kind;originalMission.owner=world.activePlayer;originalMission.unit=unitID;originalMission.turn=world.turn;
                        originalMission.action=action;originalMission.mission=mission;originalMission.data1=data1;
                        originalMission.key=next;originalMission.generation=window.SceneGeneration();originalMission.x=unit->x;originalMission.y=unit->y;
                        originalMission.citiesBefore=static_cast<int>(std::count_if(world.visibleCities.begin(),world.visibleCities.end(),[&](const WorldViewState::City& value){return value.owner==world.activePlayer;}));
                        if(build){const auto before=live.ObserveBuild(context,unitID,data1);originalMission.plot=before.plot;
                            originalMission.progressBefore=before.progress;originalMission.expectedImprovement=before.expected;}
                        originalSecondaryUnit=-1;originalSecondaryAction=-1;
                    }
                    return command;
                };
                const auto actionInfoButton=[&](const char* phase)->std::uint64_t{
                    if(uiActive || !actionInfoActive)throw std::runtime_error("ActionInfoPanel smoke needs its visible original world overlay");
                    std::uint64_t key=0;
                    for(const auto& target:actionInfoTargets)if(target.id=="EndTurnButton"){
                        if(key)throw std::runtime_error("Original end-turn button has duplicate retained input identities");key=target.key;
                    }
                    if(!key)throw std::runtime_error("Original end-turn button has no enabled callback target");
                    const auto observed=live.ObserveActionInfoPanel();
                    std::printf("INTERACTIVE_ACTION_INFO_SMOKE_TARGET=%s|%d|%d|%llu|%llu|%d\n",phase,
                        observed.blockingType,observed.notificationIndex,static_cast<unsigned long long>(key),
                        static_cast<unsigned long long>(window.SceneGeneration()),observed.turn);
                    return key;
                };
                const auto naturalPolicyWorkerState=[&](const char* phase){
                    const auto value=live.ObserveBuild(context,workerID,workerBuild);
                    if(!sameBuildObservation(value,naturalPolicyWorker))
                        throw std::runtime_error("Natural Tradition adoption changed the tracked worker");
                    std::printf("INTERACTIVE_WORKER_POLICY_WORKER_STATE=%u|%s|%d|%d|%llu|%d|%d|%d|%d|%d|%d|%d|%d|%d|%d\n",
                        naturalPolicyCycles,phase,world.turn,world.activePlayer,static_cast<unsigned long long>(window.SceneGeneration()),
                        value.unit,value.plot,value.build,value.progress,value.time,value.improvement,value.expected,value.mission,value.missionBuild,value.moves);
                };
                const auto naturalProductionQueue=[&](const char* phase,const InteractiveGameSession::ProductionObservation& value,
                                                       int turn,std::uint64_t generation){
                    std::printf("INTERACTIVE_WORKER_PRODUCTION_QUEUE=1|%s|%d|%d|%d|%llu|%d|%d|%d|%d\n",phase,turn,world.activePlayer,decisionCity,
                        static_cast<unsigned long long>(generation),value.length,value.unit,value.production,value.needed);
                };
                const auto naturalProductionWorkerState=[&](const char* phase){
                    const auto value=live.ObserveBuild(context,workerID,workerBuild);
                    if(!sameBuildObservation(value,naturalProductionWorker))throw std::runtime_error("Natural production selection changed the tracked worker");
                    std::printf("INTERACTIVE_WORKER_PRODUCTION_WORKER_STATE=%u|%s|%d|%d|%llu|%d|%d|%d|%d|%d|%d|%d|%d|%d|%d\n",
                        naturalProductionCycles,phase,world.turn,world.activePlayer,static_cast<unsigned long long>(window.SceneGeneration()),
                        value.unit,value.plot,value.build,value.progress,value.time,value.improvement,value.expected,value.mission,value.missionBuild,value.moves);
                };
                const auto naturalUnstackState=[&](const char* phase){
                    const auto production=live.ObserveProduction(decisionCity);
                    const auto research=live.ObserveResearch(naturalUnstack.research);
                    const auto worker=live.ObserveBuild(context,workerID,workerBuild);
                    if(world.turn!=naturalUnstack.turn || world.activePlayer!=naturalUnstack.owner ||
                       live.CurrentResearch()!=naturalUnstack.research || research!=naturalUnstack.researchBefore ||
                       production.length!=naturalUnstack.production.length || production.unit!=naturalUnstack.production.unit ||
                       production.production!=naturalUnstack.production.production || production.needed!=naturalUnstack.production.needed ||
                       !sameBuildObservation(worker,naturalUnstack.worker))
                        throw std::runtime_error("Natural civilian unstack changed its worker, research, empty queue, owner or turn");
                    const auto generation=static_cast<unsigned long long>(window.SceneGeneration());
                    std::printf("INTERACTIVE_WORKER_UNSTACK_QUEUE=%u|%s|%d|%d|%d|%llu|%d|%d|%d|%d\n",naturalUnstack.cycles,phase,
                        world.turn,world.activePlayer,decisionCity,generation,production.length,production.unit,production.production,production.needed);
                    std::printf("INTERACTIVE_WORKER_UNSTACK_RESEARCH=%u|%s|%d|%d|%llu|%d|%d|%d\n",naturalUnstack.cycles,phase,
                        world.turn,world.activePlayer,generation,naturalUnstack.research,research[9],research[10]);
                    std::printf("INTERACTIVE_WORKER_UNSTACK_WORKER_STATE=%u|%s|%d|%d|%llu|%d|%d|%d|%d|%d|%d|%d|%d|%d|%d\n",
                        naturalUnstack.cycles,phase,world.turn,world.activePlayer,generation,
                        worker.unit,worker.plot,worker.build,worker.progress,worker.time,worker.improvement,worker.expected,worker.mission,worker.missionBuild,worker.moves);
                };
                const auto naturalPolicyPopupBoundary=[&](){
                    if(!naturalWorkerResearch || !naturalPolicyPending || !uiActive || live.UiKind()!=UiPopupKind::SocialPolicy ||
                       world.activePlayer!=naturalPolicyOwner || world.turn!=naturalPolicyTurn || window.SceneGeneration()<=naturalPolicyGeneration ||
                       !sameBuildObservation(live.ObserveBuild(context,workerID,workerBuild),naturalPolicyWorker))
                        throw std::runtime_error("Natural policy input lost its original popup, owner, turn, generation or worker");
                };
                const auto naturalPolicyTarget=[&](const char* phase,const std::string& id,int payload=-1)->std::uint64_t{
                    naturalPolicyPopupBoundary();std::uint64_t key=0;
                    for(const auto& target:live.UiTargets())if(target.id==id && (payload<0 || (target.hasVoid1 && target.void1==payload))){
                        if(key || !target.key || target.consumeMouseOnly)
                            throw std::runtime_error("Natural policy control has a duplicate or noncallback identity");
                        key=target.key;
                    }
                    if(!key)throw std::runtime_error("Natural policy control has no enabled original callback");
                    naturalPolicyGeneration=window.SceneGeneration();
                    std::printf("INTERACTIVE_WORKER_POLICY_TARGET=%u|%s|%d|0|%llu|%llu|%u|%d|%d\n",
                        naturalPolicyCycles,phase,naturalPolicyId,static_cast<unsigned long long>(key),
                        static_cast<unsigned long long>(naturalPolicyGeneration),uiRevision,world.turn,world.activePlayer);
                    return key;
                };
                const auto notificationButton=[&](int id,const char* phase)->std::uint64_t{
                    if(uiActive || !notificationActive)throw std::runtime_error("Notification smoke requires the original world list");
                    std::uint64_t key=0;
                    for(const auto& target:notificationTargets)if(target.hasVoid1 && target.void1==id){
                        if(key && key!=target.key)throw std::runtime_error("SDK notification has more than one visible original input control");
                        key=target.key;
                    }
                    if(!key)throw std::runtime_error("SDK notification has no visible original callback control");
                    std::printf("INTERACTIVE_NOTIFICATION_SMOKE_TARGET=%s|%d|%llu|%llu|%d\n",phase,id,
                        static_cast<unsigned long long>(key),static_cast<unsigned long long>(window.SceneGeneration()),world.turn);
                    return key;
                };
                const bool scienceVisible=!uiActive && topPanelActive && std::any_of(topPanelTargets.begin(),topPanelTargets.end(),
                    [](const UiInputTarget& target){return target.id=="SciencePerTurn";});
                if(gameMenuSmoke && gameMenuSmokeStage<12 && topPanelSmokeStage==3){
                    const auto state=SdkStateSnapshot::Capture(host);
                    if(gameMenuSmokeStage==0){
                        if(uiActive || !topPanelActive)throw std::runtime_error("GameMenu smoke requires the original world menu button");
                        gameMenuBeforeState=state;Write(directory+L"\\game-menu-before.txt",state);
                    }else if(state!=gameMenuBeforeState)
                        throw std::runtime_error("Original GameMenu input or quick save changed observed SDK gameplay state");
                    const bool expectedMenu=gameMenuSmokeStage==1 || (gameMenuSmokeStage>=3 && gameMenuSmokeStage<=7) || gameMenuSmokeStage==10;
                    if(uiActive!=expectedMenu || (uiActive && live.UiKind()!=UiPopupKind::GameMenu))
                        throw std::runtime_error("GameMenu smoke lost its expected menu or returned world context");
                    const auto targets=uiActive?live.UiTargets():topPanelTargets;
                    const auto targetKey=[&](const char* id)->std::uint64_t{
                        std::uint64_t key=0;
                        for(const auto& target:targets)if(target.id==id && !target.consumeMouseOnly){
                            if(key)throw std::runtime_error("Original GameMenu has duplicate callback input targets");key=target.key;
                        }
                        if(!key)throw std::runtime_error(std::string("Original GameMenu callback target is absent: ")+id);
                        return key;
                    };
                    const auto click=[&](const char* id){
                        next=targetKey(id);
                        std::printf("INTERACTIVE_GAME_MENU_SMOKE_TARGET=%u|%s|%llu|%llu|%d\n",gameMenuSmokeStage,id,
                            static_cast<unsigned long long>(next),static_cast<unsigned long long>(window.SceneGeneration()),world.turn);
                    };
                    const auto key=[&](unsigned value){
                        if(!PostMessageW(window.NativeHandle(),WM_KEYDOWN,value,1))
                            throw std::runtime_error("Cannot post original GameMenu native key input");
                        std::printf("INTERACTIVE_GAME_MENU_SMOKE_KEY=%u|%u|%llu|%d\n",gameMenuSmokeStage,value,
                            static_cast<unsigned long long>(window.SceneGeneration()),world.turn);
                    };
                    static const char* phases[]={"top-panel-open","return-button","world-escape","main-menu-confirm",
                        "confirmation-escape","unavailable-options","unavailable-no","quick-save","unknown-world-key",
                        "world-escape-again","menu-escape","returned"};
                    std::printf("INTERACTIVE_GAME_MENU_SMOKE_STEP=%u|%s|%llu|%d|STATE_UNCHANGED\n",gameMenuSmokeStage,
                        phases[gameMenuSmokeStage],static_cast<unsigned long long>(window.SceneGeneration()),world.turn);
                    switch(gameMenuSmokeStage){
                        case 0:click("MenuButton");break;
                        case 1:click("ReturnButton");break;
                        case 2:key(VK_ESCAPE);break;
                        case 3:click("MainMenuButton");break;
                        case 4:targetKey("Yes");targetKey("No");key(VK_ESCAPE);break;
                        case 5:
                            for(const auto& target:targets)if(target.id=="Yes" || target.id=="No")
                                throw std::runtime_error("Escape failed to dismiss the original confirmation while keeping GameMenu");
                            click("OptionsButton");break;
                        case 6:
                            for(const auto& target:targets)if(target.id=="Yes" && !target.consumeMouseOnly)
                                throw std::runtime_error("Unavailable menu information exposed an enabled affirmative exit action");
                            click("No");break;
                        case 7:click("QuickSaveButton");break;
                        case 8:key('Q');break;
                        case 9:key(VK_ESCAPE);break;
                        case 10:key(VK_ESCAPE);break;
                        case 11:
                            Write(directory+L"\\game-menu-after.txt",state);
                            std::printf("INTERACTIVE_GAME_MENU_SMOKE_COMPLETE=%llu|%d|STATE_UNCHANGED\n",
                                static_cast<unsigned long long>(window.SceneGeneration()),world.turn);break;
                    }
                    ++gameMenuSmokeStage;
                }else if(actionInfoEnabled && actionInfoUnitStage<3){
                    if(actionInfoUnitStage){
                        const auto ready=live.ReadyUnits();
                        const bool selected=std::any_of(world.ownedUnits.begin(),world.ownedUnits.end(),[&](const WorldViewState::Unit& u){
                            return u.selected && std::find(ready.begin(),ready.end(),u.id)!=ready.end();
                        });
                        if(uiActive || !selected || SdkStateSnapshot::Capture(host)!=actionInfoBeforeState)
                            throw std::runtime_error("Original blocker button failed its state-preserving ready-unit selection");
                        const auto phase=actionInfoUnitStage==1?"unit-right":"unit-left";
                        Write(directory+L"\\action-info-"+Wide(phase)+L"-after.txt",SdkStateSnapshot::Capture(host));
                        std::printf("INTERACTIVE_ACTION_INFO_SMOKE_VERIFIED=%s|%llu|%d\n",phase,
                            static_cast<unsigned long long>(window.SceneGeneration()),world.turn);
                        if(actionInfoUnitStage==2){actionInfoUnitStage=3;return;}
                    }
                    const auto observed=live.ObserveActionInfoPanel();
                    if(observed.blockingType!=ENDTURN_BLOCKING_UNITS && observed.blockingType!=ENDTURN_BLOCKING_STACKED_UNITS &&
                       observed.blockingType!=ENDTURN_BLOCKING_UNIT_NEEDS_ORDERS)
                        throw std::runtime_error("Initial ActionInfoPanel smoke lacks a genuine SDK unit blocker");
                    const auto phase=actionInfoUnitStage==0?"unit-right":"unit-left";
                    actionInfoBeforeState=SdkStateSnapshot::Capture(host);
                    Write(directory+L"\\action-info-"+Wide(phase)+L"-before.txt",actionInfoBeforeState);
                    next=actionInfoButton(phase);nextRight=actionInfoUnitStage==0;++actionInfoUnitStage;
                }else if(topPanelEnabled && topPanelSmokeStage<3 && (topPanelSmokeStage>0 || scienceVisible)){
                    if(topPanelSmokeStage==0){
                        if(uiActive || !topPanelActive)throw std::runtime_error("TopPanel smoke did not start on its world overlay");
                        for(const auto& target:topPanelTargets)if(target.id=="SciencePerTurn"){
                            if(next)throw std::runtime_error("TopPanel has duplicate SciencePerTurn input targets");next=target.key;
                        }
                        if(!next)throw std::runtime_error("Original TopPanel SciencePerTurn callback is absent");
                        topPanelBeforeState=SdkStateSnapshot::Capture(host);
                        Write(directory+L"\\top-panel-before.txt",topPanelBeforeState);
                        std::printf("INTERACTIVE_TOP_PANEL_SCIENCE_TARGET=%llu|%llu|%d\n",static_cast<unsigned long long>(next),
                            static_cast<unsigned long long>(window.SceneGeneration()),world.turn);topPanelSmokeStage=1;
                    }else if(topPanelSmokeStage==1){
                        if(!uiActive || live.UiKind()!=UiPopupKind::ResearchTree || SdkStateSnapshot::Capture(host)!=topPanelBeforeState)
                            throw std::runtime_error("Original TopPanel did not open its unchanged technology tree");
                        Write(directory+L"\\top-panel-tree.txt",SdkStateSnapshot::Capture(host));
                        if(!PostMessageW(window.NativeHandle(),WM_KEYDOWN,VK_ESCAPE,1))
                            throw std::runtime_error("Cannot post TopPanel research-tree Escape");
                        topPanelSmokeStage=2;
                    }else{
                        if(uiActive || !topPanelActive || SdkStateSnapshot::Capture(host)!=topPanelBeforeState)
                            throw std::runtime_error("TopPanel technology-tree return changed gameplay or lost the world overlay");
                        Write(directory+L"\\top-panel-returned.txt",SdkStateSnapshot::Capture(host));
                        std::printf("INTERACTIVE_TOP_PANEL_SCIENCE_RETURNED=%llu|%d|STATE_UNCHANGED\n",
                            static_cast<unsigned long long>(window.SceneGeneration()),world.turn);topPanelSmokeStage=3;
                    }
                }else if(economicSmoke && topPanelSmokeStage==3 && !economicScenario.Complete() &&
                         (economicScenario.Started() || (smokeStage==17 && !uiActive))){
                    std::vector<std::uint64_t> published;
                    for(const auto& hit:scene.hits)published.push_back(hit.controlKey);
                    const auto action=economicScenario.Advance(host,context,live,directory,!checkpoint.empty(),decisionCity,
                        uiActive,topPanelActive,uiActive?live.UiKind():UiPopupKind::Ranking,topPanelTargets,
                        uiActive?live.UiTargets():std::vector<UiInputTarget>{},published,window.SceneGeneration(),uiRevision);
                    next=action.key;
                    if(action.virtualKey && !PostMessageW(window.NativeHandle(),WM_KEYDOWN,action.virtualKey,1))
                        throw std::runtime_error("Cannot post the original economic overview Escape");
                    if(economicScenario.Complete()){
                        // The ordinary next-turn production baseline is taken
                        // at stage 17, after this verified real UI replacement.
                        decisionUnit=economicScenario.SelectedUnit();
                        std::printf("INTERACTIVE_ECONOMIC_DECISION_BASELINE=%d|%d|%d\n",decisionCity,decisionUnit,decisionTech);
                    }
                }else if(tradeRouteSmoke && topPanelSmokeStage==3 && tradeRouteSmokeStage<13 &&
                         (tradeRouteSmokeStage!=1 || !checkpoint.empty() || world.turn>initialTurn) &&
                         (tradeRouteSmokeStage>1 || !uiActive)){
                    const auto control=[&](const char* id,bool top){
                        std::uint64_t found=0;
                        for(const auto& target:top?topPanelTargets:live.UiTargets())if(target.id==id){
                            if(found)throw std::runtime_error("TradeRoute smoke found duplicate original callback targets");found=target.key;
                        }
                        if(!found)throw std::runtime_error(std::string("TradeRoute smoke lacks original callback: ")+id);
                        std::printf("INTERACTIVE_TRADE_ROUTE_ACTION=%u|%s|%llu|%llu|%u\n",tradeRouteSmokeStage,id,
                            static_cast<unsigned long long>(found),static_cast<unsigned long long>(window.SceneGeneration()),uiRevision);
                        return found;
                    };
                    const auto key=[&](int value,const char* id){
                        std::printf("INTERACTIVE_TRADE_ROUTE_ACTION=%u|%s|%d|%llu|%u\n",tradeRouteSmokeStage,id,value,
                            static_cast<unsigned long long>(window.SceneGeneration()),uiRevision);
                        if(!PostMessageW(window.NativeHandle(),WM_KEYDOWN,value,1))throw std::runtime_error("Cannot post original trade-route key input");
                    };
                    if(tradeRouteSmokeStage==0){
                        if(uiActive || !topPanelActive)throw std::runtime_error("TradeRoute fixture requires its idle world frame");
                        live.PrepareTradeRoutesSmoke(checkpoint.empty());
                        Write(directory+L"\\trade-route-prepared-inventory.json",live.CaptureTradeRoutesSmoke());
                        Write(directory+L"\\trade-route-prepared-presentation.json",live.CaptureTradeVisualsSmoke());
                        redraw=true;++tradeRouteSmokeStage;
                    }else if(tradeRouteSmokeStage==1){
                        if(uiActive || !topPanelActive)throw std::runtime_error("TradeRoute smoke must enter from original TopPanel");
                        tradeRouteBeforeInventory=live.CaptureTradeRoutesSmoke();
                        Write(directory+L"\\trade-route-before-inventory.json",tradeRouteBeforeInventory);
                        Write(directory+L"\\trade-route-before-presentation.json",live.CaptureTradeVisualsSmoke());
                        live.RequireTradeRoutesSmokeReady();
                        tradeRouteBeforeState=SdkStateSnapshot::Capture(host);
                        Write(directory+L"\\trade-route-before-state.txt",tradeRouteBeforeState);
                        next=control("InternationalTradeRoutes",true);++tradeRouteSmokeStage;
                    }else if(tradeRouteSmokeStage==10 || tradeRouteSmokeStage==12){
                        const auto state=SdkStateSnapshot::Capture(host),inventory=live.CaptureTradeRoutesSmoke();
                        if(uiActive || !topPanelActive || state!=tradeRouteBeforeState || inventory!=tradeRouteBeforeInventory)
                            throw std::runtime_error("TradeRoute return changed live SDK state or lost the original TopPanel");
                        Write(directory+L"\\trade-route-returned-"+std::to_wstring(tradeRouteSmokeStage)+L"-state.txt",state);
                        Write(directory+L"\\trade-route-returned-"+std::to_wstring(tradeRouteSmokeStage)+L"-inventory.json",inventory);
                        Write(directory+L"\\trade-route-returned-"+std::to_wstring(tradeRouteSmokeStage)+L"-presentation.json",live.CaptureTradeVisualsSmoke());
                        if(tradeRouteSmokeStage==10)next=control("InternationalTradeRoutes",true);
                        else std::printf("INTERACTIVE_TRADE_ROUTE_COMPLETE=%llu|%d|STATE_UNCHANGED\n",
                            static_cast<unsigned long long>(window.SceneGeneration()),world.turn);
                        ++tradeRouteSmokeStage;
                    }else{
                        if(!uiActive || live.UiKind()!=UiPopupKind::TradeRoute || SdkStateSnapshot::Capture(host)!=tradeRouteBeforeState ||
                           live.CaptureTradeRoutesSmoke()!=tradeRouteBeforeInventory)
                            throw std::runtime_error("Original TradeRoute input changed live SDK state or left its modal context");
                        switch(tradeRouteSmokeStage){
                        case 2:case 3:next=control("FromGPT",false);break;
                        case 4:next=control("TabButtonAvailableTR",false);break;
                        case 5:PostTradeRouteWheel(window,scene);break;
                        case 6:next=control("TabButtonTRWithYou",false);break;
                        case 7:next=control("TabButtonYourTR",false);break;
                        case 8:key(VK_RETURN,"KEY_RETURN");break;
                        case 9:next=control("CloseButton",false);break;
                        case 11:key(VK_ESCAPE,"KEY_ESCAPE");break;
                        default:throw std::logic_error("Unexpected trade-route smoke phase");
                        }
                        ++tradeRouteSmokeStage;
                    }
                }else if(policyTenetSmoke && topPanelSmokeStage==3 && tenetStage<21 &&
                         (tenetStage>0 || !uiActive)){
                    const auto inventory=[&](){return live.ObserveSocialPolicySmoke();};
                    const auto retain=[&](const wchar_t* label,const SocialPolicySmokeFixture::Inventory& value){
                        Write(directory+L"\\tenet-"+label+L"-inventory.json",SocialPolicySmokeFixture::Serialize(value));
                        Write(directory+L"\\tenet-"+label+L"-state.txt",SdkStateSnapshot::Capture(host));
                    };
                    const auto control=[&](const std::string& id,bool top=false,int payload=-1){
                        std::uint64_t found=0;
                        for(const auto& target:top?topPanelTargets:live.UiTargets())if(target.id==id){
                            const bool visible=std::any_of(scene.hits.begin(),scene.hits.end(),[&](const ZeroSisPresentation::HitRecord& hit){
                                return hit.controlKey==target.key;
                            }) || std::find(scene.pixelHits.keys.begin(),scene.pixelHits.keys.end(),target.key)!=scene.pixelHits.keys.end();
                            if(!visible)continue;
                            if(!target.key || (found && id!="TenetButton"))
                                throw std::runtime_error("Tenet smoke found a zero or duplicate fixed original callback key");
                            if(!found || target.key<found)found=target.key;
                        }
                        if(!found)throw std::runtime_error("Tenet smoke lacks its published original callback: "+id);
                        std::printf("INTERACTIVE_SOCIAL_POLICY_TENET_ACTION=%u|%s|%llu|%llu|%u|%d\n",tenetStage,id.c_str(),
                            static_cast<unsigned long long>(found),static_cast<unsigned long long>(window.SceneGeneration()),uiRevision,payload);
                        return found;
                    };
                    if(tenetStage==0){
                        tenetBefore=live.PreparePolicyTenetSmoke(checkpoint.empty());
                        tenetBeforeState=SdkStateSnapshot::Capture(host);retain(L"before",tenetBefore);
                        if(!checkpoint.empty()){tenetAfter=tenetBefore;tenetAfterState=tenetBeforeState;}
                        redraw=true;++tenetStage;
                    }else if(tenetStage==1 || tenetStage==18){
                        if(uiActive || !topPanelActive)throw std::runtime_error("Tenet smoke must enter through the original world TopPanel");
                        if(tenetStage==18 && (SdkStateSnapshot::Capture(host)!=tenetAfterState ||
                           SocialPolicySmokeFixture::Serialize(inventory())!=SocialPolicySmokeFixture::Serialize(tenetAfter)))
                            throw std::runtime_error("Tenet Close changed the actual SDK state");
                        next=control("CultureString",true);++tenetStage;
                    }else{
                        if(!uiActive || live.UiKind()!=UiPopupKind::SocialPolicy)
                            throw std::runtime_error("Tenet smoke lost the original policy modal context");
                        if(tenetStage<=9 && (SdkStateSnapshot::Capture(host)!=tenetBeforeState ||
                           SocialPolicySmokeFixture::Serialize(inventory())!=SocialPolicySmokeFixture::Serialize(tenetBefore)))
                            throw std::runtime_error("Tenet selection or cancellation mutated the SDK before Yes");
                        switch(tenetStage){
                        case 2:next=control("TabButtonIdeologies");if(!checkpoint.empty())tenetStage=16;break;
                        case 3:case 7:next=control("IdeologyButton11");break;
                        case 4:case 8:case 11:case 15:next=control("TenetButton");break;
                        case 5:next=control("TenetConfirmNo");break;
                        case 6:next=control("TenetCancelButton");break;
                        case 9:
                            retain(L"cancelled",inventory());selectedTenet=live.SelectedPolicyTenet();
                            next=control("TenetConfirmYes",false,selectedTenet);break;
                        case 10:
                            tenetFreeFirst=inventory();SocialPolicySmokeFixture::RequireTenetAdoption(tenetBefore,tenetFreeFirst,selectedTenet);
                            retain(L"free-1",tenetFreeFirst);next=control("IdeologyButton12");break;
                        case 12:
                            if(SocialPolicySmokeFixture::Serialize(inventory())!=SocialPolicySmokeFixture::Serialize(tenetFreeFirst))
                                throw std::runtime_error("Second free tenet selection changed the SDK before confirmation");
                            selectedTenet=live.SelectedPolicyTenet();next=control("TenetConfirmYes",false,selectedTenet);break;
                        case 13:
                            tenetFreeSecond=inventory();SocialPolicySmokeFixture::RequireTenetAdoption(tenetFreeFirst,tenetFreeSecond,selectedTenet);
                            retain(L"free-2",tenetFreeSecond);
                            tenetFunded=live.FundPaidPolicyTenetSmoke();retain(L"funded",tenetFunded);redraw=true;break;
                        case 14:next=control("IdeologyButton13");break;
                        case 16:
                            if(SocialPolicySmokeFixture::Serialize(inventory())!=SocialPolicySmokeFixture::Serialize(tenetFunded))
                                throw std::runtime_error("Paid tenet selection changed the SDK before confirmation");
                            selectedTenet=live.SelectedPolicyTenet();next=control("TenetConfirmYes",false,selectedTenet);break;
                        case 17:
                            if(checkpoint.empty()){
                                tenetAfter=inventory();SocialPolicySmokeFixture::RequireTenetAdoption(tenetFunded,tenetAfter,selectedTenet);
                                if(tenetAfter.freeTenets!=0 || tenetAfter.culture!=0)
                                    throw std::runtime_error("Tenet smoke retained a mandatory adoption resource");
                            }else if(SdkStateSnapshot::Capture(host)!=tenetBeforeState ||
                                    SocialPolicySmokeFixture::Serialize(inventory())!=SocialPolicySmokeFixture::Serialize(tenetBefore))
                                throw std::runtime_error("Restored ideology view changed the saved SDK tenets");
                            tenetAfterState=SdkStateSnapshot::Capture(host);retain(L"adopted",tenetAfter);next=control("CloseButton");break;
                        case 19:next=control("TabButtonIdeologies");break;
                        case 20:
                            if(SdkStateSnapshot::Capture(host)!=tenetAfterState ||
                               SocialPolicySmokeFixture::Serialize(inventory())!=SocialPolicySmokeFixture::Serialize(tenetAfter))
                                throw std::runtime_error("Tenet reopen changed the saved SDK state");
                            std::printf("INTERACTIVE_SOCIAL_POLICY_TENET_ACTION=%u|KEY_ESCAPE|27|%llu|%u|-1\n",tenetStage,
                                static_cast<unsigned long long>(window.SceneGeneration()),uiRevision);
                            if(!PostMessageW(window.NativeHandle(),WM_KEYDOWN,VK_ESCAPE,1))
                                throw std::runtime_error("Cannot post original ideology Escape");
                            break;
                        default:throw std::logic_error("Unexpected original tenet smoke stage");
                        }
                        ++tenetStage;
                    }
                }else if(policyTenetSmoke && tenetStage==21){
                    if(uiActive || !topPanelActive || SdkStateSnapshot::Capture(host)!=tenetAfterState ||
                       SocialPolicySmokeFixture::Serialize(live.ObserveSocialPolicySmoke())!=SocialPolicySmokeFixture::Serialize(tenetAfter))
                        throw std::runtime_error("Tenet Escape lost world input or changed saved gameplay");
                    Write(directory+L"\\tenet-returned-inventory.json",SocialPolicySmokeFixture::Serialize(live.ObserveSocialPolicySmoke()));
                    Write(directory+L"\\tenet-returned-state.txt",SdkStateSnapshot::Capture(host));
                    std::printf("INTERACTIVE_SOCIAL_POLICY_TENET_COMPLETE=%u|%d|%s\n",uiRevision,world.turn,
                        checkpoint.empty()?"THREE_TENETS_AND_RETURN":"RESTORED_TENETS_UNCHANGED_AND_RETURN");++tenetStage;
                }else if(socialPolicySmoke && !policyTenetSmoke && topPanelSmokeStage==3 && socialPolicyStage<18 &&
                         (socialPolicyStage>0 || !uiActive)){
                    const auto inventory=[&](){return live.ObserveSocialPolicySmoke();};
                    const auto retain=[&](const wchar_t* label,const SocialPolicySmokeFixture::Inventory& value){
                        Write(directory+L"\\social-policy-"+label+L"-inventory.json",SocialPolicySmokeFixture::Serialize(value));
                        Write(directory+L"\\social-policy-"+label+L"-state.txt",SdkStateSnapshot::Capture(host));
                    };
                    const auto control=[&](const std::string& id,bool top,int payload=-1){
                        std::uint64_t found=0;
                        for(const auto& target:top?topPanelTargets:live.UiTargets())if(target.id==id &&
                            (payload<0 || (target.hasVoid1 && target.void1==payload))){
                            if(found || !target.key)throw std::runtime_error("SocialPolicy smoke found duplicate or zero original callback key");
                            found=target.key;
                        }
                        if(!found)throw std::runtime_error("SocialPolicy smoke lacks original visible callback: "+id);
                        // PostClick will additionally require this exact key in
                        // the published native frame. Key zero is never a hit.
                        std::printf("INTERACTIVE_SOCIAL_POLICY_ACTION=%u|%s|%llu|%llu|%u|%d\n",socialPolicyStage,id.c_str(),
                            static_cast<unsigned long long>(found),static_cast<unsigned long long>(window.SceneGeneration()),uiRevision,payload);
                        return found;
                    };
                    if(socialPolicyStage==0){
                        socialPolicyBefore=live.PrepareSocialPolicySmoke(checkpoint.empty());
                        socialPolicyBeforeState=SdkStateSnapshot::Capture(host);retain(L"before",socialPolicyBefore);
                        if(checkpoint.empty()){
                            for(const auto& branch:socialPolicyBefore.branches)if(!branch.unlocked && branch.canUnlock && !branch.blocked && branch.freePolicy>=0){
                                socialPolicyBranch=branch.id;break;
                            }
                            if(socialPolicyBranch<0)throw std::runtime_error("SocialPolicy smoke has no legal branch ID");
                        }else{
                            socialPolicyAfter=socialPolicyBefore;socialPolicyAfterState=socialPolicyBeforeState;
                        }
                        redraw=true;++socialPolicyStage;
                    }else if(socialPolicyStage==1 || socialPolicyStage==16){
                        if(uiActive || !topPanelActive)throw std::runtime_error("SocialPolicy must enter through the retained world TopPanel");
                        if(socialPolicyStage==16 && (SdkStateSnapshot::Capture(host)!=socialPolicyAfterState ||
                            SocialPolicySmokeFixture::Serialize(inventory())!=SocialPolicySmokeFixture::Serialize(socialPolicyAfter)))
                            throw std::runtime_error("SocialPolicy Close changed the actual SDK state");
                        next=control("CultureString",true);
                        if(socialPolicyStage==1 && !checkpoint.empty())socialPolicyStage=8;
                        ++socialPolicyStage;
                    }else{
                        if(!uiActive || live.UiKind()!=UiPopupKind::SocialPolicy)
                            throw std::runtime_error("SocialPolicy posted input lost its original modal context");
                        if(socialPolicyStage<=5 && (SdkStateSnapshot::Capture(host)!=socialPolicyBeforeState ||
                            SocialPolicySmokeFixture::Serialize(inventory())!=SocialPolicySmokeFixture::Serialize(socialPolicyBefore)))
                            throw std::runtime_error("SocialPolicy selection or No changed the SDK before confirmation");
                        switch(socialPolicyStage){
                        case 2:case 4:next=control("BranchButton"+std::to_string(socialPolicyBranch),false,socialPolicyBranch);break;
                        case 3:next=control("No",false);break;
                        case 5:retain(L"cancelled",inventory());next=control("Yes",false);break;
                        case 6:{
                            socialPolicyAfterBranch=inventory();
                            SocialPolicySmokeFixture::RequireAdoption(socialPolicyBefore,socialPolicyAfterBranch,socialPolicyBranch,false);
                            if(socialPolicyAfterBranch.culture!=0)throw std::runtime_error("Exact branch fixture retained surplus culture");
                            retain(L"branch",socialPolicyAfterBranch);
                            socialPolicyFunded=live.FundSecondSocialPolicySmoke();retain(L"funded",socialPolicyFunded);
                            redraw=true;break;
                        }
                        case 7:{
                            for(const auto& policy:socialPolicyFunded.policies)if(policy.branch==socialPolicyBranch && !policy.has && policy.canAdopt && !policy.blocked){
                                socialPolicyChoice=policy.id;break;
                            }
                            if(socialPolicyChoice<0)throw std::runtime_error("Adopted SDK branch has no legal paid policy choice");
                            next=control("PolicyIcon",false,socialPolicyChoice);break;
                        }
                        case 8:
                            if(SocialPolicySmokeFixture::Serialize(inventory())!=SocialPolicySmokeFixture::Serialize(socialPolicyFunded))
                                throw std::runtime_error("Policy selection changed SDK state before Yes");
                            next=control("Yes",false);break;
                        case 9:
                            if(checkpoint.empty()){
                                socialPolicyAfter=inventory();
                                SocialPolicySmokeFixture::RequireAdoption(socialPolicyFunded,socialPolicyAfter,socialPolicyChoice,true);
                                if(socialPolicyAfter.culture!=0)throw std::runtime_error("Exact policy fixture retained surplus culture");
                                std::printf("INTERACTIVE_SOCIAL_POLICY_ADOPTED=%d|%d|%d|%d|%d|%d|%d\n",world.activePlayer,socialPolicyBranch,
                                    socialPolicyChoice,socialPolicyBefore.culture,socialPolicyAfterBranch.culture,socialPolicyAfter.culture,world.turn);
                            }else if(SdkStateSnapshot::Capture(host)!=socialPolicyBeforeState ||
                                    SocialPolicySmokeFixture::Serialize(inventory())!=SocialPolicySmokeFixture::Serialize(socialPolicyBefore))
                                throw std::runtime_error("Restored policy popup altered saved SDK policies or culture");
                            socialPolicyAfterState=SdkStateSnapshot::Capture(host);retain(L"adopted",socialPolicyAfter);
                            next=control("TabButtonIdeologies",false);break;
                        case 10:next=control("TabButtonSocialPolicies",false);break;
                        case 11:next=control("PolicyInfo",false);break;
                        case 12:
                            if(SdkStateSnapshot::Capture(host)!=socialPolicyAfterState ||
                               SocialPolicySmokeFixture::Serialize(inventory())!=SocialPolicySmokeFixture::Serialize(socialPolicyAfter))
                                throw std::runtime_error("SocialPolicy tabs or checkbox changed gameplay state");
                            next=control("CloseButton",false);socialPolicyStage=15;break;
                        case 17:
                            if(SdkStateSnapshot::Capture(host)!=socialPolicyAfterState ||
                               SocialPolicySmokeFixture::Serialize(inventory())!=SocialPolicySmokeFixture::Serialize(socialPolicyAfter))
                                throw std::runtime_error("SocialPolicy reopen changed gameplay state");
                            std::printf("INTERACTIVE_SOCIAL_POLICY_ACTION=%u|KEY_ESCAPE|27|%llu|%u|-1\n",socialPolicyStage,
                                static_cast<unsigned long long>(window.SceneGeneration()),uiRevision);
                            if(!PostMessageW(window.NativeHandle(),WM_KEYDOWN,VK_ESCAPE,1))
                                throw std::runtime_error("Cannot post original SocialPolicy Escape");
                            break;
                        default:throw std::logic_error("Unexpected SocialPolicy smoke stage");
                        }
                        ++socialPolicyStage;
                    }
                }else if(socialPolicySmoke && !policyTenetSmoke && socialPolicyStage==18){
                    if(uiActive || !topPanelActive || SdkStateSnapshot::Capture(host)!=socialPolicyAfterState ||
                       SocialPolicySmokeFixture::Serialize(live.ObserveSocialPolicySmoke())!=SocialPolicySmokeFixture::Serialize(socialPolicyAfter))
                        throw std::runtime_error("SocialPolicy Escape lost world input or changed gameplay");
                    Write(directory+L"\\social-policy-returned-inventory.json",SocialPolicySmokeFixture::Serialize(live.ObserveSocialPolicySmoke()));
                    Write(directory+L"\\social-policy-returned-state.txt",SdkStateSnapshot::Capture(host));
                    std::printf("INTERACTIVE_SOCIAL_POLICY_COMPLETE=%llu|%d|%s\n",
                        static_cast<unsigned long long>(window.SceneGeneration()),world.turn,
                        checkpoint.empty()?"TWO_PAID_ADOPTIONS_AND_RETURN":"RESTORED_POLICIES_UNCHANGED_AND_RETURN");++socialPolicyStage;
                }else if(uiActive && live.UiKind()==UiPopupKind::TechAward){
                    // The real SDK technology grants in the explicit trade
                    // fixture issue their normal awards, even without the
                    // optional announcement flag. Dismiss them through the
                    // original Continue callback before advancing the turn.
                    if(tradeRouteSmoke && tradeRouteSmokeStage==1 && checkpoint.empty() && world.turn==initialTurn){
                        const int technology=live.TechAwardTechnology();
                        if(++tradeRouteFixtureAwards>2 || !live.HasTechnology(technology))
                            throw std::runtime_error("Unexpected technology award from the bounded trade-route fixture");
                        for(const auto& target:live.UiTargets())if(target.id=="ContinueButton"){
                            if(next)throw std::runtime_error("Trade-route fixture award has duplicate Continue callbacks");next=target.key;
                        }
                        if(!next)throw std::runtime_error("Trade-route fixture award lacks its original Continue callback");
                        std::printf("INTERACTIVE_TRADE_ROUTE_FIXTURE_TECH_AWARD=%d|%llu|%llu|%d\n",technology,
                            static_cast<unsigned long long>(next),static_cast<unsigned long long>(window.SceneGeneration()),world.turn);
                        return;
                    }
                    if(naturalWorkerResearch){
                        const int technology=live.TechAwardTechnology();
                        if(smokeStage!=4 || world.turn!=workerResearchTurn+1 || world.turn<=initialTurn || world.turn>initialTurn+32 ||
                           world.activePlayer!=workerResearchBefore[2] || technology!=workerResearchTech || naturalAwardPending ||
                           window.SceneGeneration()<=naturalAwardGeneration || !live.HasTechnology(technology) ||
                           std::find(naturalAwardedTechnologies.begin(),naturalAwardedTechnologies.end(),technology)!=naturalAwardedTechnologies.end())
                            throw std::runtime_error("Unexpected, untracked or repeated natural research award in worker turns");
                        for(const auto& target:live.UiTargets())if(target.id=="ContinueButton" && !target.consumeMouseOnly){
                            if(next)throw std::runtime_error("Natural research award has duplicate Continue callbacks");next=target.key;
                        }
                        if(!next)throw std::runtime_error("Natural research award lacks its visible original Continue callback");
                        naturalAwardTurn=world.turn;naturalAwardTech=technology;naturalAwardGeneration=window.SceneGeneration();
                        naturalAwardWorker=live.ObserveBuild(context,workerID,workerBuild);naturalAwardState=SdkStateSnapshot::Capture(host);
                        naturalAwardedTechnologies.push_back(technology);naturalAwardPending=true;
                        std::printf("INTERACTIVE_WORKER_TECH_AWARD_TARGET=%d|%d|%d|%llu|%llu|1\n",world.turn,world.activePlayer,technology,
                            static_cast<unsigned long long>(next),static_cast<unsigned long long>(naturalAwardGeneration));
                        return;
                    }
                    if(!techAwardSmoke || smokeStage!=4 || ++techAwardChoices!=1 ||
                       lastTechAwardGeneration==window.SceneGeneration() || live.TechAwardTechnology()!=decisionTech || !live.HasTechnology(decisionTech))
                        throw std::runtime_error("Unexpected or repeated original technology award in finite smoke");
                    lastTechAwardGeneration=window.SceneGeneration();
                    for(const auto& target:live.UiTargets())if(target.id=="ContinueButton"){
                        if(next)throw std::runtime_error("Technology award has duplicate Continue callbacks");next=target.key;
                    }
                    if(!next)throw std::runtime_error("Technology award lacks its visible original Continue callback");
                    std::printf("INTERACTIVE_TECH_AWARD_TARGET=%d|%llu|%llu|%d\n",decisionTech,static_cast<unsigned long long>(next),
                        static_cast<unsigned long long>(window.SceneGeneration()),world.turn);
                }else if(uiActive && live.UiKind()==UiPopupKind::LeaderHead){
                    if(lastLeaderSmokeGeneration==window.SceneGeneration() || ++leaderSmokeChoices>8)
                        throw std::runtime_error("Original leader return failed to settle in the bounded smoke");
                    lastLeaderSmokeGeneration=window.SceneGeneration();next=live.LeaderBackKey();
                    std::printf("INTERACTIVE_DIPLOMACY_CHOICE=%llu|%llu\n",static_cast<unsigned long long>(next),
                        static_cast<unsigned long long>(window.SceneGeneration()));
                }else if(naturalWorkerResearch && smokeStage==0 && unitCycleStage<3 && !uiActive){
                    if(!unitPanelActive || world.selectedUnits.size()!=1 || world.selectedUnits.front().first!=world.activePlayer)
                        throw std::runtime_error("Original unit cycle requires its visible panel and one active-player selection");
                    const auto chosen=std::find_if(world.ownedUnits.begin(),world.ownedUnits.end(),
                        [&](const WorldViewState::Unit& unit){return unit.id==world.selectedUnits.front().second && unit.selected;});
                    if(chosen==world.ownedUnits.end())throw std::runtime_error("Original unit cycle lost its selected SDK unit");
                    std::unique_ptr<ICvGame1> current(context.GetGame());
                    if(!current)throw std::runtime_error("Original unit cycle has no current SDK game");
                    std::unique_ptr<ICvRandom1> random(current->GetRandomNumberGenerator());
                    if(!random)throw std::runtime_error("Original unit cycle has no synchronous RNG");
                    const auto state=SdkStateSnapshot::Capture(host);
                    const auto ready=live.ReadyUnits();
                    if(unitCycleStage==0){
                        if(ready.empty() || std::find(ready.begin(),ready.end(),chosen->id)==ready.end() ||
                           (checkpoint.empty() && ready.size()<2))
                            throw std::runtime_error("Original cycle scenario lacks its initial ready unit profile");
                        unitCycleInitial=chosen->id;unitCycleReady=ready;
                        unitCycleBefore=state;unitCycleSeed=random->GetSeed();
                        Write(directory+L"\\unit-cycle-before-state.txt",state);
                    }else{
                        if(state!=unitCycleBefore || random->GetSeed()!=unitCycleSeed || ready!=unitCycleReady ||
                           window.SceneGeneration()<=unitCycleGeneration ||
                           host.cameraPresentations.size()!=unitCycleCameraCount+1)
                            throw std::runtime_error("Original unit cycle changed semantic gameplay/RNG/readiness or lost its single camera request");
                        const auto& focus=host.cameraPresentations.back();
                        if(focus.plotIndex!=chosen->plotIndex || focus.x!=chosen->x || focus.y!=chosen->y ||
                           focus.type!=CAMERALOOKAT_NORMAL || cameraX!=chosen->x || cameraY!=chosen->y ||
                           (unitCycleReady.size()>1 && chosen->id==unitCyclePrevious))
                            throw std::runtime_error("Original unit cycle did not focus the newly selected unit's real plot");
                        const wchar_t* label=unitCycleStage==1?L"right":L"left";
                        Write(directory+L"\\unit-cycle-"+label+L"-state.txt",state);
                        std::printf("INTERACTIVE_UNIT_CYCLE_OBSERVED=%s|%d|%d|%d|%d|%d|%d|%d|%d|%llu|%zu|%lu\n",
                            unitCycleStage==1?"right":"left",world.turn,world.activePlayer,chosen->id,chosen->plotIndex,
                            chosen->x,chosen->y,cameraX,cameraY,static_cast<unsigned long long>(window.SceneGeneration()),
                            host.cameraPresentations.size(),random->GetSeed());
                        if(unitCycleStage==2){
                            if(chosen->id!=unitCycleInitial)throw std::runtime_error("Original left/right unit cycle did not return to its initial selection");
                            unitCycleStage=3;
                        }
                    }
                    if(unitCycleStage<2){
                        const char* id=unitCycleStage==0?"CycleRight":"CycleLeft";
                        for(const auto& target:unitPanelTargets)if(target.id==id && !target.consumeMouseOnly){
                            if(next)throw std::runtime_error("Original unit cycle has duplicate visible callbacks");next=target.key;
                        }
                        if(!next)throw std::runtime_error("Original unit cycle has no visible callback target");
                        unitCyclePrevious=chosen->id;unitCycleCameraCount=host.cameraPresentations.size();
                        unitCycleGeneration=window.SceneGeneration();
                        std::printf("INTERACTIVE_UNIT_CYCLE_TARGET=%s|%d|%d|%d|%zu|%llu|%llu|%zu|%lu\n",
                            unitCycleStage==0?"right":"left",world.turn,world.activePlayer,chosen->id,unitCycleReady.size(),
                            static_cast<unsigned long long>(next),static_cast<unsigned long long>(unitCycleGeneration),
                            unitCycleCameraCount,unitCycleSeed);
                        ++unitCycleStage;
                    }
                }else if(smokeStage==0){
                    for(const auto& unit:world.ownedUnits)if(unit.type!="UNIT_SETTLER" && unit.moves>0 &&
                        (!actionSmoke || (live.IsFortifyLegal(context,unit.id) && live.UnitActivity(unit.id)!=ACTIVITY_SLEEP))){
                        smokeUnit=unit.id;break;
                    }
                    if(smokeUnit<0)throw std::runtime_error("Gameplay smoke has no eligible mobile unit for its requested action");
                    next=WorldViewHitKey::OwnedUnit(smokeUnit);smokeStage=actionSmoke?20:1;
                }else if(smokeStage==1){
                    const auto chosen=std::find_if(world.ownedUnits.begin(),world.ownedUnits.end(),[&](const WorldViewState::Unit& unit){return unit.id==smokeUnit && unit.selected;});
                    if(chosen==world.ownedUnits.end())throw std::runtime_error("Posted gameplay selection did not select the real unit");
                    originX=chosen->x;originY=chosen->y;
                    for(const auto& plot:world.plots)if(plot.visible &&
                        std::none_of(world.ownedUnits.begin(),world.ownedUnits.end(),[&](const WorldViewState::Unit& u){return u.x==plot.x && u.y==plot.y;}) &&
                        live.IsAdjacentMoveLegal(smokeUnit,plot.x,plot.y)){
                        targetX=plot.x;targetY=plot.y;next=WorldViewHitKey::Plot(plot.index);break;
                    }
                    if(!next)throw std::runtime_error("Gameplay smoke has no visible legal adjacent destination");
                    leftSelectState=SdkStateSnapshot::Capture(host);
                    SdkStateSnapshot::Write(directory+L"\\play-left-select-before-state.txt",leftSelectState);smokeStage=101;
                }else if(smokeStage==101){
                    const auto after=SdkStateSnapshot::Capture(host);
                    if(after!=leftSelectState)throw std::runtime_error("Left plot selection changed SDK gameplay state");
                    SdkStateSnapshot::Write(directory+L"\\play-left-select-after-state.txt",after);
                    std::printf("INTERACTIVE_LEFT_SELECT_STATE_UNCHANGED=%d|%d|%d\n",smokeUnit,targetX,targetY);
                    next=WorldViewHitKey::OwnedUnit(smokeUnit);smokeStage=102;
                }else if(smokeStage==102){
                    for(const auto& plot:world.plots)if(plot.x==targetX && plot.y==targetY)next=WorldViewHitKey::Plot(plot.index);
                    nextRight=true;smokeStage=2;
                }else if(smokeStage==2){
                    const auto moved=std::find_if(world.ownedUnits.begin(),world.ownedUnits.end(),[&](const WorldViewState::Unit& unit){return unit.id==smokeUnit && unit.x==targetX && unit.y==targetY;});
                    if(moved==world.ownedUnits.end())throw std::runtime_error("Posted movement did not move the SDK unit to its destination");
                    if(moved->moves<=0 && !unitActions.empty())throw std::runtime_error("Exhausted unit still has published mission actions");
                    smokeMoved=true;std::printf("INTERACTIVE_SMOKE_MOVEMENT_VERIFIED=%d|%d|%d\n",smokeUnit,targetX,targetY);
                    live.PrepareQueuedMoveSmoke(smokeUnit);next=WorldViewHitKey::OwnedUnit(smokeUnit);smokeStage=103;
                }else if(smokeStage==103){
                    for(const auto& plot:world.plots)if(plot.x==originX && plot.y==originY)next=WorldViewHitKey::Plot(plot.index);
                    nextRight=true;nextShift=true;smokeStage=104;
                }else if(smokeStage==104){
                    const auto order=live.ObserveQueuedMove(smokeUnit);
                    if(order[0]!=targetX || order[1]!=targetY || order[2]!=0 || order[3]!=context.GetInfoTypeForString("MISSION_MOVE_TO",true) ||
                       order[4]!=originX || order[5]!=originY)throw std::runtime_error("Shift right click did not retain the SDK move order");
                    std::printf("INTERACTIVE_SHIFT_ORDER_VERIFIED=%d|%d|%d|%d|%d|%d\n",smokeUnit,targetX,targetY,order[3],originX,originY);
                    next=WorldViewHitKey::OwnedUnit(smokeUnit);nextRight=true;smokeStage=105;
                }else if(smokeStage==105){
                    const auto order=live.ObserveQueuedMove(smokeUnit);
                    if(order[0]!=targetX || order[1]!=targetY || order[2]!=0 || order[3]!=-1)
                        throw std::runtime_error("Same-plot right click did not cancel the SDK queued move");
                    std::printf("INTERACTIVE_RIGHT_CANCEL_VERIFIED=%d|%d|%d\n",smokeUnit,targetX,targetY);
                    smokeStage=decisions?10:3;
                }else if(smokeStage==20){
                    actionMission=context.GetInfoTypeForString("MISSION_FORTIFY",true);
                    const int originalAction=live.OriginalUnitMissionAction(actionMission);
                    if(!unitPanelActive)throw std::runtime_error("Original UnitPanel is absent for its fortify test");
                    for(const auto& target:unitPanelTargets)if(target.hasVoid1 && target.void1==originalAction &&
                        (target.id=="UnitActionButton" || target.id=="RecommendedActionButton")){
                        next=target.key;break;
                    }
                    if(!next && !actionSecondaryOpened){
                        // Stock UnitPanel places lower-priority actions in its
                        // collapsed secondary stack. Open it through the same
                        // visible original button used by a human player.
                        for(const auto& target:unitPanelTargets)if(target.id=="SecondaryButton"){
                            next=target.key;break;
                        }
                        if(!next)throw std::runtime_error("Original UnitPanel has neither a fortify target nor its secondary action button");
                        std::printf("INTERACTIVE_ORIGINAL_UNIT_SECONDARY_TARGET=%llu\n",static_cast<unsigned long long>(next));
                        // Stay in the unit-action phase while its original
                        // secondary stack is opened. Phase 22 belongs to the
                        // existing CityView return sequence.
                        actionSecondaryOpened=true;
                    }else{
                        if(!next)throw std::runtime_error("Original UnitPanel has no legal registered fortify button after opening secondary actions");
                        std::printf("INTERACTIVE_ORIGINAL_UNIT_ACTION_TARGET=%d|%d|%llu\n",smokeUnit,originalAction,static_cast<unsigned long long>(next));
                        actionBefore=live.UnitActivity(smokeUnit);
                        std::printf("INTERACTIVE_UNIT_ACTION_TARGET=%d|%d|%llu|%d|%llu\n",smokeUnit,actionMission,static_cast<unsigned long long>(next),actionBefore,
                            static_cast<unsigned long long>(window.SceneGeneration()));
                        smokeStage=21;
                    }
                }else if(smokeStage==21){
                    const int after=live.UnitActivity(smokeUnit);const auto ready=live.ReadyUnits();
                    const bool stillReady=std::find(ready.begin(),ready.end(),smokeUnit)!=ready.end();
                    std::printf("INTERACTIVE_UNIT_ACTION_OBSERVED=%d|%d|%d|%d|%d\n",smokeUnit,actionMission,actionBefore,after,stillReady?1:0);
                    if(actionBefore==after || after!=ACTIVITY_SLEEP || stillReady)
                        throw std::runtime_error("Posted fortify action did not change original SDK activity and readiness");
                    std::printf("INTERACTIVE_UNIT_ACTION_SMOKE_VERIFIED=%d|%d|%d|%d\n",smokeUnit,actionMission,actionBefore,after);
                    smokeStage=1;
                }else if(smokeStage==10){
                    for(const auto& city:world.visibleCities)if(city.owner==world.activePlayer){decisionCity=city.id;break;}
                    if(decisionCity>=0){smokeStage=12;}
                    else{
                        for(const auto& unit:world.ownedUnits)if(unit.type=="UNIT_SETTLER"){next=WorldViewHitKey::OwnedUnit(unit.id);break;}
                        if(!next)throw std::runtime_error("Integrated decision smoke has neither a city nor a settler");smokeStage=11;
                    }
                }else if(smokeStage==11){
                    const auto selected=host.localSelection.Snapshot();
                    if(selected.size()!=1 || selected.front().first!=world.activePlayer)
                        throw std::runtime_error("Original found smoke lacks its selected active-player settler");
                    if(originalMissionButton("found",selected.front().second,context.GetInfoTypeForString("MISSION_FOUND",true),-1))smokeStage=12;
                }else if(smokeStage==12){
                    if(uiActive){
                        if(notificationEnabled && notificationSmokeStage==1){
                            if(live.UiKind()!=notificationSmokeKind || SdkStateSnapshot::Capture(host)!=notificationBeforeState)
                                throw std::runtime_error("Original notification selected the wrong SDK popup or changed gameplay");
                            std::printf("INTERACTIVE_NOTIFICATION_POPUP_OPENED=%d|%s|%llu|%d\n",notificationSmokeId,
                                notificationSmokeKind==UiPopupKind::Production?"production":"research",
                                static_cast<unsigned long long>(window.SceneGeneration()),world.turn);
                            notificationSmokeStage=2;
                        }
                        if(actionInfoEnabled && actionInfoNotificationStage==1){
                            if(live.UiKind()!=actionInfoNotificationKind || SdkStateSnapshot::Capture(host)!=actionInfoBeforeState)
                                throw std::runtime_error("Actual blocker notification opened the wrong original popup or changed game state");
                            std::printf("INTERACTIVE_ACTION_INFO_NOTIFICATION_OPENED=%s|%llu|%d\n",
                                actionInfoNotificationKind==UiPopupKind::Production?"production":"research",
                                static_cast<unsigned long long>(window.SceneGeneration()),world.turn);
                            actionInfoNotificationStage=2;
                        }
                        if(!PostMessageW(window.NativeHandle(),WM_KEYDOWN,VK_ESCAPE,1))throw std::runtime_error("Cannot close an automatic original decision popup");
                    }else{
                        if(notificationEnabled && checkpoint.empty() && notificationSmokeStage<4){
                            if(notificationSmokeStage==0){
                                const auto observed=live.ObserveActionInfoPanel();notificationSmokeId=observed.notificationIndex;
                                if(notificationSmokeId<0 || (observed.blockingType!=ENDTURN_BLOCKING_PRODUCTION && observed.blockingType!=ENDTURN_BLOCKING_RESEARCH))
                                    throw std::runtime_error("Founded city lacks its natural production/research notification");
                                notificationSmokeKind=observed.blockingType==ENDTURN_BLOCKING_PRODUCTION?UiPopupKind::Production:UiPopupKind::Research;
                                notificationBeforeState=SdkStateSnapshot::Capture(host);
                                Write(directory+L"\\notification-open-before.txt",notificationBeforeState);
                                next=notificationButton(notificationSmokeId,"open");notificationSmokeStage=1;return;
                            }
                            if(notificationSmokeStage==2){
                                if(SdkStateSnapshot::Capture(host)!=notificationBeforeState)
                                    throw std::runtime_error("Original notification popup close changed gameplay");
                                Write(directory+L"\\notification-open-after.txt",SdkStateSnapshot::Capture(host));
                                std::unique_ptr<ICvGame1> current(context.GetGame());
                                std::unique_ptr<ICvPlayer1> player(current?current->GetPlayer(static_cast<PlayerTypes>(world.activePlayer)):nullptr);
                                if(!player || player->MayUserDismissNotification(notificationSmokeId))
                                    throw std::runtime_error("Mandatory notification unexpectedly permits user dismissal");
                                std::printf("INTERACTIVE_NOTIFICATION_OPEN_VERIFIED=%d|%llu|%d|STATE_UNCHANGED\n",notificationSmokeId,
                                    static_cast<unsigned long long>(window.SceneGeneration()),world.turn);
                                Write(directory+L"\\notification-dismiss-before.txt",notificationBeforeState);
                                next=notificationButton(notificationSmokeId,"dismiss-blocked");nextRight=true;notificationSmokeStage=3;return;
                            }
                            if(notificationSmokeStage==3){
                                if(SdkStateSnapshot::Capture(host)!=notificationBeforeState)
                                    throw std::runtime_error("Rejected mandatory notification dismissal changed gameplay");
                                {std::lock_guard<std::mutex> guard(host.dataMutex);
                                 if(host.notifications.find({world.activePlayer,notificationSmokeId})==host.notifications.end())
                                    throw std::runtime_error("Rejected mandatory notification disappeared from SDK presentation");}
                                Write(directory+L"\\notification-dismiss-after.txt",SdkStateSnapshot::Capture(host));
                                std::printf("INTERACTIVE_NOTIFICATION_DISMISS_BLOCKED=%d|%llu|%d|STATE_UNCHANGED\n",notificationSmokeId,
                                    static_cast<unsigned long long>(window.SceneGeneration()),world.turn);
                                notificationSmokeStage=4;
                            }
                        }
                        if(actionInfoEnabled && checkpoint.empty() && !actionInfoNotificationStage){
                            const auto observed=live.ObserveActionInfoPanel();
                            if(observed.notificationIndex<0 || (observed.blockingType!=ENDTURN_BLOCKING_PRODUCTION && observed.blockingType!=ENDTURN_BLOCKING_RESEARCH))
                                throw std::runtime_error("Founded city lacks its genuine production/research blocker notification");
                            actionInfoNotificationKind=observed.blockingType==ENDTURN_BLOCKING_PRODUCTION?UiPopupKind::Production:UiPopupKind::Research;
                            actionInfoBeforeState=SdkStateSnapshot::Capture(host);
                            Write(directory+L"\\action-info-notification-before.txt",actionInfoBeforeState);
                            next=actionInfoButton("notification");actionInfoNotificationStage=1;return;
                        }
                        if(actionInfoEnabled && actionInfoNotificationStage==2){
                            if(SdkStateSnapshot::Capture(host)!=actionInfoBeforeState)
                                throw std::runtime_error("Original notification popup Escape changed gameplay");
                            Write(directory+L"\\action-info-notification-after.txt",SdkStateSnapshot::Capture(host));
                            std::printf("INTERACTIVE_ACTION_INFO_SMOKE_VERIFIED=notification|%llu|%d\n",
                                static_cast<unsigned long long>(window.SceneGeneration()),world.turn);
                            actionInfoNotificationStage=3;
                        }
                        decisionCity=-1;
                        for(const auto& city:world.visibleCities)if(city.owner==world.activePlayer){
                            if(live.CanChooseProduction(city.id)){
                                if(decisionCity<0)decisionCity=city.id;
                            }else{
                                // Check the ordinary Host production entry point rejects a
                                // restored puppet before posting input to an eligible city.
                                if(live.OpenProduction(city.id) || live.HasUi())
                                    throw std::runtime_error("Puppet city unexpectedly opened manual production");
                                std::printf("INTERACTIVE_PUPPET_PRODUCTION_GUARD=%d|HOST_CALL_REJECTED\n",city.id);
                            }
                        }
                        if(decisionCity<0 || !live.OwnsCity(decisionCity))throw std::runtime_error("Integrated decision smoke lacks an owned non-puppet production city");
                        citySpecialistBuilding=live.PrepareCityManagementSmoke(decisionCity);
                        live.PrepareCityPurchaseSmoke(decisionCity);
                        std::printf("INTERACTIVE_DECISION_CITY_READY=%d\n",decisionCity);
                        next=WorldViewHitKey::OwnedCity(decisionCity);smokeStage=13;
                    }
                }else if(smokeStage==13){
                    if(selectedCity!=decisionCity)throw std::runtime_error("Owned city native hit did not select its exact SDK identity");
                    if(!uiActive || live.UiKind()!=UiPopupKind::CityView || host.cityScreenViewingMode || !host.cityScreenUp)
                        throw std::runtime_error("Owned city native hit did not enter the original editable CityView");
                    for(const auto& target:live.UiTargets())if(target.id=="WorkerHeader")next=target.key;
                    if(!next)throw std::runtime_error("Owned CityView has no original citizen-management header");
                    std::printf("INTERACTIVE_OWNED_CITY_HEADER_TARGET=%d|%llu|%llu\n",decisionCity,
                        static_cast<unsigned long long>(next),static_cast<unsigned long long>(window.SceneGeneration()));
                    smokeStage=70;
                }else if(smokeStage==70){
                    cityFocusTarget=live.CityFocus(decisionCity)==CITY_AI_FOCUS_TYPE_PRODUCTION?CITY_AI_FOCUS_TYPE_FOOD:CITY_AI_FOCUS_TYPE_PRODUCTION;
                    const char* control=cityFocusTarget==CITY_AI_FOCUS_TYPE_PRODUCTION?"ProductionFocusButton":"FoodFocusButton";
                    for(const auto& target:live.UiTargets())if(target.id==control)next=target.key;
                    if(!next)throw std::runtime_error("Original citizen-management header did not expose its focus controls");
                    std::printf("INTERACTIVE_OWNED_CITY_FOCUS_TARGET=%d|%d|%llu|%llu\n",decisionCity,cityFocusTarget,
                        static_cast<unsigned long long>(next),static_cast<unsigned long long>(window.SceneGeneration()));
                    smokeStage=71;
                }else if(smokeStage==71){
                    if(live.CityFocus(decisionCity)!=cityFocusTarget)throw std::runtime_error("Original focus callback did not update SDK citizens");
                    cityAvoidTarget=!live.CityAvoidGrowth(decisionCity);
                    for(const auto& target:live.UiTargets())if(target.id=="AvoidGrowthButton")next=target.key;
                    if(!next)throw std::runtime_error("Original CityView has no growth option control");
                    std::printf("INTERACTIVE_OWNED_CITY_GROWTH_TARGET=%d|%u|%llu|%llu\n",decisionCity,cityAvoidTarget?1u:0u,
                        static_cast<unsigned long long>(next),static_cast<unsigned long long>(window.SceneGeneration()));
                    smokeStage=72;
                }else if(smokeStage==72){
                    if(live.CityAvoidGrowth(decisionCity)!=cityAvoidTarget || live.CityFocus(decisionCity)!=cityFocusTarget)
                        throw std::runtime_error("Original growth callback did not preserve the selected SDK focus and growth state");
                    std::printf("INTERACTIVE_OWNED_CITY_SETTINGS_VERIFIED=%d|%d|%u\n",decisionCity,cityFocusTarget,cityAvoidTarget?1u:0u);
                    cityNoAutoTarget=!live.CityNoAutoSpecialists(decisionCity);
                    for(const auto& target:live.UiTargets())if(target.id=="NoAutoSpecialistCheckbox")next=target.key;
                    if(!next)throw std::runtime_error("Original CityView has no specialist automation checkbox");
                    std::printf("INTERACTIVE_CITY_MANAGEMENT_TARGET=automation|%d|%d|%llu|%llu\n",decisionCity,cityNoAutoTarget?1:0,
                        static_cast<unsigned long long>(next),static_cast<unsigned long long>(window.SceneGeneration()));smokeStage=73;
                }else if(smokeStage==73){
                    if(live.CityNoAutoSpecialists(decisionCity)!=cityNoAutoTarget)throw std::runtime_error("Original specialist automation checkbox did not reach the SDK");
                    citySpecialistsBefore=live.CitySpecialists(decisionCity,citySpecialistBuilding);
                    citySpecialistDelta=citySpecialistsBefore>0?-1:1;
                    const char* prefix=citySpecialistDelta>0?"BuildingEmptySpecialistSlot":"BuildingFilledSpecialistSlot";
                    for(const auto& target:live.UiTargets())if(!next && target.id.rfind(prefix,0)==0 && target.hasVoidPayload && target.void1==citySpecialistBuilding)next=target.key;
                    if(!next)throw std::runtime_error("Original specialist building has no available slot callback");
                    std::printf("INTERACTIVE_CITY_MANAGEMENT_TARGET=specialist-first|%d|%d|%llu|%llu\n",decisionCity,citySpecialistDelta,
                        static_cast<unsigned long long>(next),static_cast<unsigned long long>(window.SceneGeneration()));smokeStage=74;
                }else if(smokeStage==74){
                    if(!live.CityNoAutoSpecialists(decisionCity) || live.CitySpecialists(decisionCity,citySpecialistBuilding)!=citySpecialistsBefore+citySpecialistDelta)
                        throw std::runtime_error("Original specialist callback did not apply automation and slot assignment");
                    const char* prefix=citySpecialistDelta>0?"BuildingFilledSpecialistSlot":"BuildingEmptySpecialistSlot";
                    for(const auto& target:live.UiTargets())if(!next && target.id.rfind(prefix,0)==0 && target.hasVoidPayload && target.void1==citySpecialistBuilding)next=target.key;
                    if(!next)throw std::runtime_error("Original specialist reverse callback is missing");
                    std::printf("INTERACTIVE_CITY_MANAGEMENT_TARGET=specialist-return|%d|%d|%llu|%llu\n",decisionCity,-citySpecialistDelta,
                        static_cast<unsigned long long>(next),static_cast<unsigned long long>(window.SceneGeneration()));smokeStage=75;
                }else if(smokeStage==75){
                    if(live.CitySpecialists(decisionCity,citySpecialistBuilding)!=citySpecialistsBefore)
                        throw std::runtime_error("Original specialist reverse callback did not restore its count");
                    for(const auto& target:live.UiTargets())if(!next && target.id=="PlotButtonImage" && target.hasVoid1 && target.void1>0 &&
                        !live.CityWorkedPlot(decisionCity,target.void1) && live.CityCanWorkPlot(decisionCity,target.void1)){
                        cityWorkPlot=target.void1;next=target.key;
                    }
                    if(!next)throw std::runtime_error("Original CityView has no legal unworked plot target");
                    std::printf("INTERACTIVE_CITY_MANAGEMENT_TARGET=force-plot|%d|%d|%llu|%llu\n",decisionCity,cityWorkPlot,
                        static_cast<unsigned long long>(next),static_cast<unsigned long long>(window.SceneGeneration()));smokeStage=76;
                }else if(smokeStage==76){
                    if(!live.CityForcedPlot(decisionCity,cityWorkPlot))throw std::runtime_error("Original plot callback did not force the SDK worked plot");
                    for(const auto& target:live.UiTargets())if(target.id=="ResetButton")next=target.key;
                    if(!next)throw std::runtime_error("Original citizen reset button is missing");
                    std::printf("INTERACTIVE_CITY_MANAGEMENT_TARGET=reset-plots|%d|0|%llu|%llu\n",decisionCity,
                        static_cast<unsigned long long>(next),static_cast<unsigned long long>(window.SceneGeneration()));smokeStage=77;
                }else if(smokeStage==77){
                    if(live.CityForcedPlot(decisionCity,cityWorkPlot))throw std::runtime_error("Original citizen reset did not clear forced plots");
                    for(const auto& target:live.UiTargets())if(target.id=="BuyPlotButton")next=target.key;
                    if(!next)throw std::runtime_error("Original CityView buy plot button is missing");
                    std::printf("INTERACTIVE_CITY_MANAGEMENT_TARGET=buy-mode|%d|0|%llu|%llu\n",decisionCity,
                        static_cast<unsigned long long>(next),static_cast<unsigned long long>(window.SceneGeneration()));smokeStage=78;
                }else if(smokeStage==78){
                    if(host.interfaceMode!=INTERFACEMODE_PURCHASE_PLOT)throw std::runtime_error("Original buy button did not enter purchase plot mode");
                    for(const auto& target:live.UiTargets())if(!next && target.id=="BuyPlotAnchoredButton" && target.hasVoid1 && target.void1>0){
                        cityBuyPlot=target.void1;next=target.key;
                    }
                    if(!next || live.CityPlotOwner(decisionCity,cityBuyPlot)!=NO_PLAYER)throw std::runtime_error("Original purchase mode has no legal unowned tile target");
                    cityBuyCost=live.CityPlotCost(decisionCity,cityBuyPlot);cityGoldBefore=live.ActiveGold();
                    if(cityBuyCost<=0 || cityBuyCost>cityGoldBefore)throw std::runtime_error("Original plot price is not affordable");
                    std::printf("INTERACTIVE_CITY_MANAGEMENT_TARGET=buy-plot|%d|%d|%llu|%llu\n",decisionCity,cityBuyPlot,
                        static_cast<unsigned long long>(next),static_cast<unsigned long long>(window.SceneGeneration()));smokeStage=79;
                }else if(smokeStage==79){
                    if(live.CityPlotOwner(decisionCity,cityBuyPlot)!=world.activePlayer || live.ActiveGold()!=cityGoldBefore-cityBuyCost)
                        throw std::runtime_error("Original plot purchase did not transfer the tile and charge its exact SDK price");
                    std::printf("INTERACTIVE_CITY_MANAGEMENT_VERIFIED=%d|%d|%d|%d|%d|%d|%d\n",decisionCity,citySpecialistBuilding,
                        citySpecialistsBefore,cityWorkPlot,cityBuyPlot,cityBuyCost,live.ActiveGold());
                    for(const auto& target:live.UiTargets())if(target.id=="ProductionButton"){
                        if(next)throw std::runtime_error("Owned CityView has duplicate production controls");next=target.key;
                    }
                    if(!next)throw std::runtime_error("Owned CityView has no original production control");
                    std::printf("INTERACTIVE_OWNED_CITY_PRODUCTION_TARGET=%d|%llu|%llu\n",decisionCity,
                        static_cast<unsigned long long>(next),static_cast<unsigned long long>(window.SceneGeneration()));
                    smokeStage=14;
                }else if(smokeStage==14){
                    if(!uiActive || live.UiKind()!=UiPopupKind::Production)throw std::runtime_error("World production button did not open the original production popup");
                    for(const auto& target:live.UiTargets())if(target.hasVoidPayload && target.void1==6 && target.void2>=0 &&
                       (decisionUnit<0 || target.void2<decisionUnit) && live.CanTrain(decisionCity,target.void2)){
                        decisionUnit=target.void2;next=target.key;
                    }
                    if(!next)throw std::runtime_error("Original integrated production popup has no legal train button");
                    std::printf("INTERACTIVE_DECISION_PRODUCTION_TARGET=%d|%d|%llu\n",decisionCity,decisionUnit,static_cast<unsigned long long>(next));smokeStage=15;
                }else if(smokeStage==15){
                    if(!uiActive || live.UiKind()!=UiPopupKind::CityView || live.ProductionUnit(decisionCity)!=decisionUnit ||
                       host.cityScreenViewingMode || !host.cityScreenUp || host.selectedCityId!=decisionCity)
                        throw std::runtime_error("Original production callback did not return to its retained owned CityView");
                    smokeStage=80;
                }else if(smokeStage==80){
                    if(!uiActive || live.UiKind()!=UiPopupKind::CityView || host.selectedCityId!=decisionCity)
                        throw std::runtime_error("Purchase opener lost its original owned CityView");
                    for(const auto& target:live.UiTargets())if(target.id=="PurchaseButton"){
                        if(next)throw std::runtime_error("Owned CityView has duplicate purchase controls");next=target.key;
                    }
                    if(!next)throw std::runtime_error("Owned CityView has no original purchase control");
                    std::printf("INTERACTIVE_CITY_PURCHASE_OPEN=%d|%d|%llu|%llu\n",decisionCity,purchaseSelections[purchaseStep],
                        static_cast<unsigned long long>(next),static_cast<unsigned long long>(window.SceneGeneration()));smokeStage=81;
                }else if(smokeStage==81){
                    if(!uiActive || live.UiKind()!=UiPopupKind::Production)throw std::runtime_error("Original purchase button did not open ProductionPopup");
                    purchaseItem=-1;const int selection=purchaseSelections[purchaseStep];
                    for(const auto& target:live.UiTargets())if(target.hasVoidPayload && target.void1==selection && target.void2>=0 &&
                        (purchaseItem<0 || target.void2<purchaseItem)){
                        const auto observation=live.ObservePurchase(decisionCity,selection,target.void2);
                        if(observation.legal){next=target.key;purchaseItem=target.void2;purchaseBefore=observation;}
                    }
                    if(!next || purchaseBefore.price<=0)throw std::runtime_error("Original purchase list has no legal affordable scenario item");
                    SdkStateSnapshot::Write(directory+L"\\play-purchase-"+std::to_wstring(selection)+L"-before-state.txt",SdkStateSnapshot::Capture(host));
                    std::printf("INTERACTIVE_CITY_PURCHASE_TARGET=%d|%d|%d|%d|%d|%d|%d|%llu|%llu\n",decisionCity,selection,purchaseItem,
                        purchaseBefore.price,purchaseBefore.gold,purchaseBefore.faith,purchaseBefore.count,
                        static_cast<unsigned long long>(next),static_cast<unsigned long long>(window.SceneGeneration()));smokeStage=82;
                }else if(smokeStage==82){
                    if(!uiActive || live.UiKind()!=UiPopupKind::CityView || host.cityScreenViewingMode || !host.cityScreenUp ||
                        host.selectedCityId!=decisionCity || live.ProductionUnit(decisionCity)!=decisionUnit)
                        throw std::runtime_error("Original purchase did not retain production and return to its owned CityView");
                    const int selection=purchaseSelections[purchaseStep];const auto after=live.ObservePurchase(decisionCity,selection,purchaseItem);
                    if(after.count!=purchaseBefore.count+1 || after.gold!=purchaseBefore.gold-(selection<3?purchaseBefore.price:0) ||
                        after.faith!=purchaseBefore.faith-(selection>=3?purchaseBefore.price:0))
                        throw std::runtime_error("Original purchase did not charge its exact currency and create exactly one selected item");
                    SdkStateSnapshot::Write(directory+L"\\play-purchase-"+std::to_wstring(selection)+L"-after-state.txt",SdkStateSnapshot::Capture(host));
                    std::printf("INTERACTIVE_CITY_PURCHASE_VERIFIED=%d|%d|%d|%d|%d|%d|%d|%d|%d|%d\n",decisionCity,selection,purchaseItem,
                        purchaseBefore.price,purchaseBefore.gold,after.gold,purchaseBefore.faith,after.faith,purchaseBefore.count,after.count);
                    ++purchaseStep;
                    if(purchaseStep<static_cast<int>(sizeof(purchaseSelections)/sizeof(purchaseSelections[0])))smokeStage=80;
                    else smokeStage=83;
                }else if(smokeStage==83){
                    next=live.CityViewExitKey();smokeStage=22;
                    std::printf("INTERACTIVE_OWNED_CITY_RETURN_TARGET=%d|%llu|%llu\n",decisionCity,
                        static_cast<unsigned long long>(next),static_cast<unsigned long long>(window.SceneGeneration()));
                }else if(smokeStage==22){
                    if(uiActive || host.cityScreenUp || host.cityScreenViewingMode || host.selectedCityId!=-1)
                        throw std::runtime_error("Owned CityView exit did not restore normal world input");
                    std::printf("INTERACTIVE_OWNED_CITY_SEQUENCE_VERIFIED=%d|%d\n",decisionCity,decisionUnit);
                    if(notificationEnabled && checkpoint.empty() && notificationSmokeStage==4 && notificationSmokeKind==UiPopupKind::Production){
                        {std::lock_guard<std::mutex> guard(host.dataMutex);
                         if(host.notifications.find({world.activePlayer,notificationSmokeId})!=host.notifications.end())
                            throw std::runtime_error("Completed original production choice left its SDK notification active");}
                        for(const auto& target:notificationTargets)if(target.hasVoid1 && target.void1==notificationSmokeId)
                            throw std::runtime_error("Removed SDK notification retained a live original callback");
                        std::printf("INTERACTIVE_NOTIFICATION_REMOVED_VERIFIED=%d|%llu|%d\n",notificationSmokeId,
                            static_cast<unsigned long long>(window.SceneGeneration()),world.turn);notificationSmokeStage=5;
                    }
                    if(actionInfoEnabled && checkpoint.empty()){
                        const auto observed=live.ObserveActionInfoPanel();
                        if(observed.blockingType!=ENDTURN_BLOCKING_RESEARCH || observed.notificationIndex<0)
                            throw std::runtime_error("Original research blocker is missing after city production selection");
                        next=actionInfoButton("research");
                    }else next=WorldViewHitKey::Action(WorldViewAction::Research);
                    smokeStage=16;
                }else if(smokeStage==16){
                    if(!uiActive || live.UiKind()!=UiPopupKind::Research)throw std::runtime_error("World research button did not open the original TechPopup");
                    if(researchTree){
                        for(const auto& target:live.UiTargets())if(target.id=="OpenTTButton"){
                            if(next)throw std::runtime_error("Original TechPopup has duplicate research-tree handoff buttons");
                            next=target.key;
                        }
                        if(!next)throw std::runtime_error("Original TechPopup has no visible research-tree handoff button");
                        std::printf("INTERACTIVE_DECISION_TREE_HANDOFF_TARGET=%llu\n",static_cast<unsigned long long>(next));smokeStage=18;
                    }else{
                        for(const auto& target:live.UiTargets())if(target.id=="TechButton" && target.hasVoidPayload && target.void2==0 &&
                       (decisionTech<0 || target.void1<decisionTech) && live.CanResearch(target.void1)){
                            decisionTech=target.void1;next=target.key;
                        }
                        if(!next)throw std::runtime_error("Original integrated research popup has no legal technology button");
                        std::printf("INTERACTIVE_DECISION_RESEARCH_TARGET=%d|%llu\n",decisionTech,static_cast<unsigned long long>(next));smokeStage=17;
                    }
                }else if(smokeStage==18){
                    if(!uiActive || live.UiKind()!=UiPopupKind::ResearchTree)throw std::runtime_error("Original handoff did not open TechTree in the world window");
                    for(const auto& target:live.UiTargets())if(target.id=="TechButton" && target.hasVoidPayload && target.void2==0 &&
                       (decisionTech<0 || target.void1<decisionTech) && live.CanResearch(target.void1)){
                        decisionTech=target.void1;next=target.key;
                    }
                    if(!next)throw std::runtime_error("Original integrated research popup has no legal technology button");
                    std::printf("INTERACTIVE_DECISION_RESEARCH_TARGET=%d|%llu\n",decisionTech,static_cast<unsigned long long>(next));smokeStage=19;
                }else if(smokeStage==19){
                    if(!uiActive || live.UiKind()!=UiPopupKind::ResearchTree || live.CurrentResearch()!=decisionTech)
                        throw std::runtime_error("Original TechTree did not apply research while retaining its open context");
                    std::puts("INTERACTIVE_DECISION_TREE_SELECTION_REMAINS_OPEN=true");
                    if(!PostMessageW(window.NativeHandle(),WM_KEYDOWN,VK_ESCAPE,1))throw std::runtime_error("Cannot close the original research tree with native Escape input");
                    smokeStage=17;
                }else if(smokeStage==17){
                    if(uiActive || live.CurrentResearch()!=decisionTech)throw std::runtime_error("Original research UI did not apply its exact SDK technology and close");
                    if(techAwardSmoke)live.PrepareResearchCompletionSmoke(decisionTech);
                    decisionBefore=live.DecisionState(decisionCity,decisionUnit,decisionTech);
                    EmitDecision("INTERACTIVE_DECISION_BEFORE_TURN",decisionBefore);
                    if(naturalWorkerResearch){
                        if(live.HasTechnology(decisionTech))throw std::runtime_error("Original initial research choice is already owned");
                        const auto production=live.ObserveProduction(decisionCity);
                        if(decisionUnit!=context.GetInfoTypeForString("UNIT_SETTLER",true) || production.length!=1 || production.unit!=decisionUnit ||
                           production.production<0 || production.needed<=production.production)
                            throw std::runtime_error("Natural production baseline requires the original unfinished settler order");
                        std::printf("INTERACTIVE_WORKER_PRODUCTION_BASELINE=%d|%d|%d|%d|%d|%d|%d|%llu\n",world.turn,world.activePlayer,
                            decisionCity,decisionUnit,production.length,production.production,production.needed,static_cast<unsigned long long>(window.SceneGeneration()));
                        std::printf("INTERACTIVE_WORKER_RESEARCH_SELECTED=%d|%d|%d|%llu|%d|0|%d|%d\n",world.turn,world.activePlayer,
                            decisionTech,static_cast<unsigned long long>(window.SceneGeneration()),live.CurrentResearch(),decisionBefore[9],decisionBefore[10]);
                    }
                    SdkStateSnapshot::Write(directory+L"\\play-decisions-selected-state.txt",SdkStateSnapshot::Capture(host));smokeStage=workerSmoke?30:combatSmoke?40:captureSmoke?50:warSmoke?60:3;
                }else if(smokeStage==50){
                    captureFixture=live.CreateCityCaptureSmokeFixture();cameraX=captureFixture.x;cameraY=captureFixture.y;
                    std::printf("INTERACTIVE_CITY_CAPTURE_FIXTURE=%d|%d|%d|%d|%d|%d\n",captureFixture.attackerOwner,
                        captureFixture.attacker,captureFixture.defenderOwner,captureFixture.oldCity,captureFixture.x,captureFixture.y);
                    std::printf("INTERACTIVE_CITY_CAPTURE_CAPITAL=%d|%d|%d|%d|%d|%d\n",captureFixture.defenderOwner,
                        captureFixture.capitalCity,captureFixture.defenderCitiesBefore,captureFixture.declaredWar,captureFixture.capitalCreated,captureFixture.metForFixture);
                    redraw=true;smokeStage=51;
                }else if(smokeStage==51){
                    next=WorldViewHitKey::OwnedUnit(captureFixture.attacker);smokeStage=52;
                }else if(smokeStage==52){
                    const auto attacker=std::find_if(world.ownedUnits.begin(),world.ownedUnits.end(),[&](const WorldViewState::Unit& u){
                        return u.id==captureFixture.attacker && u.owner==captureFixture.attackerOwner && u.selected;});
                    const auto city=std::find_if(world.visibleCities.begin(),world.visibleCities.end(),[&](const WorldViewState::City& c){
                        return c.owner==captureFixture.defenderOwner && c.id==captureFixture.oldCity && c.x==captureFixture.x && c.y==captureFixture.y;});
                    if(attacker==world.ownedUnits.end() || city==world.visibleCities.end())throw std::runtime_error("City capture lacks its visible selected attacker/hostile city");
                    const auto plot=std::find_if(world.plots.begin(),world.plots.end(),[&](const WorldViewState::Plot& p){return p.x==captureFixture.x && p.y==captureFixture.y && p.visible;});
                    if(plot==world.plots.end())throw std::runtime_error("City capture target plot is not visible");
                    next=WorldViewHitKey::Plot(plot->index);nextRight=true;
                    SdkStateSnapshot::Write(directory+L"\\play-city-capture-before-state.txt",SdkStateSnapshot::Capture(host));
                    std::printf("INTERACTIVE_CITY_CAPTURE_TARGET=%d|%llu|%llu\n",plot->index,static_cast<unsigned long long>(next),static_cast<unsigned long long>(window.SceneGeneration()));
                    smokeStage=53;
                }else if(smokeStage==53){
                    if(!uiActive || live.UiKind()!=UiPopupKind::CityCapture || !live.HasMandatoryCityDecision())
                        throw std::runtime_error("Legal posted city attack did not open the SDK captured-city decision popup");
                    const auto city=live.ObserveCapturedCityAtPlot(captureFixture.x,captureFixture.y);
                    if(city.owner!=captureFixture.attackerOwner || city.cityID<0 || city.originalOwner!=captureFixture.defenderOwner)
                        throw std::runtime_error("SDK capture did not create the expected newly owned city");
                    capturedCity=city.cityID;next=live.CapturedViewKey();
                    std::printf("INTERACTIVE_CITY_VIEW_CHOICE=%d|%llu|%llu\n",capturedCity,static_cast<unsigned long long>(next),static_cast<unsigned long long>(window.SceneGeneration()));
                    smokeStage=55;
                }else if(smokeStage==55){
                    if(!uiActive || live.UiKind()!=UiPopupKind::CityView || !live.HasMandatoryCityDecision())
                        throw std::runtime_error("Original View City did not preserve the unresolved capture decision");
                    next=live.CityViewExitKey();
                    SdkStateSnapshot::Write(directory+L"\\play-city-view-shown-state.txt",SdkStateSnapshot::Capture(host));
                    std::printf("INTERACTIVE_CITY_VIEW_EXIT_CHOICE=%d|%llu|%llu\n",capturedCity,static_cast<unsigned long long>(next),static_cast<unsigned long long>(window.SceneGeneration()));
                    smokeStage=56;
                }else if(smokeStage==56){
                    if(!uiActive || live.UiKind()!=UiPopupKind::CityCapture || !live.HasMandatoryCityDecision())
                        throw std::runtime_error("Original CityView return lost its captured-city popup");
                    SdkStateSnapshot::Write(directory+L"\\play-city-view-returned-state.txt",SdkStateSnapshot::Capture(host));
                    next=live.CapturedPuppetKey();
                    std::printf("INTERACTIVE_CITY_CAPTURE_CHOICE=%d|%llu|%llu\n",capturedCity,static_cast<unsigned long long>(next),static_cast<unsigned long long>(window.SceneGeneration()));
                    smokeStage=54;
                }else if(smokeStage==54){
                    const auto city=live.ObserveCapturedCityAtPlot(captureFixture.x,captureFixture.y);
                    if(uiActive || live.HasMandatoryCityDecision() || city.cityID!=capturedCity || city.owner!=captureFixture.attackerOwner ||
                       !city.isPuppet || city.isRazing || city.originalOwner!=captureFixture.defenderOwner)
                        throw std::runtime_error("Original puppet choice did not reach the exact SDK captured city");
                    SdkStateSnapshot::Write(directory+L"\\play-city-capture-after-state.txt",SdkStateSnapshot::Capture(host));
                    std::printf("INTERACTIVE_CITY_CAPTURE_VERIFIED=%d|%d|%d|%d|%d\n",city.owner,city.cityID,city.isPuppet,city.isRazing,city.originalOwner);
                    smokeStage=3;
                }else if(smokeStage==60){
                    warFixture=live.CreateDeclareWarSmokeFixture(warRanged);cameraX=warFixture.x;cameraY=warFixture.y;
                    {std::lock_guard<std::mutex> lock(host.dataMutex);warCombatBefore=host.combatPresentations.size();}
                    redraw=true;smokeStage=61;
                    std::printf("INTERACTIVE_DECLARE_WAR_FIXTURE=%d|%d|%d|%d|%d|%d|%d|%d\n",warFixture.ranged,warFixture.owner,
                        warFixture.unit,warFixture.rivalPlayer,warFixture.rivalTeam,warFixture.targetUnit,warFixture.x,warFixture.y);
                }else if(smokeStage==61){
                    next=WorldViewHitKey::OwnedUnit(warFixture.unit);smokeStage=62;
                }else if(smokeStage==62){
                    const auto attacker=std::find_if(world.ownedUnits.begin(),world.ownedUnits.end(),[&](const WorldViewState::Unit& u){
                        return u.id==warFixture.unit && u.owner==warFixture.owner && u.selected;});
                    const auto defender=std::find_if(world.visibleForeignUnits.begin(),world.visibleForeignUnits.end(),[&](const WorldViewState::Unit& u){
                        return u.id==warFixture.targetUnit && u.owner==warFixture.rivalPlayer && u.x==warFixture.x && u.y==warFixture.y && !u.hostile;});
                    if(uiActive || attacker==world.ownedUnits.end() || defender==world.visibleForeignUnits.end() || live.DeclareWarFixtureAtWar(warFixture))
                        throw std::runtime_error("War input must select its real unit and visible peaceful target");
                    next=WorldViewHitKey::Plot(defender->plotIndex);nextRight=true;
                    std::printf("INTERACTIVE_DECLARE_WAR_WORLD_TARGET=%u|%d|%d|%llu|%llu\n",warAttempt,warFixture.unit,defender->plotIndex,
                        static_cast<unsigned long long>(next),static_cast<unsigned long long>(window.SceneGeneration()));smokeStage=63;
                }else if(smokeStage==63){
                    if(!uiActive || live.UiKind()!=UiPopupKind::DeclareWar || live.DeclareWarFixtureAtWar(warFixture))
                        throw std::runtime_error("Peaceful world action did not open the original war confirmation");
                    warBeforeState=SdkStateSnapshot::Capture(host);
                    SdkStateSnapshot::Write(directory+L"\\play-declare-war-before-"+std::to_wstring(warAttempt)+L"-state.txt",warBeforeState);
                    const int key=warAttempt==1?VK_ESCAPE:0;
                    if(!key){
                        for(const auto& target:live.UiTargets())if(target.id==(warAttempt==0?"Button2":"Button1")){
                            if(next)throw std::runtime_error("War confirmation has duplicate original decision buttons");next=target.key;
                        }
                        if(!next)throw std::runtime_error("War confirmation lost its original Yes/No callback");
                    }
                    std::printf("INTERACTIVE_DECLARE_WAR_CHOICE=%u|%d|%llu|%llu\n",warAttempt,key,
                        static_cast<unsigned long long>(next),static_cast<unsigned long long>(window.SceneGeneration()));
                    if(key){
                        if(!PostMessageW(window.NativeHandle(),WM_KEYDOWN,VK_ESCAPE,1))throw std::runtime_error("Cannot post original war Escape input");
                        std::printf("INTERACTIVE_DECLARE_WAR_POSTED_ESCAPE=27|%llu\n",static_cast<unsigned long long>(window.SceneGeneration()));
                    }
                    smokeStage=64;
                }else if(smokeStage==64){
                    if(uiActive)throw std::runtime_error("Original war confirmation did not close after its decision");
                    const auto after=SdkStateSnapshot::Capture(host);
                    SdkStateSnapshot::Write(directory+L"\\play-declare-war-after-"+std::to_wstring(warAttempt)+L"-state.txt",after);
                    if(warAttempt<2){
                        if(after!=warBeforeState || live.DeclareWarFixtureAtWar(warFixture))
                            throw std::runtime_error("Original No/Escape war cancellation changed gameplay or declared war");
                        {std::lock_guard<std::mutex> lock(host.dataMutex);if(host.combatPresentations.size()!=warCombatBefore)
                            throw std::runtime_error("Cancelled war input performed combat");}
                        std::printf("INTERACTIVE_DECLARE_WAR_REJECTED=%u|STATE_UNCHANGED|AT_PEACE\n",warAttempt);
                        ++warAttempt;smokeStage=62;
                    }else{
                        if(!live.DeclareWarFixtureAtWar(warFixture) || after==warBeforeState)
                            throw std::runtime_error("Confirmed original war callback did not reach SDK war state");
                        CombatPresentation combat;
                        {std::lock_guard<std::mutex> lock(host.dataMutex);
                         if(host.combatPresentations.size()!=warCombatBefore+1)throw std::runtime_error("Confirmed war did not continue exactly one original attack");
                         combat=host.combatPresentations.back();}
                        const auto& attacker=combat.participants[BATTLE_UNIT_ATTACKER];const auto& defender=combat.participants[BATTLE_UNIT_DEFENDER];
                        if(combat.cityEvent || combat.ranged!=warRanged || !attacker.hasUnit || !defender.hasUnit ||
                           attacker.unitOwner!=warFixture.owner || attacker.unitId!=warFixture.unit || defender.unitOwner!=warFixture.rivalPlayer ||
                           defender.unitId!=warFixture.targetUnit || combat.plotX!=warFixture.x || combat.plotY!=warFixture.y ||
                           !live.CombatSmokeUnitAlive(warFixture.owner,warFixture.unit))
                            throw std::runtime_error("Confirmed war attack resolved a different SDK unit, target or mode");
                        std::printf("INTERACTIVE_DECLARE_WAR_VERIFIED=%d|%d|%d|%d|%d|%d|%d|%d\n",warFixture.ranged,warFixture.owner,
                            warFixture.unit,warFixture.rivalPlayer,warFixture.rivalTeam,warFixture.targetUnit,warFixture.x,warFixture.y);smokeStage=3;
                    }
                }else if(smokeStage==40){
                    combatFixture=live.CreateCombatSmokeFixture(combatKind);cameraX=combatFixture.x;cameraY=combatFixture.y;
                    redraw=true;smokeStage=41;
                    std::printf("INTERACTIVE_COMBAT_FIXTURE=%d|%d|%d|%d|%d|%d|%d\n",combatKind,combatFixture.attackerOwner,
                        combatFixture.attacker,combatFixture.defenderOwner,combatFixture.defender,combatFixture.x,combatFixture.y);
                }else if(smokeStage==41){
                    next=WorldViewHitKey::OwnedUnit(combatFixture.attacker);smokeStage=42;
                }else if(smokeStage==42){
                    const auto attacker=std::find_if(world.ownedUnits.begin(),world.ownedUnits.end(),[&](const WorldViewState::Unit& u){
                        return u.id==combatFixture.attacker && u.owner==combatFixture.attackerOwner && u.selected;});
                    const auto defender=std::find_if(world.visibleForeignUnits.begin(),world.visibleForeignUnits.end(),[&](const WorldViewState::Unit& u){
                        return u.id==combatFixture.defender && u.owner==combatFixture.defenderOwner && u.x==combatFixture.x && u.y==combatFixture.y && u.hostile;});
                    if(attacker==world.ownedUnits.end() || defender==world.visibleForeignUnits.end())
                        throw std::runtime_error("Combat native input lacks its selected attacker or visible hostile defender");
                    next=WorldViewHitKey::Plot(defender->plotIndex);nextRight=true;
                    SdkStateSnapshot::Write(directory+L"\\play-combat-before-"+std::to_wstring(combatKind)+L"-state.txt",SdkStateSnapshot::Capture(host));
                    {std::lock_guard<std::mutex> lock(host.dataMutex);combatBefore=host.combatPresentations.size();}
                    std::printf("INTERACTIVE_COMBAT_TARGET=%d|%d|%d|%llu|%llu\n",combatKind,combatFixture.attacker,defender->plotIndex,
                        static_cast<unsigned long long>(next),static_cast<unsigned long long>(window.SceneGeneration()));smokeStage=43;
                }else if(smokeStage==43){
                    std::size_t count=0;CombatPresentation combat;
                    {std::lock_guard<std::mutex> lock(host.dataMutex);count=host.combatPresentations.size();
                        if(count!=combatBefore+1)throw std::runtime_error("Posted attack did not produce exactly one original SDK combat callback");
                        combat=host.combatPresentations.back();}
                    const auto& attacker=combat.participants[BATTLE_UNIT_ATTACKER];const auto& defender=combat.participants[BATTLE_UNIT_DEFENDER];
                    const bool defenderAlive=live.CombatSmokeUnitAlive(combatFixture.defenderOwner,combatFixture.defender);
                    if(combat.cityEvent || combat.ranged!=(combatKind==1) || !attacker.hasUnit || !defender.hasUnit ||
                       attacker.unitOwner!=combatFixture.attackerOwner || attacker.unitId!=combatFixture.attacker ||
                       defender.unitOwner!=combatFixture.defenderOwner || defender.unitId!=combatFixture.defender ||
                       combat.plotX!=combatFixture.x || combat.plotY!=combatFixture.y ||
                       !live.CombatSmokeUnitAlive(combatFixture.attackerOwner,combatFixture.attacker) || defenderAlive!=(combatKind==0))
                        throw std::runtime_error("Posted combat resolved a different SDK target or casualty outcome");
                    SdkStateSnapshot::Write(directory+L"\\play-combat-after-"+std::to_wstring(combatKind)+L"-state.txt",SdkStateSnapshot::Capture(host));
                    std::printf("INTERACTIVE_COMBAT_VERIFIED=%d|%d|%d|%d|%d|%zu|%d\n",combatKind,combatFixture.attackerOwner,
                        combatFixture.attacker,combatFixture.defenderOwner,combatFixture.defender,count-combatBefore,defenderAlive?1:0);
                    if(++combatKind<2)smokeStage=40;else smokeStage=3;
                }else if(smokeStage==30){
                    workerID=live.CreateWorkerBuildSmokeFixture();workerBuild=context.GetInfoTypeForString("BUILD_FARM",true);
                    workerBefore=live.ObserveBuild(context,workerID,workerBuild);
                    if(workerBefore.progress!=0 || workerBefore.improvement>=0 || workerBefore.expected<0 || workerBefore.time<=0)
                        throw std::runtime_error("Worker fixture must start with no improvement and no construction progress");
                    workerProgress=workerBefore.progress;redraw=true;smokeStage=31;
                    std::printf("INTERACTIVE_WORKER_BUILD_FIXTURE=%d|%d|%d|%d|%d|%d\n",workerID,workerBefore.plot,workerBuild,
                        workerBefore.progress,workerBefore.time,workerBefore.expected);
                }else if(smokeStage==31){
                    next=WorldViewHitKey::OwnedUnit(workerID);smokeStage=32;
                }else if(smokeStage==32){
                    const int mission=context.GetInfoTypeForString("MISSION_BUILD",true);int actionIndex=-1;
                    for(std::size_t index=0;index<unitActions.size();++index)if(unitActions[index].unit==workerID &&
                       unitActions[index].mission==mission && unitActions[index].data1==workerBuild && unitActions[index].data2==-1){
                        actionIndex=static_cast<int>(index);break;
                    }
                    if(actionIndex<0)throw std::runtime_error("Selected worker has no legal published farm action");
                    if(originalMissionButton("build",workerID,mission,workerBuild)){
                        smokeStage=33;
                        std::printf("INTERACTIVE_WORKER_BUILD_TARGET=%d|%d|%d|%d|%llu|%llu\n",workerID,workerBefore.plot,workerBuild,
                            mission,static_cast<unsigned long long>(next),static_cast<unsigned long long>(window.SceneGeneration()));
                    }
                }else if(smokeStage==33){
                    const auto after=live.ObserveBuild(context,workerID,workerBuild);
                    if(after.plot!=workerBefore.plot || (after.progress<=workerProgress && after.improvement!=workerBefore.expected))
                        throw std::runtime_error("Posted worker build did not advance original SDK construction");
                    workerProgress=after.progress;
                    std::printf("INTERACTIVE_WORKER_BUILD_STARTED=%d|%d|%d|%d|%d\n",workerID,after.plot,workerBuild,after.progress,after.improvement);
                    smokeStage=3;
                }else if(smokeStage==3){
                    const auto ready=live.ReadyUnits();if(ready.empty()){
                        if(actionInfoEnabled){
                            const auto observed=live.ObserveActionInfoPanel();
                            if(naturalWorkerResearch && observed.blockingType==ENDTURN_BLOCKING_RESEARCH){
                                if(uiActive || naturalAwardPending || naturalAwardTurn!=world.turn || naturalAwardTech!=workerResearchTech ||
                                   !live.HasTechnology(naturalAwardTech) || live.CurrentResearch()>=0 || observed.notificationIndex<0)
                                    throw std::runtime_error("Research continuation has no settled natural completion or original SDK blocker");
                                next=actionInfoButton("research-continuation");smokeStage=90;return;
                            }
                            if(naturalWorkerResearch && observed.blockingType==ENDTURN_BLOCKING_POLICY){
                                if(uiActive || naturalAwardPending || naturalPolicyPending || naturalPolicyCycles!=0 ||
                                   observed.owner!=world.activePlayer || observed.turn!=world.turn || observed.canEndTurn || observed.notificationIndex<0)
                                    throw std::runtime_error("Natural policy blocker is outside the first paid adoption boundary");
                                const auto notification=std::find_if(observed.notifications.begin(),observed.notifications.end(),[&](const NotificationPresentation& item){
                                    return item.id==observed.notificationIndex && item.player==world.activePlayer && item.type==NOTIFICATION_POLICY;
                                });
                                if(notification==observed.notifications.end())
                                    throw std::runtime_error("Natural policy blocker has no matching paid-policy SDK notification");
                                naturalPolicyBefore=live.ObserveSocialPolicySmoke();
                                naturalPolicyId=context.GetInfoTypeForString("POLICY_BRANCH_TRADITION",true);
                                const int opener=context.GetInfoTypeForString("POLICY_TRADITION",true);
                                const auto branch=std::find_if(naturalPolicyBefore.branches.begin(),naturalPolicyBefore.branches.end(),[&](const SocialPolicySmokeFixture::Branch& value){
                                    return value.id==naturalPolicyId;
                                });
                                const auto policy=std::find_if(naturalPolicyBefore.policies.begin(),naturalPolicyBefore.policies.end(),[&](const SocialPolicySmokeFixture::Policy& value){
                                    return value.id==opener;
                                });
                                // This finite worker scenario audits only the first paid Tradition opener.
                                // Its rules do not change worker speed, missions, movement or improvements.
                                if(naturalPolicyId!=0 || opener!=6 || naturalPolicyBefore.activePlayer!=world.activePlayer || naturalPolicyBefore.turn!=world.turn ||
                                   naturalPolicyBefore.freePolicies!=0 || naturalPolicyBefore.policySaving || naturalPolicyBefore.nextCost<=0 ||
                                   naturalPolicyBefore.culture<naturalPolicyBefore.nextCost || branch==naturalPolicyBefore.branches.end() ||
                                   branch->unlocked || !branch->canUnlock || branch->blocked || branch->freePolicy!=opener ||
                                   policy==naturalPolicyBefore.policies.end() || policy->has || policy->blocked)
                                    throw std::runtime_error("Natural policy blocker lacks its legal, affordable and unowned Tradition opener");
                                naturalPolicyOwner=world.activePlayer;naturalPolicyTurn=world.turn;naturalPolicyGeneration=window.SceneGeneration();
                                naturalPolicyWorker=live.ObserveBuild(context,workerID,workerBuild);
                                naturalPolicyBeforeState=SdkStateSnapshot::Capture(host);naturalPolicyPending=true;++naturalPolicyCycles;
                                const auto inventoryPath=directory+L"\\worker-policy-"+std::to_wstring(naturalPolicyCycles)+L"-before-inventory.json";
                                Write(inventoryPath,SocialPolicySmokeFixture::Serialize(naturalPolicyBefore));
                                std::printf("INTERACTIVE_WORKER_POLICY_BEGIN=%u|%d|%d|%d|%llu|%d|%d|%d\n",naturalPolicyCycles,world.turn,world.activePlayer,
                                    observed.notificationIndex,static_cast<unsigned long long>(naturalPolicyGeneration),
                                    naturalPolicyBefore.culture,naturalPolicyBefore.nextCost,naturalPolicyBefore.freePolicies);
                                std::printf("INTERACTIVE_WORKER_POLICY_INVENTORY=%u|before|%s\n",naturalPolicyCycles,Utf8(inventoryPath).c_str());
                                naturalPolicyWorkerState("before");
                                next=actionInfoButton("policy-continuation");smokeStage=92;return;
                            }
                            if(naturalWorkerResearch && observed.blockingType==ENDTURN_BLOCKING_PRODUCTION){
                                if(uiActive || naturalAwardPending || naturalPolicyPending || naturalProductionPending || naturalProductionFinished!=1 ||
                                   naturalProductionCycles!=0 || naturalProductionTurn!=world.turn || observed.owner!=world.activePlayer || observed.turn!=world.turn ||
                                   observed.canEndTurn || observed.notificationIndex<0 || !live.CanChooseProduction(decisionCity))
                                    throw std::runtime_error("Natural production blocker is outside its first completed owned-city order");
                                const auto notice=std::find_if(observed.notifications.begin(),observed.notifications.end(),[&](const NotificationPresentation& item){
                                    return item.id==observed.notificationIndex && item.player==world.activePlayer && item.type==NOTIFICATION_PRODUCTION;
                                });
                                if(notice==observed.notifications.end())throw std::runtime_error("Natural production blocker lacks its matching SDK notification");
                                naturalProductionBefore=live.ObserveProduction(decisionCity);
                                if(naturalProductionBefore.length!=0 || naturalProductionBefore.unit!=-1)
                                    throw std::runtime_error("Natural production continuation requires an empty completed city queue");
                                naturalProductionOwner=world.activePlayer;naturalProductionResearch=live.CurrentResearch();
                                if(naturalProductionResearch<0)throw std::runtime_error("Natural production continuation has no selected original research");
                                naturalProductionResearchBefore=live.ObserveResearch(naturalProductionResearch);
                                naturalProductionWorker=live.ObserveBuild(context,workerID,workerBuild);
                                naturalProductionBeforeState=SdkStateSnapshot::Capture(host);naturalProductionGeneration=window.SceneGeneration();
                                naturalProductionPending=true;++naturalProductionCycles;
                                std::printf("INTERACTIVE_WORKER_PRODUCTION_BEGIN=%u|%d|%d|%d|%d|%llu|%d\n",naturalProductionCycles,world.turn,
                                    world.activePlayer,decisionCity,observed.notificationIndex,static_cast<unsigned long long>(naturalProductionGeneration),naturalProductionResearch);
                                naturalProductionQueue("before",naturalProductionBefore,world.turn,naturalProductionGeneration);
                                naturalProductionWorkerState("before");next=actionInfoButton("production-continuation");smokeStage=96;return;
                            }
                            if(observed.blockingType!=NO_ENDTURN_BLOCKING_TYPE || !observed.canEndTurn)
                                throw std::runtime_error("Unhandled original end-turn blocker in bounded worker smoke: blockingType="+
                                    std::to_string(observed.blockingType)+", notification="+std::to_string(observed.notificationIndex)+
                                    ", canEndTurn="+std::to_string(observed.canEndTurn));
                            next=actionInfoButton("end-turn");
                        }else next=WorldViewHitKey::Action(WorldViewAction::EndTurn);
                        if(naturalWorkerResearch){
                            workerResearchTech=live.CurrentResearch();workerResearchTurn=world.turn;
                            if(workerResearchTech<0 || live.HasTechnology(workerResearchTech) || world.turn>=initialTurn+32)
                                throw std::runtime_error("Worker end-turn lacks its original uncompleted research selection or exceeds its bound");
                            workerResearchBefore=live.ObserveResearch(workerResearchTech);
                            if(naturalProductionFinished==0){
                                naturalProductionBeforeTurn=live.ObserveProduction(decisionCity);
                                if(naturalProductionBeforeTurn.length!=1 || naturalProductionBeforeTurn.unit!=decisionUnit ||
                                   naturalProductionBeforeTurn.production<0 || naturalProductionBeforeTurn.needed<=naturalProductionBeforeTurn.production)
                                    throw std::runtime_error("Natural first production order changed before its completing turn");
                                naturalProductionWorldBefore=world;naturalProductionBeforeGeneration=window.SceneGeneration();
                                naturalProductionBeforeScene=directory+L"\\play-scene-"+std::to_wstring(revision)+L".json";
                            }
                            std::printf("INTERACTIVE_WORKER_RESEARCH_BEFORE_TURN=%d|%d|%d|%llu|0|%d|%d\n",world.turn,world.activePlayer,
                                workerResearchTech,static_cast<unsigned long long>(window.SceneGeneration()),workerResearchBefore[9],workerResearchBefore[10]);
                        }
                        smokeStage=4;
                    }
                    else{
                        bool selected=false;for(const auto& unit:world.ownedUnits)if(unit.id==ready.front() && unit.selected)selected=true;
                        if(selected && naturalWorkerResearch && naturalProductionFinished==1 && naturalProductionCycles==0 &&
                           world.turn==naturalProductionTurn && live.IsProductionCivilianStack(context,ready.front(),naturalProducedUnit,decisionCity)){
                            if(uiActive || originalMission.kind || naturalAwardPending || naturalPolicyPending || naturalProductionPending ||
                               naturalUnstack.pending || naturalUnstack.cycles!=0 || naturalUnstack.completed!=0)
                                throw std::runtime_error("Natural civilian unstack is outside its single completed-production boundary");
                            const auto selection=host.localSelection.Snapshot();
                            const auto unit=std::find_if(world.ownedUnits.begin(),world.ownedUnits.end(),[&](const WorldViewState::Unit& value){
                                return value.id==ready.front() && value.owner==world.activePlayer && value.selected;
                            });
                            if(unit==world.ownedUnits.end() || unit->id==naturalProducedUnit || unit->id==workerID ||
                               unit->unitType!=decisionUnit || unit->type!="UNIT_SETTLER" || unit->moves<=0 ||
                               selection.size()!=1 || selection.front().first!=world.activePlayer || selection.front().second!=unit->id ||
                               std::none_of(naturalProductionWorldBefore.ownedUnits.begin(),naturalProductionWorldBefore.ownedUnits.end(),
                                   [&](const WorldViewState::Unit& previous){return previous.id==unit->id && previous.owner==unit->owner && previous.unitType==unit->unitType;}))
                                throw std::runtime_error("Natural civilian unstack did not select the existing owned settler");
                            for(const auto& plot:world.plots)if(plot.revealed && plot.visible &&
                                std::find(scene.pixelHits.keys.begin(),scene.pixelHits.keys.end(),WorldViewHitKey::Plot(plot.index))!=scene.pixelHits.keys.end() &&
                                live.IsVacantAdjacentMoveLegal(unit->id,plot.x,plot.y)){
                                naturalUnstack.toPlot=plot.index;naturalUnstack.toX=plot.x;naturalUnstack.toY=plot.y;
                                next=WorldViewHitKey::Plot(plot.index);break;
                            }
                            if(!next)throw std::runtime_error("Natural civilian unstack has no published vacant legal adjacent destination");
                            naturalUnstack.production=live.ObserveProduction(decisionCity);
                            if(naturalUnstack.production.length!=0 || naturalUnstack.production.unit!=-1)
                                throw std::runtime_error("Natural civilian unstack lost the completed city's empty production queue");
                            naturalUnstack.research=live.CurrentResearch();
                            if(naturalUnstack.research<0)throw std::runtime_error("Natural civilian unstack lacks selected original research");
                            naturalUnstack.researchBefore=live.ObserveResearch(naturalUnstack.research);
                            naturalUnstack.worker=live.ObserveBuild(context,workerID,workerBuild);
                            naturalUnstack.owner=world.activePlayer;naturalUnstack.turn=world.turn;
                            naturalUnstack.unit=unit->id;naturalUnstack.produced=naturalProducedUnit;naturalUnstack.unitType=unit->unitType;
                            naturalUnstack.fromPlot=unit->plotIndex;naturalUnstack.fromX=unit->x;naturalUnstack.fromY=unit->y;naturalUnstack.moves=unit->moves;
                            naturalUnstack.mission=context.GetInfoTypeForString("MISSION_MOVE_TO",true);
                            naturalUnstack.generation=window.SceneGeneration();naturalUnstack.key=next;naturalUnstack.beforeWorld=world;
                            naturalUnstack.beforeScene=directory+L"\\play-scene-"+std::to_wstring(revision)+L".json";
                            naturalUnstack.pending=true;++naturalUnstack.cycles;
                            std::printf("INTERACTIVE_WORKER_UNSTACK_BEGIN=%u|%d|%d|%d|%d|%d|%d|%d|%d|%d|%d|%llu|%d|2|1|0\n",
                                naturalUnstack.cycles,world.turn,world.activePlayer,decisionCity,unit->id,naturalProducedUnit,unit->unitType,
                                unit->plotIndex,unit->x,unit->y,unit->moves,static_cast<unsigned long long>(naturalUnstack.generation),naturalUnstack.research);
                            naturalUnstackState("before");
                            std::printf("INTERACTIVE_WORKER_UNSTACK_TARGET=%u|%d|%d|%d|%d|%d|%d|%llu|%llu|%d|1|1\n",naturalUnstack.cycles,
                                world.turn,world.activePlayer,naturalUnstack.unit,naturalUnstack.toPlot,naturalUnstack.toX,naturalUnstack.toY,
                                static_cast<unsigned long long>(next),static_cast<unsigned long long>(naturalUnstack.generation),naturalUnstack.mission);
                            nextRight=true;smokeStage=98;
                        }else if(selected)originalMissionButton("skip",ready.front(),context.GetInfoTypeForString("MISSION_SKIP",true),-1);
                        else next=WorldViewHitKey::OwnedUnit(ready.front());
                    }
                }else if(smokeStage==98){
                    if(!naturalWorkerResearch || !naturalUnstack.pending || naturalUnstack.commands!=1 || naturalUnstack.cycles!=1 ||
                       uiActive || !actionInfoActive || world.turn!=naturalUnstack.turn || world.activePlayer!=naturalUnstack.owner ||
                       window.SceneGeneration()<=naturalUnstack.generation || world.ownedUnits.size()!=naturalUnstack.beforeWorld.ownedUnits.size())
                        throw std::runtime_error("Natural civilian unstack did not return to its same-turn world after one original move");
                    for(const auto& previous:naturalUnstack.beforeWorld.ownedUnits){
                        const auto unit=std::find_if(world.ownedUnits.begin(),world.ownedUnits.end(),[&](const WorldViewState::Unit& value){
                            return value.id==previous.id && value.owner==previous.owner && value.unitType==previous.unitType;
                        });
                        if(unit==world.ownedUnits.end() || unit->damage!=previous.damage ||
                           (previous.id==naturalUnstack.unit ?
                            (unit->plotIndex!=naturalUnstack.toPlot || unit->x!=naturalUnstack.toX || unit->y!=naturalUnstack.toY ||
                             unit->moves<0 || unit->moves>=naturalUnstack.moves) :
                            (unit->plotIndex!=previous.plotIndex || unit->x!=previous.x || unit->y!=previous.y || unit->moves!=previous.moves)))
                            throw std::runtime_error("Natural civilian unstack changed another owned unit or failed its exact move");
                    }
                    naturalUnstackState("returned");
                    const auto moved=std::find_if(world.ownedUnits.begin(),world.ownedUnits.end(),[&](const WorldViewState::Unit& value){return value.id==naturalUnstack.unit;});
                    const auto afterScene=directory+L"\\play-scene-"+std::to_wstring(revision)+L".json";
                    std::printf("INTERACTIVE_WORKER_UNSTACK_SCENES=%u|%s|%s\n",naturalUnstack.cycles,Utf8(naturalUnstack.beforeScene).c_str(),Utf8(afterScene).c_str());
                    std::printf("INTERACTIVE_WORKER_UNSTACK_RETURNED=%u|%d|%d|%d|%d|%d|%d|%d|%d|%llu|%d\n",naturalUnstack.cycles,
                        world.turn,world.activePlayer,naturalUnstack.unit,naturalUnstack.produced,moved->plotIndex,moved->x,moved->y,moved->moves,
                        static_cast<unsigned long long>(window.SceneGeneration()),naturalUnstack.research);
                    naturalUnstack.pending=false;++naturalUnstack.completed;smokeStage=3;
                }else if(smokeStage==90){
                    if(!naturalWorkerResearch || !uiActive || live.UiKind()!=UiPopupKind::Research || world.turn!=naturalAwardTurn)
                        throw std::runtime_error("Original research blocker did not open the same-turn TechPopup");
                    nextResearchTech=-1;
                    for(const auto& target:live.UiTargets())if(target.id=="TechButton" && target.hasVoidPayload && target.void1>=0 && target.void2==0 &&
                        !target.consumeMouseOnly && !live.HasTechnology(target.void1) && live.CanResearch(target.void1) &&
                        (nextResearchTech<0 || target.void1<nextResearchTech)){
                        nextResearchTech=target.void1;next=target.key;
                    }
                    if(!next)throw std::runtime_error("Original continuation TechPopup has no legal unowned research callback");
                    nextResearchGeneration=window.SceneGeneration();nextResearchWorker=live.ObserveBuild(context,workerID,workerBuild);
                    std::printf("INTERACTIVE_WORKER_RESEARCH_TARGET=%d|%d|%d|%llu|%llu\n",world.turn,world.activePlayer,nextResearchTech,
                        static_cast<unsigned long long>(next),static_cast<unsigned long long>(nextResearchGeneration));smokeStage=91;
                }else if(smokeStage==91){
                    if(!naturalWorkerResearch || uiActive || world.turn!=naturalAwardTurn || window.SceneGeneration()<=nextResearchGeneration ||
                       live.CurrentResearch()!=nextResearchTech || live.HasTechnology(nextResearchTech) ||
                       !sameBuildObservation(live.ObserveBuild(context,workerID,workerBuild),nextResearchWorker))
                        throw std::runtime_error("Original continuation research callback did not close, select its SDK technology and preserve the worker");
                    const auto selected=live.ObserveResearch(nextResearchTech);
                    std::printf("INTERACTIVE_WORKER_RESEARCH_SELECTED=%d|%d|%d|%llu|%d|0|%d|%d\n",world.turn,world.activePlayer,
                        nextResearchTech,static_cast<unsigned long long>(window.SceneGeneration()),live.CurrentResearch(),selected[9],selected[10]);smokeStage=3;
                }else if(smokeStage==92){
                    naturalPolicyPopupBoundary();
                    if(SdkStateSnapshot::Capture(host)!=naturalPolicyBeforeState ||
                       SocialPolicySmokeFixture::Serialize(live.ObserveSocialPolicySmoke())!=SocialPolicySmokeFixture::Serialize(naturalPolicyBefore))
                        throw std::runtime_error("Original policy notification changed SDK state before selection");
                    next=naturalPolicyTarget("branch","BranchButton"+std::to_string(naturalPolicyId),naturalPolicyId);smokeStage=93;
                }else if(smokeStage==93){
                    naturalPolicyPopupBoundary();
                    if(SdkStateSnapshot::Capture(host)!=naturalPolicyBeforeState ||
                       SocialPolicySmokeFixture::Serialize(live.ObserveSocialPolicySmoke())!=SocialPolicySmokeFixture::Serialize(naturalPolicyBefore))
                        throw std::runtime_error("Original branch selection changed SDK state before Yes");
                    naturalPolicyWorkerState("selected");next=naturalPolicyTarget("confirm","Yes");smokeStage=94;
                }else if(smokeStage==94){
                    naturalPolicyPopupBoundary();naturalPolicyAfter=live.ObserveSocialPolicySmoke();
                    SocialPolicySmokeFixture::RequireAdoption(naturalPolicyBefore,naturalPolicyAfter,naturalPolicyId,false);
                    if(naturalPolicyAfter.freeTenets!=naturalPolicyBefore.freeTenets || naturalPolicyAfter.ideology!=naturalPolicyBefore.ideology)
                        throw std::runtime_error("Natural Tradition opener changed ideology or free tenets");
                    // Confirmed policies legitimately change the SDK and may consume RNG.
                    // Establish a new baseline only after the original receiver has applied the choice.
                    naturalPolicyAfterState=SdkStateSnapshot::Capture(host);
                    const auto inventoryPath=directory+L"\\worker-policy-"+std::to_wstring(naturalPolicyCycles)+L"-after-inventory.json";
                    Write(inventoryPath,SocialPolicySmokeFixture::Serialize(naturalPolicyAfter));
                    std::printf("INTERACTIVE_WORKER_POLICY_ADOPTED=%u|%d|%d|%d|0|%d|%d|%d|%llu\n",naturalPolicyCycles,world.turn,world.activePlayer,
                        naturalPolicyId,naturalPolicyBefore.culture,naturalPolicyBefore.nextCost,naturalPolicyAfter.culture,
                        static_cast<unsigned long long>(window.SceneGeneration()));
                    std::printf("INTERACTIVE_WORKER_POLICY_INVENTORY=%u|after|%s\n",naturalPolicyCycles,Utf8(inventoryPath).c_str());
                    naturalPolicyWorkerState("adopted");next=naturalPolicyTarget("close","CloseButton");smokeStage=95;
                }else if(smokeStage==95){
                    if(!naturalWorkerResearch || !naturalPolicyPending || uiActive || !actionInfoActive || world.activePlayer!=naturalPolicyOwner ||
                       world.turn!=naturalPolicyTurn || window.SceneGeneration()<=naturalPolicyGeneration || SdkStateSnapshot::Capture(host)!=naturalPolicyAfterState ||
                       SocialPolicySmokeFixture::Serialize(live.ObserveSocialPolicySmoke())!=SocialPolicySmokeFixture::Serialize(naturalPolicyAfter))
                        throw std::runtime_error("Original policy Close did not restore the same-turn world and adopted SDK state");
                    naturalPolicyWorkerState("returned");
                    const auto observed=live.ObserveActionInfoPanel();
                    if(observed.owner!=naturalPolicyOwner || observed.turn!=naturalPolicyTurn)
                        throw std::runtime_error("Policy return observed another SDK owner or turn");
                    std::printf("INTERACTIVE_WORKER_POLICY_RETURNED=%u|%d|%d|%llu|%d|%d|%u|%d\n",naturalPolicyCycles,world.turn,world.activePlayer,
                        static_cast<unsigned long long>(window.SceneGeneration()),observed.blockingType,observed.notificationIndex,
                        observed.canEndTurn?1u:0u,live.CurrentResearch());
                    naturalPolicyPending=false;++naturalPolicyCompleted;smokeStage=3;
                }else if(smokeStage==96){
                    if(!naturalWorkerResearch || !naturalProductionPending || !uiActive || live.UiKind()!=UiPopupKind::Production ||
                       world.activePlayer!=naturalProductionOwner || world.turn!=naturalProductionTurn || window.SceneGeneration()<=naturalProductionGeneration ||
                       SdkStateSnapshot::Capture(host)!=naturalProductionBeforeState || live.ObserveResearch(naturalProductionResearch)!=naturalProductionResearchBefore)
                        throw std::runtime_error("Original production notification did not open its same-turn unchanged production popup");
                    const auto opened=live.ObserveProduction(decisionCity);
                    if(opened.length!=naturalProductionBefore.length || opened.unit!=naturalProductionBefore.unit ||
                       opened.production!=naturalProductionBefore.production || opened.needed!=naturalProductionBefore.needed)
                        throw std::runtime_error("Original production notification changed its empty city queue");
                    naturalProductionQueue("opened",opened,world.turn,window.SceneGeneration());naturalProductionWorkerState("opened");
                    naturalProductionUnit=-1;
                    for(const auto& target:live.UiTargets())if(target.id=="Button" && target.hasVoidPayload && target.void1==6 && target.void2>=0 &&
                        !target.consumeMouseOnly && live.CanTrain(decisionCity,target.void2) &&
                        (naturalProductionUnit<0 || target.void2<naturalProductionUnit)){
                        naturalProductionUnit=target.void2;next=target.key;
                    }
                    if(!next)throw std::runtime_error("Original production continuation has no legal published training callback");
                    naturalProductionKey=next;naturalProductionGeneration=window.SceneGeneration();
                    std::printf("INTERACTIVE_WORKER_PRODUCTION_TARGET=%u|%d|%d|%d|%d|%llu|%llu|%u\n",naturalProductionCycles,world.turn,
                        world.activePlayer,decisionCity,naturalProductionUnit,static_cast<unsigned long long>(next),
                        static_cast<unsigned long long>(naturalProductionGeneration),uiRevision);smokeStage=97;
                }else if(smokeStage==97){
                    if(!naturalWorkerResearch || !naturalProductionPending || uiActive || !actionInfoActive || world.activePlayer!=naturalProductionOwner ||
                       world.turn!=naturalProductionTurn || window.SceneGeneration()<=naturalProductionGeneration ||
                       live.ObserveResearch(naturalProductionResearch)!=naturalProductionResearchBefore)
                        throw std::runtime_error("Original production callback did not return to its same-turn world and research");
                    const auto after=live.ObserveProduction(decisionCity);
                    if(after.length!=1 || after.unit!=naturalProductionUnit || after.production<0 || after.needed<=after.production)
                        throw std::runtime_error("Original production callback did not queue exactly its legal unfinished unit");
                    naturalProductionQueue("returned",after,world.turn,window.SceneGeneration());naturalProductionWorkerState("returned");
                    const auto observed=live.ObserveActionInfoPanel();
                    if(observed.owner!=naturalProductionOwner || observed.turn!=naturalProductionTurn ||
                       observed.blockingType!=NO_ENDTURN_BLOCKING_TYPE || observed.notificationIndex!=-1 || !observed.canEndTurn ||
                       live.CurrentResearch()!=naturalProductionResearch)
                        throw std::runtime_error("Natural production return did not clear its actual end-turn blocker");
                    std::printf("INTERACTIVE_WORKER_PRODUCTION_RETURNED=%u|%d|%d|%d|%d|%llu|%d|%d|%u|%d\n",naturalProductionCycles,
                        world.turn,world.activePlayer,decisionCity,naturalProductionUnit,static_cast<unsigned long long>(window.SceneGeneration()),
                        observed.blockingType,observed.notificationIndex,observed.canEndTurn?1u:0u,live.CurrentResearch());
                    naturalProductionPending=false;++naturalProductionCompleted;smokeStage=3;
                }else if(smokeStage==4){
                    if(!smokeMoved || world.turn<initialTurn+1 || (!workerSmoke && world.turn!=initialTurn+1))
                        throw std::runtime_error("Posted end-turn did not return to the next real human turn");
                    bool naturalCompleted=false;
                    if(naturalWorkerResearch){
                        naturalCompleted=live.HasTechnology(workerResearchTech);
                        if(uiActive || world.turn!=workerResearchTurn+1 || world.activePlayer!=workerResearchBefore[2] ||
                           (naturalCompleted && (naturalAwardPending || naturalAwardTurn!=world.turn || naturalAwardTech!=workerResearchTech)) ||
                           (!naturalCompleted && live.CurrentResearch()!=workerResearchTech))
                            throw std::runtime_error("Worker turn returned without its tracked research or complete original award sequence");
                        const auto research=live.ObserveResearch(workerResearchTech,naturalCompleted);
                        if(naturalCompleted ? (research[9]<workerResearchBefore[9] || research[10]!=0) :
                           (research[9]<=workerResearchBefore[9] || !naturalResearchRemainingAdvanced(workerResearchBefore[10],research[10])))
                            throw std::runtime_error("Worker turn did not advance or naturally complete its exact SDK research");
                        std::printf("INTERACTIVE_WORKER_RESEARCH_TURN_RETURNED=%d|%d|%d|%llu|%d|%d|%d|%d\n",world.turn,world.activePlayer,
                            workerResearchTech,static_cast<unsigned long long>(window.SceneGeneration()),live.CurrentResearch(),naturalCompleted?1:0,research[9],research[10]);
                        if(naturalProductionFinished==0){
                            const auto production=live.ObserveProduction(decisionCity);
                            if(production.length==0 && production.unit==-1){
                                const auto city=std::find_if(world.visibleCities.begin(),world.visibleCities.end(),[&](const WorldViewState::City& value){
                                    return value.id==decisionCity && value.owner==world.activePlayer;
                                });
                                if(city==world.visibleCities.end() || naturalProductionWorldBefore.turn+1!=world.turn ||
                                   naturalProductionWorldBefore.activePlayer!=world.activePlayer || naturalProductionBeforeTurn.length!=1 ||
                                   naturalProductionBeforeTurn.unit!=decisionUnit || world.ownedUnits.size()!=naturalProductionWorldBefore.ownedUnits.size()+1)
                                    throw std::runtime_error("Natural production completion changed its city, turn or expected owned-unit count");
                                for(const auto& previous:naturalProductionWorldBefore.ownedUnits)if(std::none_of(world.ownedUnits.begin(),world.ownedUnits.end(),
                                    [&](const WorldViewState::Unit& value){return value.id==previous.id && value.owner==previous.owner && value.unitType==previous.unitType;}))
                                    throw std::runtime_error("Natural production completion lost a previous owned unit");
                                unsigned added=0;
                                for(const auto& value:world.ownedUnits)if(std::none_of(naturalProductionWorldBefore.ownedUnits.begin(),naturalProductionWorldBefore.ownedUnits.end(),
                                    [&](const WorldViewState::Unit& previous){return previous.id==value.id;})){
                                    if(value.owner!=world.activePlayer || value.unitType!=decisionUnit || value.x!=city->x || value.y!=city->y)
                                        throw std::runtime_error("Natural production completed a different unit or city");
                                    naturalProducedUnit=value.id;++added;
                                }
                                if(added!=1)throw std::runtime_error("Natural production completion has no unique new owned settler");
                                naturalProductionTurn=world.turn;++naturalProductionFinished;
                                std::printf("INTERACTIVE_WORKER_PRODUCTION_FINISHED=1|%d|%d|%d|%d|%d|%llu\n",world.turn,world.activePlayer,
                                    decisionCity,decisionUnit,naturalProducedUnit,static_cast<unsigned long long>(window.SceneGeneration()));
                                const auto afterScene=directory+L"\\play-scene-"+std::to_wstring(revision)+L".json";
                                std::printf("INTERACTIVE_WORKER_PRODUCTION_SCENES=1|%s|%s\n",Utf8(naturalProductionBeforeScene).c_str(),Utf8(afterScene).c_str());
                                naturalProductionQueue("last-turn",naturalProductionBeforeTurn,world.turn-1,naturalProductionBeforeGeneration);
                                naturalProductionQueue("finished",production,world.turn,window.SceneGeneration());
                            }else if(production.length!=1 || production.unit!=decisionUnit)
                                throw std::runtime_error("Natural first production order changed without its expected completed settler");
                        }
                    }
                    if(decisions && !decisionTurnChecked){
                        const bool naturalDecisionCompleted=naturalCompleted && workerResearchTech==decisionTech;
                        const auto after=live.DecisionState(decisionCity,decisionUnit,decisionTech,techAwardSmoke || naturalDecisionCompleted);
                        EmitDecision("INTERACTIVE_DECISION_AFTER_TURN",after);
                        if(after[6]!=1 || after[7]<=decisionBefore[7] || after[8]!=decisionBefore[8] ||
                           (naturalDecisionCompleted ? (after[9]<decisionBefore[9] || after[10]!=0) :
                            (after[9]<=decisionBefore[9] || (!techAwardSmoke && (naturalWorkerResearch?
                                !naturalResearchRemainingAdvanced(decisionBefore[10],after[10]):after[10]>=decisionBefore[10])))))
                            throw std::runtime_error("Normal integrated turn did not advance original production and research");
                        SdkStateSnapshot::Write(directory+L"\\play-decisions-next-turn-state.txt",SdkStateSnapshot::Capture(host));
                        if(techAwardSmoke){
                            if(uiActive || techAwardChoices!=1 || !live.HasTechnology(decisionTech) || live.CurrentResearch()==decisionTech)
                                throw std::runtime_error("Research completion did not settle after the original award callback");
                            std::printf("INTERACTIVE_RESEARCH_COMPLETION_VERIFIED=%d|%d|%d|1|%u\n",decisionTech,world.turn,live.CurrentResearch(),techAwardChoices);
                        }
                        std::puts("INTERACTIVE_DECISION_SMOKE_COMPLETE=1");decisionTurnChecked=true;
                    }
                    bool buildComplete=true;
                    if(workerSmoke){
                        const auto after=live.ObserveBuild(context,workerID,workerBuild);
                        buildComplete=after.improvement==workerBefore.expected;
                        // An order issued on turn zero already spent that
                        // turn's worker moves. At the first next-turn input
                        // boundary the SDK restores movement; its queued
                        // AutoMission runs when that new turn is processed.
                        const bool firstPending=world.turn==initialTurn+1 && after.progress==workerProgress &&
                            after.mission==context.GetInfoTypeForString("MISSION_BUILD",true) &&
                            after.missionBuild==workerBuild && after.moves>0;
                        std::printf("INTERACTIVE_WORKER_BUILD_OBSERVED=%d|%d|%d|%d|%d|%d|%d|%d|%d\n",
                            world.turn,workerID,after.plot,workerBuild,after.progress,after.improvement,after.moves,after.mission,after.missionBuild);
                        if(after.plot!=workerBefore.plot || (!buildComplete && after.progress<=workerProgress && !firstPending))
                            throw std::runtime_error("Normal turns did not continue construction on the same worker plot");
                        if(!buildComplete && firstPending)std::printf("INTERACTIVE_WORKER_BUILD_AWAITING_TURN=%d|%d|%d|%d|%d|%d|%d|%d\n",
                            world.turn,workerID,after.plot,workerBuild,after.progress,after.moves,after.mission,after.missionBuild);
                        if(world.turn-initialTurn>32)throw std::runtime_error("Worker construction exceeded the finite turn bound");
                        workerProgress=after.progress;
                        std::printf("INTERACTIVE_WORKER_BUILD_PROGRESS=%d|%d|%d|%d|%d|%d\n",world.turn,workerID,after.plot,workerBuild,after.progress,after.improvement);
                        if(buildComplete)std::printf("INTERACTIVE_WORKER_BUILD_COMPLETED=%d|%d|%d|%d|%d\n",workerID,after.plot,workerBuild,after.improvement,world.turn);
                    }
                    if(buildComplete){
                        if(socialPolicySmoke)Write(directory+(policyTenetSmoke?L"\\tenet-next-turn-inventory.json":L"\\social-policy-next-turn-inventory.json"),
                            SocialPolicySmokeFixture::Serialize(live.ObserveSocialPolicySmoke()));
                        next=WorldViewHitKey::Action(WorldViewAction::Save);smokeStage=5;
                    }
                    else smokeStage=3;
                }else if(smokeStage==5){
                    if(checkpoint.empty())throw std::runtime_error("Save did not publish the scene-transition close regression frame");
                    if(decisions){next=WorldViewHitKey::OwnedCity(decisionCity);smokeStage=84;}
                    else {next=WorldViewHitKey::Action(WorldViewAction::Research);smokeStage=7;}
                }else if(smokeStage==84){
                    if(!uiActive || live.UiKind()!=UiPopupKind::CityView)throw std::runtime_error("Close regression did not reopen the original city");
                    for(const auto& target:live.UiTargets())if(target.id=="BuyPlotButton")next=target.key;
                    if(!next)throw std::runtime_error("Close regression has no original buy plot mode control");smokeStage=85;
                }else if(smokeStage==85){
                    if(host.interfaceMode!=INTERFACEMODE_PURCHASE_PLOT || !uiActive || live.UiKind()!=UiPopupKind::CityView)
                        throw std::runtime_error("Close regression did not enter original purchase-plot mode");
                    for(const auto& target:live.UiTargets())if(target.id=="PurchaseButton")next=target.key;
                    if(!next)throw std::runtime_error("Close regression has no original purchase popup control");
                    std::printf("INTERACTIVE_CITY_PURCHASE_CLOSE_TARGET=%d|%d|%llu|%llu\n",decisionCity,world.turn,
                        static_cast<unsigned long long>(next),static_cast<unsigned long long>(window.SceneGeneration()));
                    purchaseCloseSmoke=true;smokeStage=7;
                }
            });
            if(next && !PostClick(window,scene,next,nextRight,nextShift))throw std::runtime_error("Gameplay smoke target has no visible native hit record");
        }
        // Wait with no borrowed SDK object call or GameCore lock held.
        MsgWaitForMultipleObjectsEx(0,nullptr,16,QS_ALLINPUT,MWMO_INPUTAVAILABLE);
    }
    if(smoke && smokeStage!=6)throw std::runtime_error("Gameplay smoke closed before its complete input sequence");
    if(naturalWorkerResearch && unitCycleStage!=3)
        throw std::runtime_error("Gameplay smoke closed before its original unit-cycle camera round trip");
    if(smoke && topPanelEnabled && topPanelSmokeStage!=3)
        throw std::runtime_error("Gameplay smoke closed before the original TopPanel science round trip");
    if(gameMenuSmoke && gameMenuSmokeStage!=12)
        throw std::runtime_error("Gameplay smoke closed before its original menu, confirmation, quick-save and native-key roundtrips");
    if(smoke && actionInfoEnabled){
        if(actionInfoUnitStage!=3 || (checkpoint.empty() && actionInfoNotificationStage!=3))
            throw std::runtime_error("Gameplay smoke closed before the original end-turn HUD and notification roundtrip");
        std::puts("INTERACTIVE_ACTION_INFO_PANEL_SMOKE_COMPLETE=1");
    }
    if(smoke && notificationEnabled){
        if(checkpoint.empty() && notificationSmokeStage!=5)
            throw std::runtime_error("Notification smoke closed before its original popup, forbidden dismissal and SDK removal sequence");
        std::printf("INTERACTIVE_NOTIFICATION_PANEL_SMOKE_COMPLETE=%s\n",checkpoint.empty()?"FRESH_INPUT_AND_SDK_REMOVAL":"RESTORED_SDK_LIST_PRESENTATION");
    }
    if(tradeRouteSmoke && tradeRouteSmokeStage!=13)
        throw std::runtime_error("Gameplay smoke closed before the original TradeRoute overview round trip");
    if(economicSmoke && !economicScenario.Complete())
        throw std::runtime_error("Gameplay smoke closed before economic cancel, production replacement and original popup return");
    if(socialPolicySmoke && (policyTenetSmoke?tenetStage!=22:socialPolicyStage!=19))
        throw std::runtime_error("Gameplay smoke closed before paid SocialPolicy adoptions and the original popup return");
    if(smoke && unitAnimation && (!worldAnimationProved || (decisions&&!uiAnimationProved)))
        throw std::runtime_error("Gameplay smoke did not exercise live animation across world/UI frames");
    if(naturalWorkerResearch){
        if(naturalUnstack.pending || naturalUnstack.cycles!=naturalUnstack.completed || naturalUnstack.commands!=naturalUnstack.completed ||
           naturalUnstack.cycles>1 || naturalUnstack.cycles>naturalProductionFinished)
            throw std::runtime_error("Natural civilian unstack did not complete its bounded original movement sequence");
        if(naturalProductionPending || naturalProductionFinished!=naturalProductionCycles || naturalProductionCompleted!=naturalProductionCycles || naturalProductionCycles>1)
            throw std::runtime_error("Natural production continuation did not complete its bounded original callback sequence");
        if(naturalPolicyPending || naturalPolicyCompleted!=naturalPolicyCycles || naturalPolicyCycles>1)
            throw std::runtime_error("Gameplay smoke closed before its natural paid-policy callback sequence completed");
        std::printf("INTERACTIVE_WORKER_UNSTACK_COMPLETE=%u\n",naturalUnstack.completed);
        std::printf("INTERACTIVE_WORKER_PRODUCTION_COMPLETE=%u\n",naturalProductionCompleted);
        std::printf("INTERACTIVE_WORKER_POLICY_COMPLETE=%u\n",naturalPolicyCompleted);
    }
    return {};
}
}
#endif
