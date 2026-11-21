// Exercises the actual presentation-only controls. No SDK, window or GPU API.
#include "../Source/Presentation/WorldCameraControls.h"

#include <cstdio>
#include <initializer_list>
#include <limits>
#include <stdexcept>
#include <utility>

namespace {
using ZeroSisPresentation::PanCameraCoordinate;
using ZeroSisPresentation::WorldCameraZoom;
unsigned checks = 0, cases = 0;

static_assert(WorldCameraZoom::Default == 56.0f, "Default scale changed");
static_assert(WorldCameraZoom::Minimum == 24.0f, "Minimum scale changed");
static_assert(WorldCameraZoom::Maximum == 112.0f, "Maximum scale changed");
static_assert(WorldCameraZoom::Step == 8.0f, "Candidate step changed");
static_assert(noexcept(std::declval<const WorldCameraZoom&>().TileWidth()), "Query must be noexcept");
static_assert(noexcept(std::declval<WorldCameraZoom&>().ZoomIn()), "ZoomIn must be noexcept");
static_assert(noexcept(std::declval<WorldCameraZoom&>().ZoomOut()), "ZoomOut must be noexcept");

void Check(bool value, const char* reason) {
    ++checks;
    if (!value) throw std::runtime_error(reason);
}

void Zoom() {
    ++cases;
    WorldCameraZoom zoom;
    Check(zoom.TileWidth() == 56.0f, "Default construction changed");
    Check(zoom.ZoomIn() && zoom.TileWidth() == 64.0f, "ZoomIn must enlarge tile width");
    Check(zoom.ZoomOut() && zoom.TileWidth() == 56.0f, "One-step round trip failed");
    Check(zoom.ZoomOut() && zoom.TileWidth() == 48.0f, "ZoomOut must reduce tile width");
    Check(zoom.ZoomIn() && zoom.TileWidth() == 56.0f, "Reverse round trip failed");

    ++cases;
    for (unsigned i = 0; i < 4; ++i) Check(zoom.ZoomOut(), "Minimum reached too early");
    Check(zoom.TileWidth() == 24.0f, "Four steps from default must reach minimum");
    const float levels[] = {32, 40, 48, 56, 64, 72, 80, 88, 96, 104, 112};
    for (float level : levels) {
        Check(zoom.ZoomIn(), "Ascending level must report change");
        Check(zoom.TileWidth() == level, "Ascending scale skipped a level");
    }
    for (unsigned i = 0; i < 256; ++i) {
        Check(!zoom.ZoomIn(), "Maximum must report no change");
        Check(zoom.TileWidth() == 112.0f, "Maximum drifted during repeated input");
    }
    ++cases;
    const float descending[] = {104, 96, 88, 80, 72, 64, 56, 48, 40, 32, 24};
    for (float level : descending) {
        Check(zoom.ZoomOut(), "Descending level must report change");
        Check(zoom.TileWidth() == level, "Descending scale skipped a level");
    }
    for (unsigned i = 0; i < 256; ++i) {
        Check(!zoom.ZoomOut(), "Minimum must report no change");
        Check(zoom.TileWidth() == 24.0f, "Minimum drifted during repeated input");
    }
    ++cases;
    for (unsigned i = 0; i < 4; ++i) Check(zoom.ZoomIn(), "Return from minimum failed");
    Check(zoom.TileWidth() == 56.0f, "Full-range traversal did not restore default");
    const WorldCameraZoom retained = zoom;
    Check(retained.TileWidth() == zoom.TileWidth(), "Value copy lost presentation scale");
}

void PanBoundaries() {
    constexpr int hi = (std::numeric_limits<int>::max)();
    constexpr int lo = (std::numeric_limits<int>::min)();
    struct Row { int position, delta, span; bool wraps; int expected; };
    const Row rows[] = {
        {0, 0, 7, false, 0}, {6, 0, 7, true, 6},
        {0, -3, 7, false, 0}, {6, 3, 7, false, 6},
        {0, -3, 7, true, 4}, {6, 3, 7, true, 2},
        {1, -17, 5, true, 4}, {3, 18, 5, true, 1},
        {2, 15, 5, true, 2}, {2, -15, 5, true, 2},
        {0, hi, 1, false, 0}, {0, lo, 1, false, 0},
        {0, hi, 1, true, 0}, {0, lo, 1, true, 0},
        {0, hi, 2, true, 1}, {0, lo, 2, true, 0},
        {0, hi, 11, true, 1}, {0, lo, 11, true, 9},
        {10, hi, 11, true, 0}, {10, lo, 11, true, 8},
        {hi - 1, hi, hi, false, hi - 1},
        {hi - 1, lo, hi, false, 0},
        {hi - 1, hi, hi, true, hi - 1},
        {hi - 1, lo, hi, true, hi - 2},
        {0, hi, hi, true, 0}, {0, lo, hi, true, hi - 1},
        {1, lo, hi, true, 0}, {hi - 1, -hi, hi, true, hi - 1},
    };
    for (const auto& row : rows) {
        ++cases;
        Check(PanCameraCoordinate(row.position, row.delta, row.span, row.wraps) == row.expected,
              "Pan boundary or overflow result differs");
    }
}

void InvalidPanInputs() {
    constexpr int hi = (std::numeric_limits<int>::max)();
    constexpr int lo = (std::numeric_limits<int>::min)();
    struct Row { int position, delta, span; };
    const Row rows[] = {{0, 0, 0}, {0, hi, -1}, {0, lo, lo}, {-1, 3, 7},
                        {7, -3, 7}, {hi, lo, hi}, {lo, hi, 7}};
    for (const auto& row : rows) for (bool wraps : {false, true}) {
        ++cases;
        bool rejected = false;
        try { (void)PanCameraCoordinate(row.position, row.delta, row.span, wraps); }
        catch (const std::invalid_argument&) { rejected = true; }
        Check(rejected, "Invalid coordinate/span was not rejected with invalid_argument");
    }
}

void AxisIndependenceAndRepeatedTravel() {
    for (bool wrapX : {false, true}) for (bool wrapY : {false, true}) {
        ++cases;
        int x = 0, y = 8;
        x = PanCameraCoordinate(x, -3, 7, wrapX);
        Check(x == (wrapX ? 4 : 0) && y == 8, "Horizontal pan changed Y or used Y wrapping");
        y = PanCameraCoordinate(y, 3, 9, wrapY);
        Check(x == (wrapX ? 4 : 0) && y == (wrapY ? 2 : 8), "Vertical pan used X wrapping");
        x = PanCameraCoordinate(x, 3, 7, wrapX);
        y = PanCameraCoordinate(y, -3, 9, wrapY);
        Check(x == (wrapX ? 0 : 3) && y == (wrapY ? 8 : 5), "Independent reverse pan failed");
    }
    ++cases;
    int wrapped = 0, clamped = 0;
    for (unsigned i = 0; i < 1000; ++i) {
        wrapped = PanCameraCoordinate(wrapped, -3, 7, true);
        clamped = PanCameraCoordinate(clamped, -3, 7, false);
        Check(wrapped >= 0 && wrapped < 7 && clamped == 0, "Repeated negative pan escaped bounds");
    }
    for (unsigned i = 0; i < 1000; ++i) {
        wrapped = PanCameraCoordinate(wrapped, 3, 7, true);
        clamped = PanCameraCoordinate(clamped, 3, 7, false);
        Check(wrapped >= 0 && wrapped < 7 && clamped >= 0 && clamped <= 6,
              "Repeated positive pan escaped bounds");
    }
    Check(wrapped == 0 && clamped == 6, "Repeated round trip or upper clamp failed");
}
}  // namespace

int main() {
    try {
        Zoom();
        PanBoundaries();
        InvalidPanInputs();
        AxisIndependenceAndRepeatedTravel();
        std::printf("WORLD_CAMERA_CONTROLS_PASS checks=%u cases=%u GAMECORE_LOADED=false HWND_CREATED=false GPU_USED=false\n",
                    checks, cases);
        return 0;
    } catch (const std::exception& error) {
        std::fprintf(stderr, "WORLD_CAMERA_CONTROLS_FAIL checks=%u cases=%u reason=%s\n", checks, cases, error.what());
        return 1;
    }
}
