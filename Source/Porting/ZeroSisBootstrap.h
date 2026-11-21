#pragma once
#ifndef NOMINMAX
#define NOMINMAX
#endif
#include <windows.h>
#include <mutex>
#include <new>

namespace ZeroSisBootstrap {
enum class Phase : unsigned { Empty, Starting, Ready, Stopping, CleanupRequired };

class Backend {
public:
    virtual ~Backend() = default;
    // Timer failure must leave no request. Symbol/context creation may retain
    // partial resources, so cleanup is armed before these operations begin.
    virtual bool BeginTimer() noexcept = 0;
    virtual bool EndTimer() noexcept = 0;
    virtual bool BeginSymbols(HMODULE module) = 0;
    virtual bool EndSymbols() noexcept = 0;
    virtual void* CreateContext() = 0;
    virtual bool DestroyContext() noexcept = 0;
};

class Lifecycle {
public:
    // Entry and shutdown must run after DllMain, never under the loader lock.
    // Shutdown also requires the host to release every outstanding SDK adapter
    // and stop game/worker calls; returned pointers are not refcounted leases.
    void* Start(Backend& backend, HMODULE module) noexcept {
        std::lock_guard<std::recursive_mutex> guard(mutex_);
        if (phase_ == Phase::Ready) {
            if (backend_ != &backend || module_ != module) { Error(ERROR_INVALID_PARAMETER); return nullptr; }
            Error(ERROR_SUCCESS);
            return context_;
        }
        if (phase_ != Phase::Empty) { Error(ERROR_BUSY); return nullptr; }
        if (!module) { Error(ERROR_INVALID_HANDLE); return nullptr; }
        backend_ = &backend;
        module_ = module;
        phase_ = Phase::Starting;
        DWORD failure = ERROR_SUCCESS;
        try {
            SetLastError(ERROR_SUCCESS);
            if (!backend.BeginTimer()) failure = Failure();
            else {
                timer_ = true;
                symbols_ = true;
                SetLastError(ERROR_SUCCESS);
                if (!backend.BeginSymbols(module)) failure = Failure();
                else {
                    contextCleanup_ = true;
                    SetLastError(ERROR_SUCCESS);
                    context_ = backend.CreateContext();
                    if (!context_) failure = Failure();
                }
            }
        } catch (const std::bad_alloc&) { failure = ERROR_NOT_ENOUGH_MEMORY; }
        catch (...) { failure = ERROR_DLL_INIT_FAILED; }
        if (failure == ERROR_SUCCESS) {
            phase_ = Phase::Ready;
            Error(ERROR_SUCCESS);
            return context_;
        }
        // Preserve the creation failure for the caller. Cleanup failures retain
        // ownership and prohibit another Start until explicit Shutdown succeeds.
        phase_ = Phase::Stopping;
        Cleanup();
        Error(failure);
        return nullptr;
    }

    bool Shutdown() noexcept {
        std::lock_guard<std::recursive_mutex> guard(mutex_);
        if (phase_ == Phase::Starting || phase_ == Phase::Stopping) { Error(ERROR_BUSY); return false; }
        if (phase_ == Phase::Empty) { Error(ERROR_SUCCESS); return true; }
        phase_ = Phase::Stopping;
        return Cleanup();
    }

    DWORD LastError() const noexcept {
        std::lock_guard<std::recursive_mutex> guard(mutex_);
        return error_;
    }
    Phase State() const noexcept {
        std::lock_guard<std::recursive_mutex> guard(mutex_);
        return phase_;
    }

private:
    static DWORD Failure() noexcept { const DWORD value = GetLastError(); return value ? value : ERROR_GEN_FAILURE; }
    void Error(DWORD value) noexcept { error_ = value; SetLastError(value); }
    bool Cleanup() noexcept {
        if (contextCleanup_) {
            SetLastError(ERROR_SUCCESS);
            if (!backend_->DestroyContext()) return CleanupFailed();
            contextCleanup_ = false;
            context_ = nullptr;
        }
        if (symbols_) {
            SetLastError(ERROR_SUCCESS);
            if (!backend_->EndSymbols()) return CleanupFailed();
            symbols_ = false;
        }
        if (timer_) {
            SetLastError(ERROR_SUCCESS);
            if (!backend_->EndTimer()) return CleanupFailed();
            timer_ = false;
        }
        phase_ = Phase::Empty;
        backend_ = nullptr;
        module_ = nullptr;
        Error(ERROR_SUCCESS);
        return true;
    }
    bool CleanupFailed() noexcept {
        const DWORD failure = Failure();
        phase_ = Phase::CleanupRequired;
        Error(failure);
        return false;
    }
    mutable std::recursive_mutex mutex_;
    Phase phase_ = Phase::Empty;
    DWORD error_ = ERROR_SUCCESS;
    Backend* backend_ = nullptr;
    HMODULE module_ = nullptr;
    void* context_ = nullptr;
    bool timer_ = false, symbols_ = false, contextCleanup_ = false;
};
}
