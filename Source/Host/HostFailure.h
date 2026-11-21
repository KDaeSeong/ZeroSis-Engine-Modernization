#pragma once
#include <cstddef>
#include <exception>

namespace ZeroSisHost {
enum class ErrorOrigin { None,Standard,Unknown };

// Host-owned value data only: no exception_ptr, DLL string, RTTI or destructor.
// Capture while the foreign exception and its module are still alive, then leave
// the catch handler before any cleanup can unload that module.
class ErrorSnapshot {
public:
    static constexpr std::size_t Capacity=1024;
    bool Present() const noexcept{return origin_!=ErrorOrigin::None;}
    explicit operator bool() const noexcept{return Present();}
    ErrorOrigin Origin() const noexcept{return origin_;}
    bool Truncated() const noexcept{return truncated_;}
    const char* Message() const noexcept{return message_;}
    void Clear() noexcept{*this=ErrorSnapshot{};}
    void Capture(const std::exception& error) noexcept {
        origin_=ErrorOrigin::Standard;
        const char* text=error.what();Copy(text?text:"Native exception without a message");
    }
    void CaptureUnknown() noexcept{origin_=ErrorOrigin::Unknown;Copy("Unknown native exception");}
private:
    void Copy(const char* text) noexcept {
        std::size_t count=0;
        while(count+1<Capacity && text[count]){message_[count]=text[count];++count;}
        message_[count]='\0';truncated_=text[count]!='\0';
    }
    ErrorOrigin origin_=ErrorOrigin::None;
    bool truncated_=false;
    char message_[Capacity]{};
};

class HostOperationError final : public std::exception {
public:
    explicit HostOperationError(ErrorSnapshot error) noexcept:error_(error){}
    const char* what() const noexcept override{return error_.Message();}
    const ErrorSnapshot& Details() const noexcept{return error_;}
private:ErrorSnapshot error_;
};
}
