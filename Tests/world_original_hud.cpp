// Actual WorldViewRenderer software/WIC path. No Host, SDK, window, swap chain,
// terrain package, D3D device, or unit-art package is constructed by this test.
#include "../Source/Presentation/WorldViewRenderer.h"
#include "../Source/Presentation/WorldTerrainRenderer.h"

#include <Windows.h>
#include <wincodec.h>
#include <wrl/client.h>

#include <algorithm>
#include <array>
#include <cmath>
#include <cstdint>
#include <filesystem>
#include <iostream>
#include <limits>
#include <stdexcept>
#include <string>
#include <unordered_set>
#include <utility>
#include <vector>

namespace {
unsigned terrainCalls = 0, gpuTerrainCalls = 0;
}

// These link-only stand-ins fail closed if the production renderer ever enters
// either terrain branch. Every fixture leaves both asset paths empty. They do
// not replace any executed WorldView, rasterization, picking, or WIC code.
namespace ZeroSisPresentation {
bool RenderWorldTerrain(const WorldView&, std::uint32_t, std::uint32_t,
                        std::uint32_t, TerrainFrame*, std::wstring* error) {
    ++terrainCalls;
    if (error) *error = L"Unexpected terrain call in software HUD component test";
    return false;
}
bool RenderWorldTerrainToTexture(const WorldView&, std::uint32_t, std::uint32_t,
                                std::uint32_t, ID3D11Device*, ID3D11DeviceContext*,
                                ID3D11Texture2D*, TerrainFrame*, std::wstring* error) {
    ++gpuTerrainCalls;
    if (error) *error = L"Unexpected GPU terrain call in software HUD component test";
    return false;
}
}

namespace {
using namespace ZeroSisPresentation;
using Microsoft::WRL::ComPtr;
constexpr unsigned Width = 1920, Height = 1080;
constexpr int GridWidth = 31, GridHeight = 21;
constexpr int CentralPlot = 10 * GridWidth + 15;
constexpr int RightEdgePlot = 11 * GridWidth + 26;
unsigned checks = 0, renders = 0, hudCases = 0, fullscreenCases = 0;
unsigned auxiliaryHudCases = 0, wheelCases = 0, wheelChecks = 0;
std::uint64_t pixelRegionsChecked = 0, regionPixelComparisons = 0;

static_assert(sizeof(void*) == 8, "This component test requires the x64 renderer");
static_assert(noexcept(std::declval<WorldCameraZoom&>().ApplyWheelDelta(std::int32_t{})),
              "Raw wheel input must remain noexcept");
static_assert(noexcept(std::declval<WorldCameraZoom&>().ResetWheelRemainder()),
              "Wheel remainder reset must remain noexcept");

void Check(bool value, const char* reason) {
    ++checks;
    if (!value) throw std::runtime_error(reason);
}

void Near(float actual, float expected, const char* reason) {
    Check(std::fabs(actual - expected) < 0.002f, reason);
}

void WheelCheck(bool value, const char* reason) {
    ++wheelChecks; Check(value, reason);
}

void WheelCases() {
    // These tests exercise the actual pure production camera helper. They do
    // not claim that WM_MOUSEWHEEL, viewport ownership, or routing was run.
    {
        ++wheelCases; WorldCameraZoom zoom;
        WheelCheck(zoom.TileWidth() == 56.0f, "Default keyboard zoom scale changed");
        WheelCheck(zoom.ZoomIn() && zoom.TileWidth() == 64.0f, "Keyboard ZoomIn changed");
        WheelCheck(zoom.ZoomOut() && zoom.TileWidth() == 56.0f, "Keyboard ZoomOut changed");
        WheelCheck(!zoom.ApplyWheelDelta(0) && zoom.TileWidth() == 56.0f, "Zero raw wheel input changed scale");
        WheelCheck(zoom.ApplyWheelDelta(120) && zoom.TileWidth() == 64.0f, "Positive raw notch did not zoom in once");
        WheelCheck(zoom.ApplyWheelDelta(-120) && zoom.TileWidth() == 56.0f, "Negative raw notch did not zoom out once");
    }
    {
        ++wheelCases; WorldCameraZoom zoom;
        WheelCheck(!zoom.ApplyWheelDelta(60) && zoom.TileWidth() == 56.0f, "Half a positive notch changed scale");
        WheelCheck(zoom.ApplyWheelDelta(60) && zoom.TileWidth() == 64.0f, "Two positive half-notches were not accumulated");
        WheelCheck(!zoom.ApplyWheelDelta(-60) && zoom.TileWidth() == 64.0f, "Half a negative notch changed scale");
        WheelCheck(zoom.ApplyWheelDelta(-60) && zoom.TileWidth() == 56.0f, "Two negative half-notches were not accumulated");
    }
    {
        ++wheelCases; WorldCameraZoom zoom;
        WheelCheck(!zoom.ApplyWheelDelta(60) && !zoom.ApplyWheelDelta(-60), "Opposite half-notches changed scale");
        WheelCheck(!zoom.ApplyWheelDelta(119) && zoom.TileWidth() == 56.0f, "Canceled remainder leaked into positive input");
        WheelCheck(zoom.ApplyWheelDelta(1) && zoom.TileWidth() == 64.0f, "Positive fraction did not complete at exactly 120");
    }
    {
        ++wheelCases; WorldCameraZoom zoom;
        WheelCheck(!zoom.ApplyWheelDelta(-119) && !zoom.ApplyWheelDelta(118) && !zoom.ApplyWheelDelta(1),
                   "Mixed-sign fractions failed to cancel exactly");
        WheelCheck(!zoom.ApplyWheelDelta(-119) && zoom.TileWidth() == 56.0f, "Canceled remainder leaked into negative input");
        WheelCheck(zoom.ApplyWheelDelta(-1) && zoom.TileWidth() == 48.0f, "Negative fraction did not complete at exactly -120");
    }
    {
        ++wheelCases; WorldCameraZoom zoom;
        WheelCheck(zoom.ApplyWheelDelta(240) && zoom.TileWidth() == 72.0f, "A two-notch packet was reduced to one notch");
        WheelCheck(zoom.ApplyWheelDelta(-360) && zoom.TileWidth() == 48.0f, "A three-notch negative packet changed direction or count");
        WheelCheck(!zoom.ApplyWheelDelta(60), "An incomplete notch changed scale after a multi-notch packet");
        WheelCheck(zoom.ApplyWheelDelta(180) && zoom.TileWidth() == 64.0f, "A complete packet plus retained fraction lost a notch");
        WheelCheck(zoom.ApplyWheelDelta(-300) && zoom.TileWidth() == 48.0f, "A negative packet lost its retained fraction");
        WheelCheck(!zoom.ApplyWheelDelta(60) && zoom.TileWidth() == 48.0f, "Opposite packet remainder did not cancel");
    }
    {
        ++wheelCases; WorldCameraZoom zoom;
        WheelCheck(zoom.ApplyWheelDelta(840) && zoom.TileWidth() == 112.0f, "Raw wheel input did not reach the exact maximum");
        WheelCheck(!zoom.ApplyWheelDelta(180) && zoom.TileWidth() == 112.0f, "Clamped wheel input falsely reported a scale change");
        WheelCheck(!zoom.ApplyWheelDelta(-60), "Maximum clamp retained a consumed whole notch");
        WheelCheck(zoom.ApplyWheelDelta(-120) && zoom.TileWidth() == 104.0f, "Maximum clamp did not consume its integer notches");
    }
    {
        ++wheelCases; WorldCameraZoom zoom;
        WheelCheck(zoom.ApplyWheelDelta(-480) && zoom.TileWidth() == 24.0f, "Raw wheel input did not reach the exact minimum");
        WheelCheck(!zoom.ApplyWheelDelta(-180) && zoom.TileWidth() == 24.0f, "Minimum clamp falsely reported a scale change");
        WheelCheck(!zoom.ApplyWheelDelta(60), "Minimum clamp retained a consumed whole notch");
        WheelCheck(zoom.ApplyWheelDelta(120) && zoom.TileWidth() == 32.0f, "Minimum clamp did not consume its integer notches");
    }
    {
        ++wheelCases; WorldCameraZoom zoom;
        WheelCheck(zoom.ApplyWheelDelta((std::numeric_limits<std::int32_t>::max)()) && zoom.TileWidth() == 112.0f,
                   "INT32_MAX raw input overflowed or missed maximum clamp");
        WheelCheck(!zoom.ApplyWheelDelta(-7), "INT32_MAX did not retain the independent expected remainder 7");
        WheelCheck(zoom.ApplyWheelDelta(-120) && zoom.TileWidth() == 104.0f, "INT32_MAX left latent whole notches");
    }
    {
        ++wheelCases; WorldCameraZoom zoom;
        WheelCheck(zoom.ApplyWheelDelta((std::numeric_limits<std::int32_t>::min)()) && zoom.TileWidth() == 24.0f,
                   "INT32_MIN raw input overflowed or missed minimum clamp");
        WheelCheck(!zoom.ApplyWheelDelta(8), "INT32_MIN did not retain the independent expected remainder -8");
        WheelCheck(zoom.ApplyWheelDelta(120) && zoom.TileWidth() == 32.0f, "INT32_MIN left latent whole notches");
    }
    {
        ++wheelCases; WorldCameraZoom zoom;
        WheelCheck(!zoom.ApplyWheelDelta(119), "Pre-extreme positive fraction changed scale");
        WheelCheck(zoom.ApplyWheelDelta((std::numeric_limits<std::int32_t>::max)()) && zoom.TileWidth() == 112.0f,
                   "Positive remainder plus INT32_MAX overflowed signed accumulation");
        WheelCheck(!zoom.ApplyWheelDelta(-6), "Positive extended sum did not retain expected remainder 6");
        WheelCheck(zoom.ApplyWheelDelta(-120) && zoom.TileWidth() == 104.0f, "Positive extended sum retained latent notches");
    }
    {
        ++wheelCases; WorldCameraZoom zoom;
        WheelCheck(!zoom.ApplyWheelDelta(-119), "Pre-extreme negative fraction changed scale");
        WheelCheck(zoom.ApplyWheelDelta((std::numeric_limits<std::int32_t>::min)()) && zoom.TileWidth() == 24.0f,
                   "Negative remainder plus INT32_MIN overflowed signed accumulation");
        WheelCheck(!zoom.ApplyWheelDelta(7), "Negative extended sum did not retain expected remainder -7");
        WheelCheck(zoom.ApplyWheelDelta(120) && zoom.TileWidth() == 32.0f, "Negative extended sum retained latent notches");
    }
    {
        ++wheelCases; WorldCameraZoom zoom;
        WheelCheck(zoom.ApplyWheelDelta((std::numeric_limits<std::int32_t>::max)()), "Positive extreme did not move from default");
        WheelCheck(zoom.ApplyWheelDelta((std::numeric_limits<std::int32_t>::min)()) && zoom.TileWidth() == 24.0f,
                   "Consecutive opposite extremes overflowed or lost their order");
        WheelCheck(!zoom.ApplyWheelDelta(1), "Opposite extremes did not leave expected remainder -1");
        WheelCheck(zoom.ApplyWheelDelta(120) && zoom.TileWidth() == 32.0f, "Opposite extremes retained latent whole notches");
    }
    {
        ++wheelCases; WorldCameraZoom zoom;
        WheelCheck(!zoom.ApplyWheelDelta(60), "Pre-reset positive half-notch changed scale");
        zoom.ResetWheelRemainder();
        WheelCheck(zoom.TileWidth() == 56.0f && !zoom.ApplyWheelDelta(60), "Reset changed scale or retained the old positive fraction");
        zoom.ResetWheelRemainder(); zoom.ResetWheelRemainder();
        WheelCheck(!zoom.ApplyWheelDelta(-60), "Repeated reset retained a previous positive fraction");
        WheelCheck(zoom.ApplyWheelDelta(-60) && zoom.TileWidth() == 48.0f, "Negative halves failed after remainder reset");
    }
    {
        ++wheelCases; WorldCameraZoom zoom;
        WheelCheck(!zoom.ApplyWheelDelta(-119), "Keyboard-interleaved negative fraction changed scale");
        WheelCheck(zoom.ZoomIn() && zoom.TileWidth() == 64.0f, "Keyboard ZoomIn changed with a pending fraction");
        WheelCheck(zoom.ApplyWheelDelta(-1) && zoom.TileWidth() == 56.0f, "Keyboard ZoomIn discarded a pending negative fraction");
        WheelCheck(!zoom.ApplyWheelDelta(119), "Keyboard-interleaved positive fraction changed scale");
        WheelCheck(zoom.ZoomOut() && zoom.TileWidth() == 48.0f, "Keyboard ZoomOut changed with a pending fraction");
        WheelCheck(zoom.ApplyWheelDelta(1) && zoom.TileWidth() == 56.0f, "Keyboard ZoomOut discarded a pending positive fraction");
    }
}

std::string NarrowError(const std::wstring& error) {
    std::string text;
    for (const wchar_t value : error)
        text.push_back(static_cast<unsigned long>(value) < 128ul ? static_cast<char>(value) : '?');
    return text;
}

void CheckRender(bool result, const std::wstring& error) {
    ++checks;
    if (!result) throw std::runtime_error("Production RenderWorldView failed: " + NarrowError(error));
}

WorldView Fixture() {
    WorldView view{};
    view.gridWidth = GridWidth; view.gridHeight = GridHeight;
    view.turn = 17; view.activePlayer = 0;
    view.wrapX = false; view.wrapY = false;
    view.cameraX = 15; view.cameraY = 10; view.tileWidth = 56.0f;
    view.status = L"Diagnostic status must disappear with the complete original HUD";
    view.plots.reserve(static_cast<std::size_t>(GridWidth) * GridHeight);
    for (int y = 0; y < GridHeight; ++y) for (int x = 0; x < GridWidth; ++x) {
        WorldViewPlot plot{};
        plot.index = y * GridWidth + x; plot.x = x; plot.y = y;
        plot.revealed = true; plot.visible = true;
        plot.terrain = "TERRAIN_GRASS"; plot.continent = 0;
        view.plots.push_back(std::move(plot));
    }
    WorldViewUnit unit{};
    unit.id = 17; unit.owner = 0; unit.x = 15; unit.y = 11;
    unit.moves = 2; unit.damage = 23; unit.selected = true;
    unit.name = L"Selected unit caption"; unit.type = "UNIT_WARRIOR";
    view.units.push_back(std::move(unit));
    WorldViewCity city{};
    city.id = 23; city.owner = 0; city.x = 14; city.y = 10;
    city.name = L"City"; city.rawName = "City";
    view.cities.push_back(std::move(city)); view.selectedCity = 23;
    for (int i = 0; i < 13; ++i)
        view.unitActions.push_back({100 + i, L"Diagnostic action " + std::to_wstring(i)});
    view.unitActionPage = 1;
    return view;
}

void SetHud(WorldView& view, unsigned mask) {
    view.originalTopPanel = (mask & 1u) != 0;
    view.originalUnitPanel = (mask & 2u) != 0;
    view.originalActionInfoPanel = (mask & 4u) != 0;
}

std::vector<unsigned char> ReadPixels(const std::filesystem::path& path) {
    const HRESULT initialized = CoInitializeEx(nullptr, COINIT_MULTITHREADED);
    Check(SUCCEEDED(initialized) || initialized == RPC_E_CHANGED_MODE, "WIC COM initialization failed");
    struct Apartment {
        HRESULT result;
        ~Apartment() { if (SUCCEEDED(result)) CoUninitialize(); }
    } apartment{initialized};
    ComPtr<IWICImagingFactory> factory;
    Check(SUCCEEDED(CoCreateInstance(CLSID_WICImagingFactory, nullptr, CLSCTX_INPROC_SERVER,
          IID_PPV_ARGS(&factory))), "WIC factory creation failed");
    ComPtr<IWICBitmapDecoder> decoder;
    Check(SUCCEEDED(factory->CreateDecoderFromFilename(path.c_str(), nullptr, GENERIC_READ,
          WICDecodeMetadataCacheOnLoad, &decoder)), "Rendered PNG could not be decoded");
    UINT frameCount = 0;
    Check(SUCCEEDED(decoder->GetFrameCount(&frameCount)) && frameCount == 1,
          "Rendered PNG must contain exactly one frame");
    ComPtr<IWICBitmapFrameDecode> frame;
    Check(SUCCEEDED(decoder->GetFrame(0, &frame)), "Rendered PNG frame is unavailable");
    UINT width = 0, height = 0;
    Check(SUCCEEDED(frame->GetSize(&width, &height)) && width == Width && height == Height,
          "Rendered PNG changed the 1920x1080 dimensions");
    ComPtr<IWICFormatConverter> converter;
    Check(SUCCEEDED(factory->CreateFormatConverter(&converter)), "WIC format converter creation failed");
    Check(SUCCEEDED(converter->Initialize(frame.Get(), GUID_WICPixelFormat32bppBGRA,
          WICBitmapDitherTypeNone, nullptr, 0.0, WICBitmapPaletteTypeCustom)), "WIC BGRA conversion failed");
    std::vector<unsigned char> pixels(static_cast<std::size_t>(Width) * Height * 4u);
    Check(SUCCEEDED(converter->CopyPixels(nullptr, Width * 4u, static_cast<UINT>(pixels.size()),
          pixels.data())), "Rendered PNG pixels could not be read");
    return pixels;
}

struct Frame {
    Scene scene{};
    std::vector<unsigned char> pixels;
};

Frame Capture(const WorldView& view, const std::filesystem::path& path, const Scene* previous = nullptr) {
    Check(view.terrainAssetsPath.empty() && view.unitAssetsPath.empty(), "A fixture requested external assets");
    Check(!std::filesystem::exists(path), "The private temporary PNG already exists");
    Frame result;
    if (previous) result.scene = *previous;
    WorldViewProjection projection;
    projection.ready = true; projection.mapWidth = -123;
    std::wstring error;
    CheckRender(RenderWorldView(view, path.wstring(), &result.scene, &error, &projection), error);
    ++renders;
    Check(error.empty(), "Successful software rendering retained an error");
    Check(terrainCalls == 0 && gpuTerrainCalls == 0, "A terrain stand-in was executed");
    Check(!projection.ready && projection.mapWidth == 0 && projection.plots.empty(),
          "Software fixture fabricated a terrain projection");
    Check(result.scene.width == Width && result.scene.height == Height, "Scene dimensions changed");
    Check(result.scene.textures.empty() && result.scene.sprites.empty() && result.scene.scrolls.empty(),
          "Software fixture created external textures, retained overlays, or scrolling controls");
    Check(result.scene.pixelHits.indices.empty() && result.scene.pixelHits.keys.empty(),
          "Software fixture fabricated terrain pixel picking");
    result.pixels = ReadPixels(path);
    Check(std::filesystem::remove(path), "The exact private temporary PNG was not removed");
    return result;
}

const HitRecord* Find(const Scene& scene, std::uint64_t key) {
    const auto found = std::find_if(scene.hits.begin(), scene.hits.end(),
                                  [key](const HitRecord& hit) { return hit.controlKey == key; });
    return found == scene.hits.end() ? nullptr : &*found;
}

bool SameHits(const Scene& left, const Scene& right) {
    if (left.hits.size() != right.hits.size()) return false;
    for (std::size_t i = 0; i < left.hits.size(); ++i) {
        if (left.hits[i].controlKey != right.hits[i].controlKey) return false;
        for (unsigned j = 0; j < 4; ++j) if (left.hits[i].bounds[j] != right.hits[i].bounds[j]) return false;
    }
    return true;
}

constexpr std::array<WorldViewAction, 14> Actions{
    WorldViewAction::NextUnit, WorldViewAction::Skip, WorldViewAction::Found,
    WorldViewAction::EndTurn, WorldViewAction::Save, WorldViewAction::Close,
    WorldViewAction::PanLeft, WorldViewAction::PanRight, WorldViewAction::PanUp,
    WorldViewAction::PanDown, WorldViewAction::Research, WorldViewAction::Production,
    WorldViewAction::UnitActionsPrevious, WorldViewAction::UnitActionsNext
};

std::unordered_set<std::uint64_t> MapKeys(const WorldView& view) {
    std::unordered_set<std::uint64_t> keys;
    for (const auto& plot : view.plots) keys.insert(WorldViewHitKey::Plot(plot.index));
    for (const auto& unit : view.units) keys.insert(WorldViewHitKey::OwnedUnit(unit.id));
    for (const auto& city : view.cities) keys.insert(WorldViewHitKey::OwnedCity(city.id));
    return keys;
}

void CheckControls(const WorldView& view, const Scene& scene, bool fullMap) {
    auto allowed = MapKeys(view);
    for (const auto action : Actions) {
        bool expected = !fullMap;
        if (view.originalActionInfoPanel && action == WorldViewAction::EndTurn) expected = false;
        if (view.originalUnitPanel &&
            (action == WorldViewAction::Found || action == WorldViewAction::Skip ||
             action == WorldViewAction::UnitActionsPrevious || action == WorldViewAction::UnitActionsNext))
            expected = false;
        const auto key = WorldViewHitKey::Action(action);
        Check((Find(scene, key) != nullptr) == expected, "A diagnostic control did not match its HUD ownership");
        if (expected) allowed.insert(key);
    }
    for (const auto& action : view.unitActions) {
        const bool expected = !fullMap && !view.originalUnitPanel && action.index >= 106 && action.index < 112;
        const auto key = WorldViewHitKey::UnitAction(action.index);
        Check((Find(scene, key) != nullptr) == expected, "A diagnostic action-page hit survived or disappeared");
        if (expected) allowed.insert(key);
    }
    std::unordered_set<std::uint64_t> unique;
    for (const auto& hit : scene.hits) {
        Check(allowed.count(hit.controlKey) == 1, "An unaccounted diagnostic hit remains in the scene");
        Check(unique.insert(hit.controlKey).second, "A rendered hit key was duplicated");
    }
}

void CheckMap(const WorldView& view, const Scene& scene, bool fullMap) {
    const auto keys = MapKeys(view);
    const float maximumX = fullMap ? 1920.0f : 1380.0f;
    std::size_t mapHits = 0;
    bool clippedRightEdge = false;
    for (const auto& hit : scene.hits) {
        if (!keys.count(hit.controlKey)) continue;
        ++mapHits;
        Check(hit.bounds[0] >= 0 && hit.bounds[1] >= 0 && hit.bounds[2] <= maximumX && hit.bounds[3] <= 1080.0f,
              "Map hit bounds escaped the displayed viewport");
        Check(hit.bounds[0] < hit.bounds[2] && hit.bounds[1] < hit.bounds[3], "Map hit became empty or reversed");
        if (hit.bounds[2] == maximumX) clippedRightEdge = true;
    }
    Check(mapHits > 100, "The grid fixture did not exercise both viewport edges and many map rows");
    Check(clippedRightEdge, "The grid fixture did not exercise right-edge hit clipping");
    const auto* central = Find(scene, WorldViewHitKey::Plot(CentralPlot));
    Check(central != nullptr, "Central empty plot lost its selection hit");
    Near((central->bounds[0] + central->bounds[2]) * 0.5f, fullMap ? 960.0f : 690.0f,
         "The camera was not centered in the expected viewport");
    Near((central->bounds[1] + central->bounds[3]) * 0.5f, 540.0f, "Vertical camera center moved");
    Check(Find(scene, WorldViewHitKey::OwnedUnit(17)) != nullptr, "The selected owned-unit map hit disappeared");
    Check(Find(scene, WorldViewHitKey::OwnedCity(23)) != nullptr, "The selected owned-city map hit disappeared");
    const auto* rightEdge = Find(scene, WorldViewHitKey::Plot(RightEdgePlot));
    Check((rightEdge != nullptr) == fullMap, "The former right-panel area did not become selectable map");
    if (rightEdge) {
        // Independent fixed geometry: this odd-row plot is centered at x=1926,
        // so its selectable rectangle crosses the 1920-pixel frame boundary.
        Near(rightEdge->bounds[0], 1893.24f, "Right-edge plot moved to an unexpected horizontal position");
        Near(rightEdge->bounds[2], 1920.0f, "Right-edge plot did not clip at the full-width boundary");
        Check(rightEdge->bounds[0] < 1910.0f && rightEdge->bounds[2] > 1910.0f,
              "The former diagnostic panel has no rightmost map hit");
    }
}

bool EqualRect(const std::vector<unsigned char>& left, const std::vector<unsigned char>& right,
               unsigned x0, unsigned y0, unsigned x1, unsigned y1) {
    ++pixelRegionsChecked;
    if (left.size() != static_cast<std::size_t>(Width) * Height * 4u || right.size() != left.size()) return false;
    for (unsigned y = y0; y < y1; ++y) {
        for (unsigned x = x0; x < x1; ++x) {
            const auto pixel = (static_cast<std::size_t>(y) * Width + x) * 4u;
            ++regionPixelComparisons;
            if (!std::equal(left.begin() + pixel, left.begin() + pixel + 4u, right.begin() + pixel)) return false;
        }
    }
    return true;
}

bool SamePixel(const std::vector<unsigned char>& left, const std::vector<unsigned char>& right,
               unsigned x, unsigned y) {
    return EqualRect(left, right, x, y, x + 1u, y + 1u);
}

Scene MapOnly(const WorldView& view, const Scene& input) {
    Scene result{};
    const auto keys = MapKeys(view);
    for (const auto& hit : input.hits) if (keys.count(hit.controlKey)) result.hits.push_back(hit);
    return result;
}

void CheckPartialPixels(const WorldView& view, const Frame& frame, const Frame& baseline) {
    Check(EqualRect(frame.pixels, baseline.pixels, 0, 0, 1380, 1080),
          "A partial original HUD changed legacy map pixels or the viewport");
    Check(SameHits(MapOnly(view, frame.scene), MapOnly(view, baseline.scene)),
          "A partial original HUD changed ordered map selection geometry");
    Check(SamePixel(frame.pixels, baseline.pixels, 1383, 900) && SamePixel(frame.pixels, baseline.pixels, 1910, 1050),
          "A partial original HUD lost the diagnostic divider or panel background");
    Check(EqualRect(frame.pixels, baseline.pixels, 1404, 30, 1890, 144) != view.originalTopPanel,
          "Partial TopPanel title/turn suppression changed its prior behavior");
    Check(EqualRect(frame.pixels, baseline.pixels, 1401, 180, 1896, 276) != view.originalUnitPanel,
          "Partial UnitPanel caption suppression changed its prior behavior");
    Check(EqualRect(frame.pixels, baseline.pixels, 1647, 546, 1872, 606) != view.originalActionInfoPanel,
          "Partial ActionInfoPanel EndTurn suppression changed its prior behavior");
}

void CheckFixtureStillOwned(const WorldView& view) {
    Check(view.plots.size() == 651 && view.units.size() == 1 && view.cities.size() == 1 && view.unitActions.size() == 13,
          "Rendering changed the detached fixture inventories");
    Check(view.gridWidth == 31 && view.gridHeight == 21 && view.cameraX == 15 && view.cameraY == 10 &&
          view.tileWidth == 56.0f && view.activePlayer == 0 && view.unitActionPage == 1 && view.selectedCity == 23,
          "Rendering changed detached view selection, camera, owner, or action page");
    Check(view.terrainAssetsPath.empty() && view.unitAssetsPath.empty(), "Rendering changed detached asset paths");
}

void HudCases(const std::filesystem::path& png) {
    auto view = Fixture();
    Check(!view.fullScreenUi && !view.originalTopPanel && !view.originalUnitPanel && !view.originalActionInfoPanel,
          "The default detached view no longer starts with the diagnostic fallback");
    Frame fallback = Capture(view, png);
    CheckControls(view, fallback.scene, false); CheckMap(view, fallback.scene, false);
    Frame full;
    for (unsigned mask = 0; mask < 8; ++mask) {
        SetHud(view, mask);
        Frame frame = mask == 0 ? fallback : Capture(view, png, &fallback.scene);
        ++hudCases;
        CheckControls(view, frame.scene, mask == 7); CheckMap(view, frame.scene, mask == 7);
        CheckFixtureStillOwned(view);
        if (mask != 7) CheckPartialPixels(view, frame, fallback);
        else full = std::move(frame);
    }
    Check(!SamePixel(full.pixels, fallback.pixels, 1383, 900),
          "The diagnostic separator still covers the expanded map");
    Check(!SamePixel(full.pixels, fallback.pixels, 1910, 613),
          "The rightmost map was left as diagnostic panel pixels");
    // Labels that exist only in the temporary panel must have no raster or
    // input effect after the original HUD takes ownership. The map-side city
    // name, unit health, selected state, and physical map facts stay fixed.
    auto varied = view;
    varied.turn = 91; varied.status = L"A completely different diagnostic status";
    varied.units[0].name = L"A different diagnostic selected-unit caption";
    for (auto& action : varied.unitActions) action.name = L"Changed diagnostic action";
    Frame hidden = Capture(varied, png, &fallback.scene);
    ++auxiliaryHudCases;
    Check(hidden.pixels == full.pixels && SameHits(hidden.scene, full.scene),
          "Complete original HUD retained diagnostic captions, status, or actions");
    CheckFixtureStillOwned(varied);

    // Existing full-screen behavior must remain identical for every partial
    // HUD readiness combination. It is also an independent full-width raster
    // and hit-map oracle for the newly complete original-HUD state.
    view.fullScreenUi = true;
    for (unsigned mask = 0; mask < 8; ++mask) {
        SetHud(view, mask);
        Frame frame = Capture(view, png, &fallback.scene);
        ++fullscreenCases;
        CheckControls(view, frame.scene, true); CheckMap(view, frame.scene, true);
        Check(frame.pixels == full.pixels && SameHits(frame.scene, full.scene),
              "Full-screen behavior changed with retained HUD readiness or differs from the full original HUD");
        CheckFixtureStillOwned(view);
    }

    view.fullScreenUi = false; SetHud(view, 0);
    Frame restored = Capture(view, png, &full.scene);
    ++auxiliaryHudCases;
    Check(restored.pixels == fallback.pixels && SameHits(restored.scene, fallback.scene),
          "Losing original HUD readiness did not restore identical fallback pixels and ordered hits");
    CheckControls(view, restored.scene, false); CheckMap(view, restored.scene, false);
    CheckFixtureStillOwned(view);
}

void Quoted(std::ostream& output, const std::string& text) {
    output << '"';
    for (const unsigned char value : text) {
        if (value == '\\' || value == '"') output << '\\' << static_cast<char>(value);
        else if (value < 0x20u || value >= 0x7fu) output << '?';
        else output << static_cast<char>(value);
    }
    output << '"';
}
}

int wmain(int argc, wchar_t** argv) {
    try {
        Check(argc == 2, "Expected one existing empty private output directory");
        const std::filesystem::path output(argv[1]);
        Check(output.is_absolute() && std::filesystem::is_directory(output) &&
              !std::filesystem::is_symlink(output) && std::filesystem::is_empty(output),
              "Output must be an existing empty absolute private directory");
        const auto png = output / L"world-original-hud-temporary.png";
        WheelCases();
        HudCases(png);
        Check(hudCases == 8 && fullscreenCases == 8, "HUD readiness combinations were omitted");
        Check(terrainCalls == 0 && gpuTerrainCalls == 0, "An offscreen fixture executed the terrain renderer");
        Check(!std::filesystem::exists(png) && std::filesystem::is_empty(output),
              "A successful component test retained a temporary capture");
        std::cout << "{\"schema\":\"zerosis.world.original_hud_test.v1\","
                     "\"status\":\"PASS_WORLD_ORIGINAL_HUD_COMPONENT\",\"checks\":" << checks
                  << ",\"renders\":" << renders << ",\"hud_combinations\":" << hudCases
                  << ",\"fullscreen_combinations\":" << fullscreenCases
                  << ",\"fixtures\":" << hudCases + fullscreenCases + auxiliaryHudCases + wheelCases
                  << ",\"camera_wheel_cases\":" << wheelCases << ",\"camera_wheel_checks\":" << wheelChecks
                  << ",\"pixel_regions_checked\":" << pixelRegionsChecked
                  << ",\"region_pixel_comparisons\":" << regionPixelComparisons
                  << ",\"partial_viewport_pixels\":1380,\"complete_viewport_pixels\":1920,"
                     "\"production_world_renderer_executed\":true,\"wic_offscreen_executed\":true,"
                     "\"complete_hud_matches_fullscreen_pixels_and_hits\":true,"
                     "\"fallback_roundtrip_pixels_and_hits_unchanged\":true,"
                     "\"diagnostic_hits_removed\":true,\"temporary_png_removed\":true,"
                     "\"terrain_calls\":0,\"gpu_terrain_calls\":0,\"terrain_stand_ins_executed\":false,"
                     "\"window_calls\":0,\"camera_wheel_routing_executed\":false,"
                     "\"host_executed\":false,\"sdk_executed\":false,\"gamecore_loaded\":false,"
                     "\"window_created\":false,\"swapchain_created\":false,\"d3d_device_created\":false,"
                     "\"game_accessed\":false,\"user_saves_accessed\":false,\"restore_approved\":false,"
                     "\"full_campaign_ui_verified\":false,\"full_engine_goal_complete\":false}\n";
        return 0;
    } catch (const std::exception& error) {
        std::cout << "{\"schema\":\"zerosis.world.original_hud_test.v1\","
                     "\"status\":\"FAIL_WORLD_ORIGINAL_HUD_COMPONENT\",\"checks\":" << checks
                  << ",\"renders\":" << renders << ",\"error\":";
        Quoted(std::cout, error.what());
        std::cout << ",\"host_executed\":false,\"sdk_executed\":false,\"window_created\":false,"
                     "\"full_engine_goal_complete\":false}\n";
        return 1;
    }
}
