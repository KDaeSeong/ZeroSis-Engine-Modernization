#pragma once
namespace ZeroSisPresentation { namespace OriginalWater {
constexpr const char* PackageSha256="2ff227dae9d16398e038e8ea33624940a9581e0eb2d37c3891121fae22c25afc";
// Candidate temporal/UV/lighting calibration, not recovered retail runtime values.
constexpr float CandidateWaterUvScales[4]={1.0f/512.0f,1.0f/704.0f,1.0f/960.0f,1.0f/384.0f};
constexpr float CandidateWaterTranslation=0.01f;
constexpr float CandidateRiverTranslation=0.05f;
}}
