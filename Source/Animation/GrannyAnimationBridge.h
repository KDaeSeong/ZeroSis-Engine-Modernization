#pragma once
#include <stdint.h>

#ifdef _WIN32
# ifdef ZS_GRANNY_BUILD
#  define ZS_GRANNY_API __declspec(dllexport)
# else
#  define ZS_GRANNY_API __declspec(dllimport)
# endif
# define ZS_GRANNY_CALL __cdecl
#else
# define ZS_GRANNY_API
# define ZS_GRANNY_CALL
#endif

extern "C" {
enum { ZS_GRANNY_BRIDGE_ABI_VERSION = 1, ZS_GRANNY_SAMPLE_VERSION = 1 };
enum ZSGrannyStatus : int32_t {
    ZS_GRANNY_OK = 0,
    ZS_GRANNY_INVALID_ARGUMENT = 1,
    ZS_GRANNY_BAD_VERSION_OR_SIZE = 2,
    ZS_GRANNY_WRONG_THREAD = 3,
    ZS_GRANNY_FAILURE = 4
};
struct ZSGrannySample {
    uint32_t version;
    uint32_t size;
    float position[3];
    float orientation[4];
    float scale_shear[9];
};
struct ZSGrannyBridge;
ZS_GRANNY_API uint32_t ZS_GRANNY_CALL ZSGrannyBridge_GetAbiVersion();
ZS_GRANNY_API int32_t ZS_GRANNY_CALL ZSGrannyBridge_Open(const wchar_t* gsd, const wchar_t* model,
                                                          const wchar_t* animation, ZSGrannyBridge** out_handle);
ZS_GRANNY_API int32_t ZS_GRANNY_CALL ZSGrannyBridge_GetInfo(ZSGrannyBridge* handle, uint32_t* out_track_count,
                                                             float* out_duration);
ZS_GRANNY_API int32_t ZS_GRANNY_CALL ZSGrannyBridge_GetTrackName(ZSGrannyBridge* handle, uint32_t track_index,
                                                                  wchar_t* buffer, uint32_t capacity, uint32_t* out_required);
ZS_GRANNY_API int32_t ZS_GRANNY_CALL ZSGrannyBridge_Sample(ZSGrannyBridge* handle, uint32_t track_index,
                                                            float time, float duration, uint32_t sample_version,
                                                            uint32_t sample_size, ZSGrannySample* sample);
ZS_GRANNY_API int32_t ZS_GRANNY_CALL ZSGrannyBridge_Close(ZSGrannyBridge** handle);
ZS_GRANNY_API int32_t ZS_GRANNY_CALL ZSGrannyBridge_GetLastError(wchar_t* buffer, uint32_t capacity,
                                                                  uint32_t* out_required);
}
