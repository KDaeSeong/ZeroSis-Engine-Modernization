#pragma once
struct ExceptionProbe {
    int live=0,created=0,destroyed=0,whatCalls=0;
};
enum class ForeignError { Standard,Unknown,Borrowed,LongMessage,NullMessage };
using ThrowForeignError=void(*)(ExceptionProbe*,ForeignError);
