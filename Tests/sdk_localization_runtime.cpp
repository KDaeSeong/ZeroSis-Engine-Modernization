// Original-component observations, using the same sealed in-memory database.
#define main sealed_localization_reference_entry_point
#include "sdk_localization_trace.cpp"
#undef main

static void Query(const char* label, const char* key) {
    const Localization::StringDictionary& dictionary = Localization::GetStringDictionary();
    Localization::String value("unchanged");
    const bool found = dictionary.TryLookup(key, static_cast<unsigned>(std::strlen(key)), value);
    std::printf("QUERY|%s|found=%d|has=%d\n", label, found, dictionary.HasKey(key, static_cast<unsigned>(std::strlen(key))));
    Emit(label, value);
}
static void Updates(Database::Connection& db) {
    const Localization::StringDictionary& dictionary = Localization::GetStringDictionary();
    for (unsigned i=0; i<dictionary.GetLanguageCount(); ++i) {
        std::printf("LANG|%u|%s|%s|%d\n", i, dictionary.GetLanguageType(i), dictionary.GetLanguageDisplayName(i), dictionary.GetLanguage(i).GetPluralityRule());
    }
    Query("initial", "TXT_HELLO"); Query("missing", "TXT_NEW");
    CHECK(db.ExecuteMultiple("UPDATE LocalizedText SET Text='Changed' WHERE Language='en_US' AND Tag='TXT_HELLO';"
        "INSERT INTO LocalizedText VALUES('en_US','TXT_NEW','New',NULL,NULL);"
        "INSERT INTO LocalizedText VALUES('en_US','TXT_COLD_NEW','Cold new',NULL,NULL);"
        "UPDATE LocalizedText SET Text='Cold changed' WHERE Tag='TXT_COLD';"));
    Query("before_notify", "TXT_HELLO"); Query("new_before_notify", "TXT_NEW");
    Query("cold_before_notify", "TXT_COLD"); Query("cold_new_before_notify", "TXT_COLD_NEW");
    dictionary.NotifyDatabaseUpdated(); Query("after_notify", "TXT_HELLO"); Query("new_after_notify", "TXT_NEW");
    CHECK(db.ExecuteMultiple("DELETE FROM LocalizedText WHERE Tag='TXT_HELLO';"));
    Query("deleted_before_notify", "TXT_HELLO"); dictionary.NotifyDatabaseUpdated(); Query("deleted_after_notify", "TXT_HELLO");
    CHECK(db.ExecuteMultiple("INSERT INTO LocalizedText VALUES('en_US','TXT_NULL',NULL,NULL,NULL);"
        "INSERT INTO LocalizedText VALUES('en_US','TXT_EMPTY','',NULL,NULL);"));
    dictionary.NotifyDatabaseUpdated(); Query("null", "TXT_NULL"); Query("empty", "TXT_EMPTY");
    Localization::String explicitLookup = dictionary.LookupLanguage("TXT_ONLY_KO", 0); Emit("explicit_fallback", explicitLookup);
    CHECK(Localization::ShutdownDictionary());
    CHECK(Localization::InitializeDictionary(db,"Languages","en_US",true));
    Query("fallback_disabled", "TXT_ONLY_KO"); Query("fallback_disabled_own", "TXT_ONLY_EN");
    Query("disabled_missing", "TXT_ABSENT");
}
static void LanguageBinding(Database::Connection& db) {
    CHECK(db.ExecuteMultiple("INSERT INTO LocalizedText VALUES('en_US','TXT_NUM','{1:spellout}',NULL,NULL);"
        "INSERT INTO LocalizedText VALUES('ko_KR','TXT_NUM','{1:spellout}',NULL,NULL);"));
    Localization::GetStringDictionary().NotifyDatabaseUpdated();
    Localization::String late("{TXT_HELLO}"), explicitText("{TXT_HELLO}"), fetched = Localization::Lookup("TXT_NUM");
    CHECK(explicitText.SetLanguage(const_cast<Localization::Language*>(&Localization::GetCurrentLanguage())));
    CHECK(fetched.PushArgument(2));
    CHECK(Localization::SetCurrentLanguage("ko_KR"));
    Emit("late", late); Emit("explicit_english", explicitText); Emit("fetched_english", fetched);
    std::printf("BOUND_LANGUAGE|%s|%s|%s\n", late.GetLanguage()?late.GetLanguage()->GetType():"NULL",
        explicitText.GetLanguage()?explicitText.GetLanguage()->GetType():"NULL", fetched.GetLanguage()?fetched.GetLanguage()->GetType():"NULL");
    CHECK(Localization::SetCurrentLanguage("en_US")); Emit("composed_after_switch", late);
    CHECK(explicitText.SetLanguage(NULL)); Emit("explicit_reset", explicitText);
}
static void Selectors() {
    const char* patterns[]={"{1[2]}","{1_Name[2]}","{1[0]}","{1[9]}","{1[feminine]}","{1[2]:upper}",
        "{1[2]:plural 1?one;2?two;other?other;}","{@1:gender masculine?he;feminine?she;other?they;}",
        "{@1:plural 1?one;2?two;other?other;}","{@2}","{1:gender *:vowel?vowel;feminine?female;other?other;}",
        "{1:gender masculine:vowel?vowel;feminine?female;other?other;}","{1:plural other?other;1?one;}",
        "{1:plural 1?first;1?second;other?other;}","{1:gender unknown?unknown;other?other;}",
        "{1:plural 1?{2};other?{3};}","{TXT_HELLO[1]}","{1:textkey}","{1:UPPER}"};
    for(unsigned i=0;i<sizeof(patterns)/sizeof(patterns[0]);++i) {
        Localization::String value(patterns[i]), argument("alpha|beta|gamma");
        CHECK(argument.SetGender("masculine:vowel|feminine|neuter")); CHECK(argument.SetPlurality("1|2|1"));
        CHECK(value.PushArgument(argument));CHECK(value.PushArgument("second"));CHECK(value.PushArgument("third"));
        CHECK(value.SetGender(Localization::GENDER_FEMININE));CHECK(value.SetPlurality("2"));
        std::printf("SELECTOR|%u|%s\n",i,patterns[i]);Emit("selector",value);
    }
    Localization::String value("a|b|c|d");CHECK(value.SetGender("masculine|feminine|masculine|feminine"));CHECK(value.SetPlurality("1|2|1|2"));
    for(int offset=-1;offset<=5;++offset)std::printf("OFFSET|%d|gender=%u|plural=%u|both=%u\n",offset,
        static_cast<unsigned>(value.GetFormByGender("feminine",offset)),static_cast<unsigned>(value.GetFormByPlurality(2,offset)),
        static_cast<unsigned>(value.GetFormByPluralityAndGender(2,"feminine",offset)));
}
static void Rules(int rule) {
    const int values[]={-101,-21,-11,-2,-1,0,1,2,3,4,5,6,7,10,11,12,14,15,19,20,21,22,25,99,100,101,102,111,112,1000};
        std::printf("RULE|%d",rule);
            const Localization::Language& language=Localization::GetCurrentLanguage();
            Localization::IPluralityRule* plurality=language.GetPluralityRule();
            std::printf("|rule_null=%d",plurality==NULL);
            if(plurality) {
                std::printf("|max=%u",plurality->GetMaxPluralForms());
                for(unsigned i=0;i<sizeof(values)/sizeof(values[0]);++i)std::printf("|%d:%u",values[i],language.GetPluralForm(values[i]));
                for(int value=-250;value<=250;++value)std::printf("|%d:%u",value,language.GetPluralForm(value));
            }
        std::printf("\n");
}
static unsigned destroyedLoggers=0;
struct CountedLogger:Localization::ILocalizationLogger {
    ~CountedLogger(){++destroyedLoggers;}
    void Log(const char*,LogTypes) {}
};
static void Ownership() {
    Localization::SetLogger(new CountedLogger);std::printf("LOGGER|first|destroyed=%u\n",destroyedLoggers);
    Localization::SetLogger(new CountedLogger);std::printf("LOGGER|replace|destroyed=%u\n",destroyedLoggers);
    Localization::SetLogger(NULL);std::printf("LOGGER|clear|destroyed=%u\n",destroyedLoggers);
    Localization::SetLogger(new CountedLogger);
}
static void Setters() {
    const char* forms[]={"","one","one|two","one|two|three"};
    for(unsigned f=0;f<4;++f)for(unsigned p=0;p<5;++p) {
        Localization::String value(forms[f]);const bool result=value.SetPlurality(static_cast<size_t>(p));
        std::printf("SET_ALL|forms=%u|value=%u|result=%d",f,p,result);
        for(unsigned form=1;form<=value.GetNumForms();++form)std::printf("|%u:%u",form,static_cast<unsigned>(value.GetPlurality(form)));
        std::printf("\n");
    }
}
static void Edges() {
    const char* patterns[]={"before {1:title} after","before {1:upper} after","before {1:textkey} after",
        "before {TXT_NESTED:upper} after","before {TXT_NESTED} after","{1[2]}","{1['feminine']}","{1[\"feminine\"]}",
        "{1[{2}]}","{1[2]:title}","{1:plural 1?yes;other?no;}","{1:gender other?other;masculine?male;}",
        "{1['2']}","{1['masculine']}","{1['feminine']}","{1['1']}","{1['0']}"};
    for(unsigned p=0;p<sizeof(patterns)/sizeof(patterns[0]);++p)for(int input=0;input<4;++input) {
        Localization::String value(patterns[p]);
        if(input==0)CHECK(value.PushArgument(12));
        else if(input==1){Localization::String child("one|two");CHECK(child.SetGender("masculine|feminine"));CHECK(value.PushArgument(child));}
        else if(input==2)CHECK(value.PushArgument(""));
        else CHECK(value.PushArgument("missing {9}"));
        CHECK(value.PushArgument(2));std::printf("EDGE|%u|%d\n",p,input);Emit("edge",value);
    }
    const char* strings[]={"a","A","b","z","\xed\x95\x9c\xea\xb8\x80","\xff"};
    for(unsigned i=0;i<6;++i){int result=99;const bool success=Localization::GetCurrentLanguage().Compare(strings[i],std::strlen(strings[i]),"a",1,result);
        std::printf("COMPARE|%u|success=%d|result=%d\n",i,success,result);}
}
int main(int argc,char** argv) {
    if(argc!=2)return 1;SetErrorMode(SEM_FAILCRITICALERRORS|SEM_NOGPFAULTERRORBOX);std::setvbuf(stdout,NULL,_IONBF,0);
    Database::Connection db;Setup(db);Localization::SetLogger(new Logger);
    CHECK(db.ExecuteMultiple("INSERT INTO LocalizedText VALUES('en_US','TXT_COLD','Cold old',NULL,NULL);"));
    const int rule=!std::strncmp(argv[1],"rule_",5)?std::atoi(argv[1]+5):-1;
    if(rule>=0) {char sql[160];sprintf_s(sql,sizeof(sql),"UPDATE Languages SET PluralRule=%d",rule);CHECK(db.ExecuteMultiple(sql));}
    CHECK(Localization::Initialize(L"icudt44l.dat",db,"Languages","en_US",false));
    if(!std::strcmp(argv[1],"updates"))Updates(db);else if(!std::strcmp(argv[1],"binding"))LanguageBinding(db);
    else if(!std::strcmp(argv[1],"selectors"))Selectors();else if(!std::strcmp(argv[1],"ownership"))Ownership();
    else if(!std::strcmp(argv[1],"setters"))Setters();else if(!std::strcmp(argv[1],"edges"))Edges();else if(rule>=0)Rules(rule);else return 1;
    CHECK(Localization::Shutdown());
    if(!std::strcmp(argv[1],"ownership"))std::printf("LOGGER|shutdown|destroyed=%u\n",destroyedLoggers);
    Localization::SetLogger(NULL);
    if(!std::strcmp(argv[1],"ownership"))std::printf("LOGGER|final|destroyed=%u\n",destroyedLoggers);
    std::printf("PASS|%u\n",checks);return 0;
}
