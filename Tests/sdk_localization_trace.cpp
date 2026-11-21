#include "SdkLocalizationIncludes.h"
#include "localization_numeric_cases.h"
static unsigned checks=0;
#define CHECK(x) do { ++checks;if(!(x)) { std::fprintf(stderr,"FAIL|%u|%d|%s\n",checks,__LINE__,#x);std::exit(2); } } while(0)
static void Hex(const char* text,size_t size) {
    if(!text) { std::printf("NULL");return; }
    for(size_t i=0;i<size;++i)std::printf("%02x",static_cast<unsigned char>(text[i]));
}
struct Logger:Localization::ILocalizationLogger {
    void Log(const char* message,LogTypes type) { std::printf("LOG|%d|",type);Hex(message,message?std::strlen(message):0);std::printf("\n"); }
};
static void Emit(const char* label,Localization::String& value,int form=1) {
    size_t size=0;const char* output=value.toUTF8(size,form);
    std::printf("TEXT|%s|empty=%d|forms=%u|form=%d|bytes=%u|",label,value.IsEmpty(),
        static_cast<unsigned>(value.GetNumForms()),form,static_cast<unsigned>(size));
    Hex(output,size);std::printf("\n");
}
static void Basic() {
    Localization::String empty,plain("hello"),binary("a\0b",3),korean("\xed\x95\x9c\xea\xb8\x80");
    Emit("empty",empty);Emit("plain",plain);Emit("binary",binary);Emit("korean",korean);
    Localization::String copied(plain);Emit("copied",copied);plain="changed";Emit("copy_independent",copied);
    copied=copied;Emit("self",copied);copied=empty;Emit("empty_assignment",copied);
    Localization::String key=Localization::Lookup("TXT_HELLO"),missing=Localization::Lookup("TXT_MISSING"),literal=Localization::Lookup("literal words");
    Emit("lookup",key);Emit("missing",missing);Emit("lookup_literal",literal);
    Localization::String askey("TXT_HELLO");Emit("key_constructor",askey);
    std::printf("STATIC_EMPTY|%d\n",Localization::String::Empty.IsEmpty());
}
static void Parameters() {
    const char* cases[]={"{1}","{1_Name}","Hello {1_Name}, {2_Num}!","{2}:{1}:{2}","{TXT_HELLO}","{TXT_NESTED}",
        "{{1}}","{0}","{9_Missing}","open {1","close }","{1:bad}","[COLOR_RED]{1}[ENDCOLOR]","{1_Name:upper}","{1_Name:lower}",
        "{1_Name:uppercase}","{1_Name:lowercase}","{1_Name:titlecase}","{1_Name:textkey}","{1_Name:title}","{1_Name:capitalize}"};
    for(unsigned i=0;i<sizeof(cases)/sizeof(cases[0]);++i) {
        std::printf("CASE|%u|%s\n",i,cases[i]);Localization::String value(cases[i]);
        CHECK(value.PushArgument("hEllo"));CHECK(value.PushArgument(7));Emit("parameters",value);
    }
    Localization::String nested("[ {1} ]");Localization::String argument("child {1}");CHECK(argument.PushArgument(12));CHECK(nested.PushArgument(argument));
    Emit("nested",nested);argument="changed";Emit("nested_retained",nested);
    Localization::String lazy("{1}/{2}");CHECK(lazy.PushArgument("first"));Emit("partial",lazy);CHECK(lazy.PushArgument("second"));Emit("after_compose",lazy);
}
static void Numbers() {
    const char* formats[]={"{1}","{1_Num}","{1: number}","{1_Num:number}","{1_Num:number #,##0.00}","{1_Num:number(0.00)}",
        "{1_Num:percent}","{1_Num:currency}","{1_Num:roman}","{1_Num:spellout}","{1_Num:ordinal}"};
    for(unsigned i=0;i<sizeof(formats)/sizeof(formats[0]);++i) {
        std::printf("FORMAT|%u|%s\n",i,formats[i]);
        Localization::String integer(formats[i]),real(formats[i]);CHECK(integer.PushArgument(12345));CHECK(real.PushArgument(1.25f));
        Emit("integer",integer);Emit("float",real);
    }
}
static void NumericCorpus() {
    using namespace LocalizationNumericCases;
    const std::vector<Input> values = Values();
    for (unsigned lang = 0; lang < sizeof(Locales) / sizeof(Locales[0]); ++lang) {
        CHECK(Localization::SetCurrentLanguage(Locales[lang]));
        for (unsigned style = 0; style < sizeof(Formats) / sizeof(Formats[0]); ++style) {
            for (unsigned i = 0; i < values.size(); ++i) {
                const Input& input = values[i];
                if (UnsafeRuleBased(style, input)) continue;
                Localization::String value(Formats[style]);
                bool pushed = false;
                switch (input.kind) {
                case Integer: pushed = value.PushArgument(static_cast<int>(input.integer)); break;
                case Integer64: pushed = value.PushArgument(input.integer); break;
                case Float: pushed = value.PushArgument(static_cast<float>(input.real)); break;
                case Double: pushed = value.PushArgument(input.real); break;
                }
                CHECK(pushed);
                size_t size = 0; const char* text = value.toUTF8(size);
                std::printf("NUMERIC|%u|%u|%u|", lang, style, i); Hex(text, size); std::printf("\n");
            }
        }
    }
}
static void SpelloutNaN() {
    unsigned bits = 0x7fc00000u; float value; std::memcpy(&value, &bits, sizeof(value));
    Localization::String text("{1_Num:spellout}"); CHECK(text.PushArgument(value));
    std::printf("BEGIN|SPELL_OUT_FLOAT_QUIET_NAN\n"); Emit("spellout_nan", text);
}
static void Forms() {
    const char* cases[]={"one|many","one;many","one/many","one\\many","one[NEWLINE]many","{1:plural one;many;}","{1:plural 1?one;other?many;}",
        "{1:gender masculine?he;feminine?she;other?they;}","{1:plural 1?one;2?many;}"};
    for(unsigned i=0;i<sizeof(cases)/sizeof(cases[0]);++i) {
        std::printf("CASE|%u|%s\n",i,cases[i]);Localization::String value(cases[i]);CHECK(value.PushArgument(2));
        Emit("forms",value,1);Emit("forms",value,2);
    }
}
static void Dictionary() {
    const Localization::StringDictionary& dictionary=Localization::GetStringDictionary();
    std::printf("LANGUAGES|%u|%u\n",static_cast<unsigned>(dictionary.GetLanguageCount()),dictionary.GetCurrentLanguageIndex());
    const char* languages[]={"en_US","ko_KR","absent"};const char* keys[]={"TXT_HELLO","TXT_NESTED","TXT_ONLY_EN","TXT_ONLY_KO","TXT_MISSING","TXT_FORMS"};
    for(unsigned l=0;l<3;++l) {
        std::printf("SET_LANGUAGE|%s|%d\n",languages[l],Localization::SetCurrentLanguage(languages[l]));
        for(unsigned i=0;i<6;++i) {
            Localization::String result=Localization::Lookup(keys[i]);std::printf("KEY|%s\n",keys[i]);Emit("dictionary",result);
        }
    }
}
static void Setup(Database::Connection& db) {
    CHECK(db.Open(":memory:",Database::OPEN_READWRITE|Database::OPEN_CREATE));
    CHECK(db.ExecuteMultiple(
        "CREATE TABLE Languages(ID INTEGER PRIMARY KEY,Type TEXT,Name TEXT,TableName TEXT,PluralRule INTEGER);"
        "INSERT INTO Languages VALUES(0,'en_US','English','Language_en_US',2);"
        "INSERT INTO Languages VALUES(8,'ko_KR','Korean','Language_KO_KR',2);"
        "CREATE TABLE LocalizedText(Language TEXT,Tag TEXT,Text TEXT,Gender TEXT,Plurality TEXT,PRIMARY KEY(Language,Tag));"
        "CREATE TABLE LanguagePriorities(LanguageSet TEXT,Language TEXT,Priority INTEGER,PRIMARY KEY(LanguageSet,Language));"
        "INSERT INTO LanguagePriorities VALUES('en_US','en_US',100);"
        "INSERT INTO LanguagePriorities VALUES('ko_KR','ko_KR',100);"
        "INSERT INTO LanguagePriorities VALUES('ko_KR','en_US',50);"
        "INSERT INTO LocalizedText VALUES('en_US','TXT_HELLO','Hello',NULL,NULL);"
        "INSERT INTO LocalizedText VALUES('en_US','TXT_NESTED','Value {1_Num}',NULL,NULL);"
        "INSERT INTO LocalizedText VALUES('en_US','TXT_ONLY_EN','English only',NULL,NULL);"
        "INSERT INTO LocalizedText VALUES('ko_KR','TXT_HELLO','\xed\x95\x9c\xea\xb8\x80',NULL,NULL);"
        "INSERT INTO LocalizedText VALUES('ko_KR','TXT_ONLY_KO','Korean only',NULL,NULL);"
        "INSERT INTO LocalizedText VALUES('en_US','TXT_FORMS','one:many','masculine:feminine','1:2');"
        "CREATE VIEW Language_en_US AS SELECT Tag,Text,Gender,Plurality FROM LocalizedText WHERE Language='en_US';"
        "CREATE VIEW Language_KO_KR AS SELECT Tag,Text,Gender,Plurality FROM LocalizedText WHERE Language='ko_KR';"));
}
int main(int argc,char** argv) {
    if(argc!=2)return 1;SetErrorMode(SEM_FAILCRITICALERRORS|SEM_NOGPFAULTERRORBOX);
    std::setvbuf(stdout,NULL,_IONBF,0);Database::Connection db;Setup(db);Localization::SetLogger(new Logger);
    const bool ready=Localization::Initialize(L"icudt44l.dat",db,"Languages","en_US",false);std::printf("INITIALIZE|%d\n",ready);CHECK(ready);
    {
        if(!std::strcmp(argv[1],"basic"))Basic();else if(!std::strcmp(argv[1],"parameters"))Parameters();
        else if(!std::strcmp(argv[1],"numbers"))Numbers();else if(!std::strcmp(argv[1],"forms"))Forms();
        else if(!std::strcmp(argv[1],"dictionary"))Dictionary();else if(!std::strcmp(argv[1],"numeric_corpus"))NumericCorpus();
        else if(!std::strcmp(argv[1],"spellout_nan"))SpelloutNaN();else return 1;
    }
    std::printf("SHUTDOWN|%d\n",Localization::Shutdown());Localization::SetLogger(NULL);
    std::printf("PASS|%u\n",checks);return 0;
}
