#pragma once
#include <cstdint>

namespace ZeroSisPresentation {
// Numeric Win32 virtual-key values keep this owner policy independent of HWNDs.
inline bool ShouldQueueBitmapGameplayNavigationKey(bool enabled,std::uint32_t key) noexcept {
    if(!enabled)return false;
    switch(key){
    case 0x09: // Tab
    case 0x20: // Space
    case 0x21: // Page Up
    case 0x22: // Page Down
    case 0x23: // End
    case 0x24: // Home
    case 0x25: // Left
    case 0x26: // Up
    case 0x27: // Right
    case 0x28: // Down
    case 0x74: // F5
        return true;
    default:return false;
    }
}
}
