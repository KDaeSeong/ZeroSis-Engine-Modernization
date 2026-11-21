// Pure CPU checks of OriginalTerrainBicubicRetail.h.  Expected values come from sources that are
// independent of the header's matrix arithmetic: the piecewise Mitchell-Netravali kernel in
// double precision, closed-form polynomials, and literal index words read from the retail
// generator rule.  No D3D, SDK, window or game code is used.
#include "OriginalTerrainBicubicRetail.h"
#include <cstdio>
#include <cstdlib>
#include <limits>

namespace G = ZeroSisClaudeGeometry::TerrainBicubicRetail;

static unsigned long long g_checks = 0;
static void Check(bool condition, const char* what) {
    ++g_checks;
    if (!condition) { std::printf("FAIL %s\n", what); std::exit(1); }
}
// Mitchell-Netravali kernel, B = 3/4, C = 0, written from the published piecewise definition.
static double Kernel(double x) {
    const double B = 0.75, C = 0.0;
    x = std::fabs(x);
    if (x < 1.0) return ((12 - 9 * B - 6 * C) * x * x * x + (-18 + 12 * B + 6 * C) * x * x + (6 - 2 * B)) / 6.0;
    if (x < 2.0) return ((-B - 6 * C) * x * x * x + (6 * B + 30 * C) * x * x + (-12 * B - 48 * C) * x + (8 * B + 24 * C)) / 6.0;
    return 0.0;
}
static double Reference(const G::Heights& controls, double u, double v) {
    double sum = 0.0;
    for (int r = 0; r < 4; ++r)
        for (int c = 0; c < 4; ++c)
            sum += Kernel(u - (c - 1)) * Kernel(v - (r - 1)) * static_cast<double>(controls[static_cast<unsigned>(r * 4 + c)]);
    return sum;
}
static std::uint32_t g_state = 0x13572468u;
static float Random01() {
    g_state = g_state * 1664525u + 1013904223u;
    return static_cast<float>(g_state >> 8) * (1.0f / 16777216.0f);
}
template <class Call> static bool Throws(Call call) {
    try { call(); } catch (const std::invalid_argument&) { return true; }
    return false;
}

int main() {
    const G::Basis basis = G::RetailBasis();
    double maxSurfaceError = 0.0;
    unsigned long long surfaceSamples = 0;

    // 1. Basis weights equal the kernel at every control for a dense set of parameters.
    for (int step = 0; step <= 256; ++step) {
        const float t = static_cast<float>(step) / 256.0f;
        const G::Row weights = G::Weights(basis, t);
        double sum = 0.0;
        for (int c = 0; c < 4; ++c) {
            Check(std::fabs(static_cast<double>(weights[static_cast<unsigned>(c)]) - Kernel(static_cast<double>(t) - (c - 1))) < 2e-7, "weight equals kernel");
            sum += static_cast<double>(weights[static_cast<unsigned>(c)]);
        }
        Check(std::fabs(sum - 1.0) < 4e-7, "partition of unity");
    }
    Check(basis[3][0] == 0.125f && basis[3][1] == 0.75f && basis[3][2] == 0.125f && basis[3][3] == 0.0f, "t=0 weights 1/8, 6/8, 1/8, 0");

    // 2. Constant surface.
    for (const float level : {0.0f, 1.0f, 12.75f, 51.0f}) {
        G::Heights flat; flat.fill(level);
        for (int a = 0; a <= 8; ++a) for (int b = 0; b <= 8; ++b)
            Check(std::fabs(G::Evaluate(flat, static_cast<float>(a) / 8.0f, static_cast<float>(b) / 8.0f) - level) <= 2e-5f, "constant surface");
    }

    // 3. Ramp: the retail basis has no linear precision.  Controls c - 1 give -t^3/2 + 3t^2/4 + 3t/4.
    G::Heights rampX, rampY;
    for (unsigned r = 0; r < 4; ++r) for (unsigned c = 0; c < 4; ++c) {
        rampX[r * 4 + c] = static_cast<float>(c) - 1.0f;
        rampY[r * 4 + c] = static_cast<float>(r) - 1.0f;
    }
    for (int a = 0; a <= 64; ++a) for (int b = 0; b <= 8; ++b) {
        const double t = a / 64.0, s = b / 8.0;
        const double closed = -0.5 * t * t * t + 0.75 * t * t + 0.75 * t;
        Check(std::fabs(static_cast<double>(G::Evaluate(rampX, static_cast<float>(t), static_cast<float>(s))) - closed) < 2e-6, "ramp along u");
        Check(std::fabs(static_cast<double>(G::Evaluate(rampY, static_cast<float>(s), static_cast<float>(t))) - closed) < 2e-6, "ramp along v");
    }
    Check(std::fabs(G::Evaluate(rampX, 0.25f, 0.5f) - 0.25f) > 0.02f, "ramp is not reproduced as a plane");
    Check(G::Evaluate(rampX, 0.0f, 0.5f) == 0.0f && std::fabs(G::Evaluate(rampX, 1.0f, 0.5f) - 1.0f) < 1e-6f, "ramp end values");

    // 4. Curved surfaces against the double-precision kernel.
    for (int surface = 0; surface < 4000; ++surface) {
        G::Heights controls;
        for (float& value : controls) value = Random01() * 51.0f;
        for (int a = 0; a <= 4; ++a) for (int b = 0; b <= 4; ++b) {
            const float u = static_cast<float>(a) / 4.0f, v = static_cast<float>(b) / 4.0f;
            const double error = std::fabs(static_cast<double>(G::Evaluate(controls, u, v)) - Reference(controls, u, v));
            if (error > maxSurfaceError) maxSurfaceError = error;
            ++surfaceSamples;
            Check(error < 2e-4, "curved surface equals kernel reference");
        }
    }

    // 5. Patch borders: neighbours that share controls meet with equal value and first derivative.
    for (int trial = 0; trial < 2000; ++trial) {
        float field[4][5];
        for (auto& row : field) for (float& value : row) value = Random01() * 51.0f;
        G::Heights left, right;
        for (unsigned r = 0; r < 4; ++r) for (unsigned c = 0; c < 4; ++c) { left[r * 4 + c] = field[r][c]; right[r * 4 + c] = field[r][c + 1]; }
        for (int b = 0; b <= 4; ++b) {
            const float v = static_cast<float>(b) / 4.0f;
            Check(std::fabs(G::Evaluate(left, 1.0f, v) - G::Evaluate(right, 0.0f, v)) < 1e-4f, "C0 across the u border");
            const float h = 1.0f / 64.0f;
            const float slopeLeft = (G::Evaluate(left, 1.0f, v) - G::Evaluate(left, 1.0f - h, v)) / h;
            const float slopeRight = (G::Evaluate(right, h, v) - G::Evaluate(right, 0.0f, v)) / h;
            Check(std::fabs(slopeLeft - slopeRight) < 2.5f, "C1 across the u border (finite difference)");
        }
        // Transposed layout checks the v border with the same data.
        G::Heights lower, upper;
        for (unsigned r = 0; r < 4; ++r) for (unsigned c = 0; c < 4; ++c) { lower[r * 4 + c] = field[c][r]; upper[r * 4 + c] = field[c][r + 1]; }
        for (int a = 0; a <= 4; ++a) {
            const float u = static_cast<float>(a) / 4.0f;
            Check(std::fabs(G::Evaluate(lower, u, 1.0f) - G::Evaluate(upper, u, 0.0f)) < 1e-4f, "C0 across the v border");
        }
    }
    // Exact derivative of the weights at the border: (0, -3/8, 0, 3/8) at t = 1 equals the shifted t = 0 row.
    {
        const G::Row d1{{3 * basis[0][0] + 2 * basis[1][0] + basis[2][0], 3 * basis[0][1] + 2 * basis[1][1] + basis[2][1],
                         3 * basis[0][2] + 2 * basis[1][2] + basis[2][2], 3 * basis[0][3] + 2 * basis[1][3] + basis[2][3]}};
        Check(d1[0] == 0.0f && d1[1] == basis[2][0] && d1[2] == basis[2][1] && d1[3] == basis[2][2], "analytic C1 of the weights");
        const G::Row w1 = G::Weights(basis, 1.0f);
        Check(w1[0] == 0.0f && w1[1] == basis[3][0] && w1[2] == basis[3][1] && w1[3] == basis[3][2], "analytic C0 of the weights");
    }

    // 6. Control index words: literal words of patch 0 and the vertex-shader decode.
    {
        const std::uint16_t literal[16] = {0x0202, 0x0203, 0x0204, 0x0205, 0x0302, 0x0303, 0x0304, 0x0305,
                                           0x0402, 0x0403, 0x0404, 0x0405, 0x0502, 0x0503, 0x0504, 0x0505};
        for (unsigned r = 0; r < 4; ++r) for (unsigned c = 0; c < 4; ++c)
            Check(G::ControlIndexWord(0, 0, c, r) == literal[r * 4 + c], "patch 0 literal index words");
        for (unsigned py = 0; py < 40; ++py) for (unsigned px = 0; px < 40; ++px)
            for (unsigned r = 0; r < 4; ++r) for (unsigned c = 0; c < 4; ++c) {
                const G::ControlTexel texel = G::DecodeControl(G::ControlIndexWord(px, py, c, r));
                Check(texel.x == static_cast<int>(px + c) - 1 && texel.y == static_cast<int>(py + r) - 1, "control position (px + c - 1, py + r - 1)");
            }
        const G::ControlTexel origin = G::DecodeControl(G::ControlIndexWord(7, 9, 1, 1));
        Check(origin.x == 7 && origin.y == 9, "control 5 is the patch origin");
        Check(Throws([] { G::ControlIndexWord(251, 0, 3, 0); }) && Throws([] { G::ControlIndexWord(0, 0, 4, 0); }), "index field overflow rejected");
        Check(G::LevelSize(65, 0) == 65 && G::LevelSize(65, 1) == 33 && G::LevelSize(65, 2) == 17 && G::LevelSize(65, 4) == 5, "level sizes");
        Check(G::LevelSize(5, 1) == 3 && G::LevelSize(4, 1) == 3 && G::PatchCount(5, 4, 0) == 12 && G::PatchCount(5, 4, 1) == 4, "odd level sizes and patch counts");
        Check(G::ControlSpacing(65, 0) == 1.0f && G::ControlSpacing(65, 2) == 4.0f && G::ControlSpacing(65, 4) == 16.0f, "control spacing per level");
        Check(Throws([] { G::LevelSize(1, 0); }) && Throws([] { G::LevelSize(65, 5); }), "invalid level input rejected");
    }

    // 7. Unexplored controls are refused before any height is read; malformed input is rejected.
    {
        G::Heights poison; poison.fill(std::numeric_limits<float>::quiet_NaN());
        G::Known known; known.fill(1);
        for (unsigned index = 0; index < 16; ++index) {
            G::Known partial = known; partial[index] = 0;
            const G::Sample sample = G::EvaluateKnown(poison, partial, 0.5f, 0.5f);
            Check(!sample.available && sample.height == 0.0f, "unexplored control denies the sample without reading heights");
        }
        Check(Throws([&] { G::EvaluateKnown(poison, known, 0.5f, 0.5f); }), "nonfinite known height rejected");
        G::Known bad = known; bad[3] = 2;
        G::Heights fine; fine.fill(1.0f);
        Check(Throws([&] { G::EvaluateKnown(fine, bad, 0.5f, 0.5f); }), "invalid known state rejected");
        Check(Throws([&] { G::Evaluate(fine, -0.01f, 0.5f); }) && Throws([&] { G::Evaluate(fine, 0.5f, 1.01f); }) &&
              Throws([&] { G::Evaluate(fine, std::numeric_limits<float>::infinity(), 0.5f); }), "domain outside [0,1] rejected");
        Check(Throws([&] { G::EvaluateKnown(poison, bad, 2.0f, 0.5f); }), "domain is validated before the known state");
        const G::Sample ok = G::EvaluateKnown(fine, known, 0.25f, 0.75f);
        Check(ok.available && std::fabs(ok.height - 1.0f) < 1e-6f, "fully known footprint evaluates");
    }

    // 8. Units.
    Check(G::ControlHeight(0.0f) == 0.0f && G::ControlHeight(1.0f) == (1.0f * 0.2f) * 255.0f, "height = alpha * 0.2 * 255");
    Check(std::fabs(G::ControlHeight(1.0f) - 51.0f) < 1e-5f, "full alpha is 51 world units");
    Check(Throws([] { G::ControlHeight(1.5f); }) && Throws([] { G::ControlHeight(std::numeric_limits<float>::quiet_NaN()); }), "invalid alpha rejected");
    {
        const G::WorldXY world = G::PatchWorldXY(0.5f, 0.25f, 4.0f, 4.0f, 8.0f, 12.0f, 64.0f, 128.0f);
        Check(world.x == 74.0f && std::fabs(world.y - 141.0f * 0.866f) < 1e-4f, "world xy = texel * (1, 0.866)");
        Check(G::RetailUnitY != 0.8660254f, "0.866 literal, not sqrt(3)/2");
    }

    std::printf("PASS_TERRAIN_BICUBIC_RETAIL checks=%llu surface_samples=%llu max_surface_error=%.3e basis=retail_exe_literals runtime_executed=0\n",
                g_checks, surfaceSamples, maxSurfaceError);
    return 0;
}
