#include "SdkFoundationIncludes.h"

static_assert(sizeof(dword)==4,"SDK CRC state is exactly 32 bits");
static_assert(sizeof(FCRC)==1032,"Preserve the SDK table/polynomial/magic layout");
FCRC g_CRC32;

FCRC::FCRC(dword polynomial) { InitTable(polynomial); }
FCRC::~FCRC() {}
void FCRC::InitTable(dword polynomial) {
    m_polynomial=polynomial;
    for(dword index=0;index<256;++index) {
        dword value=index;
        for(unsigned int bit=0;bit<8;++bit) value=(value>>1)^((value&1)?polynomial:0);
        m_table[index]=value;
    }
    const dword zero=0;
    m_magic=Calc(&zero,4,CRC_INIT);
}
dword FCRC::Calc(const void* data,int length,dword state) const {
    if(length<0 || (length && !data)) throw std::invalid_argument("Invalid CRC input");
    const byte* bytes=static_cast<const byte*>(data);
    for(int index=0;index<length;++index) state=(state>>8)^m_table[(state^bytes[index])&255];
    return state;
}
dword FCRC::CalcBits(const void* data,int length,dword state) const {
    if(length<0 || (length && !data)) throw std::invalid_argument("Invalid CRC input");
    const byte* bytes=static_cast<const byte*>(data);
    for(int index=0;index<length;++index) {
        state^=bytes[index];
        for(unsigned int bit=0;bit<8;++bit) state=(state>>1)^((state&1)?m_polynomial:0);
    }
    return state;
}
