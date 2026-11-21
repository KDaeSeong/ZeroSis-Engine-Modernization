#pragma once

#include "BitmapRenderer.h"
#include "BitmapPointerPress.h"

#include <Windows.h>

#include <cstdint>
#include <functional>
#include <string>
#include <vector>

namespace ZeroSisPresentation {

enum class BitmapInputKind : std::uint32_t {
    KeyDown=0,
    ControlClick=1,
    CloseRequest=2,
    PointerMove=3,
    Scroll=4,
    ControlRightClick=5,
    TextInput=6,
    WorldWheel=7,
    ControlDrag=8,
};

struct BitmapInputEvent {
    BitmapInputKind kind;
    std::uint64_t controlKey;
    std::uint32_t virtualKey;
    float logicalX;
    float logicalY;
    std::uint64_t sceneGeneration;
    float scrollDelta=0.0f;
    std::uint32_t modifiers=0;
    std::uint32_t unicodeScalar=0;
    std::uint64_t editorOwner=0;
    std::uint64_t textFocusEpoch=0;
    std::int32_t wheelDelta=0;
    // Nonzero only for a physical press. Origin remains the logical down point
    // even when several move events coalesce before their owner drains them.
    std::uint64_t pointerPressId=0;
    float pointerPressX=0.0f,pointerPressY=0.0f;
};

struct BitmapTextInputState {
    std::uint64_t editorOwner=0;
    std::uint64_t focusEpoch=0;
    bool enabled=false;
};

struct BitmapDisplayRect {
    float left;
    float top;
    float right;
    float bottom;
};

enum class BitmapDeviceKind : std::uint32_t {
    Unknown,
    Hardware,
    Warp,
};

struct BitmapFrameInfo {
    std::uint32_t clientWidth;
    std::uint32_t clientHeight;
    std::uint64_t renderCount;
    std::uint64_t presentCount;
    std::int32_t lastPresentResult;
    BitmapDeviceKind deviceKind;
    std::uint64_t deviceIdentity;
    bool lastPresentOccluded;
};

// Owns one HWND and its thread-local message handling. It never calls SDK/Lua callbacks.
// Each instance is one-shot: Create may be attempted once (after argument validation).
// Create, all instance method calls, and destruction must occur on that same owner thread.
// UpdateScene requires pending input to be drained; consumers must ignore events whose
// sceneGeneration differs from SceneGeneration after changing the active scene.
// Strict callers must quiesce input producers while updating and resume only after
// drawing the new scene. The pump barrier and millisecond message cutoff do not
// establish old/new provenance for uncoordinated physical input at the commit boundary.
// UpdateSceneRetainingInput commits while retaining inputs dispatched before commit with
// their original generation for the host to drain afterward. Its bounded message pump cannot starve under
// continuous producers; the millisecond cutoff remains best-effort and cannot prove exact
// physical input provenance at the commit boundary.
class BitmapWindow final {
public:
    struct DisplaySettings final {
        std::uint32_t width=1280,height=720;
        bool fullscreen=false,vsync=true;
    };
    BitmapWindow();
    ~BitmapWindow();
    BitmapWindow(const BitmapWindow&) = delete;
    BitmapWindow& operator=(const BitmapWindow&) = delete;

    bool Create(const Scene& scene, const std::wstring& renderedPng,
                const std::wstring& title, std::uint32_t clientWidth,
                std::uint32_t clientHeight, bool show, std::wstring* error);
    bool UpdateScene(const Scene& scene, const std::wstring& renderedPng, std::wstring* error);
    bool UpdateSceneRetainingInput(const Scene& scene, const std::wstring& renderedPng,
                                   std::wstring* error);
    // Compose on the window's D3D11 device without an intermediate scene PNG.
    // A failed candidate leaves the committed frame and input generation intact.
    bool CreateGpuScene(const Scene& scene, const std::wstring& title,
                        std::uint32_t clientWidth, std::uint32_t clientHeight,
                        bool show, std::wstring* error);
    bool UpdateGpuScene(const Scene& scene, std::wstring* error);
    bool UpdateGpuSceneRetainingInput(const Scene& scene, std::wstring* error);
    using GpuFramePainter = std::function<bool(ID3D11Device*, ID3D11DeviceContext*,
                                               ID3D11Texture2D*, std::wstring*)>;
    // The painter fully paints a private 1920x1080 target on the owner thread,
    // even before Create. Borrowed interfaces must not be retained. Only a
    // successful prepared commit publishes the pixels and consumes the target.
    bool PrepareGpuFrame(const GpuFramePainter& painter, std::wstring* error);
    bool OverlayPreparedGpuFrame(const Scene& scene, std::wstring* error);
    bool CapturePreparedGpuFrame(const std::wstring& png, std::wstring* error);
    bool CreatePreparedGpuScene(const Scene& scene, const std::wstring& title,
                                std::uint32_t clientWidth, std::uint32_t clientHeight,
                                bool show, std::wstring* error);
    bool UpdatePreparedGpuSceneRetainingInput(const Scene& scene, std::wstring* error,
                                              std::uint64_t editorOwner=0,
                                              std::uint64_t textFocusEpoch=0);
    // Visual-only animation: identical input geometry keeps its generation and
    // queued events. Does not dispatch messages, change the cutoff, or call SDK.
    bool RefreshPreparedGpuFrame(const Scene& scene, std::wstring* error);
    std::uint64_t SceneGeneration() const;
    void Show(bool visible);
    bool ResizeClient(std::uint32_t width, std::uint32_t height, std::wstring* error);
    // Actual owned-window settings. A failed application attempts to restore
    // the preceding display mode; callers must not persist a failed request.
    bool ReadDisplaySettings(DisplaySettings* settings,std::wstring* error) const;
    bool ApplyDisplaySettings(const DisplaySettings& settings,DisplaySettings* actual,std::wstring* error);
    bool PumpMessages(std::wstring* error);
    bool DrainInputs(std::vector<BitmapInputEvent>* events, std::wstring* error);
    // Read the current physical pointer without enqueuing input or changing
    // capture. Disabled/outside/failed samples return a neutral pointer event.
    // A wrong-thread sample has generation zero and cannot be dispatched.
    BitmapInputEvent CurrentPointerInput() const;
    bool EnableProductionPointerInput(bool enabled, std::wstring* error,
                                     bool automaticLeaveTracking=true);
    // Explicitly opted-in UI tracks only. No world gesture is synthesized.
    bool EnableControlDragInput(bool enabled,std::wstring* error);
    bool HasControlDragCapture() const;
    // World input adds explicit navigation keys and defers WM_CLOSE until the
    // owner has drained commands and saved. Popup input behavior stays intact.
    bool EnableGameplayInput(bool enabled, std::wstring* error);
    // Bind world wheel input to this committed scene; nullptr relinquishes it.
    // ScrollPanel viewports and retained UI hit regions always own input first.
    bool SetWorldWheelViewport(const BitmapDisplayRect* viewport, std::wstring* error);
    // Opt in only while a text-owning UI context is active. The native queue
    // transports committed Unicode scalars; the context owns EditBox focus.
    // Windows retains its default IME composition/candidate presentation.
    bool EnableTextInput(bool enabled, std::wstring* error, std::uint64_t editorOwner=0);
    bool GetTextInputState(BitmapTextInputState* state, std::wstring* error) const;
    bool CaptureFrame(const std::wstring& png, std::wstring* error);
    bool GetFrameInfo(BitmapFrameInfo* info, std::wstring* error) const;
    bool IsOpen() const;
    HWND NativeHandle() const;

    static BitmapDisplayRect ComputeDisplayRect(std::uint32_t clientWidth,
                                                std::uint32_t clientHeight);
    static bool MapClientPointToLogical(std::uint32_t clientWidth,
                                       std::uint32_t clientHeight,
                                       std::int32_t clientX, std::int32_t clientY,
                                       float* logicalX, float* logicalY);

private:
#if defined(ZEROSIS_BITMAP_WINDOW_DIAGNOSTICS)
    friend struct BitmapWindowReentryTestAccess;
#endif
    static LRESULT CALLBACK WindowProc(HWND hwnd, UINT message, WPARAM wParam, LPARAM lParam);
    LRESULT HandleMessage(UINT message, WPARAM wParam, LPARAM lParam);
    bool LoadBitmap(const std::wstring& path, std::wstring* error);
    bool CreateImpl(const Scene& scene, const std::wstring* renderedPng,
                    const std::wstring& title, std::uint32_t clientWidth,
                    std::uint32_t clientHeight, bool show, bool preparedGpu, std::wstring* error);
    bool UpdateSceneImpl(const Scene& scene, const std::wstring* renderedPng,
                          bool retainPendingInput, bool preparedGpu, std::wstring* error,
                          std::uint64_t editorOwner=0, std::uint64_t textFocusEpoch=0);
    bool InitializeOwner(std::wstring* error);
    bool EnsureGpuDevice(std::wstring* error);
    bool EnsureRenderTarget(std::wstring* error);
    bool RenderFrame(const std::wstring* capturePng, std::wstring* error);
    void LatchRenderFailure(const std::wstring& error);
    void ReleaseRenderTarget();
    void QueueKey(std::uint32_t virtualKey);
    void QueueUtf16Character(std::uint32_t codeUnit);
    void QueueTextScalar(std::uint32_t scalar);
    void ResetTextInput(bool cancelComposition);
    void InvalidateTextFocus(bool cancelComposition, bool discardQueuedMessages);
    bool IsTextInputMessageCurrent() const;
    void QueueClick(BitmapInputKind kind, std::int32_t x, std::int32_t y,
                    std::uint64_t generation, bool startedOnUi, std::uint32_t modifiers=0,
                    const BitmapPointerPress* press=nullptr);
    void CancelPointerPresses();
    void QueuePointerMove(std::int32_t x, std::int32_t y);
    void QueueControlDrag(std::int32_t x,std::int32_t y);
    void QueueScroll(std::int32_t x, std::int32_t y, std::int32_t wheelDelta);
    void QueueClose();
    std::uint64_t HitTestLogicalPoint(float logicalX, float logicalY, bool* uiHit=nullptr) const;
    std::uint64_t HitTestScrollLogicalPoint(float logicalX, float logicalY, bool* viewportHit=nullptr) const;
    bool OnOwnerThread(std::wstring* error) const;
    bool IsInputMessageCurrent() const;

    HWND hwnd_;
    DWORD ownerThreadId_;
    std::uint32_t logicalWidth_;
    std::uint32_t logicalHeight_;
    std::uint32_t dpi_;
    bool closing_;
    bool closeQueued_;
    bool inWindowProc_;
    bool queueOverflow_;
    bool productionPointerInputEnabled_;
    bool gameplayInputEnabled_;
    bool textInputEnabled_;
    bool nativeTextFocused_;
    bool imeCompositionActive_;
    std::uint16_t pendingHighSurrogate_;
    std::uint64_t editorOwner_;
    std::uint64_t textFocusEpoch_;
    DWORD textInputCutoffTick_;
    bool textInputCutoffActive_;
    bool automaticLeaveTracking_;
    bool trackingMouseLeave_;
    using PointerPress=BitmapPointerPress;
    std::uint64_t pointerPressSequence_=0;
    bool controlDragInputEnabled_=false;
    PointerPress leftPress_;
    PointerPress rightPress_;
    bool comInitialized_;
    bool creationAttempted_;
    std::uint64_t sceneGeneration_;
    BitmapDisplayRect worldWheelViewport_{};
    std::uint64_t worldWheelGeneration_=0;
    DWORD inputCutoffTick_;
    bool inputCutoffActive_;
    std::vector<HitRecord> hits_;
    std::vector<HitRecord> scrolls_;
    PixelHitMap pixelHits_;
    std::vector<BitmapInputEvent> pending_;
    struct Impl;
    Impl* impl_;
};

}  // namespace ZeroSisPresentation
