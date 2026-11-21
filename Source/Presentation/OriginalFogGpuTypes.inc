namespace OF=OriginalFog;
struct FogMask {
    OF::Grid key;
    ComPtr<ID3D11ShaderResourceView> texture;
    ComPtr<ID3D11SamplerState> sampler;
};
struct FogCatalog {
    std::wstring path;
    std::array<ComPtr<ID3D11ShaderResourceView>,6> textures;
    ComPtr<ID3D11ShaderResourceView> lut;
    std::array<float,3> colour;
    ComPtr<ID3D11VertexShader> vs;
    ComPtr<ID3D11PixelShader> ps,underlayPs;
    ComPtr<ID3D11Buffer> constants;
    ComPtr<ID3D11SamplerState> clampSampler,wrapSampler;
    ComPtr<ID3D11DepthStencilState> depthDisabled;
    std::unique_ptr<FogMask> mask;
};
struct FogConstants {
    XMFLOAT4X4 inverseViewProjection;
    float viewport[4],mapInfo[4],camera[4],distance[4],colour[4];
    float flow[3][4],phase[4],waterOverlay[4];
};
static_assert(sizeof(FogConstants)==224,"Original fog constant buffer layout differs");
