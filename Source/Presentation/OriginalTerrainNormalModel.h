#pragma once
#include <array>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <stdexcept>

namespace ZeroSisPresentation { namespace OriginalTerrainNormal {

struct Vec3 { float x=0.0f,y=0.0f,z=1.0f; };
// Original heightmap fields +a8/+ac/+b0. Mapping the current atlas/world units
// onto these values is a separate calibration policy, not a recovered constant.
struct Metrics { float stepX=1.0f,stepY=1.0f,heightScale=1.0f; };
struct KnownWindow {
    std::array<std::uint16_t,25> height{};
    bool centerKnown=false;
    unsigned substitutedUnknown=0;
};
struct Derivatives { float x=0.0f,y=0.0f; };
struct HalfNormal { std::array<std::uint16_t,4> value{}; };

inline void Require(bool condition,const char* message){if(!condition)throw std::invalid_argument(message);}
inline void Validate(const Metrics& value){
    Require(std::isfinite(value.stepX)&&value.stepX>0.0f&&std::isfinite(value.stepY)&&value.stepY>0.0f&&
        std::isfinite(value.heightScale)&&value.heightScale>=0.0f,"Invalid terrain normal metric");
}
inline unsigned Index(int x,int y){return static_cast<unsigned>((x+2)*5+y+2);}

// Consumers must not even fetch the numeric height of an unknown neighbour.
// Substituting the known centre is an explicit privacy policy; the original
// executable assumes access to the complete map and does not impose this rule.
template<class Known,class ReadHeight>
inline KnownWindow CaptureKnownWindow(Known known,ReadHeight readHeight){
    KnownWindow result;
    if(!known(0,0))return result;
    result.centerKnown=true;const std::uint16_t center=readHeight(0,0);
    for(int x=-2;x<=2;++x)for(int y=-2;y<=2;++y){
        const unsigned at=Index(x,y);
        if(x==0&&y==0)result.height[at]=center;
        else if(known(x,y))result.height[at]=readHeight(x,y);
        else{result.height[at]=center;++result.substitutedUnknown;}
    }
    return result;
}

inline Vec3 Normalize(float x,float y,float z){
    // The imported retail D3DX normalization dispatch/precision is not proven.
    // Double length and a finite up-vector fallback are explicit current policy.
    if(!std::isfinite(x)||!std::isfinite(y)||!std::isfinite(z))return {};
    const double length=std::sqrt(static_cast<double>(x)*x+static_cast<double>(y)*y+static_cast<double>(z)*z);
    if(!std::isfinite(length)||length<=0.0)return {};
    return {static_cast<float>(x/length),static_cast<float>(y/length),static_cast<float>(z/length)};
}
inline Vec3 FromDerivatives(Derivatives value,const Metrics& metric){
    Validate(metric);
    // The original cross product is Z-up, before any renderer Y-up conversion.
    return Normalize(metric.stepY*(value.x*metric.heightScale),metric.stepX*(value.y*metric.heightScale),
                     metric.stepY*metric.stepX);
}
inline int SignedHalfDifference(std::uint16_t positive,std::uint16_t negative){
    const int difference=static_cast<int>(positive)-static_cast<int>(negative);
    // x86 SAR rounds a negative odd difference downward, unlike integer / 2.
    return difference>=0?difference/2:-((-difference+1)/2);
}
inline float Height(std::uint16_t value){return static_cast<float>(value)*(1.0f/255.0f);}
inline float KernelA(unsigned at){
    static const float weights[5]={0.0228f,0.2293f,0.4948f,0.2293f,0.0228f};return weights[at];
}
inline float KernelB(unsigned at){
    static const float weights[5]={0.0702f,0.3526f,0.0f,-0.3526f,-0.0702f};return weights[at];
}
inline float BulkRange(float reference,float height){
    float q=reference-height;q=q*q;q=q*(-3.3333332538604736f);q=q*0.00006103515625f;
    float value=q*q;value=value*0.5f;value=value+q;value=value+1.0f;return value*1.03f;
}
inline float ScalarRange(float reference,float height){
    float q=(reference-height)*0.0078125f;q=q*q;q=q*(-3.3333332538604736f);
    const float squared=q*q;
    float value=squared*q;value=value*0.1666666716337204f;
    value=value+squared*0.5f;value=value+q;value=value+1.0f;
    return value*static_cast<float>(1.0/std::sqrt(0.9424778597544758));
}
inline Derivatives BulkDerivatives(const std::array<std::uint16_t,25>& raw){
    const float center=Height(raw[Index(0,0)]);
    const float dx=static_cast<float>(SignedHalfDifference(raw[Index(1,0)],raw[Index(-1,0)]))*(1.0f/255.0f);
    const float dy=static_cast<float>(SignedHalfDifference(raw[Index(0,1)],raw[Index(0,-1)]))*(1.0f/255.0f);
    float referenceX=center+dx*(-2.0f),referenceY=center+dy*(-2.0f);
    float numeratorX=0.0f,denominatorX=0.0f,numeratorY=0.0f,denominatorY=0.0f;
    // 0x728240 uses the four nonzero derivative rows/columns, omits corners,
    // and advances each reference by literal 1.0. Do not replace it by an
    // ideal Gaussian, by a derivative increment, or by the scalar fallback.
    for(unsigned outer=0;outer<5;++outer){
        if(outer==2){referenceX=referenceX+1.0f;referenceY=referenceY+1.0f;continue;}
        for(unsigned inner=0;inner<5;++inner){
            if((outer==0||outer==4)&&(inner==0||inner==4))continue;
            const float coefficientX=KernelB(outer)*KernelA(inner);
            const float hx=Height(raw[outer*5+inner]);
            const float hy=Height(raw[inner*5+outer]);
            const float wx=BulkRange(referenceX,hx)*coefficientX;
            const float wy=BulkRange(referenceY,hy)*coefficientX;
            numeratorX=numeratorX+wx*hx;denominatorX=denominatorX+std::abs(wx);
            numeratorY=numeratorY+wy*hy;denominatorY=denominatorY+std::abs(wy);
        }
        referenceX=referenceX+1.0f;referenceY=referenceY+1.0f;
    }
    if(!std::isfinite(denominatorX)||!std::isfinite(denominatorY)||denominatorX<=0.0f||denominatorY<=0.0f)return {};
    return {numeratorX/denominatorX,numeratorY/denominatorY};
}
inline Derivatives ScalarDerivatives(const std::array<std::uint16_t,25>& raw){
    const float center=Height(raw[Index(0,0)]);
    const float refX=center+static_cast<float>(SignedHalfDifference(raw[Index(1,0)],raw[Index(-1,0)]))*(1.0f/255.0f);
    const float refY=center+static_cast<float>(SignedHalfDifference(raw[Index(0,1)],raw[Index(0,-1)]))*(1.0f/255.0f);
    float numeratorX=0.0f,denominatorX=0.0f,numeratorY=0.0f,denominatorY=0.0f;
    for(unsigned x=0;x<5;++x)for(unsigned y=0;y<5;++y){
        const float h=Height(raw[x*5+y]);
        const float wx=ScalarRange(refX,h)*(KernelA(y)*KernelB(x));
        const float wy=ScalarRange(refY,h)*(KernelB(y)*KernelA(x));
        numeratorX=numeratorX+wx*h;denominatorX=denominatorX+std::abs(wx);
        numeratorY=numeratorY+wy*h;denominatorY=denominatorY+std::abs(wy);
    }
    if(!std::isfinite(denominatorX)||!std::isfinite(denominatorY)||denominatorX<=0.0f||denominatorY<=0.0f)return {};
    return {numeratorX/denominatorX,numeratorY/denominatorY};
}
inline Vec3 BaseNormal(const KnownWindow& window,const Metrics& metric){
    Validate(metric);if(!window.centerKnown)return {};return FromDerivatives(BulkDerivatives(window.height),metric);
}
inline Vec3 ScalarFallbackNormal(const KnownWindow& window,const Metrics& metric){
    Validate(metric);if(!window.centerKnown)return {};return FromDerivatives(ScalarDerivatives(window.height),metric);
}
inline Vec3 DecodeCachedXY(std::uint8_t x,std::uint8_t y){
    const float nx=(static_cast<float>(x)-128.0f)*(1.0f/255.0f);
    const float ny=(static_cast<float>(y)-128.0f)*(1.0f/255.0f);
    // Exact getter 0x719ba0: no factor two and no post-decode normalization.
    const float z=static_cast<float>(std::sqrt(1.0-static_cast<double>(nx)*nx-static_cast<double>(ny)*ny));
    return {nx,ny,z};
}
inline std::uint16_t PackNormalHalf(float value){
    Require(std::isfinite(value)&&std::abs(value)<=1.0f,"Only finite unit-normal components may be packed");
    std::uint32_t bits=0;std::memcpy(&bits,&value,sizeof(bits));
    const std::uint32_t sign=(bits>>16)&0x8000u;bits&=0x7fffffffu;
    std::uint32_t result=0;
    if(bits<0x38800000u){
        const unsigned shift=113u-(bits>>23);
        std::uint32_t mantissa=(bits&0x7fffffu)|0x800000u;
        mantissa=shift>31?0u:mantissa>>shift;
        result=(mantissa+((mantissa>>13)&1u)+0xfffu)>>13;
    }else result=(bits+((bits>>13)&1u)-0x37fff001u)>>13;
    return static_cast<std::uint16_t>(sign|result);
}
inline float UnpackNormalHalf(std::uint16_t value){
    const unsigned sign=value>>15,exponent=(value>>10)&31u,mantissa=value&1023u;
    Require(exponent!=31u,"Nonfinite half input");
    const float magnitude=exponent?std::ldexp(1.0f+static_cast<float>(mantissa)/1024.0f,
        static_cast<int>(exponent)-15):std::ldexp(static_cast<float>(mantissa),-24);
    return sign?-magnitude:magnitude;
}
inline HalfNormal PackVertexNormal(Vec3 value){return {{{PackNormalHalf(value.x),PackNormalHalf(value.y),PackNormalHalf(value.z),0x3c00u}}};}
inline Vec3 QuantizeVertexNormal(Vec3 value){
    const auto half=PackVertexNormal(value);return {UnpackNormalHalf(half.value[0]),UnpackNormalHalf(half.value[1]),UnpackNormalHalf(half.value[2])};
}

}}
