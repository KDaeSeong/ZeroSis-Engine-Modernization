// Compile-only instantiation of all four corrected templates with real SDK types.
// No test hooks, streams, globals or game objects are constructed or executed.
#include "CvGameCoreDLLPCH.h"
#include "CvInfosSerializationHelper.h"

static_assert(sizeof(uint) == 4, "SDK vector-count wire type must remain uint32");

namespace ZeroSisCompileChecks {
void InstantiateSdkVectorWriters(FDataStream& stream, const std::vector<int>& values,
    const std::vector<ResourceTypes>& resources) {
    CvInfosSerializationHelper::WriteDataArray<ResourceTypes, int>(stream, values);
    CvInfosSerializationHelper::WriteHashedDataArray<ResourceTypes, int>(stream, values);
    CvInfosSerializationHelper::WriteTypeArray<ResourceTypes>(stream, resources);
    CvInfosSerializationHelper::WriteHashedTypeArray<ResourceTypes>(stream, resources);
}
} // namespace ZeroSisCompileChecks
