#pragma once
#include "SdkWorldBuilderMapIncludes.h"
#include <FireWorks/FIFile.h>

// Test-only file transport. Original map code performs every format operation.
// There is no filesystem fallback: the file is the caller-supplied byte vector.
extern std::vector<byte> worldMapFile;
extern bool worldMapTraceIO;
void InstallWorldMapFileHost();
