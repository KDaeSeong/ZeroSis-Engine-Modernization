#pragma once
namespace ZeroSisPresentation { namespace OriginalWaterFog {
// Original WaterPS gray literal. The absent overlay producer is neutral.
constexpr float ReplacementGray=0.4f;
constexpr float CandidateOverlay[4]={0,0,0,0};
constexpr unsigned SurfaceFragment=1,OtherFragment=0;
constexpr unsigned FogCompleteFragment=2;
constexpr unsigned FragmentTarget=4;
// Original OM state8 is statically recovered: source-alpha RGB over destination,
// additive alpha. FOW is applied before blending; marker2 skips a second pass.
constexpr bool RetailHardwareBlendStateRecovered=true;
// Actual device execution remains held; static recovery is not GPU acceptance.
constexpr bool RetailHardwareBlendVerified=false;
}}
