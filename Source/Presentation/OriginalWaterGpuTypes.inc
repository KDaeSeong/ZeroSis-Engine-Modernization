namespace OW=OriginalWater;
struct WaterGeometry {
    bool riversOnly=false;
    OW::Grid key;
    std::weak_ptr<OriginalSurface> surface;
    ComPtr<ID3D11Buffer> vertices;
    std::vector<std::array<OW::DrawRange,3>> ranges;
};
struct WaterCatalog {
    std::wstring path;
    std::array<ComPtr<ID3D11ShaderResourceView>,14> textures;
    std::vector<OW::CoastStyle> styles;
    std::vector<OW::CoastProfile> profiles;
    ComPtr<ID3D11VertexShader> vs;ComPtr<ID3D11PixelShader> ps;
    ComPtr<ID3D11InputLayout> layout;ComPtr<ID3D11Buffer> constants;
    ComPtr<ID3D11SamplerState> wrapSampler,clampSampler;
    ComPtr<ID3D11DepthStencilState> depthReadOnly;
    ComPtr<ID3D11BlendState> alphaBlend;
    std::unique_ptr<WaterGeometry> geometry;
};
struct WaterConstants {float placement[4],mapInfo[4],shade[4],uvScales[4],eye[4],motion[4];};
static_assert(sizeof(WaterConstants)==96,"Original water draw constant buffer layout differs");
