// Portable framing tests. No GameCore, operating-system UI, save writer or inflater.
// Writer order follows BNW CvPreGame::writeArchive/saveSlotHints and CvInfos,
// independently of the production reader. Original utility conformance determines
// GameTypes=1 byte, GameMapTypes=4 bytes. Public offsets are fixed blob observations.
#include "../Source/Host/RetailSavePregame.h"
#include <fstream>
#include <iostream>
#include <limits>

namespace {
using Bytes = std::vector<unsigned char>;
using Prefix = ZeroSisHost::RetailSavePregame;
using Limits = ZeroSisHost::RetailSavePregameLimits;
using Error = ZeroSisHost::RetailSavePregameError;
using Code = ZeroSisHost::RetailSavePregameErrorCode;
using HeaderError = ZeroSisHost::RetailSaveHeaderError;
using HeaderCode = ZeroSisHost::RetailSaveHeaderErrorCode;
struct { std::size_t checks=0, fixtures=0, truncations=0, mutations=0, accepted=0, rejected=0; } counts;

void Check(bool condition, const char* message) {
    ++counts.checks;
    if (!condition) throw std::runtime_error(message);
}
template<class F> void Reject(Code code, F operation) {
    bool rejected=false;
    try { operation(); } catch (const Error& error) {
        Check(error.Code()==code,"Wrong Pregame error category"); rejected=true;
    }
    Check(rejected,"Invalid Pregame input was accepted");
}
template<class F> void RejectHeader(HeaderCode code, F operation) {
    bool rejected=false;
    try { operation(); } catch (const HeaderError& error) {
        Check(error.Code()==code,"Wrong metadata error category"); rejected=true;
    }
    Check(rejected,"Invalid metadata input was accepted");
}
Limits Bounded() {
    Limits l;
    l.maximumPrefixBytes=65536; l.maximumStringBytes=4096;
    l.maximumArrayRecords=4096; l.maximumTotalArrayRecords=16384;
    return l;
}
Bytes Read(const char* path) {
    std::ifstream f(path,std::ios::binary|std::ios::ate);
    Check(static_cast<bool>(f),"Cannot open explicit public fixture");
    const auto end=f.tellg();
    Check(end>std::streampos(0)&&end<=std::streampos(65536),"Fixture is not a bounded nonempty fragment");
    Bytes b(static_cast<std::size_t>(end)); f.seekg(0);
    f.read(reinterpret_cast<char*>(b.data()),static_cast<std::streamsize>(b.size()));
    Check(static_cast<bool>(f)&&f.gcount()==static_cast<std::streamsize>(b.size()),"Incomplete fixture read");
    Check(f.peek()==std::char_traits<char>::eof(),"Fixture changed during read");
    return b;
}
Bytes Join(const Bytes& a,const Bytes& b) { Bytes result=a;result.insert(result.end(),b.begin(),b.end());return result; }
void SetWord(Bytes& b,std::size_t at,std::uint32_t value) {
    Check(at<=b.size()&&b.size()-at>=4,"Invalid independent mutation offset");
    for (unsigned int i=0;i<4;++i) b[at+i]=static_cast<unsigned char>(value>>(8*i));
}

struct Writer {
    Bytes data;
    std::size_t metadataEnd=0,slotAt=0,archiveAt=0,worldAt=0,compressionAt=0;
    std::size_t firstArrayAt=0,adminLengthAt=0,records=0;
    bool rich;
    explicit Writer(bool varied):rich(varied) {}
    void Byte(unsigned char v) { data.push_back(v); }
    void Word(std::uint32_t v) { for (unsigned int i=0;i<4;++i) Byte(static_cast<unsigned char>(v>>(8*i))); }
    void Text(const std::string& s) {
        Check(s.size()<=65536,"Synthetic source string too large");
        Word(static_cast<std::uint32_t>(s.size())); data.insert(data.end(),s.begin(),s.end());
    }
    void BaseInfo() {
        Word(0x13579bdfu);
        for (unsigned int i=0;i<8;++i) {
            std::string s="info-"+std::to_string(i);
            s.append("\0x\x78\x9c",4); s+=u8"한글";
            Text(s); // All eight strings are nonempty, with NUL and magic-byte decoys.
        }
    }
    void Ints() {
        const std::uint32_t n=rich?2u:0u;Word(n);records+=n;
        if (n) { Word(0xffffffffu);Word(0x12345678u); }
    }
    void Flags() {
        const std::uint32_t n=rich?2u:0u;Word(n);records+=n;
        if (n) { Byte(0);Byte(1); }
    }
    void Strings() {
        const std::uint32_t n=rich?2u:0u;Word(n);records+=n;
        if (n) { Text("");Text(std::string("A\0B",3)+u8"문명"); }
    }
    void Options() {
        const std::uint32_t n=rich?2u:0u;Word(n);records+=n;
        if (n) { Text("OPTION_ALPHA");Word(0);Text("OPTION_BETA");Word(0xffffffffu); }
    }
};

Writer Synthetic(std::uint32_t outer,std::uint32_t world,std::uint32_t format,bool rich) {
    Writer w(rich);
    for (unsigned char c:std::string("CIV5")) w.Byte(c);
    w.Word(outer);w.Text("1.0.3.279");w.Text("403694");w.Word(42);w.Byte(1);
    for (const char* s:{"CIVILIZATION_KOREA","HANDICAP_PRINCE","ERA_ANCIENT","ERA_MEDIEVAL",
                        "GAMESPEED_STANDARD","WORLDSIZE_STANDARD","Maps\\test.lua"}) w.Text(s);
    w.Word(0);w.Word(0); // DLC and mod metadata lists.
    w.metadataEnd=w.data.size();
    w.Text("civilization name");w.Text("leader name");w.Text("PLAYERCOLOR_KOREA");
    for (unsigned int i=0;i<16;++i) w.Byte(i%2?0x9c:0x78);
    w.Text("1.0.0");for (unsigned int i=0;i<16;++i) w.Byte(static_cast<unsigned char>(i));w.Word(0);
    w.slotAt=w.data.size();w.Word(3);
    w.Word(2);w.Word(3);w.Text("Maps\\test.lua");
    w.firstArrayAt=w.data.size();w.Ints();w.Strings(); // civilizations, nicknames
    w.Ints();w.Ints();w.Ints();w.Ints(); // statuses, claims, teams, handicaps
    w.Strings();w.Strings(); // civilization and leader keys
    w.archiveAt=w.data.size();w.Word(6);
    w.Word(1);w.adminLengthAt=w.data.size();w.Text("admin");w.Word(50);w.Text("alias");
    w.Ints(); // art styles
    w.Byte(1);w.Word(0x3f800000u);w.Word(99);w.Word(2);w.Word(0);w.BaseInfo();
    w.Strings();w.Strings();w.Strings();w.Strings(); // civilization identity fields
    w.Word(1);w.BaseInfo();
    for (unsigned int i=0;i<11;++i) w.Word(0x10203040u+i); // climate scalars
    w.Word(2);w.Strings();w.Word(0x40000000u);w.Strings(); // era, emails, timer, decals
    w.Flags();w.Word(0);w.Text("game name"); // deprecated controls, mode, name
    w.Word(2);w.Byte(1);w.Word(42);w.Byte(0xfe);w.Word(0x71625344u);w.Word(3);
    w.Ints();w.Ints();w.Byte(0);w.Byte(1);w.Strings(); // handicaps and leader names
    w.Text("load name");w.Text("local email");w.Byte(0);w.Word(123);w.Byte(1);w.Byte(0);w.Text("Maps\\test.lua");
    w.Word(0);w.Word(500);w.Word(12);w.Strings(); // elimination, turn limit, minor keys
    w.Flags();w.Byte(0);w.Flags();w.Ints();w.Strings(); // minor flags, dummy, MP, net IDs, names
    w.Word(5);w.Word(24);w.Flags();w.Strings(); // victories, pitboss, playable, color keys
    w.Byte(0);w.Byte(1);w.Byte(0);w.Word(4);w.Byte(1);w.Byte(0);w.Byte(1);w.Flags();
    w.Word(0);w.BaseInfo();w.Word(7);w.Byte(0); // sea level and dummy
    w.Ints();w.Ints();w.Text("smtp");w.Word(456);w.Word(1000);w.Ints();w.Byte(1);
    w.BaseInfo();w.Word(1);w.Word(2);w.Word(3);w.Word(4);w.Word(0);w.Byte(1); // timer info and flags
    w.Flags();w.Flags();
    w.worldAt=w.data.size();w.Word(world);w.BaseInfo();
    for (unsigned int i=0;i<18;++i) w.Word(100+i);
    if (world==2) w.Word(27);
    w.Word(3);w.Options();w.Options();w.Text("1.0.3.279");
    w.Flags();w.Flags();w.Strings();
    w.compressionAt=w.data.size();w.Word(format);w.Word(65536);
    return w;
}

void Spans(const Prefix& p,std::size_t total) {
    Check(p.metadata.consumedPrefixBytes<=total,"Metadata escaped input");
    for (const auto span:{p.playerInfo,p.slotHints,p.archive,p.compressionHeader}) {
        Check(span.offset<=total,"Span offset escaped input");
        Check(span.bytes<=total-span.offset,"Span length escaped input");
    }
    Check(p.playerInfo.offset==p.metadata.consumedPrefixBytes,"Wrapper does not follow metadata");
    Check(p.playerInfo.bytes<=total-p.playerInfo.offset,"Wrapper escaped input");
    Check(p.slotHints.offset==p.playerInfo.offset+p.playerInfo.bytes,"Slot hints are not contiguous");
    Check(p.slotHints.bytes<=total-p.slotHints.offset,"Slot hints escaped input");
    Check(p.archive.offset==p.slotHints.offset+p.slotHints.bytes,"Archive is not contiguous");
    Check(p.archive.bytes<=total-p.archive.offset,"Archive escaped input");
    Check(p.compressionHeader.offset==p.archive.offset+p.archive.bytes,"Descriptor is not contiguous");
    Check(p.compressionHeader.bytes==8&&p.compressionHeader.bytes<=total-p.compressionHeader.offset,"Invalid descriptor span");
    Check(p.compressedDataOffset==p.compressionHeader.offset+8&&p.compressedDataOffset<=total,"Invalid compressed-body offset");
}
void Public(const Bytes& good,const Bytes& unsupported) {
    const auto p=Prefix::ParsePrefix(good,Bounded());Spans(p,good.size());
    Check(good.size()==10991&&p.metadata.consumedPrefixBytes==718,"Public metadata/retention offsets changed");
    Check(p.playerInfo.offset==718&&p.playerInfo.bytes==76,"Public wrapper offset mismatch");
    Check(p.slotHints.offset==794&&p.slotHints.bytes==3098,"Public slot-hints offset mismatch");
    Check(p.archive.offset==3892&&p.archive.bytes==7091,"Public archive offset mismatch");
    Check(p.compressionHeader.offset==10983&&p.compressedDataOffset==10991,"Public compression boundary mismatch");
    Check(p.slotHintsVersion==3&&p.archiveVersion==6&&p.worldInfoVersion==2,"Public versions mismatch");
    Check(p.compressionFormatId==2&&p.compressionChunkSize==65536&&p.arrayRecords==2082,"Public descriptor/count mismatch");
    Check(p.metadata.playerCivilization=="CIVILIZATION_DENMARK"&&p.metadata.currentTurn==264,"Public metadata changed");
    Check(unsupported.size()==5526,"Unsupported witness range changed");
    Reject(Code::UnsupportedPregameVersion,[&]{Prefix::ParsePrefix(unsupported,Bounded());});
    counts.fixtures+=2;
}
void SyntheticCases(const Writer& w,std::uint32_t outer,std::uint32_t world,std::uint32_t format) {
    const auto p=Prefix::ParsePrefix(w.data,Bounded());Spans(p,w.data.size());
    Check(p.metadata.saveGameVersion==outer&&p.metadata.consumedPrefixBytes==w.metadataEnd,"Synthetic metadata framing");
    Check(p.slotHints.offset==w.slotAt&&p.archive.offset==w.archiveAt,"Synthetic SDK span positions");
    Check(p.worldInfoVersion==world&&p.compressionFormatId==format,"Synthetic nested versions");
    Check(p.compressionHeader.offset==w.compressionAt&&p.compressedDataOffset==w.data.size(),"Magic decoy influenced boundary");
    Check(p.arrayRecords==w.records,"Synthetic total array records");
    // The API parses prefixes, not deflate validity: arbitrary tails do not turn
    // this success into a restored or fully validated save.
    auto opaque=w.data;opaque.insert(opaque.end(),{0,0x78,0x9c,0xff,0x78,0x9c});
    const auto tail=Prefix::ParsePrefix(opaque,Bounded());Spans(tail,opaque.size());
    Check(tail.compressedDataOffset==w.data.size(),"Opaque payload altered parsed prefix");
    auto exact=Bounded();exact.maximumPrefixBytes=w.data.size();exact.maximumTotalArrayRecords=w.records;
    Check(Prefix::ParsePrefix(w.data,exact).compressedDataOffset==w.data.size(),"Exact inclusive budgets rejected");
}
void Truncations(const Bytes& b,std::size_t metadataEnd) {
    for (std::size_t n=0;n<b.size();++n) {
        bool rejected=false;
        try { Prefix::ParsePrefix(b.data(),n,Bounded()); }
        catch (const Error& error) {
            Check(n>=metadataEnd&&error.Code()==Code::Truncated,"Wrong Pregame truncation category/domain");rejected=true;
        }
        catch (const HeaderError& error) {
            Check(n<metadataEnd&&error.Code()==HeaderCode::Truncated,"Wrong metadata truncation category/domain");rejected=true;
        }
        Check(rejected,"Truncated prefix was accepted");++counts.truncations;
    }
}
void Negatives(const Writer& w) {
    RejectHeader(HeaderCode::NullInput,[]{Prefix::ParsePrefix(nullptr,1);});
    RejectHeader(HeaderCode::Truncated,[]{Prefix::ParsePrefix(nullptr,0);});
    Bytes b=w.data;b[0]='X';RejectHeader(HeaderCode::Signature,[&]{Prefix::ParsePrefix(b);});
    for (auto version:{0u,6u,9u,0xffffffffu}) {
        auto changed=w.data;SetWord(changed,4,version);
        RejectHeader(HeaderCode::UnsupportedVersion,[&]{Prefix::ParsePrefix(changed);});
    }
    const auto checkWord=[&](std::size_t at,std::uint32_t value,Code expected) {
        Bytes changed=w.data;SetWord(changed,at,value);
        Reject(expected,[&]{Prefix::ParsePrefix(changed,Bounded());});
    };
    for (auto version:{0u,1u,2u,4u,0xffffffffu}) checkWord(w.slotAt,version,Code::UnsupportedSlotHintsVersion);
    for (auto version:{0u,1u,3u,5u,7u,0xffffffffu}) checkWord(w.archiveAt,version,Code::UnsupportedPregameVersion);
    for (auto version:{0u,3u,5u,0xffffffffu}) checkWord(w.worldAt,version,Code::UnsupportedWorldInfoVersion);
    for (auto format:{0u,3u,0xffffffffu}) checkWord(w.compressionAt,format,Code::UnsupportedCompressionFormat);
    for (auto size:{0u,65535u,65537u,0xffffffffu}) checkWord(w.compressionAt+4,size,Code::UnsupportedChunkSize);
    checkWord(w.adminLengthAt,1024u*1024u+1u,Code::StringLimit);
    checkWord(w.firstArrayAt,0xffffffffu,Code::RecordLimit);
    auto l=Bounded();l.maximumPrefixBytes=w.data.size()-1;
    Reject(Code::PrefixLimit,[&]{Prefix::ParsePrefix(w.data,l);});
    l=Bounded();l.maximumArrayRecords=0;
    Reject(Code::RecordLimit,[&]{Prefix::ParsePrefix(w.data,l);});
    l=Bounded();l.maximumTotalArrayRecords=w.records-1;
    Reject(Code::RecordLimit,[&]{Prefix::ParsePrefix(w.data,l);});
    // Force aggregate-count failure after one accepted nonempty array.
    l=Bounded();l.maximumTotalArrayRecords=2;
    Reject(Code::RecordLimit,[&]{Prefix::ParsePrefix(w.data,l);});
    l=Bounded();l.maximumPrefixBytes=w.metadataEnd-1;
    RejectHeader(HeaderCode::HeaderLimit,[&]{Prefix::ParsePrefix(w.data,l);});
    l=Bounded();l.maximumStringBytes=1;
    RejectHeader(HeaderCode::StringLimit,[&]{Prefix::ParsePrefix(w.data,l);});
}
struct Observation { bool accepted=false;int error=-1;Prefix value; };
Observation Probe(const Bytes& b) {
    Observation o;
    try { o.value=Prefix::ParsePrefix(b,Bounded());o.accepted=true;Spans(o.value,b.size()); }
    catch (const Error& e) { o.error=static_cast<int>(e.Code()); }
    catch (const HeaderError& e) { o.error=100+static_cast<int>(e.Code()); }
    return o;
}
std::uint32_t Next(std::uint32_t& state) { state=state*1664525u+1013904223u;return state; }
void Mutations(const Bytes& original,std::uint32_t seed) {
    for (std::size_t i=0;i<512;++i) {
        auto b=original;
        const auto edits=1u+Next(seed)%4u;
        for (std::uint32_t j=0;j<edits;++j) {
            const auto at=static_cast<std::size_t>(Next(seed))%b.size();
            b[at]^=static_cast<unsigned char>((Next(seed)>>16)|1u);
        }
        if (i%7==0) b.resize(static_cast<std::size_t>(Next(seed))%(b.size()+1));
        const auto a=Probe(b),again=Probe(b);
        Check(a.accepted==again.accepted&&a.error==again.error,"Nondeterministic bounded mutation outcome");
        if (a.accepted) {
            Check(a.value.compressedDataOffset==again.value.compressedDataOffset&&
                a.value.arrayRecords==again.value.arrayRecords&&a.value.archive.offset==again.value.archive.offset,
                "Nondeterministic bounded mutation boundary");++counts.accepted;
        } else ++counts.rejected;
        ++counts.mutations;
    }
}
std::string Json(const std::string& text) {
    std::string s="\"";constexpr char hex[]="0123456789abcdef";
    for (const unsigned char c:text) {
        if (c=='"'||c=='\\') {s+='\\';s+=static_cast<char>(c);}
        else if (c<32) {s+="\\u00";s+=hex[c>>4];s+=hex[c&15];}
        else s+=static_cast<char>(c);
    }
    return s+'"';
}
void Summary(bool success,const std::string& error={}) {
    std::cout<<"{\"status\":\""<<(success?"PASS_PUBLIC_PREGAME_COMPONENT":"FAIL_PUBLIC_PREGAME_COMPONENT")
        <<"\",\"checks\":"<<counts.checks<<",\"fixtures\":"<<counts.fixtures
        <<",\"truncations\":"<<counts.truncations<<",\"mutations\":"<<counts.mutations
        <<",\"accepted_mutations\":"<<counts.accepted<<",\"rejected_mutations\":"<<counts.rejected
        <<",\"supported_public_profiles\":1,\"unsupported_public_profile_witnesses\":1"
        <<",\"compressed_payload_validated\":false,\"sdk_restore_verified\":false"
        <<",\"input_files_unchanged\":"<<(success?"true":"null")
        <<",\"gamecore_loaded\":false,\"window_created\":false";
    if (!error.empty()) std::cout<<",\"error\":"<<Json(error);
    std::cout<<"}\n";
}
}

int main(int argc,char** argv) {
    static_assert(sizeof(void*)==8,"This component must execute as x64");
    try {
        Check(argc==5,"Expected exactly four explicit public fragment paths");
        const auto a=Read(argv[1]),b=Read(argv[2]),c=Read(argv[3]),d=Read(argv[4]);
        const auto good=Join(a,b),unsupported=Join(c,d);Public(good,unsupported);
        for (auto outer:{7u,8u}) for (auto world:{1u,2u}) for (auto format:{1u,2u}) for (bool rich:{false,true})
            SyntheticCases(Synthetic(outer,world,format,rich),outer,world,format);
        const auto rich7=Synthetic(7,1,1,true),rich8=Synthetic(8,2,2,true);
        Negatives(rich8);Truncations(good,718);Truncations(rich7.data,rich7.metadataEnd);Truncations(rich8.data,rich8.metadataEnd);
        Mutations(good,0x403694u);Mutations(unsupported,0x8c1057u);
        Mutations(rich7.data,0x7ab84cu);Mutations(rich8.data,0x80ff94u);
        Check(Read(argv[1])==a&&Read(argv[2])==b&&Read(argv[3])==c&&Read(argv[4])==d,"Public fixtures changed");
        Check(counts.fixtures==2&&counts.mutations==2048,"Incomplete fixture/mutation coverage");
        Summary(true);return 0;
    } catch (const std::exception& e) { Summary(false,e.what());return 1; }
    catch (...) { Summary(false,"Unexpected nonstandard exception");return 2; }
}
