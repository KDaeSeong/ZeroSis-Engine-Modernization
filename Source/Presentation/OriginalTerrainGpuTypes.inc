namespace OT=OriginalTerrain;
struct LightingField;
struct OriginalGpuMesh {
    ComPtr<ID3D11Buffer> vertices;
    OT::ChunkSlots slots;
    bool dense=false;unsigned column=0,row=0;
    std::unique_ptr<LightingField> lightingField;
};
struct OriginalSurface {
    int width=0,height=0;bool wrapX=false,wrapY=false;std::uint32_t seed=0;
    std::vector<OT::Cell> cells;
    OT::Atlas atlas;
    // A weak lookup reuses overlapping visible meshes without accumulating
    // every historical camera window. Only current/candidate frames own them.
    std::vector<std::weak_ptr<OriginalGpuMesh>> meshes;
};
struct OriginalDraw {std::shared_ptr<OriginalGpuMesh> mesh;int column=0,row=0;};
struct OriginalGroundData {
    std::shared_ptr<OriginalSurface> surface;
    std::vector<OriginalDraw> draws;
    ComPtr<ID3D11ShaderResourceView> plotState,lightingSelectors;
};
struct OriginalCatalog {
    std::vector<OT::PackageRow> rows;
    std::vector<ComPtr<ID3D11ShaderResourceView>> textures;
    OT::PieceLibrary library;OT::MaterialTable table;
    std::shared_ptr<OriginalSurface> surface;
    ComPtr<ID3D11VertexShader> vs;ComPtr<ID3D11PixelShader> ps;
    ComPtr<ID3D11InputLayout> layout;
    ComPtr<ID3D11Buffer> constants,indices,quadIndices;
};
struct OriginalVertex {float x,y,z,u,v,light;std::uint32_t w0,w1;float nx,ny,nz;};
static_assert(sizeof(OriginalVertex)==44,"Original terrain vertex layout differs");
struct OriginalConstants {float materials[8][4],placement[4],mapInfo[4],textureOrigin[4],fogInfo[4];};
static_assert(sizeof(OriginalConstants)==192,"Original terrain constant buffer layout differs");
std::unique_ptr<OriginalCatalog> LoadOriginalCatalog(ID3D11Device* device,std::vector<unsigned char> bytes);
