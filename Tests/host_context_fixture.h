#pragma once
#pragma warning(push)
#pragma warning(disable:4100)
namespace ZeroSisHost {
class ContextFixtureBase : public ICvGameContext3 {
public:
    void* DLLCALL QueryInterface(GUID guidInterface) override { Unsupported("ICvUnknown::QueryInterface"); }
    void DLLCALL Destroy() override { Unsupported("ICvUnknown::Destroy"); }
    GUID DLLCALL GetDLLGUID() override { Unsupported("ICvGameContext1::GetDLLGUID"); }
    const char * DLLCALL GetDLLVersion() override { Unsupported("ICvGameContext1::GetDLLVersion"); }
    ICvNetworkSyncronization1* DLLCALL GetNetworkSyncronizer() override { Unsupported("ICvGameContext1::GetNetworkSyncronizer"); }
    ICvNetMessageHandler1* DLLCALL GetNetMessageHandler() override { Unsupported("ICvGameContext1::GetNetMessageHandler"); }
    ICvWorldBuilderMapLoader1* DLLCALL GetWorldBuilderMapLoader() override { Unsupported("ICvGameContext1::GetWorldBuilderMapLoader"); }
    ICvPreGame1* DLLCALL GetPreGame() override { Unsupported("ICvGameContext1::GetPreGame"); }
    ICvGame1* DLLCALL GetGame() override { Unsupported("ICvGameContext1::GetGame"); }
    ICvGameAsynch1* DLLCALL GetGameAsynch() override { Unsupported("ICvGameContext1::GetGameAsynch"); }
    ICvMap1* DLLCALL GetMap() override { Unsupported("ICvGameContext1::GetMap"); }
    ICvTeam1* DLLCALL GetTeam(TeamTypes eTeam) override { Unsupported("ICvGameContext1::GetTeam"); }
    int DLLCALL GetInfoTypeForString(const char* szType, bool hideAssert = false) const override { Unsupported("ICvGameContext1::GetInfoTypeForString"); }
    int DLLCALL GetInfoTypeForHash(uint uiHash, bool hideAssert = false) const override { Unsupported("ICvGameContext1::GetInfoTypeForHash"); }
    CivilizationTypes DLLCALL GetCivilizationInfoIndex(const char* pszType) override { Unsupported("ICvGameContext1::GetCivilizationInfoIndex"); }
    int DLLCALL GetNumPlayableCivilizationInfos() override { Unsupported("ICvGameContext1::GetNumPlayableCivilizationInfos"); }
    int DLLCALL GetNumAIPlayableCivilizationInfos() override { Unsupported("ICvGameContext1::GetNumAIPlayableCivilizationInfos"); }
    int DLLCALL GetNumPlayableMinorCivs() override { Unsupported("ICvGameContext1::GetNumPlayableMinorCivs"); }
    int DLLCALL GetNumBuildInfos() override { Unsupported("ICvGameContext1::GetNumBuildInfos"); }
    int DLLCALL GetNumBuildingInfos() override { Unsupported("ICvGameContext1::GetNumBuildingInfos"); }
    int DLLCALL GetNumCivilizationInfos() override { Unsupported("ICvGameContext1::GetNumCivilizationInfos"); }
    int DLLCALL GetNumClimateInfos() override { Unsupported("ICvGameContext1::GetNumClimateInfos"); }
    int DLLCALL GetNumColorInfos() override { Unsupported("ICvGameContext1::GetNumColorInfos"); }
    int DLLCALL GetNumEraInfos() override { Unsupported("ICvGameContext1::GetNumEraInfos"); }
    int DLLCALL GetNumFeatureInfos() override { Unsupported("ICvGameContext1::GetNumFeatureInfos"); }
    int DLLCALL GetNumGameOptionInfos() override { Unsupported("ICvGameContext1::GetNumGameOptionInfos"); }
    int DLLCALL GetNumGameSpeedInfos() override { Unsupported("ICvGameContext1::GetNumGameSpeedInfos"); }
    int DLLCALL GetNumHandicapInfos() override { Unsupported("ICvGameContext1::GetNumHandicapInfos"); }
    int DLLCALL GetNumImprovementInfos() override { Unsupported("ICvGameContext1::GetNumImprovementInfos"); }
    int DLLCALL GetNumLeaderHeadInfos() override { Unsupported("ICvGameContext1::GetNumLeaderHeadInfos"); }
    int DLLCALL GetNumMinorCivInfos() override { Unsupported("ICvGameContext1::GetNumMinorCivInfos"); }
    int DLLCALL GetNumPlayerColorInfos() override { Unsupported("ICvGameContext1::GetNumPlayerColorInfos"); }
    int DLLCALL GetNumPolicyInfos() override { Unsupported("ICvGameContext1::GetNumPolicyInfos"); }
    int DLLCALL GetNumPromotionInfos() override { Unsupported("ICvGameContext1::GetNumPromotionInfos"); }
    int DLLCALL GetNumResourceInfos() override { Unsupported("ICvGameContext1::GetNumResourceInfos"); }
    int DLLCALL GetNumSeaLevelInfos() override { Unsupported("ICvGameContext1::GetNumSeaLevelInfos"); }
    int DLLCALL GetNumTechInfos() override { Unsupported("ICvGameContext1::GetNumTechInfos"); }
    int DLLCALL GetNumTerrainInfos() override { Unsupported("ICvGameContext1::GetNumTerrainInfos"); }
    int DLLCALL GetNumUnitCombatClassInfos() override { Unsupported("ICvGameContext1::GetNumUnitCombatClassInfos"); }
    int DLLCALL GetNumUnitInfos() override { Unsupported("ICvGameContext1::GetNumUnitInfos"); }
    int DLLCALL GetNumVictoryInfos() override { Unsupported("ICvGameContext1::GetNumVictoryInfos"); }
    int DLLCALL GetNumWorldInfos() override { Unsupported("ICvGameContext1::GetNumWorldInfos"); }
    ICvBuildInfo1* DLLCALL GetBuildInfo(BuildTypes eBuildNum) override { Unsupported("ICvGameContext1::GetBuildInfo"); }
    ICvBuildingInfo1* DLLCALL GetBuildingInfo(BuildingTypes eBuilding) override { Unsupported("ICvGameContext1::GetBuildingInfo"); }
    ICvCivilizationInfo1* DLLCALL GetCivilizationInfo(CivilizationTypes eCivilizationNum) override { Unsupported("ICvGameContext1::GetCivilizationInfo"); }
    ICvColorInfo1* DLLCALL GetColorInfo(ColorTypes e) override { Unsupported("ICvGameContext1::GetColorInfo"); }
    ICvEraInfo1* DLLCALL GetEraInfo(EraTypes eEraNum) override { Unsupported("ICvGameContext1::GetEraInfo"); }
    ICvFeatureInfo1* DLLCALL GetFeatureInfo(FeatureTypes eFeatureNum) override { Unsupported("ICvGameContext1::GetFeatureInfo"); }
    ICvGameOptionInfo1* DLLCALL GetGameOptionInfo(GameOptionTypes eGameOptionNum) override { Unsupported("ICvGameContext1::GetGameOptionInfo"); }
    ICvGameSpeedInfo1* DLLCALL GetGameSpeedInfo(GameSpeedTypes eGameSpeedNum) override { Unsupported("ICvGameContext1::GetGameSpeedInfo"); }
    ICvHandicapInfo1* DLLCALL GetHandicapInfo(HandicapTypes eHandicapNum) override { Unsupported("ICvGameContext1::GetHandicapInfo"); }
    ICvInterfaceModeInfo1* DLLCALL GetInterfaceModeInfo(InterfaceModeTypes e) override { Unsupported("ICvGameContext1::GetInterfaceModeInfo"); }
    ICvImprovementInfo1* DLLCALL GetImprovementInfo(ImprovementTypes eImprovement) override { Unsupported("ICvGameContext1::GetImprovementInfo"); }
    ICvLeaderHeadInfo1* DLLCALL GetLeaderHeadInfo(LeaderHeadTypes eLeaderHeadNum) override { Unsupported("ICvGameContext1::GetLeaderHeadInfo"); }
    ICvMinorCivInfo1* DLLCALL GetMinorCivInfo(MinorCivTypes eMinorCiv) override { Unsupported("ICvGameContext1::GetMinorCivInfo"); }
    ICvMissionInfo1* DLLCALL GetMissionInfo(MissionTypes eMission) override { Unsupported("ICvGameContext1::GetMissionInfo"); }
    ICvPlayerColorInfo1* DLLCALL GetPlayerColorInfo(PlayerColorTypes e) override { Unsupported("ICvGameContext1::GetPlayerColorInfo"); }
    ICvPlayerOptionInfo1* DLLCALL GetPlayerOptionInfo(PlayerOptionTypes ePlayerOptionNum) override { Unsupported("ICvGameContext1::GetPlayerOptionInfo"); }
    ICvPolicyInfo1* DLLCALL GetPolicyInfo(PolicyTypes ePolicy) override { Unsupported("ICvGameContext1::GetPolicyInfo"); }
    ICvPromotionInfo1* DLLCALL GetPromotionInfo(PromotionTypes ePromotion) override { Unsupported("ICvGameContext1::GetPromotionInfo"); }
    ICvResourceInfo1* DLLCALL GetResourceInfo(ResourceTypes eResourceNum) override { Unsupported("ICvGameContext1::GetResourceInfo"); }
    ICvTechInfo1* DLLCALL GetTechInfo(TechTypes eTech) override { Unsupported("ICvGameContext1::GetTechInfo"); }
    ICvTerrainInfo1* DLLCALL GetTerrainInfo(TerrainTypes eTerrainNum) override { Unsupported("ICvGameContext1::GetTerrainInfo"); }
    ICvUnitInfo1* DLLCALL GetUnitInfo(UnitTypes eUnit) override { Unsupported("ICvGameContext1::GetUnitInfo"); }
    ICvUnitCombatClassInfo1* DLLCALL GetUnitCombatClassInfo(UnitCombatTypes eUnitCombat) override { Unsupported("ICvGameContext1::GetUnitCombatClassInfo"); }
    ICvVictoryInfo1* DLLCALL GetVictoryInfo(VictoryTypes eVictoryType) override { Unsupported("ICvGameContext1::GetVictoryInfo"); }
    bool DLLCALL GetDefineSTRING(char* szBuffer, size_t lenBuffer, const char* szName, bool bReportErrors = true) override { Unsupported("ICvGameContext1::GetDefineSTRING"); }
    int DLLCALL GetMOVE_DENOMINATOR() const override { Unsupported("ICvGameContext1::GetMOVE_DENOMINATOR"); }
    int DLLCALL GetMAX_CITY_HIT_POINTS() const override { Unsupported("ICvGameContext1::GetMAX_CITY_HIT_POINTS"); }
    float DLLCALL GetCITY_ZOOM_OFFSET() const override { Unsupported("ICvGameContext1::GetCITY_ZOOM_OFFSET"); }
    float DLLCALL GetCITY_ZOOM_LEVEL_1() const override { Unsupported("ICvGameContext1::GetCITY_ZOOM_LEVEL_1"); }
    float DLLCALL GetCITY_ZOOM_LEVEL_2() const override { Unsupported("ICvGameContext1::GetCITY_ZOOM_LEVEL_2"); }
    float DLLCALL GetCITY_ZOOM_LEVEL_3() const override { Unsupported("ICvGameContext1::GetCITY_ZOOM_LEVEL_3"); }
    int DLLCALL GetRUINS_IMPROVEMENT() const override { Unsupported("ICvGameContext1::GetRUINS_IMPROVEMENT"); }
    int DLLCALL GetSHALLOW_WATER_TERRAIN() const override { Unsupported("ICvGameContext1::GetSHALLOW_WATER_TERRAIN"); }
    int DLLCALL GetDEFICIT_UNIT_DISBANDING_THRESHOLD() const override { Unsupported("ICvGameContext1::GetDEFICIT_UNIT_DISBANDING_THRESHOLD"); }
    int DLLCALL GetLAST_UNIT_ART_ERA() const override { Unsupported("ICvGameContext1::GetLAST_UNIT_ART_ERA"); }
    int DLLCALL GetLAST_EMBARK_ART_ERA() const override { Unsupported("ICvGameContext1::GetLAST_EMBARK_ART_ERA"); }
    int DLLCALL GetHEAVY_RESOURCE_THRESHOLD() const override { Unsupported("ICvGameContext1::GetHEAVY_RESOURCE_THRESHOLD"); }
    int DLLCALL GetSTANDARD_HANDICAP() const override { Unsupported("ICvGameContext1::GetSTANDARD_HANDICAP"); }
    int DLLCALL GetSTANDARD_GAMESPEED() const override { Unsupported("ICvGameContext1::GetSTANDARD_GAMESPEED"); }
    int DLLCALL GetLAST_BRIDGE_ART_ERA() const override { Unsupported("ICvGameContext1::GetLAST_BRIDGE_ART_ERA"); }
    int DLLCALL GetBARBARIAN_CIVILIZATION() const override { Unsupported("ICvGameContext1::GetBARBARIAN_CIVILIZATION"); }
    int DLLCALL GetMINOR_CIVILIZATION() const override { Unsupported("ICvGameContext1::GetMINOR_CIVILIZATION"); }
    int DLLCALL GetBARBARIAN_HANDICAP() const override { Unsupported("ICvGameContext1::GetBARBARIAN_HANDICAP"); }
    int DLLCALL GetBARBARIAN_LEADER() const override { Unsupported("ICvGameContext1::GetBARBARIAN_LEADER"); }
    int DLLCALL GetMINOR_CIV_HANDICAP() const override { Unsupported("ICvGameContext1::GetMINOR_CIV_HANDICAP"); }
    int DLLCALL GetWALLS_BUILDINGCLASS() const override { Unsupported("ICvGameContext1::GetWALLS_BUILDINGCLASS"); }
    int DLLCALL GetAI_HANDICAP() const override { Unsupported("ICvGameContext1::GetAI_HANDICAP"); }
    int DLLCALL GetNUM_CITY_PLOTS() const override { Unsupported("ICvGameContext1::GetNUM_CITY_PLOTS"); }
    const char** DLLCALL GetHexDebugLayerNames() override { Unsupported("ICvGameContext1::GetHexDebugLayerNames"); }
    float DLLCALL GetHexDebugLayerScale(const char* szLayerName) override { Unsupported("ICvGameContext1::GetHexDebugLayerScale"); }
    bool DLLCALL GetHexDebugLayerString(ICvPlot1* pPlot, const char* szLayerName, PlayerTypes ePlayer, char* szBuffer, unsigned int uiBufferLength) override { Unsupported("ICvGameContext1::GetHexDebugLayerString"); }
    void DLLCALL Init() override { Unsupported("ICvGameContext1::Init"); }
    void DLLCALL Uninit() override { Unsupported("ICvGameContext1::Uninit"); }
    ICvScriptSystemUtility1* DLLCALL GetScriptSystemUtility() override { Unsupported("ICvGameContext1::GetScriptSystemUtility"); }
    const char* DLLCALL GetNotificationType(int NotificationID) const override { Unsupported("ICvGameContext1::GetNotificationType"); }
    bool DLLCALL GetLogging() override { Unsupported("ICvGameContext1::GetLogging"); }
    void DLLCALL SetLogging(bool bEnable) override { Unsupported("ICvGameContext1::SetLogging"); }
    int DLLCALL GetRandLogging() override { Unsupported("ICvGameContext1::GetRandLogging"); }
    void DLLCALL SetRandLogging(int iRandLoggingFlags) override { Unsupported("ICvGameContext1::SetRandLogging"); }
    bool DLLCALL GetAILogging() override { Unsupported("ICvGameContext1::GetAILogging"); }
    void DLLCALL SetAILogging(bool bEnable) override { Unsupported("ICvGameContext1::SetAILogging"); }
    bool DLLCALL GetAIPerfLogging() override { Unsupported("ICvGameContext1::GetAIPerfLogging"); }
    void DLLCALL SetAIPerfLogging(bool bEnable) override { Unsupported("ICvGameContext1::SetAIPerfLogging"); }
    bool DLLCALL GetBuilderAILogging() override { Unsupported("ICvGameContext1::GetBuilderAILogging"); }
    void DLLCALL SetBuilderAILogging(bool bEnable) override { Unsupported("ICvGameContext1::SetBuilderAILogging"); }
    bool DLLCALL GetPlayerAndCityAILogSplit() override { Unsupported("ICvGameContext1::GetPlayerAndCityAILogSplit"); }
    void DLLCALL SetPlayerAndCityAILogSplit(bool bEnable) override { Unsupported("ICvGameContext1::SetPlayerAndCityAILogSplit"); }
    bool DLLCALL GetTutorialLogging() override { Unsupported("ICvGameContext1::GetTutorialLogging"); }
    void DLLCALL SetTutorialLogging(bool bEnable) override { Unsupported("ICvGameContext1::SetTutorialLogging"); }
    bool DLLCALL GetTutorialDebugging() override { Unsupported("ICvGameContext1::GetTutorialDebugging"); }
    void DLLCALL SetTutorialDebugging(bool bEnable) override { Unsupported("ICvGameContext1::SetTutorialDebugging"); }
    bool DLLCALL GetAllowRClickMovementWhileScrolling() override { Unsupported("ICvGameContext1::GetAllowRClickMovementWhileScrolling"); }
    void DLLCALL SetAllowRClickMovementWhileScrolling(bool bAllow) override { Unsupported("ICvGameContext1::SetAllowRClickMovementWhileScrolling"); }
    bool DLLCALL GetPostTurnAutosaves() override { Unsupported("ICvGameContext1::GetPostTurnAutosaves"); }
    void DLLCALL SetPostTurnAutosaves(bool bEnable) override { Unsupported("ICvGameContext1::SetPostTurnAutosaves"); }
    ICvDLLDatabaseUtility1* DLLCALL GetDatabaseLoadUtility() override { Unsupported("ICvGameContext1::GetDatabaseLoadUtility"); }
    int* DLLCALL GetPlotDirectionX() override { Unsupported("ICvGameContext1::GetPlotDirectionX"); }
    int* DLLCALL GetPlotDirectionY() override { Unsupported("ICvGameContext1::GetPlotDirectionY"); }
    int* DLLCALL GetCityPlotX() override { Unsupported("ICvGameContext1::GetCityPlotX"); }
    int* DLLCALL GetCityPlotY() override { Unsupported("ICvGameContext1::GetCityPlotY"); }
    void DLLCALL SetGameDatabase(Database::Connection* pGameDatabase) override { Unsupported("ICvGameContext1::SetGameDatabase"); }
    bool DLLCALL SetDLLIFace(ICvEngineUtility1* pDll) override { Unsupported("ICvGameContext1::SetDLLIFace"); }
    bool DLLCALL IsGraphicsInitialized() const override { Unsupported("ICvGameContext1::IsGraphicsInitialized"); }
    void DLLCALL SetGraphicsInitialized(bool bVal) override { Unsupported("ICvGameContext1::SetGraphicsInitialized"); }
    void DLLCALL SetOutOfSyncDebuggingEnabled(bool isEnabled) override { Unsupported("ICvGameContext1::SetOutOfSyncDebuggingEnabled"); }
    bool DLLCALL RandomNumberGeneratorSyncCheck(PlayerTypes ePlayer, ICvRandom1* pRandom, bool bIsHost) override { Unsupported("ICvGameContext1::RandomNumberGeneratorSyncCheck"); }
    unsigned int DLLCALL CreateRandomNumberGenerator() override { Unsupported("ICvGameContext1::CreateRandomNumberGenerator"); }
    ICvRandom1* DLLCALL GetRandomNumberGenerator(unsigned int index) override { Unsupported("ICvGameContext1::GetRandomNumberGenerator"); }
    void DLLCALL DestroyRandomNumberGenerator(unsigned int index) override { Unsupported("ICvGameContext1::DestroyRandomNumberGenerator"); }
    unsigned int DLLCALL CreateNetInitInfo() override { Unsupported("ICvGameContext1::CreateNetInitInfo"); }
    ICvNetInitInfo1* DLLCALL GetNetInitInfo(unsigned int index) override { Unsupported("ICvGameContext1::GetNetInitInfo"); }
    void DLLCALL DestroyNetInitInfo(unsigned int index) override { Unsupported("ICvGameContext1::DestroyNetInitInfo"); }
    unsigned int DLLCALL CreateNetLoadGameInfo() override { Unsupported("ICvGameContext1::CreateNetLoadGameInfo"); }
    ICvNetLoadGameInfo1* DLLCALL GetNetLoadGameInfo(unsigned int index) override { Unsupported("ICvGameContext1::GetNetLoadGameInfo"); }
    void DLLCALL DestroyNetLoadGameInfo(unsigned int index) override { Unsupported("ICvGameContext1::DestroyNetLoadGameInfo"); }
    void DLLCALL TEMPOnHexUnitChanged(ICvUnit1* pUnit) override { Unsupported("ICvGameContext1::TEMPOnHexUnitChanged"); }
    void DLLCALL TEMPOnHexUnitChangedAttack(ICvUnit1* pUnit) override { Unsupported("ICvGameContext1::TEMPOnHexUnitChangedAttack"); }
    ICvEnumerator* DLLCALL TEMPCalculatePathFinderUpdates(ICvUnit1* pHeadSelectedUnit, int iMouseMapX, int iMouseMapY) override { Unsupported("ICvGameContext1::TEMPCalculatePathFinderUpdates"); }
    void DLLCALL ResetPathFinder() override { Unsupported("ICvGameContext1::ResetPathFinder"); }
    void DLLCALL SetEngineUserInterface(ICvUserInterface2* pUI) override { Unsupported("ICvGameContext2::SetEngineUserInterface"); }
    HANDLE DLLCALL Debug_GetHeap() const override { Unsupported("ICvGameContext3::Debug_GetHeap"); }
};
}
#pragma warning(pop)
