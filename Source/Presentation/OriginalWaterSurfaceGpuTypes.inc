namespace WS=OriginalWater::Surface;
namespace WL=OriginalWaterLean;
namespace WO=OriginalWaterOptics;
namespace WB=OriginalWaterSurfaceBinding;
struct SurfaceTargets {
    unsigned width=0,height=0,mapWidth=0,reflectionWidth=0,reflectionHeight=0;
    XMFLOAT4X4 reflectionViewProjection{};
    bool reflectionProjectionValid=false;
    ComPtr<ID3D11Texture2D> reflectionColor,reflectionDepth;
    ComPtr<ID3D11RenderTargetView> reflectionView,reflectionRawView;
    ComPtr<ID3D11DepthStencilView> reflectionDepthView;
    ComPtr<ID3D11ShaderResourceView> reflectionResource;
};
struct WaterSurfaceGeometry {
    OW::Grid key;std::weak_ptr<OriginalSurface> surface;
    ComPtr<ID3D11Buffer> vertices;ComPtr<ID3D11ShaderResourceView> waterMask;
    std::vector<std::array<std::vector<OW::DrawRange>,2>> ranges;
};
struct WaterSurfaceCatalog {
    std::wstring path;std::array<ComPtr<ID3D11ShaderResourceView>,2> lean;
    ComPtr<ID3D11VertexShader> vs;ComPtr<ID3D11PixelShader> ps;
    ComPtr<ID3D11InputLayout> layout;ComPtr<ID3D11Buffer> constants;
    std::array<ComPtr<ID3D11BlendState>,2> originalAlphaBlend;
    WO::CandidateOpticsPolicy optics;
    std::unique_ptr<WaterSurfaceGeometry> geometry;
    std::unique_ptr<SurfaceTargets> targets;
};
struct WaterSurfaceConstants {
    XMFLOAT4X4 reflectionViewProjection;
    float placement[4],mapInfo[4],eye[4],viewport[4],reflection[4],optics[4],uvScales[4],motion[4];
    float light0[4],light1[4],absorption[4],warp0[4],warp1[4];
    float lightColour0[4],lightColour1[4],shadow[4];
    float fogDistance[4],fogColour[4],waterOverlay[4];
};
static_assert(sizeof(WaterSurfaceConstants)==368,"Water surface constant layout differs");
