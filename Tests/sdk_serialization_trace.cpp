// Direct SDK enum operators and container header templates, in isolated tests.
#include "SdkSerializationIncludes.h"
#include "SdkGameCoreSerializationExtract.h"

static unsigned int checks=0;
static void require(bool value) { ++checks; if(!value) { fprintf(stderr,"FAIL|%u\n",checks); throw std::exception(); } }
static std::vector<unsigned char> readFile(const std::string& path) {
    FILE* file=fopen(path.c_str(),"rb"); require(file!=NULL);
    std::vector<unsigned char> data; unsigned char block[4096]; size_t size;
    while((size=fread(block,1,sizeof(block),file))!=0) data.insert(data.end(),block,block+size);
    require(ferror(file)==0); fclose(file); return data;
}
static void writeFile(const std::string& path,const FMemoryStream& stream) {
    FILE* file=fopen(path.c_str(),"wb"); require(file!=NULL);
    const size_t written=fwrite(stream.GetBuf(),1,stream.GetEOF(),file);
    fclose(file); require(written==stream.GetEOF());
}
static unsigned int bits32(const void* value) { unsigned int bits; memcpy(&bits,value,4); return bits; }
template<unsigned int WireBytes> struct EnumReadValue { static unsigned int expected(unsigned int bits) { return bits; } };
template<> struct EnumReadValue<1> {
    static unsigned int expected(unsigned int bits) { const unsigned int byte=bits&255u; return byte<128 ? byte : byte|0xffffff00u; }
};

template<class E,unsigned int WireBytes> static void enumTrace(const char* name,const std::vector<unsigned char>& data,int endian,FILE* file) {
    typedef char AssertSize[sizeof(E)==4?1:-1]; (void)sizeof(AssertSize);
    FMemoryStream stream; stream.SetDesiredEndianNess(static_cast<FEndian::EEndianness>(endian));
    for(size_t i=0;i<data.size();i+=4) {
        E value; memcpy(&value,&data[i],4);
        FDataStream& returned=operator<<(stream,value); require(&returned==&stream);
    }
    require(stream.GetEOF()==data.size()/4*WireBytes);
    require(fwrite(stream.GetBuf(),1,stream.GetEOF(),file)==stream.GetEOF());
    stream.Rewind();
    for(size_t i=0;i<data.size();i+=4) {
        E value; FDataStream& returned=operator>>(stream,value);
        const unsigned int expected=EnumReadValue<WireBytes>::expected(bits32(&data[i]));
        require(&returned==&stream); require(bits32(&value)==expected);
    }
    require(stream.AtEnd());
    printf("ENUM|%s|%u\n",name,static_cast<unsigned int>(data.size()/4));
}
static void allEnums(const char* input,const char* output,int endian) {
    const std::vector<unsigned char> data=readFile(input); require(!data.empty() && data.size()%4==0);
    FILE* file=fopen(output,"wb"); require(file!=NULL);
#define SDK_ENUM(Type) enumTrace<Type,4>(#Type,data,endian,file);
#define SDK_ENUM_BYTE(Type) enumTrace<Type,1>(#Type,data,endian,file);
#include "SdkEnumTypes.inc"
#undef SDK_ENUM
#undef SDK_ENUM_BYTE
    fclose(file);
}

template<class T> static bool sameLogicalValues(const T& a,const T& b) { return a==b; }
static bool sameLogicalValues(const stdext::hash_map<int,int>& a,const stdext::hash_map<int,int>& b) {
    return std::map<int,int>(a.begin(),a.end())==std::map<int,int>(b.begin(),b.end());
}
#if _MSC_VER >= 1900
typedef std::unordered_set<int> TestUnorderedSet;
#else
typedef std::tr1::unordered_set<int> TestUnorderedSet;
#endif
static bool sameLogicalValues(const TestUnorderedSet& a,const TestUnorderedSet& b) {
    // VC9 _Hash::operator== compares iteration order, including after a load.
    return std::set<int>(a.begin(),a.end())==std::set<int>(b.begin(),b.end());
}
static bool sameLogicalValues(const VoteSelectionData& a,const VoteSelectionData& b) {
    if(a.iId!=b.iId || a.eVoteSource!=b.eVoteSource || a.aVoteOptions.size()!=b.aVoteOptions.size()) return false;
    for(size_t i=0;i<a.aVoteOptions.size();++i) {
        const VoteSelectionSubData& x=a.aVoteOptions[i]; const VoteSelectionSubData& y=b.aVoteOptions[i];
        if(x.eVote!=y.eVote || x.ePlayer!=y.ePlayer || x.iCityId!=y.iCityId || x.eOtherPlayer!=y.eOtherPlayer || x.strText!=y.strText) return false;
    }
    return true;
}
template<class T> static void existingValues(FDataStream&,const T&) {}
static void existingValues(FDataStream& source,const CvReplayInfo::TurnData& value) {
    source.Rewind(); CvReplayInfo::TurnData result; result[17]=11; result[42]=999;
    CvReplayInfo::TurnData expected=result;
    for(CvReplayInfo::TurnData::const_iterator it=value.begin();it!=value.end();++it) expected[it->first]=it->second;
    source>>result; require(result==expected && source.AtEnd());
    printf("EXISTING_VALUES|replay_merge\n");
}
static void existingValues(FDataStream& source,const VoteSelectionData& value) {
    source.Rewind(); VoteSelectionData result; VoteSelectionSubData old; old.iCityId=99;
    result.aVoteOptions.push_back(old); VoteSelectionData expected=value;
    expected.aVoteOptions.insert(expected.aVoteOptions.begin(),old);
    source>>result; require(sameLogicalValues(result,expected) && source.AtEnd());
    printf("EXISTING_VALUES|vote_append\n");
}
template<class T> static void container(const char* name,const T& value,int endian,const char* directory,bool reading) {
    const std::string path=std::string(directory)+"/"+name+".bin";
    FMemoryStream encoded; encoded.SetDesiredEndianNess(static_cast<FEndian::EEndianness>(endian));
    if(!reading) { encoded<<value; writeFile(path,encoded); }
    const std::vector<unsigned char> raw=readFile(path);
    FMemoryStream source(static_cast<int>(raw.size()),raw.empty()?NULL:&raw[0],false);
    source.SetDesiredEndianNess(static_cast<FEndian::EEndianness>(endian));
    T result; source>>result; require(source.AtEnd());
    require(sameLogicalValues(result,value));
    existingValues(source,value);
    printf("CONTAINER|%s|%u\n",name,static_cast<unsigned int>(raw.size()));
}
static void containers(const char* directory,int endian,bool reading) {
    std::vector<int> v; const int values[]={-1,0,INT_MIN,INT_MAX,0x12345678};
    for(unsigned int i=0;i<sizeof(values)/sizeof(values[0]);++i) v.push_back(values[i]);
    container("vector_int",v,endian,directory,reading);
    std::vector<int> empty; container("vector_empty",empty,endian,directory,reading);
    std::deque<std::string> dq; dq.push_back(""); dq.push_back("abc"); dq.push_back(std::string("x\0y",3));
    container("deque_string",dq,endian,directory,reading);
    std::list<UnitTypes> units; units.push_back(NO_UNIT); units.push_back(static_cast<UnitTypes>(42));
    container("list_enum",units,endian,directory,reading);
    std::map<int,std::string> m; m[-3]="A"; m[4]=std::string("x\0y",3); m[17]="\xed\x95\x9c";
    container("map_string",m,endian,directory,reading);
    std::set<int> ordered; ordered.insert(-1); ordered.insert(0); ordered.insert(42);
    container("set_int",ordered,endian,directory,reading);
    std::vector<std::vector<int> > nested; nested.push_back(empty); nested.push_back(v); nested.push_back(std::vector<int>(3,7));
    container("nested_vector",nested,endian,directory,reading);
    std::string binary; for(int i=0;i<256;++i) binary.push_back(static_cast<char>(i));
    container("string_binary",binary,endian,directory,reading);
    container("string_empty",std::string(),endian,directory,reading);
    stdext::hash_map<int,int> hash; for(int i=0;i<20;++i) hash[(i*17)%53]=i-7;
    container("hash_map",hash,endian,directory,reading);
    TestUnorderedSet us;
    for(int i=0;i<20;++i) us.insert((i*17)%53);
    container("unordered_set",us,endian,directory,reading);
    CvReplayInfo::TurnData turns; turns[0]=INT_MIN; turns[42]=-1; turns[UINT_MAX]=INT_MAX;
    container("replay_turn_data",turns,endian,directory,reading);
    container("replay_empty",CvReplayInfo::TurnData(),endian,directory,reading);
    VoteSelectionData vote; vote.iId=-7; vote.eVoteSource=static_cast<VoteSourceTypes>(42);
    VoteSelectionSubData option; vote.aVoteOptions.push_back(option);
    option.eVote=static_cast<VoteTypes>(INT_MAX); option.ePlayer=static_cast<PlayerTypes>(63);
    option.iCityId=INT_MIN; option.eOtherPlayer=static_cast<PlayerTypes>(17);
    option.strText.assign("x\0\xed\x95\x9c",5); vote.aVoteOptions.push_back(option);
    container("vote_selection",vote,endian,directory,reading);
    container("vote_empty",VoteSelectionData(),endian,directory,reading);
}

#ifdef SERIALIZATION_CANDIDATE
struct CountOnlyContainer {
    size_t count;
    explicit CountOnlyContainer(size_t n):count(n) {}
    size_t size() const { return count; }
};
static void countBoundaries() {
    FMemoryStream stream; stream.WriteIt(2,"ok");
    CountOnlyContainer huge(static_cast<size_t>(0x100000000ULL));
    bool rejected=false;
    try { SerializeFromSequenceContainer<int,CountOnlyContainer> value(stream,huge); (void)value; }
    catch(const std::exception&) { rejected=true; }
    require(rejected && stream.GetPosition()==2 && stream.GetEOF()==2 && !memcmp(stream.GetBuf(),"ok",2));
    rejected=false;
    try { SerializeFromAssociativeContainer<int,CountOnlyContainer> value(stream,huge); (void)value; }
    catch(const std::exception&) { rejected=true; }
    require(rejected && stream.GetPosition()==2 && stream.GetEOF()==2 && !memcmp(stream.GetBuf(),"ok",2));
    stream.Truncate(); CountOnlyContainer maximum(static_cast<size_t>(UINT_MAX));
    SerializeFromSequenceContainer<int,CountOnlyContainer> limit(stream,maximum); (void)limit;
    require(stream.GetEOF()==4); stream.Rewind(); unsigned int count=0; stream>>count; require(count==UINT_MAX);
    printf("COUNT_BOUNDARIES|2|4\n");
}
#endif

int main(int argc,char** argv) {
    SetErrorMode(SEM_FAILCRITICALERRORS|SEM_NOGPFAULTERRORBOX); setvbuf(stdout,NULL,_IONBF,0);
    try {
        require(argc>=5);
        const int endian=atoi(argv[2]); require(endian>=0 && endian<=2);
        if(!strcmp(argv[1],"enums")) { require(argc==5); allEnums(argv[3],argv[4],endian); }
        else if(!strcmp(argv[1],"containers")) containers(argv[3],endian,!strcmp(argv[4],"read"));
#ifdef SERIALIZATION_CANDIDATE
        else if(!strcmp(argv[1],"boundaries")) countBoundaries();
#endif
        else require(false);
        printf("PASS|%u\n",checks); return 0;
    } catch(...) { fprintf(stderr,"UNEXPECTED_EXCEPTION\n"); return 1; }
}
