#include "SdkAutoArchiveIncludes.h"
static unsigned int checks=0;
static void require(bool value) { ++checks;if(!value) { fprintf(stderr,"FAIL|%u\n",checks);throw std::runtime_error("check"); } }
static void hex(const char* name,const void* data,size_t size) {
    printf("%s|%u|",name,static_cast<unsigned int>(size));const unsigned char* p=static_cast<const unsigned char*>(data);
    for(size_t i=0;i<size;++i)printf("%02x",p[i]);printf("\n");
}
static void text(const char* name,const std::string& value) { hex(name,value.data(),value.size()); }
static void bytes(const char* name,const FMemoryStream& stream) { hex(name,stream.GetBuf(),stream.GetEOF()); }
struct Archive : FAutoArchive {
    mutable std::map<const FAutoVariableBase*,std::string> names;
    bool failNames;
    Archive():failNames(false) {}
    virtual const std::string* getVariableName(const FAutoVariableBase& value) const {
        std::map<const FAutoVariableBase*,std::string>::const_iterator it=names.find(&value);return it==names.end()?NULL:&it->second;
    }
    virtual void setVariableName(const FAutoVariableBase& value,const std::string& name) const { if(failNames)throw std::runtime_error("name fault");names[&value]=name; }
    virtual std::string debugDump(const FAutoVariableBase&) const { return "ARCHIVE_DETAIL"; }
    virtual std::string stackTraceRemark(const FAutoVariableBase&) const { return "ARCHIVE_REMARK"; }
    size_t count() const { return m_contents.size(); }
};
struct Variable : FAutoVariableBase {
    Archive& owner;int value;unsigned int loaded,deltaLoaded,saved,deltaSaved,cleared,resetCount;bool attached,failSave,failClear;
    Variable(const char* name,Archive& archive,int initial,bool tracking=false)
        : FAutoVariableBase(name,archive,tracking),owner(archive),value(initial),loaded(0),deltaLoaded(0),saved(0),deltaSaved(0),cleared(0),resetCount(0),attached(true),failSave(false),failClear(false) {}
    ~Variable() { if(attached)owner.remove(*this); }
    void detach() { owner.remove(*this);attached=false; }
    void set(int next) { if(next!=value) { owner.touch(*this);value=next; } }
    virtual void load(FDataStream& s) { ++loaded;s>>value; }
    virtual void loadDelta(FDataStream& s) { ++deltaLoaded;s>>value; }
    virtual void save(FDataStream& s) const { ++const_cast<Variable*>(this)->saved;s<<value; }
    virtual void saveDelta(FDataStream& s) const { ++const_cast<Variable*>(this)->deltaSaved;if(failSave)throw std::runtime_error("save fault");s<<value; }
    virtual void clearDelta() { ++cleared;if(failClear)throw std::runtime_error("clear fault"); }
    virtual bool compare(FDataStream& s) const { int other=0;s>>other;return other==value; }
    virtual void reset() { ++resetCount;value=0; }
    virtual const std::string& name() const { return *owner.getVariableName(*this); }
    virtual void setStackTraceRemark() {}
    virtual std::string toString() const { return FSerialization::toString(value); }
};
static void stacks(const std::vector<std::pair<std::string,std::string> >& values) {
    printf("STACKS|%u\n",static_cast<unsigned int>(values.size()));
    for(size_t i=0;i<values.size();++i) { text("STACK",values[i].first);text("REMARK",values[i].second); }
}
static void probe() {
    Archive archive;printf("EMPTY|%u|%d\n",static_cast<uint>(archive.count()),archive.hasDeltas());
    __declspec(align(16)) unsigned char storage[3][256];require(sizeof(Variable)<=256);
    Variable* a=new(storage[2])Variable("alpha",archive,11);
    Variable* b=new(storage[0])Variable("beta",archive,22);
    Variable* c=new(storage[1])Variable("gamma",archive,33,true);
    archive.remove(*c);archive.add(*c); // Exercise both real SDK entry points; keep registration order unchanged.
    printf("REGISTERED|%u|%d\n",static_cast<uint>(archive.count()),archive.hasDeltas());
    text("NAME",a->name());text("NAME",b->name());text("NAME",c->name());
    FMemoryStream full;archive.save(full);bytes("FULL",full);
    a->set(101);c->set(303);b->set(202);archive.touch(*b);
    FMemoryStream delta;std::vector<std::pair<std::string,std::string> > callStacks;
    callStacks.push_back(std::make_pair(std::string("OLD_STACK"),std::string("OLD_REMARK")));
    archive.saveDelta(delta,callStacks);bytes("DELTA",delta);stacks(callStacks);
    printf("AFTER_SAVE|%d|%u|%u|%u\n",archive.hasDeltas(),a->deltaSaved,b->deltaSaved,c->deltaSaved);
    FMemoryStream repeated;archive.saveDelta(repeated,callStacks);bytes("REPEATED",repeated);stacks(callStacks);
    delta.Rewind();std::vector<const FAutoVariableBase*> matches=archive.findMismatchedVariables(delta);
    printf("MATCH|%u|%u\n",static_cast<uint>(matches.size()),delta.GetPosition());
    b->value=-9;delta.Rewind();matches=archive.findMismatchedVariables(delta);printf("MISMATCH|%u|%u\n",static_cast<uint>(matches.size()),delta.GetPosition());
    for(size_t i=0;i<matches.size();++i)text("MISMATCH_NAME",matches[i]->name());
    printf("FIND|%d|%d\n",archive.findVariable("beta")==b,archive.findVariable("missing")==NULL);
    delta.Rewind();archive.loadDelta(delta);printf("LOAD_DELTA|%d|%d|%d|%u|%u|%u|%d\n",a->value,b->value,c->value,a->deltaLoaded,b->deltaLoaded,c->deltaLoaded,archive.hasDeltas());
    full.Rewind();archive.load(full);printf("LOAD_FULL|%d|%d|%d|%u|%u|%u|%d\n",a->value,b->value,c->value,a->loaded,b->loaded,c->loaded,archive.hasDeltas());
    text("TRACE",a->getStackTrace());text("TRACE_REMARK",a->getStackTraceRemark());text("DEBUG",a->debugDump(callStacks));
    archive.clearDelta();printf("CLEAR|%d|%u|%u|%u\n",archive.hasDeltas(),a->cleared,b->cleared,c->cleared);
    a->set(99);archive.reset();printf("RESET|%d|%d|%d|%d|%u|%u|%u|%u|%u|%u\n",a->value,b->value,c->value,archive.hasDeltas(),a->resetCount,b->resetCount,c->resetCount,a->cleared,b->cleared,c->cleared);
    c->detach();printf("REMOVE|%u|%d\n",static_cast<uint>(archive.count()),archive.hasDeltas());
    c->~Variable();b->~Variable();a->~Variable();printf("DESTROY|%u|%d\n",static_cast<uint>(archive.count()),archive.hasDeltas());
    printf("CALLSTACK_DEFAULT|%d\n",FAutoArchive::AreCallStacksEnabled());
    FAutoArchive::EnableCallStacks(true);printf("CALLSTACK_ON|%d\n",FAutoArchive::AreCallStacksEnabled());
    FAutoArchive::EnableCallStacks(false);printf("CALLSTACK_OFF|%d\n",FAutoArchive::AreCallStacksEnabled());
}
static void strings() {
    for(int i=-3;i<=15;++i) {
        int integer=i;unsigned int positive=static_cast<unsigned int>(i);bool boolean=i!=0;char character=static_cast<char>(i);
        short shortValue=static_cast<short>(i);unsigned short unsignedShortValue=static_cast<unsigned short>(i);unsigned char byteValue=static_cast<unsigned char>(i);
        float real=static_cast<float>(i)/7;double wide=static_cast<double>(i)/7;
        printf("CASE|%d\n",i);text("INT",FSerialization::toString(integer));text("UINT",FSerialization::toString(positive));
        text("BOOL",FSerialization::toString(boolean));text("CHAR",FSerialization::toString(character));text("UCHAR",FSerialization::toString(byteValue));
        text("SHORT",FSerialization::toString(shortValue));text("USHORT",FSerialization::toString(unsignedShortValue));
        text("FLOAT",FSerialization::toString(real));text("DOUBLE",FSerialization::toString(wide));
        DirectionTypes direction=static_cast<DirectionTypes>(i);ActivityTypes activity=static_cast<ActivityTypes>(i);
        text("DIRECTION",FSerialization::toString(direction));text("ACTIVITY",FSerialization::toString(activity));
    }
    std::string plain("A\0B\n",4);text("STRING",FSerialization::toString(plain));
    Archive archive;Variable value("alpha",archive,83);text("VARIABLE",FSerialization::toString(static_cast<const FAutoVariableBase&>(value)));
    std::vector<std::pair<std::string,std::string> > traces;
    traces.push_back(std::make_pair(std::string("one\ntwo"),std::string("remark1")));
    traces.push_back(std::make_pair(std::string("three"),std::string("remark2")));
    text("DEBUG_TRACES",value.debugDump(traces));
}
static void formatting() {
    for(int i=-32768;i<32768;++i) {
        const short s=static_cast<short>(i);const unsigned short u=static_cast<unsigned short>(i);
        text("SHORT",FSerialization::toString(s));text("USHORT",FSerialization::toString(u));
    }
    for(int i=-128;i<128;++i) {
        const char c=static_cast<char>(i);const unsigned char u=static_cast<unsigned char>(i);
        text("CHAR",FSerialization::toString(c));text("UCHAR",FSerialization::toString(u));
    }
    const unsigned int integers[]={0,1,0xffffffffu,0x80000000u,0x7fffffffu,0x12345678u};
    for(size_t i=0;i<sizeof(integers)/sizeof(integers[0]);++i) {
        const int s=static_cast<int>(integers[i]);text("INT",FSerialization::toString(s));text("UINT",FSerialization::toString(integers[i]));
    }
    // Keep original sprintf output within its observed 32-byte float buffers.
    const double reals[]={0.0,-0.0,0.5,-0.5,0.0000005,-0.0000005,1.2345675,1.2345685,
        0.0078125,-0.0078125,1.0078125,1.0000005,1e-20,-1e-20,1e20,-1e20,123456.1234567};
    for(size_t i=0;i<sizeof(reals)/sizeof(reals[0]);++i) {
        const float f=static_cast<float>(reals[i]);text("DOUBLE",FSerialization::toString(reals[i]));text("FLOAT",FSerialization::toString(f));
    }
    const unsigned __int64 bits[]={0x7ff0000000000000ui64,0xfff0000000000000ui64,0x7ff8000000000000ui64,0xfff8000000000000ui64};
    for(size_t i=0;i<4;++i) { double d=0;memcpy(&d,&bits[i],sizeof(d));text("SPECIAL",FSerialization::toString(d)); }
}
static std::vector<unsigned char> readFile(const std::string& path) {
    FILE* f=fopen(path.c_str(),"rb");require(f!=NULL);std::vector<unsigned char> result;unsigned char block[4096];size_t n;
    while((n=fread(block,1,sizeof(block),f))!=0)result.insert(result.end(),block,block+n);
    require(!ferror(f));require(fclose(f)==0);return result;
}
static void writeFile(const std::string& path,const FMemoryStream& stream) {
    FILE* f=fopen(path.c_str(),"wb");require(f!=NULL);
    const size_t n=fwrite(stream.GetBuf(),1,stream.GetEOF(),f);require(fclose(f)==0);require(n==stream.GetEOF());
}
static void order(FDataStream& stream,int endian) { stream.SetDesiredEndianNess(static_cast<FEndian::EEndianness>(endian)); }
static void fromFile(FMemoryStream& stream,const std::string& path,int endian) {
    const std::vector<unsigned char> data=readFile(path);require(data.size()<=INT_MAX);
    if(!data.empty())require(stream.WriteIt(static_cast<unsigned int>(data.size()),&data[0])==data.size());
    stream.Rewind();order(stream,endian);
}
struct Seven {
    Archive archive;
    union Slot { unsigned char bytes[256]; void* alignment; } storage[7];
    Variable* variables[7];
    Seven(bool reverse=false) {
        require(sizeof(Variable)<=256);const unsigned int slots[]={6,0,4,2,5,1,3};
        for(unsigned int i=0;i<7;++i) {
            char name[16];sprintf_s(name,"v%u",i);
            variables[i]=new(storage[reverse?6-slots[i]:slots[i]].bytes)Variable(name,archive,static_cast<int>(10+i*101));
        }
    }
    ~Seven() { archive.clearDelta();for(unsigned int i=7;i!=0;--i)variables[i-1]->~Variable(); }
};
static void trace(int endian,const char* input,const char* output) {
    const std::vector<unsigned char> fixture=readFile(input);require(fixture.size()%12==0);
    Seven owner;FMemoryStream result;order(result,endian);std::vector<std::pair<std::string,std::string> > callStacks;
    for(size_t offset=0;offset<fixture.size();offset+=12) {
        unsigned int op=0,index=0;int value=0;memcpy(&op,&fixture[offset],4);memcpy(&index,&fixture[offset+4],4);memcpy(&value,&fixture[offset+8],4);
        require(index<7);FMemoryStream side;order(side,endian);Archive& a=owner.archive;
        if(op==0)owner.variables[index]->set(value);
        else if(op==1)a.touch(*owner.variables[index]);
        else if(op==2) { require(&(static_cast<FDataStream&>(side)<<static_cast<const FAutoArchive&>(a))==&side); }
        else if(op==3)a.reset();
        else if(op==4)a.saveDelta(side,callStacks);
        else if(op==5) {
            FMemoryStream delta;order(delta,endian);delta<<2u<<index<<value<<((index+1)%7)<<(value^0x1234);
            delta.Rewind();a.loadDelta(delta);require(delta.AtEnd());
        }
        else if(op==6) {
            FMemoryStream remote;order(remote,endian);remote<<7u;
            for(unsigned int j=7;j!=0;--j)remote<<(j-1)<<(owner.variables[j-1]->value^(index==j-1?1:0));
            remote.Rewind();const std::vector<const FAutoVariableBase*> mismatches=a.findMismatchedVariables(remote);
            require(mismatches.size()==1&&mismatches[0]==owner.variables[index]&&remote.AtEnd());side<<1u<<index;
        }
        else if(op==7)a.clearDelta();
        else if(op==8) {
            FMemoryStream full;order(full,endian);for(unsigned int j=0;j<7;++j)full<<(value^static_cast<int>(j*17));
            full.Rewind();require(&(static_cast<FDataStream&>(full)>>static_cast<FAutoArchive&>(a))==&full);require(full.AtEnd());
        }
        else require(false);
        result<<op<<static_cast<unsigned int>(a.hasDeltas())<<side.GetEOF();
        if(side.GetEOF())require(result.WriteIt(side.GetEOF(),side.GetBuf())==side.GetEOF());
        a.save(result);
        for(unsigned int j=0;j<7;++j)result<<owner.variables[j]->cleared;
        for(unsigned int j=0;j<7;++j)result<<owner.variables[j]->resetCount;
    }
    writeFile(output,result);printf("TRACE|%u|%u\n",static_cast<unsigned int>(fixture.size()/12),result.GetEOF());
}
static void exchange(int endian,const char* directory,bool writing) {
    const std::string prefix=std::string(directory)+"/";Seven owner(!writing);FMemoryStream full,delta;order(full,endian);order(delta,endian);
    if(writing) {
        owner.archive.save(full);for(unsigned int i=1;i<7;i+=2)owner.variables[i]->set(-static_cast<int>(i*99));
        std::vector<std::pair<std::string,std::string> > callStacks;owner.archive.saveDelta(delta,callStacks);
        writeFile(prefix+"full.bin",full);writeFile(prefix+"delta.bin",delta);
    } else {
        fromFile(full,prefix+"full.bin",endian);fromFile(delta,prefix+"delta.bin",endian);
        for(unsigned int i=0;i<7;++i)owner.variables[i]->value=-1111;
        owner.archive.load(full);require(full.AtEnd());
        for(unsigned int i=0;i<7;++i)require(owner.variables[i]->value==static_cast<int>(10+i*101));
        owner.archive.loadDelta(delta);require(delta.AtEnd());
        for(unsigned int i=0;i<7;++i)require(owner.variables[i]->value==(i%2?-static_cast<int>(i*99):static_cast<int>(10+i*101)));
        delta.Rewind();require(owner.archive.findMismatchedVariables(delta).empty());require(delta.AtEnd());
    }
    printf("EXCHANGE|%d|%d\n",endian,writing);
}
// The archive stores this reference; it never calls TemplateOwner methods during construction.
#pragma warning(push)
#pragma warning(disable:4355)
struct TemplateOwner {
    FAutoArchiveClassContainer<TemplateOwner> archive;
    FAutoVariable<int,TemplateOwner> number;
    FAutoVariable<std::string,TemplateOwner> word;
    FAutoVariable<std::vector<int>,TemplateOwner> vector;
    FAutoVariable<DirectionTypes,TemplateOwner> direction;
    FAutoVariable<bool,TemplateOwner> flag;
    TemplateOwner():archive(*this),number("number",archive,7),word("word",archive,std::string("A\0B",3)),
        vector("vector",archive,static_cast<size_t>(3),false),direction("direction",archive,DIRECTION_EAST),flag("flag",archive,true,false) {}
    std::string debugDump(const FAutoVariableBase&) const { return "OWNER_DETAIL"; }
    std::string stackTraceRemark(const FAutoVariableBase&) const { return "OWNER_REMARK"; }
    void mutate() {
        number=42;word=std::string("x\0y\n",4);vector.push_back(-7);vector.setAt(1,5);vector.erase(0);
        vector.insert(2,9);vector.resize(6);vector.resize(7,-2);direction=DIRECTION_SOUTHWEST;flag=false;
    }
};
#pragma warning(pop)
static void templates(int endian,const char* directory,bool writing) {
    const std::string prefix=std::string(directory)+"/";TemplateOwner owner;FMemoryStream full,delta;order(full,endian);order(delta,endian);
    require(owner.vector.size()==3&&!owner.archive.hasDeltas());require(owner.number.name()=="number"&&owner.vector.name()=="vector");
    owner.number.set(7);require(!owner.archive.hasDeltas());owner.number.dirtyGet()=7;require(owner.archive.hasDeltas());owner.archive.clearDelta();
    owner.vector.dirtyGet()[0]=0;require(!owner.archive.hasDeltas());
    if(writing) {
        full<<owner.archive;owner.mutate();std::vector<std::pair<std::string,std::string> > callStacks;owner.archive.saveDelta(delta,callStacks);
        require(!owner.archive.hasDeltas());writeFile(prefix+"templates_full.bin",full);writeFile(prefix+"templates_delta.bin",delta);
    } else {
        fromFile(full,prefix+"templates_full.bin",endian);full>>owner.archive;require(full.AtEnd());
        // The actual vector header's full load calls clear(), which touches its archive.
        require(owner.archive.hasDeltas());owner.archive.clearDelta();
        fromFile(delta,prefix+"templates_delta.bin",endian);owner.archive.loadDelta(delta);require(delta.AtEnd());
        require(owner.number.get()==42&&owner.word.get()==std::string("x\0y\n",4)&&owner.direction.get()==DIRECTION_SOUTHWEST&&!owner.flag.get());
        const int expected[]={5,0,9,-7,0,0,-2};require(owner.vector.size()==7);
        for(unsigned int i=0;i<7;++i)require(owner.vector[i]==expected[i]);
        delta.Rewind();require(owner.archive.findMismatchedVariables(delta).empty());require(delta.AtEnd());
    }
    std::vector<std::pair<std::string,std::string> > traces;text("TEMPLATE_DEBUG",owner.number.debugDump(traces));
    text("TEMPLATE_VECTOR",owner.vector.toString());owner.archive.clearDelta();owner.archive.reset();
    require(owner.number.get()==0&&owner.word.get().empty()&&owner.vector.size()==0&&!owner.flag.get());
    printf("TEMPLATES|%d|%d\n",endian,writing);
}
#ifdef AUTO_ARCHIVE_CANDIDATE
struct FaultStream: FMemoryStream {
    unsigned int remaining;bool throws;
    FaultStream(unsigned int limit,bool throwing):remaining(limit),throws(throwing) {}
    virtual unsigned int WriteIt(unsigned int count,const void* data) {
        if(count>remaining) {
            if(throws)throw std::runtime_error("stream fault");
            const unsigned int written=remaining;remaining=0;return written?FMemoryStream::WriteIt(written,data):0;
        }
        remaining-=count;return FMemoryStream::WriteIt(count,data);
    }
};
static void hardening() {
    unsigned int rejects=0,retries=0;std::vector<std::pair<std::string,std::string> > stacks;
    {
        Archive a;Variable v("v",a,1);a.touch(v);v.detach();a.remove(v);require(a.count()==0&&!a.hasDeltas());
        FMemoryStream empty;a.saveDelta(empty,stacks);empty.Rewind();unsigned int n=99;empty>>n;require(n==0&&empty.AtEnd());
    }
    {
        Archive a;Variable v("v",a,1);try { a.add(v);require(false); }catch(const std::invalid_argument&) { ++rejects; }
        require(a.count()==1);a.failNames=true;
        bool rejected=false;try { Variable fail("fail",a,2); }catch(const std::runtime_error&) { rejected=true;++rejects; }
        require(rejected&&a.count()==1&&!a.hasDeltas());
    }
    {
        Archive a,b;Variable v("foreign",b,3);a.touch(v);FMemoryStream s;
        try { a.saveDelta(s,stacks);require(false); }catch(const std::invalid_argument&) { ++rejects; }
        require(s.GetEOF()==0&&a.hasDeltas());
        try { a.clearDelta();require(false); }catch(const std::invalid_argument&) { ++rejects; }
        a.remove(v);require(!a.hasDeltas()&&b.count()==1);
    }
    for(unsigned int throwing=0;throwing<2;++throwing)for(unsigned int failAt=0;failAt<60;++failAt) {
        Seven owner;for(unsigned int i=0;i<7;++i)owner.archive.touch(*owner.variables[i]);
        FaultStream broken(failAt,throwing!=0);
        bool rejected=false;try { owner.archive.saveDelta(broken,stacks); }catch(const std::runtime_error&) { rejected=true;++rejects; }
        require(rejected&&owner.archive.hasDeltas());FMemoryStream retry;owner.archive.saveDelta(retry,stacks);
        require(retry.GetEOF()==60&&!owner.archive.hasDeltas());retry.Rewind();require(owner.archive.findMismatchedVariables(retry).empty());++retries;
    }
    {
        Seven owner;owner.archive.touch(*owner.variables[2]);owner.variables[2]->failSave=true;FMemoryStream failed;
        bool rejected=false;try { owner.archive.saveDelta(failed,stacks); }catch(const std::runtime_error&) { rejected=true;++rejects; }
        require(rejected&&owner.archive.hasDeltas());owner.variables[2]->failSave=false;owner.variables[2]->failClear=true;rejected=false;
        try { owner.archive.clearDelta(); }catch(const std::runtime_error&) { rejected=true;++rejects; }
        require(rejected&&owner.archive.hasDeltas());owner.variables[2]->failClear=false;owner.archive.clearDelta();require(!owner.archive.hasDeltas());
    }
    for(int endian=0;endian<3;++endian)for(unsigned int compare=0;compare<2;++compare)for(unsigned int bad=0;bad<5;++bad) {
        Seven owner;FMemoryStream data;order(data,endian);
        if(bad==0) { data<<0xffffffffu; }
        else if(bad==1) { data<<1u<<7u<<123; }
        else if(bad==2) { data<<1u<<0xffffffffu<<123; }
        else if(bad==3) { data<<1u<<0u; }
        else { data<<2u<<0u<<777<<7u<<888; }
        data.Rewind();bool rejected=false;
        try { if(compare)owner.archive.findMismatchedVariables(data);else owner.archive.loadDelta(data); }
        catch(const std::exception&) { rejected=true;++rejects; }
        require(rejected);require(owner.variables[0]->value==(!compare&&bad==4?777:10));
        for(unsigned int i=1;i<7;++i)require(owner.variables[i]->value==static_cast<int>(10+i*101));
    }
    // Repeated valid indices are legal in the SDK input grammar (last load wins).
    {
        Archive a;Variable v("v",a,0);FMemoryStream data;data<<2u<<0u<<11<<0u<<22;data.Rewind();a.loadDelta(data);require(v.value==22&&data.AtEnd());
        data.Rewind();const std::vector<const FAutoVariableBase*> result=a.findMismatchedVariables(data);require(result.size()==1&&result[0]==&v);
    }
    const double extremes[]={std::numeric_limits<double>::max(),-std::numeric_limits<double>::max(),std::numeric_limits<double>::min(),
        std::numeric_limits<double>::denorm_min(),static_cast<double>(std::numeric_limits<float>::max())};
    for(size_t i=0;i<sizeof(extremes)/sizeof(extremes[0]);++i)text("EXTREME",FSerialization::toString(extremes[i]));
    printf("HARDENING|%u|%u\n",rejects,retries);
}
#endif
int main(int argc,char** argv) {
    SetErrorMode(SEM_FAILCRITICALERRORS|SEM_NOGPFAULTERRORBOX);setvbuf(stdout,NULL,_IONBF,0);
    try {
        require(argc>=2);
        if(argc==5) {
            const int endian=atoi(argv[2]);require(endian>=0&&endian<3);
            if(!strcmp(argv[1],"trace"))trace(endian,argv[3],argv[4]);
            else if(!strcmp(argv[1],"exchange"))exchange(endian,argv[3],!strcmp(argv[4],"write"));
            else if(!strcmp(argv[1],"templates"))templates(endian,argv[3],!strcmp(argv[4],"write"));
            else require(false);
        } else {
            require(argc==2);if(!strcmp(argv[1],"probe"))probe();else if(!strcmp(argv[1],"strings"))strings();else if(!strcmp(argv[1],"formatting"))formatting();
#ifdef AUTO_ARCHIVE_CANDIDATE
            else if(!strcmp(argv[1],"hardening"))hardening();
#endif
            else require(false);
        }
        printf("PASS|%u\n",checks);return 0;
    }
    catch(const std::exception& e) { fprintf(stderr,"EXCEPTION|%s\n",e.what());return 1; }
}
