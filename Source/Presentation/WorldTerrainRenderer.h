#pragma once
#include "WorldViewRenderer.h"
#include <map>

struct ID3D11Device;
struct ID3D11DeviceContext;
struct ID3D11Texture2D;

namespace ZeroSisPresentation {
// Release on the rendering owner before the Host pins/CLR runtime shut down.
void ReleaseWorldTerrainResources();
struct TerrainProjection { float x=0, y=0; };
struct TerrainFrame {
    std::vector<unsigned char> bgra;
    PixelHitMap picking;
    std::map<int,TerrainProjection> centers;
    std::map<int,WorldProjectedPlot> projectedPlots;
    std::uint64_t triangles=0;
    std::uint64_t unitTriangles=0;
    unsigned modelUnits=0;
    bool hardware=false;
};

// D3D11 mesh, depth and integer-ID passes share one camera and geometry.
// Original DDS samples are preserved; piece selection, height scale, UVs,
// lighting and edge blending are candidate policies, not retail equivalence.
bool RenderWorldTerrain(const WorldView& view, std::uint32_t width,
                        std::uint32_t height, std::uint32_t mapWidth,
                        TerrainFrame* frame, std::wstring* error);

// Renders the same color/depth/plot-ID passes using the caller-owned immediate
// context. Color bytes are copied from the renderer's sRGB RTV into a matching
// BGRA8_UNORM RT|SRV caller target (no CPU color readback or color conversion). The
// caller retains device/context/target ownership, must keep target unbound from
// its pipeline for the call, and must rebind its own D3D state afterward. On
// success frame->bgra is empty. Exact unchanged ground inputs reuse immutable
// meshes and owned ID/projection metadata; every pose clears and redraws depth.
bool RenderWorldTerrainToTexture(const WorldView& view, std::uint32_t width,
                                std::uint32_t height, std::uint32_t mapWidth,
                                ID3D11Device* device, ID3D11DeviceContext* context,
                                ID3D11Texture2D* targetTexture, TerrainFrame* frame,
                                std::wstring* error);
}
