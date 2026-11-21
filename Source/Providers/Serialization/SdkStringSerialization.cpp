#include "SdkSerializationIncludes.h"

// Select the tested member serializer explicitly to avoid recursive lookup of
// this free operator. Its int32 character count matches the archived SDK.
FDataStream& operator<<(FDataStream& stream,const std::string& value) {
    return stream.operator<<(value);
}
FDataStream& operator>>(FDataStream& stream,std::string& value) {
    return stream.operator>>(value);
}
