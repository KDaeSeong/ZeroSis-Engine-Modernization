#pragma once
#include "OriginalWaterModel.h"
#include "OriginalWaterPackage.h"
#include "OriginalTerrainGeometry.h"
#include "OriginalTerrainBinding.h"

namespace ZeroSisPresentation { namespace OriginalWater {
// The parser validates the canonical 13 styles and nine 100-point profiles.
// Applying their Y ordinate as a lateral shoreline meander is a candidate.
inline double CoastProfileY(const std::vector<CoastStyle>& styles,const std::vector<CoastProfile>& profiles,
    LandStyle style,unsigned band,double t){
    Require(std::isfinite(t)&&t>=0&&t<=1&&band<3,"Invalid coast profile sample");
    const auto& definition=styles.at(static_cast<unsigned>(style));
    const auto& selected=band==0?definition.waterline:band==1?definition.lowBeach:definition.highBeach;
    if(selected.character==65535)return 0;
    const auto& points=profiles.at(selected.character).points;
    Require(points.size()==100,"Coast profile requires100 canonical points");
    const double coordinate=400*(1-t);
    const auto it=std::lower_bound(points.begin(),points.end(),coordinate,[](const SplinePoint& point,double x){return point.x>x;});
    if(it==points.begin())return it->y;if(it==points.end())return points.back().y;
    const auto& a=*(it-1);const auto& b=*it;return a.y+(b.y-a.y)*((coordinate-a.x)/(b.x-a.x));
}

inline Mesh BuildAtlasMesh(const Grid& grid,const OriginalTerrain::Atlas& atlas,const std::vector<CoastStyle>& styles,
    const std::vector<CoastProfile>& profiles,const MeshPolicy& policy=MeshPolicy{}){
    Require(styles.size()==13&&profiles.size()==9,"Water bridge requires the canonical coast library");
    for(unsigned i=0;i<styles.size();++i)Require(styles[i].name==StyleName(i),"Water bridge coast style order differs");
    for(const auto& profile:profiles){
        Require(profile.points.size()==100,"Water bridge coast profile size differs");
        for(std::size_t i=0;i<profile.points.size();++i){const auto& p=profile.points[i];
            Require(std::isfinite(p.x)&&std::isfinite(p.y)&&std::isfinite(p.z)&&p.z==0&&
                (i==0||profile.points[i-1].x>p.x),"Invalid water bridge coast profile points");
        }
    }
    auto mesh=BuildMesh(grid,[&](double x,double z){
        return static_cast<double>(OriginalTerrain::AtlasWorldHeight(atlas,x*64,-z/OriginalTerrain::RowSpacing*64));
    },[&](LandStyle style,unsigned band,double t){return CoastProfileY(styles,profiles,style,band,t);},policy);
    // Original Water PS uses raw global height h. Existing atlas height/scale
    // calibration is a candidate; colour-only geometry leaves ground depth intact.
    for(auto& vertex:mesh.vertices)if(vertex.kind==static_cast<float>(SurfaceKind::Water))
        vertex.depth=static_cast<float>((vertex.y-policy.lift)/OriginalTerrain::HeightWorldScaleCandidate+OriginalTerrain::HeightOffsetCandidate);
    return mesh;
}
}}
