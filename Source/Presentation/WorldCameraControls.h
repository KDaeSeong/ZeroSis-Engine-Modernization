#pragma once

#include <cstdint>
#include <stdexcept>

namespace ZeroSisPresentation {

// Candidate presentation scale; these values are not retail camera calibration.
class WorldCameraZoom final {
public:
    static constexpr float Default = 56.0f;
    static constexpr float Minimum = 24.0f;
    static constexpr float Maximum = 112.0f;
    static constexpr float Step = 8.0f;
    static constexpr std::int32_t WheelUnitsPerNotch = 120;

    float TileWidth() const noexcept { return tileWidth_; }
    bool ZoomIn() noexcept { return SetTileWidth(tileWidth_ + Step); }
    bool ZoomOut() noexcept { return SetTileWidth(tileWidth_ - Step); }
    // Preserve signed WM_MOUSEWHEEL fractions across normal world redraws.
    bool ApplyWheelDelta(std::int32_t rawDelta) noexcept {
        const std::int64_t total = wheelRemainder_ + static_cast<std::int64_t>(rawDelta);
        const std::int64_t notches = total / WheelUnitsPerNotch;
        wheelRemainder_ = total % WheelUnitsPerNotch;
        return notches != 0 && SetTileWidth(tileWidth_ + static_cast<float>(notches) * Step);
    }
    void ResetWheelRemainder() noexcept { wheelRemainder_ = 0; }

private:
    bool SetTileWidth(float value) noexcept {
        const float bounded = value < Minimum ? Minimum : value > Maximum ? Maximum : value;
        const bool changed = bounded != tileWidth_;
        tileWidth_ = bounded;
        return changed;
    }

    float tileWidth_ = Default;
    std::int64_t wheelRemainder_ = 0;
};

inline int PanCameraCoordinate(int position, int delta, int span, bool wraps) {
    if (span <= 0 || position < 0 || position >= span)
        throw std::invalid_argument("Camera position must be inside a positive map span");
    const std::int64_t shifted = static_cast<std::int64_t>(position) + static_cast<std::int64_t>(delta);
    if (wraps) {
        const std::int64_t remainder = shifted % static_cast<std::int64_t>(span);
        return static_cast<int>(remainder < 0 ? remainder + span : remainder);
    }
    if (shifted < 0) return 0;
    if (shifted >= span) return span - 1;
    return static_cast<int>(shifted);
}

}  // namespace ZeroSisPresentation
