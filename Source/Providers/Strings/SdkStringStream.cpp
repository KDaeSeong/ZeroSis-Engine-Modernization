#include "SdkStringIncludes.h"
#include <stdexcept>

void FDataStream::Write(const FStringA& value) {
    const unsigned count=static_cast<unsigned>(value.GetLength());
    *this<<count;
    if(count && WriteIt(count,value.c_str())!=count)throw std::runtime_error("Short FString write");
}
void FDataStream::Read(FStringA& value) {
    unsigned count=0;*this>>count;
    if(count>INT_MAX)throw std::length_error("FString saved length exceeds int32");
    if(count>GetSizeLeft())throw std::out_of_range("FString saved payload is truncated");
    std::vector<char> buffer(count);
    if(count && ReadIt(count,buffer.data())!=count)throw std::runtime_error("Short FString read");
    // Copy prepares allocation before modifying the destination. Stream progress
    // is not rolled back: only the caller owns a transaction spanning fields.
    value.Copy(static_cast<int>(count),count?buffer.data():NULL);
}
