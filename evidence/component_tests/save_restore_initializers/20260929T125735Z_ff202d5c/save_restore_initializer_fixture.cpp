#include <array>
#include <iostream>
#include <string>
#include <vector>

constexpr int MAX_CIV_PLAYERS = 63;
constexpr int MAX_MAJOR_CIVS = 22;
constexpr int NO_WAR_STATE_TYPE = -101;
constexpr int NO_THREAT_VALUE = -102;
constexpr int NO_STRENGTH_VALUE = -103;
constexpr int NO_TARGET_VALUE = -104;
constexpr int NO_DEFENSE_STATE = -105;
constexpr int NO_ARMY_TYPE = -106;
constexpr int NO_PUBLIC_OPINION = -107;
constexpr int NO_POLICY_BRANCH_TYPE = -108;
constexpr int NO_PLAYER = -109;

struct CvPlayer {};

struct MilitaryStrategyList
{
	int count;
	int GetNumMilitaryAIStrategies() const { return count; }
};

struct MilitaryOriginal
{
	int m_iTotalThreatWeight;
	int m_eArmyTypeBeingBuilt;
	int m_iNumLandUnits, m_iNumRangedLandUnits, m_iNumMobileLandUnits;
	int m_iNumAirUnits, m_iNumAntiAirUnits, m_iNumMeleeLandUnits, m_iNumNavalUnits;
	int m_iNumLandUnitsInArmies, m_iNumNavalUnitsInArmies;
	int m_iBarbarianCampCount, m_iVisibleBarbarianCount;
	int m_iRecommendedMilitarySize, m_iMandatoryReserveSize;
	int m_eLandDefenseState, m_eNavalDefenseState;
	int m_iNumberOfTimesOpsBuildSkippedOver;
	MilitaryStrategyList* m_pAIStrategies;
	bool* m_pabUsingStrategy;
	int* m_paiTurnStrategyAdopted;
	int* m_paeLastTurnWarState;
	int* m_paeLastTurnMilitaryThreat;
	int* m_paeLastTurnMilitaryStrength;
	int* m_paeLastTurnTargetValue;
	void Reset()
	{

	int iI;

	m_iTotalThreatWeight = 1;  // Don't ever assume there is no threat at all
	m_eArmyTypeBeingBuilt = NO_ARMY_TYPE;

	m_iNumLandUnits = 0;
	m_iNumRangedLandUnits = 0;
	m_iNumMobileLandUnits = 0;
	m_iNumAirUnits = 0;
	m_iNumAntiAirUnits = 0;
	m_iNumMeleeLandUnits = 0;
	m_iNumNavalUnits = 0;
	m_iNumLandUnitsInArmies = 0;
	m_iNumNavalUnitsInArmies = 0;
	m_iBarbarianCampCount = 0;
	m_iVisibleBarbarianCount = 0;
	m_iRecommendedMilitarySize = 0;
	m_iMandatoryReserveSize = 0;
	m_eLandDefenseState = NO_DEFENSE_STATE;
	m_eNavalDefenseState = NO_DEFENSE_STATE;
	m_iNumberOfTimesOpsBuildSkippedOver = 0;

	for(iI = 0; iI < m_pAIStrategies->GetNumMilitaryAIStrategies(); iI++)
	{
		m_pabUsingStrategy[iI] = false;
		m_paiTurnStrategyAdopted[iI] = -1;
		m_paeLastTurnWarState[iI] = NO_WAR_STATE_TYPE;
		m_paeLastTurnMilitaryThreat[iI] = NO_THREAT_VALUE;
		m_paeLastTurnMilitaryStrength[iI] = NO_STRENGTH_VALUE;
		m_paeLastTurnTargetValue[iI] = NO_TARGET_VALUE;
	}

	}
};

struct MilitaryCandidate
{
	int m_iTotalThreatWeight;
	int m_eArmyTypeBeingBuilt;
	int m_iNumLandUnits, m_iNumRangedLandUnits, m_iNumMobileLandUnits;
	int m_iNumAirUnits, m_iNumAntiAirUnits, m_iNumMeleeLandUnits, m_iNumNavalUnits;
	int m_iNumLandUnitsInArmies, m_iNumNavalUnitsInArmies;
	int m_iBarbarianCampCount, m_iVisibleBarbarianCount;
	int m_iRecommendedMilitarySize, m_iMandatoryReserveSize;
	int m_eLandDefenseState, m_eNavalDefenseState;
	int m_iNumberOfTimesOpsBuildSkippedOver;
	MilitaryStrategyList* m_pAIStrategies;
	bool* m_pabUsingStrategy;
	int* m_paiTurnStrategyAdopted;
	int* m_paeLastTurnWarState;
	int* m_paeLastTurnMilitaryThreat;
	int* m_paeLastTurnMilitaryStrength;
	int* m_paeLastTurnTargetValue;
	void Reset()
	{

	int iI;

	m_iTotalThreatWeight = 1;  // Don't ever assume there is no threat at all
	m_eArmyTypeBeingBuilt = NO_ARMY_TYPE;

	m_iNumLandUnits = 0;
	m_iNumRangedLandUnits = 0;
	m_iNumMobileLandUnits = 0;
	m_iNumAirUnits = 0;
	m_iNumAntiAirUnits = 0;
	m_iNumMeleeLandUnits = 0;
	m_iNumNavalUnits = 0;
	m_iNumLandUnitsInArmies = 0;
	m_iNumNavalUnitsInArmies = 0;
	m_iBarbarianCampCount = 0;
	m_iVisibleBarbarianCount = 0;
	m_iRecommendedMilitarySize = 0;
	m_iMandatoryReserveSize = 0;
	m_eLandDefenseState = NO_DEFENSE_STATE;
	m_eNavalDefenseState = NO_DEFENSE_STATE;
	m_iNumberOfTimesOpsBuildSkippedOver = 0;

	for(iI = 0; iI < m_pAIStrategies->GetNumMilitaryAIStrategies(); iI++)
	{
		m_pabUsingStrategy[iI] = false;
		m_paiTurnStrategyAdopted[iI] = -1;
	}

	// These four arrays are indexed by player, independently of strategy count.
	for(iI = 0; iI < MAX_CIV_PLAYERS; iI++)
	{
		m_paeLastTurnWarState[iI] = NO_WAR_STATE_TYPE;
		m_paeLastTurnMilitaryThreat[iI] = NO_THREAT_VALUE;
		m_paeLastTurnMilitaryStrength[iI] = NO_STRENGTH_VALUE;
		m_paeLastTurnTargetValue[iI] = NO_TARGET_VALUE;
	}

	}
};

struct CultureOriginal
{
	CvPlayer* m_pPlayer;
	std::vector<int> m_aDigCompletePlots;
	int m_iLastTurnLifetimeCulture;
	int m_aiCulturalInfluence[MAX_MAJOR_CIVS];
	int m_aiLastTurnCulturalInfluence[MAX_MAJOR_CIVS];
	bool m_bReportedTwoCivsAway, m_bReportedOneCivAway;
	int m_eOpinion, m_eOpinionBiggestInfluence, m_iTurnIdeologySwitch;
	int m_ePreferredIdeology, m_iOpinionUnhappiness;
	std::string m_strOpinionTooltip, m_strOpinionUnhappinessTooltip;
	int m_iSwappableWritingIndex, m_iSwappableArtIndex;
	int m_iSwappableArtifactIndex, m_iSwappableMusicIndex;
	void ResetDigCompletePlots() { m_aDigCompletePlots.clear(); }
	void Init(CvPlayer* pPlayer)
	{

	m_pPlayer = pPlayer;

	ResetDigCompletePlots();

	m_iLastTurnLifetimeCulture = 0;
	m_iOpinionUnhappiness = 0;

	for (int iI = 0; iI < MAX_MAJOR_CIVS; iI++)
	{
		m_aiCulturalInfluence[iI] = 0;
		m_aiLastTurnCulturalInfluence[iI] = 0;
	}

	m_bReportedTwoCivsAway = false;
	m_bReportedOneCivAway = false;

	m_iSwappableWritingIndex  = -1;
	m_iSwappableArtIndex      = -1;
	m_iSwappableArtifactIndex = -1;
	m_iSwappableMusicIndex    = -1;

	m_iTurnIdeologySwitch = -1;

	}
};

struct CultureCandidate
{
	CvPlayer* m_pPlayer;
	std::vector<int> m_aDigCompletePlots;
	int m_iLastTurnLifetimeCulture;
	int m_aiCulturalInfluence[MAX_MAJOR_CIVS];
	int m_aiLastTurnCulturalInfluence[MAX_MAJOR_CIVS];
	bool m_bReportedTwoCivsAway, m_bReportedOneCivAway;
	int m_eOpinion, m_eOpinionBiggestInfluence, m_iTurnIdeologySwitch;
	int m_ePreferredIdeology, m_iOpinionUnhappiness;
	std::string m_strOpinionTooltip, m_strOpinionUnhappinessTooltip;
	int m_iSwappableWritingIndex, m_iSwappableArtIndex;
	int m_iSwappableArtifactIndex, m_iSwappableMusicIndex;
	void ResetDigCompletePlots() { m_aDigCompletePlots.clear(); }
	void Init(CvPlayer* pPlayer)
	{

	m_pPlayer = pPlayer;

	ResetDigCompletePlots();

	m_iLastTurnLifetimeCulture = 0;
	m_eOpinion = NO_PUBLIC_OPINION;
	m_ePreferredIdeology = NO_POLICY_BRANCH_TYPE;
	m_eOpinionBiggestInfluence = NO_PLAYER;
	m_iOpinionUnhappiness = 0;
	m_strOpinionTooltip = "";
	m_strOpinionUnhappinessTooltip = "";

	for (int iI = 0; iI < MAX_MAJOR_CIVS; iI++)
	{
		m_aiCulturalInfluence[iI] = 0;
		m_aiLastTurnCulturalInfluence[iI] = 0;
	}

	m_bReportedTwoCivsAway = false;
	m_bReportedOneCivAway = false;

	m_iSwappableWritingIndex  = -1;
	m_iSwappableArtIndex      = -1;
	m_iSwappableArtifactIndex = -1;
	m_iSwappableMusicIndex    = -1;

	m_iTurnIdeologySwitch = -1;

	}
};

static const int kDirty = 777777;
static const int kGuard = 424242;
static const int kGuardSlots = MAX_CIV_PLAYERS + 80 + 2;

template <typename Fixture>
bool runMilitaryCase(const char* label, int strategyCount, bool expectFixed)
{
	std::array<bool, 82> usingStrategy;
	std::array<int, 82> adopted;
	std::array<int, kGuardSlots> warState, threat, strength, target;
	usingStrategy.fill(true);
	adopted.fill(kDirty);
	warState.fill(kGuard);
	threat.fill(kGuard);
	strength.fill(kGuard);
	target.fill(kGuard);

	MilitaryStrategyList strategies = { strategyCount };
	Fixture fixture = {};
	fixture.m_pAIStrategies = &strategies;
	fixture.m_pabUsingStrategy = usingStrategy.data() + 1;
	fixture.m_paiTurnStrategyAdopted = adopted.data() + 1;
	fixture.m_paeLastTurnWarState = warState.data() + 1;
	fixture.m_paeLastTurnMilitaryThreat = threat.data() + 1;
	fixture.m_paeLastTurnMilitaryStrength = strength.data() + 1;
	fixture.m_paeLastTurnTargetValue = target.data() + 1;
	fixture.Reset();

	bool ok = true;
	for (int i = 0; i < strategyCount; ++i)
		ok = ok && !fixture.m_pabUsingStrategy[i] && fixture.m_paiTurnStrategyAdopted[i] == -1;
	ok = ok && usingStrategy[0] && adopted[0] == kDirty;
	ok = ok && usingStrategy[strategyCount + 1] && adopted[strategyCount + 1] == kDirty;

	const int checkedPlayerIndex = strategyCount > MAX_CIV_PLAYERS ? strategyCount : MAX_CIV_PLAYERS;
	for (int i = -1; i <= checkedPlayerIndex; ++i)
	{
		const bool inPlayerArray = i >= 0 && i < MAX_CIV_PLAYERS;
		const bool expectedWrite = i >= 0 && i < strategyCount;
		const int expectedWar = expectedWrite ? NO_WAR_STATE_TYPE : kGuard;
		const int expectedThreat = expectedWrite ? NO_THREAT_VALUE : kGuard;
		const int expectedStrength = expectedWrite ? NO_STRENGTH_VALUE : kGuard;
		const int expectedTarget = expectedWrite ? NO_TARGET_VALUE : kGuard;
		const int actualIndex = i + 1;
		const bool actualIsExpected = warState[actualIndex] == expectedWar &&
			threat[actualIndex] == expectedThreat && strength[actualIndex] == expectedStrength &&
			target[actualIndex] == expectedTarget;
		if (expectFixed)
		{
			const int boundedIndex = i + 1;
			const int boundedWar = inPlayerArray ? NO_WAR_STATE_TYPE : kGuard;
			const int boundedThreat = inPlayerArray ? NO_THREAT_VALUE : kGuard;
			const int boundedStrength = inPlayerArray ? NO_STRENGTH_VALUE : kGuard;
			const int boundedTarget = inPlayerArray ? NO_TARGET_VALUE : kGuard;
			ok = ok && warState[boundedIndex] == boundedWar && threat[boundedIndex] == boundedThreat &&
				strength[boundedIndex] == boundedStrength && target[boundedIndex] == boundedTarget;
		}
		else
			ok = ok && actualIsExpected;
	}

	// Every backing slot outside the declared 63-player storage is a safe guard region.
	for (int i = MAX_CIV_PLAYERS + 1; i < kGuardSlots; ++i)
	{
		if (expectFixed)
			ok = ok && warState[i] == kGuard && threat[i] == kGuard && strength[i] == kGuard && target[i] == kGuard;
	}
	int omittedTailPerArray = 0;
	int overwrittenGuardPerArray = 0;
	for (int i = 0; i < MAX_CIV_PLAYERS; ++i)
		if (warState[i + 1] == kGuard) ++omittedTailPerArray;
	for (int i = MAX_CIV_PLAYERS + 1; i < kGuardSlots; ++i)
		if (warState[i] != kGuard) ++overwrittenGuardPerArray;
	std::cout << label << " strategyCount=" << strategyCount
		<< " playerArrayOmissionsPerArray=" << omittedTailPerArray
		<< " outOfBoundsWritesPerArray=" << overwrittenGuardPerArray
		<< " " << (ok ? "PASS" : "FAIL") << "\n";
	return ok;
}

template <typename Fixture>
bool runCultureCase(const char* label, bool expectFixed)
{
	Fixture fixture = {};
	CvPlayer player;
	fixture.m_pPlayer = nullptr;
	fixture.m_aDigCompletePlots.push_back(1);
	fixture.m_iLastTurnLifetimeCulture = kDirty;
	fixture.m_iOpinionUnhappiness = kDirty;
	for (int i = 0; i < MAX_MAJOR_CIVS; ++i)
	{
		fixture.m_aiCulturalInfluence[i] = kDirty;
		fixture.m_aiLastTurnCulturalInfluence[i] = kDirty;
	}
	fixture.m_bReportedTwoCivsAway = true;
	fixture.m_bReportedOneCivAway = true;
	fixture.m_eOpinion = 901;
	fixture.m_ePreferredIdeology = 902;
	fixture.m_eOpinionBiggestInfluence = 903;
	fixture.m_iTurnIdeologySwitch = kDirty;
	fixture.m_strOpinionTooltip = "dirty opinion tooltip";
	fixture.m_strOpinionUnhappinessTooltip = "dirty unhappiness tooltip";
	fixture.m_iSwappableWritingIndex = kDirty;
	fixture.m_iSwappableArtIndex = kDirty;
	fixture.m_iSwappableArtifactIndex = kDirty;
	fixture.m_iSwappableMusicIndex = kDirty;
	fixture.Init(&player);

	bool ok = fixture.m_pPlayer == &player && fixture.m_aDigCompletePlots.empty();
	for (int i = 0; i < MAX_MAJOR_CIVS; ++i)
		ok = ok && fixture.m_aiCulturalInfluence[i] == 0 && fixture.m_aiLastTurnCulturalInfluence[i] == 0;
	ok = ok && fixture.m_iLastTurnLifetimeCulture == 0 && fixture.m_iOpinionUnhappiness == 0 &&
		!fixture.m_bReportedTwoCivsAway && !fixture.m_bReportedOneCivAway &&
		fixture.m_iTurnIdeologySwitch == -1 && fixture.m_iSwappableWritingIndex == -1 &&
		fixture.m_iSwappableArtIndex == -1 && fixture.m_iSwappableArtifactIndex == -1 &&
		fixture.m_iSwappableMusicIndex == -1;
	if (expectFixed)
		ok = ok && fixture.m_eOpinion == NO_PUBLIC_OPINION &&
			fixture.m_ePreferredIdeology == NO_POLICY_BRANCH_TYPE &&
			fixture.m_eOpinionBiggestInfluence == NO_PLAYER &&
			fixture.m_strOpinionTooltip.empty() && fixture.m_strOpinionUnhappinessTooltip.empty();
	else
		ok = ok && fixture.m_eOpinion == 901 && fixture.m_ePreferredIdeology == 902 &&
			fixture.m_eOpinionBiggestInfluence == 903 &&
			fixture.m_strOpinionTooltip == "dirty opinion tooltip" &&
			fixture.m_strOpinionUnhappinessTooltip == "dirty unhappiness tooltip";
	std::cout << label << " cultureInit opinionFields="
		<< (expectFixed ? "sentinels-and-empty-tooltips" : "dirty-values-retained")
		<< " " << (ok ? "PASS" : "FAIL") << "\n";
	return ok;
}

int main()
{
	bool ok = true;
	const int counts[] = { 25, 63, 64, 80 };
	for (int count : counts)
	{
		ok = runMilitaryCase<MilitaryOriginal>("original", count, false) && ok;
		ok = runMilitaryCase<MilitaryCandidate>("candidate", count, true) && ok;
	}
	ok = runCultureCase<CultureOriginal>("original", false) && ok;
	ok = runCultureCase<CultureCandidate>("candidate", true) && ok;
	return ok ? 0 : 1;
}
