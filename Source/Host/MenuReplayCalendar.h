#pragma once
#include <array>
#include <cstdint>
#include <functional>
#include <limits>
#include <map>
#include <new>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

namespace ZeroSisHost {
struct MenuReplayCalendarIncrement final {std::int64_t monthIncrement=0,turns=0;};
struct MenuReplayCalendarCatalog final {
    std::map<int,std::string> calendars,gameSpeeds;
    std::map<std::string,std::vector<MenuReplayCalendarIncrement>> speedTurns;
    std::vector<std::wstring> monthNames,seasonNames;
    int weeksPerMonth=0,hiddenStartTurnOffset=0;
    std::function<std::wstring(const char*,std::int64_t)> localizeNumber;
};
enum class MenuReplayCalendarStatus {
    Available,UnknownCalendar,UnknownGameSpeed,UnsupportedCalendar,InvalidTurn,
    InvalidCatalog,NumericOverflow,MissingLocalization
};
struct MenuReplayCalendarResult final {
    bool available=false;std::wstring text;
    MenuReplayCalendarStatus status=MenuReplayCalendarStatus::InvalidCatalog;
    bool stockWeeksRepair=false;
};

// ReplayViewer.lua calls the short formats from GameCalendarUtilities.lua.
// Its six working formats are retained, including BI_YEARLY's floor(turn/2).
// Only broken WEEKS uses CvGameTextMgr::setDateStr/getTurnMonthForGame instead.
class MenuReplayCalendar final {
public:
    explicit MenuReplayCalendar(MenuReplayCalendarCatalog catalog):catalog_(std::move(catalog)){}
    MenuReplayCalendarResult ShortDate(int calendarId,int speedId,int startYear,int turn) const {
        if(turn<0 || turn>10000000)return Failure(MenuReplayCalendarStatus::InvalidTurn);
        const auto calendar=catalog_.calendars.find(calendarId);
        if(calendar==catalog_.calendars.end())return Failure(MenuReplayCalendarStatus::UnknownCalendar);
        const auto speed=catalog_.gameSpeeds.find(speedId);
        if(speed==catalog_.gameSpeeds.end())return Failure(MenuReplayCalendarStatus::UnknownGameSpeed);
        if(calendarId<0 || speedId<0 || speed->second.empty())return Failure(MenuReplayCalendarStatus::InvalidCatalog);
        const std::string& type=calendar->second;
        std::int64_t year=startYear;std::wstring prefix;
        bool weeksRepair=false;
        if(type=="CALENDAR_DEFAULT"){
            // The stock short DEFAULT format needs the month count only.
            if(!CountValid(catalog_.monthNames))return Failure(MenuReplayCalendarStatus::InvalidCatalog);
            const auto rows=catalog_.speedTurns.find(speed->second);
            if(rows==catalog_.speedTurns.end() || rows->second.size()>4096)return Failure(MenuReplayCalendarStatus::InvalidCatalog);
            for(const auto& row:rows->second)if(row.monthIncrement<0 || row.monthIncrement>MaxExact() || row.turns<=0 || row.turns>MaxExact())
                return Failure(MenuReplayCalendarStatus::InvalidCatalog);
            std::int64_t turnCount=0,turnMonth=0,lastMonthIncrement=1;
            for(const auto& row:rows->second){
                lastMonthIncrement=row.monthIncrement;
                if(row.turns>MaxExact()-turnCount)return Failure(MenuReplayCalendarStatus::NumericOverflow);
                const std::int64_t amount=turn>turnCount+row.turns?row.turns:turn-turnCount;
                if(!AddProduct(turnMonth,row.monthIncrement,amount))return Failure(MenuReplayCalendarStatus::NumericOverflow);
                turnCount+=amount;
                if(turnCount==turn)break;
            }
            if(turn>turnCount && !AddProduct(turnMonth,lastMonthIncrement,turn-turnCount))return Failure(MenuReplayCalendarStatus::NumericOverflow);
            if(!AddExact(year,turnMonth/static_cast<std::int64_t>(catalog_.monthNames.size())))return Failure(MenuReplayCalendarStatus::NumericOverflow);
        }else if(type=="CALENDAR_YEARS"){
            year+=turn;
        }else if(type=="CALENDAR_BI_YEARLY"){
            year+=turn/2;
        }else if(type=="CALENDAR_TURNS"){
            return Localized("TXT_KEY_TIME_TURN",static_cast<std::int64_t>(turn)+1);
        }else if(type=="CALENDAR_SEASONS" || type=="CALENDAR_MONTHS"){
            const auto& names=type=="CALENDAR_SEASONS"?catalog_.seasonNames:catalog_.monthNames;
            if(!NamesValid(names))return Failure(MenuReplayCalendarStatus::InvalidCatalog);
            const auto count=static_cast<std::int64_t>(names.size());
            prefix=names[static_cast<std::size_t>(turn%count)]+L", ";year+=turn/count;
        }else if(type=="CALENDAR_WEEKS"){
            if(!NamesValid(catalog_.monthNames) || catalog_.weeksPerMonth<=0)return Failure(MenuReplayCalendarStatus::InvalidCatalog);
            const std::int64_t effectiveTurn=static_cast<std::int64_t>(turn)+catalog_.hiddenStartTurnOffset;
            if(effectiveTurn<0)return Failure(MenuReplayCalendarStatus::InvalidTurn);
            const auto months=static_cast<std::int64_t>(catalog_.monthNames.size());
            const std::int64_t startMonth=static_cast<std::int64_t>(startYear)*months;
            const std::int64_t turnMonth=startMonth+effectiveTurn/catalog_.weeksPerMonth;
            // These are int intermediates in the original SDK. Do not invoke its
            // undefined overflow behavior, or replace an unavailable date.
            if(!FitsSdkInt(effectiveTurn) || !FitsSdkInt(startMonth) || !FitsSdkInt(turnMonth))return Failure(MenuReplayCalendarStatus::NumericOverflow);
            year=turnMonth/months; // SDK signed division truncates toward zero.
            if(year==(std::numeric_limits<int>::min)())return Failure(MenuReplayCalendarStatus::NumericOverflow);
            const auto week=Localized("TXT_KEY_TIME_WEEK",effectiveTurn%catalog_.weeksPerMonth+1);
            if(!week.available)return week;
            const auto index=static_cast<std::size_t>((effectiveTurn/catalog_.weeksPerMonth)%months);
            prefix=week.text+L", "+catalog_.monthNames[index]+L", ";weeksRepair=true;
        }else return Failure(MenuReplayCalendarStatus::UnsupportedCalendar);
        auto result=Localized(year<0?"TXT_KEY_TIME_BC":"TXT_KEY_TIME_AD",year<0?-year:(year==0?1:year));
        if(result.available){result.text=prefix+result.text;result.stockWeeksRepair=weeksRepair;}
        return result;
    }
private:
    static std::int64_t MaxExact() noexcept{return 9007199254740991LL;}
    static bool FitsSdkInt(std::int64_t value) noexcept {
        return value>=(std::numeric_limits<int>::min)() && value<=(std::numeric_limits<int>::max)();
    }
    static bool AddExact(std::int64_t& value,std::int64_t amount) noexcept {
        if(amount<0 || amount>MaxExact() || value>MaxExact()-amount)return false;
        value+=amount;return true;
    }
    static bool AddProduct(std::int64_t& value,std::int64_t increment,std::int64_t amount) noexcept {
        if(amount<0 || (amount && increment>MaxExact()/amount))return false;
        return AddExact(value,increment*amount);
    }
    static bool TextValid(const std::wstring& text) noexcept {
        return !text.empty() && text.size()<=4096 && text.find(L'\0')==std::wstring::npos && text.compare(0,8,L"TXT_KEY_")!=0;
    }
    // Month/season names are the stock Locale.Lookup(Description) result. The
    // retail Lookup binding has no presence test and the original component
    // returns a missing key itself, so a raw TXT_KEY_ name is the original text
    // (stock Seasons keys have no text rows). Empty or NUL text stays invalid.
    static bool NameValid(const std::wstring& text) noexcept {
        return !text.empty() && text.size()<=4096 && text.find(L'\0')==std::wstring::npos;
    }
    static bool CountValid(const std::vector<std::wstring>& names) noexcept {return !names.empty() && names.size()<=1024;}
    static bool NamesValid(const std::vector<std::wstring>& names) noexcept {
        if(!CountValid(names))return false;
        for(const auto& name:names)if(!NameValid(name))return false;return true;
    }
    static MenuReplayCalendarResult Failure(MenuReplayCalendarStatus status) {
        MenuReplayCalendarResult result;result.status=status;return result;
    }
    MenuReplayCalendarResult Localized(const char* key,std::int64_t number) const {
        if(!catalog_.localizeNumber)return Failure(MenuReplayCalendarStatus::MissingLocalization);
        MenuReplayCalendarResult result;
        try{result.text=catalog_.localizeNumber(key,number);}
        catch(const std::bad_alloc&){throw;}
        catch(const std::exception&){return Failure(MenuReplayCalendarStatus::MissingLocalization);}
        if(!TextValid(result.text))return Failure(MenuReplayCalendarStatus::MissingLocalization);
        result.available=true;result.status=MenuReplayCalendarStatus::Available;return result;
    }
    MenuReplayCalendarCatalog catalog_;
};

struct MenuReplayGraphTick final {int turn=0;bool visible=false;};
struct MenuReplayGraphDomain final {
    int initialTurn=0,finalTurn=0,minTurn=0,maxTurn=4;
    std::array<MenuReplayGraphTick,5> ticks{};
    static MenuReplayGraphDomain Create(int initial,int final) {
        if(initial<0 || final<initial || final>10000000 || final-initial>1000000)
            throw std::invalid_argument("Replay graph domain escaped recorded turn bounds");
        MenuReplayGraphDomain result;result.initialTurn=initial;result.finalTurn=final;
        result.minTurn=final-initial<4?final-4:initial;result.maxTurn=final;
        const int range=result.maxTurn-result.minTurn;
        for(std::size_t i=0;i<result.ticks.size();++i){auto& tick=result.ticks[i];
            tick.turn=i==4?final:result.minTurn+static_cast<int>(i)*range/4;tick.visible=tick.turn>=initial;}
        return result;
    }
    double UnitX(int turn) const noexcept {
        return (static_cast<double>(turn)-minTurn)/(static_cast<double>(maxTurn)-minTurn);
    }
};
}
