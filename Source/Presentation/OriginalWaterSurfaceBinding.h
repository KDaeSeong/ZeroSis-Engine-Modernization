#pragma once
#include "OriginalTerrainBinding.h"
namespace ZeroSisPresentation { namespace OriginalWaterSurfaceBinding {
constexpr const char* LeanPackageSha256="69c6780dbeb5f8605d8231cef944d0ec9392109b6ccc81a9d3b76ae83cfd0ef7";
// Original default waterline is a candidate for the unrecovered runtime plane constant.
constexpr double RawLevelCandidate=0.19836;
constexpr float WorldPlaneCandidate=static_cast<float>((RawLevelCandidate-OriginalTerrain::HeightOffsetCandidate)*OriginalTerrain::HeightWorldScaleCandidate);
constexpr float CandidateReflectionScale=0.5f;
constexpr float CandidateRefractionDisplacement=0.012f;
}}
