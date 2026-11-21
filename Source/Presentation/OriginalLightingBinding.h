#pragma once
namespace ZeroSisPresentation { namespace OriginalLighting {
constexpr const char* LightingPackageSha256="d0873d3915da23e45ee1b66187bb7e4174673a1e8cce1fea16b6151ff515e424";
// Candidate runtime binding: continent0=Generic,1=America,2=Asia,3=Africa,4=Europe.
// Cube sampling consumes raw BC1_UNORM values, without sRGB conversion.
// Terrain LUT is raw encoded RGBA8_UNORM; TGA-to-volume loader equivalence,
// cube-normal axes, LUT runtime selection and sampler state remain unverified.
constexpr unsigned CandidateTerrainLutSide=32;
}}
