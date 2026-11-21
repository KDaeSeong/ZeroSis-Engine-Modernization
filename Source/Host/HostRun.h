#pragma once
#include "HostFiles.h"
#include "WindowsModule.h"
#include "ScriptMetadata.h"
#include "CoreRuntimeProbe.h"
#include "GameInfoDatabase.h"
#include "NewGameProbe.h"
#include "FirstTurnProbe.h"
#include "FoundCityProbe.h"
#include "CityDecisionProbe.h"
#include "HostTempHeap.h"
#include "SdkGameRestore.h"
#include "SdkStateSnapshot.h"
#include "UiPopupContext.h"
#include "InteractiveGameLoop.h"
#include "TradeRouteFixtureProbe.h"
#include "MenuLifecycleWindow.h"
#if defined(ZEROSIS_UI_WINDOW_PRESENTATION)
#include "MenuReplayPresentation.h"
#endif
#include <CvLocalization.h>
#include <DatabaseResults.h>

namespace ZeroSisHost {
// A Run owns every dependency until both GameCore and provider shutdown finish.
// On unrecoverable cleanup failure main retains the entire Run until process exit.
class HostRun {
public:
    explicit HostRun(std::wstring directory):bundle_(std::move(directory)),
        module_(bundle_.Directory()+L"\\CvGameCoreDLL_Expansion2_x64.dll"){}
    ~HostRun(){if(dataTouched_ || session_.Phase()!=SessionPhase::Empty)std::terminate();}
    void Prepare(const std::string& language) {
        if(dataTouched_)throw std::logic_error("Host data already prepared or requires cleanup");
        if(language.empty())throw std::invalid_argument("Language type is required");
        sessionDirectory_=NewSessionDirectory(bundle_);
        dataTouched_=true;
        tempHeap_.Start();
        const DWORD size=GetCurrentDirectoryW(0,nullptr);
        if(!size)throw std::runtime_error("Cannot record original working directory");
        std::vector<wchar_t> buffer(size);
        const DWORD count=GetCurrentDirectoryW(size,buffer.data());
        if(!count || count>=size)throw std::runtime_error("Cannot record original working directory");
        oldDirectory_.assign(buffer.data(),count);
        if(!SetCurrentDirectoryW(sessionDirectory_.c_str()))throw std::runtime_error("Cannot enter private session directory");
        directoryChanged_=true;
        const auto rulesPath=sessionDirectory_+L"\\rules.db";
        if(!CopyFileW((bundle_.Directory()+L"\\rules.db").c_str(),rulesPath.c_str(),TRUE))
            throw std::runtime_error("Cannot create private rules database copy");
        if(!rules_.Open(Utf8(rulesPath).c_str(),Database::OPEN_READWRITE|Database::OPEN_FULLMUTEX))
            throw std::runtime_error("Cannot open private rules database");
        if(!localization_.Open(Utf8(bundle_.Directory()+L"\\localization.db").c_str(),Database::OPEN_READONLY|Database::OPEN_FULLMUTEX))
            throw std::runtime_error("Cannot open read-only localization database");
        PrepareDiplomacyResponseCatalog();
        localizationTouched_=true; // Shutdown also covers a partially completed initialize.
        if(!Localization::Initialize((bundle_.Directory()+L"\\icudt44l.dat").c_str(),localization_,"Languages",language.c_str(),false))
            throw std::runtime_error("Cannot initialize localization for language "+language);
        ReadFileHandle audioFile(bundle_.Directory()+L"\\audio-catalog.bin");
        LARGE_INTEGER audioSize;
        if(!GetFileSizeEx(audioFile.Get(),&audioSize) || audioSize.QuadPart<0 || audioSize.QuadPart>16*1024*1024)
            throw std::runtime_error("Invalid audio catalog file size");
        std::vector<unsigned char> audioBytes(static_cast<std::size_t>(audioSize.QuadPart));
        if(audioFile.Read(audioBytes.data(),static_cast<DWORD>(audioBytes.size()))!=audioBytes.size())
            throw std::runtime_error("Audio catalog read was truncated");
        auto catalog=std::make_shared<AudioCatalog>(audioBytes);
        ReadFileHandle scriptFile(bundle_.Directory()+L"\\script-catalog.bin");LARGE_INTEGER scriptSize;
        if(!GetFileSizeEx(scriptFile.Get(),&scriptSize) || scriptSize.QuadPart<0 || scriptSize.QuadPart>64*1024*1024)
            throw std::runtime_error("Invalid script catalog file size");
        std::vector<unsigned char> scriptBytes(static_cast<std::size_t>(scriptSize.QuadPart));
        if(scriptFile.Read(scriptBytes.data(),static_cast<DWORD>(scriptBytes.size()))!=scriptBytes.size())
            throw std::runtime_error("Script catalog read was truncated");
        auto scripts=std::make_shared<ScriptSystem>(nullptr,nullptr,std::make_shared<ScriptCatalog>(scriptBytes));
        scripts->BindRules(std::make_shared<GameInfoDatabase>(rules_));
        // This isolated profile activates no mods. The cached rules database
        // is not an activation manifest, and installed DLC is not a mod list.
        // Native saves bind the exact host/bundle bytes; both fresh sessions
        // use this same explicit empty declaration. Mod loading is separate.
        auto activeMods=std::make_shared<const ActiveModCatalog>(std::vector<ActiveModCatalog::Entry>{});
        state_=std::make_shared<HostState>(Utf8(sessionDirectory_+L"\\"),nullptr,std::move(catalog),std::move(scripts),std::move(activeMods));
        std::printf("SESSION_ACTIVE_MODS=%zu\n",state_->activeMods->Size());
        // The public SDK interface exposes unit/building rules but no project
        // or process info getters. Own the exact read-only DB identities before
        // any local city command can dispatch into the SDK's indexed arrays.
        const auto cityRuleIds=[&](const char* sql,std::set<int>& output){
            Database::Results rows;
            if(!rules_.Execute(rows,sql))throw std::runtime_error("Cannot read local city command rules");
            while(rows.Step()){
                const char* type=rows.GetText(1);const double raw=rows.GetDouble(0);
                if(!type || std::strcmp(type,"integer")!=0 || !std::isfinite(raw) || raw<0 || raw>INT_MAX || std::floor(raw)!=raw)
                    throw std::runtime_error("City command rules contain an invalid item ID");
                if(!output.insert(static_cast<int>(raw)).second)
                    throw std::runtime_error("City command rules contain a duplicate item ID");
            }
            if(rules_.ErrorCode()!=0 && rules_.ErrorCode()!=101)
                throw std::runtime_error("City command rule enumeration failed");
        };
        cityRuleIds("SELECT ID,typeof(ID) FROM Projects ORDER BY ID",state_->validCityProjectTypes);
        cityRuleIds("SELECT ID,typeof(ID) FROM Processes ORDER BY ID",state_->validCityProcessTypes);
        state_->cityItemRulesReady=true;
        std::printf("CITY_COMMAND_RULE_IDS=%zu,%zu\n",state_->validCityProjectTypes.size(),state_->validCityProcessTypes.size());
        Database::Results cityNames;
        if(!rules_.Execute(cityNames,"SELECT CityName FROM Civilization_CityNames UNION SELECT CityName FROM MinorCivilization_CityNames"))
            throw std::runtime_error("Cannot read built-in city names");
        while(cityNames.Step()){
            const char* name=cityNames.GetText(0);
            if(!name || !*name || std::strspn(name,"ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_")!=std::strlen(name))
                throw std::runtime_error("Built-in city name is not a plain localization key");
            state_->builtInCityNames.insert(name);
        }
        if((rules_.ErrorCode()!=0 && rules_.ErrorCode()!=101) || state_->builtInCityNames.empty())
            throw std::runtime_error("Built-in city name catalog is incomplete");
    }
    void InitializeCore() {
        if(!state_)throw std::logic_error("Host data must be prepared before GameCore");
        session_.Initialize(module_,state_,rules_);
    }
#if defined(ZEROSIS_UI_WINDOW_PRESENTATION)
    void StartCapturedSetup(const MenuLifecycleSetup& setup){
        if(!state_ || interactive_ || popup_)throw std::logic_error("Captured setup requires a fresh prepared host");
        ReadFileHandle file(bundle_.Directory()+L"\\bundle.manifest");std::array<unsigned char,16385> bytes{};
        const auto size=file.Read(bytes.data(),static_cast<DWORD>(bytes.size()));
        if(!size || size==bytes.size())throw std::runtime_error("Restart bundle identity is invalid");
        const std::vector<unsigned char> manifest(bytes.begin(),bytes.begin()+size);
        session_.WithCore([&](ICvGameContext3& context){setup.ApplyAndStart(context,*state_,manifest);});
        std::puts("INTERACTIVE_CAPTURED_SETUP_STARTED=EXACT_CURRENT_SETUP_ORIGINAL_INITIAL_SEEDS_FRESH_CORE");
    }
    std::shared_ptr<const MenuReplayCalendar> ReplayCalendarCatalog(){
        MenuReplayCalendarCatalog catalog;
        const auto integer=[](Database::Results& rows,int index,int typeIndex){
            const auto* type=rows.GetText(typeIndex);const double value=rows.GetDouble(index);
            if(!type || std::strcmp(type,"integer") || !std::isfinite(value) || value<INT_MIN || value>INT_MAX || std::floor(value)!=value)
                throw std::runtime_error("Replay calendar rule is not an exact supported integer");
            return static_cast<int>(value);
        };
        const auto identities=[&](const char* sql,std::map<int,std::string>& output){
            Database::Results rows;if(!rules_.Execute(rows,sql))throw std::runtime_error("Cannot read replay calendar identities");
            while(rows.Step()){
                const int id=integer(rows,0,1);const char* type=rows.GetText(2);
                if(id<0 || !type || !*type || std::strspn(type,"ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_")!=std::strlen(type) ||
                   !output.emplace(id,type).second)throw std::runtime_error("Invalid or duplicate replay calendar identity");
            }
            if((rules_.ErrorCode()!=0 && rules_.ErrorCode()!=101) || output.empty())throw std::runtime_error("Replay calendar identity query did not finish");
        };
        identities("SELECT ID,typeof(ID),Type FROM Calendars ORDER BY ID",catalog.calendars);
        identities("SELECT ID,typeof(ID),Type FROM GameSpeeds ORDER BY ID",catalog.gameSpeeds);
        for(const auto& speed:catalog.gameSpeeds)catalog.speedTurns.emplace(speed.second,std::vector<MenuReplayCalendarIncrement>{});
        Database::Results increments;
        if(!rules_.Execute(increments,"SELECT GameSpeedType,MonthIncrement,typeof(MonthIncrement),TurnsPerIncrement,typeof(TurnsPerIncrement) FROM GameSpeed_Turns ORDER BY rowid"))
            throw std::runtime_error("Cannot read original replay calendar speed increments");
        while(increments.Step()){
            const auto* speed=increments.GetText(0);const int months=integer(increments,1,2),turns=integer(increments,3,4);
            if(!speed || !*speed || months<0 || turns<=0)throw std::runtime_error("Invalid replay calendar speed increment");
            const auto found=std::find_if(catalog.gameSpeeds.begin(),catalog.gameSpeeds.end(),[&](const std::pair<const int,std::string>& value){return value.second==speed;});
            if(found==catalog.gameSpeeds.end())throw std::runtime_error("Replay calendar speed increment has no declared speed");
            auto& values=catalog.speedTurns[speed];if(values.size()>=4096)throw std::runtime_error("Replay calendar speed increment bound exceeded");
            values.push_back({months,turns});
        }
        if(rules_.ErrorCode()!=0 && rules_.ErrorCode()!=101)throw std::runtime_error("Replay calendar increment query did not finish");
        const auto names=[&](const char* sql,std::vector<std::wstring>& output){
            Database::Results rows;if(!rules_.Execute(rows,sql))throw std::runtime_error("Cannot read replay calendar name catalog");
            while(rows.Step()){
                const int id=integer(rows,0,1);const auto* key=rows.GetText(2);
                if(id<0 || static_cast<std::size_t>(id)!=output.size() || output.size()>=1024 || !key || !*key)
                    throw std::runtime_error("Replay calendar names are not contiguous original identities");
                auto localized=Localization::Lookup(key);const char* text=localized.toUTF8();
                // Stock ReplayViewer shows Locale.Lookup(Description). The retail
                // Lookup binding has no presence test and a missing key returns
                // the key itself; stock Seasons keys have no text rows, so the
                // original SEASONS date shows the raw key. Keep exactly that.
                output.push_back(text && *text?MenuLifecycleWindowDetail::Wide(text):std::wstring());
            }
            if((rules_.ErrorCode()!=0 && rules_.ErrorCode()!=101) || output.empty())throw std::runtime_error("Replay calendar names query did not finish");
        };
        names("SELECT ID,typeof(ID),Description FROM Months ORDER BY ID",catalog.monthNames);
        names("SELECT ID,typeof(ID),Description FROM Seasons ORDER BY ID",catalog.seasonNames);
        Database::Results defines;
        if(!rules_.Execute(defines,"SELECT Name,Value,typeof(Value) FROM Defines WHERE Name IN ('WEEKS_PER_MONTHS','HIDDEN_START_TURN_OFFSET') ORDER BY Name"))
            throw std::runtime_error("Cannot read original replay calendar definitions");
        std::set<std::string> observed;
        while(defines.Step()){
            const auto* key=defines.GetText(0);if(!key || !observed.insert(key).second)throw std::runtime_error("Duplicate replay calendar definition");
            const int value=integer(defines,1,2);
            if(std::strcmp(key,"WEEKS_PER_MONTHS")==0)catalog.weeksPerMonth=value;
            else if(std::strcmp(key,"HIDDEN_START_TURN_OFFSET")==0)catalog.hiddenStartTurnOffset=value;
            else throw std::runtime_error("Unexpected replay calendar definition");
        }
        if((rules_.ErrorCode()!=0 && rules_.ErrorCode()!=101) || observed.size()!=2 || catalog.weeksPerMonth<=0)
            throw std::runtime_error("Replay calendar definitions are incomplete");
        catalog.localizeNumber=[](const char* key,std::int64_t value){
            auto result=Localization::Lookup(key);
            if(!result.PushArgument(static_cast<__int64>(value)))throw std::runtime_error("Replay calendar localization argument failed");
            const char* text=result.toUTF8();if(!text || !*text || std::strcmp(text,key)==0)
                throw std::runtime_error("Replay calendar localization is unavailable");
            return MenuLifecycleWindowDetail::Wide(text);
        };
        return std::make_shared<const MenuReplayCalendar>(std::move(catalog));
    }
    MenuLifecycleFrontEndChoice FrontEnd(const std::shared_ptr<const MenuLifecycleSetup>& setup,
                                         const std::shared_ptr<const MenuLifecycleEndGame>& endGame){
        if(!state_ || session_.Phase()!=SessionPhase::Empty || interactive_ || popup_)
            throw std::logic_error("Front end requires prepared data with no attached GameCore");
        EnsureHostMenuOptions(*state_,bundle_.Directory(),[]{return std::make_shared<UiAudioPlayback>();});
        std::vector<MenuLifecycleRanking> rankings;Database::Results rows;
        if(endGame){
            if(!rules_.Execute(rows,"SELECT HistoricLeader,LeaderScore FROM HistoricRankings ORDER BY ID"))
                throw std::runtime_error("Cannot read original historical ranking thresholds");
            while(rows.Step()){
                const char* key=rows.GetText(0);if(!key || !*key)throw std::runtime_error("Historical ranking has no leader key");
                auto localized=Localization::Lookup(key);const auto* text=localized.toUTF8();
                if(!text || !*text)throw std::runtime_error("Historical ranking localization is unavailable");
                rankings.push_back({rows.GetInt(1),MenuLifecycleWindowDetail::Wide(text)});
            }
            if((rules_.ErrorCode()!=0 && rules_.ErrorCode()!=101) || rankings.empty())
                throw std::runtime_error("Historical ranking enumeration is incomplete");
        }
        std::puts("INTERACTIVE_FRONT_END_ENTERED=OLD_GAMECORE_ABSENT_REAL_OWNED_MENU_LOOP");
        MenuFrontEndHooks hooks;
        hooks.options=state_->menuOptions;
        hooks.applyOptions=[host=state_](ZeroSisPresentation::BitmapWindow& window,const MenuOptionsValues& value){
            return ApplyHostMenuOptions(*host,window,value);
        };
        hooks.persistOptions=[store=state_->menuOptionsStore](const MenuOptionsValues& value){store->WriteAtomic(value);};
        std::shared_ptr<MenuReplayView> replay;
        if(endGame){
            MenuReplayLabels labels;
            labels.title=MenuLifecycleWindowDetail::Localized("TXT_KEY_REPLAY_TITLE");
            labels.map=MenuLifecycleWindowDetail::Localized("TXT_KEY_REPLAY_VIEWER_MAP_TITLE");
            labels.graphs=MenuLifecycleWindowDetail::Localized("TXT_KEY_REPLAY_VIEWER_GRAPHS_TITLE");
            labels.messages=MenuLifecycleWindowDetail::Localized("TXT_KEY_REPLAY_VIEWER_MESSAGES_TITLE");
            labels.playPause=MenuLifecycleWindowDetail::Localized("TXT_KEY_REPLAY_PLAYPAUSE");
            labels.back=MenuLifecycleWindowDetail::Localized("TXT_KEY_BACK_BUTTON");
            labels.turnCounter=[](int turn){
                auto value=Localization::Lookup("TXT_KEY_TP_TURN_COUNTER");
                if(!value.PushArgument(turn))throw std::runtime_error("Replay turn caption localization argument failed");
                const char* text=value.toUTF8();if(!text || !*text || std::strcmp(text,"TXT_KEY_TP_TURN_COUNTER")==0)
                    throw std::runtime_error("Replay turn caption localization is unavailable");
                return MenuLifecycleWindowDetail::Wide(text);
            };
            labels.turn=L"\ud134";labels.noGraphData=MenuLifecycleWindowDetail::Localized("TXT_KEY_REPLAY_NOGRAPHDATA");
            labels.terrainReference=L"\uc9c0\ub3c4\ub294 \uac04\ub7b5 \ud45c\uc2dc\uc774\uba70 \uc9c0\ud615\uc740 \ucd5c\uc885 \uc2dc\uc810\uc744 \ucc38\uc870\ud569\ub2c8\ub2e4. \uc601\ud1a0\uc640 \ub3c4\uc2dc\ub294 \uc120\ud0dd\ud55c \ud134\uc758 \uae30\ub85d\uc774\uba70 \uc6d0\ubcf8 3D \uc9c0\ub3c4\ub294 \uc544\uc9c1 \uc9c0\uc6d0\ud558\uc9c0 \uc54a\uc2b5\ub2c8\ub2e4.";
            labels.unsupportedReplay=L"\uc774 \uc7ac\uc0dd \uae30\ub85d\uc758 \ud615\uc2dd\uc744 \uc9c0\uc6d0\ud558\uc9c0 \uc54a\uc2b5\ub2c8\ub2e4.";
            MenuReplayPalette palette;
            palette.calendar=ReplayCalendarCatalog();
            std::vector<MenuReplayGraphColor> orderedGraphColors;
            Database::Results richColors;
            if(!rules_.Execute(richColors,"SELECT Type,Red,Green,Blue,Alpha FROM Colors ORDER BY ID"))
                throw std::runtime_error("Cannot enumerate original replay text colors");
            while(richColors.Step()){
                const char* name=richColors.GetText(0);
                if(!name || !*name)throw std::runtime_error("Replay text color has no original identity");
                float channels[4]{};double originalChannels[4]{};
                for(int i=0;i<4;++i){const double value=richColors.GetDouble(i+1);
                    if(!std::isfinite(value) || value<0 || value>1)throw std::runtime_error("Replay text color channel is invalid");
                    originalChannels[i]=value;channels[i]=static_cast<float>(value);}
                orderedGraphColors.push_back({name,originalChannels[0],originalChannels[1],originalChannels[2],originalChannels[3]});
                if(!palette.richColors.emplace(name,MenuFrontEndAssets::Color{channels[0],channels[1],channels[2],channels[3]}).second)
                    throw std::runtime_error("Replay text color identity is duplicated");
            }
            if(rules_.ErrorCode()!=0 && rules_.ErrorCode()!=101)throw std::runtime_error("Replay text-color query did not finish");
            // The replay records custom player-color IDs. Query those exact
            // IDs rather than silently replacing them with civilization defaults.
            std::map<int,std::pair<MenuFrontEndAssets::Color,MenuFrontEndAssets::Color>> colors;
            std::map<int,std::pair<std::string,std::string>> graphColorTypes;
            Database::Results colorRows;
            if(!rules_.Execute(colorRows,"SELECT p.ID,a.Red,a.Green,a.Blue,a.Alpha,b.Red,b.Green,b.Blue,b.Alpha,a.Type,b.Type FROM PlayerColors p JOIN Colors a ON a.Type=p.PrimaryColor JOIN Colors b ON b.Type=p.SecondaryColor ORDER BY p.ID"))
                throw std::runtime_error("Cannot enumerate original replay player colors");
            while(colorRows.Step()){
                float values[8]{};
                for(int i=0;i<8;++i){const double value=colorRows.GetDouble(i+1);
                    if(!std::isfinite(value) || value<0 || value>1)throw std::runtime_error("Replay palette contains an invalid color channel");
                    values[i]=static_cast<float>(value);}
                colors.emplace(colorRows.GetInt(0),std::make_pair(
                    MenuFrontEndAssets::Color{values[0],values[1],values[2],values[3]},
                    MenuFrontEndAssets::Color{values[4],values[5],values[6],values[7]}));
                const char* primaryType=colorRows.GetText(9);const char* secondaryType=colorRows.GetText(10);
                if(!primaryType || !*primaryType || !secondaryType || !*secondaryType ||
                   !graphColorTypes.emplace(colorRows.GetInt(0),std::make_pair(primaryType,secondaryType)).second)
                    throw std::runtime_error("Replay graph palette identities are invalid or duplicated");
            }
            if(rules_.ErrorCode()!=0 && rules_.ErrorCode()!=101)throw std::runtime_error("Replay color query did not finish");
            int minorCivilization=-1;Database::Results minorRows;
            if(!rules_.Execute(minorRows,"SELECT ID FROM Civilizations WHERE Type='CIVILIZATION_MINOR'"))
                throw std::runtime_error("Cannot read original replay minor-civilization identity");
            if(minorRows.Step())minorCivilization=minorRows.GetInt(0);
            struct ReplayCivilization final {MenuReplayPalette::LegendIcon icon;std::string label;};
            std::map<int,ReplayCivilization> civilizations;
            Database::Results civilizationRows;
            if(!rules_.Execute(civilizationRows,"SELECT c.ID,c.PortraitIndex,c.ShortDescription,a.Filename,a.IconsPerRow,a.IconsPerColumn FROM Civilizations c JOIN IconTextureAtlases a ON a.Atlas=c.IconAtlas AND a.IconSize=32 ORDER BY c.ID"))
                throw std::runtime_error("Cannot read original replay civilization portraits");
            const auto positive=[](const char* value){
                if(!value || !*value || std::strlen(value)>5 || std::strspn(value,"0123456789")!=std::strlen(value))
                    throw std::runtime_error("Replay civilization atlas dimensions are invalid");
                const auto number=std::stoul(value);if(!number || number>4096)throw std::runtime_error("Replay civilization atlas dimensions exceed bounds");
                return static_cast<unsigned>(number);
            };
            while(civilizationRows.Step()){
                const int id=civilizationRows.GetInt(0),portrait=civilizationRows.GetInt(1);
                const auto* label=civilizationRows.GetText(2);const auto* texture=civilizationRows.GetText(3);
                if(id<0 || portrait<0 || !label || !*label || !texture || !*texture ||
                   std::strspn(texture,"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_.")!=std::strlen(texture))
                    throw std::runtime_error("Replay civilization portrait lacks its original identity");
                ReplayCivilization binding;auto localized=Localization::Lookup(label);const char* text=localized.toUTF8();
                if(text && *text && std::strcmp(text,label)!=0)binding.label=text;
                binding.icon.texture=texture;
                binding.icon.portrait=static_cast<unsigned>(portrait);binding.icon.columns=positive(civilizationRows.GetText(4));binding.icon.rows=positive(civilizationRows.GetText(5));
                if(binding.icon.portrait>=static_cast<std::uint64_t>(binding.icon.columns)*binding.icon.rows || !civilizations.emplace(id,std::move(binding)).second)
                    throw std::runtime_error("Replay civilization portrait identity is duplicated or out of range");
            }
            if(rules_.ErrorCode()!=0 && rules_.ErrorCode()!=101)throw std::runtime_error("Replay civilization portrait query did not finish");
            std::shared_ptr<const MenuReplayDocument> replayDocument;
            try{replayDocument=std::make_shared<const MenuReplayDocument>(ReadMenuReplay(endGame->replay));}
            catch(const std::runtime_error&){
                // The viewer owns format errors and preserves the raw bytes.
                // Unsupported streams still have a usable results/back screen.
            }
            if(replayDocument){
                const auto& document=*replayDocument;
                std::vector<std::pair<std::string,std::string>> recordedGraphColors;bool graphTypesAvailable=true;
                for(const auto& player:document.players){
                    const auto graphTypes=graphColorTypes.find(player.playerColor);
                    if(graphTypes==graphColorTypes.end())graphTypesAvailable=false;
                    else recordedGraphColors.push_back(graphTypes->second);
                    const auto civilization=civilizations.find(player.civilization);
                    palette.legendIcons.push_back(civilization==civilizations.end()?MenuReplayPalette::LegendIcon{}:civilization->second.icon);
                    std::string caption;
                    if(!player.civilizationShortName.empty()){
                        auto localized=Localization::Lookup(player.civilizationShortName.c_str());const auto* text=localized.toUTF8();
                        if(text && *text)caption=text;
                    }else if(civilization!=civilizations.end())caption=civilization->second.label;
                    palette.playerLabels.push_back(std::move(caption));
                    if(player.civilization==minorCivilization)palette.initiallyHiddenPlayers.insert(palette.playerLabels.size()-1);
                    auto primary=MenuFrontEndAssets::Color{0.5f,0.5f,0.5f,0.8f};
                    auto secondary=MenuFrontEndAssets::Color{0.75f,0.75f,0.75f,1};
                    const auto found=colors.find(player.playerColor);
                    if(found!=colors.end()){primary=found->second.first;secondary=found->second.second;}
                    auto messagePrimary=primary,messageSecondary=secondary;messagePrimary.a=messageSecondary.a=1;
                    palette.messagePrimary.push_back(messagePrimary);palette.messageSecondary.push_back(messageSecondary);
                    if(found!=colors.end() && player.civilization==minorCivilization)std::swap(primary,secondary);
                    primary.a=0.8f;secondary.a=1;
                    palette.playerPrimary.push_back(primary);palette.playerSecondary.push_back(secondary);
                }
                if(graphTypesAvailable){const auto selected=SelectMenuReplayGraphColors(orderedGraphColors,recordedGraphColors);
                    for(const auto& color:selected)palette.graphColors.push_back({static_cast<float>(color.r),static_cast<float>(color.g),static_cast<float>(color.b),static_cast<float>(color.a)});}
            }
            Database::Results datasets;
            if(!rules_.Execute(datasets,"SELECT Type,Description FROM ReplayDataSets ORDER BY ID"))
                throw std::runtime_error("Cannot enumerate original replay graph labels");
            while(datasets.Step()){
                const char* type=datasets.GetText(0);const char* key=datasets.GetText(1);
                if(!type || !*type || !key || !*key)throw std::runtime_error("Replay graph dataset lacks its original label");
                palette.dataSetLabels.emplace(type,MenuLifecycleWindowDetail::Localized(key));
            }
            if(rules_.ErrorCode()!=0 && rules_.ErrorCode()!=101)throw std::runtime_error("Replay graph query did not finish");
            replay=std::make_shared<MenuReplayView>(endGame->replay,std::move(labels),std::move(palette));
            hooks.replayScene=[replay](const MenuFrontEndAssets& assets){return replay->Scene(assets);};
            hooks.replayInput=[replay](const ZeroSisPresentation::BitmapInputEvent& input){return replay->Input(input);};
            hooks.replayAdvance=[replay](double seconds){return replay->Advance(seconds);};
            hooks.replayPointerCapture=[replay](bool held){return replay->PointerCapture(held);};
        }
        return RunMenuLifecycleFrontEnd(!!setup,endGame,rankings,hooks);
    }
#endif
    void EnableUiPopups(bool windowPresentation=false,bool displayResize=false,bool refreshClosed=false){
        if(popup_)throw std::logic_error("UI popup context is already enabled");
        session_.WithCore([&](ICvGameContext3& context){
            popup_.reset(new UiPopupContext(state_,context,sessionDirectory_,windowPresentation,displayResize,refreshClosed));
        });
    }
    std::string CoreObservation() {
        if(session_.Phase()!=SessionPhase::CoreInitialized)throw std::logic_error("Core must be initialized before runtime observation");
        coreProbe_.Begin(*state_);
        Database::Results values;
        if(!rules_.Execute(values,"SELECT (SELECT ID FROM Units WHERE Type='UNIT_SETTLER'),(SELECT ID FROM Civilizations WHERE Type='CIVILIZATION_AMERICA'),(SELECT ID FROM Buildings WHERE Type='BUILDING_MONUMENT')") || !values.Step())
            throw std::runtime_error("Cannot query core observation reference types");
        for(unsigned i=0;i<3;++i)if(values.GetInt(static_cast<int>(i))!=coreProbe_.TypeValue(i))throw std::runtime_error("Core Lua type differs from rules database");
        return coreProbe_.Observation();
    }
    std::string CoreShutdownObservation() const{return coreProbe_.ShutdownObservation();}
    std::string NewGameObservation(){
        try{session_.WithCore([&](ICvGameContext3& context){newGameProbe_.Begin(context,*state_,rules_);});}
        catch(...){
            if(state_ && state_->scripts && *state_->scripts->LastError())
                std::fprintf(stderr,"NEW_GAME_SCRIPT_FAILURE: %s\n",state_->scripts->LastError());
            TraceNewGameServices();
            throw;
        }
        TraceNewGameServices();
        return newGameProbe_.Observation();
    }
    std::string FirstTurnObservation(bool turnCycle=false){
        try{session_.WithCore([&](ICvGameContext3& context){firstTurnProbe_.Begin(context,*state_,sessionDirectory_,bundle_.Directory(),turnCycle);});}
        catch(...){TraceNewGameServices();throw;}
        TraceNewGameServices();return firstTurnProbe_.Observation();
    }
    void TradeRouteFixtureObservation(){
        if(popup_ || interactive_)throw std::logic_error("Trade fixture probe must not share an interactive UI context");
        try{session_.WithCore([&](ICvGameContext3& context){
            TradeRouteFixtureProbe::Run(context,state_,sessionDirectory_,bundle_.Directory());
        });}catch(...){TraceNewGameServices();throw;}
        TraceNewGameServices();
    }
#if defined(ZEROSIS_UI_WINDOW_PRESENTATION)
    InteractiveGameSession::LoadHandoff InteractivePlay(bool smoke,const std::wstring& checkpoint=L"",
                                                        std::shared_ptr<const NativeSaveArchive> decodedArchive={}){
        if(popup_ || interactive_)throw std::logic_error("Interactive play requires its own persistent UI session");
        interactive_.reset(new InteractiveGameSession(state_,sessionDirectory_,bundle_.Directory()));
        InteractiveGameSession::LoadHandoff result;
        try{result=RunInteractiveGameLoop(session_,*state_,*interactive_,sessionDirectory_,smoke,checkpoint,bundle_.UnitAssetsPath(),bundle_.UnitAnimation(),std::move(decodedArchive));}
        catch(...){TraceNewGameServices();throw;}
        TraceNewGameServices();
        return result;
    }
#endif
    std::wstring SaveCheckpoint(std::string& snapshot){
        std::wstring path;
        session_.WithCore([&](ICvGameContext3& context){
            snapshot=SdkStateSnapshot::Capture(*state_);
            SdkStateSnapshot::Write(sessionDirectory_+L"\\state-before-save.txt",snapshot);
            SdkGameSave saves(context,*state_,sessionDirectory_,bundle_.Directory());
            path=saves.Checkpoint();
        });
        return path;
    }
    FoundCityResult FoundCityObservation(){
        FoundCityResult result;
        try{session_.WithCore([&](ICvGameContext3& context){
            std::unique_ptr<ICvGame1> game(context.GetGame());
            std::unique_ptr<ICvNetMessageHandler1> messages(context.GetNetMessageHandler());
            if(!game || !messages)throw std::runtime_error("Founding requires actual SDK game and receiver interfaces");
            LocalSdkSession localSession(*state_,*messages,*game,context);
            result=FoundCityProbe::Run(*game,*state_);
            SdkStateSnapshot::Write(sessionDirectory_+L"\\state-after-founded-city.txt",SdkStateSnapshot::Capture(*state_));
        });}catch(...){TraceNewGameServices();throw;}
        TraceNewGameServices();return result;
    }
    void RestoreFoundCityCheckpoint(const std::wstring& path,const std::string& expected,FoundCityResult founded,CityDecisionResult* decisions=nullptr,bool productionUi=false,bool productionWindow=false,bool liveProduction=false,bool researchUi=false,bool researchWindow=false,bool researchTree=false){
        if(researchWindow && !researchUi)throw std::logic_error("Research window requires the official TechPopup");
        if(researchTree && (!researchUi || researchWindow))throw std::logic_error("Research-tree probe requires its separate direct-input mode");
        if(researchUi && productionUi)throw std::logic_error("Separate decision UI fixtures require distinct snapshot sessions");
        if(productionWindow && !productionUi)throw std::logic_error("Native production input requires its official popup fixture");
        if(liveProduction && !productionWindow)throw std::logic_error("Live production requires the owned GPU window profile");
        try{session_.WithCore([&](ICvGameContext3& context){
            const auto archive=SdkGameRestore::Load(context,*state_,path,bundle_.Directory());
            if(archive.turn!=0 || archive.elapsed!=0 || archive.activePlayer!=0)
                throw std::runtime_error("Founded-city checkpoint left the initial human turn");
            std::unique_ptr<ICvGame1> game(context.GetGame());
            std::unique_ptr<ICvMap1> map(context.GetMap());
            std::unique_ptr<ICvNetMessageHandler1> messages(context.GetNetMessageHandler());
            if(!game || !map || !messages)throw std::runtime_error("Missing founded-city restore SDK interfaces");
            LocalSdkSession localSession(*state_,*messages,*game,context);
            SdkGameSave saves(context,*state_,sessionDirectory_,bundle_.Directory());
            game->InitTacticalAnalysisMap(map->NumPlots());
            for(int id=0;id<MAX_PLAYERS;++id){
                std::unique_ptr<ICvPlayer1> player(game->GetPlayer(static_cast<PlayerTypes>(id)));
                if(!player || player->GetID()!=id)throw std::runtime_error("Missing founded-city restored player slot");
                player->LaterInit();
            }
            game->DoGameStarted();
            const auto actual=SdkStateSnapshot::Capture(*state_);
            SdkStateSnapshot::Write(sessionDirectory_+L"\\state-after-found-city-restore.txt",actual);
            if(actual!=expected)throw std::runtime_error("Founded-city fresh-session semantic state differs");
            std::puts("FOUND_CITY_RESTORE_STATE_EQUAL=true");
            FoundCityProbe::Check(*game,*state_,founded,true);
            const auto written=saves.Capture(false,false);
            const unsigned equal=SdkGameRestore::VerifyRoundtrip(context,archive,written);
            if(archive.sections[2].bytes!=written.sections[2].bytes)
                std::printf("FOUND_CITY_RESTORE_SECTION_CHANGED=%u,%u\n",archive.sections[2].kind,archive.sections[2].index);
            NativeSaveArchive::WriteAtomic(sessionDirectory_+L"\\state-after-found-city-restore.zssave",written.Encode());
            std::printf("FOUND_CITY_RESTORE_SECTIONS_EQUAL=%u,%zu\n",equal,archive.sections.size());
            for(int update=0;update<3;++update){game->Update();FoundCityProbe::Check(*game,*state_,founded,true);}
            const auto idle=SdkStateSnapshot::Capture(*state_);
            if(idle!=expected)throw std::runtime_error("Restored founded city changed without further user input");
            SdkStateSnapshot::Write(sessionDirectory_+L"\\state-after-found-city-idle.txt",idle);
            std::puts("FOUND_CITY_RESTORE_IDLE_UPDATES=3\nFOUND_CITY_RESTORE_IDLE_STATE_EQUAL=true");
            if(decisions){
                if(productionUi){
                    if(popup_)throw std::logic_error("Production fixture cannot replace another UI context");
                    popup_.reset(new UiPopupContext(state_,context,sessionDirectory_,productionWindow,productionWindow,productionWindow,UiPopupKind::Production,liveProduction));
                    const auto previous=state_->Events();
                    popup_->Submit(CvPopupInfo(BUTTONPOPUP_CHOOSEPRODUCTION,founded.city,-1,-1,0,false,false));
                    const auto beforeFrame=SdkStateSnapshot::Capture(*state_);
                    popup_->CaptureFrame(0.25);
                    if(SdkStateSnapshot::Capture(*state_)!=beforeFrame)
                        throw std::runtime_error("Owned UI frame clock changed gameplay state");
                    std::puts("PRODUCTION_UI_OWNER_CLOCK=0,0.25\nPRODUCTION_UI_FRAME_GAMEPLAY_STATE_EQUAL=true");
                    const int unit=popup_->ChooseProductionUnit(founded.city);
                    popup_->Stop();popup_.reset();
                    const auto events=state_->Events();
                    const auto order="local-city-order:"+std::to_string(founded.city)+":"+
                        std::to_string(static_cast<int>(ORDER_TRAIN))+":"+std::to_string(unit)+":0:1:1";
                    if(std::count(events.begin(),events.end(),order)-std::count(previous.begin(),previous.end(),order)!=1)
                        throw std::runtime_error("Official production input did not dispatch exactly one original SDK order");
                    std::puts("PRODUCTION_UI_INPUT_ROUTE=OFFICIAL_BNW_POPUP_RETAINED_BUTTON_SDK_RECEIVER\nPRODUCTION_UI_TIMER_SEMAPHORE=0");
                    if(productionWindow)std::puts("PRODUCTION_UI_WINDOW_ROUTE=OWNED_HWND_HIT_OFFICIAL_CALLBACK_SDK_RECEIVER");
                    if(liveProduction)std::puts("PRODUCTION_UI_LIVE_ROUTE=OWNER_THREAD_CATEGORY_POINTER_PANEL_WHEEL_ATOMIC_SCENE_REFRESH");
                }
                if(researchUi){
                    if(popup_)throw std::logic_error("Research cannot replace a live UI context");
                    popup_.reset(new UiPopupContext(state_,context,sessionDirectory_,researchWindow,researchWindow,researchWindow,UiPopupKind::Research));
                    const auto previous=state_->Events();
                    popup_->Submit(CvPopupInfo(BUTTONPOPUP_CHOOSETECH,0,-1,-1,0,false,false));
                    if(researchTree){
                        const auto treeRequest=popup_->OpenResearchTree();
                        popup_->Stop();popup_.reset();
                        const auto treeDirectory=sessionDirectory_+L"\\research-tree";
                        if(!CreateDirectoryW(treeDirectory.c_str(),nullptr))
                            throw std::runtime_error("Cannot allocate the separate research-tree snapshot directory");
                        popup_.reset(new UiPopupContext(state_,context,treeDirectory,false,false,false,UiPopupKind::ResearchTree));
                        popup_->Submit(treeRequest);
                        std::puts("RESEARCH_TREE_UI_HANDOFF_ROUTE=OFFICIAL_OPEN_TT_BUTTON_DEFERRED_OWNER_NEW_VM\nRESEARCH_TREE_UI_TIMER_SHOWN=1");
                    }
                    const auto beforeFrame=SdkStateSnapshot::Capture(*state_);
                    const auto seedBefore=popup_->SynchronousRandomSeed();
                    popup_->CaptureFrame(0.25);
                    const auto seedAfter=popup_->SynchronousRandomSeed();
                    if(seedBefore!=seedAfter)throw std::runtime_error("Research frame consumed synchronous RNG");
                    std::printf("RESEARCH_UI_FRAME_SYNC_RNG=%lu|%lu\n",seedBefore,seedAfter);
                    if(SdkStateSnapshot::Capture(*state_)!=beforeFrame)
                        throw std::runtime_error("Research frame clock changed gameplay state");
                    std::puts("RESEARCH_UI_OWNER_CLOCK=0,0.25\nRESEARCH_UI_FRAME_GAMEPLAY_STATE_EQUAL=true");
                    const int tech=researchTree?popup_->ChooseResearchTreeTechnology():popup_->ChooseResearchTechnology();
                    popup_->Stop();popup_.reset();
                    const auto events=state_->Events();
                    const auto research="local-research:"+std::to_string(tech)+":0:-1:0";
                    if(std::count(events.begin(),events.end(),research)-std::count(previous.begin(),previous.end(),research)!=1)
                        throw std::runtime_error("Official TechSelected did not dispatch exactly one original SDK research tuple");
                    std::printf("RESEARCH_UI_LOCAL_EVENT=%s\n",research.c_str());
                    std::puts(researchTree?"RESEARCH_TREE_UI_INPUT_ROUTE=OFFICIAL_BNW_TECH_TREE_RETAINED_BUTTON_SDK_RECEIVER":
                        "RESEARCH_UI_INPUT_ROUTE=OFFICIAL_BNW_TECH_POPUP_RETAINED_BUTTON_SDK_RECEIVER\nRESEARCH_UI_TIMER_SEMAPHORE=0");
                    if(researchWindow)std::puts("RESEARCH_UI_WINDOW_ROUTE=OWNED_HWND_HIT_OFFICIAL_TECH_SELECTED_SDK_RECEIVER");
                }
                *decisions=CityDecisionProbe::Run(*game,state_,founded,productionUi,researchUi);
                SdkStateSnapshot::Write(sessionDirectory_+L"\\state-after-city-decision-turn.txt",SdkStateSnapshot::Capture(*state_));
                std::puts(researchUi?"CITY_DECISION_INPUT_ROUTE=SDK_CITY_PUSH_ORDER_AND_OFFICIAL_RESEARCH_UI\nFOUND_CITY_CONTINUED_TURN_VERIFIED=true":productionUi?"CITY_DECISION_INPUT_ROUTE=OFFICIAL_PRODUCTION_UI_AND_ENGINE_NETWORK_SEND_RESEARCH\nFOUND_CITY_CONTINUED_TURN_VERIFIED=true":
                    "CITY_DECISION_INPUT_ROUTE=SDK_CITY_PUSH_ORDER_AND_ENGINE_NETWORK_SEND_RESEARCH\nFOUND_CITY_CONTINUED_TURN_VERIFIED=true");
            }else std::puts("FOUND_CITY_CONTINUED_TURN_VERIFIED=false");
        });}catch(...){TraceNewGameServices();throw;}
        TraceNewGameServices();
    }
    void RestoreCityDecisionCheckpoint(const std::wstring& path,const std::string& expected,const CityDecisionResult& decisions){
        try{session_.WithCore([&](ICvGameContext3& context){
            const auto archive=SdkGameRestore::Load(context,*state_,path,bundle_.Directory());
            if(archive.turn!=1 || archive.elapsed!=1 || archive.activePlayer!=0)
                throw std::runtime_error("City decision checkpoint is not the next human turn");
            std::unique_ptr<ICvGame1> game(context.GetGame());
            std::unique_ptr<ICvMap1> map(context.GetMap());
            std::unique_ptr<ICvNetMessageHandler1> messages(context.GetNetMessageHandler());
            if(!game || !map || !messages)throw std::runtime_error("Missing city decision restore SDK interfaces");
            LocalSdkSession localSession(*state_,*messages,*game,context);
            SdkGameSave saves(context,*state_,sessionDirectory_,bundle_.Directory());
            game->InitTacticalAnalysisMap(map->NumPlots());
            for(int id=0;id<MAX_PLAYERS;++id){
                std::unique_ptr<ICvPlayer1> player(game->GetPlayer(static_cast<PlayerTypes>(id)));
                if(!player || player->GetID()!=id)throw std::runtime_error("Missing city-decision restored player slot");
                player->LaterInit();
            }
            game->DoGameStarted();
            const auto actual=SdkStateSnapshot::Capture(*state_);
            SdkStateSnapshot::Write(sessionDirectory_+L"\\state-after-city-decision-restore.txt",actual);
            if(actual!=expected)throw std::runtime_error("City decision fresh-session semantic state differs");
            std::puts("CITY_DECISION_RESTORE_STATE_EQUAL=true");
            CityDecisionProbe::CheckRestored(*game,*state_,decisions);
            const auto written=saves.Capture(false,false);
            const unsigned equal=SdkGameRestore::VerifyRoundtrip(context,archive,written);
            if(archive.sections[2].bytes!=written.sections[2].bytes)
                std::printf("CITY_DECISION_RESTORE_SECTION_CHANGED=%u,%u\n",archive.sections[2].kind,archive.sections[2].index);
            NativeSaveArchive::WriteAtomic(sessionDirectory_+L"\\state-after-city-decision-restore.zssave",written.Encode());
            std::printf("CITY_DECISION_RESTORE_SECTIONS_EQUAL=%u,%zu\n",equal,archive.sections.size());
            for(int update=0;update<3;++update){game->Update();CityDecisionProbe::CheckRestored(*game,*state_,decisions);}
            const auto idle=SdkStateSnapshot::Capture(*state_);
            if(idle!=expected)throw std::runtime_error("Restored city decision changed without another input");
            SdkStateSnapshot::Write(sessionDirectory_+L"\\state-after-city-decision-idle.txt",idle);
            std::puts("CITY_DECISION_RESTORE_IDLE_UPDATES=3\nCITY_DECISION_RESTORE_IDLE_STATE_EQUAL=true");
        });}catch(...){TraceNewGameServices();throw;}
        TraceNewGameServices();
    }
    void RestoreCheckpoint(const std::wstring& path,const std::string& expected,unsigned extraTurns=0,bool fixturePromotions=false,bool fixtureUnitActions=false){
        if(extraTurns>98)throw std::invalid_argument("Extended probe allows at most 98 additional turns");
        if(fixturePromotions && (!extraTurns || !popup_))
            throw std::invalid_argument("Fixture promotions require extended turns and the UI candidate");
        if(fixtureUnitActions && !fixturePromotions)
            throw std::invalid_argument("SDK unit action inputs require the fixture promotion profile");
        try{session_.WithCore([&](ICvGameContext3& context){
            const auto archive=SdkGameRestore::Load(context,*state_,path,bundle_.Directory());
            std::unique_ptr<ICvGame1> game(context.GetGame());
            std::unique_ptr<ICvMap1> map(context.GetMap());
            std::unique_ptr<ICvNetMessageHandler1> messages(context.GetNetMessageHandler());
            if(!game || !map || !messages)throw std::runtime_error("Missing restored SDK interfaces");
            LocalSdkSession localSession(*state_,*messages,*game,context);
            SdkGameSave saves(context,*state_,sessionDirectory_,bundle_.Directory());
            std::puts("NATIVE_RESTORE_PHASE=post_load_initialization");
            game->InitTacticalAnalysisMap(map->NumPlots());
            for(int id=0;id<MAX_PLAYERS;++id){
                std::unique_ptr<ICvPlayer1> player(game->GetPlayer(static_cast<PlayerTypes>(id)));
                if(!player || player->GetID()!=id)throw std::runtime_error("Missing restored player slot");
                player->LaterInit();
            }
            game->DoGameStarted();
            std::puts("NATIVE_RESTORE_PHASE=compare_sdk_state");
            const auto actual=SdkStateSnapshot::Capture(*state_);
            SdkStateSnapshot::Write(sessionDirectory_+L"\\state-after-restore.txt",actual);
            if(actual!=expected)throw std::runtime_error("Restored SDK semantic state differs from the checkpoint");
            std::printf("NATIVE_RESTORE_STATE_EQUAL=true\nNATIVE_RESTORE_STATE_BYTES=%zu\n",actual.size());
            const auto written=saves.Capture(false,false);
            const unsigned equal=SdkGameRestore::VerifyRoundtrip(context,archive,written);
            if(archive.sections[2].bytes!=written.sections[2].bytes)
                std::printf("NATIVE_RESTORE_SECTION_CHANGED=%u,%u\n",archive.sections[2].kind,archive.sections[2].index);
            NativeSaveArchive::WriteAtomic(sessionDirectory_+L"\\state-after-restore.zssave",written.Encode());
            std::printf("NATIVE_RESTORE_SECTIONS_EQUAL=%u,%zu\n",equal,archive.sections.size());
            std::unique_ptr<ICvPlayer1> local(game->GetPlayer(game->GetActivePlayer()));
            if(!local || !local->IsAlive() || !local->IsHuman() || !local->IsTurnActive())
                throw std::runtime_error("Restored game did not preserve the active human");
            std::puts("NATIVE_RESTORE_PHASE=idle_updates");
            for(int update=0;update<3;++update){
                game->Update();
                if(game->GetGameTurn()!=archive.turn || game->GetElapsedGameTurns()!=archive.elapsed ||
                   game->GetNumGameTurnActive()!=1 || game->CountNumHumanGameTurnActive()!=1 ||
                   !local->IsTurnActive() || !state_->localCommands.IsQuiescent() || *state_->scripts->LastError())
                    throw std::runtime_error("Restored human turn did not wait for input");
            }
            std::printf("NATIVE_RESTORE_OBSERVATION=%d,%d,%d,%d,%d,%d,1,1,3\n",game->GetGameTurn(),game->GetElapsedGameTurns(),
                static_cast<int>(game->GetActivePlayer()),map->GetGridWidth(),map->GetGridHeight(),map->NumPlots());
            std::puts("NATIVE_RESTORE_PHASE=resume_turn");
            FirstTurnProbe::AdvanceOneTurn(*game,*local,*state_,"RESTORED_TURN_CYCLE");
            const auto resumed=SdkStateSnapshot::Capture(*state_);
            SdkStateSnapshot::Write(sessionDirectory_+L"\\state-after-resumed-turn.txt",resumed);
            const auto resumedSave=saves.Capture(false,false);
            NativeSaveArchive::WriteAtomic(sessionDirectory_+L"\\state-after-resumed-turn.zssave",resumedSave.Encode());
            std::printf("RESUMED_TURN_STATE_BYTES=%zu\n",resumed.size());
            if(extraTurns){
                // Retain the existing local binding and its SDK acknowledgements
                // for this live session; rebinding would discard turn readiness.
                TraceNewGameServices();
                std::printf("EXTENDED_TURNS_BEGIN=2,%u\n",extraTurns);
                for(unsigned index=0;index<extraTurns;++index){
                    // Later SDK battles can legitimately change the unit count.
                    // Exhaust all remaining units without asserting the initial two.
                    FirstTurnProbe::AdvanceOneTurn(*game,*local,*state_,"EXTENDED_TURN_CYCLE",-1,fixturePromotions,fixtureUnitActions);
                    const auto snapshot=SdkStateSnapshot::Capture(*state_);
                    const auto snapshotPath=sessionDirectory_+L"\\extended-state-turn-"+std::to_wstring(game->GetGameTurn())+L".txt";
                    SdkStateSnapshot::Write(snapshotPath,snapshot);
                    std::printf("EXTENDED_TURN_SNAPSHOT=%d,%zu\n",game->GetGameTurn(),snapshot.size());
                }
                const auto finalSave=saves.Capture(false,false);
                NativeSaveArchive::WriteAtomic(sessionDirectory_+L"\\state-after-extended-turns.zssave",finalSave.Encode());
                std::printf("EXTENDED_TURNS_COMPLETE=2,%d,%u\n",game->GetGameTurn(),extraTurns);
            }
        });}catch(...){TraceNewGameServices();throw;}
        TraceNewGameServices();
    }
    std::string DataObservation() {
        if(!state_)throw std::logic_error("Host data is not prepared");
        Database::Results rows;
        if(!rules_.Execute(rows,"SELECT (SELECT COUNT(*) FROM Civilizations),(SELECT COUNT(*) FROM Units),(SELECT COUNT(*) FROM Buildings)") || !rows.Step())
            throw std::runtime_error("Cannot query required rules tables");
        std::string output="RULE_COUNTS=";const int civilizations=rows.GetInt(0);
        for(int column=0;column<3;++column){
            const int count=rows.GetInt(column);if(count<=0)throw std::runtime_error("A required rules table is empty");
            if(column)output+=",";output+=std::to_string(count);
        }
        const auto& dictionary=Localization::GetStringDictionary();
        output+="\nLANGUAGE=";output+=dictionary.GetLanguageType(dictionary.GetCurrentLanguageIndex());
        auto sample=Localization::Lookup("TXT_KEY_SINGLE_PLAYER");
        output+="\nSAMPLE_TEXT=";output+=sample.toUTF8();
        Database::Results audioRows;
        if(!rules_.Execute(audioRows,"SELECT WorldSoundscapeAudioScript FROM Improvements UNION SELECT WorldSoundscapeAudioScript FROM Features UNION SELECT WorldSoundscapeAudioScript FROM Terrains ORDER BY 1"))
            throw std::runtime_error("Cannot query rules audio tags");
        EngineServices services(state_);unsigned found=0,missing=0;
        while(audioRows.Step()){
            const char* tag=audioRows.GetText(0);if(!tag || !*tag)continue;
            const int index=services.GetAudioTagIndex(tag,AUDIOTAG_SOUNDSCAPE);
            if(index<0){++missing;output+="\nMISSING_AUDIO_TAG=";output+=tag;}
            else {++found;if(state_->audio->Definition(index).tag!=tag)throw std::logic_error("Audio index/name mismatch");}
        }
        if(rules_.ErrorCode()!=0 && rules_.ErrorCode()!=101)throw std::runtime_error("Rules audio tag iteration failed");
        output+="\nAUDIO_TAG_COUNTS="+std::to_string(state_->audio->Size())+","+std::to_string(found)+","+std::to_string(missing);
        output+="\n"+ScriptObservation(civilizations,sample.toUTF8());
        const auto map=ReadMapScriptMetadata(*state_->scripts,"Assets/Maps/Continents.lua");
        output+="\nMAP_SCRIPT_METADATA="+map.name+","+map.description+","+std::to_string(map.customOptions);
        output+="\nSCRIPT_CATALOG_COUNT="+std::to_string(state_->scripts->Catalog()->Size());
        return output;
    }
    void Shutdown() {
        if(state_ && state_->scripts && !state_->scripts->IsQuiescent())
            throw std::logic_error("Cannot shut down the host during a script callback");
        if(popup_){
            session_.WithCore([&](ICvGameContext3&){popup_->Stop();});
            popup_.reset();
        }
#if defined(ZEROSIS_UI_WINDOW_PRESENTATION)
        if(interactive_){session_.WithCore([&](ICvGameContext3&){interactive_->Stop();});interactive_.reset();}
#endif
        session_.Shutdown();
        if(state_ && state_->scripts && !state_->scripts->Close())throw std::runtime_error("Script cleanup is pending");
        tempHeap_.Close();
        if(localizationTouched_){if(!Localization::Shutdown())throw std::runtime_error("Localization cleanup is pending");localizationTouched_=false;}
        CloseDatabase(localization_);CloseDatabase(rules_);
        if(directoryChanged_){
            if(!SetCurrentDirectoryW(oldDirectory_.c_str()))throw std::runtime_error("Cannot restore working directory");
            directoryChanged_=false;
        }
        state_.reset();dataTouched_=false;
    }
    const std::wstring& SessionDirectory() const noexcept{return sessionDirectory_;}
    SessionPhase Phase() const noexcept{return session_.Phase();}
private:
    void PrepareDiplomacyResponseCatalog() {
        // CvGame::GetDiploResponse selects English tags in the rules connection,
        // then resolves the selected tag in the current localization language.
        // Our immutable bundle separates those databases. Restore that catalog
        // only for this connection, preserving the SDK's weighting and RNG.
        {
            Database::Results existing;
            if(!rules_.Execute(existing,"SELECT name FROM sqlite_master WHERE lower(name)='language_en_us' "
                "UNION ALL SELECT name FROM sqlite_temp_master WHERE lower(name)='language_en_us'"))
                throw std::runtime_error("Cannot check diplomacy catalog schema");
            if(existing.Step())throw std::runtime_error("Diplomacy catalog would shadow an existing rules object");
            if(rules_.ErrorCode()!=0 && rules_.ErrorCode()!=101)
                throw std::runtime_error("Diplomacy catalog schema query failed");
        }
        if(!rules_.Execute("SAVEPOINT host_diplomacy_catalog"))
            throw std::runtime_error("Cannot begin temporary diplomacy catalog preparation");
        std::size_t copied=0;
        try {
            if(!rules_.Execute("CREATE TEMP TABLE Language_en_US(Tag TEXT NOT NULL PRIMARY KEY,Text TEXT,Gender TEXT,Plurality TEXT)"))
                throw std::runtime_error("Cannot create temporary diplomacy catalog");
            {
                Database::Results source,insert;
                if(!localization_.Execute(source,"SELECT Tag,Text,Gender,Plurality FROM LocalizedText WHERE Language='en_US' ORDER BY rowid") ||
                   !rules_.Execute(insert,"INSERT INTO temp.Language_en_US(Tag,Text,Gender,Plurality) VALUES(?1,?2,?3,?4)"))
                    throw std::runtime_error("Cannot prepare canonical diplomacy catalog copy");
                while(source.Step()) {
                    if(source.ColumnType(0)!=Database::COLTYPE_TEXT || !source.GetText(0) || !*source.GetText(0))
                        throw std::runtime_error("Canonical diplomacy catalog contains an invalid tag");
                    for(int column=0;column<4;++column) {
                        const auto type=source.ColumnType(column);
                        if(type!=Database::COLTYPE_TEXT && type!=Database::COLTYPE_NULL)
                            throw std::runtime_error("Canonical diplomacy catalog contains a non-text field");
                        const bool bound=type==Database::COLTYPE_NULL?insert.BindNULL(column+1):insert.Bind(column+1,source.GetText(column));
                        if(!bound)throw std::runtime_error("Cannot bind canonical diplomacy catalog field");
                    }
                    if(!insert.Execute() || !insert.Reset())
                        throw std::runtime_error("Cannot copy canonical diplomacy catalog row");
                    ++copied;
                }
                if((localization_.ErrorCode()!=0 && localization_.ErrorCode()!=101) || copied==0)
                    throw std::runtime_error("Canonical English diplomacy catalog is empty or unreadable");
            }
            {
                Database::Results count,query;
                if(!rules_.Execute(count,"SELECT COUNT(*) FROM temp.Language_en_US") || !count.Step() ||
                   count.GetInt64(0)!=static_cast<__int64>(copied))
                    throw std::runtime_error("Temporary diplomacy catalog row count differs from its source");
                if(!rules_.Execute(query,"select Tag, Bias from Diplomacy_Responses, Language_en_US where "
                    "(LeaderType = ? or LeaderType = 'GENERIC') and ResponseType = ? and Tag like Response"))
                    throw std::runtime_error("Original SDK diplomacy response query cannot prepare");
            }
            if(!rules_.Execute("RELEASE host_diplomacy_catalog"))
                throw std::runtime_error("Cannot finish temporary diplomacy catalog preparation");
        } catch(...) {
            rules_.Execute("ROLLBACK TO host_diplomacy_catalog");
            rules_.Execute("RELEASE host_diplomacy_catalog");
            throw;
        }
        std::printf("DIPLOMACY_CANONICAL_ENGLISH_CATALOG=%zu|temporary|en_US\n",copied);
    }
    void TraceNewGameServices() noexcept {
#if defined(ZEROSIS_NEW_GAME_TRACE)
        try{
            if(!state_)return;
            std::map<std::string,std::size_t> counts;
            for(const auto& event:state_->Events())
                if(event.compare(0,9,"platform-")==0 || event.compare(0,14,"gameplay-unit-")==0 ||
                   event.rfind("gameplay-combat:",0)==0)
                    ++counts[event];
            for(const auto& item:counts)
                std::printf("NEW_GAME_HOST_EVENT=%zu|%s\n",item.second,item.first.c_str());
            counts.clear();
            for(const auto& event:state_->Events())
                if(event.rfind("local-",0)==0 || event.rfind("ui-player-turn-",0)==0 ||
                   event.rfind("ui-active-player",0)==0 || event.rfind("gameplay-turn-changed",0)==0 ||
                   event.rfind("new-game-turn",0)==0)++counts[event];
            for(const auto& item:counts)std::printf("TURN_CYCLE_EVENT=%zu|%s\n",item.second,item.first.c_str());
        }catch(...){std::fputs("NEW_GAME_HOST_EVENT_TRACE_UNAVAILABLE\n",stderr);}
#endif
    }
    std::string ScriptObservation(int count,const char* localizedText) {
        EngineServices engine(state_);auto& service=*engine.GetScriptSystem();
        struct Probe {
            ICvEngineScriptSystem1& service;lua_State* vm=nullptr;ICvEngineScriptSystemArgs1* args=nullptr;
            ~Probe(){service.DestroyArgs(args);service.FreeLuaThread(vm);}
        } probe{service};
        state_->scripts->RegisterFile("host-probe.lua",
            "GameEvents.ZeroSisHostProbe.Add(function(count,label) assert(type(label)=='string'); return count+#label end)");
        probe.vm=service.CreateLuaThread("Host data diagnostics");probe.args=service.CreateArgs(2);
        if(!service.LoadFile(probe.vm,"host-probe.lua"))throw std::runtime_error(state_->scripts->LastError());
        probe.args->Push(count);const auto bytes=std::strlen(localizedText);probe.args->Push(localizedText,bytes);
        int value=-1;if(!service.CallAccumulator("ZeroSisHostProbe",probe.args,value))throw std::runtime_error(state_->scripts->LastError());
        return "SCRIPT_OBSERVATION="+std::to_string(count)+","+std::to_string(bytes)+","+std::to_string(value);
    }
    static void CloseDatabase(Database::Connection& connection) {
        connection.Close();
        // The SDK Close ABI is void. This provider returns -1 only when detached.
        if(connection.ErrorCode()!=-1)throw std::runtime_error("Database close is pending; live statements remain");
    }
    VerifiedBundle bundle_;
    Database::Connection rules_,localization_;
    WindowsModule module_;
    std::shared_ptr<HostState> state_;
    std::unique_ptr<UiPopupContext> popup_;
#if defined(ZEROSIS_UI_WINDOW_PRESENTATION)
    std::unique_ptr<InteractiveGameSession> interactive_;
#endif
    Session session_;
    CoreRuntimeProbe coreProbe_;
    NewGameProbe newGameProbe_;
    FirstTurnProbe firstTurnProbe_;
    HostTempHeap tempHeap_;
    std::wstring sessionDirectory_,oldDirectory_;
    bool dataTouched_=false,localizationTouched_=false,directoryChanged_=false;
};
}
