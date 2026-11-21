#pragma once
#include <array>
#include <cmath>
#include <stdexcept>

namespace ZeroSisPresentation { namespace OriginalCamera {
using Matrix=std::array<float,16>;
struct Vector {float x=0,y=0,z=0;};
constexpr float ResetNearPlane=1.0f,ResetFarPlane=10000.0f;
constexpr double DegreesToRadians=0.017453292519943295;
// The general camera projection/reset callsites are recovered. The actual
// world-camera instance, pose, FOV and map/world-unit calibration are not.
constexpr bool WorldCameraCalibrationVerified=false;
inline bool Finite(Vector value)noexcept{return std::isfinite(value.x)&&std::isfinite(value.y)&&std::isfinite(value.z);}
inline float Radians(float degrees){
    if(!std::isfinite(degrees)||degrees<=0||degrees>=180)
        throw std::invalid_argument("Invalid original camera FOV");
    // 0x8e4a9c..0x8e4acc widens float degrees, multiplies the double constant,
    // then narrows before calling D3DXMatrixPerspectiveFovRH.
    return static_cast<float>(static_cast<double>(degrees)*DegreesToRadians);
}
inline Matrix Perspective(float degrees,float aspect,float nearPlane,float farPlane){
    const float radians=Radians(degrees);
    if(!std::isfinite(aspect)||aspect<=0||!std::isfinite(nearPlane)||!std::isfinite(farPlane)||
       nearPlane<=0||farPlane<=nearPlane)
        throw std::invalid_argument("Invalid original camera projection inputs");
    const float scale=1.0f/std::tan(radians*0.5f);
    Matrix result{};result[0]=scale/aspect;result[5]=scale;
    result[10]=farPlane/(nearPlane-farPlane);result[11]=-1;result[14]=nearPlane*result[10];
    for(const auto value:result)if(!std::isfinite(value))throw std::invalid_argument("Original camera projection overflow");
    return result;
}
inline float Dot(Vector a,Vector b)noexcept{return (a.x*b.x+a.y*b.y)+a.z*b.z;}
inline Vector Cross(Vector a,Vector b)noexcept{return {a.y*b.z-a.z*b.y,a.z*b.x-a.x*b.z,a.x*b.y-a.y*b.x};}
inline Vector Unit(Vector value){
    if(!Finite(value))throw std::invalid_argument("Invalid original camera direction");
    const float lengthSquared=Dot(value,value);
    if(!std::isfinite(lengthSquared)||lengthSquared<=0)throw std::invalid_argument("Degenerate original camera direction");
    const float reciprocal=1.0f/std::sqrt(lengthSquared);
    return {value.x*reciprocal,value.y*reciprocal,value.z*reciprocal};
}
inline Matrix LookAt(Vector eye,Vector target,Vector up){
    if(!Finite(eye)||!Finite(target)||!Finite(up))throw std::invalid_argument("Invalid original camera pose");
    const Vector z=Unit({eye.x-target.x,eye.y-target.y,eye.z-target.z}),x=Unit(Cross(up,z)),y=Cross(z,x);
    Matrix result{{x.x,y.x,z.x,0,x.y,y.y,z.y,0,x.z,y.z,z.z,0,-Dot(x,eye),-Dot(y,eye),-Dot(z,eye),1}};
    for(const auto value:result)if(!std::isfinite(value))throw std::invalid_argument("Original camera pose overflow");
    return result;
}
// Source-level RH reference only. No D3DX/renderer call is executed here, and
// floating-point parity with its runtime-dispatched implementation is unproven.
}}
