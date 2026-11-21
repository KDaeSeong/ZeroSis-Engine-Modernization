#pragma once

#include "BitmapRenderer.h"
#include "WorldCameraControls.h"
#include "OriginalScreenLightingModel.h"

#include <string>
#include <vector>
#include <map>
#include <array>

namespace ZeroSisPresentation {

struct WorldViewPlot {
    int index;
    int x, y;
    bool revealed, visible, water, hills, mountain;
    std::string terrain, feature;
    int improvementType=-1, routeType=-1;
    bool improvementPillaged=false, routePillaged=false;
    std::wstring improvementName, routeName;
    int continent=-1;
    int terrainId=-1;
    bool naturalWonder=false;
    // Detached SDK river edges: E, SE and SW are owned by this plot.
    bool lake=false; // Public ICvPlot1 has no lake classification query.
    bool riverW=false,riverNW=false,riverNE=false;
    int flowE=-1,flowSE=-1,flowSW=-1;
};

struct WorldViewUnit {
    int id, owner, x, y, moves, damage;
    bool selected;
    std::wstring name;
    int maxHitPoints=100;
    bool hostile=false;
    // Detached original SDK art-selection inputs. Kept at the aggregate tail
    // with defaults so existing DTO fixtures remain source-compatible.
    int unitType=-1, civilizationType=-1, artStyleType=-1, ownerEra=-1;
    int facingDirection=-1;
    std::string type, unitArtInfoTag, artStylePrefix, artStyleSuffix, eraArtPrefix;
    bool unitArtInfoCulturalVariation=false, unitArtInfoEraVariation=false, embarked=false;
};

struct WorldViewCity {
    int id, owner, x, y;
    // Localized presentation text and the untouched SDK/save-side name value.
    std::wstring name;
    std::string rawName;
};

struct WorldViewUnitAction {int index;std::wstring name;};

struct WorldView {
    int gridWidth, gridHeight, turn, activePlayer;
    int selectedCity = -1;
    bool fullScreenUi = false; // Original full-screen UI replaces the temporary world HUD.
    bool originalTopPanel = false;
    bool originalActionInfoPanel = false;
    bool originalUnitPanel = false;
    bool wrapX, wrapY;
    std::vector<WorldViewPlot> plots;
    std::vector<WorldViewUnit> units;
    std::vector<WorldViewCity> cities;
    std::vector<WorldViewUnitAction> unitActions;
    int unitActionPage = 0;
    std::wstring status;
    int cameraX, cameraY;
    float tileWidth = WorldCameraZoom::Default;
    std::wstring terrainAssetsPath;
    std::wstring unitAssetsPath;
    // Presentation clock only; no SDK RNG, turn timing or save-state mutation.
    double animationSeconds=0.0;
    // Detached initial map seed, read without consuming any SDK RNG state.
    std::uint32_t mapRandomSeed=0;
    // Explicit supplemental FOW package. Empty keeps the existing renderer path.
    std::wstring fogAssetsPath;
    double fogAnimationSeconds=0.0;
    std::wstring waterAssetsPath;
    double waterAnimationSeconds=0.0;
    // Explicit LEAN/plane mode, independent from the retained colour overlay.
    std::wstring waterSurfaceAssetsPath;
    // Optional original irradiance cubes and terrain colour lookup package.
    std::wstring lightingAssetsPath;
    // Private presentation policy; never serialized into SDK/save/original INI.
    OriginalScreenLighting::Policy screenLightingPolicy;
    // Explicit pinned specscreenmap package; independent of water reflection.
    std::wstring screenLightingAssetsPath;
};

// Detached screen geometry from the same depth/ID pass as the displayed map.
// Spans are (y,x,count), in raster order, and contain only winning plot pixels.
struct WorldProjectedPlot {
    float centerX=-1000000,centerY=-1000000;
    bool anchorVisible=false;
    std::vector<std::array<int,3>> spans;
};
struct WorldViewProjection {
    bool ready=false;
    std::uint64_t frameGeneration=0;
    int cameraX=0,cameraY=0,gridWidth=0,gridHeight=0,mapWidth=0;
    std::map<int,WorldProjectedPlot> plots;
};

enum class WorldViewAction : std::uint32_t {
    NextUnit = 1, Skip, Found, EndTurn, Save, Close,
    PanLeft, PanRight, PanUp, PanDown, Research, Production, UnitActionsPrevious, UnitActionsNext
};

namespace WorldViewHitKey {
std::uint64_t Plot(int plotIndex) noexcept;
std::uint64_t OwnedUnit(int unitId) noexcept;
std::uint64_t OwnedCity(int cityId) noexcept;
std::uint64_t UnitAction(int actionIndex) noexcept;
std::uint64_t Action(WorldViewAction action) noexcept;
}

// Produces a 1920x1080 frame and matching input. A sealed terrain package
// enables the D3D11 terrain pass; an empty path retains the legacy 2D diagnostic.
// Original terrain assets do not by themselves prove original 3D equivalence.
bool RenderWorldView(const WorldView& view, const std::wstring& pngPath,
                     Scene* scene, std::wstring* error, WorldViewProjection* projection=nullptr);

// Renders the same world/HUD/input projection into a private candidate owned by
// the caller's immediate D3D11 context. No color readback or PNG is produced.
bool RenderWorldViewToTexture(const WorldView& view, ID3D11Device* device,
                              ID3D11DeviceContext* context, ID3D11Texture2D* texture,
                              Scene* scene, std::wstring* error,
                              WorldViewProjection* projection=nullptr,bool traceFrame=true);

}  // namespace ZeroSisPresentation
