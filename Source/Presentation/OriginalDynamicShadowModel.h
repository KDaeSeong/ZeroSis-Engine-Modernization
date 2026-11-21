#pragma once
#include <algorithm>
#include <array>
#include <cmath>
#include <cstdint>
#include <stdexcept>

namespace ZeroSisPresentation { namespace OriginalDynamicShadow {
// Bounded isolated-renderer policy. Retail shadow camera, resolution and bias
// have not been captured; these values are not claims of retail equivalence.
constexpr unsigned CandidateResolution=2048;
constexpr double CandidateMargin=2.0;
constexpr float CandidateBias=0.0005f;
struct Vec3 {double x=0,y=0,z=0;};
inline bool Finite(Vec3 v){return std::isfinite(v.x)&&std::isfinite(v.y)&&std::isfinite(v.z);}
inline double Dot(Vec3 a,Vec3 b){return a.x*b.x+a.y*b.y+a.z*b.z;}
inline Vec3 Cross(Vec3 a,Vec3 b){return {a.y*b.z-a.z*b.y,a.z*b.x-a.x*b.z,a.x*b.y-a.y*b.x};}
inline Vec3 Normalize(Vec3 v){const double q=Dot(v,v);if(!Finite(v)||q<1e-16)throw std::runtime_error("Invalid shadow direction");
    const double r=1/std::sqrt(q);return {v.x*r,v.y*r,v.z*r};}
struct Bounds {Vec3 minimum{},maximum{};bool populated=false;
    void Add(Vec3 p){if(!Finite(p)||std::max({std::abs(p.x),std::abs(p.y),std::abs(p.z)})>4096)throw std::runtime_error("Shadow bounds exceed controlled domain");
        if(!populated){minimum=maximum=p;populated=true;return;}
        minimum={std::min(minimum.x,p.x),std::min(minimum.y,p.y),std::min(minimum.z,p.z)};
        maximum={std::max(maximum.x,p.x),std::max(maximum.y,p.y),std::max(maximum.z,p.z)};}
};
struct Projection {std::array<float,16> matrix{};unsigned resolution=0;bool enabled=false;};
inline Projection Fit(const Bounds& bounds,unsigned resolution=CandidateResolution,Vec3 sun={-1,2,-1}){
    if(resolution<16||resolution>4096||(resolution&(resolution-1)))throw std::runtime_error("Invalid shadow resolution");
    Projection result;result.resolution=resolution;if(!bounds.populated)return result;
    const auto s=Normalize(sun);const Vec3 f{-s.x,-s.y,-s.z};
    const auto r=Normalize(Cross(std::abs(f.y)>.99?Vec3{0,0,1}:Vec3{0,1,0},f)),u=Cross(f,r);
    Bounds projected;
    for(unsigned mask=0;mask<8;++mask){const Vec3 p{mask&1?bounds.maximum.x:bounds.minimum.x,
        mask&2?bounds.maximum.y:bounds.minimum.y,mask&4?bounds.maximum.z:bounds.minimum.z};
        projected.Add({Dot(p,r),Dot(p,u),Dot(p,f)});}
    // Reserve half a texel at each edge before snapping the centre; otherwise
    // a small-resolution target can clip a corner after a translated fit.
    const double snapReserve=static_cast<double>(resolution)/(resolution-1);
    const double width=(projected.maximum.x-projected.minimum.x+2*CandidateMargin)*snapReserve;
    const double height=(projected.maximum.y-projected.minimum.y+2*CandidateMargin)*snapReserve;
    const double nearPlane=projected.minimum.z-CandidateMargin,depth=projected.maximum.z-projected.minimum.z+2*CandidateMargin;
    const double stepX=width/resolution,stepY=height/resolution;
    const double cx=std::floor((projected.minimum.x+projected.maximum.x)*.5/stepX+.5)*stepX;
    const double cy=std::floor((projected.minimum.y+projected.maximum.y)*.5/stepY+.5)*stepY;
    const double values[16]={r.x*2/width,u.x*2/height,f.x/depth,0,r.y*2/width,u.y*2/height,f.y/depth,0,
        r.z*2/width,u.z*2/height,f.z/depth,0,-cx*2/width,-cy*2/height,-nearPlane/depth,1};
    for(unsigned i=0;i<16;++i)result.matrix[i]=static_cast<float>(values[i]);
    result.enabled=true;return result;
}
inline Vec3 Project(const Projection& p,Vec3 v){const auto& m=p.matrix;
    return {v.x*m[0]+v.y*m[4]+v.z*m[8]+m[12],v.x*m[1]+v.y*m[5]+v.z*m[9]+m[13],v.x*m[2]+v.y*m[6]+v.z*m[10]+m[14]};}
template<class DepthAt> double Occlusion(bool known,const Projection& projection,Vec3 world,double bias,DepthAt&& depthAt){
    // Unknown receivers must not read any projected texture data.
    if(!known||!projection.enabled)return 0;
    if(!Finite(world)||!std::isfinite(bias)||bias<0||bias>1)throw std::runtime_error("Invalid shadow receiver");
    const auto p=Project(projection,world);if(p.x< -1||p.x>1||p.y< -1||p.y>1||p.z<0||p.z>1)return 0;
    const double x=(p.x*.5+.5)*projection.resolution-.5,y=(.5-p.y*.5)*projection.resolution-.5;
    const int ix=static_cast<int>(std::floor(x)),iy=static_cast<int>(std::floor(y));const double fx=x-ix,fy=y-iy;
    double shadow=0;
    for(int dy=0;dy<2;++dy)for(int dx=0;dx<2;++dx){const int sx=ix+dx,sy=iy+dy;
        if(sx<0||sy<0||sx>=static_cast<int>(projection.resolution)||sy>=static_cast<int>(projection.resolution))continue;
        const double sample=depthAt(static_cast<unsigned>(sx),static_cast<unsigned>(sy));
        if(!std::isfinite(sample)||sample<0||sample>1)throw std::runtime_error("Invalid shadow depth sample");
        if(p.z-bias>sample)shadow+=(dx?fx:1-fx)*(dy?fy:1-fy);}
    return shadow;
}
inline double WaterAttenuation(double shadow,double strength){if(!std::isfinite(shadow)||!std::isfinite(strength)||strength<0||strength>1)
    throw std::runtime_error("Invalid water shadow input");return 1-.67*std::max(0.0,std::min(1.0,shadow))*strength;}
}}
