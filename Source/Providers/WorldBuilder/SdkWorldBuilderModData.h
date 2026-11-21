#pragma once
#include "SdkWorldBuilderIncludes.h"
#include "SdkWorldBuilderModDataWire.h"
namespace ZeroSisWorldBuilder {
// The eventual map file loader must use this length-bearing boundary, then
// validate the number of plots against its own map header before publishing.
void DeserializeModData(CvWorldBuilderMapModData& target,const void* bytes,size_t length);
}
