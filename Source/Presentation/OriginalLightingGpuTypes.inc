namespace LG=OriginalLighting;
struct OriginalLightingConstants {
    float info[4],specularAxis[4],composition[4],screenLight[4],overlay[4];
};
static_assert(sizeof(OriginalLightingConstants)==80,"Original lighting constant layout differs");
struct LightingCatalog {
    std::wstring path;
    std::array<ComPtr<ID3D11ShaderResourceView>,5> sunlight,shadowlight,terrainLut;
    ComPtr<ID3D11SamplerState> clampSampler;
    ComPtr<ID3D11Buffer> constants;
};
