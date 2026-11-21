#include "SdkStringIncludes.h"
static unsigned checks=0;
#define CHECK(x) do { ++checks; if(!(x)) { std::fprintf(stderr,"FAIL|%u|%d|%s\n",checks,__LINE__,#x); std::exit(2); } } while(0)
static void Emit(const char* label,const FStringA& text) {
    std::printf("A|%s|%d|",label,text.GetLength());
    for(int i=0;i<text.GetLength();++i)std::printf("%02x",static_cast<unsigned char>(text.c_str()[i]));
    CHECK(text.c_str()[text.GetLength()]==0);std::printf("\n");
}
static void Emit(const char* label,const FStringW& text) {
    std::printf("W|%s|%d|",label,text.GetLength());
    for(int i=0;i<text.GetLength();++i)std::printf("%04x",static_cast<unsigned>(text.c_str()[i]));
    CHECK(text.c_str()[text.GetLength()]==0);std::printf("\n");
}
static void Values() {
    FStringA empty; FStringW wempty; Emit("empty",empty);Emit("empty",wempty);
    const char narrow[]={'a',0,'b','c',0}; const wchar_t wide[]={L'a',0,0xd55c,0xae00,0};
    FStringA a(narrow,4),copy(a); FStringW w(wide,4),wcopy(w);
    Emit("binary",a);Emit("binary",w); Emit("copy",copy);Emit("copy",wcopy);
    a="abcdef";a.Copy(3,"xx12345",2);Emit("offset",a);
    a.SetAt(1,2,"YZ");Emit("overwrite",a);a.SetAt(3,2,"ab");Emit("append",a);
    a.SetAt(1,1,"q");Emit("tail",a);
    a.Copy(-1,"ignored");a.SetAt(-1,2,"zz");a.SetAt(900,2,"zz");Emit("invalid_noop",a);
    a.Copy(0,NULL);Emit("zero",a);a="seed";a.Copy(5,NULL);Emit("null",a);
    a="aAaA";const int replacements=a.Replace('a','z');CHECK(replacements==2);Emit("replace",a);
    a=narrow; a.Copy(4,narrow);const int zeros=a.Replace('b',char(0));CHECK(zeros==1);Emit("replace_nul",a);
    w=L"abcdef";w.Copy(3,L"xx12345",2);Emit("offset",w);w.Copy(0,NULL);Emit("zero",w);
    for(int length=1;length<=129;++length) {
        const std::string text(static_cast<size_t>(length),'a');const std::wstring wt(static_cast<size_t>(length),0xd55c);
        FStringA item(text);FStringW witem(wt);CHECK(item.GetLength()==length && witem.GetLength()==length);
        // GetMaxLength is declared but absent in the Windows archive; inspect
        // the public data header using the SDK's documented contiguous layout.
        const FStringA::FStringAData* data=reinterpret_cast<const FStringA::FStringAData*>(item.c_str())-1;
        const FStringW::FStringWData* wdata=reinterpret_cast<const FStringW::FStringWData*>(witem.c_str())-1;
        std::printf("CAP|%d|%d|%d\n",length,data->m_iAllocLength,wdata->m_iAllocLength);
    }
    a="retained";a.Reserve(400);CHECK(a.GetLength()==8);Emit("reserve",a);a.Empty();Emit("empty_retained",a);
    std::printf("VALUES_DONE\n");
}
static void Fixed() {
    FStringA a;FStringA::FStringAFixedBuffer<16> buffer(a);
    const char* initial=a.c_str();a="twelve chars";CHECK(a.c_str()==initial);Emit("fixed",a);
    a="This string must grow beyond sixteen bytes";CHECK(a.c_str()!=initial);Emit("grown",a);
    FStringW w;FStringW::FStringWFixedBuffer<16> wbuffer(w);
    const wchar_t* winitial=w.c_str();w=L"short";CHECK(w.c_str()==winitial);Emit("fixed",w);
    w=L"This string must grow beyond sixteen chars";CHECK(w.c_str()!=winitial);Emit("grown",w);
    a.Format("%s:%d:%08X:%I64d","entry",17,0xabcdef,-9223372036854775807LL);Emit("format",a);
    // Deliberately exercise the SDK's documented single-pointer class-vararg
    // ABI; this is an MSVC extension and is not a portable C++ calling pattern.
#if _MSC_VER >= 1900
#pragma warning(push)
#pragma warning(disable:4840)
#endif
    FStringA word("word");a.Format("%s",word);Emit("class_vararg",a);
#if _MSC_VER >= 1900
#pragma warning(pop)
#endif
    a.Format("%.*s:%c:%u",3,"abcdef",'z',4294967295u);Emit("format_fields",a);
    a.Format("embedded:%c:end",0);Emit("format_nul",a);
}
static void Paths() {
    const wchar_t* paths[]={L"",L"name",L"name.ext",L"a.b.c",L".hidden",L"C:\\folder\\map.Civ5Map",L"C:\\folder\\",L"/dir.with.dot/map.ext",L"a/b\\c.ext",L"a:map.ext",L"prefix:map.ext",L"one:two:map.ext",L":name",L"\\\\host\\dir\\file.ext"};
    for(unsigned i=0;i<sizeof(paths)/sizeof(paths[0]);++i) {
        FStringW source(paths[i]), result;
        source.ExtractFileTitle(result,L'\\');Emit("backslash",result);Emit("source",source);
        source.ExtractFileTitle(result,L'/');Emit("slash",result);
    }
    const wchar_t binary[]={L'a',0,L'/',L'b',L'.',L'c',0};FStringW source(binary,6),result;
    source.ExtractFileTitle(result,L'/');Emit("embedded_nul",result);
    source.ExtractFileTitle(result,0);Emit("nul_delimiter",result);
}
static void Encoding() {
    const char* utf8[]={"","ASCII","\xed\x95\x9c\xea\xb8\x80","\xf0\x9f\x8c\x8d","\xc0\xaf","\xed\xa0\x80","\xe2\x82","\xff","\xef\xbb\xbftext"};
    for(unsigned i=0;i<sizeof(utf8)/sizeof(utf8[0]);++i) {
        const std::wstring decoded=CvStringUtils::FromUTF8ToUTF16(utf8[i]);
        FStringW w(decoded);Emit("decode",w);FStringA encoded;w.CopyToUTF8(&encoded);Emit("encode",encoded);
    }
    std::string binary("a\0b",3);std::wstring decoded=CvStringUtils::FromUTF8ToUTF16(binary);Emit("decode_nul",FStringW(decoded));
    const wchar_t content[]={L'a',0,L'b',0};FStringW w(content,3);FStringA out("before");w.CopyToUTF8(&out);Emit("encode_nul",out);
    const wchar_t broken[]={0xd800,0};FStringW invalid(broken);invalid.CopyToUTF8(&out);Emit("lone_surrogate",out);
}
static std::string StreamPayload(unsigned item) {
    const unsigned lengths[]={256,4096,65535,65536};
    const unsigned length=item<130?item:lengths[item-130];std::string value(length,'\0');
    for(unsigned i=0;i<length;++i)value[i]=static_cast<char>((i*73u+length)&255u);return value;
}
static void ReadFields(FMemoryStream& stream) {
    FStringA a("old"),b("old"),c("old");stream>>a>>b>>c;
    Emit("stream_binary",a);Emit("stream_empty",b);Emit("stream_unicode",c);
    CHECK(a.GetLength()==4 && !std::memcmp(a.c_str(),"a\0bc",4));CHECK(b.GetLength()==0);
    CHECK(c.GetLength()==6 && !std::memcmp(c.c_str(),"\xed\x95\x9c\xea\xb8\x80",6));
    for(unsigned item=0;item<134;++item) {
        const std::string expected=StreamPayload(item);FStringA value("old");stream>>value;
        CHECK(value.GetLength()==static_cast<int>(expected.size()));
        CHECK(!std::memcmp(value.c_str(),expected.c_str(),expected.size()+1));
    }
}
static void Stream(const char* output) {
    FILE* file=fopen(output,"wb");CHECK(file!=NULL);
    for(int endian=0;endian<3;++endian) {
        FMemoryStream stream;stream.SetDesiredEndianNess(static_cast<FEndian::EEndianness>(endian));
        const char payload[]={'a',0,'b','c',0};FStringA first(payload,4),empty,unicode("\xed\x95\x9c\xea\xb8\x80");
        stream<<first<<empty<<unicode;
        for(unsigned item=0;item<134;++item)stream<<FStringA(StreamPayload(item));
        CHECK(fwrite(stream.GetBuf(),1,stream.GetEOF(),file)==stream.GetEOF());
        stream.Rewind();ReadFields(stream);CHECK(stream.GetPosition()==stream.GetEOF());
        std::printf("STREAM|%d|137|%u\n",endian,stream.GetEOF());
    }
    CHECK(fclose(file)==0);
}
static void ReadStream(const char* input) {
    FILE* file=fopen(input,"rb");CHECK(file!=NULL);CHECK(fseek(file,0,SEEK_END)==0);const long size=ftell(file);CHECK(size>=0);rewind(file);
    std::vector<char> bytes(static_cast<size_t>(size));CHECK(fread(&bytes[0],1,bytes.size(),file)==bytes.size());CHECK(fclose(file)==0);
    FMemoryStream stream(static_cast<int>(bytes.size()),&bytes[0]);
    for(int endian=0;endian<3;++endian) { stream.SetDesiredEndianNess(static_cast<FEndian::EEndianness>(endian));ReadFields(stream); }
    CHECK(stream.GetPosition()==stream.GetEOF());
}
static void Overlap() {
    FStringA a("abcdef");a.Copy(3,a.c_str(),1);Emit("same_base_copy",a);
    a="abcdef";a.Copy(3,a.c_str()+1);Emit("interior_copy",a);
    FStringW w(L"abcdef");w.Copy(3,w.c_str(),1);Emit("same_base_copy",w);
    w=L"abcdef";w.Copy(3,w.c_str()+1);Emit("interior_copy",w);
    a="abcdef";a.Reserve(2);Emit("short_reserve",a);
    w=L"abcdef";w.Reserve(2);Emit("short_reserve",w);
}
static void FixedBoundary() {
    struct Narrow { FStringA::FStringAFixedBuffer<16> buffer; unsigned char canary[8]; } storage;
    struct Wide { FStringW::FStringWFixedBuffer<16> buffer; unsigned char canary[8]; } wstorage;
    std::memset(storage.canary,0x7b,sizeof(storage.canary));std::memset(wstorage.canary,0x7b,sizeof(wstorage.canary));
    FStringA a;FStringW w;a.SetFixedBuffer(&storage.buffer.GetStringData());w.SetFixedBuffer(&wstorage.buffer.GetStringData());
    a="1234567890123456";w=L"1234567890123456";
    Emit("boundary",a);Emit("boundary",w);
    std::printf("CANARY|%u|%u|%u\n",storage.canary[0],wstorage.canary[0],wstorage.canary[1]);
    CHECK(a.GetLength()==16 && w.GetLength()==16);
}
static unsigned Next(unsigned& seed) { seed=seed*1664525u+1013904223u;return seed; }
template<class C,class S> static void CorpusType(const char* name,unsigned seed) {
    S actual;std::basic_string<C> expected;unsigned checksum=2166136261u;
    for(unsigned step=0;step<4096;++step) {
        const unsigned action=Next(seed)%7;const int size=static_cast<int>(Next(seed)%97);
        std::basic_string<C> external(static_cast<size_t>(size)+4,C());
        for(size_t j=0;j<external.size();++j)external[j]=static_cast<C>(Next(seed)&(sizeof(C)==1?255:65535));
        if(action==0 || expected.size()>2048) { actual.Copy(size,external.data(),2);expected.assign(external.data()+2,size); }
        else if(action==1) {
            const int index=static_cast<int>(Next(seed)%(expected.size()+1));
            actual.SetAt(index,size,external.data(),1);
            if(size) { if(expected.size()<static_cast<size_t>(index+size))expected.resize(index+size);expected.replace(index,size,external.data()+1,size); }
        } else if(action==2) {
            const C from=external[0],to=external[1];int replacements=0;
            for(size_t j=0;j<expected.size();++j)if(expected[j]==from) { expected[j]=to;++replacements; }
            CHECK(actual.Replace(from,to)==replacements);
        } else if(action==3) { actual.Reserve(std::max(size*8,actual.GetLength())); }
        else if(action==4) { actual.Empty();expected.clear(); }
        else if(action==5) { S copied(actual);actual=copied; }
        else { actual.Concat(size,external.data(),3);expected.append(external.data()+3,size); }
        CHECK(actual.GetLength()==static_cast<int>(expected.size()));
        if(std::memcmp(actual.c_str(),expected.c_str(),(expected.size()+1)*sizeof(C))) {
            std::fprintf(stderr,"CORPUS_MISMATCH|%s|step=%u|action=%u|size=%d|length=%u\n",name,step,action,size,static_cast<unsigned>(expected.size()));
            Emit("actual",actual);Emit("expected",S(expected));
        }
        CHECK(!std::memcmp(actual.c_str(),expected.c_str(),(expected.size()+1)*sizeof(C)));
        checksum=(checksum^static_cast<unsigned>(expected.size()))*16777619u;
        for(size_t j=0;j<expected.size();++j)checksum=(checksum^(static_cast<unsigned>(actual.c_str()[j])&(sizeof(C)==1?255:65535)))*16777619u;
    }
    std::printf("CORPUS|%s|4096|%08x\n",name,checksum);
}
static void Corpus() { CorpusType<char,FStringA>("A",0x12345678u);CorpusType<wchar_t,FStringW>("W",0x89abcdefu); }
int main(int argc,char** argv) {
    if(argc<2)return 1;
    if(!std::strcmp(argv[1],"values"))Values();else if(!std::strcmp(argv[1],"fixed"))Fixed();
    else if(!std::strcmp(argv[1],"paths"))Paths();else if(!std::strcmp(argv[1],"encoding"))Encoding();
    else if(!std::strcmp(argv[1],"stream") && argc==3)Stream(argv[2]);else if(!std::strcmp(argv[1],"overlap"))Overlap();
    else if(!std::strcmp(argv[1],"read") && argc==3)ReadStream(argv[2]);
    else if(!std::strcmp(argv[1],"boundary"))FixedBoundary();else if(!std::strcmp(argv[1],"corpus"))Corpus();
    else return 1;
    std::printf("PASS|%u\n",checks);return 0;
}
