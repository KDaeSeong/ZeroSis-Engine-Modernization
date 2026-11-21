#define main preserved_world_builder_trace_main
#include "sdk_world_builder_trace.cpp"
#undef main
static void MultiFields(CvWorldBuilderMapModData& m) {
    m.m_kMapModData.AddField("dup",true);m.m_kMapModData.AddField("dup",false);m.m_kMapModData.AddField("",-0.0f);
    m.m_kMapModData.AddField("empty_text","");m.m_kMapModData.AddField("same_text","");
    for(unsigned e=0;e<12;++e){char name[24];::sprintf_s(name,sizeof(name),"enum_%u",e);ModEnum& type=m.m_kMapModData.AddEnumField(name,static_cast<int>(e%3));
        for(unsigned v=0;v<12;++v){char value[24];::sprintf_s(value,sizeof(value),"value_%u_%u",e,v);type.AddMember(value);}}
    m.m_kPlotModData.AddField("plot",true);m.InitDataEntries(2);
    for(uint f=0;f<m.m_kMapModData.GetFieldCount();++f)m.GetMapDataEntry().SetFieldToDefault(f);
    for(uint p=0;p<2;++p)m.GetPlotDataEntry(p).SetFieldToDefault(0);
}
static void Dense() {
    CvWorldBuilderMapModData m;MultiFields(m);Metadata(m.m_kMapModData);Entry(m.m_kMapModData,m.GetMapDataEntry());
    const std::vector<unsigned char> bytes=ModBytes(m,"dense");CvWorldBuilderMapModData copy;copy.Deserialize(&bytes[0]);
    Metadata(copy.m_kMapModData);Entry(copy.m_kMapModData,copy.GetMapDataEntry());CHECK(bytes==ModBytes(copy,"dense_round"));
    copy.m_kMapModData.AddField("after_read",3.5f);Metadata(copy.m_kMapModData);ModBytes(copy,"added_after_read");
}
static void Defaults() {
    CvWorldBuilderMapModData m;AddFields(m.m_kMapModData);m.InitDataEntries(0);ModDataEntry e=m.GetMapDataEntry();
    for(uint i=0;i<4;++i)e.SetFieldToDefault(i);
    const float numbers[]={0.0f,-0.0f,1.25f,-1.25f};
    for(unsigned i=0;i<4;++i){e.SetField(1,numbers[i]);Entry(m.m_kMapModData,e);}
    e.SetField(2,"default");Entry(m.m_kMapModData,e);e.SetField(2,"default");ModBytes(m,"same_string_twice");
    e.SetField(2,"");Entry(m.m_kMapModData,e);ModBytes(m,"empty_string");
    const int ints[]={0,-1,1,2,INT_MIN,INT_MAX};for(unsigned i=0;i<6;++i){e.SetField(3,ints[i]);Entry(m.m_kMapModData,e);}
    m.m_kMapModData.AddField("after_init",false);std::printf("ADDED_FIELD_COUNT|%u\n",m.m_kMapModData.GetFieldCount());
}
static void Bounds() {
    CvWorldBuilderMapModData m;AddFields(m.m_kMapModData);m.InitDataEntries(0);
    const uint indexes[]={4,100,UINT_MAX};
    for(unsigned i=0;i<3;++i){uint f=indexes[i];Text("bad_name",m.m_kMapModData.GetFieldName(f));std::printf("BAD_TYPE|%d\n",m.m_kMapModData.GetFieldType(f));
        std::printf("BAD_ENUM|%u\n",m.m_kMapModData.GetFieldEnumType(f)?1:0);
        std::printf("BAD_DEFAULT|%u|%d|%g\n",m.m_kMapModData.GetFieldDefaultAsBool(f)?1:0,m.m_kMapModData.GetFieldDefaultAsInt(f),m.m_kMapModData.GetFieldDefaultAsFloat(f));
        Text("bad_default_s",m.m_kMapModData.GetFieldDefaultAsString(f));}
    for(uint i=0;i<3;++i)std::printf("NON_ENUM|%u\n",m.m_kMapModData.GetFieldEnumType(i)?1:0);
    CHECK(true);
}
static void Fresh() {
    CvWorldBuilderMapModData m;m.m_kPlotModData.AddField("number",17.0f);m.InitDataEntries(1);m.GetPlotDataEntry(0).SetField(0,99.0f);
    m.InitDataEntries(0);m.InitDataEntries(1);std::printf("FRESH_RECREATED|%.1f\n",m.GetPlotDataEntry(0).GetFieldAsFloat(0));CHECK(true);
}
static void ModWire(const char* mode,const char* path) {
    CvWorldBuilderMapModData m;
    if(std::strcmp(mode,"write")==0){MultiFields(m);const std::vector<unsigned char> bytes=ModBytes(m,"written");
        FILE* f=NULL;CHECK(::fopen_s(&f,path,"wb")==0 && f);CHECK(std::fwrite(&bytes[0],1,bytes.size(),f)==bytes.size());CHECK(std::fclose(f)==0);
    }else{FILE* f=NULL;CHECK(::fopen_s(&f,path,"rb")==0 && f);CHECK(std::fseek(f,0,SEEK_END)==0);long size=std::ftell(f);CHECK(size>0 && size<8388608);
        CHECK(std::fseek(f,0,SEEK_SET)==0);std::vector<unsigned char> bytes(static_cast<size_t>(size));CHECK(std::fread(&bytes[0],1,bytes.size(),f)==bytes.size());CHECK(std::fclose(f)==0);
        m.Deserialize(&bytes[0]);Metadata(m.m_kMapModData);Entry(m.m_kMapModData,m.GetMapDataEntry());CHECK(bytes==ModBytes(m,"read"));}
}
int main(int argc,char** argv){SetErrorMode(SEM_FAILCRITICALERRORS|SEM_NOGPFAULTERRORBOX);setvbuf(stdout,NULL,_IONBF,0);
    if(argc==3){ModWire(argv[1],argv[2]);std::printf("PASS|%u\n",checks);return 0;}if(argc!=2)return 3;
    if(std::strcmp(argv[1],"baseline")==0)Mods();else if(std::strcmp(argv[1],"dense")==0)Dense();else if(std::strcmp(argv[1],"defaults")==0)Defaults();else if(std::strcmp(argv[1],"bounds")==0)Bounds();else if(std::strcmp(argv[1],"fresh")==0)Fresh();else return 3;
    std::printf("PASS|%u\n",checks);return 0;
}
