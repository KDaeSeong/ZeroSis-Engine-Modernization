#pragma once

// Zero-copy framing of a caller-declared raw length/payload sequence.
// Reaching the supplied input end proves no producer, zlib EOF, or load contract.
#include "RetailSavePregame.h"
#include <cstddef>
#include <cstdint>
#include <stdexcept>
#include <vector>

namespace ZeroSisHost {

enum class RetailSaveChunkFramingProfile {
    U32LengthPayloadsToEnd
};

enum class RetailSaveChunkFramesErrorCode {
    NullInput, InputLimit, InvalidOffset, EmptyContainer, TruncatedLength,
    ZeroLength, FrameLimit, FrameSizeLimit, TotalPayloadLimit, TruncatedPayload,
    UnsupportedProfile
};

class RetailSaveChunkFramesError final : public std::runtime_error {
public:
    RetailSaveChunkFramesError(RetailSaveChunkFramesErrorCode code,
                              std::size_t offset, const char* message)
        : std::runtime_error(message), code_(code), offset_(offset) {}
    RetailSaveChunkFramesErrorCode Code() const noexcept { return code_; }
    std::size_t Offset() const noexcept { return offset_; }
private:
    RetailSaveChunkFramesErrorCode code_;
    std::size_t offset_;
};

struct RetailSaveChunkFramesLimits {
    std::size_t maximumInputBytes = 16u * 1024u * 1024u;
    std::size_t maximumFrames = 128u;
    std::size_t maximumFrameBytes = 65536u;
    std::size_t maximumTotalPayloadBytes = 8u * 1024u * 1024u;
};

struct RetailSaveChunkFrame {
    RetailSaveWireSpan header;
    RetailSaveWireSpan payload;
};

struct RetailSaveChunkFramesInspection {
    std::vector<RetailSaveChunkFrame> frames;
    std::size_t totalPayloadBytes = 0;
    RetailSaveWireSpan containerSpan;
};

class RetailSaveChunkFrames {
public:
    static RetailSaveChunkFramesInspection Inspect(const unsigned char* bytes,
        std::size_t size, std::size_t firstLengthOffset,
        RetailSaveChunkFramingProfile profile,
        const RetailSaveChunkFramesLimits& limits = RetailSaveChunkFramesLimits{}) {
        using Code = RetailSaveChunkFramesErrorCode;
        if (profile != RetailSaveChunkFramingProfile::U32LengthPayloadsToEnd)
            Fail(Code::UnsupportedProfile, firstLengthOffset, "Unsupported chunk framing profile");
        if (!bytes && size != 0)
            Fail(Code::NullInput, 0, "Null chunk framing input");
        if (size > limits.maximumInputBytes)
            Fail(Code::InputLimit, 0, "Chunk framing input exceeds byte budget");
        if (firstLengthOffset > size)
            Fail(Code::InvalidOffset, firstLengthOffset, "Chunk framing offset exceeds input");
        if (firstLengthOffset == size)
            Fail(Code::EmptyContainer, firstLengthOffset, "Empty chunk framing container");

        RetailSaveChunkFramesInspection result;
        result.containerSpan = {firstLengthOffset, size - firstLengthOffset};
        auto cursor = firstLengthOffset;
        while (cursor < size) {
            // All frame errors identify the rejected length word's start.
            if (result.frames.size() >= limits.maximumFrames)
                Fail(Code::FrameLimit, cursor, "Chunk frame count exceeds budget");
            if (size - cursor < 4u)
                Fail(Code::TruncatedLength, cursor, "Truncated chunk length word");
            const std::uint32_t length = static_cast<std::uint32_t>(bytes[cursor]) |
                (static_cast<std::uint32_t>(bytes[cursor + 1u]) << 8) |
                (static_cast<std::uint32_t>(bytes[cursor + 2u]) << 16) |
                (static_cast<std::uint32_t>(bytes[cursor + 3u]) << 24);
            const auto payloadBytes = static_cast<std::size_t>(length);
            if (length == 0)
                Fail(Code::ZeroLength, cursor, "Zero-length chunk payload");
            if (payloadBytes > limits.maximumFrameBytes)
                Fail(Code::FrameSizeLimit, cursor, "Chunk payload exceeds per-frame budget");
            if (result.totalPayloadBytes > limits.maximumTotalPayloadBytes ||
                payloadBytes > limits.maximumTotalPayloadBytes - result.totalPayloadBytes)
                Fail(Code::TotalPayloadLimit, cursor, "Chunk payload total exceeds budget");
            // The complete length word guarantees cursor + 4 <= size.
            const auto payloadOffset = cursor + 4u;
            if (payloadBytes > size - payloadOffset)
                Fail(Code::TruncatedPayload, cursor, "Truncated chunk payload");

            // Allocate only span metadata, after all length and budget checks.
            result.frames.push_back({{cursor, 4u}, {payloadOffset, payloadBytes}});
            result.totalPayloadBytes += payloadBytes;
            cursor = payloadOffset + payloadBytes;
        }
        return result;
    }
private:
    [[noreturn]] static void Fail(RetailSaveChunkFramesErrorCode code,
                                std::size_t offset, const char* message) {
        throw RetailSaveChunkFramesError(code, offset, message);
    }
};

} // namespace ZeroSisHost
