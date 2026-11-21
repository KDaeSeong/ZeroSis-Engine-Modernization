namespace DS=OriginalDynamicShadow;
struct DynamicShadowConstants {
    XMFLOAT4X4 viewProjection;float placement[4],mapInfo[4],info[4];
};
static_assert(sizeof(DynamicShadowConstants)==112,"Dynamic shadow constant layout differs");
struct DynamicShadowMap {
    ComPtr<ID3D11Texture2D> depth;
    ComPtr<ID3D11DepthStencilView> depthView;
    ComPtr<ID3D11ShaderResourceView> depthResource;
    ComPtr<ID3D11VertexShader> groundVs,unitVs;
    ComPtr<ID3D11PixelShader> groundPs;
    ComPtr<ID3D11InputLayout> groundLayout,unitLayout;
    ComPtr<ID3D11Buffer> constants;
    DynamicShadowConstants parameters{};
    DS::Projection projection;
};
