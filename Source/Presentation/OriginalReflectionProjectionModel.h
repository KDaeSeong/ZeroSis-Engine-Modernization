#pragma once

// CPU-only row-vector reference for the original base-view reflection path.
// The caller must supply original frame bounds, the reflection axis and any
// current-world conversion. None is inferred from the current main camera.
#include <array>
#include <cmath>
#include <stdexcept>

namespace ZeroSisPresentation { namespace OriginalReflectionProjection {
using Matrix=std::array<float,16>;
struct Vector {float x=0,y=0,z=0;};
struct Homogeneous {float x=0,y=0,z=0,w=0;};
struct TexturePoint {float u=0,v=0;};
struct Span {float x=0,y=0;};
struct Plane {Vector normal{};float constant=0;};
struct FrameInputs {
    Vector minimum{},maximum{},axis{};
    bool supplied=false;
};
struct WorldAdapter {
    Matrix currentToOriginal{};
    bool supplied=false;
};
struct Projector {
    Vector center{},eye{};Span signedHalfSpan{};
    Matrix view{},projection{},viewProjection{};
};
constexpr float EyeDistance=5000.0f,NearPlane=30000.0f,FarPlane=-30000.0f;
constexpr bool WorldCameraCalibrationVerified=false;
constexpr bool OriginalClipPlaneVerified=false;
constexpr bool IndexedViewAdjustmentVerified=false;

namespace Detail {
inline void Require(bool value,const char* text){if(!value)throw std::invalid_argument(text);}
inline bool Finite(Vector value)noexcept{return std::isfinite(value.x)&&std::isfinite(value.y)&&std::isfinite(value.z);}
inline void Validate(const Matrix& value){for(const auto v:value)Require(std::isfinite(v),"Nonfinite reflection matrix");}
inline float Dot(Vector a,Vector b)noexcept{return (a.x*b.x+a.y*b.y)+a.z*b.z;}
inline Vector Cross(Vector a,Vector b)noexcept{return {a.y*b.z-a.z*b.y,a.z*b.x-a.x*b.z,a.x*b.y-a.y*b.x};}
inline Vector Unit(Vector value){
    Require(Finite(value),"Nonfinite reflection axis");
    const float square=Dot(value,value);
    Require(std::isfinite(square)&&square>0,"Degenerate reflection axis");
    const float reciprocal=1.0f/std::sqrt(square);
    const Vector result{value.x*reciprocal,value.y*reciprocal,value.z*reciprocal};
    Require(Finite(result),"Reflection axis overflow");return result;
}
inline Matrix LookAt(Vector eye,Vector target){
    const Vector z=Unit({eye.x-target.x,eye.y-target.y,eye.z-target.z});
    const Vector x=Unit(Cross({0,1,0},z)),y=Cross(z,x);
    const Matrix result{{x.x,y.x,z.x,0,x.y,y.y,z.y,0,x.z,y.z,z.z,0,-Dot(x,eye),-Dot(y,eye),-Dot(z,eye),1}};
    Validate(result);return result;
}
}

inline Matrix Multiply(const Matrix& a,const Matrix& b){
    Detail::Validate(a);Detail::Validate(b);Matrix result{};
    for(unsigned row=0;row<4;++row)for(unsigned column=0;column<4;++column)
        result[row*4+column]=((a[row*4]*b[column]+a[row*4+1]*b[4+column])+a[row*4+2]*b[8+column])+a[row*4+3]*b[12+column];
    Detail::Validate(result);return result;
}
inline Homogeneous Transform(Homogeneous value,const Matrix& matrix){
    Detail::Validate(matrix);
    Detail::Require(std::isfinite(value.x)&&std::isfinite(value.y)&&std::isfinite(value.z)&&std::isfinite(value.w),"Nonfinite reflection position");
    Homogeneous result;
    result.x=((value.x*matrix[0]+value.y*matrix[4])+value.z*matrix[8])+value.w*matrix[12];
    result.y=((value.x*matrix[1]+value.y*matrix[5])+value.z*matrix[9])+value.w*matrix[13];
    result.z=((value.x*matrix[2]+value.y*matrix[6])+value.z*matrix[10])+value.w*matrix[14];
    result.w=((value.x*matrix[3]+value.y*matrix[7])+value.z*matrix[11])+value.w*matrix[15];
    Detail::Require(std::isfinite(result.x)&&std::isfinite(result.y)&&std::isfinite(result.z)&&std::isfinite(result.w),"Reflection transform overflow");return result;
}
inline Projector Build(const FrameInputs& inputs){
    Detail::Require(inputs.supplied,"Original reflection frame inputs unavailable");
    Detail::Require(Detail::Finite(inputs.minimum)&&Detail::Finite(inputs.maximum)&&Detail::Finite(inputs.axis),"Nonfinite reflection frame inputs");
    Detail::Require(inputs.minimum.x<inputs.maximum.x&&inputs.minimum.y<inputs.maximum.y&&inputs.minimum.z<=inputs.maximum.z,"Invalid original reflection bounds");
    Projector result;
    // 0x615960..0x615a64 uses (max+min)*.5 and XY (min-max)*.5.
    result.center={(inputs.maximum.x+inputs.minimum.x)*0.5f,(inputs.maximum.y+inputs.minimum.y)*0.5f,(inputs.maximum.z+inputs.minimum.z)*0.5f};
    result.signedHalfSpan={(inputs.minimum.x-inputs.maximum.x)*0.5f,(inputs.minimum.y-inputs.maximum.y)*0.5f};
    result.eye={result.center.x-inputs.axis.x*EyeDistance,result.center.y-inputs.axis.y*EyeDistance,result.center.z-inputs.axis.z*EyeDistance};
    Detail::Require(Detail::Finite(result.center)&&std::isfinite(result.signedHalfSpan.x)&&std::isfinite(result.signedHalfSpan.y)&&Detail::Finite(result.eye),"Original reflection bounds overflow");
    result.view=Detail::LookAt(result.eye,result.center);
    // D3DXMatrixOrthoOffCenterRH receives signed left/bottom and their
    // negations, with near=+30000 and far=-30000; do not sort depth planes.
    const float left=result.signedHalfSpan.x,right=-left,bottom=result.signedHalfSpan.y,top=-bottom;
    result.projection[0]=2.0f/(right-left);result.projection[5]=2.0f/(top-bottom);
    result.projection[10]=1.0f/(NearPlane-FarPlane);
    result.projection[12]=(left+right)/(left-right);result.projection[13]=(top+bottom)/(bottom-top);
    result.projection[14]=NearPlane/(NearPlane-FarPlane);result.projection[15]=1;
    Detail::Validate(result.projection);
    result.viewProjection=Multiply(result.view,result.projection);return result;
}

inline void Validate(const WorldAdapter& adapter){
    Detail::Require(adapter.supplied,"Current-to-original world adapter unavailable");Detail::Validate(adapter.currentToOriginal);
    const auto& m=adapter.currentToOriginal;
    Detail::Require(m[3]==0&&m[7]==0&&m[11]==0&&m[15]==1,"Reflection world adapter must be affine");
    const float determinant=m[0]*(m[5]*m[10]-m[6]*m[9])-m[1]*(m[4]*m[10]-m[6]*m[8])+m[2]*(m[4]*m[9]-m[5]*m[8]);
    Detail::Require(std::isfinite(determinant)&&determinant!=0,"Singular reflection world adapter");
}
inline Matrix ForCurrentWorld(const WorldAdapter& adapter,const Matrix& originalMatrix){
    Validate(adapter);return Multiply(adapter.currentToOriginal,originalMatrix);
}
inline TexturePoint WaterTexturePoint(Vector originalPosition,const Matrix& originalViewProjection){
    const auto clip=Transform({originalPosition.x,originalPosition.y,originalPosition.z,1},originalViewProjection);
    Detail::Require(clip.w!=0,"Zero reflection projection divisor");
    // WaterShader_2 PS cb1[22..25]: divide XY by W, then (.5,-.5)
    // and (-.5,-.5). Preserve negative UVs for the separate WRAP sampler.
    const TexturePoint result{clip.x/clip.w*0.5f-0.5f,clip.y/clip.w*-0.5f-0.5f};
    Detail::Require(std::isfinite(result.u)&&std::isfinite(result.v),"Reflection UV overflow");return result;
}
inline TexturePoint WaterTexturePointCurrent(Vector currentPosition,const WorldAdapter& adapter,const Projector& projector){
    return WaterTexturePoint(currentPosition,ForCurrentWorld(adapter,projector.viewProjection));
}
inline Plane ToCurrentPlane(const WorldAdapter& adapter,Plane originalPlane){
    Validate(adapter);Detail::Require(Detail::Finite(originalPlane.normal)&&std::isfinite(originalPlane.constant),"Invalid explicit original plane");
    Detail::Require(Detail::Dot(originalPlane.normal,originalPlane.normal)>0,"Degenerate explicit original plane");
    const auto& m=adapter.currentToOriginal;
    const auto n=originalPlane.normal;const float d=originalPlane.constant;
    Plane result{{((m[0]*n.x+m[1]*n.y)+m[2]*n.z)+m[3]*d,
                  ((m[4]*n.x+m[5]*n.y)+m[6]*n.z)+m[7]*d,
                  ((m[8]*n.x+m[9]*n.y)+m[10]*n.z)+m[11]*d},
                  ((m[12]*n.x+m[13]*n.y)+m[14]*n.z)+m[15]*d};
    Detail::Require(Detail::Finite(result.normal)&&std::isfinite(result.constant),"Explicit reflection plane overflow");return result;
}
inline float PlaneValue(Vector position,Plane plane){
    Detail::Require(Detail::Finite(position)&&Detail::Finite(plane.normal)&&std::isfinite(plane.constant),"Invalid explicit plane evaluation");
    const float result=Detail::Dot(position,plane.normal)+plane.constant;
    Detail::Require(std::isfinite(result),"Explicit plane evaluation overflow");return result;
}
// The plane helpers preserve a caller-supplied affine half-space; they do not
// claim that the original Raw pass clips at the candidate current water plane.
// D3DX float implementation parity and indexed-view offsets remain unverified.
}}
