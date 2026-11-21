#define CvLocalizationAPI __declspec(dllexport)
#include "SdkLocalizationRuntime.h"
#include <cctype>
#include <cmath>
#include <limits>
#include <unicode/utypes.h>

namespace {
using namespace Localization;
using Lock = std::lock_guard<std::recursive_mutex>;
constexpr size_t MaxOutput = 16 * 1024 * 1024;
thread_local unsigned renderDepth = 0;
thread_local size_t renderWork = 0;
thread_local bool renderLimitExceeded = false;
struct RenderScope {
    RenderScope() { if (!renderDepth) {renderWork=0;renderLimitExceeded=false;} ++renderDepth; }
    ~RenderScope() { --renderDepth; }
};
bool Space(char c) { return c==' ' || c=='\t' || c=='\r' || c=='\n'; }
bool Digit(char c) { return c>='0' && c<='9'; }
bool Name(char c) { return (c>='a'&&c<='z') || (c>='A'&&c<='Z') || Digit(c) || c=='_'; }
std::string Trim(const std::string& text) {
    size_t first=0,last=text.size();while(first<last&&Space(text[first]))++first;while(last>first&&Space(text[last-1]))--last;
    return text.substr(first,last-first);
}
bool Append(std::string& target,const char* data,size_t length) {
    if(length>MaxOutput-target.size())return false;
    target.append(data?data:"",length);return true;
}
bool Append(std::string& target,const std::string& value) { return Append(target,value.data(),value.size()); }
bool Unsigned(const std::string& text,size_t& number) {
    if(text.empty())return false;size_t result=0;
    for(char c:text){if(!Digit(c)||result>((std::numeric_limits<size_t>::max)()-static_cast<unsigned>(c-'0'))/10)return false;result=result*10+static_cast<unsigned>(c-'0');}
    number=result;return true;
}
std::vector<std::string> Split(const std::string& value,char delimiter) {
    std::vector<std::string> parts;size_t start=0;
    for(;;){const size_t end=value.find(delimiter,start);parts.push_back(value.substr(start,end==std::string::npos?end:end-start));if(end==std::string::npos)break;start=end+1;}
    return parts;
}
bool GenderToken(std::string text,Gender& output) {
    for(char& c:text)if(c>='A'&&c<='Z')c=static_cast<char>(c-'A'+'a');
    if(text.empty())return false;
    const char* names[]={"neuter","masculine","feminine"};
    for(int i=0;i<3;++i)if(text.size()<=std::strlen(names[i])&&text.compare(0,text.size(),names[i],text.size())==0){output=static_cast<Gender>(i);return true;}
    return false;
}
bool MatchesGender(const SingleFormString& form,const std::string& selector) {
    const auto tokens=Split(selector,':');Gender gender=GENDER_NEUTER;
    if(tokens[0]!="*"&&(!GenderToken(tokens[0],gender)||form.GetGender()!=gender))return false;
    for(size_t i=1;i<tokens.size();++i)if(!form.HasTrait(tokens[i].data(),tokens[i].size()))return false;
    return true;
}
struct Token {
    size_t begin=0,end=0,index=0;
    std::string key,selector,style,options;
};
bool ParseToken(const std::string& body,Token& token) {
    size_t p=0;while(p<body.size()&&Space(body[p]))++p;if(p<body.size()&&body[p]=='@')++p;
    const size_t start=p;
    if(p<body.size()&&Digit(body[p])) {
        while(p<body.size()&&Digit(body[p]))++p;
        if(!Unsigned(body.substr(start,p-start),token.index)||!token.index)return false;
        if(p<body.size()&&body[p]=='_')while(p<body.size()&&Name(body[p]))++p;
    } else {
        while(p<body.size()&&Name(body[p]))++p;
        if(p==start)return false;token.key=body.substr(start,p-start);
    }
    while(p<body.size()&&Space(body[p]))++p;
    if(p<body.size()&&body[p]=='[') {
        const size_t selectorStart=++p;unsigned depth=1;
        while(p<body.size()&&depth){if(body[p]=='[')++depth;else if(body[p]==']')--depth;if(depth)++p;}
        if(depth)return false;token.selector=Trim(body.substr(selectorStart,p-selectorStart));++p;
    }
    while(p<body.size()&&Space(body[p]))++p;
    if(p==body.size())return true;
    if(body[p++]!=':')return false;
    while(p<body.size()&&Space(body[p]))++p;
    const size_t styleStart=p;while(p<body.size()&&Name(body[p]))++p;
    if(p==styleStart)return false;token.style=body.substr(styleStart,p-styleStart);token.options=Trim(body.substr(p));return true;
}
bool ParseTokens(const char* text,size_t length,std::vector<Token>& tokens) {
    if((!text&&length)||length>MaxOutput)return false;
    for(size_t p=0;p<length;) {
        if(text[p]!='{'){++p;continue;}Token token;token.begin=p;const size_t start=++p;unsigned depth=1;
        while(p<length&&depth){if(text[p]=='{'){if(++depth>64)return false;}else if(text[p]=='}')--depth;if(depth)++p;}
        if(depth)return false;token.end=p+1;
        if(!ParseToken(std::string(text+start,p-start),token))return false;
        tokens.push_back(std::move(token));++p;
    }
    return true;
}
bool Numeric(const ParameterArgument& argument,ZeroSisLocalization::NumericValue& output) {
    using ZeroSisLocalization::NumericValue;
    switch(argument.m_type) {
    case ParameterArgument::ARGTYPE_INT:output=NumericValue::FromInteger(argument.m_value.i);return true;
    case ParameterArgument::ARGTYPE_INT64:output=NumericValue::FromInteger(argument.m_value.i64);return true;
    case ParameterArgument::ARGTYPE_FLOAT:output=NumericValue::FromReal(argument.m_value.f);return true;
    case ParameterArgument::ARGTYPE_DOUBLE:output=NumericValue::FromReal(argument.m_value.d);return true;
    default:return false;
    }
}
bool Plain(const ParameterArgument& argument,size_t form,const Language& language,std::string& output) {
    if(argument.m_type==ParameterArgument::ARGTYPE_STRING) {
        if(!argument.m_str)return false;
        if(form>INT_MAX){output.clear();return true;}
        if(!argument.m_str->HasForm(static_cast<int>(form))) {output.clear();return true;}
        return StringImplementation::ReadComposed(*argument.m_str,form,output);
    }
    ZeroSisLocalization::NumericValue number{};
    return ZeroSisLocalization::IcuReady()&&Numeric(argument,number)&&ZeroSisLocalization::FormatNumeric(
        ZeroSisLocalization::LocaleOf(language),ZeroSisLocalization::NumericStyle::Decimal,number,"",output).succeeded;
}
bool Choice(const ParameterArgument& argument,const std::string& style,const std::string& options,const Language& language,
            const std::vector<ParameterArgument>& arguments,std::string& output) {
    size_t plurality=0;
    if(style=="gender") {if(argument.m_type!=ParameterArgument::ARGTYPE_STRING||!argument.m_str)return false;}
    else if(argument.m_type==ParameterArgument::ARGTYPE_STRING) {if(!argument.m_str)return false;plurality=argument.m_str->GetPlurality();}
    else {
        ZeroSisLocalization::NumericValue number{};if(!Numeric(argument,number))return false;
        int value=0;
        if(number.isInteger) {if(number.integer<INT_MIN||number.integer>INT_MAX)return false;value=static_cast<int>(number.integer);}
        else {if(!std::isfinite(number.real)||number.real<INT_MIN||number.real>INT_MAX)return false;value=static_cast<int>(number.real);}
        plurality=language.GetPluralForm(value);
    }
    size_t start=0;unsigned depth=0;
    for(size_t p=0;p<options.size();++p) {
        if(options[p]=='{')++depth;else if(options[p]=='}'&&depth)--depth;
        if(options[p]!=';'||depth)continue;
        const std::string branch=options.substr(start,p-start);start=p+1;const size_t question=branch.find('?');
        if(question==std::string::npos)continue;const std::string selector=Trim(branch.substr(0,question));bool match=selector=="other";
        if(!match&&style=="gender") match=argument.m_str->GetFormByGender(selector.data(),selector.size())==1;
        if(!match&&style=="plural"){size_t wanted=0;match=Unsigned(selector,wanted)&&wanted==plurality;}
        if(match){const std::string selected=branch.substr(question+1);return ZeroSisLocalization::RenderMessage(selected.data(),selected.size(),arguments,language,output);}
    }
    output.clear();return true;
}
}

namespace ZeroSisLocalization {
bool ValidateMessage(const char* text,size_t length,std::vector<Localization::StringParameter>& parameters) {
    std::vector<Token> tokens;if(!ParseTokens(text,length,tokens))return false;
    std::vector<Localization::StringParameter> parsed;parsed.reserve(tokens.size());
    for(const auto& token:tokens) {
        if(token.index>INT_MAX)return false;
        Localization::StringParameter p;p.ArgumentIndex=static_cast<int>(token.index);p.uiParameterStart=token.begin;p.uiParameterEnd=token.end;
        parsed.push_back(p);
    }
    parameters.swap(parsed);return true;
}
bool TransformArgument(const Localization::ParameterArgument& argument,const std::string& style,const std::string& options,
                       const Localization::Language& language,const std::vector<Localization::ParameterArgument>& arguments,std::string& output) {
    using namespace Localization;
    if(style=="plural"||style=="gender")return Choice(argument,style,options,language,arguments,output);
    if(style=="upper"||style=="lower"||style=="title"||style=="textkey") {
        if(argument.m_type!=ParameterArgument::ARGTYPE_STRING)return false;
        std::string text;if(!Plain(argument,1,language,text))return false;
        if(style=="textkey") {
            String value=GetStringDictionary().Lookup(text.c_str());
            for(const auto& item:arguments)if(!value.PushArgument(item))return false;
            return StringImplementation::ReadComposed(value,1,output);
        }
        if(!IcuReady())return false;
        const TextCase operation=style=="upper"?TextCase::Upper:style=="lower"?TextCase::Lower:TextCase::Title;
        const auto result=TransformTextCase(LocaleOf(language),operation,text.data(),text.size(),output);
        if(operation==TextCase::Title&&result.status==U_MISSING_RESOURCE_ERROR){output.clear();return true;}
        return result.succeeded;
    }
    NumericValue number{};if(!IcuReady()||!Numeric(argument,number))return false;
    NumericStyle format;
    if(style=="number")format=options.empty()?NumericStyle::Decimal:NumericStyle::Pattern;
    else if(style=="percent")format=NumericStyle::Percent;
    else if(style=="currency")format=NumericStyle::Currency;
    else if(style=="roman")format=NumericStyle::Roman;
    else if(style=="spellout")format=NumericStyle::Spellout;
    else if(style=="ordinal")format=NumericStyle::Ordinal;
    else return false;
    return FormatNumeric(LocaleOf(language),format,number,options,output).succeeded;
}
bool RenderMessage(const char* text,size_t length,const std::vector<Localization::ParameterArgument>& arguments,
                   const Localization::Language& language,std::string& output) {
    using namespace Localization;RenderScope scope;
    if(renderDepth>64||++renderWork>100000){renderLimitExceeded=true;return false;}
    std::vector<Token> tokens;if(!ParseTokens(text,length,tokens))return false;
    std::string candidate;size_t cursor=0;
    for(const auto& token:tokens) {
        if(!Append(candidate,text+cursor,token.begin-cursor))return false;
        std::unique_ptr<ParameterArgument> lookedUp;const ParameterArgument* argument=nullptr;
        if(token.index){if(token.index>arguments.size())return false;argument=&arguments[token.index-1];}
        else {
            String value=Lookup(token.key.c_str());
            if(token.style.empty())for(const auto& item:arguments)if(!value.PushArgument(item))return false;
            lookedUp.reset(new ParameterArgument(value));argument=lookedUp.get();
        }
        std::string rendered;
        if(token.style.empty()) {
            size_t form=1;
            if(!token.selector.empty()) {
                if(Unsigned(token.selector,form)) {if(!form)form=1;}
                else if(token.selector.front()=='{'&&token.selector.back()=='}') {
                    std::string selected;
                    if(!RenderMessage(token.selector.data(),token.selector.size(),arguments,language,selected))return false;
                    if(!Unsigned(selected,form))form=(std::numeric_limits<size_t>::max)();
                } else if(token.selector.size()>=2&&token.selector.front()=='\''&&token.selector.back()=='\'') {
                    // Quoted selectors are syntactically accepted but do not
                    // coerce to a numbered form in the original component.
                    form=(std::numeric_limits<size_t>::max)();
                } else return false;
            }
            if(!Plain(*argument,form,language,rendered))return false;
        } else if(!TransformArgument(*argument,token.style,token.options,language,arguments,rendered))return false;
        if(!Append(candidate,rendered))return false;cursor=token.end;
    }
    if(!Append(candidate,text?text+cursor:"",length-cursor))return false;
    output.swap(candidate);return true;
}
}

namespace Localization {
bool StringImplementation::ReadComposed(String& value,size_t form,std::string& output) {
    if(!form||form>value.m_Forms.size()){output.clear();return true;}
    if(!value.Compose(form)){output.clear();return !renderLimitExceeded;}
    size_t length=0;const char* text=value.m_Forms[form-1].GetComposedString().GetString(length);
    output.assign(text?text:"",length);return true;
}
ParameterArgument::ParameterArgument(const ParameterArgument& other) : m_value(other.m_value),m_str(),m_type(other.m_type) {
    if(other.m_str)m_str=std::make_shared<String>(*other.m_str);
}
ParameterArgument::ParameterArgument(const String& text) : m_value{},m_str(std::make_shared<String>(text)),m_type(ARGTYPE_STRING) {}
ParameterArgument::ParameterArgument(int value) : m_value{},m_str(),m_type(ARGTYPE_INT) {m_value.i=value;}
ParameterArgument::ParameterArgument(__int64 value) : m_value{},m_str(),m_type(ARGTYPE_INT64) {m_value.i64=value;}
ParameterArgument::ParameterArgument(float value) : m_value{},m_str(),m_type(ARGTYPE_FLOAT) {m_value.f=value;}
ParameterArgument::ParameterArgument(double value) : m_value{},m_str(),m_type(ARGTYPE_DOUBLE) {m_value.d=value;}

SingleFormString::SingleFormString() : m_BaseString(),m_ComposedString(),m_Plurality(0),m_Gender(0),m_Traits(),m_Parameters(),m_Composed(false),m_Parsed(false) {}
SingleFormString::SingleFormString(const SharedString& base,size_t plurality,Gender gender) : m_BaseString(base),m_ComposedString(),m_Plurality(plurality),m_Gender(gender),m_Traits(),m_Parameters(),m_Composed(false),m_Parsed(false) {}
SingleFormString::~SingleFormString() {}
SingleFormString& SingleFormString::operator=(const SingleFormString& other) {
    if(this!=&other){SingleFormString copy(other);m_BaseString=copy.m_BaseString;m_ComposedString=copy.m_ComposedString;m_Plurality=copy.m_Plurality;m_Gender=copy.m_Gender;
        m_Traits.swap(copy.m_Traits);m_Parameters.swap(copy.m_Parameters);m_Composed=copy.m_Composed;m_Parsed=copy.m_Parsed;}return *this;
}
const SharedString& SingleFormString::GetBaseString() const {return m_BaseString;}
const SharedString& SingleFormString::GetComposedString() const {return m_ComposedString;}
size_t SingleFormString::GetPlurality() const {return m_Plurality;}
void SingleFormString::SetGender(Gender gender) {m_Gender=gender;}
Gender SingleFormString::GetGender() const {return static_cast<Gender>(m_Gender);}
bool SingleFormString::HasTrait(const char* trait,size_t length) const {
    if(!trait&&length)return false;const std::string value(trait?trait:"",length);return std::find(m_Traits.begin(),m_Traits.end(),value)!=m_Traits.end();
}
bool SingleFormString::Parse() {
    if(m_Parsed)return true;size_t length=0;const char* text=m_BaseString.GetString(length);
    m_Parsed=ZeroSisLocalization::ValidateMessage(text,length,m_Parameters);return m_Parsed;
}
bool SingleFormString::Compose(const std::vector<ParameterArgument>& arguments) {
    Lock lock(ZeroSisLocalization::RuntimeMutex());if(!Parse())return false;
    size_t length=0;const char* text=m_BaseString.GetString(length);std::string output;
    if(!ZeroSisLocalization::RenderMessage(text,length,arguments,GetCurrentLanguage(),output))return false;
    m_ComposedString=SharedString(output.data(),output.size());m_Composed=true;return true;
}
String String::Empty;
String::String() : m_BaseString(),m_ComposedNullTerminated(),m_arguments(),m_Forms(),m_pkLanguage(nullptr) {}
String::String(const char* text) : String(text, text?static_cast<unsigned>(std::min<size_t>(std::strlen(text),UINT_MAX)):0) {
    if(text&&std::strlen(text)>UINT_MAX)throw std::length_error("Localization string exceeds SDK length");
}
String::String(const char* text,unsigned length) : String() {
    if(!text&&!length)return;
    m_BaseString=SharedString(text,length);if(!length)return;
    size_t start=0;
    for(size_t i=0;i<=length;++i)if(i==length||text[i]=='|') {
        SharedString form(m_BaseString);form.SetOffsetAndLength(start,i-start);m_Forms.emplace_back(form,1,GENDER_MASCULINE);start=i+1;
    }
}
String::String(const String& other) : m_BaseString(other.m_BaseString),m_ComposedNullTerminated(other.m_ComposedNullTerminated),m_arguments(other.m_arguments),m_Forms(other.m_Forms),m_pkLanguage(other.m_pkLanguage) {}
String::~String() {}
bool String::IsEmpty() const {return m_BaseString.GetLength()==0;}
String& String::operator=(const String& other) {
    if(this!=&other){String copy(other);m_BaseString=copy.m_BaseString;m_ComposedNullTerminated=copy.m_ComposedNullTerminated;
        m_arguments.swap(copy.m_arguments);m_Forms.swap(copy.m_Forms);m_pkLanguage=copy.m_pkLanguage;}return *this;
}
String& String::operator=(const char* text) {
    String candidate(text);m_BaseString=candidate.m_BaseString;m_ComposedNullTerminated=SharedString();m_Forms.swap(candidate.m_Forms);return *this;
}
const char* String::GetBaseString(size_t& bytes) const {return m_BaseString.GetString(bytes);}
const char* String::toUTF8(size_t& bytes,int form) {
    bytes=0;if(form<=0||!Compose(static_cast<size_t>(form)))return "";
    const char* text=m_Forms[static_cast<size_t>(form)-1].m_ComposedString.GetString(bytes);return text?text:"";
}
const char* String::toUTF8() {
    size_t bytes=0;const char* text=toUTF8(bytes,1);m_ComposedNullTerminated=SharedString(text,bytes);return m_ComposedNullTerminated.GetString(bytes);
}
Language* String::GetLanguage() const {return m_pkLanguage;}
bool String::SetLanguage(Language* language) {if(!ZeroSisLocalization::IsKnownLanguage(language))return false;m_pkLanguage=language;return true;}
size_t String::GetArgumentCount() const {return m_arguments.size();}
bool String::PushArgument(const char* text) {return PushArgument(String(text));}
bool String::PushArgument(const char* text,size_t length) {if(length>UINT_MAX||(!text&&length))return false;return PushArgument(String(text,static_cast<unsigned>(length)));}
bool String::PushArgument(int value) {return PushArgument(ParameterArgument(value));}
bool String::PushArgument(__int64 value) {return PushArgument(ParameterArgument(value));}
bool String::PushArgument(float value) {return PushArgument(ParameterArgument(value));}
bool String::PushArgument(double value) {return PushArgument(ParameterArgument(value));}
bool String::PushArgument(const String& text) {return PushArgument(ParameterArgument(text));}
bool String::PushArgument(const ParameterArgument& argument) {m_arguments.push_back(argument);return true;}
size_t String::GetNumForms() const {return m_Forms.size();}
bool String::HasForm(int form) const {return form>0&&static_cast<size_t>(form)<=m_Forms.size();}
size_t String::GetFormByPlurality(int plurality,int offset) const {
    if(plurality<0||offset<0)return 0;
    for(size_t i=0;i<m_Forms.size();++i)if(m_Forms[i].m_Plurality==static_cast<size_t>(plurality)){if(!offset)return i+1;--offset;}return 0;
}
size_t String::GetFormByGender(const char* selector,size_t length,int offset) const {
    (void)offset; // The original gender selector ignores this argument; plurality-only selection does not.
    if(!selector&&length)return 0;const std::string value(selector?selector:"",length);
    for(size_t i=0;i<m_Forms.size();++i)if(MatchesGender(m_Forms[i],value))return i+1;return 0;
}
size_t String::GetFormByPluralityAndGender(int plurality,const char* selector,size_t length,int offset) const {
    (void)offset;if(plurality<0||(!selector&&length))return 0;const std::string value(selector?selector:"",length);
    for(size_t i=0;i<m_Forms.size();++i)if(m_Forms[i].m_Plurality==static_cast<size_t>(plurality)&&MatchesGender(m_Forms[i],value))return i+1;return 0;
}
bool String::HasFormByPlurality(int plurality,int offset) const {return GetFormByPlurality(plurality,offset)!=0;}
bool String::HasFormByGender(const char* selector,size_t length,int offset) const {return GetFormByGender(selector,length,offset)!=0;}
bool String::HasFormByPluralityAndGender(int plurality,const char* selector,size_t length,int offset) const {return GetFormByPluralityAndGender(plurality,selector,length,offset)!=0;}
bool String::SetGender(size_t form,Gender gender) {if(!form||form>m_Forms.size()||gender<GENDER_NEUTER||gender>GENDER_FEMININE)return false;m_Forms[form-1].m_Gender=gender;return true;}
bool String::SetGender(Gender gender) {if(gender<GENDER_NEUTER||gender>GENDER_FEMININE)return false;for(auto& form:m_Forms)form.m_Gender=gender;return true;}
bool String::SetGender(size_t form,const char* text,size_t length) {
    if(!form||form>m_Forms.size()||(!text&&length))return false;auto values=Split(std::string(text?text:"",length),':');Gender gender=GENDER_NEUTER;
    GenderToken(values[0],gender);std::vector<std::string> traits(values.begin()+1,values.end());
    m_Forms[form-1].m_Gender=gender;m_Forms[form-1].m_Traits.swap(traits);return true;
}
bool String::SetGender(const char* text,size_t length) {
    if(!text&&length)return false;const auto values=Split(std::string(text?text:"",length),'|');
    for(size_t i=0;i<m_Forms.size();++i){if(values.size()!=1&&i>=values.size())break;const auto& value=values[values.size()==1?0:i];if(!SetGender(i+1,value.data(),value.size()))return false;}return true;
}
Gender String::GetGender(size_t form) const {return form&&form<=m_Forms.size()?static_cast<Gender>(m_Forms[form-1].m_Gender):GENDER_NEUTER;}
bool String::SetPlurality(size_t form,size_t plurality) {
    Lock lock(ZeroSisLocalization::RuntimeMutex());if(!form||form>m_Forms.size()||!plurality)return false;
    auto rule=(m_pkLanguage?*m_pkLanguage:GetCurrentLanguage()).GetPluralityRule();if(!rule||plurality>rule->GetMaxPluralForms())return false;
    m_Forms[form-1].m_Plurality=plurality;return true;
}
bool String::SetPlurality(size_t plurality) {
    Lock lock(ZeroSisLocalization::RuntimeMutex());
    auto rule=(m_pkLanguage?*m_pkLanguage:GetCurrentLanguage()).GetPluralityRule();if(!plurality||!rule||plurality>rule->GetMaxPluralForms())return false;
    for(auto& form:m_Forms)form.m_Plurality=plurality;return true;
}
bool String::SetPlurality(const char* text,size_t length) {
    if(!text&&length)return false;const auto values=Split(std::string(text?text:"",length),'|');
    for(size_t i=0;i<m_Forms.size();++i){if(values.size()!=1&&i>=values.size())break;const auto& value=values[values.size()==1?0:i];
        size_t end=0;while(end<value.size()&&Digit(value[end]))++end;size_t plurality=0;
        if(!Unsigned(value.substr(0,end),plurality)||!SetPlurality(i+1,plurality))return false;}return true;
}
size_t String::GetPlurality(size_t form) const {return form&&form<=m_Forms.size()?m_Forms[form-1].m_Plurality:0;}
bool String::Parse(size_t form) {return form&&form<=m_Forms.size()&&m_Forms[form-1].Parse();}
bool String::Compose(size_t form) {
    Lock lock(ZeroSisLocalization::RuntimeMutex());if(!Parse(form))return false;
    size_t length=0;auto& target=m_Forms[form-1];const char* text=target.m_BaseString.GetString(length);std::string output;
    if(!ZeroSisLocalization::RenderMessage(text,length,m_arguments,m_pkLanguage?*m_pkLanguage:GetCurrentLanguage(),output)) {
        target.m_Composed=false;LogError("Failed to compose localization string");return false;
    }
    target.m_ComposedString=SharedString(output.data(),output.size());target.m_Composed=true;return true;
}
}

std::ostream& operator<<(std::ostream& stream,Localization::String& value) {
    size_t length=0;const char* text=value.toUTF8(length);stream.write(text,static_cast<std::streamsize>(length));return stream;
}
