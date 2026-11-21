// Reuse the already sealed fixture, logger and trace helpers unchanged.
#define main sealed_numeric_reference_entry_point
#include "sdk_localization_trace.cpp"
#undef main

static void Describe(const char* label, Localization::String& value) {
    size_t baseLength = 0; const char* base = value.GetBaseString(baseLength);
    std::printf("BASE|%s|empty=%d|forms=%u|bytes=%u|", label, value.IsEmpty(), static_cast<unsigned>(value.GetNumForms()), static_cast<unsigned>(baseLength));
    Hex(base, baseLength); std::printf("\n");
    for (unsigned f = 0; f <= value.GetNumForms() + 1; ++f) {
        size_t plurality = value.GetPlurality(f);
        std::printf("META|%u|gender=%d|plurality=%d\n", f, value.GetGender(f), plurality == static_cast<size_t>(-1) ? -1 : static_cast<int>(plurality));
        Emit(label, value, static_cast<int>(f));
    }
}

static void Shared() {
    Localization::SharedString empty, text("a\0bcd",5), copy(text);
    size_t n = 777; const char* p = empty.GetBuffer(n);
    std::printf("SHARED_EMPTY|buffer_null=%d|n=%u|offset=%u|length=%u|bufferlength=%u\n", p==NULL, static_cast<unsigned>(n), static_cast<unsigned>(empty.GetOffset()), static_cast<unsigned>(empty.GetLength()), static_cast<unsigned>(empty.GetBufferLength()));
    const size_t offsets[] = {0,1,4,5,6,1,0}; const size_t lengths[] = {5,3,1,0,0,9,0};
    for (unsigned i=0;i<7;++i) {
        const bool changed = copy.SetOffsetAndLength(offsets[i],lengths[i]);
        p=copy.GetString(n);
        std::printf("SHARED|%u|set=%d|offset=%u|length=%u|buffer=%u|n=%u|",i,changed,static_cast<unsigned>(copy.GetOffset()),static_cast<unsigned>(copy.GetLength()),static_cast<unsigned>(copy.GetBufferLength()),static_cast<unsigned>(n));
        Hex(p,n);std::printf("\n");
    }
    p=text.GetString(n);std::printf("SHARED_ORIGINAL|");Hex(p,n);std::printf("\n");
}

static void FormMetadata() {
    const char* texts[]={"","|","one|","|two","one||three","one|two|three","{1:plural 1?a|b;other?c;}","[COLOR_RED]one[ENDCOLOR]|two"};
    for(unsigned i=0;i<sizeof(texts)/sizeof(texts[0]);++i) {
        std::printf("FORM_INPUT|%u|%s\n",i,texts[i]);Localization::String value(texts[i]);CHECK(value.PushArgument(1));Describe("forms",value);
    }
    const char* genders[]={"masculine:feminine:neuter","masculine|feminine|neuter","m:f:n","Masculine:Feminine:Neuter","feminine,animal:masculine:neuter","feminine animal:masculine:neuter","feminine;animal:masculine:neuter","animal:feminine:masculine","masculine:vowel|feminine:no_article|neuter:animal"};
    for(unsigned i=0;i<sizeof(genders)/sizeof(genders[0]);++i) {
        Localization::String value("one|two|three");std::printf("GENDER_INPUT|%u|%s|set=%d\n",i,genders[i],value.SetGender(genders[i],std::strlen(genders[i])));Describe("gender",value);
        std::printf("FIND_GENDER|m=%u|f=%u|n=%u|animal=%u\n",static_cast<unsigned>(value.GetFormByGender("masculine")),static_cast<unsigned>(value.GetFormByGender("feminine")),static_cast<unsigned>(value.GetFormByGender("neuter")),static_cast<unsigned>(value.GetFormByGender("animal")));
        std::printf("FIND_TRAIT|m_vowel=%u|vowel=%u|f_no_article=%u|animal=%u\n",static_cast<unsigned>(value.GetFormByGender("masculine:vowel")),static_cast<unsigned>(value.GetFormByGender("*:vowel")),static_cast<unsigned>(value.GetFormByGender("feminine:no_article")),static_cast<unsigned>(value.GetFormByGender("*:animal")));
    }
    const char* pluralities[]={"1:2:3","1|2|3","0:1:2","1;2;3","1:2","1","other","-1:2:3"};
    for(unsigned i=0;i<sizeof(pluralities)/sizeof(pluralities[0]);++i) {
        Localization::String value("one|two|three");std::printf("PLURALITY_INPUT|%u|%s|set=%d\n",i,pluralities[i],value.SetPlurality(pluralities[i],std::strlen(pluralities[i])));Describe("plurality",value);
        std::printf("FIND_PLURAL|0=%u|1=%u|2=%u|3=%u\n",static_cast<unsigned>(value.GetFormByPlurality(0)),static_cast<unsigned>(value.GetFormByPlurality(1)),static_cast<unsigned>(value.GetFormByPlurality(2)),static_cast<unsigned>(value.GetFormByPlurality(3)));
    }
}

static void Grammar() {
    const char* patterns[]={"{ 1 }","{1_Any_Label}","{1: upper}","{1:upper lower}","{1:upper:lower}","{1:upper;lower}","{1:upper}{1:lower}",
        "{TXT_HELLO:upper}","{TXT_NESTED}","{TXT_NESTED:upper}","{TXT_MISSING}","{TXT_HELLO(1)}","{1!}","before {1} after", "{1}\0ignored",
        "{1:plural 1?one;2?two;other?many;}","{1:plural 1?{TXT_HELLO};other?{2};}","{1:plural 1?one;other?many}",
        "{1:plural 1?one;else?many;}","{1:plural 0?zero;1?one;2?two;}","{1:choice 1?one;other?many;}",
        "{1:gender masculine?he;feminine?she;other?they;}","{1:text foo?yes;other?no;}","{1:select foo?yes;other?no;}"};
    for(unsigned p=0;p<sizeof(patterns)/sizeof(patterns[0]);++p) {
        for(int input=-1;input<=3;++input) {
            std::printf("GRAMMAR|%u|%d|%s\n",p,input,patterns[p]);Localization::String value(patterns[p]);
            if(input==-1) { Localization::String s("foo");CHECK(s.SetGender(Localization::GENDER_FEMININE));CHECK(value.PushArgument(s)); }
            else CHECK(value.PushArgument(input));
            CHECK(value.PushArgument("second"));Emit("grammar",value);
        }
    }
}

static void Mutations() {
    Localization::String value("{1}/{2}|{2}/{1}"); CHECK(value.PushArgument("a")); CHECK(value.PushArgument(7));Describe("initial",value);
    Localization::String copy(value); CHECK(value.PushArgument(9));Describe("extra_arg",value);Describe("copy",copy);
    value="{1}";Emit("assigned",value);CHECK(value.PushArgument("new"));Emit("assigned_arg",value);
    const char* retained=value.toUTF8();value=retained;Emit("self_buffer",value);
    Localization::String noForms;CHECK(noForms.PushArgument(123));Describe("empty_args",noForms);
    Localization::String argument("one|two");CHECK(argument.SetGender(Localization::GENDER_FEMININE));
    std::printf("SET_ALL_PLURAL|%d\n",argument.SetPlurality(2));Describe("all_plural",argument);
    std::printf("SET_PLURAL_STRING|%d\n",argument.SetPlurality("2"));Describe("string_plural",argument);
    Localization::String parent("{1}|{1:gender feminine?she;other?they;}");CHECK(parent.PushArgument(argument));Describe("nested_forms",parent);
    std::printf("SET_FORM|plural0=%d|plural4=%d|gender0=%d|gender4=%d\n",argument.SetPlurality(static_cast<size_t>(0),3),argument.SetPlurality(4,3),argument.SetGender(0,Localization::GENDER_MASCULINE),argument.SetGender(4,Localization::GENDER_MASCULINE));
}

int main(int argc,char** argv) {
    if(argc!=2)return 1;SetErrorMode(SEM_FAILCRITICALERRORS|SEM_NOGPFAULTERRORBOX);std::setvbuf(stdout,NULL,_IONBF,0);
    Database::Connection db;Setup(db);Localization::SetLogger(new Logger);
    CHECK(Localization::Initialize(L"icudt44l.dat",db,"Languages","en_US",false));
    if(!std::strcmp(argv[1],"shared"))Shared();else if(!std::strcmp(argv[1],"metadata"))FormMetadata();
    else if(!std::strcmp(argv[1],"grammar"))Grammar();else if(!std::strcmp(argv[1],"mutations"))Mutations();else return 1;
    CHECK(Localization::Shutdown());Localization::SetLogger(NULL);std::printf("PASS|%u\n",checks);return 0;
}
