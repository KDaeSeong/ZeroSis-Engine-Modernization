#define CvLocalizationAPI __declspec(dllexport)
#include "SdkLocalizationRuntime.h"
#include <map>
#include <set>
#include <limits>
#include <malloc.h>
#include <unicode/uclean.h>
#include <unicode/udata.h>
#include <unicode/ucol.h>
#include <unicode/ustring.h>

namespace {
using Localization::Language;
using Localization::ParameterTransforms;
using Localization::IPluralityRule;
using Lock = std::lock_guard<std::recursive_mutex>;

// Integer rules use the original component's observed arithmetic, including
// its treatment of negative values and whole-number teen exceptions.
class PluralRule final : public IPluralityRule {
    unsigned m_id;
public:
    explicit PluralRule(unsigned id) : m_id(id) {}
    unsigned GetMaxPluralForms() const override {
        const unsigned counts[] = {0,1,2,2,3,3,3,3,3,3,3,4,5,6,4,3,2};
        return m_id < sizeof(counts)/sizeof(counts[0]) ? counts[m_id] : 0;
    }
    unsigned GetPluralForm(int n) const override {
        const int a = n % 10, b = n % 100;
        switch (m_id) {
        case 1: return 1;
        case 2: return n == 1 ? 1 : 2;
        case 3: return n == 0 || n == 1 ? 1 : 2;
        case 4: return n == 0 ? 1 : a == 1 && n != 11 ? 2 : 3;
        case 5: return n == 1 ? 1 : n == 2 ? 2 : 3;
        case 6: return n == 1 ? 1 : b < 20 ? 2 : 3;
        case 7: return a == 1 ? 1 : a == 0 ? 2 : 3;
        case 8: return a == 1 && n != 11 ? 1 : a >= 2 && a <= 4 && !(n >= 12 && n <= 14) ? 2 : 3;
        case 9: return n == 1 ? 1 : n >= 2 && n <= 4 ? 2 : 3;
        case 10: return n == 1 ? 1 : a >= 2 && a <= 4 && !(n >= 12 && n <= 14) ? 2 : 3;
        case 11: return a == 1 ? 1 : a == 2 ? 2 : a == 3 || a == 4 ? 3 : 4;
        case 12: return n == 1 ? 1 : n == 2 ? 2 : n >= 3 && n <= 6 ? 3 : n >= 7 && n <= 10 ? 4 : 5;
        case 13: return n == 0 ? 6 : n == 1 ? 1 : n == 2 ? 2 : b >= 3 && b <= 10 ? 3 : b >= 11 ? 4 : 5;
        case 14: return n == 1 ? 1 : b >= 11 && b <= 19 ? 3 : b < 11 ? 2 : 4;
        case 15: return a == 1 ? 1 : a == 2 ? 2 : 3;
        case 16: return a == 1 && n != 11 ? 1 : 2;
        default: return 0;
        }
    }
};
struct LanguageState {
    std::string locale, type;
    IPluralityRule* rule = nullptr; // Custom SDK rules are borrowed, never deleted through their non-virtual base.
    std::shared_ptr<PluralRule> ownedRule;
    std::unique_ptr<ParameterTransforms> transforms;
};
struct TextEntry { std::string text, gender, plurality; bool nullText = false; };
struct CatalogEntry {
    Localization::StringDictionary::Language view;
    std::string type, displayName;
    int rule;
    std::map<std::string, TextEntry> strings;
};
struct DictionaryState {
    Database::Connection* connection = nullptr; // Borrowed until ShutdownDictionary; caller serializes all other DB access.
    std::string table;
    bool disableFallback = false;
    unsigned current = 0;
    std::vector<std::shared_ptr<CatalogEntry>> languages;
};
struct AlignedDelete { void operator()(void* p) const { _aligned_free(p); } };
struct Runtime {
    std::recursive_mutex mutex;
    std::map<const Language*, std::shared_ptr<LanguageState>> languageStates;
    std::map<const ParameterTransforms*, std::string> transformLocales;
    std::unique_ptr<Language> currentLanguage;
    DictionaryState dictionary;
    Localization::StringDictionary dictionaryView;
    std::unique_ptr<Localization::ILocalizationLogger> logger;
    std::unique_ptr<void, AlignedDelete> data;
    bool ready = false;
    ~Runtime() {
        dictionary.languages.clear();
        currentLanguage.reset();
        if (ready) u_cleanup();
    }
};
Runtime runtime;

std::shared_ptr<LanguageState> State(const Language* language) {
    const auto found = runtime.languageStates.find(language);
    if (found == runtime.languageStates.end()) throw std::invalid_argument("Unknown Localization language");
    return found->second;
}
std::string ShortType(const std::string& locale) {
    const size_t end = locale.find_first_of("_-@");
    return locale.substr(0, end);
}
std::shared_ptr<LanguageState> MakeState(const char* type, IPluralityRule* rule) {
    if (!type || !*type) throw std::invalid_argument("Empty Localization locale");
    auto state = std::make_shared<LanguageState>();
    state->locale = type; state->type = ShortType(state->locale); state->rule = rule;
    state->transforms.reset(new ParameterTransforms(type));
    return state;
}
std::shared_ptr<LanguageState> MakeCatalogState(const CatalogEntry& entry) {
    auto rule = entry.rule >= 1 && entry.rule <= 16 ? std::make_shared<PluralRule>(static_cast<unsigned>(entry.rule)) : nullptr;
    auto state = MakeState(entry.type.c_str(), rule.get()); state->ownedRule = rule; return state;
}
void EnsureCurrent() {
    if (!runtime.currentLanguage) {
        runtime.currentLanguage.reset(new Language("en_US", nullptr));
        auto state = State(runtime.currentLanguage.get());
        state->ownedRule = std::make_shared<PluralRule>(2); state->rule = state->ownedRule.get();
    }
}
const CatalogEntry* Catalog(const Localization::StringDictionary::Language* view) {
    for (const auto& entry : runtime.dictionary.languages) if (&entry->view == view) return entry.get();
    return nullptr;
}
bool ReadCompleted(const Database::Connection& db) {
    // SDK Results::Step returns false for both end-of-results and execution
    // failure. Inspect the public connection status before publishing a cache.
    const int status=db.ErrorCode();return status==0 || status==101; // SQLITE_OK / SQLITE_DONE
}
bool FillStrings(DictionaryState& dictionary) {
    if (!dictionary.connection) return false;
    std::set<std::string> keys;
    Database::Results tags;
    if (!dictionary.connection->Execute(tags, "SELECT DISTINCT Tag FROM LocalizedText")) return false;
    while (tags.Step()) {
        const char* key = tags.GetText(0); if (key) keys.insert(key);
    }
    if(!ReadCompleted(*dictionary.connection))return false;
    for (auto& language : dictionary.languages) {
        language->strings.clear();
        if (dictionary.disableFallback) for (const auto& key : keys) language->strings.emplace(key, TextEntry{key,"","",false});
        Database::Results results;
        const char* sql = dictionary.disableFallback ?
            "SELECT Tag,Text,Gender,Plurality FROM LocalizedText WHERE Language=?1 ORDER BY rowid" :
            "SELECT T.Tag,T.Text,T.Gender,T.Plurality FROM LocalizedText AS T LEFT JOIN "
            "(SELECT Language,Priority FROM LanguagePriorities WHERE LanguageSet=?1) AS P ON T.Language=P.Language "
            "ORDER BY P.Priority DESC,T.rowid";
        if (!dictionary.connection->Execute(results, sql) || !results.Bind(1, language->type.c_str())) return false;
        std::set<std::string> seen;
        while (results.Step()) {
            const char* key = results.GetText(0);
            if (!key || !seen.insert(key).second) continue;
            TextEntry value;
            value.nullText = results.ColumnType(1) == Database::COLTYPE_NULL;
            const char* text = results.GetText(1); if (text) value.text = text;
            const char* gender = results.GetText(2); if (gender) value.gender = gender;
            const char* plurality = results.GetText(3); if (plurality) value.plurality = plurality;
            language->strings[key] = std::move(value);
        }
        if(!ReadCompleted(*dictionary.connection))return false;
    }
    return true;
}
bool PrepareDictionary(Database::Connection& db, const char* table, const char* type, bool disable, DictionaryState& output) {
    if (!table || !*table || !type || !*type) return false;
    std::string quoted = "\"";
    for (const char* p = table; *p; ++p) { if (*p == '"') quoted += '"'; quoted += *p; }
    quoted += '"';
    Database::Results rows;
    const std::string query = "SELECT Type,Name,PluralRule FROM " + quoted + " ORDER BY ID";
    if (!db.Execute(rows, query.c_str())) return false;
    DictionaryState candidate; candidate.connection = &db; candidate.table = table; candidate.disableFallback = disable;
    bool selected = false;
    while (rows.Step()) {
        const char* name = rows.GetText(0); if (!name || !*name) return false;
        auto entry = std::make_shared<CatalogEntry>(); entry->type = name;
        const char* display = rows.GetText(1); if (display) entry->displayName = display;
        entry->rule = rows.GetInt(2);
        if (candidate.languages.size() >= (std::numeric_limits<unsigned>::max)()) return false;
        if (entry->type == type) { candidate.current = static_cast<unsigned>(candidate.languages.size()); selected = true; }
        candidate.languages.push_back(std::move(entry));
    }
    if (!ReadCompleted(db) || !selected || !FillStrings(candidate)) return false;
    output = std::move(candidate); return true;
}
bool SelectLanguage(unsigned index) {
    if (index >= runtime.dictionary.languages.size()) return false;
    auto candidate = MakeCatalogState(*runtime.dictionary.languages[index]);
    EnsureCurrent(); runtime.languageStates.at(runtime.currentLanguage.get()).swap(candidate);
    runtime.dictionary.current = index; return true;
}
bool LookupIndex(const char* key, unsigned length, unsigned index, Localization::String& output) {
    if ((!key && length) || index >= runtime.dictionary.languages.size()) return false;
    const auto& entries = runtime.dictionary.languages[index]->strings;
    auto found = entries.find(std::string(key ? key : "", length));
    if (found == entries.end()) return false;
    const TextEntry& entry = found->second;
    Localization::String value(entry.nullText ? nullptr : entry.text.c_str());
    if (!entry.gender.empty() && !value.SetGender(entry.gender.data(), entry.gender.size())) return false;
    if (!entry.plurality.empty()) value.SetPlurality(entry.plurality.data(), entry.plurality.size());
    output = value; return true;
}
bool HasKeyIndex(const char* key, unsigned length, unsigned index) {
    if ((!key && length) || length > INT_MAX || index >= runtime.dictionary.languages.size() || !runtime.dictionary.connection) return false;
    Database::Results row;
    const char* query = runtime.dictionary.disableFallback ?
        "SELECT 1 FROM LocalizedText WHERE Tag=?1 AND Language=?2 LIMIT 1" : "SELECT 1 FROM LocalizedText WHERE Tag=?1 LIMIT 1";
    if (!runtime.dictionary.connection->Execute(row, query) || !row.Bind(1, key ? key : "", static_cast<int>(length))) return false;
    if (runtime.dictionary.disableFallback && !row.Bind(2, runtime.dictionary.languages[index]->type.c_str())) return false;
    return row.Step();
}
unsigned CStringLength(const char* text) {
    const size_t length = text ? std::strlen(text) : 0;
    if (length > UINT_MAX) throw std::length_error("Localization key exceeds SDK length");
    return static_cast<unsigned>(length);
}
std::unique_ptr<void, AlignedDelete> ReadData(const wchar_t* path) {
    if (!path || !*path) return {};
    HANDLE file = CreateFileW(path, GENERIC_READ, FILE_SHARE_READ, nullptr, OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, nullptr);
    if (file == INVALID_HANDLE_VALUE) return {};
    struct FileCloser { HANDLE handle; ~FileCloser() { CloseHandle(handle); } } closer{file};
    LARGE_INTEGER length;
    if (!GetFileSizeEx(file, &length) || length.QuadPart < 32 || length.QuadPart > 128*1024*1024) return {};
    std::unique_ptr<void, AlignedDelete> data(_aligned_malloc(static_cast<size_t>(length.QuadPart),16));
    if (!data) throw std::bad_alloc();
    DWORD actual = 0;
    if (!ReadFile(file,data.get(),static_cast<DWORD>(length.QuadPart),&actual,nullptr) || actual != static_cast<DWORD>(length.QuadPart)) return {};
    const auto bytes = static_cast<const unsigned char*>(data.get());
    if (bytes[2] != 0xda || bytes[3] != 0x27 || std::memcmp(bytes+12,"CmnD",4) != 0) return {};
    return data;
}
}

namespace ZeroSisLocalization {
std::recursive_mutex& RuntimeMutex() { return runtime.mutex; }
bool IcuReady() { return runtime.ready; }
bool IsKnownLanguage(const Localization::Language* language) { Lock lock(runtime.mutex); return !language || runtime.languageStates.count(language) != 0; }
const char* LocaleOf(const Localization::Language& language) { return State(&language)->locale.c_str(); }
}

namespace Localization {
Language::Language(const char* type, IPluralityRule* rule) { Lock lock(runtime.mutex); runtime.languageStates.emplace(this,MakeState(type,rule)); }
Language::Language(const Language& other) {
    Lock lock(runtime.mutex); auto old = State(&other); auto copy = MakeState(old->locale.c_str(),old->rule);
    copy->ownedRule = old->ownedRule; runtime.languageStates.emplace(this,std::move(copy));
}
Language::~Language() { Lock lock(runtime.mutex); runtime.languageStates.erase(this); }
const char* Language::GetType() const { Lock lock(runtime.mutex); return State(this)->type.c_str(); }
unsigned Language::GetPluralForm(int count) const { Lock lock(runtime.mutex); auto state = State(this); return state->rule ? state->rule->GetPluralForm(count) : 0; }
IPluralityRule* Language::GetPluralityRule() const { Lock lock(runtime.mutex); return State(this)->rule; }
void Language::SetPluralityRule(IPluralityRule* rule) { Lock lock(runtime.mutex); auto state=State(this); if(rule!=state->rule) {state->rule=rule;state->ownedRule.reset();} }
const ParameterTransforms& Language::GetParameterTransforms() const { Lock lock(runtime.mutex); return *State(this)->transforms; }
bool Language::Compare(const char* first,size_t firstLength,const char* second,size_t secondLength,int& result) const {
    Lock lock(runtime.mutex);
    if (!runtime.ready || (!first && firstLength) || (!second && secondLength) || firstLength > INT_MAX || secondLength > INT_MAX) return false;
    UErrorCode status=U_ZERO_ERROR;
    std::unique_ptr<UCollator,decltype(&ucol_close)> collator(ucol_open(State(this)->locale.c_str(),&status),&ucol_close);
    if(U_FAILURE(status)||!collator)return false;
    if(firstLength>=INT_MAX||secondLength>=INT_MAX)return false;
    std::vector<UChar> first16(firstLength+1),second16(secondLength+1);int32_t firstCount=0,secondCount=0;
    u_strFromUTF8(first16.data(),static_cast<int32_t>(first16.size()),&firstCount,first?first:"",static_cast<int32_t>(firstLength),&status);
    if(U_FAILURE(status))return false;
    u_strFromUTF8(second16.data(),static_cast<int32_t>(second16.size()),&secondCount,second?second:"",static_cast<int32_t>(secondLength),&status);
    if(U_FAILURE(status))return false;
    result=static_cast<int>(ucol_strcoll(collator.get(),first16.data(),firstCount,second16.data(),secondCount));return true;
}
ParameterTransforms::ParameterTransforms(const char* type) { Lock lock(runtime.mutex); if(!type)throw std::invalid_argument("Null transform locale");runtime.transformLocales.emplace(this,type); }
ParameterTransforms::~ParameterTransforms() { Lock lock(runtime.mutex);runtime.transformLocales.erase(this); }

bool Initialize(const wchar_t* dataPath,Database::Connection& db,const char* table,const char* type,bool disableFallback) {
    Lock lock(runtime.mutex); if(runtime.ready)return false;
    DictionaryState dictionary; if(!PrepareDictionary(db,table,type,disableFallback,dictionary))return false;
    auto state=MakeCatalogState(*dictionary.languages[dictionary.current]);EnsureCurrent();
    auto data=ReadData(dataPath);if(!data)return false;
    UErrorCode status=U_ZERO_ERROR;udata_setFileAccess(UDATA_NO_FILES,&status);
    if(U_SUCCESS(status))udata_setCommonData(data.get(),&status);
    if(U_SUCCESS(status))u_init(&status);
    if(U_FAILURE(status)){u_cleanup();return false;}
    runtime.data=std::move(data);runtime.ready=true;
    runtime.dictionary=std::move(dictionary);runtime.languageStates.at(runtime.currentLanguage.get()).swap(state);return true;
}
bool Shutdown() {
    Lock lock(runtime.mutex);ShutdownDictionary();
    if(runtime.ready){u_cleanup();runtime.ready=false;}runtime.data.reset();runtime.logger.reset();return true;
}
bool InitializeDictionary(Database::Connection& db,const char* table,const char* type,bool disableFallback) {
    Lock lock(runtime.mutex);DictionaryState candidate;if(!PrepareDictionary(db,table,type,disableFallback,candidate))return false;
    auto state=MakeCatalogState(*candidate.languages[candidate.current]);EnsureCurrent();
    runtime.dictionary=std::move(candidate);runtime.languageStates.at(runtime.currentLanguage.get()).swap(state);return true;
}
bool ShutdownDictionary() { Lock lock(runtime.mutex);runtime.dictionary=DictionaryState();return true; }
bool SetCurrentLanguage(const char* type) { return runtime.dictionaryView.SetCurrentLanguage(type); }
const Language& GetCurrentLanguage() { Lock lock(runtime.mutex);EnsureCurrent();return *runtime.currentLanguage; }
const StringDictionary& GetStringDictionary() { return runtime.dictionaryView; }
String Lookup(const char* key) { return GetStringDictionary().Lookup(key); }
void SetLogger(ILocalizationLogger* logger) { Lock lock(runtime.mutex);if(runtime.logger.get()!=logger)runtime.logger.reset(logger); }
ILocalizationLogger* GetLogger() { Lock lock(runtime.mutex);return runtime.logger.get(); }
void LogMessage(const char* message) { Lock lock(runtime.mutex);if(runtime.logger)runtime.logger->Log(message?message:"",ILocalizationLogger::TYPE_MESSAGE); }
void LogWarning(const char* message) { Lock lock(runtime.mutex);if(runtime.logger)runtime.logger->Log(message?message:"",ILocalizationLogger::TYPE_WARNING); }
void LogError(const char* message) { Lock lock(runtime.mutex);if(runtime.logger)runtime.logger->Log(message?message:"",ILocalizationLogger::TYPE_ERROR); }

String StringDictionary::Lookup(const char* key) const { return Lookup(key,CStringLength(key)); }
String StringDictionary::Lookup(const char* key,unsigned length) const { Lock lock(runtime.mutex);return LookupLanguage(key,length,runtime.dictionary.current); }
bool StringDictionary::TryLookup(const char* key,unsigned length,String& output) const { Lock lock(runtime.mutex);return LookupIndex(key,length,runtime.dictionary.current,output); }
String StringDictionary::LookupLanguage(const char* key,unsigned index) const { return LookupLanguage(key,CStringLength(key),index); }
String StringDictionary::LookupLanguage(const char* key,unsigned length,unsigned index) const {
    Lock lock(runtime.mutex);String output;if(LookupIndex(key,length,index,output))return output;return String(key,length);
}
bool StringDictionary::TryLookupLanguage(const char* key,unsigned length,unsigned index,String& output) const { Lock lock(runtime.mutex);return LookupIndex(key,length,index,output); }
bool StringDictionary::HasKey(const char* key,unsigned length) const { Lock lock(runtime.mutex);return HasKeyIndex(key,length,runtime.dictionary.current); }
bool StringDictionary::HasKey(const char* key,unsigned length,unsigned index) const { Lock lock(runtime.mutex);return HasKeyIndex(key,length,index); }
unsigned StringDictionary::GetCurrentLanguageIndex() const { Lock lock(runtime.mutex);return runtime.dictionary.current; }
bool StringDictionary::SetCurrentLanguage(unsigned index) { Lock lock(runtime.mutex);return SelectLanguage(index); }
bool StringDictionary::SetCurrentLanguage(const char* type) {
    Lock lock(runtime.mutex);if(!type)return false;
    for(size_t i=0;i<runtime.dictionary.languages.size();++i)if(runtime.dictionary.languages[i]->type==type)return SelectLanguage(static_cast<unsigned>(i));
    return false;
}
size_t StringDictionary::GetLanguageCount() const { Lock lock(runtime.mutex);return runtime.dictionary.languages.size(); }
const char* StringDictionary::GetLanguageType(unsigned index) const { Lock lock(runtime.mutex);return index<runtime.dictionary.languages.size()?runtime.dictionary.languages[index]->type.c_str():nullptr; }
const char* StringDictionary::GetLanguageDisplayName(unsigned index) const { Lock lock(runtime.mutex);return index<runtime.dictionary.languages.size()?runtime.dictionary.languages[index]->displayName.c_str():nullptr; }
const StringDictionary::Language& StringDictionary::GetLanguage(unsigned index) const { Lock lock(runtime.mutex);if(index>=runtime.dictionary.languages.size())throw std::out_of_range("Localization language index");return runtime.dictionary.languages[index]->view; }
void StringDictionary::NotifyDatabaseUpdated() const {
    Lock lock(runtime.mutex);if(!runtime.dictionary.connection)return;
    DictionaryState candidate;candidate.connection=runtime.dictionary.connection;candidate.table=runtime.dictionary.table;
    candidate.disableFallback=runtime.dictionary.disableFallback;candidate.current=runtime.dictionary.current;
    for(const auto& entry:runtime.dictionary.languages) {
        auto copy=std::make_shared<CatalogEntry>();copy->type=entry->type;copy->displayName=entry->displayName;copy->rule=entry->rule;
        candidate.languages.push_back(std::move(copy));
    }
    if(!FillStrings(candidate)){LogError("Localization dictionary refresh failed; previous snapshot retained");return;}
    for(size_t i=0;i<candidate.languages.size();++i)runtime.dictionary.languages[i]->strings.swap(candidate.languages[i]->strings);
}
const char* StringDictionary::Language::GetType() const { Lock lock(runtime.mutex);const auto entry=Catalog(this);return entry?entry->type.c_str():nullptr; }
const char* StringDictionary::Language::GetDisplayName() const { Lock lock(runtime.mutex);const auto entry=Catalog(this);return entry?entry->displayName.c_str():nullptr; }
int StringDictionary::Language::GetPluralityRule() const { Lock lock(runtime.mutex);const auto entry=Catalog(this);return entry?entry->rule:0; }
}
