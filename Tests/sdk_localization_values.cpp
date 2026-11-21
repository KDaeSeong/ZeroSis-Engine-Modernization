#include "SdkLocalizationIncludes.h"
#include <limits>
static unsigned checks = 0;
#define CHECK(x) do { ++checks; if (!(x)) { std::fprintf(stderr,"FAIL|%u|%d|%s\n",checks,__LINE__,#x);std::exit(2); } } while(0)
static void Hex(const char* data,size_t length) {
    if(!data) { std::printf("NULL");return; }
    for(size_t i=0;i<length;++i)std::printf("%02x",static_cast<unsigned char>(data[i]));
}
static void Show(const char* label,const Localization::SharedString& value) {
    size_t length=999;const char* p=value.GetString(length);
    std::printf("STRING|%s|offset=%u|length=%u|buffer=%u|n=%u|",label,static_cast<unsigned>(value.GetOffset()),static_cast<unsigned>(value.GetLength()),static_cast<unsigned>(value.GetBufferLength()),static_cast<unsigned>(length));
    Hex(p,length);std::printf("\n");p=value.GetBuffer(length);std::printf("BUFFER|%s|n=%u|",label,static_cast<unsigned>(length));Hex(p,length);std::printf("\n");
}
static void Shared() {
    Localization::SharedString empty,zero("",0),nullZero(NULL,0),source("a\0bcd",5),copy(source),assigned;
    Show("default",empty);Show("zero",zero);Show("null_zero",nullZero);Show("source",source);Show("copy",copy);
    const size_t positions[]={0,1,4,5,5,6,6,7,1,0};const size_t lengths[]={5,3,1,0,1,0,1,0,9,0};
    for(unsigned i=0;i<10;++i) { std::printf("SLICE|%u|%d\n",i,copy.SetOffsetAndLength(positions[i],lengths[i]));Show("slice",copy); }
    assigned=source;Show("assigned",assigned);assigned=assigned;Show("self",assigned);assigned=empty;Show("assigned_empty",assigned);
    copy=source;CHECK(copy.SetOffsetAndLength(1,3));source=empty;Show("retained",copy);
    std::printf("EMPTY_SLICE|%d|%d\n",empty.SetOffsetAndLength(0,0),empty.SetOffsetAndLength(1,0));
}
#ifdef ZEROSIS_LOCALIZATION_VALUES_HARDENING
static void PrintParameter(const char* label,const Localization::StringParameter& parameter) {
    std::printf("PARAM|%s|%d|%u|%u|%u|%u|%u|%u|children=%u\n",label,parameter.ArgumentIndex,
        static_cast<unsigned>(parameter.uiTextKeyStart),static_cast<unsigned>(parameter.lenTextKey),
        static_cast<unsigned>(parameter.uiParameterStart),static_cast<unsigned>(parameter.uiParameterEnd),
        static_cast<unsigned>(parameter.uiTransformTagStart),static_cast<unsigned>(parameter.uiTransformTagEnd),static_cast<unsigned>(parameter.m_injected_parameters.size()));
}
static void Parameters() {
    Localization::StringParameter parameter;PrintParameter("default",parameter);
    parameter.ArgumentIndex=3;parameter.uiTextKeyStart=11;parameter.lenTextKey=12;parameter.uiParameterStart=13;
    parameter.uiParameterEnd=14;parameter.uiTransformTagStart=15;parameter.uiTransformTagEnd=16;
    Localization::StringParameter child;child.ArgumentIndex=9;parameter.m_injected_parameters.push_back(child);
    Localization::StringParameter copy(parameter);parameter.m_injected_parameters[0].ArgumentIndex=99;parameter.ArgumentIndex=88;
    PrintParameter("copy",copy);PrintParameter("retained_child",copy.m_injected_parameters[0]);
    CHECK(copy.ArgumentIndex==3 && copy.m_injected_parameters[0].ArgumentIndex==9);
}
#include <thread>
#include <atomic>
static void Boundaries() {
    Localization::SharedString value("abc",3);const size_t maximum=(std::numeric_limits<size_t>::max)();
    CHECK(!value.SetOffsetAndLength(maximum,1));CHECK(!value.SetOffsetAndLength(1,maximum));CHECK(value.GetOffset()==0 && value.GetLength()==3);
    bool invalid=false;try { Localization::SharedString rejected(NULL,1); }catch(const std::invalid_argument&) { invalid=true; }CHECK(invalid);
    bool oversized=false;try { Localization::SharedString rejected("x",maximum); }catch(const std::length_error&) { oversized=true; }CHECK(oversized);
    std::atomic<unsigned> errors(0),completed(0);std::vector<std::thread> threads;
    for(unsigned t=0;t<4;++t)threads.emplace_back([&]() {
        for(unsigned i=0;i<1024;++i) {
            Localization::SharedString own(value);if(!own.SetOffsetAndLength(1,2))++errors;
            size_t length=0;const char* data=own.GetString(length);if(length!=2 || std::memcmp(data,"bc",2))++errors;
            ++completed;
        }
    });
    for(auto& thread:threads)thread.join();CHECK(errors==0);CHECK(completed==4096);CHECK(value.GetOffset()==0 && value.GetLength()==3);
    std::printf("BOUNDARIES|PASS|independent_copies=%u\n",completed.load());
}
#endif
int main(int argc,char** argv) {
    SetErrorMode(SEM_FAILCRITICALERRORS|SEM_NOGPFAULTERRORBOX);std::setvbuf(stdout,NULL,_IONBF,0);
    if(argc!=2)return 1;
    if(!std::strcmp(argv[1],"shared"))Shared();
#ifdef ZEROSIS_LOCALIZATION_VALUES_HARDENING
    else if(!std::strcmp(argv[1],"parameters"))Parameters();
    else if(!std::strcmp(argv[1],"boundaries"))Boundaries();
#endif
    else return 1;
    std::printf("PASS|%u\n",checks);return 0;
}
