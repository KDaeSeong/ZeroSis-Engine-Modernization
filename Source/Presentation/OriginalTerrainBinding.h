#pragma once
#include "OriginalTerrainCacheSamplingModel.h"
namespace ZeroSisPresentation { namespace OriginalTerrain {
constexpr char PackageSha256[]="02104c582759bf0cefb58f97379699e45300eb2a9c6da6fdd3c65d1440cb84e8";
// The display origin is a presentation candidate, not the recovered waterline.
// Raw heightmap -> world metrics are file-backed defaults; the world camera
// and any runtime overrides remain a separate calibration gate.
constexpr float HeightOffsetCandidate=15300.0f/65535.0f;
constexpr float HeightWorldScaleCandidate=OriginalTerrainCacheSampling::NormalizedHeightRangeDefault;
constexpr float RetailWorldUnitsPerHexCandidate=64.0f;
inline float DisplayHeightOriginCandidate(){
    return OriginalTerrainCacheSampling::RawHeightToOriginalWorld(15300);
}
}}
