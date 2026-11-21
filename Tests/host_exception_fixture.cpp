// Deliberately separate DLL: its exception RTTI, vtables and destructors leave
// the address space on FreeLibrary. No GameCore object is linked or loaded.
#include "host_exception_fixture.h"
#include "ZeroSisLuaBorrowed.h"
#include <exception>

class ForeignStandard final : public std::exception {
public:
    ForeignStandard(ExceptionProbe* probe,ForeignError kind):probe_(probe),kind_(kind){
        ++probe_->live;++probe_->created;
        for(unsigned i=0;i<sizeof(message_)-1;++i)message_[i]='L';
        message_[sizeof(message_)-1]='\0';
    }
    ForeignStandard(const ForeignStandard& other):ForeignStandard(other.probe_,other.kind_){}
    ~ForeignStandard() noexcept override;
    const char* what() const noexcept override;
private:ExceptionProbe* probe_;ForeignError kind_;char message_[2048];
};
ForeignStandard::~ForeignStandard() noexcept {--probe_->live;++probe_->destroyed;}
const char* ForeignStandard::what() const noexcept {
    ++probe_->whatCalls;
    return kind_==ForeignError::NullMessage?nullptr:kind_==ForeignError::LongMessage?message_:"foreign-module-failure";
}
class ForeignUnknown {
public:
    explicit ForeignUnknown(ExceptionProbe* probe):probe_(probe){++probe_->live;++probe_->created;}
    ForeignUnknown(const ForeignUnknown& other):ForeignUnknown(other.probe_){}
    ~ForeignUnknown() noexcept;
private:ExceptionProbe* probe_;
};
ForeignUnknown::~ForeignUnknown() noexcept {--probe_->live;++probe_->destroyed;}

static void ThrowForeignImpl(ExceptionProbe* probe,ForeignError kind) {
    if(kind==ForeignError::Unknown)throw ForeignUnknown(probe);
    if(kind==ForeignError::Borrowed){
        struct Owner{int value;};Owner owner{42};
        ZeroSisLuaBorrowed::NativeReference<Owner> reference(&owner);
        ZeroSisLuaBorrowed::Invalidate(&owner);
        // Exercise the actual integrated native-reference error class in this DLL.
        volatile int unused=reference->value;(void)unused;
    }
    throw ForeignStandard(probe,kind);
}
extern "C" __declspec(dllexport) ThrowForeignError GetThrowForeign() noexcept {return &ThrowForeignImpl;}
