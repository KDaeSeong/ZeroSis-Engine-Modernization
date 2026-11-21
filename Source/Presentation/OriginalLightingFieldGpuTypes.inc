namespace LF=OriginalLightingField;
struct LightingField {
    ComPtr<ID3D11ShaderResourceView> normal,shadow;
};
struct LightingFieldConstants {float materials[8][4],origin[4],parameters[4],worldAdapter[4];};
static_assert(sizeof(LightingFieldConstants)==176,"Lighting field constant layout differs");
struct LightingFieldBaker {
    ComPtr<ID3D11VertexShader> heightVs,normalVs;
    ComPtr<ID3D11PixelShader> heightPs,normalPs;
    ComPtr<ID3D11InputLayout> heightLayout;
    ComPtr<ID3D11Buffer> vertices,indices,constants;
    ComPtr<ID3D11Texture2D> height;
    ComPtr<ID3D11RenderTargetView> heightView;
    ComPtr<ID3D11ShaderResourceView> heightResource;
    ComPtr<ID3D11SamplerState> wrapSampler;
    ComPtr<ID3D11DepthStencilState> depthDisabled;
};
