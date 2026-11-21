#pragma once
#include "SdkHostIncludes.h"
// Generated ABI declarations. Unsupported slots always identify and reject the call.
#pragma warning(push)
#pragma warning(disable:4100) // SDK parameter names are retained for review.
namespace ZeroSisHost {
class EngineServicesBase : public ICvEngineUtility4 {
public:
    void* DLLCALL QueryInterface(GUID guidInterface) override { Unsupported("ICvUnknown::QueryInterface"); }
    void DLLCALL Destroy() override { Unsupported("ICvUnknown::Destroy"); }
    CvDLLInterfaceIFaceBase* getInterfaceIFace() override { Unsupported("ICvEngineUtility1::getInterfaceIFace"); }
    ICvEngineScriptSystem1* GetScriptSystem() override { Unsupported("ICvEngineUtility1::GetScriptSystem"); }
    void reset() override { Unsupported("ICvEngineUtility1::reset"); }
    void DoMapSetup(int iWorldNumPlots) override { Unsupported("ICvEngineUtility1::DoMapSetup"); }
    void DoTurn() override { Unsupported("ICvEngineUtility1::DoTurn"); }
    bool IsHost() const override { Unsupported("ICvEngineUtility1::IsHost"); }
    bool IsPlayerConnected(PlayerTypes playerId) override { Unsupported("ICvEngineUtility1::IsPlayerConnected"); }
    Database::Connection* GetModsDatabase() override { Unsupported("ICvEngineUtility1::GetModsDatabase"); }
    bool IsModActivated(_In_z_ const char* szModID) override { Unsupported("ICvEngineUtility1::IsModActivated"); }
    bool IsModActivated(_In_z_ const char* szModID, int iVersion) override { Unsupported("ICvEngineUtility1::IsModActivated"); }
    bool IsDLCValid(const GUID& kID) const override { Unsupported("ICvEngineUtility1::IsDLCValid"); }
    int getAssignedNetworkID(int iPlayerID) override { Unsupported("ICvEngineUtility1::getAssignedNetworkID"); }
    bool IsPitbossHost() const override { Unsupported("ICvEngineUtility1::IsPitbossHost"); }
    CvString GetPitbossSmtpHost() const override { Unsupported("ICvEngineUtility1::GetPitbossSmtpHost"); }
    CvString GetPitbossSmtpLogin() const override { Unsupported("ICvEngineUtility1::GetPitbossSmtpLogin"); }
    CvString GetPitbossSmtpPassword() const override { Unsupported("ICvEngineUtility1::GetPitbossSmtpPassword"); }
    CvString GetPitbossEmail() const override { Unsupported("ICvEngineUtility1::GetPitbossEmail"); }
    void netMessageDebugLog(const std::string & logMessage) const override { Unsupported("ICvEngineUtility1::netMessageDebugLog"); }
    void sendPlayerInfo(PlayerTypes eActivePlayer) override { Unsupported("ICvEngineUtility1::sendPlayerInfo"); }
    void sendGameInfo(const CvString& szGameName, const CvString& szAdminPassword) override { Unsupported("ICvEngineUtility1::sendGameInfo"); }
    void sendPlayerOption(PlayerOptionTypes eOption, bool bValue) override { Unsupported("ICvEngineUtility1::sendPlayerOption"); }
    void sendExtendedGame() override { Unsupported("ICvEngineUtility1::sendExtendedGame"); }
    void SendFoundPantheon(PlayerTypes ePlayer, BeliefTypes eBelief) override { Unsupported("ICvEngineUtility1::SendFoundPantheon"); }
    void SendFoundReligion(PlayerTypes ePlayer, ReligionTypes eReligion, const char* szCustomName, BeliefTypes eBelief1, BeliefTypes eBelief2, BeliefTypes eBelief3, BeliefTypes eBelief4, int iCityX, int iCityY) override { Unsupported("ICvEngineUtility1::SendFoundReligion"); }
    void SendEnhanceReligion(PlayerTypes ePlayer, ReligionTypes eReligion, const char* szCustomName, BeliefTypes eBelief1, BeliefTypes eBelief2, int iCityX, int iCityY) override { Unsupported("ICvEngineUtility1::SendEnhanceReligion"); }
    void SendMoveSpy(PlayerTypes ePlayer, int iSpyIndex, int iTargetPlayer, int iTargetCity, bool bAsDiplomat) override { Unsupported("ICvEngineUtility1::SendMoveSpy"); }
    void SendStageCoup(PlayerTypes eSpyPlayer, int iSpyIndex) override { Unsupported("ICvEngineUtility1::SendStageCoup"); }
    void SendFaithPurchase(PlayerTypes ePlayer, FaithPurchaseTypes eFaithPurchaseType, int iFaithPurchaseIndex) override { Unsupported("ICvEngineUtility1::SendFaithPurchase"); }
    void sendAutoMoves() override { Unsupported("ICvEngineUtility1::sendAutoMoves"); }
    void sendTurnComplete() override { Unsupported("ICvEngineUtility1::sendTurnComplete"); }
    bool HasSentTurnComplete() override { Unsupported("ICvEngineUtility1::HasSentTurnComplete"); }
    bool HasReceivedTurnComplete(PlayerTypes ePlayer) override { Unsupported("ICvEngineUtility1::HasReceivedTurnComplete"); }
    bool HasSentTurnAllComplete() override { Unsupported("ICvEngineUtility1::HasSentTurnAllComplete"); }
    bool HasReceivedTurnAllComplete(PlayerTypes ePlayer) override { Unsupported("ICvEngineUtility1::HasReceivedTurnAllComplete"); }
    bool HasReceivedTurnAllCompleteFromAllPlayers() override { Unsupported("ICvEngineUtility1::HasReceivedTurnAllCompleteFromAllPlayers"); }
    bool sendTurnUnready() override { Unsupported("ICvEngineUtility1::sendTurnUnready"); }
    void sendPushMission(int iUnitID, MissionTypes eMission, int iData1, int iData2, int iFlags, bool bShift) override { Unsupported("ICvEngineUtility1::sendPushMission"); }
    void sendAutoMission(int iUnitID) override { Unsupported("ICvEngineUtility1::sendAutoMission"); }
    void sendDoCommand(int iUnitID, CommandTypes eCommand, int iData1, int iData2, bool bAlt) override { Unsupported("ICvEngineUtility1::sendDoCommand"); }
    void sendPushOrder(int iCityID, OrderTypes eOrder, int iData, bool bAlt, bool bShift, bool bCtrl) override { Unsupported("ICvEngineUtility1::sendPushOrder"); }
    void sendPopOrder(int iCity, int iNum) override { Unsupported("ICvEngineUtility1::sendPopOrder"); }
    void sendSwapOrder(int iCity, int iNum0) override { Unsupported("ICvEngineUtility1::sendSwapOrder"); }
    void sendPurchase(int iCity, UnitTypes eUnitType, BuildingTypes eBuildingType, ProjectTypes eProjectType) override { Unsupported("ICvEngineUtility1::sendPurchase"); }
    void sendDoTask(int iCity, TaskTypes eTask, int iData1, int iData2, bool bOption, bool bAlt, bool bShift, bool bCtrl) override { Unsupported("ICvEngineUtility1::sendDoTask"); }
    void sendResearch(TechTypes eTech, int iDiscover, PlayerTypes ePlayerToStealFrom, bool bShift) override { Unsupported("ICvEngineUtility1::sendResearch"); }
    void sendChat(const CvString& szChatString, ChatTargetTypes eTargetType, PlayerTypes toWho) override { Unsupported("ICvEngineUtility1::sendChat"); }
    void sendPing(int iX, int iY) override { Unsupported("ICvEngineUtility1::sendPing"); }
    void sendPause(int iPauseID = -1) override { Unsupported("ICvEngineUtility1::sendPause"); }
    void sendChangeWar(TeamTypes iRivalTeam, bool bWar) override { Unsupported("ICvEngineUtility1::sendChangeWar"); }
    void sendIgnoreWarning(TeamTypes iRivalTeam) override { Unsupported("ICvEngineUtility1::sendIgnoreWarning"); }
    void SendPledgeMinorProtection(PlayerTypes eMinor, bool bValue) override { Unsupported("ICvEngineUtility1::SendPledgeMinorProtection"); }
    void SendMinorNoUnitSpawning(PlayerTypes eMinor, bool bValue) override { Unsupported("ICvEngineUtility1::SendMinorNoUnitSpawning"); }
    void SendLiberateMinor(PlayerTypes eMinor, int iCityID) override { Unsupported("ICvEngineUtility1::SendLiberateMinor"); }
    void sendUpdatePolicies(bool bNOTPolicyBranch, int iID, bool bValue) override { Unsupported("ICvEngineUtility1::sendUpdatePolicies"); }
    void SendDiploVote(PlayerTypes eVotePlayer) override { Unsupported("ICvEngineUtility1::SendDiploVote"); }
    void sendLaunch(PlayerTypes ePlayer, VictoryTypes eVictory) override { Unsupported("ICvEngineUtility1::sendLaunch"); }
    void sendAdvancedStartAction(AdvancedStartActionTypes eAction, PlayerTypes ePlayer, int iX, int iY, int iData, bool bAdd) override { Unsupported("ICvEngineUtility1::sendAdvancedStartAction"); }
    void sendMinorCivQuestNoInterest(PlayerTypes eMinor, bool bPeace) override { Unsupported("ICvEngineUtility1::sendMinorCivQuestNoInterest"); }
    void sendMinorCivQuestCompleted(PlayerTypes eMinor, bool bPeace) override { Unsupported("ICvEngineUtility1::sendMinorCivQuestCompleted"); }
    void sendMinorCivIntrusion(PlayerTypes eMinor, int iOptionChosen) override { Unsupported("ICvEngineUtility1::sendMinorCivIntrusion"); }
    void sendMinorCivEnterTerritory(PlayerTypes eMinor) override { Unsupported("ICvEngineUtility1::sendMinorCivEnterTerritory"); }
    void sendBarbarianRansom(int iOptionChosen, int iUnitID) override { Unsupported("ICvEngineUtility1::sendBarbarianRansom"); }
    void sendGiftUnit(PlayerTypes eMinor, int iUnitID) override { Unsupported("ICvEngineUtility1::sendGiftUnit"); }
    void sendReturnCivilian(bool bReturn, PlayerTypes ePlayer, int iUnitID) override { Unsupported("ICvEngineUtility1::sendReturnCivilian"); }
    void SendUpdateCityCitizens(int iCityID) override { Unsupported("ICvEngineUtility1::SendUpdateCityCitizens"); }
    void SendSellBuilding(int iCityID, BuildingTypes eBuilding) override { Unsupported("ICvEngineUtility1::SendSellBuilding"); }
    void SendRenameCity (int iCityID, CvString szNewName) override { Unsupported("ICvEngineUtility1::SendRenameCity"); }
    void SendRenameUnit (int iUnitID, CvString szNewName) override { Unsupported("ICvEngineUtility1::SendRenameUnit"); }
    void sendPlayerHurry(HurryTypes eHurry) override { Unsupported("ICvEngineUtility1::sendPlayerHurry"); }
    void sendSwapUnits(int iUnitID, MissionTypes eMission, int iData1, int iData2, int iFlags, bool bShift) override { Unsupported("ICvEngineUtility1::sendSwapUnits"); }
    void sendCityBuyPlot (int iCityID, int iX, int iY) override { Unsupported("ICvEngineUtility1::sendCityBuyPlot"); }
    void sendMinorPledgeProtection(PlayerTypes eMajor, PlayerTypes eMinor, bool bProtect, bool bPledgeNowBroken) override { Unsupported("ICvEngineUtility1::sendMinorPledgeProtection"); }
    void sendMinorGiftGold(PlayerTypes eMinor, int iGold) override { Unsupported("ICvEngineUtility1::sendMinorGiftGold"); }
    void sendMinorGiftTileImprovement(PlayerTypes eMajor, PlayerTypes eMinor, int iPlotX, int iPlotY) override { Unsupported("ICvEngineUtility1::sendMinorGiftTileImprovement"); }
    void sendMinorBullyGold(PlayerTypes eBully, PlayerTypes eMinor, int iGold) override { Unsupported("ICvEngineUtility1::sendMinorBullyGold"); }
    void sendMinorBullyUnit(PlayerTypes eBully, PlayerTypes eMinor, UnitTypes eUnitType) override { Unsupported("ICvEngineUtility1::sendMinorBullyUnit"); }
    void sendMinorBuyout(PlayerTypes eMajor, PlayerTypes eMinor) override { Unsupported("ICvEngineUtility1::sendMinorBuyout"); }
    void sendGreatPersonChoice(PlayerTypes ePlayer, UnitTypes eUnit) override { Unsupported("ICvEngineUtility1::sendGreatPersonChoice"); }
    void sendMayaBonusChoice(PlayerTypes ePlayer, UnitTypes eUnit) override { Unsupported("ICvEngineUtility1::sendMayaBonusChoice"); }
    void sendFaithGreatPersonChoice(PlayerTypes ePlayer, UnitTypes eUnit) override { Unsupported("ICvEngineUtility1::sendFaithGreatPersonChoice"); }
    void sendSetCityAIFocus (int iCityID, CityAIFocusTypes eFocus) override { Unsupported("ICvEngineUtility1::sendSetCityAIFocus"); }
    void sendSetCityAvoidGrowth (int iCityID, bool bAvoidGrowth) override { Unsupported("ICvEngineUtility1::sendSetCityAvoidGrowth"); }
    void sendUnitSyncCheck(PlayerTypes playerId, int unitId, FMemoryStream & syncArchiveData, const std::vector<std::pair<std::string, std::string> > &) const override { Unsupported("ICvEngineUtility1::sendUnitSyncCheck"); }
    void sendPlotSyncCheck(PlayerTypes playerId, short plotX, short plotY, FMemoryStream & syncArchiveData, const std::vector<std::pair<std::string, std::string> > &) const override { Unsupported("ICvEngineUtility1::sendPlotSyncCheck"); }
    void sendCitySyncCheck(PlayerTypes playerId, int cityId, FMemoryStream & syncArchiveData, const std::vector<std::pair<std::string, std::string> > &) const override { Unsupported("ICvEngineUtility1::sendCitySyncCheck"); }
    void sendRandomNumberGeneratorSyncCheck(PlayerTypes playerId, ICvRandom1* pRandomNumberGenerator) const override { Unsupported("ICvEngineUtility1::sendRandomNumberGeneratorSyncCheck"); }
    void sendPlayerSyncCheck(PlayerTypes playerId, FMemoryStream & syncData, const std::vector<std::pair<std::string, std::string> > &) const override { Unsupported("ICvEngineUtility1::sendPlayerSyncCheck"); }
    void sendFromUIDiploEvent(PlayerTypes eOtherPlayer, FromUIDiploEventTypes eEvent, int iArg1, int iArg2) override { Unsupported("ICvEngineUtility1::sendFromUIDiploEvent"); }
    void sendNetDealAccepted(PlayerTypes fromPlayer, PlayerTypes toPlayer, ICvDeal1* pDeal, int iDealValueToMe, int iValueImOffering, int iValueTheyreOffering) const override { Unsupported("ICvEngineUtility1::sendNetDealAccepted"); }
    void sendNetDemandAccepted(PlayerTypes fromPlayer, PlayerTypes toPlayer, ICvDeal1* pDeal) const override { Unsupported("ICvEngineUtility1::sendNetDemandAccepted"); }
    void sendTurnReminder(PlayerTypes toPlayer) override { Unsupported("ICvEngineUtility1::sendTurnReminder"); }
    void sendGoodyChoice(PlayerTypes ePlayerID, int iPlotX, int iPlotY, GoodyTypes eGoody, int iUnitID) override { Unsupported("ICvEngineUtility1::sendGoodyChoice"); }
    void sendSetSwappableGreatWork(PlayerTypes ePlayer, int iWorkClass, int iWorkIndex) override { Unsupported("ICvEngineUtility1::sendSetSwappableGreatWork"); }
    void sendSwapGreatWorks(PlayerTypes ePlayer1, int iWork1, PlayerTypes ePlayer2, int iWork2) override { Unsupported("ICvEngineUtility1::sendSwapGreatWorks"); }
    void sendMoveGreatWorks(PlayerTypes ePlayer, int iCity1, int iBuildingClass1, int iWorkIndex1, int iCity2, int iBuildingClass2, int iWorkIndex2) override { Unsupported("ICvEngineUtility1::sendMoveGreatWorks"); }
    void netDisconnect() override { Unsupported("ICvEngineUtility1::netDisconnect"); }
    void sendPlayerInitialAIProcessed() const override { Unsupported("ICvEngineUtility1::sendPlayerInitialAIProcessed"); }
    void hotJoinComplete() const override { Unsupported("ICvEngineUtility1::hotJoinComplete"); }
    bool allAIProcessedThisTurn() const override { Unsupported("ICvEngineUtility1::allAIProcessedThisTurn"); }
    int getMillisecsPerTurn() override { Unsupported("ICvEngineUtility1::getMillisecsPerTurn"); }
    float getSecsPerTurn() override { Unsupported("ICvEngineUtility1::getSecsPerTurn"); }
    int getTurnsPerSecond() override { Unsupported("ICvEngineUtility1::getTurnsPerSecond"); }
    int getTurnsPerMinute() override { Unsupported("ICvEngineUtility1::getTurnsPerMinute"); }
    bool CanAdvanceTurn() override { Unsupported("ICvEngineUtility1::CanAdvanceTurn"); }
    void openSlot(PlayerTypes eID) override { Unsupported("ICvEngineUtility1::openSlot"); }
    void closeSlot(PlayerTypes eID) override { Unsupported("ICvEngineUtility1::closeSlot"); }
    CvString getMapScriptName() override { Unsupported("ICvEngineUtility1::getMapScriptName"); }
    bool getTransferredMap() override { Unsupported("ICvEngineUtility1::getTransferredMap"); }
    bool isWBMapScript() override { Unsupported("ICvEngineUtility1::isWBMapScript"); }
    bool isWBMapNoPlayers() override { Unsupported("ICvEngineUtility1::isWBMapNoPlayers"); }
    CvString getPlayerName(int iIndex, uint uiForm = 0) override { Unsupported("ICvEngineUtility1::getPlayerName"); }
    CvString getPlayerNameKey(int iIndex) override { Unsupported("ICvEngineUtility1::getPlayerNameKey"); }
    CvString getPlayerDisplayNickName(int iIndex) override { Unsupported("ICvEngineUtility1::getPlayerDisplayNickName"); }
    CvString getCivDescription(int iIndex, uint uiForm = 0) override { Unsupported("ICvEngineUtility1::getCivDescription"); }
    CvString getCivDescriptionKey(int iIndex) override { Unsupported("ICvEngineUtility1::getCivDescriptionKey"); }
    CvString getCivShortDesc(int iIndex, uint uiForm = 0) override { Unsupported("ICvEngineUtility1::getCivShortDesc"); }
    CvString getCivShortDescKey(int iIndex) override { Unsupported("ICvEngineUtility1::getCivShortDescKey"); }
    CvString getCivAdjective(int iIndex, uint uiForm = 0) override { Unsupported("ICvEngineUtility1::getCivAdjective"); }
    CvString getCivAdjectiveKey(int iIndex) override { Unsupported("ICvEngineUtility1::getCivAdjectiveKey"); }
    void stripSpecialCharacters(CvString& szName) override { Unsupported("ICvEngineUtility1::stripSpecialCharacters"); }
    void InitGlobals() override { Unsupported("ICvEngineUtility1::InitGlobals"); }
    void UninitGlobals() override { Unsupported("ICvEngineUtility1::UninitGlobals"); }
    void SetDone(bool bDone) override { Unsupported("ICvEngineUtility1::SetDone"); }
    bool GetDone() override { Unsupported("ICvEngineUtility1::GetDone"); }
    bool GetAutorun() override { Unsupported("ICvEngineUtility1::GetAutorun"); }
    int GetAudioTagIndex(const char* szTag, int iScriptType = -1) override { Unsupported("ICvEngineUtility1::GetAudioTagIndex"); }
    bool altKey() override { Unsupported("ICvEngineUtility1::altKey"); }
    bool shiftKey() override { Unsupported("ICvEngineUtility1::shiftKey"); }
    bool ctrlKey() override { Unsupported("ICvEngineUtility1::ctrlKey"); }
    void EnumerateFiles(EnumeratedFilesList& files, const char* szFolder, const size_t lenFolder, const char* szPattern, const size_t lenPattern, const bool bRecursive = false) override { Unsupported("ICvEngineUtility1::EnumerateFiles"); }
    void ReleaseEnumeratedFilesList(EnumeratedFilesList &files) override { Unsupported("ICvEngineUtility1::ReleaseEnumeratedFilesList"); }
    void SaveGame(SaveGameTypes eSaveGame) override { Unsupported("ICvEngineUtility1::SaveGame"); }
    void LoadGame() override { Unsupported("ICvEngineUtility1::LoadGame"); }
    void AutoSave(bool bInitial = false, bool bPostTurn = false) override { Unsupported("ICvEngineUtility1::AutoSave"); }
    bool saveReplay() override { Unsupported("ICvEngineUtility1::saveReplay"); }
    void QuickSave() override { Unsupported("ICvEngineUtility1::QuickSave"); }
    void QuickLoad() override { Unsupported("ICvEngineUtility1::QuickLoad"); }
    void sendPbemTurn(PlayerTypes ePlayer) override { Unsupported("ICvEngineUtility1::sendPbemTurn"); }
    void getPassword(PlayerTypes ePlayer) override { Unsupported("ICvEngineUtility1::getPassword"); }
    void RestartGame() override { Unsupported("ICvEngineUtility1::RestartGame"); }
    bool getPlayerOption(PlayerOptionTypes ePlayerOption) override { Unsupported("ICvEngineUtility1::getPlayerOption"); }
    const char* GetCacheFolderPath() override { Unsupported("ICvEngineUtility1::GetCacheFolderPath"); }
    void GameplayEraChanged(PlayerTypes playerID, EraTypes newEra) override { Unsupported("ICvEngineUtility1::GameplayEraChanged"); }
    void GameplayBridgeChanged(bool bBridge, unsigned char newBridgeStyle) override { Unsupported("ICvEngineUtility1::GameplayBridgeChanged"); }
    void GameplayUnitCreated(_In_ ICvUnit1* pThisUnit) override { Unsupported("ICvEngineUtility1::GameplayUnitCreated"); }
    void GameplayUnitMoved(_In_ ICvUnit1* pThisUnit, const CvPlotIndexVector& kPlots) override { Unsupported("ICvEngineUtility1::GameplayUnitMoved"); }
    void GameplayUnitTeleported(_In_ ICvUnit1* pThisUnit, _In_ ICvPlot1* pThisPlot) override { Unsupported("ICvEngineUtility1::GameplayUnitTeleported"); }
    void GameplayUnitDestroyed(_In_ ICvUnit1* pThisUnit) override { Unsupported("ICvEngineUtility1::GameplayUnitDestroyed"); }
    void GameplayUnitDestroyedInCombat(_In_ ICvUnit1* pUnit) override { Unsupported("ICvEngineUtility1::GameplayUnitDestroyedInCombat"); }
    void GameplayUnitSetDamage(_In_ ICvUnit1* pThisUnit, int iDamage, int iPreviousDamage) override { Unsupported("ICvEngineUtility1::GameplayUnitSetDamage"); }
    void GameplayUnitFortify(_In_ ICvUnit1* pThisUnit, bool bFortify) override { Unsupported("ICvEngineUtility1::GameplayUnitFortify"); }
    void GameplayUnitWork(_In_ ICvUnit1* pThisUnit, int iWorkType) override { Unsupported("ICvEngineUtility1::GameplayUnitWork"); }
    void GameplayUnitParadrop(_In_ ICvUnit1* pThisUnit) override { Unsupported("ICvEngineUtility1::GameplayUnitParadrop"); }
    void GameplayUnitActivate(_In_ ICvUnit1* pThisUnit) override { Unsupported("ICvEngineUtility1::GameplayUnitActivate"); }
    void GameplayUnitEmbark(_In_ ICvUnit1* pThisUnit, bool bEmbark) override { Unsupported("ICvEngineUtility1::GameplayUnitEmbark"); }
    void GameplayUnitGarrison(_In_ ICvUnit1* pThisUnit, bool bGarrison) override { Unsupported("ICvEngineUtility1::GameplayUnitGarrison"); }
    void GameplayUnitShouldDimFlag(_In_ ICvUnit1* pThisUnit, bool bDim) override { Unsupported("ICvEngineUtility1::GameplayUnitShouldDimFlag"); }
    void GameplayUnitMarkThreatening(_In_ ICvUnit1* pThisUnit, bool bMark) override { Unsupported("ICvEngineUtility1::GameplayUnitMarkThreatening"); }
    void GameplayUnitVisibility(_In_ ICvUnit1* pThisUnit, bool bVisible, bool bChangeInvisibility = false, const float fBlendTime = 0.5f) override { Unsupported("ICvEngineUtility1::GameplayUnitVisibility"); }
    uint GameplayUnitCombat(_In_ ICvCombatInfo1* pCombatInfo) override { Unsupported("ICvEngineUtility1::GameplayUnitCombat"); }
    void GameplayCityCreated(_In_ ICvCity1* pThisCity, EraTypes eCurrentEra) override { Unsupported("ICvEngineUtility1::GameplayCityCreated"); }
    void GameplayCityDestroyed(_In_ ICvCity1* pThisCity, PlayerTypes eNewOwner) override { Unsupported("ICvEngineUtility1::GameplayCityDestroyed"); }
    void GameplayCityCaptured(_In_ ICvCity1* pThisCity, PlayerTypes eNewOwner) override { Unsupported("ICvEngineUtility1::GameplayCityCaptured"); }
    void GameplayCitySetDamage(_In_ ICvCity1* pThisCity, int iDamage, int iPreviousDamage) override { Unsupported("ICvEngineUtility1::GameplayCitySetDamage"); }
    void GameplayCityPopulationChanged(_In_ ICvCity1* pThisCity, int newPopulation) override { Unsupported("ICvEngineUtility1::GameplayCityPopulationChanged"); }
    uint GameplayCityCombat(_In_ ICvCombatInfo1* pInfo) override { Unsupported("ICvEngineUtility1::GameplayCityCombat"); }
    void GameplayUnitMissionEnd(_In_ ICvUnit1* pThisUnit) override { Unsupported("ICvEngineUtility1::GameplayUnitMissionEnd"); }
    void GameplayUnitRebased(_In_ ICvUnit1* pThisUnit, _In_ ICvPlot1* pOldPlot, _In_ ICvPlot1* pThisPlot) override { Unsupported("ICvEngineUtility1::GameplayUnitRebased"); }
    void GameplayUnitResetAnimationState(_In_ ICvUnit1* pThisUnit) override { Unsupported("ICvEngineUtility1::GameplayUnitResetAnimationState"); }
    void GameplayTechAcquired(TeamTypes eTeam, TechTypes eTech) override { Unsupported("ICvEngineUtility1::GameplayTechAcquired"); }
    void GameplayFeatureChanged(_In_ ICvPlot1* pThisPlot, FeatureTypes newFeature) override { Unsupported("ICvEngineUtility1::GameplayFeatureChanged"); }
    void GameplayPlotStateChange(_In_ const ICvPlot1* pThisPlot, const ResourceTypes eRevealedResource, const ImprovementTypes eRevealedImprovement, const int iRevealedImprovementState, const RouteTypes eRevealedRoute, const int iRouteState) override { Unsupported("ICvEngineUtility1::GameplayPlotStateChange"); }
    void GameplayPlotIconStateChange(_In_ const ICvPlot1* pThisPlot, const ResourceTypes eRevealedResource, const ImprovementTypes eRevealedImprovement, const int iRevealedImprovementState) override { Unsupported("ICvEngineUtility1::GameplayPlotIconStateChange"); }
    void GameplayNaturalWonderRevealed(_In_ ICvPlot1* pThisPlot) override { Unsupported("ICvEngineUtility1::GameplayNaturalWonderRevealed"); }
    void GameplayWallCreated(_In_ ICvPlot1* pThisPlot) override { Unsupported("ICvEngineUtility1::GameplayWallCreated"); }
    void GameplayDoFX(_In_opt_ ICvPlot1* pThisPlot, int iFXType = -1) override { Unsupported("ICvEngineUtility1::GameplayDoFX"); }
    void GameplayFOWChanged(int x, int y, int eFOWType, bool bSetAll) override { Unsupported("ICvEngineUtility1::GameplayFOWChanged"); }
    void GameplayYieldMightHaveChanged(_In_ ICvPlot1* pThisPlot) override { Unsupported("ICvEngineUtility1::GameplayYieldMightHaveChanged"); }
    void NotifyAILeadersInGame() override { Unsupported("ICvEngineUtility1::NotifyAILeadersInGame"); }
    void NotifySpecificAILeaderInGame(PlayerTypes ePlayer) override { Unsupported("ICvEngineUtility1::NotifySpecificAILeaderInGame"); }
    void GameplayWarStateChanged(TeamTypes eTeam1, TeamTypes eTeam2, bool bWar) override { Unsupported("ICvEngineUtility1::GameplayWarStateChanged"); }
    void DoClearDiplomacyTradeTable() override { Unsupported("ICvEngineUtility1::DoClearDiplomacyTradeTable"); }
    void GameplayDiplomacyAILeaderMessage(PlayerTypes ePlayer, DiploUIStateTypes eDiploUIState, const char* szLeaderMessage, LeaderheadAnimationTypes eAction, int iData1 = -1) override { Unsupported("ICvEngineUtility1::GameplayDiplomacyAILeaderMessage"); }
    void GameplayMetTeam(TeamTypes eMyTeam, TeamTypes eTheirTeam) override { Unsupported("ICvEngineUtility1::GameplayMetTeam"); }
    void NetMessageDebug(const std::string &) const override { Unsupported("ICvEngineUtility1::NetMessageDebug"); }
    void endTurnTimerLength(float lengthInSeconds) override { Unsupported("ICvEngineUtility1::endTurnTimerLength"); }
    float endTurnTimerLength() const override { Unsupported("ICvEngineUtility1::endTurnTimerLength"); }
    void GameplayWonderCreated(PlayerTypes ePlayerID, _In_ ICvPlot1* pThisPlot, BuildingTypes eBuildingIndex, int iState) override { Unsupported("ICvEngineUtility1::GameplayWonderCreated"); }
    void GameplayWonderEdited(PlayerTypes ePlayerID, _In_ ICvPlot1* pThisPlot, BuildingTypes eBuildingIndex, int iState) override { Unsupported("ICvEngineUtility1::GameplayWonderEdited"); }
    void GameplayWonderRemoved(PlayerTypes ePlayerID, _In_ ICvPlot1* pThisPlot, BuildingTypes eBuildingIndex) override { Unsupported("ICvEngineUtility1::GameplayWonderRemoved"); }
    void GameplaySpaceshipCreated(_In_ ICvPlot1* pThisPlot, int iState) override { Unsupported("ICvEngineUtility1::GameplaySpaceshipCreated"); }
    void GameplaySpaceshipEdited(_In_ ICvPlot1* pThisPlot, int iState) override { Unsupported("ICvEngineUtility1::GameplaySpaceshipEdited"); }
    void GameplaySpaceshipRemoved(_In_ ICvPlot1* pThisPlot) override { Unsupported("ICvEngineUtility1::GameplaySpaceshipRemoved"); }
    void GameplayOpenOptionsScreen() override { Unsupported("ICvEngineUtility1::GameplayOpenOptionsScreen"); }
    void GameplaySearchForPediaEntry(const char * c) override { Unsupported("ICvEngineUtility1::GameplaySearchForPediaEntry"); }
    void GameplayOpenInfoCorner(int iInfoCornerID) override { Unsupported("ICvEngineUtility1::GameplayOpenInfoCorner"); }
    void GameplayWorldAnchor(GenericWorldAnchorTypes eAnchor, bool bAdd, int iX, int iY, int iData1) override { Unsupported("ICvEngineUtility1::GameplayWorldAnchor"); }
    void GameplayMinimapUnitSelect(int iX, int iY) override { Unsupported("ICvEngineUtility1::GameplayMinimapUnitSelect"); }
    void GameplayMinimapNotification(int iX, int iY, int iID) override { Unsupported("ICvEngineUtility1::GameplayMinimapNotification"); }
    void GameplayGoldenAgeStarted() override { Unsupported("ICvEngineUtility1::GameplayGoldenAgeStarted"); }
    void GameplayGoldenAgeEnded() override { Unsupported("ICvEngineUtility1::GameplayGoldenAgeEnded"); }
    void GameplayTurnChanged(int iNewTurn) override { Unsupported("ICvEngineUtility1::GameplayTurnChanged"); }
    void GameplayActivePlayerChanged(PlayerTypes eNewPlayer) override { Unsupported("ICvEngineUtility1::GameplayActivePlayerChanged"); }
    void PublishActivePlayer(PlayerTypes ePlayer, PlayerTypes eOldPlayer) override { Unsupported("ICvEngineUtility1::PublishActivePlayer"); }
    void PublishNewGameTurn(int gameTurn) override { Unsupported("ICvEngineUtility1::PublishNewGameTurn"); }
    void UnlockAchievement(EAchievement eAchievement) override { Unsupported("ICvEngineUtility1::UnlockAchievement"); }
    bool IsAchievementUnlocked(EAchievement eAchievement) const override { Unsupported("ICvEngineUtility1::IsAchievementUnlocked"); }
    bool GetSteamStat(ESteamStat eStat, int32 * pStat) const override { Unsupported("ICvEngineUtility1::GetSteamStat"); }
    bool SetSteamStat(ESteamStat eStat, int32 nStat) override { Unsupported("ICvEngineUtility1::SetSteamStat"); }
    bool IncrementSteamStat(ESteamStat eStat) override { Unsupported("ICvEngineUtility1::IncrementSteamStat"); }
    bool IncrementSteamStatAndUnlock(ESteamStat eStat, int nThreshold, EAchievement eAchievement) override { Unsupported("ICvEngineUtility1::IncrementSteamStatAndUnlock"); }
    void SetAdvisorBadAttackInterrupt (bool bValue) override { Unsupported("ICvEngineUtility1::SetAdvisorBadAttackInterrupt"); }
    bool GetAdvisorBadAttackInterrupt (void) override { Unsupported("ICvEngineUtility1::GetAdvisorBadAttackInterrupt"); }
    void SetAdvisorCityAttackInterrupt (bool bValue) override { Unsupported("ICvEngineUtility1::SetAdvisorCityAttackInterrupt"); }
    bool GetAdvisorCityAttackInterrupt (void) override { Unsupported("ICvEngineUtility1::GetAdvisorCityAttackInterrupt"); }
    int GetTutorialLevel (void) override { Unsupported("ICvEngineUtility1::GetTutorialLevel"); }
    void ReseatPlayer(PlayerTypes p, bool bClosePlayersOldSlot=false) const override { Unsupported("ICvEngineUtility1::ReseatPlayer"); }
    bool IsNetPlayer(PlayerTypes p) const override { Unsupported("ICvEngineUtility1::IsNetPlayer"); }
    void SendGameDoTurnProcessed() const override { Unsupported("ICvEngineUtility1::SendGameDoTurnProcessed"); }
    bool RecordVictoryInformation(int score) override { Unsupported("ICvEngineUtility1::RecordVictoryInformation"); }
    bool RecordLeaderboardScore(int score) override { Unsupported("ICvEngineUtility1::RecordLeaderboardScore"); }
    bool TunerConnected() override { Unsupported("ICvEngineUtility1::TunerConnected"); }
    bool TunerEverConnected() override { Unsupported("ICvEngineUtility1::TunerEverConnected"); }
    void PublishEraChanges() override { Unsupported("ICvEngineUtility1::PublishEraChanges"); }
    void RecordGameCoreMessages(bool bRecord) override { Unsupported("ICvEngineUtility1::RecordGameCoreMessages"); }
    bool IsProcessingGameCoreMessages() override { Unsupported("ICvEngineUtility1::IsProcessingGameCoreMessages"); }
    void GetGameCoreLock() override { Unsupported("ICvEngineUtility1::GetGameCoreLock"); }
    void ReleaseGameCoreLock() override { Unsupported("ICvEngineUtility1::ReleaseGameCoreLock"); }
    bool TryGameCoreLock() override { Unsupported("ICvEngineUtility1::TryGameCoreLock"); }
    bool HasGameCoreLock() override { Unsupported("ICvEngineUtility1::HasGameCoreLock"); }
    bool IsGameCoreThread() override { Unsupported("ICvEngineUtility1::IsGameCoreThread"); }
    bool IsGameCoreExecuting() override { Unsupported("ICvEngineUtility1::IsGameCoreExecuting"); }
    void sendPurchase(int iCity, UnitTypes eUnitType, BuildingTypes eBuildingType, ProjectTypes eProjectType, int ePurchaseYield) override { Unsupported("ICvEngineUtility2::sendPurchase"); }
    bool ReseatConnectedPlayer(PlayerTypes p) const override { Unsupported("ICvEngineUtility2::ReseatConnectedPlayer"); }
    void SendLeagueVoteEnact(LeagueTypes eLeague, int iResolutionID, PlayerTypes eVoter, int iNumVotes, int iChoice) override { Unsupported("ICvEngineUtility3::SendLeagueVoteEnact"); }
    void SendLeagueVoteRepeal(LeagueTypes eLeague, int iResolutionID, PlayerTypes eVoter, int iNumVotes, int iChoice) override { Unsupported("ICvEngineUtility3::SendLeagueVoteRepeal"); }
    void SendLeagueVoteAbstain(LeagueTypes eLeague, PlayerTypes eVoter, int iNumVotes) override { Unsupported("ICvEngineUtility3::SendLeagueVoteAbstain"); }
    void SendLeagueProposeEnact(LeagueTypes eLeague, ResolutionTypes eResolution, PlayerTypes eProposer, int iChoice) override { Unsupported("ICvEngineUtility3::SendLeagueProposeEnact"); }
    void SendLeagueProposeRepeal(LeagueTypes eLeague, int iResolutionID, PlayerTypes eProposer) override { Unsupported("ICvEngineUtility3::SendLeagueProposeRepeal"); }
    void SendLeagueEditName(LeagueTypes eLeague, PlayerTypes ePlayer, const char* szCustomName) override { Unsupported("ICvEngineUtility3::SendLeagueEditName"); }
    void sendChangeIdeology() override { Unsupported("ICvEngineUtility3::sendChangeIdeology"); }
    void TradeVisuals_NewRoute(int iRoute, int iPlayer, TradeConnectionType type, int nPlots, int x[], int y[]) override { Unsupported("ICvEngineUtility3::TradeVisuals_NewRoute"); }
    void TradeVisuals_UpdateRouteDirection(int iRoute, bool bForwards) override { Unsupported("ICvEngineUtility3::TradeVisuals_UpdateRouteDirection"); }
    void TradeVisuals_DestroyRoute(int iRoute, int iPlayer) override { Unsupported("ICvEngineUtility3::TradeVisuals_DestroyRoute"); }
    void TradeVisuals_ActivatePopupRoute(int iRoute) override { Unsupported("ICvEngineUtility3::TradeVisuals_ActivatePopupRoute"); }
    void TradeVisuals_DeactivatePopupRoute() override { Unsupported("ICvEngineUtility3::TradeVisuals_DeactivatePopupRoute"); }
    void FlushTurnReminders() override { Unsupported("ICvEngineUtility3::FlushTurnReminders"); }
    void BeginSendBundle() override { Unsupported("ICvEngineUtility3::BeginSendBundle"); }
    void EndSendBundle() override { Unsupported("ICvEngineUtility3::EndSendBundle"); }
    bool IsPlayerKicked(int iPlayerID) override { Unsupported("ICvEngineUtility3::IsPlayerKicked"); }
    bool IsPlayerHotJoining(int iPlayerID) override { Unsupported("ICvEngineUtility3::IsPlayerHotJoining"); }
    bool allAICivsProcessedThisTurn() const override { Unsupported("ICvEngineUtility3::allAICivsProcessedThisTurn"); }
    void SendAICivsProcessed() const override { Unsupported("ICvEngineUtility3::SendAICivsProcessed"); }
    bool HasReceivedAICivsProcessed(PlayerTypes ePlayer) const override { Unsupported("ICvEngineUtility3::HasReceivedAICivsProcessed"); }
    int GetNumAICivsProcessed() const override { Unsupported("ICvEngineUtility3::GetNumAICivsProcessed"); }
    void VerifyPlayerSlot(PlayerTypes ePlayer) const override { Unsupported("ICvEngineUtility3::VerifyPlayerSlot"); }
    bool ShouldValidateGameDatabase() const override { Unsupported("ICvEngineUtility3::ShouldValidateGameDatabase"); }
    bool DLLCALL GetEvaluatedMapScriptPath(_In_z_ const char* szPath, _Inout_z_cap_(szEvaluatedPathSize) char* szEvaluatedPath, unsigned int szEvaluatedPathSize) const override { Unsupported("ICvEngineUtility4::GetEvaluatedMapScriptPath"); }
};
class UserInterfaceBase : public ICvUserInterface2 {
public:
    void* DLLCALL QueryInterface(GUID guidInterface) override { Unsupported("ICvUnknown::QueryInterface"); }
    void DLLCALL Destroy() override { Unsupported("ICvUnknown::Destroy"); }
    void lookAtSelectionPlot(bool bRelease = false) override { Unsupported("ICvUserInterface1::lookAtSelectionPlot"); }
    bool CanDoInterfaceMode(InterfaceModeTypes eInterfaceMode, bool bTestVisible = false) override { Unsupported("ICvUserInterface1::CanDoInterfaceMode"); }
    ICvPlot1* getSelectionPlot() override { Unsupported("ICvUserInterface1::getSelectionPlot"); }
    ICvUnit1* GetHeadSelectedUnit() override { Unsupported("ICvUserInterface1::GetHeadSelectedUnit"); }
    bool DoAutoUnitCycle() override { Unsupported("ICvUserInterface1::DoAutoUnitCycle"); }
    ICvDeal1* GetScratchDeal() override { Unsupported("ICvUserInterface1::GetScratchDeal"); }
    void SetScratchDeal(ICvDeal1* pDeal) override { Unsupported("ICvUserInterface1::SetScratchDeal"); }
    bool isPopupUp() override { Unsupported("ICvUserInterface1::isPopupUp"); }
    bool isPopupQueued() override { Unsupported("ICvUserInterface1::isPopupQueued"); }
    bool isDiploOrPopupWaiting() override { Unsupported("ICvUserInterface1::isDiploOrPopupWaiting"); }
    bool isDiploActive() override { Unsupported("ICvUserInterface1::isDiploActive"); }
    bool IsUnitSelected(PlayerTypes playerID, int unitID) override { Unsupported("ICvUserInterface1::IsUnitSelected"); }
    void selectUnit(ICvUnit1* pUnit, bool bClear, bool bToggle = false, bool bSound = false) override { Unsupported("ICvUserInterface1::selectUnit"); }
    void selectGroup(ICvUnit1* pUnit, bool bShift, bool bCtrl, bool bAlt) override { Unsupported("ICvUserInterface1::selectGroup"); }
    void selectAll(ICvPlot1* pPlot) override { Unsupported("ICvUserInterface1::selectAll"); }
    bool RemoveFromSelectionList(ICvUnit1* pUnit) override { Unsupported("ICvUserInterface1::RemoveFromSelectionList"); }
    void makeSelectionListDirty() override { Unsupported("ICvUserInterface1::makeSelectionListDirty"); }
    bool CanSelectionListFound() override { Unsupported("ICvUserInterface1::CanSelectionListFound"); }
    ICvUnit1* getLastSelectedUnit() override { Unsupported("ICvUserInterface1::getLastSelectedUnit"); }
    void setLastSelectedUnit(ICvUnit1* pUnit) override { Unsupported("ICvUserInterface1::setLastSelectedUnit"); }
    void changePlotListColumn(int iChange) override { Unsupported("ICvUserInterface1::changePlotListColumn"); }
    int getOriginalPlotIndex() override { Unsupported("ICvUserInterface1::getOriginalPlotIndex"); }
    void ClearSelectionList() override { Unsupported("ICvUserInterface1::ClearSelectionList"); }
    void InsertIntoSelectionList(ICvUnit1* pUnit, bool bClear, bool bToggle, bool bGroup = false, bool bSound = false, bool bMinimalChange = false) override { Unsupported("ICvUserInterface1::InsertIntoSelectionList"); }
    int GetLengthSelectionList() override { Unsupported("ICvUserInterface1::GetLengthSelectionList"); }
    void VisuallyDeselectUnit(ICvUnit1* pUnit) override { Unsupported("ICvUserInterface1::VisuallyDeselectUnit"); }
    ICvEnumerator* GetSelectedUnits() override { Unsupported("ICvUserInterface1::GetSelectedUnits"); }
    void selectCity(ICvCity1* pNewValue, bool bTestProduction = false) override { Unsupported("ICvUserInterface1::selectCity"); }
    void selectLookAtCity(bool bAdd = false) override { Unsupported("ICvUserInterface1::selectLookAtCity"); }
    void addSelectedCity(ICvCity1* pNewValue, bool bToggle = false) override { Unsupported("ICvUserInterface1::addSelectedCity"); }
    void clearSelectedCities() override { Unsupported("ICvUserInterface1::clearSelectedCities"); }
    bool isCitySelected(ICvCity1 *pCity) override { Unsupported("ICvUserInterface1::isCitySelected"); }
    ICvCity1* getHeadSelectedCity() override { Unsupported("ICvUserInterface1::getHeadSelectedCity"); }
    bool isCitySelection() override { Unsupported("ICvUserInterface1::isCitySelection"); }
    IDInfo* nextSelectedCitiesNode(IDInfo* pNode) override { Unsupported("ICvUserInterface1::nextSelectedCitiesNode"); }
    const IDInfo* nextSelectedCitiesNode(const IDInfo* pNode) const override { Unsupported("ICvUserInterface1::nextSelectedCitiesNode"); }
    IDInfo* headSelectedCitiesNode() override { Unsupported("ICvUserInterface1::headSelectedCitiesNode"); }
    void updateCityScreen(ICvCity1* pOldCity = NULL) override { Unsupported("ICvUserInterface1::updateCityScreen"); }
    uint AddMessage(uint uiParentEvent, PlayerTypes ePlayer, bool bForce, int iLength, const char* strString, LPCTSTR pszSound = NULL, InterfaceMessageTypes eType = MESSAGE_TYPE_INFO, LPCSTR pszIcon = NULL, ColorTypes eFlashColor = NO_COLOR, int iFlashX = -1, int iFlashY = -1, bool bShowOffScreenArrows = false, bool bShowOnScreenArrows = false) override { Unsupported("ICvUserInterface1::AddMessage"); }
    uint AddUnitMessage(uint uiParentEvent, const IDInfo& unitID, PlayerTypes ePlayer, bool bForce, int iLength, const char* szString, LPCTSTR pszSound = NULL, InterfaceMessageTypes eType = MESSAGE_TYPE_INFO, LPCSTR pszIcon = NULL, ColorTypes eFlashColor = NO_COLOR, int iFlashX = -1, int iFlashY = -1, bool bShowOffScreenArrows = false, bool bShowOnScreenArrows = false) override { Unsupported("ICvUserInterface1::AddUnitMessage"); }
    uint AddPlotMessage(uint uiParentEvent, int iPlotID, PlayerTypes ePlayer, bool bForce, int iLength, const char* szString, LPCTSTR pszSound = NULL, InterfaceMessageTypes eType = MESSAGE_TYPE_INFO, LPCSTR pszIcon = NULL, ColorTypes eFlashColor = NO_COLOR, int iFlashX = -1, int iFlashY = -1, bool bShowOffScreenArrows = false, bool bShowOnScreenArrows = false) override { Unsupported("ICvUserInterface1::AddPlotMessage"); }
    uint AddCityMessage(uint uiParentEvent, const IDInfo& cityID, PlayerTypes ePlayer, bool bForce, int iLength, const char* szString, LPCTSTR pszSound = NULL, InterfaceMessageTypes eType = MESSAGE_TYPE_INFO, LPCSTR pszIcon = NULL, ColorTypes eFlashColor = NO_COLOR, int iFlashX = -1, int iFlashY = -1, bool bShowOffScreenArrows = false, bool bShowOnScreenArrows = false) override { Unsupported("ICvUserInterface1::AddCityMessage"); }
    void clearEventMessages() override { Unsupported("ICvUserInterface1::clearEventMessages"); }
    void AddPopup(const CvPopupInfo& kPopup) override { Unsupported("ICvUserInterface1::AddPopup"); }
    void AddPopupText( int x, int y, const char *szText, float fDelay = 0 ) override { Unsupported("ICvUserInterface1::AddPopupText"); }
    void PublishActivePlayerTurnStart() override { Unsupported("ICvUserInterface1::PublishActivePlayerTurnStart"); }
    void PublishActivePlayerTurnEnd() override { Unsupported("ICvUserInterface1::PublishActivePlayerTurnEnd"); }
    void PublishRemotePlayerTurnEnd() override { Unsupported("ICvUserInterface1::PublishRemotePlayerTurnEnd"); }
    void PublishPlayerTurnStatus(CvDLLInterfaceIFaceBase::TURN_STATUS_TYPE eStatus, PlayerTypes ePlayer, const char* pszTag = NULL) override { Unsupported("ICvUserInterface1::PublishPlayerTurnStatus"); }
    void AddNotification( int iID, NotificationTypes type, const char *cTooltip, const char* cSummary, int iGameData, int iExtraGameData, PlayerTypes ePlayer, int iX = -1, int iY = -1) override { Unsupported("ICvUserInterface1::AddNotification"); }
    void RemoveNotification( int iID, PlayerTypes ePlayer ) override { Unsupported("ICvUserInterface1::RemoveNotification"); }
    void ActivateNotification (int iID, NotificationTypes type, const char* cString, int iX, int iY, int iGameIndex, int iExtraGameDataValue, PlayerTypes ePlayer) override { Unsupported("ICvUserInterface1::ActivateNotification"); }
    int getCycleSelectionCounter() override { Unsupported("ICvUserInterface1::getCycleSelectionCounter"); }
    void setCycleSelectionCounter(int iNewValue) override { Unsupported("ICvUserInterface1::setCycleSelectionCounter"); }
    void changeCycleSelectionCounter(int iChange) override { Unsupported("ICvUserInterface1::changeCycleSelectionCounter"); }
    bool IsSelectedUnitRevealingNewPlots() const override { Unsupported("ICvUserInterface1::IsSelectedUnitRevealingNewPlots"); }
    void SetSelectedUnitRevealingNewPlots(bool bValue) override { Unsupported("ICvUserInterface1::SetSelectedUnitRevealingNewPlots"); }
    int getEndTurnCounter() override { Unsupported("ICvUserInterface1::getEndTurnCounter"); }
    void setEndTurnCounter(int iNewValue) override { Unsupported("ICvUserInterface1::setEndTurnCounter"); }
    void changeEndTurnCounter(int iChange) override { Unsupported("ICvUserInterface1::changeEndTurnCounter"); }
    bool isCombatFocus() override { Unsupported("ICvUserInterface1::isCombatFocus"); }
    void setCombatFocus(bool bNewValue) override { Unsupported("ICvUserInterface1::setCombatFocus"); }
    bool isDirty(InterfaceDirtyBits eDirtyItem) override { Unsupported("ICvUserInterface1::isDirty"); }
    void setDirty(InterfaceDirtyBits eDirtyItem, bool bNewValue) override { Unsupported("ICvUserInterface1::setDirty"); }
    void makeInterfaceDirty() override { Unsupported("ICvUserInterface1::makeInterfaceDirty"); }
    bool updateCursorType() override { Unsupported("ICvUserInterface1::updateCursorType"); }
    void lookAt(const ICvPlot1* pPlot, CameraLookAtTypes type) override { Unsupported("ICvUserInterface1::lookAt"); }
    void centerCamera(ICvUnit1*) override { Unsupported("ICvUserInterface1::centerCamera"); }
    void releaseLockedCamera() override { Unsupported("ICvUserInterface1::releaseLockedCamera"); }
    bool isFocusedWidget() override { Unsupported("ICvUserInterface1::isFocusedWidget"); }
    bool isFocused() override { Unsupported("ICvUserInterface1::isFocused"); }
    void refreshYieldVisibleMode() override { Unsupported("ICvUserInterface1::refreshYieldVisibleMode"); }
    void toggleYieldVisibleMode() override { Unsupported("ICvUserInterface1::toggleYieldVisibleMode"); }
    void toggleResourceVisibleMode() override { Unsupported("ICvUserInterface1::toggleResourceVisibleMode"); }
    void toggleGridVisibleMode() override { Unsupported("ICvUserInterface1::toggleGridVisibleMode"); }
    int getOriginalPlotCount() override { Unsupported("ICvUserInterface1::getOriginalPlotCount"); }
    bool isCityScreenUp() override { Unsupported("ICvUserInterface1::isCityScreenUp"); }
    void setCityScreenUp(bool bUp) override { Unsupported("ICvUserInterface1::setCityScreenUp"); }
    void setNoSelectionListCycle(bool bValue) override { Unsupported("ICvUserInterface1::setNoSelectionListCycle"); }
    bool canEndTurn() const override { Unsupported("ICvUserInterface1::canEndTurn"); }
    void UpdateEndTurn() override { Unsupported("ICvUserInterface1::UpdateEndTurn"); }
    void SetEndTurnBlockingChanged(EndTurnBlockingTypes ePrevBlockingType, EndTurnBlockingTypes eNewBlockingType) override { Unsupported("ICvUserInterface1::SetEndTurnBlockingChanged"); }
    void setInterfaceMode(InterfaceModeTypes eNewValue) override { Unsupported("ICvUserInterface1::setInterfaceMode"); }
    InterfaceModeTypes getInterfaceMode() override { Unsupported("ICvUserInterface1::getInterfaceMode"); }
    int GetInterfaceModeValue() override { Unsupported("ICvUserInterface1::GetInterfaceModeValue"); }
    void setFlashing(PlayerTypes eWho, bool bFlashing = true) override { Unsupported("ICvUserInterface1::setFlashing"); }
    bool isFlashing(PlayerTypes eWho) override { Unsupported("ICvUserInterface1::isFlashing"); }
    void setDiplomacyLocked(bool bLocked) override { Unsupported("ICvUserInterface1::setDiplomacyLocked"); }
    bool isDiplomacyLocked() override { Unsupported("ICvUserInterface1::isDiplomacyLocked"); }
    void setCanEndTurn(bool bNewValue) override { Unsupported("ICvUserInterface1::setCanEndTurn"); }
    void updateEndTurnTimer(float percentComplete) const override { Unsupported("ICvUserInterface1::updateEndTurnTimer"); }
    bool waitingForRemotePlayers() const override { Unsupported("ICvUserInterface1::waitingForRemotePlayers"); }
    bool isHasMovedUnit() override { Unsupported("ICvUserInterface1::isHasMovedUnit"); }
    void setHasMovedUnit(bool bNewValue) override { Unsupported("ICvUserInterface1::setHasMovedUnit"); }
    bool isForcePopup() override { Unsupported("ICvUserInterface1::isForcePopup"); }
    void setForcePopup(bool bNewValue) override { Unsupported("ICvUserInterface1::setForcePopup"); }
    void lookAtCityOffset(int iCity) override { Unsupported("ICvUserInterface1::lookAtCityOffset"); }
    int getPlotListColumn() override { Unsupported("ICvUserInterface1::getPlotListColumn"); }
    void verifyPlotListColumn() override { Unsupported("ICvUserInterface1::verifyPlotListColumn"); }
    int getPlotListOffset() override { Unsupported("ICvUserInterface1::getPlotListOffset"); }
    void exitingToMainMenu(const char* szLoadFile=NULL) override { Unsupported("ICvUserInterface1::exitingToMainMenu"); }
    bool isInAdvancedStart() const override { Unsupported("ICvUserInterface1::isInAdvancedStart"); }
    void setInAdvancedStart(bool bAdvancedStart) override { Unsupported("ICvUserInterface1::setInAdvancedStart"); }
    void setBusy(bool bBusy) override { Unsupported("ICvUserInterface1::setBusy"); }
    void UpdateCountryBorder(ICvPlot1* pThisPlot) override { Unsupported("ICvUserInterface1::UpdateCountryBorder"); }
    void UpdateAllCountryBorders() override { Unsupported("ICvUserInterface1::UpdateAllCountryBorders"); }
    void DebugCityRoutePlots (ICvPlot1* pPlot, bool bOn) override { Unsupported("ICvUserInterface1::DebugCityRoutePlots"); }
    void DirectionAction(DirectionTypes eDirection) override { Unsupported("ICvUserInterface1::DirectionAction"); }
    void SetSpecificCityInfoDirty(ICvCity1* pCity, CityUpdateTypes eUpdateType) override { Unsupported("ICvUserInterface1::SetSpecificCityInfoDirty"); }
    void AddHexToUIRange(ICvPlot1* pThisPlot) override { Unsupported("ICvUserInterface1::AddHexToUIRange"); }
    void OpenEndGameMenu() override { Unsupported("ICvUserInterface1::OpenEndGameMenu"); }
    void doTurn() override { Unsupported("ICvUserInterface1::doTurn"); }
    bool IsOptionNoRewardPopups() override { Unsupported("ICvUserInterface1::IsOptionNoRewardPopups"); }
    bool IsAIRequestingConcessions() const override { Unsupported("ICvUserInterface1::IsAIRequestingConcessions"); }
    void SetAIRequestingConcessions(bool bValue) override { Unsupported("ICvUserInterface1::SetAIRequestingConcessions"); }
    bool IsHumanMakingDemand() const override { Unsupported("ICvUserInterface1::IsHumanMakingDemand"); }
    void SetHumanMakingDemand(bool bValue) override { Unsupported("ICvUserInterface1::SetHumanMakingDemand"); }
    int GetStartDiploRepeatCount() const override { Unsupported("ICvUserInterface1::GetStartDiploRepeatCount"); }
    void SetStartDiploRepeatCount(int iValue) override { Unsupported("ICvUserInterface1::SetStartDiploRepeatCount"); }
    void ChangeStartDiploRepeatCount(int iChange) override { Unsupported("ICvUserInterface1::ChangeStartDiploRepeatCount"); }
    int GetOfferTradeRepeatCount() const override { Unsupported("ICvUserInterface1::GetOfferTradeRepeatCount"); }
    void SetOfferTradeRepeatCount(int iValue) override { Unsupported("ICvUserInterface1::SetOfferTradeRepeatCount"); }
    void ChangeOfferTradeRepeatCount(int iChange) override { Unsupported("ICvUserInterface1::ChangeOfferTradeRepeatCount"); }
    void OpenTechTree() override { Unsupported("ICvUserInterface1::OpenTechTree"); }
    void OpenPlayerDealScreen( PlayerTypes ePlayer ) override { Unsupported("ICvUserInterface1::OpenPlayerDealScreen"); }
    bool IsPolicyNotificationSeen() const override { Unsupported("ICvUserInterface1::IsPolicyNotificationSeen"); }
    void SetPolicyNotificationSeen(bool bValue) override { Unsupported("ICvUserInterface1::SetPolicyNotificationSeen"); }
    bool IsForceDiscussionModeQuitOnBack() const override { Unsupported("ICvUserInterface1::IsForceDiscussionModeQuitOnBack"); }
    void SetForceDiscussionModeQuitOnBack(bool bValue) override { Unsupported("ICvUserInterface1::SetForceDiscussionModeQuitOnBack"); }
    void SetTempString(CvString strString) override { Unsupported("ICvUserInterface1::SetTempString"); }
    void PublishEndTurnDirty() const override { Unsupported("ICvUserInterface1::PublishEndTurnDirty"); }
    void AddDeferredWonderCommand(WonderCommandType eCommandType, ICvCity1* pThisCity, BuildingTypes eBuildingIndex, int iState) override { Unsupported("ICvUserInterface1::AddDeferredWonderCommand"); }
    bool IsLoadedGame() const override { Unsupported("ICvUserInterface1::IsLoadedGame"); }
    void ToggleStrategicView() override { Unsupported("ICvUserInterface1::ToggleStrategicView"); }
    bool IsPopupQueueEmpty() override { Unsupported("ICvUserInterface1::IsPopupQueueEmpty"); }
    bool IsModalStackEmpty() override { Unsupported("ICvUserInterface1::IsModalStackEmpty"); }
    bool IsDontShowPopups() const override { Unsupported("ICvUserInterface1::IsDontShowPopups"); }
    void SetDontShowPopups(bool bValue) override { Unsupported("ICvUserInterface1::SetDontShowPopups"); }
    bool IsDealInTransit() override { Unsupported("ICvUserInterface1::IsDealInTransit"); }
    void SetDealInTransit(bool bValue) override { Unsupported("ICvUserInterface1::SetDealInTransit"); }
    bool IsSPAutoEndTurnEnabled() override { Unsupported("ICvUserInterface1::IsSPAutoEndTurnEnabled"); }
    void SetSPAutoEndTurnEnabled(bool bEnable) override { Unsupported("ICvUserInterface1::SetSPAutoEndTurnEnabled"); }
    bool IsMPAutoEndTurnEnabled() override { Unsupported("ICvUserInterface1::IsMPAutoEndTurnEnabled"); }
    void SetMPAutoEndTurnEnabled(bool bEnable) override { Unsupported("ICvUserInterface1::SetMPAutoEndTurnEnabled"); }
    bool IsSPQuickCombatEnabled() override { Unsupported("ICvUserInterface1::IsSPQuickCombatEnabled"); }
    void SetSPQuickCombatEnabled(bool bEnable) override { Unsupported("ICvUserInterface1::SetSPQuickCombatEnabled"); }
    bool IsMPQuickCombatEnabled() override { Unsupported("ICvUserInterface1::IsMPQuickCombatEnabled"); }
    void SetMPQuickCombatEnabled(bool bEnable) override { Unsupported("ICvUserInterface1::SetMPQuickCombatEnabled"); }
    void PublishRemotePlayerTurnStart() override { Unsupported("ICvUserInterface2::PublishRemotePlayerTurnStart"); }
    void AddPopup(int iPopupType, int iIntArraySize, const int *pIntArray, int iBoolArraySize, const bool *pBoolArray) override { Unsupported("ICvUserInterface2::AddPopup"); }
};
}
#pragma warning(pop)
