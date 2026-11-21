#pragma once
#include "SdkWorldBuilderMapIncludes.h"
#include "WorldBuilderMapWire.h"
namespace ZeroSisWorldBuilder {
struct MapLoadResult { unsigned sourceVersion,recoveredAllocators; };
// Prepare the complete replacement before publishing. An exception leaves the
// target untouched. Explicit recovery is observable and never overwrites input.
MapLoadResult LoadMapBytes(CvWorldBuilderMap& target,const void* bytes,size_t length,
    const CvWorldBuilderMapTypeDesc& types,bool scenario=true,MapReadPolicy policy=MapReadPolicy::Strict);
// Version 12 wire fields, never native C++ record/bitset layouts.
MapBytes SaveMapBytes(const CvWorldBuilderMap& source,const CvWorldBuilderMapTypeDesc& types,bool scenario=true);
}
