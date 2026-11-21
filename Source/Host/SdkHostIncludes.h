#pragma once
// Compile against the same SDK types/STL ABI as the linked GameCore.
// No GameCore implementation or DLL is linked into the host executable.
#include <CvGameCoreDLLPCH.h>
#include <CvDllInterfaces.h>
#include <ICvDLLUserInterface.h>
#include <memory>
#include <mutex>
#include <atomic>
#include <stdexcept>
#include <map>
#include <utility>

namespace ZeroSisHost {
class UnsupportedService final : public std::runtime_error {
public:
    explicit UnsupportedService(const char* name) : std::runtime_error(name) {}
};
[[noreturn]] inline void Unsupported(const char* name) { throw UnsupportedService(name); }
}
