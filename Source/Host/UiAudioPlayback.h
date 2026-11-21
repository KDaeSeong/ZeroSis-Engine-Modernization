#pragma once

#include "UiPopupAssets.generated.h"

#include <windows.h>
#include <mmsystem.h>

#include <atomic>
#include <cstddef>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <memory>
#include <mutex>
#include <new>
#include <string>
#include <stdexcept>
#include <thread>
#include <utility>
#include <vector>

namespace ZeroSisHost {

// Plays frozen stock purchase cues through per-voice WinMM handles.
class UiAudioPlayback final {
public:
    enum class Result : unsigned char {
        Idle,
        Started,
        Completed,
        DuplicateSuppressed,
        Stopping,
        UnknownSound,
        ApiUnavailable,
        InvalidAudio,
        DeviceUnavailable,
        WaveOutFailure,
        WorkerFailure,
    };

    UiAudioPlayback() noexcept = default;
    UiAudioPlayback(const UiAudioPlayback&) = delete;
    UiAudioPlayback& operator=(const UiAudioPlayback&) = delete;
    UiAudioPlayback(UiAudioPlayback&&) = delete;
    UiAudioPlayback& operator=(UiAudioPlayback&&) = delete;

    ~UiAudioPlayback() noexcept { Stop(); }

    void SetVolumePercent(unsigned int value) {
        if(value>100u)throw std::invalid_argument("UI cue volume must be between zero and one hundred");
        volumePercent_.store(value,std::memory_order_release);
    }
    unsigned int VolumePercent() const noexcept {return volumePercent_.load(std::memory_order_acquire);}

    Result Request2D(const char* scriptId) noexcept {
        const Cue* cue = FindCue(scriptId);
        if (!cue) return RequestFailure(scriptId ? scriptId : "(null)", Result::UnknownSound);
        std::lock_guard<std::mutex> lock(mutex_);
        if (stopping_) return RequestFailureLocked(cue->script, Result::Stopping);
        ReapFinishedLocked();
        std::size_t activeForCue = 0;
        for (const auto& voice : voices_) if (voice->script == cue->script && voice->active.load()) ++activeForCue;
        if (cue->dontTriggerDuplicates && activeForCue != 0)
            return RequestFailureLocked(cue->script, Result::DuplicateSuppressed);
        if (cue->maxActive && activeForCue >= cue->maxActive)
            return RequestFailureLocked(cue->script, Result::DuplicateSuppressed);
        std::unique_ptr<Voice> voice(new (std::nothrow) Voice(cue->script));
        if (!voice) return RequestFailureLocked(cue->script, Result::WorkerFailure);
        Voice* raw = voice.get();
        std::unique_ptr<Playback, PlaybackDeleter> playback(new (std::nothrow) Playback());
        if (!playback) return RequestFailureLocked(cue->script, Result::WorkerFailure);
        const auto percent=volumePercent_.load(std::memory_order_acquire);
        const DWORD left=((cue->volume&0xffffu)*percent)/100u;
        const DWORD right=(((cue->volume>>16)&0xffffu)*percent)/100u;
        Result start = playback->Start(cue->bytes, cue->size, left|(right<<16), raw->waveOutError);
        if (start != Result::Started) {
            MMRESULT error = raw->waveOutError.load(std::memory_order_acquire);
            std::atomic<MMRESULT> cleanupError{MMSYSERR_NOERROR};
            if (!playback->Release(cleanupError)) {
                start = Result::WaveOutFailure;
                error = cleanupError.load(std::memory_order_acquire);
            }
            raw->waveOutError.store(error, std::memory_order_release);
            lastWaveOutError_.store(error, std::memory_order_release);
            return RequestFailureLocked(cue->script, start, error);
        }
        voice->active.store(true, std::memory_order_release);
        lastResult_.store(Result::Started, std::memory_order_release);
        const MMRESULT startError = raw->waveOutError.load(std::memory_order_acquire);
        lastWaveOutError_.store(startError, std::memory_order_release);
        PrintEvent("UI_AUDIO_REQUEST", cue->script, Result::Started, startError);
        try {
            voices_.push_back(std::move(voice));
            raw->worker = std::thread([this, raw, playback = std::move(playback)]() mutable {
                Result finished = playback->Wait(raw->stopping, raw->waveOutError);
                MMRESULT terminalError = raw->waveOutError.load(std::memory_order_acquire);
                std::atomic<MMRESULT> cleanupError{MMSYSERR_NOERROR};
                if (!playback->Release(cleanupError)) {
                    finished = Result::WaveOutFailure;
                    terminalError = cleanupError.load(std::memory_order_acquire);
                }
                raw->waveOutError.store(terminalError, std::memory_order_release);
                raw->terminal.store(finished, std::memory_order_release);
                raw->active.store(false, std::memory_order_release);
                lastResult_.store(finished, std::memory_order_release);
                lastWaveOutError_.store(terminalError, std::memory_order_release);
                PrintEvent("UI_AUDIO_STATUS", raw->script, finished, terminalError);
            });
        } catch (...) {
            raw->active.store(false, std::memory_order_release);
            raw->terminal.store(Result::WorkerFailure, std::memory_order_release);
            lastResult_.store(Result::WorkerFailure, std::memory_order_release);
            PrintEvent("UI_AUDIO_STATUS", cue->script, Result::WorkerFailure,
                       raw->waveOutError.load(std::memory_order_acquire));
            lastWaveOutError_.store(raw->waveOutError.load(std::memory_order_acquire), std::memory_order_release);
            return Result::WorkerFailure;
        }
        return Result::Started;
    }

    void Stop() noexcept {
        std::lock_guard<std::mutex> lock(mutex_);
        stopping_ = true;
        for (auto& voice : voices_) voice->stopping.store(true, std::memory_order_release);
        for (auto& voice : voices_) if (voice->worker.joinable()) {
            try { voice->worker.join(); } catch (...) { lastResult_.store(Result::WorkerFailure); }
        }
        voices_.clear();
    }

    Result LastResult() const noexcept { return lastResult_.load(std::memory_order_acquire); }
    MMRESULT LastWaveOutError() const noexcept { return lastWaveOutError_.load(std::memory_order_acquire); }
    bool IsActive() const noexcept {
        std::lock_guard<std::mutex> lock(mutex_);
        for (const auto& voice : voices_) if (voice->active.load(std::memory_order_acquire)) return true;
        return false;
    }

    static const char* ResultName(Result result) noexcept {
        switch (result) {
        case Result::Idle: return "Idle";
        case Result::Started: return "Started";
        case Result::Completed: return "Completed";
        case Result::DuplicateSuppressed: return "DuplicateSuppressed";
        case Result::Stopping: return "Stopping";
        case Result::UnknownSound: return "UnknownSound";
        case Result::ApiUnavailable: return "ApiUnavailable";
        case Result::InvalidAudio: return "InvalidAudio";
        case Result::DeviceUnavailable: return "DeviceUnavailable";
        case Result::WaveOutFailure: return "WaveOutFailure";
        case Result::WorkerFailure: return "WorkerFailure";
        default: return "UnknownResult";
        }
    }

private:
    std::atomic<unsigned int> volumePercent_{100};
    struct Cue {
        const char* script;
        const unsigned char* bytes;
        std::size_t size;
        DWORD volume;
        unsigned int maxActive;
        bool dontTriggerDuplicates;
    };

    struct Voice {
        explicit Voice(const char* id) noexcept : script(id) {}
        const char* script;
        std::thread worker;
        std::atomic<bool> active{false};
        std::atomic<bool> stopping{false};
        std::atomic<Result> terminal{Result::Started};
        std::atomic<MMRESULT> waveOutError{MMSYSERR_NOERROR};
    };

    static const Cue* FindCue(const char* id) noexcept {
        if (!id) return nullptr;
        static const Cue cues[] = {
            {"AS2D_INTERFACE_BUY_TILE", UiAssets::Audio2DInterfaceBuyTileWave,
             UiAssets::Audio2DInterfaceBuyTileWaveSize, UiAssets::Audio2DInterfaceBuyTileWaveOutVolume,
             UiAssets::Audio2DInterfaceBuyTileMaxActive, UiAssets::Audio2DInterfaceBuyTileDontTriggerDuplicates},
            {"AS2D_INTERFACE_CITY_SCREEN_PURCHASE", UiAssets::Audio2DInterfaceCityScreenPurchaseWave,
             UiAssets::Audio2DInterfaceCityScreenPurchaseWaveSize, UiAssets::Audio2DInterfaceCityScreenPurchaseWaveOutVolume,
             UiAssets::Audio2DInterfaceCityScreenPurchaseMaxActive, UiAssets::Audio2DInterfaceCityScreenPurchaseDontTriggerDuplicates},
            {"AS2D_INTERFACE_FAITH_PURCHASE", UiAssets::Audio2DInterfaceFaithPurchaseWave,
             UiAssets::Audio2DInterfaceFaithPurchaseWaveSize, UiAssets::Audio2DInterfaceFaithPurchaseWaveOutVolume,
             UiAssets::Audio2DInterfaceFaithPurchaseMaxActive, UiAssets::Audio2DInterfaceFaithPurchaseDontTriggerDuplicates},
            {"AS2D_INTERFACE_POLICY", UiAssets::Audio2DInterfacePolicyWave,
             UiAssets::Audio2DInterfacePolicyWaveSize, UiAssets::Audio2DInterfacePolicyWaveOutVolume,
             UiAssets::Audio2DInterfacePolicyMaxActive, UiAssets::Audio2DInterfacePolicyDontTriggerDuplicates},
        };
        for (const Cue& cue : cues) if (std::strcmp(id, cue.script) == 0) return &cue;
        return nullptr;
    }

    static void PrintEvent(const char* kind, const char* script, Result result, MMRESULT error) noexcept {
        static std::mutex logMutex;
        std::lock_guard<std::mutex> lock(logMutex);
        std::printf("%s=%s|%s|%u\n", kind, script, ResultName(result), static_cast<unsigned int>(error));
        std::fflush(stdout);
    }

    Result RequestFailure(const char* script, Result result) noexcept {
        std::lock_guard<std::mutex> lock(mutex_);
        return RequestFailureLocked(script, result);
    }

    Result RequestFailureLocked(const char* script, Result result,
                                MMRESULT error = MMSYSERR_NOERROR) noexcept {
        lastResult_.store(result, std::memory_order_release);
        lastWaveOutError_.store(error, std::memory_order_release);
        PrintEvent("UI_AUDIO_REQUEST", script, result, error);
        PrintEvent("UI_AUDIO_STATUS", script, result, error);
        return result;
    }

    void ReapFinishedLocked() noexcept {
        for (auto it = voices_.begin(); it != voices_.end();) {
            if (!(*it)->active.load(std::memory_order_acquire)) {
                if ((*it)->worker.joinable()) {
                    try { (*it)->worker.join(); } catch (...) { lastResult_.store(Result::WorkerFailure); }
                }
                it = voices_.erase(it);
            } else ++it;
        }
    }

    struct WaveOutApi {
        using Open = MMRESULT (WINAPI*)(LPHWAVEOUT, UINT, LPCWAVEFORMATEX,
                                        DWORD_PTR, DWORD_PTR, DWORD);
        using SetVolume = MMRESULT (WINAPI*)(HWAVEOUT, DWORD);
        using Prepare = MMRESULT (WINAPI*)(HWAVEOUT, LPWAVEHDR, UINT);
        using Write = MMRESULT (WINAPI*)(HWAVEOUT, LPWAVEHDR, UINT);
        using Reset = MMRESULT (WINAPI*)(HWAVEOUT);
        using Unprepare = MMRESULT (WINAPI*)(HWAVEOUT, LPWAVEHDR, UINT);
        using Close = MMRESULT (WINAPI*)(HWAVEOUT);

        Open open = nullptr;
        SetVolume setVolume = nullptr;
        Prepare prepare = nullptr;
        Write write = nullptr;
        Reset reset = nullptr;
        Unprepare unprepare = nullptr;
        Close close = nullptr;

        bool Load(HMODULE module) noexcept {
            open = reinterpret_cast<Open>(GetProcAddress(module, "waveOutOpen"));
            setVolume = reinterpret_cast<SetVolume>(GetProcAddress(module, "waveOutSetVolume"));
            prepare = reinterpret_cast<Prepare>(GetProcAddress(module, "waveOutPrepareHeader"));
            write = reinterpret_cast<Write>(GetProcAddress(module, "waveOutWrite"));
            reset = reinterpret_cast<Reset>(GetProcAddress(module, "waveOutReset"));
            unprepare = reinterpret_cast<Unprepare>(GetProcAddress(module, "waveOutUnprepareHeader"));
            close = reinterpret_cast<Close>(GetProcAddress(module, "waveOutClose"));
            return open && setVolume && prepare && write && reset && unprepare && close;
        }
    };

    struct ImaAdpcmWaveFormat {
        WAVEFORMATEX base{};
        WORD samplesPerBlock = 0;
    };

    static_assert(sizeof(WAVEFORMATEX) == 18, "Unexpected Windows WAVEFORMATEX layout");
    static_assert(sizeof(ImaAdpcmWaveFormat) == 20, "Unexpected IMA ADPCM WAVEFORMATEX extension layout");

    class Playback final {
    public:
        Playback() noexcept = default;
        Playback(const Playback&) = delete;
        Playback& operator=(const Playback&) = delete;
        ~Playback() noexcept = default;

        bool Release(std::atomic<MMRESULT>& lastError) noexcept {
            return ReleaseInternal(&lastError);
        }

        void Dispose() noexcept {
            // A failed device must not keep the game in an unbounded cleanup
            // loop. Retain the small buffer/handle owner until process exit if
            // the driver does not confirm release; freeing it would be unsafe.
            if (ReleaseInternal(nullptr))
                delete this;
        }

        Result Start(const unsigned char* bytes, std::size_t size, DWORD volumePercent,
                     std::atomic<MMRESULT>& lastError) noexcept {
            if (!ReadWave(bytes, size, lastError))
                return Result::InvalidAudio;

            wchar_t libraryPath[MAX_PATH + 16]{};
            const UINT chars = GetSystemDirectoryW(libraryPath, MAX_PATH);
            if (chars == 0 || chars >= MAX_PATH)
                return Result::ApiUnavailable;
            constexpr wchar_t suffix[] = L"\\winmm.dll";
            constexpr std::size_t suffixChars = sizeof(suffix) / sizeof(suffix[0]);
            if (chars + suffixChars > sizeof(libraryPath) / sizeof(libraryPath[0]))
                return Result::ApiUnavailable;
            std::memcpy(libraryPath + chars, suffix, sizeof(suffix));
            module_ = LoadLibraryW(libraryPath);
            if (!module_)
                return Result::ApiUnavailable;
            if (!api_.Load(module_))
                return Result::ApiUnavailable;

            event_ = CreateEventW(nullptr, FALSE, FALSE, nullptr);
            if (!event_)
                return Result::WorkerFailure;
            const MMRESULT opened = api_.open(&output_, WAVE_MAPPER, &format_.base,
                reinterpret_cast<DWORD_PTR>(event_), 0, CALLBACK_EVENT);
            lastError.store(opened, std::memory_order_release);
            if (opened != MMSYSERR_NOERROR) {
                output_ = nullptr;
                return Result::DeviceUnavailable;
            }

            // The original XML's 60 volume is mapped to 60% of WinMM's 16-bit
            // per-channel scale (0x9999). Use only this opened handle, never
            // a device identifier, so the system/default device volume is intact.
            const MMRESULT volume = api_.setVolume(output_, volumePercent);
            lastError.store(volume, std::memory_order_release);
            if (volume != MMSYSERR_NOERROR)
                return Result::WaveOutFailure;

            header_ = {};
            header_.lpData = const_cast<LPSTR>(reinterpret_cast<LPCSTR>(audioData_));
            header_.dwBufferLength = static_cast<DWORD>(audioBytes_);
            const MMRESULT prepared = api_.prepare(output_, &header_, sizeof(header_));
            lastError.store(prepared, std::memory_order_release);
            if (prepared != MMSYSERR_NOERROR)
                return Result::WaveOutFailure;
            prepared_ = true;

            // WAVE_FORMAT_DIRECT is intentionally omitted: Windows may use ACM
            // to provide a mapper-compatible path for this original IMA ADPCM.
            const MMRESULT written = api_.write(output_, &header_, sizeof(header_));
            lastError.store(written, std::memory_order_release);
            if (written != MMSYSERR_NOERROR)
                return Result::WaveOutFailure;
            return Result::Started;
        }

        Result Wait(const std::atomic<bool>& stopping,
                    std::atomic<MMRESULT>& lastError) noexcept {
            const ULONGLONG deadline = GetTickCount64() + 15000;
            for (;;) {
                if ((header_.dwFlags & WHDR_DONE) != 0)
                    return stopping.load(std::memory_order_acquire) ? Result::Stopping : Result::Completed;
                if (stopping.load(std::memory_order_acquire)) {
                    const MMRESULT reset = api_.reset(output_);
                    lastError.store(reset, std::memory_order_release);
                    if (reset != MMSYSERR_NOERROR)
                        return Result::WaveOutFailure;
                    // A successful waveOutReset returns all pending buffers.
                    return Result::Stopping;
                }
                if (GetTickCount64() >= deadline)
                    return Result::WorkerFailure;
                const DWORD waited = WaitForSingleObject(event_, 100);
                if (waited == WAIT_FAILED)
                    return Result::WorkerFailure;
                // CALLBACK_EVENT is signaled for open/close and buffer changes;
                // the WHDR_DONE bit is the completion condition.
            }
        }

    private:
        bool ReadWave(const unsigned char* bytes, std::size_t size,
                      std::atomic<MMRESULT>& lastError) noexcept {
            if (!bytes || size < 12 || std::memcmp(bytes, "RIFF", 4) != 0 ||
                std::memcmp(bytes + 8, "WAVE", 4) != 0)
                return false;
            DWORD riffBytes = 0;
            std::memcpy(&riffBytes, bytes + 4, sizeof(riffBytes));
            if (riffBytes != size - 8)
                return false;

            const unsigned char* fmt = nullptr;
            std::size_t fmtBytes = 0;
            const unsigned char* data = nullptr;
            std::size_t dataBytes = 0;
            std::size_t offset = 12;
            while (offset < size) {
                if (size - offset < 8)
                    return false;
                DWORD chunkBytes = 0;
                std::memcpy(&chunkBytes, bytes + offset + 4, sizeof(chunkBytes));
                const std::size_t body = offset + 8;
                if (chunkBytes > size - body)
                    return false;
                const std::size_t end = body + chunkBytes;
                if (std::memcmp(bytes + offset, "fmt ", 4) == 0) {
                    if (fmt)
                        return false;
                    fmt = bytes + body;
                    fmtBytes = chunkBytes;
                } else if (std::memcmp(bytes + offset, "data", 4) == 0) {
                    if (data)
                        return false;
                    data = bytes + body;
                    dataBytes = chunkBytes;
                }
                offset = end == size ? end : end + (chunkBytes & 1u);
                if (offset > size)
                    return false;
            }
            if (offset != size || !fmt || fmtBytes != sizeof(ImaAdpcmWaveFormat) || !data || !dataBytes)
                return false;
            std::memcpy(&format_, fmt, sizeof(format_));
            const std::size_t channels = format_.base.nChannels;
            const std::size_t groupBytes = 4 * channels;
            if (format_.base.wFormatTag != 0x0011 || (channels != 1 && channels != 2) ||
                format_.base.wBitsPerSample != 4 || format_.base.cbSize != sizeof(WORD) ||
                format_.base.nBlockAlign <= groupBytes ||
                dataBytes > MAXDWORD)
                return false;
            const std::size_t tailBytes = dataBytes % format_.base.nBlockAlign;
            if ((tailBytes && (tailBytes < groupBytes || tailBytes % groupBytes != 0)) ||
                format_.samplesPerBlock != 1 + (format_.base.nBlockAlign - groupBytes) * 2 / channels)
                return false;
            audioData_ = data;
            audioBytes_ = dataBytes;
            lastError.store(MMSYSERR_NOERROR, std::memory_order_release);
            return true;
        }

        bool ReleaseInternal(std::atomic<MMRESULT>* lastError) noexcept {
            if (output_ && prepared_) {
                if ((header_.dwFlags & WHDR_DONE) == 0) {
                    const MMRESULT reset = api_.reset(output_);
                    if (lastError)
                        lastError->store(reset, std::memory_order_release);
                    if (reset != MMSYSERR_NOERROR)
                        return false;
                }
                const MMRESULT result = api_.unprepare(output_, &header_, sizeof(header_));
                if (lastError)
                    lastError->store(result, std::memory_order_release);
                if (result != MMSYSERR_NOERROR)
                    return false;
                prepared_ = false;
            }
            if (output_ && api_.close) {
                const MMRESULT result = api_.close(output_);
                if (lastError)
                    lastError->store(result, std::memory_order_release);
                if (result != MMSYSERR_NOERROR)
                    return false;
                output_ = nullptr;
            }
            if (!output_ && event_) {
                CloseHandle(event_);
                event_ = nullptr;
            }
            if (!output_ && module_) {
                FreeLibrary(module_);
                module_ = nullptr;
            }
            return !output_ && !prepared_;
        }

        HMODULE module_ = nullptr;
        HANDLE event_ = nullptr;
        HWAVEOUT output_ = nullptr;
        WaveOutApi api_{};
        ImaAdpcmWaveFormat format_{};
        WAVEHDR header_{};
        const unsigned char* audioData_ = nullptr;
        std::size_t audioBytes_ = 0;
        bool prepared_ = false;
    };

    struct PlaybackDeleter {
        void operator()(Playback* playback) const noexcept {
            if (playback)playback->Dispose();
        }
    };

    mutable std::mutex mutex_;
    std::vector<std::unique_ptr<Voice>> voices_;
    bool stopping_ = false;
    std::atomic<Result> lastResult_{Result::Idle};
    std::atomic<MMRESULT> lastWaveOutError_{MMSYSERR_NOERROR};
};

} // namespace ZeroSisHost
