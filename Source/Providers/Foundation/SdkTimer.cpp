#include "SdkFoundationIncludes.h"

__int64 FTimer::m_qMark=0;
__int64 FTimer::m_qRate=0;
double FTimer::m_fFreq=0;

double FTimer::Read(__int64 offset) {
    // The SDK's unchecked first-use writes race. Publish once before any reader
    // accesses these fields; C++ local-static initialization retries on failure.
    static const bool initialized=[]() {
        LARGE_INTEGER rate,mark;
        if(!QueryPerformanceFrequency(&rate) || !QueryPerformanceCounter(&mark) || rate.QuadPart<=0)
            throw std::runtime_error("High-resolution clock is unavailable");
        m_qRate=rate.QuadPart;
        m_qMark=mark.QuadPart;
        m_fFreq=1.0/static_cast<double>(rate.QuadPart);
        return true;
    }();
    (void)initialized;
    LARGE_INTEGER now;
    if(!QueryPerformanceCounter(&now)) throw std::runtime_error("High-resolution clock read failed");
    const __int64 origin=offset?offset:m_qMark;
    // Match the SDK's 64-bit subtraction even for synthetic extreme offsets,
    // without invoking C++ signed-overflow undefined behavior.
    const unsigned __int64 bits=static_cast<unsigned __int64>(now.QuadPart)-static_cast<unsigned __int64>(origin);
    __int64 delta;
    memcpy(&delta,&bits,sizeof(delta));
    return static_cast<double>(delta)*m_fFreq;
}
