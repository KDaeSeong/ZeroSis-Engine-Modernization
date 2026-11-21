#pragma once

#include <cstdint>
#include <string>
#include <vector>

struct ID3D11Device;
struct ID3D11DeviceContext;
struct ID3D11Texture2D;

namespace ZeroSisPresentation {

constexpr std::uint32_t kSolidRectangleTexture = 0xffffffffu;
constexpr std::uint32_t kMaxSceneLines = 8192u;

// POD packet record. Rectangles are left, top, right, bottom; colors are RGBA in [0, 1].
struct Sprite {
    std::uint64_t controlKey;
    std::uint32_t textureIndex;
    float sourceRect[4];
    float targetRect[4];
    float clipRect[4];
    float tintRGBA[4];
};

struct HitRecord {
    std::uint64_t controlKey;
    float bounds[4];
};

// Per-pixel world picking table. Pixel index 0 is empty; index N resolves to
// keys[N-1]. Kept out of retained scene packets because this belongs to the
// live world renderer, not the retained UI asset format.
struct PixelHitMap {
    std::vector<std::uint32_t> indices;
    std::vector<std::uint64_t> keys;
};

struct Texture {
    std::wstring path;
};

// Owned live-scene strokes. The immutable ZSUPIX01/02 packet formats do not
// contain these records. Lines at an equal anchor retain their vector order.
struct SceneLine {
    float start[2];
    float end[2];
    float width;
    float tintRGBA[4];
    float clipRect[4];
    std::uint32_t beforeSprite;
};

struct Scene {
    std::uint32_t width;
    std::uint32_t height;
    std::vector<Texture> textures;
    std::vector<Sprite> sprites;
    std::vector<HitRecord> hits;
    std::vector<HitRecord> scrolls;
    PixelHitMap pixelHits;
    std::vector<SceneLine> lines;
};

// Reads ZSUPIX01/ZSUPIX02 packets and owns all decoded strings and records. The packet format is
// little-endian; texture paths are strict UTF-8 and relative paths resolve beside the packet.
bool LoadScenePacket(const std::wstring& packetPath, Scene* scene, std::wstring* error);

// Renders retained atlas sprites and explicit solid rectangles to an offscreen PNG using
// Direct2D composition and WIC decode/encode. No game UI window or SDK object is involved.
bool RenderToPng(const Scene& scene, const std::wstring& pngPath, std::wstring* error);

// Composites a retained Scene directly into an externally owned D3D11 texture.
// The texture must be a single-sample BGRA8 DXGI surface created by `device`,
// with D3D11_BIND_RENDER_TARGET, and within the renderer's image limits. The
// caller keeps ownership of device/context/target and must unbind target from
// D3D before calling; the function does not Present or alter the swap chain.
// The target is cleared transparent, then sprites are drawn in packet order
// using the same clipping, UV, tint, and premultiplied-alpha rules as PNG mode.
bool RenderSceneToD3D11Texture(const Scene& scene, ID3D11Device* device,
                               ID3D11DeviceContext* context, ID3D11Texture2D* target,
                               std::wstring* error);

// Same composition rules, preserving the candidate's existing world pixels.
bool OverlaySceneOnD3D11Texture(const Scene& scene, ID3D11Device* device,
                                ID3D11DeviceContext* context, ID3D11Texture2D* target,
                                std::wstring* error);

// Explicit diagnostic readback. Refuses to overwrite an existing PNG.
bool CaptureD3D11TextureToPng(ID3D11Device* device, ID3D11DeviceContext* context,
                             ID3D11Texture2D* texture, const std::wstring& png,
                             std::wstring* error);

}  // namespace ZeroSisPresentation
