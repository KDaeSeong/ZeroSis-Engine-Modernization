#pragma once
namespace ZeroSisPresentation { namespace OriginalFog {
// Supplemental immutable assets; the phase-one terrain package is reused.
constexpr const char* PackageSha256="42ae12554e1514dd48a9a5df25f47b4280d22d180dff29d169c602334e879bcc";
// Runtime calibration candidates, not recovered retail constant-buffer values.
constexpr float CandidateHeightK=0.0025f;
constexpr float CandidateDensity=0.00004f;
constexpr float CandidateRampRow=0.5f;
constexpr float CandidateFlowDisplacement=0.04f;
}}
