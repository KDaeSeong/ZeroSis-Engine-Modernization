#include "SdkSerializationIncludes.h"

// Eighty SDK enum operators store a signed 32-bit integer; GameTypes uses one
// signed byte. Preserve the measured sentinel/hashed-ID representation.
// The shared trace executes every listed operator against the actual x86 SDK.
#define SDK_ENUM(Type) \
    static_assert(sizeof(Type)==sizeof(INT32),"SDK enum storage must remain 32 bits"); \
    FDataStream& operator<<(FDataStream& stream,const Type& value) { \
        INT32 bits; memcpy(&bits,&value,sizeof(bits)); stream << bits; return stream; } \
    FDataStream& operator>>(FDataStream& stream,Type& value) { \
        INT32 bits=0; stream >> bits; memcpy(&value,&bits,sizeof(bits)); return stream; }
#define SDK_ENUM_BYTE(Type) \
    static_assert(sizeof(Type)==sizeof(INT32),"SDK enum object must remain 32 bits"); \
    FDataStream& operator<<(FDataStream& stream,const Type& value) { \
        UINT32 bits; memcpy(&bits,&value,sizeof(bits)); const unsigned char byte=static_cast<unsigned char>(bits&255u); \
        stream<<byte; return stream; } \
    FDataStream& operator>>(FDataStream& stream,Type& value) { \
        unsigned char byte=0; stream>>byte; const INT32 bits=byte<128 ? byte : static_cast<int>(byte)-256; \
        memcpy(&value,&bits,sizeof(bits)); return stream; }
#include "SdkEnumTypes.inc"
#undef SDK_ENUM
#undef SDK_ENUM_BYTE
