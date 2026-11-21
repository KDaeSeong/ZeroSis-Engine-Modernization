#pragma once
#include <array>
#include <cstddef>
#include <cstdint>
#include <cstring>
#include <string>

namespace ZeroSisPresentation { namespace OriginalTerrain {
// Small CPU-only SHA-256 for sealed terrain input validation. No DLL/provider
// load is needed by the same production parser in controlled component tests.
inline std::array<unsigned char,32> Sha256(const unsigned char* data,std::size_t size){
    static const std::uint32_t k[64]={
        0x428a2f98,0x71374491,0xb5c0fbcf,0xe9b5dba5,0x3956c25b,0x59f111f1,0x923f82a4,0xab1c5ed5,
        0xd807aa98,0x12835b01,0x243185be,0x550c7dc3,0x72be5d74,0x80deb1fe,0x9bdc06a7,0xc19bf174,
        0xe49b69c1,0xefbe4786,0x0fc19dc6,0x240ca1cc,0x2de92c6f,0x4a7484aa,0x5cb0a9dc,0x76f988da,
        0x983e5152,0xa831c66d,0xb00327c8,0xbf597fc7,0xc6e00bf3,0xd5a79147,0x06ca6351,0x14292967,
        0x27b70a85,0x2e1b2138,0x4d2c6dfc,0x53380d13,0x650a7354,0x766a0abb,0x81c2c92e,0x92722c85,
        0xa2bfe8a1,0xa81a664b,0xc24b8b70,0xc76c51a3,0xd192e819,0xd6990624,0xf40e3585,0x106aa070,
        0x19a4c116,0x1e376c08,0x2748774c,0x34b0bcb5,0x391c0cb3,0x4ed8aa4a,0x5b9cca4f,0x682e6ff3,
        0x748f82ee,0x78a5636f,0x84c87814,0x8cc70208,0x90befffa,0xa4506ceb,0xbef9a3f7,0xc67178f2};
    std::array<std::uint32_t,8> h={{0x6a09e667,0xbb67ae85,0x3c6ef372,0xa54ff53a,
                                   0x510e527f,0x9b05688c,0x1f83d9ab,0x5be0cd19}};
    const auto ror=[](std::uint32_t x,unsigned n){return (x>>n)|(x<<(32-n));};
    const auto block=[&](const unsigned char* p){
        std::uint32_t w[64]{};
        for(unsigned i=0;i<16;++i)w[i]=(std::uint32_t(p[i*4])<<24)|(std::uint32_t(p[i*4+1])<<16)|
            (std::uint32_t(p[i*4+2])<<8)|p[i*4+3];
        for(unsigned i=16;i<64;++i){
            const auto a=ror(w[i-15],7)^ror(w[i-15],18)^(w[i-15]>>3);
            const auto b=ror(w[i-2],17)^ror(w[i-2],19)^(w[i-2]>>10);
            w[i]=w[i-16]+a+w[i-7]+b;
        }
        auto a=h[0],b=h[1],c=h[2],d=h[3],e=h[4],f=h[5],g=h[6],v=h[7];
        for(unsigned i=0;i<64;++i){
            const auto t=v+(ror(e,6)^ror(e,11)^ror(e,25))+((e&f)^(~e&g))+k[i]+w[i];
            const auto u=(ror(a,2)^ror(a,13)^ror(a,22))+((a&b)^(a&c)^(b&c));
            v=g;g=f;f=e;e=d+t;d=c;c=b;b=a;a=t+u;
        }
        h[0]+=a;h[1]+=b;h[2]+=c;h[3]+=d;h[4]+=e;h[5]+=f;h[6]+=g;h[7]+=v;
    };
    const auto original=size;
    while(size>=64){block(data);data+=64;size-=64;}
    unsigned char tail[128]{};
    if(size)std::memcpy(tail,data,size);
    tail[size]=0x80;
    const unsigned bytes=size<56?64u:128u;
    const std::uint64_t bits=static_cast<std::uint64_t>(original)*8;
    for(unsigned i=0;i<8;++i)tail[bytes-1-i]=static_cast<unsigned char>(bits>>(i*8));
    block(tail);if(bytes==128)block(tail+64);
    std::array<unsigned char,32> result{};
    for(unsigned i=0;i<8;++i)for(unsigned j=0;j<4;++j)result[i*4+j]=static_cast<unsigned char>(h[i]>>(24-j*8));
    return result;
}
inline std::string Sha256Hex(const unsigned char* data,std::size_t size){
    static const char digits[]="0123456789abcdef";const auto bytes=Sha256(data,size);
    std::string result;result.reserve(64);
    for(const auto value:bytes){result.push_back(digits[value>>4]);result.push_back(digits[value&15]);}
    return result;
}
}}
