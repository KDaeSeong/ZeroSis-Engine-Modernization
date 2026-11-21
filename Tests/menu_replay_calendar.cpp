// SDK-free comparison with exact source extracts and controlled Lua goldens.
#include "MenuReplayCalendar.h"
#include <algorithm>
#include <cmath>
#include <cstdio>
#include <iostream>
#include <sstream>

using namespace ZeroSisHost;
static std::size_t checks=0;
static void Check(bool value,const char* message){++checks;if(!value)throw std::runtime_error(message);}
static std::string Token(const char* key,std::int64_t value){return std::string("{")+key+":"+std::to_string(value)+"}";}
static std::string Token(const char* key){return std::string("{")+key+"}";}
static std::wstring Wide(const std::string& text){return std::wstring(text.begin(),text.end());}

namespace StockSdkOracle {
// Database/provider stubs only. The enums and four calendar functions below
// are copied verbatim from the hash-bound SDK input by the Python driver.
using GameSpeedTypes=int;
class CvString final {
public:
    CvString()=default;
    CvString(const char* value):value_(value){}
    CvString(std::string value):value_(std::move(value)){}
    const char* GetCString()const{return value_.c_str();}
    static CvString format(const char* format,int value){char buffer[64]{};std::snprintf(buffer,sizeof(buffer),format,value);return CvString(buffer);}
    friend CvString operator+(const CvString& a,const CvString& b){return CvString(a.value_+b.value_);}
private:std::string value_;
};
static CvString GetLocalizedText(const char* key,int value){return CvString(Token(key,value));}
static CvString GetLocalizedText(const char* key){return CvString(Token(key));}
static CvString GetLocalizedText(const char* key,const char*,const char*){return CvString(Token(key));}
namespace Localization {
struct String final {std::string value;std::string toUTF8()const{return value;}};
static String Lookup(const char* key){return String{Token(key)};}
}
namespace Database {struct SingleResult final {std::string key;};}
struct DatabaseStub final {
    std::vector<std::string> months,seasons;
    int Count(const char* name)const{return static_cast<int>((std::string(name)=="Months"?months:seasons).size());}
    void SelectAt(Database::SingleResult& result,const char* table,int id)const {
        const auto& rows=std::string(table)=="Months"?months:seasons;
        result.key=rows.at(static_cast<std::size_t>(id));
    }
};
static DatabaseStub DB;
struct CvBaseInfo final {
    std::string description;
    // CvInfos.cpp CacheResults localizes Description before GetDescription.
    void CacheResult(const Database::SingleResult& result){description=GetLocalizedText(result.key.c_str()).GetCString();}
    const char* GetDescription()const{return description.c_str();}
};
struct GameTurnInfo final {int iMonthIncrement=0,iNumGameTurnsPerIncrement=0;};
struct CvGameSpeedInfo final {
    std::vector<GameTurnInfo> increments;
    int getNumTurnIncrements()const{return static_cast<int>(increments.size());}
    const GameTurnInfo& getGameTurnInfo(int index)const{return increments.at(static_cast<std::size_t>(index));}
};
struct GlobalsStub final {
    int weeksPerMonth=0,hiddenStartTurnOffset=0;std::map<int,CvGameSpeedInfo> speeds;
    CvGameSpeedInfo* getGameSpeedInfo(GameSpeedTypes speed){const auto found=speeds.find(speed);return found==speeds.end()?nullptr:&found->second;}
    int getWEEKS_PER_MONTHS()const{return weeksPerMonth;}
    int getHIDDEN_START_TURN_OFFSET()const{return hiddenStartTurnOffset;}
};
static GlobalsStub GC;
#define CvAssert(condition) do {if(!(condition))throw std::runtime_error("SDK oracle assertion");} while(false)
#include "sdk_calendar_oracle.inc"
#undef CvAssert
}

struct LuaCase final {int calendar,speed,startYear,turn;const char* expected;};
struct SdkCase final {int speed,startYear,turn;};
struct GraphCase final {int initial,final,minimum,maximum;std::array<int,5> labels;};
struct LocaleCase final {int calendar,speed,startYear,turn;const wchar_t* expected;};
#include "calendar_actual_goldens.inc"

static void Failures(const MenuReplayCalendarCatalog& actual){
    using Status=MenuReplayCalendarStatus;
    const auto require=[&](MenuReplayCalendarCatalog data,int calendar,int speed,int year,int turn,Status status){
        const auto value=MenuReplayCalendar(std::move(data)).ShortDate(calendar,speed,year,turn);
        Check(!value.available && value.text.empty() && !value.stockWeeksRepair && value.status==status,"unsupported date was manufactured or misclassified");
    };
    require(actual,-999,0,0,0,Status::UnknownCalendar);
    require(actual,0,-999,0,0,Status::UnknownGameSpeed);
    require(actual,0,0,0,-1,Status::InvalidTurn);require(actual,0,0,0,10000001,Status::InvalidTurn);
    auto changed=actual;changed.calendars[0]="CALENDAR_NEW_CUSTOM";require(changed,0,0,0,0,Status::UnsupportedCalendar);
    changed=actual;changed.gameSpeeds[0]="";require(changed,0,0,0,0,Status::InvalidCatalog);
    changed=actual;changed.monthNames.clear();require(changed,0,0,0,0,Status::InvalidCatalog);
    // Original Locale.Lookup returns a missing Description key itself.
    changed=actual;changed.monthNames[0]=L"TXT_KEY_MISSING";
    Check(MenuReplayCalendar(changed).ShortDate(5,0,0,0).text==L"TXT_KEY_MISSING, "+Wide(Token("TXT_KEY_TIME_AD",1)),"missing month key was hidden or replaced instead of shown raw");
    Check(MenuReplayCalendar(changed).ShortDate(0,0,-4000,1).available,"short DEFAULT unnecessarily required localized month names");
    changed=actual;changed.monthNames[0]=L"";require(changed,5,0,0,0,Status::InvalidCatalog);
    changed=actual;changed.monthNames[0]=std::wstring(L"a\0b",3);require(changed,5,0,0,0,Status::InvalidCatalog);
    changed=actual;changed.seasonNames.clear();require(changed,4,0,0,0,Status::InvalidCatalog);
    changed=actual;changed.speedTurns.erase(actual.gameSpeeds.at(0));require(changed,0,0,0,0,Status::InvalidCatalog);
    changed=actual;changed.speedTurns[actual.gameSpeeds.at(0)][0].turns=0;require(changed,0,0,0,0,Status::InvalidCatalog);
    changed=actual;changed.speedTurns[actual.gameSpeeds.at(0)][0].monthIncrement=-1;require(changed,0,0,0,0,Status::InvalidCatalog);
    changed=actual;changed.speedTurns[actual.gameSpeeds.at(0)][0].monthIncrement=9007199254740991LL;
    require(changed,0,0,0,2,Status::NumericOverflow);
    changed=actual;changed.speedTurns[actual.gameSpeeds.at(0)]={{1,9007199254740992LL}};require(changed,0,0,0,0,Status::InvalidCatalog);
    changed=actual;changed.speedTurns[actual.gameSpeeds.at(0)]={{0,9007199254740991LL}};
    Check(MenuReplayCalendar(changed).ShortDate(0,0,0,10000000).available,"safe large row was rejected");
    changed=actual;changed.speedTurns[actual.gameSpeeds.at(0)].clear();
    Check(MenuReplayCalendar(changed).ShortDate(0,0,0,12).text==Wide(Token("TXT_KEY_TIME_AD",1)),"stock empty-table last-increment fallback changed");
    changed=actual;changed.weeksPerMonth=0;require(changed,6,0,0,0,Status::InvalidCatalog);
    changed=actual;changed.hiddenStartTurnOffset=-1;require(changed,6,0,0,0,Status::InvalidTurn);
    changed=actual;changed.hiddenStartTurnOffset=std::numeric_limits<int>::max();require(changed,6,0,0,1,Status::NumericOverflow);
    require(actual,6,0,std::numeric_limits<int>::max(),0,Status::NumericOverflow);
    require(actual,6,0,std::numeric_limits<int>::min(),0,Status::NumericOverflow);
    changed=actual;changed.localizeNumber={};require(changed,0,0,0,0,Status::MissingLocalization);
    changed=actual;changed.localizeNumber=[](const char*,std::int64_t){return L"TXT_KEY_MISSING";};require(changed,0,0,0,0,Status::MissingLocalization);
    changed=actual;changed.localizeNumber=[](const char*,std::int64_t)->std::wstring{throw std::runtime_error("unavailable locale");};
    require(changed,6,0,0,0,Status::MissingLocalization);
    changed=actual;changed.localizeNumber=[](const char*,std::int64_t)->std::wstring{throw std::bad_alloc();};
    bool allocationFailure=false;try{MenuReplayCalendar(changed).ShortDate(0,0,0,0);}catch(const std::bad_alloc&){allocationFailure=true;}
    Check(allocationFailure,"allocation failure was concealed as unsupported metadata");
    // The retained parsed document is not changed and catalog ownership is by value.
    changed=actual;MenuReplayCalendar owned(changed);changed.calendars.clear();
    Check(owned.ShortDate(2,0,-1,1).available,"calendar retained a borrowed catalog");
    changed=actual;changed.calendars[73]=changed.calendars.at(2);changed.calendars.erase(2);
    changed.gameSpeeds[91]=changed.gameSpeeds.at(0);changed.gameSpeeds.erase(0);
    Check(MenuReplayCalendar(changed).ShortDate(73,91,-1,1).text==Wide(Token("TXT_KEY_TIME_AD",1)),"calendar enum or speed enum was hardcoded instead of using Type metadata");
}

int main(){
    try{
        const auto catalog=ActualCatalog();const MenuReplayCalendar calendar(catalog);
        for(const auto& test:LuaGoldens){const auto result=calendar.ShortDate(test.calendar,test.speed,test.startYear,test.turn);
            if(!result.available || result.text!=Wide(test.expected) || result.stockWeeksRepair){
                std::cerr<<"Lua golden mismatch "<<test.calendar<<" "<<test.speed<<" "<<test.startYear<<" "<<test.turn<<"\n";
                throw std::runtime_error("original Lua short calendar changed");}
            ++checks;
        }
        std::size_t actualWeeks=0,definitionVariations=0;
        ConfigureSdk(catalog);
        const auto compareWeeks=[&](const MenuReplayCalendarCatalog& data,const SdkCase& test){
            StockSdkOracle::GC.weeksPerMonth=data.weeksPerMonth;StockSdkOracle::GC.hiddenStartTurnOffset=data.hiddenStartTurnOffset;
            const auto result=MenuReplayCalendar(data).ShortDate(6,test.speed,test.startYear,test.turn);
            if(static_cast<std::int64_t>(test.turn)+data.hiddenStartTurnOffset<0){
                Check(!result.available && result.text.empty(),"negative SDK month index was manufactured");return;
            }
            StockSdkOracle::CvString expected;StockSdkOracle::CvGameTextMgr manager;
            manager.setDateStr(expected,test.turn,false,StockSdkOracle::CALENDAR_WEEKS,test.startYear,test.speed);
            Check(result.available && result.stockWeeksRepair && result.text==Wide(expected.GetCString()),"WEEKS differs from actual SDK source algorithm");
        };
        for(const auto& test:SdkGoldens){compareWeeks(catalog,test);++actualWeeks;}
        for(const int weeks:{1,2,5,7})for(const int offset:{-1,3,11,48}){
            auto data=catalog;data.weeksPerMonth=weeks;data.hiddenStartTurnOffset=offset;
            for(const auto& test:SdkGoldens){compareWeeks(data,test);++definitionVariations;}
        }
        // A BC fractional year uses signed truncation in the SDK, not Lua floor.
        Check(calendar.ShortDate(6,0,-1,4).text==Wide(Token("TXT_KEY_TIME_WEEK",1)+", "+Token("TXT_KEY_MONTH2")+", "+Token("TXT_KEY_TIME_AD",1)),"BC truncation/year-zero rule changed");
        Check(calendar.ShortDate(1,0,-1,2).text==Wide(Token("TXT_KEY_TIME_AD",1)),"replay BI_YEARLY was replaced by incompatible SDK arithmetic");
        std::size_t graphs=0;
        for(const auto& test:GraphGoldens){const auto domain=MenuReplayGraphDomain::Create(test.initial,test.final);
            Check(domain.minTurn==test.minimum && domain.maxTurn==test.maximum,"stock padded graph domain changed");
            for(std::size_t i=0;i<5;++i){const auto& tick=domain.ticks[i];
                Check(tick.visible==(test.labels[i]>=0) && (!tick.visible || tick.turn==test.labels[i]),"stock graph tick label changed");}
            Check(std::abs(domain.UnitX(test.minimum))<1e-14 && std::abs(domain.UnitX(test.maximum)-1)<1e-14,"shared graph mapping endpoints changed");
            Check(domain.UnitX(test.minimum-1)<0 && domain.UnitX(test.maximum+1)>1,"graph points were silently clamped");
            for(int turn=test.initial;turn<=std::min(test.final,test.initial+10);++turn)
                Check(std::abs(domain.UnitX(turn)-(static_cast<double>(turn-test.minimum)/(test.maximum-test.minimum)))<1e-14,"graph data x mapping differs from padded axis");
            ++graphs;
        }
        for(const auto& pair:std::vector<std::pair<int,int>>{{-1,0},{1,0},{0,10000001},{0,1000001}}){
            bool rejected=false;try{MenuReplayGraphDomain::Create(pair.first,pair.second);}catch(const std::invalid_argument&){rejected=true;}
            Check(rejected,"invalid graph bounds accepted");
        }
        Failures(catalog);
        const auto actualLocale=ActualLocaleCatalog();std::size_t rawSeasonSamples=0;
        for(const auto& sample:ActualLocaleSamples){
            const auto value=MenuReplayCalendar(actualLocale).ShortDate(sample.calendar,sample.speed,sample.startYear,sample.turn);
            Check(sample.expected[0] && value.available && value.text==sample.expected,"actual Korean template/name composition differs from source oracle");
            if(sample.calendar==4){
                Check(value.text.compare(0,15,L"TXT_KEY_SEASON_")==0,"missing actual season localization did not show the original raw key");++rawSeasonSamples;}
        }
        Check(rawSeasonSamples==1,"actual season sample roster changed");
        Check(MenuReplayCalendar(actualLocale).ShortDate(6,0,-4000,4).text==ActualWeeksSample(),"actual Korean WEEKS composition differs from SDK repair");
        std::cout<<"{\"status\":\"PASS_SDK_FREE_CALENDAR\",\"checks\":"<<checks
            <<",\"original_lua_goldens\":"<<(sizeof(LuaGoldens)/sizeof(LuaGoldens[0]))
            <<",\"actual_sdk_weeks_goldens\":"<<actualWeeks<<",\"sdk_definition_variations\":"<<definitionVariations
            <<",\"original_graph_domains\":"<<graphs<<",\"actual_raw_season_key_samples\":"<<rawSeasonSamples
            <<",\"native_host_sdk_window_gpu_executed\":false}\n";
        return 0;
    }catch(const std::exception& error){std::cerr<<error.what()<<"\n";return 1;}
}
