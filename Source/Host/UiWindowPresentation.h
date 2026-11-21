#pragma once
#include "HostFiles.h"
#include "../Presentation/BitmapRenderer.h"
#include "../Presentation/BitmapWindow.h"
#include <algorithm>
#include <cstdio>
#include <functional>

namespace ZeroSisHost {

// Runs only after game.Update has returned, on the owner thread with its lock.
// The preparer reads the retained tree; HWND callbacks never invoke Lua/SDK.
class UiWindowPresentation final {
public:
    // A live production context can remain open across several callbacks. Paint,
    // pointer targets and scroll ownership are replaced as one scene transaction.
    // Pending messages are drained before Lua/SDK calls; events from a replaced
    // scene never reach a callback even if their retained key still exists.
    static void ServeProduction(unsigned sequence,int turn,const std::wstring& directory,
                      const std::string& shown,
                      const std::function<std::string()>& snapshot,
                      const std::function<bool()>& active,
                      const std::function<bool(const ZeroSisPresentation::BitmapInputEvent&)>& dispatch,
                      const std::function<std::vector<std::uint64_t>()>& currentKeys,
                      const std::function<std::vector<std::uint64_t>()>& scrollKeys,
                      const std::function<std::wstring(unsigned)>& freeze) {
        using namespace ZeroSisPresentation;
        if(!active() || !currentKeys || !scrollKeys || !freeze)
            throw std::logic_error("Live production presentation requires an active owned context");
        std::wstring error;
        const auto initial=directory+L"\\ui-popup-"+std::to_wstring(sequence)+L"-window.json";
        const auto presentation=directory+L"\\presentation-popup-"+std::to_wstring(sequence);
        char reply[96]={};
        const auto acknowledge=[&](const std::string& expected) {
            if(!std::fgets(reply,sizeof(reply),stdin) || std::string(reply)!=expected+"\n")
                throw std::runtime_error("Live production scene driver disconnected or sent an invalid phase");
        };
        const auto load=[&](const std::wstring& folder,Scene& scene) {
            if(!LoadScenePacket(folder+L"\\scene.packet",&scene,&error))
                throw std::runtime_error(Utf8(error));
            if(scene.width!=1920 || scene.height!=1080)
                throw std::runtime_error("Live production scene has an unexpected logical viewport");
            const auto validate=[](std::vector<std::uint64_t> keys,const std::vector<HitRecord>& records) {
                std::vector<std::uint64_t> actual;
                for(const auto& record:records)actual.push_back(record.controlKey);
                std::sort(keys.begin(),keys.end());std::sort(actual.begin(),actual.end());
                if(std::adjacent_find(keys.begin(),keys.end())!=keys.end() ||
                   std::adjacent_find(actual.begin(),actual.end())!=actual.end() ||
                   !std::includes(keys.begin(),keys.end(),actual.begin(),actual.end()))
                    throw std::runtime_error("Prepared production targets differ from the live Lua context");
            };
            validate(currentKeys(),scene.hits);validate(scrollKeys(),scene.scrolls);
            if(active() && (scene.hits.empty() || scene.scrolls.empty()))
                throw std::runtime_error("Active production scene is missing click or scroll targets");
            if(!active() && (!scene.textures.empty() || !scene.sprites.empty() || !scene.hits.empty() || !scene.scrolls.empty()))
                throw std::runtime_error("Closed production context must contribute no paint or input");
        };
        const auto render=[&](const Scene& scene,const std::wstring& folder) {
            const auto png=folder+L"\\popup.png";
            if(GetFileAttributesW(png.c_str())!=INVALID_FILE_ATTRIBUTES)
                throw std::runtime_error("Live production refuses to overwrite retained pixels");
            if(!RenderToPng(scene,png,&error))throw std::runtime_error(Utf8(error));
            return png;
        };
        std::printf("UI_WINDOW_SCENE_REQUEST=%u|%d|%s\n",sequence,turn,Utf8(initial).c_str());
        acknowledge("READY|"+std::to_string(sequence));
        if(snapshot()!=shown)throw std::runtime_error("Live UI state changed while preparing the initial scene");
        Scene scene;load(presentation,scene);const auto png=render(scene,presentation);
        BitmapWindow window;
        if(!window.Create(scene,png,L"ZeroSis' Engine Modernization - BNW production",1000,700,false,&error) ||
           !window.EnableProductionPointerInput(true,&error,false))throw std::runtime_error(Utf8(error));
        const auto capture=[&](const std::string& phase,const std::wstring& path) {
            if(!window.CaptureFrame(path,&error))throw std::runtime_error(Utf8(error));
            BitmapFrameInfo info{};
            if(!window.GetFrameInfo(&info,&error))throw std::runtime_error(Utf8(error));
            const char* device=info.deviceKind==BitmapDeviceKind::Hardware?"hardware":
                info.deviceKind==BitmapDeviceKind::Warp?"warp":"unknown";
            std::printf("UI_WINDOW_FRAME=%u|%s|%llu|%lu|%u|%u|%llu|%llu|%ld|%s|%u|%u|%s\n",
                sequence,phase.c_str(),static_cast<unsigned long long>(reinterpret_cast<std::uintptr_t>(window.NativeHandle())),
                static_cast<unsigned long>(GetCurrentThreadId()),info.clientWidth,info.clientHeight,
                static_cast<unsigned long long>(info.renderCount),static_cast<unsigned long long>(info.presentCount),
                static_cast<long>(info.lastPresentResult),device,info.lastPresentOccluded?1u:0u,
                IsWindowVisible(window.NativeHandle())?1u:0u,Utf8(path).c_str());
            std::printf("UI_PRODUCTION_WINDOW_DEVICE=%u|%s|%llu\n",sequence,phase.c_str(),
                static_cast<unsigned long long>(info.deviceIdentity));
        };
        window.Show(true);
        if(!window.PumpMessages(&error))throw std::runtime_error(Utf8(error));
        capture("initial",presentation+L"\\frame-initial.png");
        if(!window.ResizeClient(900,600,&error) || !window.PumpMessages(&error))throw std::runtime_error(Utf8(error));
        capture("resized",presentation+L"\\frame-resized.png");
        if(snapshot()!=shown)throw std::runtime_error("Live native window creation changed the official context");
        std::printf("UI_WINDOW_STATE_UNCHANGED=%u|before-input\n",sequence);
        unsigned batch=0,revision=0,delivered=0,accepted=0,stale=0;
        auto current=shown;auto currentInput=initial;auto currentPng=png;
        const auto oldHandle=window.NativeHandle();
        const auto reconcileClear=[&](const BitmapInputEvent& event) {
            if(event.kind!=BitmapInputKind::PointerMove || event.controlKey || !active())return false;
            // Leaving all controls is independent of the replaced geometry.
            // It must not be lost with a stale click or a stale nonzero hover.
            const bool consumed=dispatch(event);if(consumed)++accepted;
            std::printf("UI_PRODUCTION_WINDOW_RECONCILE_CLEAR=%u|%u|%llu|%llu|%u\n",sequence,batch,
                static_cast<unsigned long long>(event.sceneGeneration),
                static_cast<unsigned long long>(window.SceneGeneration()),consumed?1u:0u);
            return true;
        };
        std::function<void()> refresh;
        refresh=[&]() {
            if(++revision>128)throw std::runtime_error("Live production refresh bound exceeded");
            currentInput=freeze(revision);current=snapshot();
            const auto folder=presentation+L"-live-"+std::to_wstring(revision);
            std::printf("UI_PRODUCTION_WINDOW_UPDATE=%u|%d|%u|%u|%s\n",sequence,turn,revision,active()?1u:0u,Utf8(currentInput).c_str());
            acknowledge("UPDATE|"+std::to_string(sequence)+"|"+std::to_string(revision));
            if(snapshot()!=current)throw std::runtime_error("Production state changed while preparing its replacement");
            Scene next;load(folder,next);const auto nextPng=render(next,folder);
            const auto before=window.SceneGeneration();BitmapFrameInfo beforeFrame{};
            if(!window.GetFrameInfo(&beforeFrame,&error))throw std::runtime_error(Utf8(error));
            if(!window.UpdateSceneRetainingInput(next,nextPng,&error))throw std::runtime_error(Utf8(error));
            bool needsClear=false;BitmapInputEvent clearEvent{};
            std::vector<BitmapInputEvent> pending;
            if(!window.DrainInputs(&pending,&error))throw std::runtime_error(Utf8(error));
            for(const auto& event:pending){
                ++delivered;++stale;
                std::printf("UI_PRODUCTION_WINDOW_STALE=%u|%u|%u|%llu|%llu|%llu|%u\n",sequence,batch,
                    static_cast<unsigned>(event.kind),static_cast<unsigned long long>(event.controlKey),
                    static_cast<unsigned long long>(event.sceneGeneration),static_cast<unsigned long long>(before+1),event.virtualKey);
                if(event.kind==BitmapInputKind::PointerMove && !event.controlKey){needsClear=true;clearEvent=event;}
            }
            const auto after=window.SceneGeneration();
            if(window.NativeHandle()!=oldHandle || after!=before+1)
                throw std::runtime_error("Live production refresh lost its window or scene identity");
            capture("live-"+std::to_string(revision),folder+L"\\frame-live.png");
            BitmapFrameInfo afterFrame{};
            if(!window.GetFrameInfo(&afterFrame,&error))throw std::runtime_error(Utf8(error));
            if(!beforeFrame.deviceIdentity || beforeFrame.deviceIdentity!=afterFrame.deviceIdentity)
                throw std::runtime_error("Live production refresh replaced its D3D11 device");
            std::printf("UI_PRODUCTION_WINDOW_REFRESH=%u|%u|%u|%llu|%llu|%llu|%llu|%s\n",sequence,batch,revision,
                static_cast<unsigned long long>(before),static_cast<unsigned long long>(after),
                static_cast<unsigned long long>(beforeFrame.deviceIdentity),static_cast<unsigned long long>(afterFrame.deviceIdentity),
                Utf8(nextPng).c_str());
            currentPng=nextPng;
            if(needsClear && reconcileClear(clearEvent) && snapshot()!=current)refresh();
        };
        while(active()) {
            if(++batch>32)throw std::runtime_error("Live production input batch bound exceeded");
            RECT client{};
            if(!GetClientRect(window.NativeHandle(),&client))throw std::runtime_error("Cannot inspect live production client");
            std::printf("UI_PRODUCTION_WINDOW_READY=%u|%u|%llu|%llu|%lu|%ld|%ld|%s|%s\n",sequence,batch,
                static_cast<unsigned long long>(window.SceneGeneration()),
                static_cast<unsigned long long>(reinterpret_cast<std::uintptr_t>(window.NativeHandle())),
                static_cast<unsigned long>(GetCurrentThreadId()),client.right,client.bottom,
                Utf8(currentInput).c_str(),Utf8(currentPng).c_str());
            acknowledge("STEP|"+std::to_string(sequence)+"|"+std::to_string(batch));
            if(!window.PumpMessages(&error))throw std::runtime_error(Utf8(error));
            std::vector<BitmapInputEvent> inputs;
            if(!window.DrainInputs(&inputs,&error))throw std::runtime_error(Utf8(error));
            if(inputs.empty())throw std::runtime_error("Live production batch delivered no eligible native input");
            for(const auto& event:inputs) {
                ++delivered;
                if(!event.sceneGeneration)throw std::runtime_error("Live production input has no scene generation");
                if(event.sceneGeneration!=window.SceneGeneration()) {
                    ++stale;
                    std::printf("UI_PRODUCTION_WINDOW_STALE=%u|%u|%u|%llu|%llu|%llu|%u\n",sequence,batch,
                        static_cast<unsigned>(event.kind),static_cast<unsigned long long>(event.controlKey),
                        static_cast<unsigned long long>(event.sceneGeneration),static_cast<unsigned long long>(window.SceneGeneration()),event.virtualKey);
                    if(reconcileClear(event) && snapshot()!=current)refresh();
                    continue;
                }
                std::printf("UI_PRODUCTION_WINDOW_EVENT=%u|%u|%u|%llu|%u|%.17g|%llu\n",sequence,batch,
                    static_cast<unsigned>(event.kind),static_cast<unsigned long long>(event.controlKey),event.virtualKey,
                    static_cast<double>(event.scrollDelta),static_cast<unsigned long long>(event.sceneGeneration));
                if(dispatch(event))++accepted;
                if(snapshot()!=current)refresh();
            }
            std::printf("UI_PRODUCTION_WINDOW_BATCH=%u|%u|%zu|%u|%u|%u|%llu\n",sequence,batch,inputs.size(),accepted,stale,
                active()?1u:0u,static_cast<unsigned long long>(window.SceneGeneration()));
            if(active() && !window.IsOpen())throw std::runtime_error("Native production window closed without releasing its context");
        }
        if(!currentKeys().empty() || !scrollKeys().empty())throw std::runtime_error("Closed production retains input targets");
        std::printf("UI_PRODUCTION_WINDOW_CLOSED=%u|%llu|%llu\n",sequence,
            static_cast<unsigned long long>(reinterpret_cast<std::uintptr_t>(window.NativeHandle())),
            static_cast<unsigned long long>(window.SceneGeneration()));
        acknowledge("CLOSED_INPUTS|"+std::to_string(sequence));
        if(!window.PumpMessages(&error))throw std::runtime_error(Utf8(error));
        std::vector<BitmapInputEvent> closedInputs;
        if(!window.DrainInputs(&closedInputs,&error))throw std::runtime_error(Utf8(error));
        unsigned closedAccepted=0;
        for(const auto& event:closedInputs){
            const bool consumed=dispatch(event);if(consumed)++closedAccepted;
            std::printf("UI_PRODUCTION_WINDOW_CLOSED_EVENT=%u|%u|%llu|%u|%.17g|%llu|%u\n",sequence,
                static_cast<unsigned>(event.kind),static_cast<unsigned long long>(event.controlKey),event.virtualKey,
                static_cast<double>(event.scrollDelta),static_cast<unsigned long long>(event.sceneGeneration),consumed?1u:0u);
        }
        if(closedInputs.size()!=1 || closedInputs[0].kind!=BitmapInputKind::KeyDown || closedInputs[0].virtualKey!=VK_ESCAPE ||
           closedAccepted || active() || snapshot()!=current)
            throw std::runtime_error("Closed live production accepted input or changed its retained state");
        std::printf("UI_PRODUCTION_WINDOW_COMPLETE=%u|%u|%u|%u|%u|%zu|%u|%llu|owner-thread\n",sequence,batch,delivered,accepted,stale,
            closedInputs.size(),closedAccepted,static_cast<unsigned long long>(window.SceneGeneration()));
    }

    static void Serve(unsigned sequence,int turn,const std::wstring& directory,
                      const std::string& shown,const std::vector<std::uint64_t>& liveKeys,
                      const std::function<std::string()>& snapshot,
                      const std::function<bool()>& active,
                      const std::function<bool(const ZeroSisPresentation::BitmapInputEvent&)>& dispatch,
                      bool displayResize=false,bool refreshClosed=false,
                      const std::function<std::vector<std::uint64_t>()>& currentKeys={},
                      bool productionFixture=false,std::uint64_t selectedControl=0,bool researchFixture=false) {
        using namespace ZeroSisPresentation;
        if(refreshClosed && (!displayResize || !currentKeys))
            throw std::logic_error("Closed scene refresh requires GPU display and live input target inspection");
        if(productionFixture && (!selectedControl || !displayResize || !refreshClosed))
            throw std::logic_error("Production input fixture requires its selected control and GPU closed scene refresh");
        const auto input=directory+L"\\ui-popup-"+std::to_wstring(sequence)+(productionFixture?L"-window.json":L"-shown.json");
        const auto presentation=directory+L"\\presentation-popup-"+std::to_wstring(sequence);
        std::printf("UI_WINDOW_SCENE_REQUEST=%u|%d|%s\n",sequence,turn,Utf8(input).c_str());
        char ready[64]={};
        if(!std::fgets(ready,sizeof(ready),stdin) ||
           std::string(ready)!="READY|"+std::to_string(sequence)+"\n")
            throw std::runtime_error("UI window scene preparer disconnected or sent an invalid sequence");
        if(snapshot()!=shown)throw std::runtime_error("UI state changed while waiting for scene preparation");
        Scene scene;std::wstring error;
        if(!LoadScenePacket(presentation+L"\\scene.packet",&scene,&error))
            throw std::runtime_error(Utf8(error));
        std::vector<std::uint64_t> hitKeys;
        for(const auto& hit:scene.hits)hitKeys.push_back(hit.controlKey);
        auto keys=liveKeys;
        std::sort(keys.begin(),keys.end());std::sort(hitKeys.begin(),hitKeys.end());
        if(keys.empty() || hitKeys.empty() ||
           std::adjacent_find(keys.begin(),keys.end())!=keys.end() ||
           std::adjacent_find(hitKeys.begin(),hitKeys.end())!=hitKeys.end() ||
           (productionFixture?(!std::includes(keys.begin(),keys.end(),hitKeys.begin(),hitKeys.end()) ||
                !std::binary_search(hitKeys.begin(),hitKeys.end(),selectedControl)):keys!=hitKeys))
            throw std::runtime_error("Scene hit keys differ from current official Lua input targets");
        const auto png=presentation+L"\\popup.png";
        if(GetFileAttributesW(png.c_str())!=INVALID_FILE_ATTRIBUTES)
            throw std::runtime_error("UI window refuses to overwrite a retained PNG");
        if(!RenderToPng(scene,png,&error))throw std::runtime_error(Utf8(error));
        BitmapWindow window;
        if(!window.Create(scene,png,researchFixture?L"ZeroSis' Engine Modernization - BNW research":productionFixture?L"ZeroSis' Engine Modernization - BNW production":
                         L"ZeroSis' Engine Modernization - BNW ranking",1000,700,false,&error))
            throw std::runtime_error(Utf8(error));
        const auto capture=[&](const char* phase,const std::wstring& path) {
            // A sandbox desktop can remain occluded. Retain its exact HRESULT
            // without claiming pixels appeared on the user's desktop.
            if(!window.PumpMessages(&error))throw std::runtime_error(Utf8(error));
            if(!window.CaptureFrame(path,&error))throw std::runtime_error(Utf8(error));
            BitmapFrameInfo info{};
            if(!window.GetFrameInfo(&info,&error))throw std::runtime_error(Utf8(error));
            const char* device=info.deviceKind==BitmapDeviceKind::Hardware?"hardware":
                info.deviceKind==BitmapDeviceKind::Warp?"warp":"unknown";
            std::printf("UI_WINDOW_FRAME=%u|%s|%llu|%lu|%u|%u|%llu|%llu|%ld|%s|%u|%u|%s\n",
                sequence,phase,
                static_cast<unsigned long long>(reinterpret_cast<std::uintptr_t>(window.NativeHandle())),
                static_cast<unsigned long>(GetCurrentThreadId()),info.clientWidth,info.clientHeight,
                static_cast<unsigned long long>(info.renderCount),static_cast<unsigned long long>(info.presentCount),
                static_cast<long>(info.lastPresentResult),device,info.lastPresentOccluded?1u:0u,
                IsWindowVisible(window.NativeHandle())?1u:0u,Utf8(path).c_str());
        };
        if(displayResize) {
            const auto objectName=[](HANDLE handle) {
                wchar_t name[256]={};DWORD bytes=0;
                if(!GetUserObjectInformationW(handle,UOI_NAME,name,sizeof(name),&bytes))
                    throw std::runtime_error("Cannot inspect owned UI desktop context");
                const auto result=Utf8(name);
                if(result.empty() || result.find_first_of("|\r\n")!=std::string::npos)
                    throw std::runtime_error("Invalid owned UI desktop context name");
                return result;
            };
            DWORD session=0;
            if(!ProcessIdToSessionId(GetCurrentProcessId(),&session))
                throw std::runtime_error("Cannot inspect owned UI process session");
            std::printf("UI_WINDOW_DISPLAY_CONTEXT=%u|%lu|%s|%s\n",sequence,
                static_cast<unsigned long>(session),objectName(GetProcessWindowStation()).c_str(),
                objectName(GetThreadDesktop(GetCurrentThreadId())).c_str());
            window.Show(true);
            capture("initial",presentation+L"\\frame-initial.png");
            if(!window.ResizeClient(900,600,&error) || !window.PumpMessages(&error))
                throw std::runtime_error(Utf8(error));
            capture("resized",presentation+L"\\frame-resized.png");
        }
        if(snapshot()!=shown)throw std::runtime_error("Native rendering/window creation changed live UI state");
        std::printf("UI_WINDOW_STATE_UNCHANGED=%u|before-input\n",sequence);
        RECT client{};
        if(!GetClientRect(window.NativeHandle(),&client))throw std::runtime_error("Cannot inspect UI window client bounds");
        std::printf("UI_WINDOW_READY=%u|%llu|%lu|%ld|%ld\n",sequence,
                    static_cast<unsigned long long>(reinterpret_cast<std::uintptr_t>(window.NativeHandle())),
                    static_cast<unsigned long>(GetCurrentThreadId()),client.right,client.bottom);
        // Queue the entire automated batch before pumping, so late-input
        // rejection does not depend on scheduler timing.
        if(!std::fgets(ready,sizeof(ready),stdin) ||
           std::string(ready)!="INPUTS|"+std::to_string(sequence)+"\n")
            throw std::runtime_error("UI window input batch was not committed by its owned driver");
        const ULONGLONG start=GetTickCount64();unsigned delivered=0,accepted=0;
        while(active()) {
            if(GetTickCount64()-start>30000)throw std::runtime_error("UI window input timed out");
            // Capture the epoch before pumping: WM_CLOSE can destroy the HWND
            // while its CloseRequest still belongs to this valid scene batch.
            const auto inputGeneration=window.SceneGeneration();
            if(!window.PumpMessages(&error))throw std::runtime_error(Utf8(error));
            std::vector<BitmapInputEvent> events;
            if(!window.DrainInputs(&events,&error))throw std::runtime_error(Utf8(error));
            for(const auto& event:events) {
                ++delivered;
                if(!event.sceneGeneration || event.sceneGeneration!=inputGeneration)
                    throw std::runtime_error("Refusing to dispatch input captured from an older UI scene");
                if(productionFixture && active() && (event.kind!=BitmapInputKind::ControlClick || event.controlKey!=selectedControl))
                    throw std::runtime_error("Production unit fixture refuses unrelated input before its selected unit callback");
                if(dispatch(event))++accepted;
            }
            if(!active())break;
            if(!window.IsOpen())throw std::runtime_error("UI window closed without releasing the official popup");
            // Briefly wait for owned messages without advancing GameCore.
            MsgWaitForMultipleObjects(0,nullptr,FALSE,10,QS_ALLINPUT);
        }
        if(accepted!=1)throw std::runtime_error("Owned popup fixture requires exactly one accepted closing input");
        if(refreshClosed) {
            const auto closed=snapshot();
            if(active() || !currentKeys().empty())
                throw std::runtime_error("Official closed context still exposes active input targets");
            const auto closedInput=directory+L"\\ui-popup-"+std::to_wstring(sequence)+L"-closed.json";
            const auto closedPresentation=presentation+L"-closed";
            std::printf("UI_WINDOW_REFRESH_REQUEST=%u|%d|%s\n",sequence,turn,Utf8(closedInput).c_str());
            if(!std::fgets(ready,sizeof(ready),stdin) ||
               std::string(ready)!="REFRESH|"+std::to_string(sequence)+"\n")
                throw std::runtime_error("UI closed scene preparer disconnected or sent an invalid sequence");
            if(snapshot()!=closed || active() || !currentKeys().empty())
                throw std::runtime_error("Closed UI state changed during refresh preparation");
            Scene next;
            if(!LoadScenePacket(closedPresentation+L"\\scene.packet",&next,&error))
                throw std::runtime_error(Utf8(error));
            if(next.width!=1920 || next.height!=1080 || !next.textures.empty() ||
               !next.sprites.empty() || !next.hits.empty())
                throw std::runtime_error("A dequeued popup must contribute no paint or input targets");
            const auto nextPng=closedPresentation+L"\\popup.png";
            if(GetFileAttributesW(nextPng.c_str())!=INVALID_FILE_ATTRIBUTES)
                throw std::runtime_error("UI refresh refuses to overwrite a retained PNG");
            if(!RenderToPng(next,nextPng,&error))throw std::runtime_error(Utf8(error));
            const auto oldGeneration=window.SceneGeneration();const auto oldHandle=window.NativeHandle();
            BitmapFrameInfo beforeRefresh{};
            if(!window.GetFrameInfo(&beforeRefresh,&error))throw std::runtime_error(Utf8(error));
            if(!window.UpdateScene(next,nextPng,&error))throw std::runtime_error(Utf8(error));
            const auto generation=window.SceneGeneration();
            if(!oldGeneration || generation!=oldGeneration+1 || window.NativeHandle()!=oldHandle)
                throw std::runtime_error("UI refresh lost HWND identity or its scene generation");
            capture("closed",closedPresentation+L"\\frame-closed.png");
            BitmapFrameInfo afterRefresh{};
            if(!window.GetFrameInfo(&afterRefresh,&error))throw std::runtime_error(Utf8(error));
            if(!beforeRefresh.deviceIdentity || beforeRefresh.deviceIdentity!=afterRefresh.deviceIdentity)
                throw std::runtime_error("UI refresh replaced its live D3D11 device");
            std::printf("UI_WINDOW_REFRESH_DEVICE=%u|%llu|%llu\n",sequence,
                static_cast<unsigned long long>(beforeRefresh.deviceIdentity),
                static_cast<unsigned long long>(afterRefresh.deviceIdentity));
            if(!GetClientRect(window.NativeHandle(),&client))throw std::runtime_error("Cannot inspect refreshed client bounds");
            std::printf("UI_WINDOW_REFRESH_READY=%u|%llu|%lu|%llu|%llu|%ld|%ld|%s\n",sequence,
                static_cast<unsigned long long>(reinterpret_cast<std::uintptr_t>(window.NativeHandle())),
                static_cast<unsigned long>(GetCurrentThreadId()),static_cast<unsigned long long>(oldGeneration),
                static_cast<unsigned long long>(generation),client.right,client.bottom,Utf8(nextPng).c_str());
            if(!std::fgets(ready,sizeof(ready),stdin) ||
               std::string(ready)!="REFRESH_INPUTS|"+std::to_string(sequence)+"\n")
                throw std::runtime_error("UI refresh input batch was not committed by its owned driver");
            if(!window.PumpMessages(&error))throw std::runtime_error(Utf8(error));
            std::vector<BitmapInputEvent> events;
            if(!window.DrainInputs(&events,&error))throw std::runtime_error(Utf8(error));
            unsigned refreshAccepted=0;
            for(const auto& event:events) {
                if(event.sceneGeneration!=generation)
                    throw std::runtime_error("Refreshed input batch retained an old scene generation");
                if(dispatch(event))++refreshAccepted;
            }
            if(events.size()!=1 || refreshAccepted || snapshot()!=closed || active() || !currentKeys().empty())
                throw std::runtime_error("Dequeued popup consumed an old control click or changed its closed state");
            std::printf("UI_WINDOW_REFRESH_COMPLETE=%u|%zu|%u|%llu|owner-thread\n",sequence,
                events.size(),refreshAccepted,static_cast<unsigned long long>(generation));
            std::printf("UI_WINDOW_REFRESH_STATE_UNCHANGED=%u|after-refresh\n",sequence);
        }
        std::printf("UI_WINDOW_COMPLETE=%u|%u|%u|owner-thread\n",sequence,delivered,accepted);
        // RAII destroys the HWND and all COM ownership on this same thread.
    }
};
}
