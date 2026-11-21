#pragma once
// Retail TerrainShader bicubic patch inputs, taken from CivilizationV_DX11.exe
// (SHA-256 b7c8977e...fcd8818) by basis_retail_probe.py.  Pure CPU, no D3D, no SDK.
//
// Evidence summary (addresses are virtual addresses of the retail executable):
//   0x6add60  fills cb1 of the terrain effect; rows cb1[10..13] come from nine float literals.
//   0x6c9c00  writes the 16 control index words of every patch.
//   0x5c37e0  writes the per-draw cb0 (origin, uv scale, control spacing, height mip level).
//   TerrainShader pass 0 VS/HS/DS consume them (phase10/geometry listings).
// This header is an independent component; it does not include or modify the shared sources.
#include <array>
#include <cmath>
#include <cstdint>
#include <stdexcept>

namespace ZeroSisClaudeGeometry { namespace TerrainBicubicRetail {

using Row = std::array<float, 4>;
using Basis = std::array<Row, 4>;
using Heights = std::array<float, 16>;      // index = r * 4 + c, c along x (domain u), r along y (domain v)
using Known = std::array<std::uint8_t, 16>;

// cb1[10] multiplies t^3, cb1[11] t^2, cb1[12] t, cb1[13] 1; the column is the control index.
// Every entry is a multiple of 1/8 and exact in binary32.
inline Basis RetailBasis() noexcept {
    return {{ {{-0.125f, 0.875f, -0.875f, 0.125f}},
              {{0.375f, -1.5f, 1.125f, 0.0f}},
              {{-0.375f, 0.0f, 0.375f, 0.0f}},
              {{0.125f, 0.75f, 0.125f, 0.0f}} }};
}

// cb1[16]: horizontal world units per height texel (x, y) and the height factor.  The literals
// are 1.0f, 0.866f (0x3f5db22d, not sqrt(3)/2) and 0.2f.
constexpr float RetailUnitX = 1.0f;
constexpr float RetailUnitY = 0.866f;
constexpr float RetailHeightFactor = 0.2f;
constexpr float RetailHeightTexelScale = 1.0f / 1024.0f;   // cb1[22].x; cb1[22].y is its negative

// VS: o0.x = (alpha * cb1[16].z) * 255.
inline float ControlHeight(float alpha) {
    if (!std::isfinite(alpha) || alpha < 0.0f || alpha > 1.0f)
        throw std::invalid_argument("Invalid height texture alpha");
    return (alpha * RetailHeightFactor) * 255.0f;
}

// Index word written by 0x6c9c00 for patch (px, py) and control (c, r).
inline std::uint16_t ControlIndexWord(unsigned px, unsigned py, unsigned c, unsigned r) {
    if (c > 3 || r > 3 || px + c + 2 > 255 || py + r + 2 > 255)
        throw std::invalid_argument("Terrain patch control outside the 8-bit index fields");
    return static_cast<std::uint16_t>(((py + r + 2) << 8) | (px + c + 2));
}
struct ControlTexel { int x; int y; };
// VS: ((id & 255) - 3, (id >> 8) - 3), in control spacings relative to the cell origin.
inline ControlTexel DecodeControl(std::uint16_t word) noexcept {
    return {static_cast<int>(word & 255u) - 3, static_cast<int>(word >> 8) - 3};
}
// Level size used by the index generator and by cb0[6]: n = (n >> 1) + 1 per level.
inline unsigned LevelSize(unsigned size, unsigned level) {
    if (size < 2 || size > 253 || level > 4) throw std::invalid_argument("Invalid terrain cell size or level");
    for (unsigned index = 0; index < level; ++index) size = (size >> 1) + 1;
    return size;
}
inline unsigned PatchCount(unsigned width, unsigned height, unsigned level) {
    const unsigned w = LevelSize(width, level), h = LevelSize(height, level);
    return (w - 1) * (h - 1);
}
// cb0[6].x: control spacing in height texels at a level, (W - 1) / (W_level - 1).
inline float ControlSpacing(unsigned size, unsigned level) {
    const unsigned reduced = LevelSize(size, level);
    if (reduced < 2) throw std::invalid_argument("Terrain level has no patch");
    return static_cast<float>(size - 1) / static_cast<float>(reduced - 1);
}

// DS order: w = b1 * t^2; w = b0 * t^3 + w; w = b2 * t + w; w = w + b3.
inline Row Weights(const Basis& basis, float t) noexcept {
    const float t2 = t * t, t3 = t2 * t;
    Row out{};
    for (unsigned column = 0; column < 4; ++column) {
        float value = t2 * basis[1][column];
        value = basis[0][column] * t3 + value;
        value = basis[2][column] * t + value;
        out[column] = value + basis[3][column];
    }
    return out;
}
inline float Dot(const Row& a, const Row& b) noexcept {
    return ((a[0] * b[0] + a[1] * b[1]) + a[2] * b[2]) + a[3] * b[3];
}
inline void ValidateDomain(float u, float v) {
    if (!std::isfinite(u) || !std::isfinite(v) || u < 0.0f || u > 1.0f || v < 0.0f || v > 1.0f)
        throw std::invalid_argument("Invalid terrain patch domain coordinate");
}
// DS: four row sums with the u weights, then dot(cb1[10+k], rows) and the (v^3, v^2, v, 1) dot.
inline float Evaluate(const Heights& controls, float u, float v) {
    ValidateDomain(u, v);
    for (const float value : controls)
        if (!std::isfinite(value) || std::abs(value) > 1000000.0f)
            throw std::invalid_argument("Invalid terrain patch control height");
    const Basis basis = RetailBasis();
    const Row horizontal = Weights(basis, u);
    Row rows{};
    for (unsigned r = 0; r < 4; ++r)
        rows[r] = Dot(horizontal, {{controls[r * 4], controls[r * 4 + 1], controls[r * 4 + 2], controls[r * 4 + 3]}});
    const Row vertical{{Dot(basis[0], rows), Dot(basis[1], rows), Dot(basis[2], rows), Dot(basis[3], rows)}};
    const float v2 = v * v;
    return Dot(vertical, {{v2 * v, v2, v, 1.0f}});
}
struct Sample { bool available = false; float height = 0.0f; };
// The whole 4 x 4 footprint is checked before any height is read: one unexplored control
// denies the sample, and its height value is never touched.
inline Sample EvaluateKnown(const Heights& controls, const Known& known, float u, float v) {
    ValidateDomain(u, v);
    bool missing = false;
    for (const std::uint8_t value : known) {
        if (value > 1) throw std::invalid_argument("Invalid terrain patch known state");
        missing = missing || value == 0;
    }
    if (missing) return {};
    return {true, Evaluate(controls, u, v)};
}
struct WorldXY { float x; float y; };
// DS: (domain * spacing + origin + cellOrigin) * cb1[16].xy, before the world matrix cb0[0..3].
inline WorldXY PatchWorldXY(float u, float v, float spacingX, float spacingY,
                            float originX, float originY, float cellX, float cellY) {
    ValidateDomain(u, v);
    const float x = (u * spacingX + originX) + cellX, y = (v * spacingY + originY) + cellY;
    if (!std::isfinite(x) || !std::isfinite(y)) throw std::invalid_argument("Nonfinite terrain patch position");
    return {x * RetailUnitX, y * RetailUnitY};
}
}}
