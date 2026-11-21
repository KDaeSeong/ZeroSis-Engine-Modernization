#include "SdkWorldBuilderIncludes.h"
static unsigned checks=0;
#define CHECK(x) do { ++checks; if(!(x)) { std::fprintf(stderr,"FAIL|%u|%d|%s\n",checks,__LINE__,#x); std::exit(2); } } while(0)
static void Bytes(const char* label,const void* data,size_t size) {
    const unsigned char* p=static_cast<const unsigned char*>(data);
    std::printf("BYTES|%s|%u|",label,static_cast<unsigned>(size));
    for(size_t i=0;i<size;++i)std::printf("%02x",p[i]);
    std::printf("\n");
}
static void Text(const char* label,const char* s) {
    if(s)Bytes(label,s,std::strlen(s));else std::printf("NULL|%s\n",label);
}
static std::vector<unsigned char> GroupBytes(const CvWorldBuilderMapTypeGroup& g,const char* label) {
    std::vector<unsigned char> bytes(g.GetSerializedSize()+8,0xcc);g.Serialize(&bytes[0]);
    for(size_t i=g.GetSerializedSize();i<bytes.size();++i)CHECK(bytes[i]==0xcc);
    bytes.resize(g.GetSerializedSize());Bytes(label,bytes.empty()?NULL:&bytes[0],bytes.size());return bytes;
}
static void Groups() {
    CvWorldBuilderMapTypeGroup g;GroupBytes(g,"empty");
    const char* names[]={"alpha","BETA","alpha","","beta","ALPHA","prefix","prefix_tail","\xed\x95\x9c\xea\xb8\x80"};
    for(unsigned i=0;i<sizeof(names)/sizeof(names[0]);++i){g.Add(names[i]);GroupBytes(g,"add");}
    for(unsigned i=0;i<sizeof(names)/sizeof(names[0]);++i)std::printf("HAS|%u|%u\n",i,g.Contains(names[i])?1:0);
    std::printf("HAS|missing|%u\n",g.Contains("absent")?1:0);
    CvWorldBuilderMapTypeGroup copy(g),assigned;assigned=g;
    const std::vector<unsigned char> before=GroupBytes(g,"before");
    g.Remove("alpha");GroupBytes(g,"remove_alpha");g.Remove("BETA");GroupBytes(g,"remove_BETA");
    g.Remove("missing");g.Remove("");GroupBytes(g,"remove_empty");g.Clear();GroupBytes(g,"clear");
    CHECK(before==GroupBytes(copy,"copy"));CHECK(before==GroupBytes(assigned,"assigned"));
    CvWorldBuilderMapTypeGroup round;round.Deserialize(&before[0],static_cast<uint>(before.size()));CHECK(before==GroupBytes(round,"round"));
    round.Deserialize(NULL,0);GroupBytes(round,"deserialize_zero");
}
static void GroupSelf() {
    CvWorldBuilderMapTypeGroup g;g.Add("one");g.Add("two");GroupBytes(g,"self_before");g=g;GroupBytes(g,"self_after");
}
static void GroupLength(uint length) {
    const std::string value(length,'x');CvWorldBuilderMapTypeGroup g;g.Add(value.c_str());GroupBytes(g,"long");
    std::printf("LONG_HAS|%u|%u\n",length,g.Contains(value.c_str())?1:0);g.Remove(value.c_str());GroupBytes(g,"long_removed");
}
static std::vector<unsigned char> TypeBytes(const CvWorldBuilderMapTypeDesc::TypeMap& m,const char* label) {
    std::vector<unsigned char> bytes(m.GetSerializedSize()+8,0xcc);m.Serialize(&bytes[0]);
    for(size_t i=m.GetSerializedSize();i<bytes.size();++i)CHECK(bytes[i]==0xcc);
    bytes.resize(m.GetSerializedSize());Bytes(label,bytes.empty()?NULL:&bytes[0],bytes.size());return bytes;
}
static void Types() {
    typedef CvWorldBuilderMapTypeDesc::TypeMap Map;typedef CvWorldBuilderMapTypeDesc::String String;
    Map m;TypeBytes(m,"empty");const char* names[]={NULL,"","alpha","alpha","ALPHA","beta",NULL,"\xed\x95\x9c\xea\xb8\x80"};
    for(unsigned i=0;i<sizeof(names)/sizeof(names[0]);++i)std::printf("ADD|%u|%u\n",i,m.Add(names[i]));
    const std::vector<unsigned char> bytes=TypeBytes(m,"types");
    for(uint i=0;i<m.Size()+2;++i)Text("get",m.Get(i));
    const char* queries[]={"","alpha","ALPHA","beta","missing"};
    for(unsigned i=0;i<sizeof(queries)/sizeof(queries[0]);++i){uint out=12345;const bool found=m.FindType(queries[i],out);std::printf("FIND|%u|%u|%u\n",i,found?1:0,out);}
    String a("alpha"),b("alpha"),c("ALPHA"),n(NULL),e("");
    std::printf("IDENTITY|%u|%u|%u\n",a==b?1:0,a==c?1:0,n==e?1:0);a="beta";Text("assign",a);
    Map round;std::vector<unsigned char> input(bytes);round.Deserialize(&input[0],input.size());TypeBytes(round,"round");
    for(uint i=0;i<round.Size();++i)Text("round_get",round.Get(i));
    Map to;to.Add("beta");to.Add("alpha");to.Add(NULL);to.Add("");to.Add("ALPHA");
    CvWorldBuilderMapTypeDesc::LookupTable lookup;
    std::printf("DIFFERENCES|%u\n",CvWorldBuilderMapTypeDesc::BuildLookupTable(m,to,lookup)?1:0);
    for(size_t i=0;i<lookup.size();++i)std::printf("LOOKUP|%u|%u\n",static_cast<unsigned>(i),lookup[i]);
    m.Clear();TypeBytes(m,"clear");Text("palette_survives",b);
    CvWorldBuilderMapTypeDesc descriptor;CHECK(descriptor.m_kTerrainTypes.Size()==0);CHECK(descriptor.m_kUnits.Size()==0);
}
static void Palette() {
    const char* values[]={"UPPER","upper","Upper","\xc3\x89","\xc3\xa9","I","i","empty",NULL,""};
    for(unsigned i=0;i<sizeof(values)/sizeof(values[0]);++i){CvWorldBuilderMapTypeDesc::String s(values[i]);Text("palette",s);}
    CvWorldBuilderMapTypeDesc::TypeMap m;m.Add(NULL);uint out=77;
    std::printf("FIND_NULL|%u|",m.FindType(NULL,out)?1:0);std::printf("%u\n",out);
    m.FindType("FIND_FIRST",out);m.Add("find_first");Text("find_palette_effect",m.Get(1));
    CHECK(true);
}
static unsigned Hash(unsigned value,const std::vector<unsigned char>& bytes) {
    for(size_t i=0;i<bytes.size();++i)value=(value^bytes[i])*16777619u;return value;
}
static void Corpus() {
    CvWorldBuilderMapTypeGroup g;CvWorldBuilderMapTypeDesc::TypeMap m;unsigned state=0x71b183u,hash=2166136261u;
    for(unsigned step=0;step<2048;++step){state=state*1664525u+1013904223u;char name[48];
        ::sprintf_s(name,sizeof(name),"%s_%u",state&1?"TYPE":"type",(state>>8)%73);
        if(state%3==0)g.Remove(name);else g.Add(name);
        CHECK(m.Add(step%11==0?NULL:step%17==0?"":name)==step);
        std::vector<unsigned char> gb(g.GetSerializedSize()+1),tb(m.GetSerializedSize()+1);g.Serialize(&gb[0]);m.Serialize(&tb[0]);
        gb.resize(g.GetSerializedSize());tb.resize(m.GetSerializedSize());hash=Hash(Hash(hash,gb),tb);
        if(step%127==0){CvWorldBuilderMapTypeGroup gc(g);CHECK(gc.GetSerializedSize()==g.GetSerializedSize());
            CvWorldBuilderMapTypeDesc::TypeMap mc;mc.Deserialize(&tb[0],tb.size());CHECK(mc.Size()==m.Size());}
    }
    std::printf("CORPUS|2048|%08x\n",hash);
}
static void Wire(const char* mode,const char* path) {
    CvWorldBuilderMapTypeGroup g;CvWorldBuilderMapTypeDesc::TypeMap m;
    if(std::strcmp(mode,"write")==0){
        const char* names[]={"TERRAIN_GRASS","terrain_grass","\xed\x95\x9c\xea\xb8\x80","",NULL,"RESOURCE_IRON"};
        for(unsigned i=0;i<sizeof(names)/sizeof(names[0]);++i){if(names[i])g.Add(names[i]);m.Add(names[i]);}
        std::vector<unsigned char> gb(g.GetSerializedSize()),tb(m.GetSerializedSize());g.Serialize(&gb[0]);m.Serialize(&tb[0]);
        FILE* f=NULL;CHECK(::fopen_s(&f,path,"wb")==0 && f);uint sizes[2]={static_cast<uint>(gb.size()),static_cast<uint>(tb.size())};
        CHECK(std::fwrite(sizes,4,2,f)==2);CHECK(std::fwrite(&gb[0],1,gb.size(),f)==gb.size());CHECK(std::fwrite(&tb[0],1,tb.size(),f)==tb.size());CHECK(std::fclose(f)==0);
        std::printf("WIRE_WRITTEN|%u|%u\n",sizes[0],sizes[1]);
    }else{
        FILE* f=NULL;CHECK(::fopen_s(&f,path,"rb")==0 && f);uint sizes[2];CHECK(std::fread(sizes,4,2,f)==2);CHECK(sizes[0]<8388608 && sizes[1]<8388608);
        std::vector<unsigned char> gb(sizes[0]+1),tb(sizes[1]+1);CHECK(std::fread(&gb[0],1,sizes[0],f)==sizes[0]);CHECK(std::fread(&tb[0],1,sizes[1],f)==sizes[1]);
        CHECK(std::fgetc(f)==EOF);CHECK(std::fclose(f)==0);g.Deserialize(&gb[0],sizes[0]);m.Deserialize(&tb[0],sizes[1]);GroupBytes(g,"wire_groups");TypeBytes(m,"wire_types");
        for(uint i=0;i<m.Size();++i)Text("wire_type",m.Get(i));
    }
}
#ifndef WORLD_BUILDER_TYPES_ONLY
static void Metadata(const ModType& t) {
    std::printf("FIELDS|%u\n",t.GetFieldCount());
    for(uint i=0;i<t.GetFieldCount();++i){Text("name",t.GetFieldName(i));std::printf("TYPE|%d\n",static_cast<int>(t.GetFieldType(i)));
        switch(t.GetFieldType(i)){
        case ModType::TYPE_BOOL:std::printf("DEFAULT_B|%u\n",t.GetFieldDefaultAsBool(i)?1:0);break;
        case ModType::TYPE_FLOAT:{float f=t.GetFieldDefaultAsFloat(i);Bytes("default_f",&f,sizeof(f));break;}
        case ModType::TYPE_STRING:Text("default_s",t.GetFieldDefaultAsString(i));break;
        case ModType::TYPE_ENUM:{std::printf("DEFAULT_E|%d\n",t.GetFieldDefaultAsInt(i));const ModEnum* e=t.GetFieldEnumType(i);CHECK(e!=NULL);
            std::printf("MEMBERS|%u\n",e->GetMemberCount());for(uint j=0;j<e->GetMemberCount()+1;++j)Text("member",e->GetMember(j));break;}
        default:CHECK(false);
        }
    }
}
static void Entry(const ModType& t,const ModDataEntry& entry) {
    for(uint i=0;i<t.GetFieldCount();++i){std::printf("IS_DEFAULT|%u|%u\n",i,entry.IsFieldDefaultValue(i)?1:0);
        switch(t.GetFieldType(i)){
        case ModType::TYPE_BOOL:std::printf("B|%u\n",entry.GetFieldAsBool(i)?1:0);break;
        case ModType::TYPE_FLOAT:{float f=entry.GetFieldAsFloat(i);Bytes("f",&f,sizeof(f));break;}
        case ModType::TYPE_STRING:Text("s",entry.GetFieldAsString(i));break;
        case ModType::TYPE_ENUM:std::printf("E|%d\n",entry.GetFieldAsInt(i));break;
        default:CHECK(false);
        }
    }
}
static void AddFields(ModType& t) {
    t.AddField("flag",true);t.AddField("number",1.25f);t.AddField("text","default");
    ModEnum& e=t.AddEnumField("choice",1);e.AddMember("one");e.AddMember("two");e.AddMember("one");e.AddMember("");
}
static std::vector<unsigned char> ModBytes(const CvWorldBuilderMapModData& m,const char* label) {
    std::vector<unsigned char> bytes(m.GetSerializedSize()+16,0xcc);m.Serialize(&bytes[0]);
    for(size_t i=m.GetSerializedSize();i<bytes.size();++i)CHECK(bytes[i]==0xcc);
    bytes.resize(m.GetSerializedSize());Bytes(label,bytes.empty()?NULL:&bytes[0],bytes.size());return bytes;
}
static void Mods() {
    CvWorldBuilderMapModData m;ModBytes(m,"empty");AddFields(m.m_kMapModData);AddFields(m.m_kPlotModData);
    m.InitDataEntries(3);
    // InitDataEntries only allocates storage in the original archive. Initialize
    // every field through the public contract before observing any value.
    for(uint f=0;f<4;++f){m.GetMapDataEntry().SetFieldToDefault(f);for(uint p=0;p<3;++p)m.GetPlotDataEntry(p).SetFieldToDefault(f);}
    Metadata(m.m_kMapModData);Metadata(m.m_kPlotModData);ModBytes(m,"defaults");
    Entry(m.m_kMapModData,m.GetMapDataEntry());Entry(m.m_kPlotModData,m.GetPlotDataEntry(2));
    ModDataEntry global=m.GetMapDataEntry();global.SetField(0,false);global.SetField(1,-7.5f);global.SetField(2,"changed");global.SetField(3,-2);
    ModDataEntry plot=m.GetPlotDataEntry(1);plot.SetField(2,"\xed\x95\x9c\xea\xb8\x80");plot.SetField(3,2);
    Entry(m.m_kMapModData,global);Entry(m.m_kPlotModData,plot);
    const std::vector<unsigned char> bytes=ModBytes(m,"changed");
    CvWorldBuilderMapModData copy;copy.Deserialize(&bytes[0]);Metadata(copy.m_kMapModData);Metadata(copy.m_kPlotModData);
    Entry(copy.m_kMapModData,copy.GetMapDataEntry());for(uint i=0;i<3;++i)Entry(copy.m_kPlotModData,copy.GetPlotDataEntry(i));ModBytes(copy,"round");
    for(uint i=0;i<4;++i)global.SetFieldToDefault(i);Entry(m.m_kMapModData,global);ModBytes(m,"reset_values");
    m.InitDataEntries(2);Entry(m.m_kMapModData,m.GetMapDataEntry());Entry(m.m_kPlotModData,m.GetPlotDataEntry(1));ModBytes(m,"reinit");
    m.ResetTypes();Metadata(m.m_kMapModData);Metadata(m.m_kPlotModData);ModBytes(m,"reset_types");
}
#endif
int main(int argc,char** argv){SetErrorMode(SEM_FAILCRITICALERRORS|SEM_NOGPFAULTERRORBOX);setvbuf(stdout,NULL,_IONBF,0);
    if(argc==3 && (std::strcmp(argv[1],"write")==0 || std::strcmp(argv[1],"read")==0)){Wire(argv[1],argv[2]);std::printf("PASS|%u\n",checks);return 0;}
    if(argc!=2)return 3;
    if(std::strcmp(argv[1],"groups")==0)Groups();else if(std::strcmp(argv[1],"types")==0)Types();
#ifndef WORLD_BUILDER_TYPES_ONLY
    else if(std::strcmp(argv[1],"mods")==0)Mods();
#endif
    else if(std::strcmp(argv[1],"self")==0)GroupSelf();else if(std::strcmp(argv[1],"palette")==0)Palette();
    else if(std::strcmp(argv[1],"corpus")==0)Corpus();
    else if(std::strncmp(argv[1],"length_",7)==0)GroupLength(static_cast<uint>(std::strtoul(argv[1]+7,NULL,10)));else return 3;
    std::printf("PASS|%u\n",checks);return 0;
}
