#define main localization_trace_main
#include "../../../Tests/sdk_localization_trace.cpp"
#undef main
#include <limits>

int main() {
    SetErrorMode(SEM_FAILCRITICALERRORS|SEM_NOGPFAULTERRORBOX);
    std::setvbuf(stdout,NULL,_IONBF,0);
    Database::Connection db;
    Setup(db);
    Localization::SetLogger(new Logger);
    const bool ready=Localization::Initialize(L"icudt44l.dat",db,"Languages","en_US",false);
    if(!ready)return 10;
    struct Sample { const char* name; double value; } samples[]={
        {"zero",0.0}, {"positive",1.234}, {"negative",-1.234},
        {"nan",std::numeric_limits<double>::quiet_NaN()},
        {"positive_infinity",std::numeric_limits<double>::infinity()},
        {"negative_infinity",-std::numeric_limits<double>::infinity()}
    };
    for(const auto& sample:samples){
        Localization::String formatted("{1:number #.##}");
        if(!formatted.PushArgument(static_cast<double>(sample.value)))return 11;
        size_t bytes=0;const char* output=formatted.toUTF8(bytes,1);
        std::printf("RESULT|%s|bytes=%zu|",sample.name,bytes);Hex(output,bytes);std::printf("\n");
        if(!output || !bytes)return 12;
    }
    if(!Localization::Shutdown())return 13;
    std::puts("PASS|6");
    return 0;
}
