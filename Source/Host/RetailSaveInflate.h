#pragma once

// Bounded zlib inspection, not retail container/state approval. zlib source and
// license: ../ThirdParty/zlib-1.3.2 (pinned source_receipt.json).
// Boundary semantics: zlib Z_BLOCK/data_type and RFC1951 sections 3.2.3-3.2.4.
#include "../ThirdParty/zlib-1.3.2/zlib.h"
#include <algorithm>
#include <array>
#include <cstddef>
#include <cstdint>
#include <cstdlib>
#include <limits>
#include <new>
#include <stdexcept>
#include <utility>
#include <vector>

namespace ZeroSisHost {
enum class RetailInflateErrorCode {
    NullInput, InputLimit, OutputLimit, MemoryLimit, AllocationFailure,
    WorkLimit, InvalidData, DictionaryRequired, TrailingInput, IncompleteStream
};
class RetailInflateError final : public std::invalid_argument {
public:
    RetailInflateError(RetailInflateErrorCode code,const char* message)
        :std::invalid_argument(message),code_(code) {}
    RetailInflateErrorCode Code() const noexcept { return code_; }
private:
    RetailInflateErrorCode code_;
};
struct RetailInflateLimits {
    std::size_t maximumInputBytes=64u*1024u*1024u;
    std::size_t maximumOutputBytes=64u*1024u*1024u;
    std::size_t maximumDecoderMemoryBytes=1024u*1024u;
    std::size_t maximumCalls=1048576;
};
enum class RetailInflateTermination {
    CompleteZlibStream, NonFinalEmptyStoredBlockBoundary, Incomplete
};
struct RetailInflateInspection {
    std::vector<unsigned char> bytes;
    RetailInflateTermination termination=RetailInflateTermination::Incomplete;
    std::size_t inputConsumed=0,calls=0,blocks=0,lastBoundaryBit=0,decoderPeakBytes=0;
    bool finalDeflateBlockSeen=false;
    // Only Z_STREAM_END proves the zlib wrapper trailer. Even that cannot prove
    // the retail container or SDK state is complete, compatible or safe to load.
    bool adlerTrailerVerified=false;
};

namespace RetailSaveInflateDetail {
[[noreturn]] inline void Fail(RetailInflateErrorCode code,const char* message) {
    throw RetailInflateError(code,message);
}
struct alignas(std::max_align_t) Allocation { std::size_t bytes; };
struct Memory {
    std::size_t limit=0,used=0,peak=0;
    bool denied=false;
    static voidpf Allocate(voidpf opaque,uInt items,uInt itemBytes) noexcept {
        auto& m=*static_cast<Memory*>(opaque);
        if (itemBytes && items>((std::numeric_limits<std::size_t>::max)()-sizeof(Allocation))/itemBytes) {
            m.denied=true;return nullptr;
        }
        const std::size_t bytes=sizeof(Allocation)+static_cast<std::size_t>(items)*itemBytes;
        if (m.used>m.limit||bytes>m.limit-m.used) { m.denied=true;return nullptr; }
        void* storage=std::calloc(1,bytes);
        if (!storage) return nullptr;
        auto* header=::new(storage) Allocation{bytes};
        m.used+=bytes;m.peak=(std::max)(m.peak,m.used);
        return header+1;
    }
    static void Free(voidpf opaque,voidpf address) noexcept {
        if (!address) return;
        auto& m=*static_cast<Memory*>(opaque);
        auto* header=static_cast<Allocation*>(address)-1;
        m.used-=header->bytes;header->~Allocation();std::free(header);
    }
};
struct Decoder {
    z_stream stream{};
    Memory memory;
    bool initialized=false;
    explicit Decoder(std::size_t limit) { memory.limit=limit;stream.zalloc=Memory::Allocate;stream.zfree=Memory::Free;stream.opaque=&memory; }
    ~Decoder() { if (initialized) inflateEnd(&stream); }
    void Release() { if (initialized) {inflateEnd(&stream);initialized=false;} }
};
inline bool EmptyNonfinalStored(const unsigned char* data,std::size_t size,
                               std::size_t beginBit,std::size_t endBit) {
    if (beginBit>size*8||size*8-beginBit<3) return false;
    const auto bit=[&](std::size_t at) {return (data[at/8]>>(at%8))&1u;};
    if (bit(beginBit)||bit(beginBit+1)||bit(beginBit+2)) return false;
    const auto aligned=(beginBit+3+7)/8;
    if (aligned>size||size-aligned<4||endBit!=(aligned+4)*8) return false;
    return data[aligned]==0&&data[aligned+1]==0&&data[aligned+2]==255&&data[aligned+3]==255;
}
}

class RetailSaveInflate {
public:
    // Inspection can return untrusted partial output. Its termination enum must
    // never be interpreted as successful save loading or SDK validation.
    static RetailInflateInspection Inspect(const unsigned char* data,std::size_t size,
                                           const RetailInflateLimits& limits=RetailInflateLimits{}) {
        using namespace RetailSaveInflateDetail;
        if (!data&&size) Fail(RetailInflateErrorCode::NullInput,"Null compressed input");
        if (size>limits.maximumInputBytes||size>(std::numeric_limits<uInt>::max)())
            Fail(RetailInflateErrorCode::InputLimit,"Compressed input exceeds its byte budget");
        Decoder decoder(limits.maximumDecoderMemoryBytes);
        auto& stream=decoder.stream;
        const int init=inflateInit2(&stream,15);
        if (init!=Z_OK) Fail(decoder.memory.denied?RetailInflateErrorCode::MemoryLimit:RetailInflateErrorCode::AllocationFailure,
                            "Cannot initialize bounded zlib decoder");
        decoder.initialized=true;
        stream.next_in=const_cast<Bytef*>(data);stream.avail_in=static_cast<uInt>(size);
        RetailInflateInspection result;
        std::array<unsigned char,65536> output{};
        std::size_t previousBoundaryBit=0,previousBoundaryOutput=0;
        bool haveBoundary=false;
        while (true) {
            if (result.calls==limits.maximumCalls) Fail(RetailInflateErrorCode::WorkLimit,"Compressed input exceeds its work budget");
            ++result.calls;
            const auto remaining=limits.maximumOutputBytes-result.bytes.size();
            const auto capacity=(std::min)(output.size(),remaining?remaining:std::size_t{1});
            stream.next_out=output.data();stream.avail_out=static_cast<uInt>(capacity);
            const auto beforeInput=stream.avail_in;
            const int status=inflate(&stream,Z_BLOCK);
            const auto produced=capacity-stream.avail_out;
            if (produced>remaining) Fail(RetailInflateErrorCode::OutputLimit,"Decompressed output exceeds its byte budget");
            if (produced) {
                const auto needed=result.bytes.size()+produced;
                if (needed>result.bytes.capacity()) {
                    const auto old=result.bytes.capacity();
                    const auto grown=old>limits.maximumOutputBytes-old?limits.maximumOutputBytes:old*2;
                    result.bytes.reserve((std::max)(needed,grown));
                }
                result.bytes.insert(result.bytes.end(),output.begin(),output.begin()+produced);
            }
            result.inputConsumed=size-stream.avail_in;
            if (status==Z_NEED_DICT) Fail(RetailInflateErrorCode::DictionaryRequired,"Preset deflate dictionary is unsupported");
            if (status==Z_MEM_ERROR) Fail(decoder.memory.denied?RetailInflateErrorCode::MemoryLimit:RetailInflateErrorCode::AllocationFailure,
                                       "Bounded zlib allocation failed");
            if (status!=Z_OK&&status!=Z_BUF_ERROR&&status!=Z_STREAM_END)
                Fail(RetailInflateErrorCode::InvalidData,"Invalid compressed data or wrapper checksum");
            if (status==Z_STREAM_END) {
                if (stream.avail_in) Fail(RetailInflateErrorCode::TrailingInput,"Trailing bytes after zlib stream");
                result.termination=RetailInflateTermination::CompleteZlibStream;
                result.adlerTrailerVerified=true;result.finalDeflateBlockSeen=true;break;
            }
            if (stream.data_type&128) {
                const auto endBit=result.inputConsumed*8-static_cast<unsigned int>(stream.data_type&63);
                const bool finalBlock=(stream.data_type&64)!=0;
                const bool emptyStored=haveBoundary&&!finalBlock&&result.bytes.size()==previousBoundaryOutput&&
                    EmptyNonfinalStored(data,size,previousBoundaryBit,endBit);
                if (haveBoundary) ++result.blocks;
                result.lastBoundaryBit=endBit;result.finalDeflateBlockSeen=finalBlock;
                previousBoundaryBit=endBit;previousBoundaryOutput=result.bytes.size();haveBoundary=true;
                if (emptyStored&&stream.avail_in==0&&(stream.data_type&63)==0&&endBit==size*8) {
                    result.termination=RetailInflateTermination::NonFinalEmptyStoredBlockBoundary;break;
                }
            }
            if (beforeInput==stream.avail_in&&!produced) break;
        }
        result.decoderPeakBytes=decoder.memory.peak;
        decoder.Release();
        if (decoder.memory.used) throw std::runtime_error("zlib decoder leaked bounded allocations");
        return result;
    }
    static RetailInflateInspection Inspect(const std::vector<unsigned char>& data,
                                           const RetailInflateLimits& limits=RetailInflateLimits{}) {
        return Inspect(data.data(),data.size(),limits);
    }
    // Strict generic zlib decoding deliberately rejects an open retail prefix.
    static std::vector<unsigned char> DecodeComplete(const unsigned char* data,std::size_t size,
                                                     const RetailInflateLimits& limits=RetailInflateLimits{}) {
        auto result=Inspect(data,size,limits);
        if (result.termination!=RetailInflateTermination::CompleteZlibStream)
            RetailSaveInflateDetail::Fail(RetailInflateErrorCode::IncompleteStream,"Missing complete zlib stream/trailer");
        return std::move(result.bytes);
    }
};
} // namespace ZeroSisHost
