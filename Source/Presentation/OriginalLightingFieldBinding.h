#pragma once
#include "OriginalTerrainModel.h"
#include "OriginalTerrainGeometry.h"
namespace ZeroSisPresentation { namespace OriginalLighting { namespace FieldBinding {
// Original NormalCalculate call path sets cb1[1].x to float16 (0x41800000).
// TerrainShaderScreen MRT1 feeds this path; our68/66 scratch sizes and
// resampling remain candidates. NormalTemp's recovered storage is RGBA8
// typeless with active UNORM RTV/SRV and LINEAR_CLAMP sampling.
constexpr float NormalStrength=16.0f;
constexpr unsigned HeightSide=68,NormalSide=66,TileTexels=64;
// Runtime shadow-space mapping and the shared original bias/strength are
// explicit candidates in the current normalized world-coordinate system.
constexpr double ShadowDirectionX=-1,ShadowDirectionY=1;
constexpr double TexelWorldX=1.0/64,TexelWorldY=static_cast<double>(OriginalTerrain::RowSpacing)/64;
constexpr double ShadowHeightScale=static_cast<double>(OriginalTerrain::HeightWorldScaleCandidate)/255;
constexpr double ShadowHeightOffset=static_cast<double>(OriginalTerrain::HeightOffsetCandidate);
constexpr double ShadowBiasAndStrength=0.125;
// Legacy neutral fixture for old pure CPU-reference probes. The current final
// renderer samples the static specscreenmap DDS through b6/t44; dynamic Raw
// reflection is a separate water input. This value selects neither resource.
constexpr float ScreenLightCandidate=1.0f;
}}}
