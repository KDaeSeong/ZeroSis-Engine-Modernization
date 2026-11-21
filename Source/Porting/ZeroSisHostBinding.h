#pragma once
#include <atomic>
#include <memory>

namespace ZeroSisHostBinding {
// Protect only host-binding mutations. Game calls and outstanding borrowers must
// already be quiescent; this is not a lease on every returned SDK interface.
class Gate {
public:
    bool TryEnter() noexcept { return !busy_.test_and_set(std::memory_order_acquire); }
    void Leave() noexcept { busy_.clear(std::memory_order_release); }
private:
    std::atomic_flag busy_ = ATOMIC_FLAG_INIT;
};

inline Gate& ProcessGate() { static Gate gate; return gate; }

class Lease {
public:
    explicit Lease(Gate& gate) noexcept : gate_(gate.TryEnter() ? &gate : nullptr) {}
    ~Lease() { if (gate_) gate_->Leave(); }
    Lease(const Lease&) = delete;
    Lease& operator=(const Lease&) = delete;
    explicit operator bool() const noexcept { return gate_ != nullptr; }
private:
    Gate* gate_;
};

template<class Interface> void Release(Interface* pointer) noexcept {
    // ICvUnknown has no virtual destructor. Its public class operator delete is
    // the SDK-owned Destroy dispatch. Invoke that boundary on the live object,
    // without first ending a base subobject's lifetime with a delete expression.
    if (pointer) Interface::operator delete(static_cast<void*>(pointer));
}
template<class Interface> struct Releaser {
    void operator()(Interface* pointer) const noexcept { Release(pointer); }
};
template<class Interface> using Owned = std::unique_ptr<Interface, Releaser<Interface>>;
}
