namespace OSL=OriginalScreenLighting;
struct ScreenLightCatalog {
    std::wstring path;
    ComPtr<ID3D11ShaderResourceView> texture;
};
struct ScreenLightingGpu {
    ComPtr<ID3D11Buffer> constants;
    ComPtr<ID3D11SamplerState> sampler;
};
static_assert(sizeof(OSL::Constants)==32,"Screen reflection GPU layout differs");
