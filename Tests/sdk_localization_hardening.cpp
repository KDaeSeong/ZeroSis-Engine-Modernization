#define main sealed_localization_reference_entry_point
#include "sdk_localization_trace.cpp"
#undef main
#include <atomic>
#include <thread>
#include <limits>

struct QuietLogger:Localization::ILocalizationLogger {
    unsigned errors=0;
    void Log(const char*,LogTypes type) override {if(type==TYPE_ERROR)++errors;}
};
static std::string Text(Localization::String& value) {size_t n=0;const char* p=value.toUTF8(n);return std::string(p,n);}
static void Bounds() {
    Localization::String value("one|two"),empty;
    CHECK(!value.SetPlurality(0));CHECK(!value.SetPlurality(3));
    CHECK(value.GetPlurality(1)==1&&value.GetPlurality(2)==1);
    CHECK(value.SetPlurality(2));CHECK(value.GetPlurality(1)==2&&value.GetPlurality(2)==2);
    CHECK(!value.SetPlurality(3));CHECK(value.GetPlurality(1)==2&&value.GetPlurality(2)==2);
    CHECK(empty.SetPlurality(2));CHECK(empty.IsEmpty()&&empty.GetNumForms()==0);
    CHECK(!value.PushArgument(nullptr,1));CHECK(!value.PushArgument("x",(std::numeric_limits<size_t>::max)()));
    CHECK(value.GetArgumentCount()==0);
    CHECK(!value.SetGender(0,Localization::GENDER_NEUTER));CHECK(!value.SetPlurality(999,1));
    CHECK(!value.HasForm(-1)&&!value.HasForm(0)&&value.HasForm(2)&&!value.HasForm(3));
    size_t length=99;CHECK(value.toUTF8(length,INT_MIN)!=nullptr&&length==0);
    const char embedded[]={'a',0,'b'};Localization::String binary(embedded,3);CHECK(Text(binary)==std::string(embedded,3));
    Localization::String parent("[{1}]"),argument("child {1}");CHECK(argument.PushArgument(7));CHECK(parent.PushArgument(argument));
    argument="changed";CHECK(Text(parent)=="[child 7]");
    Localization::String copy(parent);parent="other";CHECK(Text(copy)=="[child 7]");
    const char* alias=copy.toUTF8();copy=alias;CHECK(Text(copy)=="[child 7]");
    Localization::String retry("{1}/{2}");CHECK(retry.PushArgument("one"));CHECK(!retry.Compose());CHECK(Text(retry).empty());
    CHECK(retry.PushArgument("two"));CHECK(Text(retry)=="one/two");
    Localization::String invalid("prefix {1:unknown} suffix");CHECK(invalid.PushArgument("text"));CHECK(!invalid.Compose());CHECK(Text(invalid).empty());
    Localization::String unsafe("{1:spellout}");CHECK(unsafe.PushArgument(std::numeric_limits<double>::quiet_NaN()));CHECK(!unsafe.Compose());CHECK(Text(unsafe).empty());
    Localization::String preserved("unchanged");const auto& dictionary=Localization::GetStringDictionary();
    CHECK(!dictionary.TryLookupLanguage("TXT_HELLO",9,UINT_MAX,preserved));CHECK(Text(preserved)=="unchanged");
    CHECK(!dictionary.TryLookup(nullptr,1,preserved));CHECK(Text(preserved)=="unchanged");
    int compare=99;CHECK(!Localization::GetCurrentLanguage().Compare("\xff",1,"a",1,compare)&&compare==99);
    CHECK(!Localization::GetCurrentLanguage().Compare(nullptr,1,"a",1,compare)&&compare==99);
    std::printf("HARDENING|bounds|PASS\n");
}
static void DictionaryFailures(Database::Connection& db) {
    CHECK(!Localization::InitializeDictionary(db,"missing_table","en_US",false));
    auto value=Localization::Lookup("TXT_HELLO");CHECK(Text(value)=="Hello");
    CHECK(!Localization::InitializeDictionary(db,"Languages","missing_locale",false));
    CHECK(Localization::GetStringDictionary().GetCurrentLanguageIndex()==0);
    CHECK(db.ExecuteMultiple("ALTER TABLE LocalizedText RENAME TO TemporarilyUnavailable;"));
    Localization::GetStringDictionary().NotifyDatabaseUpdated();value=Localization::Lookup("TXT_HELLO");CHECK(Text(value)=="Hello");
    CHECK(db.ExecuteMultiple("ALTER TABLE TemporarilyUnavailable RENAME TO LocalizedText;"
        "UPDATE LocalizedText SET Text='Refreshed' WHERE Language='en_US' AND Tag='TXT_HELLO';"
        "INSERT INTO LocalizedText VALUES('en_US','TXT_CYCLE','{TXT_CYCLE}',NULL,NULL);"));
    Localization::GetStringDictionary().NotifyDatabaseUpdated();value=Localization::Lookup("TXT_HELLO");CHECK(Text(value)=="Refreshed");
    Localization::String cycle("before {TXT_CYCLE} after");CHECK(!cycle.Compose());CHECK(Text(cycle).empty());
    CHECK(db.ExecuteMultiple("UPDATE LocalizedText SET Text='Hello' WHERE Language='en_US' AND Tag='TXT_HELLO';"));
    Localization::GetStringDictionary().NotifyDatabaseUpdated();
    CHECK(db.ExecuteMultiple("ALTER TABLE LocalizedText RENAME TO RealLocalizedText;"
        "CREATE VIEW LocalizedText AS SELECT rowid,Language,Tag,CASE WHEN Tag='TXT_ONLY_EN' "
        "THEN abs(-9223372036854775808) ELSE Text END AS Text,Gender,Plurality FROM RealLocalizedText;"));
    Localization::GetStringDictionary().NotifyDatabaseUpdated();value=Localization::Lookup("TXT_HELLO");CHECK(Text(value)=="Hello");
    CHECK(db.ExecuteMultiple("DROP VIEW LocalizedText;ALTER TABLE RealLocalizedText RENAME TO LocalizedText;"));
    std::printf("HARDENING|dictionary_failure_and_cycle|PASS\n");
}
static void ThreadsAndLifetime(Database::Connection& db) {
    std::atomic<unsigned> failures(0),completed(0),waiting(0),phase(0);
    std::vector<std::thread> workers;
    for(unsigned w=0;w<4;++w)workers.emplace_back([&] {
        for(unsigned i=0;i<128;++i) {
            Localization::String value("{TXT_HELLO}:{1:number 0}");value.PushArgument(static_cast<int>(i));
            if(Text(value)!="Hello:"+std::to_string(i))++failures;++completed;
        }
        ++waiting;while(!phase.load())std::this_thread::yield();
        for(unsigned i=0;i<128;++i) {
            Localization::String value("{1:number}");value.PushArgument(static_cast<int>(i));
            if(value.Compose())++failures;++completed;
        }
    });
    while(waiting.load()!=4)std::this_thread::yield();
    Localization::String bound("{1:spellout}");CHECK(bound.PushArgument(2));
    CHECK(bound.SetLanguage(const_cast<Localization::Language*>(&Localization::GetCurrentLanguage())));
    CHECK(Localization::Shutdown());phase=1;
    for(auto& worker:workers)worker.join();CHECK(failures==0&&completed==1024);
    CHECK(!bound.Compose());CHECK(!Localization::Initialize(L"missing-icu-data.dat",db,"Languages","en_US",false));
    CHECK(Localization::Initialize(L"icudt44l.dat",db,"Languages","en_US",false));CHECK(Text(bound)=="two");
    CHECK(!Localization::Initialize(L"icudt44l.dat",db,"Languages","ko_KR",false));CHECK(Text(bound)=="two");
    CHECK(Localization::SetCurrentLanguage("ko_KR"));CHECK(Text(bound)=="\xec\x9d\xb4");
    CHECK(Localization::SetCurrentLanguage("en_US"));CHECK(Text(bound)=="two");
    std::printf("HARDENING|threads_and_reinitialization|PASS|workers=4|calls=%u\n",completed.load());
}
int main(int argc,char** argv) {
    if(argc!=2||std::strcmp(argv[1],"hardening"))return 1;
    SetErrorMode(SEM_FAILCRITICALERRORS|SEM_NOGPFAULTERRORBOX);std::setvbuf(stdout,nullptr,_IONBF,0);
    Database::Connection db;Setup(db);auto logger=new QuietLogger;Localization::SetLogger(logger);Localization::SetLogger(logger);
    CHECK(Localization::GetLogger()==logger);CHECK(Localization::Initialize(L"icudt44l.dat",db,"Languages","en_US",false));
    Bounds();DictionaryFailures(db);CHECK(logger->errors>0);ThreadsAndLifetime(db);
    CHECK(Localization::Shutdown());CHECK(Localization::GetLogger()==nullptr);
    std::printf("PASS|%u\n",checks);return 0;
}
