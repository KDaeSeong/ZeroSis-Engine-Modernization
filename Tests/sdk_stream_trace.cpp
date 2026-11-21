// Runs in an isolated process; never loads GameCore or starts Civilization V.
#include "SdkStreamIncludes.h"

class ProbeStream : public FMemoryStream {
public:
    template<class T> static void writeArray(FDataStream& s, int n, const T* data) {
        void (FDataStream::*f)(int,const T*) = &ProbeStream::Write; (s.*f)(n,data);
    }
    template<class T> static void readArray(FDataStream& s, int n, T* data) {
        void (FDataStream::*f)(int,T*) = &ProbeStream::Read; (s.*f)(n,data);
    }
    // Form protected member pointers without constructing a derived vtable.
    // The archived SDK uses stdext::exception in RaiseException, whereas its
    // public header declares std::exception. No shim changes that reference.
    static void state(const FMemoryStream& s, const char* name) {
        const char* start = s.*(&ProbeStream::m_pStart);
        const unsigned int capacity = start ? static_cast<unsigned int>(s.*(&ProbeStream::m_pEndOfBuffer) - start) : 0;
        const unsigned int cursor = start ? static_cast<unsigned int>(s.*(&ProbeStream::m_pData) - start) : 0;
        printf("STATE|%s|%u|%u|%u|%u|%u|%u|%u|%d|%d|%d|%d\n", name,
            s.GetPosition(), cursor, s.GetEOF(), s.GetBytesUsed(), s.GetSizeLeft(), s.*(&ProbeStream::m_uiBytesRead), capacity,
            s.AtEnd() ? 1 : 0, static_cast<int>(s.GetDesiredEndianNess()), s.*(&ProbeStream::m_bRealloc) ? 1 : 0, s.*(&ProbeStream::m_bReallocMin) ? 1 : 0);
    }
};

static void bytes(const char* label, const void* data, unsigned int size) {
    printf("HEX|%s|", label);
    const unsigned char* p = static_cast<const unsigned char*>(data);
    for (unsigned int i = 0; i < size; ++i) printf("%02x", static_cast<unsigned int>(p[i]));
    printf("\n");
}

static void memoryTrace() {
    FMemoryStream s;
    ProbeStream::state(s, "default");
    printf("RET|write6|%u\n", s.WriteIt(6, "abcdef")); ProbeStream::state(s, "write6");
    s.Rewind(); ProbeStream::state(s, "rewind");
    char out[20]; memset(out, '?', sizeof(out));
    printf("RET|read2|%u\n", s.ReadIt(2, out)); bytes("read2", out, 8); ProbeStream::state(s, "read2");
    s.Skip(1); ProbeStream::state(s, "skip1");
    printf("RET|write2|%u\n", s.WriteIt(2, "XY")); ProbeStream::state(s, "overwrite"); bytes("overwrite", s.GetBuf(), s.GetEOF());
    s.SetPosition(1); ProbeStream::state(s, "position1");
    s.Truncate(); ProbeStream::state(s, "truncate"); bytes("truncate", s.GetBuf(), s.GetEOF());
    s.FastFwd(); ProbeStream::state(s, "fastfwd");
    s.WriteIt(3, "123"); ProbeStream::state(s, "append");
    memset(out, '?', sizeof(out)); s.CopyToMem(out); bytes("copytomem", out, 8); ProbeStream::state(s, "copytomem");
    s.Rewind(); s.Skip(2);
    FMemoryStream copy(s); bytes("copy", copy.GetBuf(), copy.GetEOF());
    printf("COPY|%u|%u|%u|%u\n", copy.GetPosition(), copy.GetEOF(), copy.GetBytesUsed(), copy.GetSizeLeft());
    copy.WriteIt(1, "!"); bytes("copy_changed", copy.GetBuf(), copy.GetEOF()); bytes("original", s.GetBuf(), s.GetEOF());
    FMemoryStream assigned; assigned = s;
    printf("ASSIGN|%u|%u|%u|%u\n", assigned.GetPosition(), assigned.GetEOF(), assigned.GetBytesUsed(), assigned.GetSizeLeft());
    assigned.WriteIt(1, "@"); bytes("assigned_changed", assigned.GetBuf(), assigned.GetEOF());
    // The original leaves dangling stop/data pointers after Uninit. Do not
    // call getters that subtract them; observe reinitialization separately.
    s.Uninit();
    char input[6] = { 'h','e','l','l','o','!' };
    FMemoryStream fixed(6, input, false, false); ProbeStream::state(fixed, "init_data");
    input[0] = 'Z'; bytes("input_changed", fixed.GetBuf(), fixed.GetEOF());
    printf("RET|fixed_write|%u\n", fixed.WriteIt(2, "AB")); bytes("input_after_write", input, 6); ProbeStream::state(fixed, "fixed_write");
    FMemoryStream allocated(6, NULL, true, true); ProbeStream::state(allocated, "init_null");
    allocated.WriteIt(6, "abcdef"); ProbeStream::state(allocated, "minimal_full");
    allocated.WriteIt(1, "g"); ProbeStream::state(allocated, "minimal_grow");
    char* adopted = static_cast<char*>(malloc(6)); if (!adopted) throw std::bad_alloc();
    memcpy(adopted, input, 6);
    s.Init(6, adopted, true, false); s.Rewind(); ProbeStream::state(s, "reinit_rewind");
    adopted[3] = '#'; bytes("growable_adopts_buffer", s.GetBuf(), s.GetEOF());
    s.Skip(2); memset(out, '?', sizeof(out)); s.CopyToMem(out);
    bytes("copy_remaining", out, 8); ProbeStream::state(s, "copy_remaining");
    s.FastFwd(); ProbeStream::state(s, "fastfwd_nonempty");
}

template<class T> static void scalar(FMemoryStream& s, const T& v) { s << v; }
static void scalarTrace(int endian) {
    FMemoryStream s;
    s.SetDesiredEndianNess(static_cast<FEndian::EEndianness>(endian));
    scalar(s, true); scalar(s, false); scalar(s, static_cast<unsigned char>(0xa5)); scalar(s, static_cast<char>(-7));
    scalar(s, static_cast<INT16>(-12345)); scalar(s, static_cast<UINT16>(0xabcd)); scalar(s, static_cast<WCHAR>(0xd55c));
    scalar(s, static_cast<INT32>(-123456789)); scalar(s, static_cast<UINT32>(0x89abcdef)); scalar(s, static_cast<unsigned long>(0x76543210));
    scalar(s, static_cast<INT64>(-123456789012345LL)); scalar(s, static_cast<UINT64>(0xfedcba9876543210ULL));
    scalar(s, -13.25f); scalar(s, 1234.125);
    GUID guid = {0x12345678, 0xabcd, 0xef01, {2,3,4,5,6,7,8,9}}; scalar(s, guid);
    bytes("scalars", s.GetBuf(), s.GetEOF()); ProbeStream::state(s, "scalar_write");
    s.Rewind();
    bool b1 = false, b2 = true; unsigned char uc = 0; char c = 0; INT16 i16 = 0; UINT16 u16 = 0; WCHAR w = 0;
    INT32 i32 = 0; UINT32 u32 = 0; unsigned long ul = 0; INT64 i64 = 0; UINT64 u64 = 0; float f = 0; double d = 0; GUID g = {};
    s >> b1 >> b2 >> uc >> c >> i16 >> u16 >> w >> i32 >> u32 >> ul >> i64 >> u64 >> f >> d >> g;
    printf("VALUES|%d|%d|%u|%d|%d|%u|%u|%d|%u|%lu|%I64d|%I64u|%.8f|%.8f\n", b1, b2, uc, c, i16, u16, w, i32, u32, ul, i64, u64, f, d);
    bytes("guid_read", &g, sizeof(g)); ProbeStream::state(s, "scalar_read");
    FMemoryStream strings; strings.SetDesiredEndianNess(static_cast<FEndian::EEndianness>(endian));
    printf("RET|cstr|%u\n", strings.WriteString("abc")); printf("RET|empty|%u\n", strings.WriteString(""));
    printf("RET|wide|%u\n", strings.WriteString(L"A\xD55C\xAE00"));
    strings << std::string("x\0y", 3) << std::wstring(L"w\0z", 3);
    bytes("strings", strings.GetBuf(), strings.GetEOF()); ProbeStream::state(strings, "string_write");
    strings.Rewind(); char a[16] = {}; char e[16] = {}; wchar wide[16] = {}; std::string narrow; std::wstring ws;
    printf("RET|readcstr|%u\n", strings.ReadString(a)); printf("RET|readempty|%u\n", strings.ReadString(e));
    printf("RET|readwide|%u\n", strings.ReadString(wide)); strings >> narrow >> ws;
    bytes("readstr", a, 5); bytes("readempty", e, 2); bytes("readwide", wide, 8);
    bytes("readstd", narrow.data(), static_cast<unsigned int>(narrow.size())); bytes("readwstd", ws.data(), static_cast<unsigned int>(ws.size()*2));
    ProbeStream::state(strings, "string_read");
}

static void edgeTrace(const char* mode) {
    FMemoryStream s(4, "abcd", false, false); char out[12]; memset(out, '?', sizeof(out));
    try {
    if (!strcmp(mode, "shortread")) { s.Skip(2); printf("RET|shortread|%u\n", s.ReadIt(6, out)); bytes("shortread", out, 12); }
    else if (!strcmp(mode, "pastskip")) s.Skip(8);
    else if (!strcmp(mode, "pastseek")) s.SetPosition(8);
    else if (!strcmp(mode, "fixedoverflow")) { s.Skip(2); printf("RET|fixedoverflow|%u\n", s.WriteIt(6, "123456")); }
    else if (!strcmp(mode, "zero")) { printf("RET|read0|%u\n", s.ReadIt(0, NULL)); printf("RET|write0|%u\n", s.WriteIt(0, NULL)); }
    } catch (...) { printf("EXCEPTION|caught\n"); }
    ProbeStream::state(s, mode); bytes("remaining", s.GetBuf(), s.GetEOF());
    bytes("out_after", out, 12);
}

static void bulkTrace(int endian) {
    FMemoryStream s; s.SetDesiredEndianNess(static_cast<FEndian::EEndianness>(endian));
    const INT32 a[3] = {-1,0x12345678,42}; INT32 ar[3] = {};
    const UINT64 u[3] = {0x0123456789abcdefULL,0xfedcba9876543210ULL,0}; UINT64 ur[3] = {};
    const WCHAR w[3] = {0x41,0xd55c,0xae00}; WCHAR wr[3] = {};
    const bool b[3] = {true,false,true}; bool br[3] = {};
    ProbeStream::writeArray(s,3,a); ProbeStream::writeArray(s,3,u); ProbeStream::writeArray(s,3,w); ProbeStream::writeArray(s,3,b);
    bytes("bulk",s.GetBuf(),s.GetEOF()); s.Rewind();
    ProbeStream::readArray(s,3,ar); ProbeStream::readArray(s,3,ur); ProbeStream::readArray(s,3,wr); ProbeStream::readArray(s,3,br);
    printf("BULK_EQUAL|%d|%d|%d|%d\n",!memcmp(a,ar,sizeof(a)),!memcmp(u,ur,sizeof(u)),!memcmp(w,wr,sizeof(w)),!memcmp(b,br,sizeof(b)));
    ProbeStream::state(s,"bulk_read");
    FMemoryStream dst; dst.WriteIt(2,"XY"); s.Rewind(); s.Skip(4);
    static_cast<FDataStream&>(dst) << static_cast<FDataStream&>(s);
    bytes("stream_copy",dst.GetBuf(),dst.GetEOF()); ProbeStream::state(s,"stream_source"); ProbeStream::state(dst,"stream_dest");
}

static void record(FDataStream& s, unsigned char* raw, bool writing) {
    unsigned char* p=raw;
#define FIELD(Type) { Type value; if(writing) { memcpy(&value,p,sizeof(Type)); s<<value; } \
    else { s>>value; memcpy(p,&value,sizeof(Type)); } p+=sizeof(Type); }
    FIELD(bool) FIELD(bool) FIELD(unsigned char) FIELD(char)
    FIELD(INT16) FIELD(UINT16) FIELD(WCHAR)
    FIELD(INT32) FIELD(UINT32) FIELD(unsigned long)
    FIELD(INT64) FIELD(UINT64) FIELD(float) FIELD(double) FIELD(GUID)
#undef FIELD
}
static void randomTrace(int endian, const char* path) {
    FILE* input=fopen(path,"rb"); if(!input) throw std::exception();
    std::vector<unsigned char> records; unsigned char raw[66];
    for (;;) {
        const size_t got=fread(raw,1,sizeof(raw),input);
        if(!got) break;
        if(got!=sizeof(raw)) { fclose(input); throw std::exception(); }
        records.insert(records.end(),raw,raw+sizeof(raw));
    }
    fclose(input);
    FMemoryStream s; s.SetDesiredEndianNess(static_cast<FEndian::EEndianness>(endian));
    for(size_t i=0;i<records.size();i+=66) record(s,&records[i],true);
    bytes("random",s.GetBuf(),s.GetEOF()); s.Rewind();
    unsigned int mismatches=0;
    for(size_t i=0;i<records.size();i+=66) {
        record(s,raw,false); if(memcmp(raw,&records[i],66)) ++mismatches;
    }
    printf("ROUNDTRIP|%u|%u\n",static_cast<unsigned int>(records.size()/66),mismatches);
    ProbeStream::state(s,"random_end");
}

#if defined(STREAM_CANDIDATE)
static void hardeningTrace() {
    unsigned int checks=0,rejections=0;
#define CHECK(expr) do { ++checks; if(!(expr)) throw std::exception(); } while(0)
#define REJECT(expr) do { bool caught=false; try { expr; } catch(const std::exception&) { caught=true; ++rejections; } CHECK(caught); } while(0)
    FMemoryStream s; s.WriteIt(4,"abcd"); s.SetPosition(2);
    REJECT(s.Skip(UINT_MAX)); CHECK(s.GetPosition()==2 && s.GetEOF()==4);
    REJECT(s.SetPosition(UINT_MAX)); CHECK(s.GetPosition()==2 && s.GetSizeLeft()==2);
    REJECT(s.WriteIt(UINT_MAX,"x")); CHECK(s.GetPosition()==2 && s.GetEOF()==4);
    REJECT(s.ReadIt(1,NULL)); REJECT(s.WriteIt(1,NULL));
    REJECT(s.Init(-1,NULL,true)); CHECK(s.GetEOF()==4 && s.GetPosition()==2);
    REJECT(s.Init(2,s.GetBuf()+1,true)); CHECK(!memcmp(s.GetBuf(),"abcd",4));
    s.Uninit(); CHECK(s.GetEOF()==0 && s.GetPosition()==0 && s.GetBytesUsed()==0 && s.GetSizeLeft()==0 && s.AtEnd());
    s.Uninit(); CHECK(s.GetBuf()==NULL);
    s.WriteIt(4,"abcd"); s.FastFwd(); s.WriteIt(4,s.GetBuf()); CHECK(s.GetEOF()==8 && !memcmp(s.GetBuf(),"abcdabcd",8));
    s.SetPosition(1); s.WriteIt(5,s.GetBuf()); CHECK(!memcmp(s.GetBuf(),"aabcdacd",8));
    s=s; CHECK(s.GetEOF()==8 && s.GetPosition()==6);
    FMemoryStream c(s); CHECK(c.GetPosition()==8 && !memcmp(c.GetBuf(),s.GetBuf(),8));
    c.Uninit(); c=s; CHECK(c.GetPosition()==8 && !memcmp(c.GetBuf(),s.GetBuf(),8));
    char fixed[4]={'a','b','c','d'}; FMemoryStream f(4,fixed,false);
    REJECT(f=c); CHECK(f.GetPosition()==0 && !memcmp(fixed,"abcd",4));
    REJECT(FMemoryStream(4,NULL,false));
    REJECT(s.Grow(UINT_MAX)); CHECK(s.GetEOF()==8);
    FMemoryStream malformed; malformed << static_cast<UINT32>(UINT_MAX); malformed.Rewind();
    std::string output="unchanged"; REJECT(malformed>>output); CHECK(output=="unchanged");
    malformed.Truncate(); malformed << static_cast<UINT32>(6); malformed.WriteIt(2,"xy"); malformed.Rewind();
    REJECT(malformed>>output); CHECK(output=="unchanged");
    malformed.Truncate(); malformed.WriteIt(1,"\2"); malformed.Rewind(); bool flag=false;
    REJECT(malformed>>flag); CHECK(!flag);
    static_assert(sizeof(void*)==8 && sizeof(unsigned int)==4 && sizeof(unsigned long)==4 && sizeof(wchar)==2,"SDK wire widths");
    CHECK(reinterpret_cast<UINT_PTR>(s.GetBuf())>0xffffffffULL);
    printf("HARDENING|%u|%u|64\n",checks,rejections);
#undef CHECK
#undef REJECT
}
#endif

int main(int argc, char** argv) {
    SetErrorMode(SEM_FAILCRITICALERRORS | SEM_NOGPFAULTERRORBOX);
    setvbuf(stdout, NULL, _IONBF, 0);
    try {
        const char* mode = argc > 1 ? argv[1] : "memory";
        if (!strcmp(mode, "memory")) memoryTrace();
        else if (!strncmp(mode, "scalar", 6)) scalarTrace(atoi(mode + 6));
        else if (!strncmp(mode, "bulk", 4)) bulkTrace(atoi(mode + 4));
        else if (!strncmp(mode, "random", 6) && argc==3) randomTrace(atoi(mode+6),argv[2]);
#if defined(STREAM_CANDIDATE)
        else if (!strcmp(mode,"hardening")) hardeningTrace();
#endif
        else edgeTrace(mode);
    } catch (const std::exception&) { printf("UNEXPECTED_EXCEPTION|std\n"); return 1; }
    catch (...) { printf("UNEXPECTED_EXCEPTION|other\n"); return 1; }
    return 0;
}
