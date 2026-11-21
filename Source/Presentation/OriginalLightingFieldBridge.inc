namespace FM=OriginalLighting::Field;
namespace FB=OriginalLighting::FieldBinding;

void PrepareLightingFields(const WorldView& view,Cache& cache,const OriginalGroundData& ground){
    Require(ground.surface!=nullptr&&cache.original!=nullptr,"Lighting fields require original terrain ownership");
    const bool missing=std::any_of(ground.draws.begin(),ground.draws.end(),
        [](const OriginalDraw& draw){return draw.mesh->slots.count!=0&&!draw.mesh->lightingField;});
    // A presentation-only refresh never captures another domain, samples
    // heights, allocates a field or invokes either private bake pass.
    if(!missing)return;
    const auto domain=FM::CaptureDomain(view);
    FM::ShadowParams parameters;
    parameters.directionX=FB::ShadowDirectionX;parameters.directionY=FB::ShadowDirectionY;
    parameters.texelWorldX=FB::TexelWorldX;parameters.texelWorldY=FB::TexelWorldY;
    parameters.heightScale=FB::ShadowHeightScale;parameters.heightOffset=FB::ShadowHeightOffset;
    parameters.biasAndStrength=FB::ShadowBiasAndStrength;
    if(!cache.lightingFieldBaker)cache.lightingFieldBaker=LoadLightingFieldBaker(cache);
    for(const auto& draw:ground.draws){
        auto& mesh=*draw.mesh;if(mesh.slots.count==0||mesh.lightingField)continue;
        const FM::TileSpec supportSpec{mesh.column,mesh.row,FB::TileTexels,2};
        const auto known=FM::BuildKnownSupport(domain,ground.surface->atlas,supportSpec);
        const FM::TileSpec shadowSpec{mesh.column,mesh.row,FB::TileTexels,1};
        const auto tile=FM::BuildShadowTile(domain,ground.surface->atlas,shadowSpec,parameters);
        Require(known.size()==FB::HeightSide*FB::HeightSide&&tile.width==FB::NormalSide&&tile.height==FB::NormalSide,
            "Lighting field producer dimensions differ from the shader");
        std::vector<std::uint16_t> shadow;shadow.reserve(tile.values.size());
        for(const auto value:tile.values)shadow.push_back(FM::ToUnorm16(value));
        auto candidate=BuildLightingField(cache,*cache.lightingFieldBaker,*cache.original,*ground.surface,
            mesh,known,shadow,FB::NormalStrength);
        Require(candidate&&candidate->normal.Get()&&candidate->shadow.Get(),"Incomplete lighting field candidate");
        // The old field is never moved from before a complete replacement is
        // available. Wrapped draw images share this canonical mesh/field.
        mesh.lightingField=std::move(candidate);
    }
}
