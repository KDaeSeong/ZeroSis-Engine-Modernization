// The archived DLL-side FString code looks up these storage exports on its
// executable during global initialization. Supply only the documented empty
// string data, not replacement stream or string operations. No GameCore load.
#include "SdkStreamIncludes.h"
#include <tchar.h>
#include <hash_map>
#define STDEXT stdext
#include <FireWorks/FString.h>

namespace {
struct EmptyA { FStringA::FStringAData header; char terminator[4]; };
struct EmptyW { FStringW::FStringWData header; wchar terminator[2]; };
EmptyA narrowEmpty = { {0, 0, 0, 1}, {0, 0, 0, 0} };
EmptyW wideEmpty = { {0, 0, 0, 1}, {0, 0} };
}
extern "C" __declspec(dllexport) FStringA::FStringAData* FStringA_GetStringInitData() { return &narrowEmpty.header; }
extern "C" __declspec(dllexport) FStringW::FStringWData* FStringW_GetStringInitData() { return &wideEmpty.header; }
