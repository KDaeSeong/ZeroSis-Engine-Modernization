"""Propose checked save counts and deterministic SDK initialization/restore repairs."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from collect_baseline import PROJECT, digest


BASE = PROJECT / "evidence/sdk_x64/attempts/attempt_037/sdk_x64_patches.json"
SDK_ROOT = PROJECT / "Source/SDK_BNW_Original"
ACCEPTED_ROOT = PROJECT / "Source/SDK_BNW_x64"
OUTPUT = PROJECT / "Source/Porting/save_restore_patches.json"
EXP2 = "CvGameCoreDLL_Expansion2/"


@lru_cache(maxsize=None)
def baseline_text(relative: str) -> str:
    source = SDK_ROOT / relative
    text = source.read_bytes().decode("latin1")
    for patch in json.loads(BASE.read_text(encoding="utf-8"))["patches"]:
        if patch["file"] == relative:
            if text.count(patch["old"]) != patch["count"]:
                raise RuntimeError("Accepted attempt_037 baseline mismatch: " + patch["id"])
            text = text.replace(patch["old"], patch["new"])
    return text


def line_number(text: str, needle: str) -> int:
    lines = text.splitlines()
    matches = [index + 1 for index, line in enumerate(lines) if needle in line]
    if len(matches) != 1:
        raise RuntimeError(f"Expected one evidence line for {needle!r}; got {matches}")
    return matches[0]


def main() -> None:
    rows = []

    def add(file: str, patch_id: str, old: str, new: str, reason: str,
            writer: dict, reader: dict, callers: list[dict] | None = None) -> None:
        original = baseline_text(file)
        newline = "\r\n" if "\r\n" in original else "\n"
        old = old.replace("\r\n", "\n").replace("\n", newline)
        new = new.replace("\r\n", "\n").replace("\n", newline)
        if original.count(old) != 1:
            raise RuntimeError("Save-count patch context mismatch: " + patch_id)
        accepted = (ACCEPTED_ROOT / file).read_bytes().decode("latin1")
        # A specification is only generated for text that the separate builder can
        # reconstruct from the accepted baseline and its already accepted overlays.
        if accepted.count(old) != 1:
            raise RuntimeError("Accepted SDK source drift for " + patch_id)
        writer_file = writer["file"]
        writer_text = baseline_text(writer_file)
        writer_line = writer.get("line") or line_number(writer_text, writer["expression"])
        if writer["expression"] not in writer_text.splitlines()[writer_line - 1]:
            raise RuntimeError("Writer evidence line mismatch: " + patch_id)
        writer["line"] = writer_line
        reader_file = reader["file"]
        reader_text = baseline_text(reader_file)
        reader_line = reader.get("line") or line_number(reader_text, reader["expression"])
        if reader["expression"] not in reader_text.splitlines()[reader_line - 1]:
            raise RuntimeError("Reader evidence line mismatch: " + patch_id)
        reader["line"] = reader_line
        for caller in callers or []:
            caller_text = baseline_text(caller["file"])
            caller["line"] = line_number(caller_text, caller["expression"])
        rows.append({
            "id": patch_id,
            "file": file,
            "source_sha256": digest(SDK_ROOT / file),
            "old": old,
            "new": new,
            "count": 1,
            "reason": reason,
            "writer_evidence": writer,
            "reader_evidence": reader,
            "caller_evidence": callers or [],
        })

    helper = EXP2 + "CvInfosSerializationHelper.h"
    add(helper, "save_count_type_array_u32",
        "void WriteTypeArray(FDataStream& kStream, const std::vector<TType>& aiArray)\n{\n\tkStream << aiArray.size();",
        "void WriteTypeArray(FDataStream& kStream, const std::vector<TType>& aiArray)\n{\n\tkStream << CvChecked::Integer<unsigned int>(aiArray.size());",
        "Serialize the vector count as the legacy unsigned 32-bit field read by ReadTypeArrayDBLookup; reject a count that cannot be represented.",
        {"file": helper, "line": 646, "expression": "kStream << aiArray.size();", "container_type": "std::vector<TType>", "count_type": "size_t"},
        {"file": helper, "line": 508, "expression": "uint uiNumEntries;", "container_type": "std::vector<TType>", "count_type": "uint32"},
        [
            {"file": EXP2 + "CvPreGame.cpp", "expression": "CvInfosSerializationHelper::WriteTypeArray<MinorCivTypes>(saveTo, s_minorCivTypes);"},
            {"file": EXP2 + "CvPreGame.cpp", "expression": "CvInfosSerializationHelper::ReadTypeArrayDBLookup<MinorCivTypes>(loadFrom, s_minorCivTypes.dirtyGet(), \"MinorCivilizations\");"},
            {"file": EXP2 + "CvPreGame.cpp", "expression": "CvInfosSerializationHelper::WriteTypeArray<PlayerColorTypes>(saveTo, s_playerColors);"},
            {"file": EXP2 + "CvPreGame.cpp", "expression": "CvInfosSerializationHelper::ReadTypeArrayDBLookup<PlayerColorTypes>(loadFrom, s_playerColors.dirtyGet(), \"PlayerColors\");"},
        ])

    add(helper, "save_count_hashed_type_array_u32",
        "void WriteHashedTypeArray(FDataStream& kStream, const std::vector<TType>& aiArray)\n{\n\tkStream << aiArray.size();",
        "void WriteHashedTypeArray(FDataStream& kStream, const std::vector<TType>& aiArray)\n{\n\tkStream << CvChecked::Integer<unsigned int>(aiArray.size());",
        "Serialize the revealed-resource vector count as the legacy unsigned 32-bit field read by ReadHashedTypeArray; reject a count that cannot be represented.",
        {"file": helper, "line": 658, "expression": "kStream << aiArray.size();", "container_type": "std::vector<TType>", "count_type": "size_t"},
        {"file": helper, "line": 439, "expression": "uint uiNumEntries;", "container_type": "std::vector<TType>", "count_type": "uint32"},
        [
            {"file": EXP2 + "CvTeam.cpp", "expression": "CvInfosSerializationHelper::WriteHashedTypeArray(kStream, m_aeRevealedResources);"},
            {"file": EXP2 + "CvTeam.cpp", "expression": "CvInfosSerializationHelper::ReadHashedTypeArray(kStream, m_aeRevealedResources);"},
        ])

    add(helper, "save_count_hashed_data_array_u32",
        "void WriteHashedDataArray(FDataStream& kStream, const std::vector<TData>& aArray)\n{\n\tkStream << aArray.size();",
        "void WriteHashedDataArray(FDataStream& kStream, const std::vector<TData>& aArray)\n{\n\tkStream << CvChecked::Integer<unsigned int>(aArray.size());",
        "Serialize the std::vector data-array count as the legacy unsigned 32-bit field read by ReadHashedDataArray; reject a count that cannot be represented.",
        {"file": helper, "line": 588, "expression": "kStream << aArray.size();", "container_type": "std::vector<TData>", "count_type": "size_t"},
        {"file": helper, "line": 391, "expression": "uint uiNumEntries;", "container_type": "std::vector<TData>", "count_type": "uint32"},
        [
            {"file": EXP2 + "CvTraitClasses.cpp", "expression": "CvInfosSerializationHelper::WriteHashedDataArray<ResourceTypes>(kStream, m_aiResourceQuantityModifier);"},
            {"file": EXP2 + "CvTraitClasses.cpp", "expression": "CvInfosSerializationHelper::ReadHashedDataArray(kStream, m_aiResourceQuantityModifier);"},
            {"file": EXP2 + "CvPlayer.cpp", "expression": "CvInfosSerializationHelper::WriteHashedDataArray<ResourceTypes, int>(kStream, m_paiNumResourceUsed);"},
            {"file": EXP2 + "CvPlayer.cpp", "expression": "CvInfosSerializationHelper::WriteHashedDataArray<ResourceTypes, int>(kStream, m_paiNumResourceTotal);"},
            {"file": EXP2 + "CvPlayer.cpp", "expression": "CvInfosSerializationHelper::WriteHashedDataArray<ResourceTypes, int>(kStream, m_paiResourceGiftedToMinors);"},
            {"file": EXP2 + "CvPlayer.cpp", "expression": "CvInfosSerializationHelper::WriteHashedDataArray<ResourceTypes, int>(kStream, m_paiResourceExport);"},
            {"file": EXP2 + "CvPlayer.cpp", "expression": "CvInfosSerializationHelper::WriteHashedDataArray<ResourceTypes, int>(kStream, m_paiResourceImport);"},
            {"file": EXP2 + "CvPlayer.cpp", "expression": "CvInfosSerializationHelper::WriteHashedDataArray<ResourceTypes, int>(kStream, m_paiResourceFromMinors);"},
            {"file": EXP2 + "CvPlayer.cpp", "expression": "CvInfosSerializationHelper::WriteHashedDataArray<ResourceTypes, int>(kStream, m_paiResourcesSiphoned);"},
            {"file": EXP2 + "CvPlayer.cpp", "expression": "CvInfosSerializationHelper::WriteHashedDataArray<BuildingTypes, int>(kStream, m_paiFreeBuildingCount);"},
            {"file": EXP2 + "CvPlayer.cpp", "expression": "CvInfosSerializationHelper::WriteHashedDataArray<PromotionTypes, int>(kStream, m_paiFreePromotionCount);"},
            {"file": EXP2 + "CvCity.cpp", "expression": "CvInfosSerializationHelper::WriteHashedDataArray<ResourceTypes, int>(kStream, m_paiNoResource);"},
            {"file": EXP2 + "CvCity.cpp", "expression": "CvInfosSerializationHelper::WriteHashedDataArray<ResourceTypes, int>(kStream, m_paiFreeResource);"},
            {"file": EXP2 + "CvCity.cpp", "expression": "CvInfosSerializationHelper::WriteHashedDataArray<ResourceTypes, int>(kStream, m_paiNumResourcesLocal);"},
            {"file": EXP2 + "CvCity.cpp", "expression": "CvInfosSerializationHelper::WriteHashedDataArray<UnitTypes, int>(kStream, m_paiUnitProduction);"},
            {"file": EXP2 + "CvCity.cpp", "expression": "CvInfosSerializationHelper::WriteHashedDataArray<UnitTypes, int>(kStream, m_paiUnitProductionTime);"},
            {"file": EXP2 + "CvCity.cpp", "expression": "CvInfosSerializationHelper::WriteHashedDataArray<PromotionTypes, int>(kStream, m_paiFreePromotionCount);"},
        ])

    helper_original = baseline_text(helper)
    helper_include_old = "#pragma once\n"
    helper_include_new = helper_include_old + '#include "CvCheckedNarrow.h"\n'
    helper_newline = "\r\n" if "\r\n" in helper_original else "\n"
    helper_include_old = helper_include_old.replace("\n", helper_newline)
    helper_include_new = helper_include_new.replace("\n", helper_newline)
    if helper_original.count(helper_include_old) != 1:
        raise RuntimeError("CvInfosSerializationHelper include anchor changed")
    rows.append({
        "id": "save_count_helper_checked_include",
        "file": helper,
        "source_sha256": digest(SDK_ROOT / helper),
        "old": helper_include_old,
        "new": helper_include_new,
        "count": 1,
        "reason": "Declare CvChecked::Integer in the template header itself so every including translation unit can parse the checked count writers.",
        "writer_evidence": {"file": helper, "line": 588, "expression": "kStream << aArray.size();", "container_type": "std::vector<TData>", "count_type": "size_t"},
        "reader_evidence": {"file": helper, "line": 391, "expression": "uint uiNumEntries;", "container_type": "std::vector<TData>", "count_type": "uint32"},
    })

    trait = EXP2 + "CvTraitClasses.cpp"
    add(trait, "save_count_maya_bonus_choices_i32",
        "kStream << m_aMayaBonusChoices.size();",
        "kStream << CvChecked::Integer<int>(m_aMayaBonusChoices.size());",
        "Preserve the legacy signed 32-bit count consumed by CvPlayerTraits::Read for the std::vector Maya choice list.",
        {"file": trait, "line": 2944, "expression": "kStream << m_aMayaBonusChoices.size();", "container_type": "std::vector<MayaBonusChoice>", "count_type": "size_t"},
        {"file": trait, "line": 2698, "expression": "kStream >> iNumEntries;", "container_type": "std::vector<MayaBonusChoice>", "count_type": "int32", "read_function": "CvPlayerTraits::Read"},
        [
            {"file": EXP2 + "CvPlayer.cpp", "expression": "m_pTraits->Write(kStream);"},
            {"file": EXP2 + "CvPlayer.cpp", "expression": "m_pTraits->Read(kStream);"},
        ])

    add(trait, "save_count_no_train_i32",
        "kStream << m_abNoTrain.size();",
        "kStream << CvChecked::Integer<int>(m_abNoTrain.size());",
        "Preserve the legacy signed 32-bit count consumed by CvPlayerTraits::Read for the std::vector<bool> train mask.",
        {"file": trait, "line": 2971, "expression": "kStream << m_abNoTrain.size();", "container_type": "std::vector<bool>", "count_type": "size_t"},
        {"file": trait, "line": 2786, "expression": "kStream >> iNumEntries;", "container_type": "std::vector<bool>", "count_type": "int32", "read_function": "CvPlayerTraits::Read"},
        [
            {"file": EXP2 + "CvPlayer.cpp", "expression": "m_pTraits->Write(kStream);"},
            {"file": EXP2 + "CvPlayer.cpp", "expression": "m_pTraits->Read(kStream);"},
        ])

    culture = EXP2 + "CvCultureClasses.cpp"
    add(culture, "save_count_dig_complete_plots_i32",
        "saveTo << readFrom.m_aDigCompletePlots.size();",
        "saveTo << CvChecked::Integer<int>(readFrom.m_aDigCompletePlots.size());",
        "Preserve the legacy signed 32-bit plot count consumed by CvPlayerCulture::operator>> for the std::vector of completed dig sites.",
        {"file": culture, "line": 3922, "expression": "saveTo << readFrom.m_aDigCompletePlots.size();", "container_type": "std::vector<CvPlot*>", "count_type": "size_t"},
        {"file": culture, "line": 3832, "expression": "loadFrom >> iEntriesToRead;", "container_type": "std::vector<CvPlot*>", "count_type": "int32", "read_function": "operator>>(CvPlayerCulture&)"},
        [
            {"file": EXP2 + "CvPlayer.cpp", "expression": "kStream << *m_pCulture;"},
            {"file": EXP2 + "CvPlayer.cpp", "expression": "kStream >> *m_pCulture;"},
        ])

    requests = EXP2 + "CvDiplomacyRequests.cpp"
    add(requests, "save_count_diplomacy_requests_u32",
        "kStream << m_aRequests.size();",
        "kStream << CvChecked::Integer<unsigned int>(m_aRequests.size());",
        "Preserve the legacy unsigned 32-bit request-list count while rejecting an unrepresentable std::list size. The current CvPlayer Read/Write integration is disabled, but this paired serializer API must remain wire-compatible if used.",
        {"file": requests, "expression": "kStream << m_aRequests.size();", "container_type": "std::list<Request>", "count_type": "size_t"},
        {"file": requests, "expression": "kStream >> uiListSize;", "container_type": "std::list<Request>", "count_type": "uint32", "read_function": "CvDiplomacyRequests::Read"})

    espionage = EXP2 + "CvEspionageClasses.cpp"
    add(espionage, "save_count_spy_name_order_i32",
        "saveTo << readFrom.m_aiSpyListNameOrder.size();",
        "saveTo << CvChecked::Integer<int>(readFrom.m_aiSpyListNameOrder.size());",
        "Preserve the legacy signed 32-bit count consumed by CvPlayerEspionage::operator>> for the std::vector spy-name order.",
        {"file": espionage, "line": 3725, "expression": "saveTo << readFrom.m_aiSpyListNameOrder.size();", "container_type": "std::vector<int>", "count_type": "size_t"},
        {"file": espionage, "line": 3618, "expression": "loadFrom >> iNumSpyNames;", "container_type": "std::vector<int>", "count_type": "int32", "read_function": "operator>>(CvPlayerEspionage&)"},
        [
            {"file": EXP2 + "CvPlayer.cpp", "expression": "kStream << *m_pEspionage;"},
            {"file": EXP2 + "CvPlayer.cpp", "expression": "kStream >> *m_pEspionage;"},
        ])

    add(espionage, "save_count_heist_locations_i32",
        "saveTo << readFrom.m_aHeistLocations[uiCiv].size();",
        "saveTo << CvChecked::Integer<int>(readFrom.m_aHeistLocations[uiCiv].size());",
        "Preserve each legacy signed 32-bit count consumed by CvPlayerEspionage::operator>> for the per-civilization std::vector of heist locations.",
        {"file": espionage, "line": 3758, "expression": "saveTo << readFrom.m_aHeistLocations[uiCiv].size();", "container_type": "std::vector<HeistLocation>", "count_type": "size_t", "instances_per_save": "MAX_MAJOR_CIVS"},
        {"file": espionage, "line": 3667, "expression": "loadFrom >> iNumEntries;", "container_type": "std::vector<HeistLocation>", "count_type": "int32", "read_function": "operator>>(CvPlayerEspionage&)"},
        [
            {"file": EXP2 + "CvPlayer.cpp", "expression": "kStream << *m_pEspionage;"},
            {"file": EXP2 + "CvPlayer.cpp", "expression": "kStream >> *m_pEspionage;"},
        ])

    add(espionage, "save_count_spy_notification_messages_i32",
        "saveTo << readFrom.m_aSpyNotificationMessages.size();",
        "saveTo << CvChecked::Integer<int>(readFrom.m_aSpyNotificationMessages.size());",
        "Preserve the legacy signed 32-bit count consumed by CvPlayerEspionage::operator>> for spy notification messages.",
        {"file": espionage, "line": 3766, "expression": "saveTo << readFrom.m_aSpyNotificationMessages.size();", "container_type": "std::vector<SpyNotificationMessage>", "count_type": "size_t"},
        {"file": espionage, "line": 3678, "expression": "loadFrom >> iNumMessages;", "container_type": "std::vector<SpyNotificationMessage>", "count_type": "int32", "read_function": "operator>>(CvPlayerEspionage&)"},
        [
            {"file": EXP2 + "CvPlayer.cpp", "expression": "kStream << *m_pEspionage;"},
            {"file": EXP2 + "CvPlayer.cpp", "expression": "kStream >> *m_pEspionage;"},
        ])

    add(espionage, "save_count_intrigue_notification_messages_i32",
        "saveTo << readFrom.m_aIntrigueNotificationMessages.size();",
        "saveTo << CvChecked::Integer<int>(readFrom.m_aIntrigueNotificationMessages.size());",
        "Preserve the legacy signed 32-bit count consumed by CvPlayerEspionage::operator>> for intrigue notification messages.",
        {"file": espionage, "line": 3776, "expression": "saveTo << readFrom.m_aIntrigueNotificationMessages.size();", "container_type": "std::vector<IntrigueNotificationMessage>", "count_type": "size_t"},
        {"file": espionage, "line": 3690, "expression": "loadFrom >> iNumMessages;", "container_type": "std::vector<IntrigueNotificationMessage>", "count_type": "int32", "read_function": "operator>>(CvPlayerEspionage&)"},
        [
            {"file": EXP2 + "CvPlayer.cpp", "expression": "kStream << *m_pEspionage;"},
            {"file": EXP2 + "CvPlayer.cpp", "expression": "kStream >> *m_pEspionage;"},
        ])

    ai_read_old = """\
// serialization read
FDataStream& operator>>(FDataStream& loadFrom, CvEspionageAI& writeTo)
{
	uint uiVersion;
	loadFrom >> uiVersion;

	uint uiCount;
	loadFrom >> uiCount;
	int iValue;
	for(uint ui = 0; ui < uiCount; ui++)
	{
		loadFrom >> iValue;
		writeTo.m_aiCivOutOfTechTurn.push_back(iValue);
	}

	loadFrom >> uiCount;
	for(uint ui = 0; ui < uiCount; ui++)
	{
		loadFrom >> iValue;
		writeTo.m_aiNumSpiesCaught.push_back(iValue);
	}

	loadFrom >> uiCount;
	for(uint ui = 0; ui < uiCount; ui++)
	{
		loadFrom >> iValue;
		writeTo.m_aiNumSpiesKilled.push_back(iValue);
	}

	loadFrom >> uiCount;
	for(uint ui = 0; ui < uiCount; ui++)
	{
		loadFrom >> iValue;
		writeTo.m_aiNumSpiesDied.push_back(iValue);
	}

	loadFrom >> uiCount;
	for(uint ui = 0; ui < uiCount; ui++)
	{
		loadFrom >> iValue;
		writeTo.m_aiTurnLastSpyCaught.push_back(iValue);
	}

	loadFrom >> uiCount;
	for(uint ui = 0; ui < uiCount; ui++)
	{
		loadFrom >> iValue;
		writeTo.m_aiTurnLastSpyKilled.push_back(iValue);
	}

	loadFrom >> uiCount;
	for(uint ui = 0; ui < uiCount; ui++)
	{
		loadFrom >> iValue;
		writeTo.m_aiTurnLastSpyDied.push_back(iValue);
	}

	loadFrom >> writeTo.m_bUNCountdownStarted;
	loadFrom >> writeTo.m_iTurnEspionageStarted;
	
	return loadFrom;
}"""
    ai_read_new = ai_read_old.replace(
        "\tloadFrom >> uiCount;\n", "\tloadFrom >> uiCount;\n\twriteTo.m_aiCivOutOfTechTurn.clear();\n", 1
    )
    for vector_name in (
        "m_aiNumSpiesCaught", "m_aiNumSpiesKilled", "m_aiNumSpiesDied",
        "m_aiTurnLastSpyCaught", "m_aiTurnLastSpyKilled", "m_aiTurnLastSpyDied",
    ):
        ai_read_new = ai_read_new.replace(
            f"\tloadFrom >> uiCount;\n\tfor(uint ui = 0; ui < uiCount; ui++)\n\t{{\n\t\tloadFrom >> iValue;\n\t\twriteTo.{vector_name}.push_back(iValue);",
            f"\tloadFrom >> uiCount;\n\twriteTo.{vector_name}.clear();\n\tfor(uint ui = 0; ui < uiCount; ui++)\n\t{{\n\t\tloadFrom >> iValue;\n\t\twriteTo.{vector_name}.push_back(iValue);",
            1,
        )
    if ai_read_new.count(".clear();") != 7:
        raise RuntimeError("CvEspionageAI read replacement did not clear exactly seven arrays")
    add(espionage, "restore_espionage_ai_static_vectors_before_read",
        ai_read_old, ai_read_new,
        "Replace the seven MAX_MAJOR_CIVS defaults established by CvEspionageAI::Init/Reset before reading their serialized values; do not append a second set of entries.",
        {"file": espionage, "expression": "saveTo << readFrom.m_aiCivOutOfTechTurn.size();", "container_type": "FStaticVector<int, MAX_MAJOR_CIVS>", "count_type": "uint"},
        {"file": espionage, "expression": "writeTo.m_aiCivOutOfTechTurn.push_back(iValue);", "container_type": "FStaticVector<int, MAX_MAJOR_CIVS>", "count_type": "uint", "read_function": "operator>>(CvEspionageAI&)"},
        [
            {"file": EXP2 + "CvPlayer.cpp", "expression": "m_pEspionageAI->Init(this);"},
            {"file": EXP2 + "CvPlayer.cpp", "expression": "kStream >> *m_pEspionageAI;"},
            {"file": EXP2 + "CvPlayer.cpp", "expression": "kStream << *m_pEspionageAI;"},
        ])

    # Add the checked-narrowing declaration needed by the proposed list writer.
    original = baseline_text(requests)
    include_old = '#include "CvDiplomacyRequests.h"\n'
    include_new = include_old + '#include "CvCheckedNarrow.h"\n'
    newline = "\r\n" if "\r\n" in original else "\n"
    include_old = include_old.replace("\n", newline)
    include_new = include_new.replace("\n", newline)
    if original.count(include_old) != 1:
        raise RuntimeError("DiplomacyRequests include anchor changed")
    # The include-only support patch repeats the relevant pair references so every
    # proposed change remains auditable as part of that serialized field contract.
    rows.append({
        "id": "save_count_diplomacy_requests_checked_include",
        "file": requests,
        "source_sha256": digest(SDK_ROOT / requests),
        "old": include_old,
        "new": include_new,
        "count": 1,
        "reason": "Make the checked 32-bit size conversion explicit in the serializer translation unit.",
        "writer_evidence": {"file": requests, "line": line_number(original, "kStream << m_aRequests.size();"), "expression": "kStream << m_aRequests.size();", "container_type": "std::list<Request>", "count_type": "size_t"},
        "reader_evidence": {"file": requests, "line": line_number(original, "kStream >> uiListSize;"), "expression": "kStream >> uiListSize;", "container_type": "std::list<Request>", "count_type": "uint32"},
    })

    culture_original = baseline_text(culture)
    culture_include_old = '#include "CvGameCoreDLLPCH.h"\n'
    culture_include_new = culture_include_old + '#include "CvCheckedNarrow.h"\n'
    culture_newline = "\r\n" if "\r\n" in culture_original else "\n"
    culture_include_old = culture_include_old.replace("\n", culture_newline)
    culture_include_new = culture_include_new.replace("\n", culture_newline)
    if culture_original.count(culture_include_old) != 1:
        raise RuntimeError("CultureClasses include anchor changed")
    rows.append({
        "id": "save_count_dig_complete_plots_checked_include",
        "file": culture,
        "source_sha256": digest(SDK_ROOT / culture),
        "old": culture_include_old,
        "new": culture_include_new,
        "count": 1,
        "reason": "Make the checked 32-bit size conversion explicit in the culture serializer translation unit.",
        "writer_evidence": {"file": culture, "line": 3922, "expression": "saveTo << readFrom.m_aDigCompletePlots.size();", "container_type": "std::vector<CvPlot*>", "count_type": "size_t"},
        "reader_evidence": {"file": culture, "line": 3832, "expression": "loadFrom >> iEntriesToRead;", "container_type": "std::vector<CvPlot*>", "count_type": "int32"},
    })

    military = EXP2 + "CvMilitaryAI.cpp"
    add(military, "initialize_military_player_arrays_with_player_bound",
        "\t\tm_paiTurnStrategyAdopted[iI] = -1;\n\t\tm_paeLastTurnWarState[iI] = NO_WAR_STATE_TYPE;",
        "\t\tm_paiTurnStrategyAdopted[iI] = -1;\n\t}\n\n\t// These four arrays are indexed by player, independently of strategy count.\n\tfor(iI = 0; iI < MAX_CIV_PLAYERS; iI++)\n\t{\n\t\tm_paeLastTurnWarState[iI] = NO_WAR_STATE_TYPE;",
        "Reset the four MAX_CIV_PLAYERS diplomacy-history arrays over their allocated player bound. The original strategy-count loop left serialized tails uninitialized for fewer strategies and could overrun them for more strategies.",
        {"file": military, "expression": "kStream << ArrayWrapper<int>(MAX_CIV_PLAYERS, m_paeLastTurnMilitaryStrength);"},
        {"file": military, "expression": "ArrayWrapper<int> wrapm_paeLastTurnMilitaryStrength(MAX_CIV_PLAYERS, m_paeLastTurnMilitaryStrength);"},
        [{"file": EXP2 + "CvPlayer.cpp", "expression": "m_pMilitaryAI->Write(kStream);"}])

    add(culture, "initialize_culture_public_opinion_before_first_save",
        "\tm_iLastTurnLifetimeCulture = 0;\n\tm_iOpinionUnhappiness = 0;",
        "\tm_iLastTurnLifetimeCulture = 0;\n\tm_eOpinion = NO_PUBLIC_OPINION;\n\tm_ePreferredIdeology = NO_POLICY_BRANCH_TYPE;\n\tm_eOpinionBiggestInfluence = NO_PLAYER;\n\tm_iOpinionUnhappiness = 0;\n\tm_strOpinionTooltip = \"\";\n\tm_strOpinionUnhappinessTooltip = \"\";",
        "Initialize public-opinion fields to the existing DoPublicOpinion/legacy-reader defaults before any player can be saved, including inactive slots which have not executed a turn. Clear associated derived tooltips on reinitialization.",
        {"file": culture, "expression": "saveTo << readFrom.m_eOpinion;"},
        {"file": culture, "expression": "writeTo.m_eOpinion = (PublicOpinionTypes)iTemp;"},
        [{"file": EXP2 + "CvPlayer.cpp", "expression": "kStream << *m_pCulture;"}])

    add(trait, "initialize_optional_trait_combat_improvement",
        "\tm_eFreeUnitPrereqTech(NO_TECH),\n\tm_eFreeBuilding(NO_BUILDING),",
        "\tm_eFreeUnitPrereqTech(NO_TECH),\n\tm_eCombatBonusImprovement(NO_IMPROVEMENT),\n\tm_eFreeBuilding(NO_BUILDING),",
        "Initialize the optional CombatBonusImprovement field in each newly allocated trait entry. CacheResults only assigns non-NULL database values; InitPlayerTraits otherwise copies an indeterminate enum over the player's existing NO_IMPROVEMENT default.",
        {"file": trait, "expression": "kStream << m_eCombatBonusImprovement;"},
        {"file": trait, "expression": "kStream >> m_eCombatBonusImprovement;"},
        [{"file": trait, "expression": "m_eCombatBonusImprovement = trait->GetCombatBonusImprovement();"}])

    operation = EXP2 + "CvAIOperation.cpp"
    add(operation, "initialize_operation_reinforcement_flag_in_reset",
        "\tm_iDefaultArea = FFreeList::INVALID_INDEX;\n\tm_eCurrentState = AI_OPERATION_STATE_ABORTED;",
        "\tm_iDefaultArea = FFreeList::INVALID_INDEX;\n\tm_bShouldReplaceLossesWithReinforcements = false;\n\tm_eCurrentState = AI_OPERATION_STATE_ABORTED;",
        "Initialize the serialized reinforcement-replacement flag in Reset. CvAIOperationBasicCityAttack::Init is a virtual override that calls Reset directly and does not call CvAIOperation::Init, so the base Init assignment is bypassed for this common operation; without this default, the bool serialized by CvAIOperation::Write remains indeterminate.",
        {"file": operation, "expression": "kStream << m_bShouldReplaceLossesWithReinforcements;", "field": "m_bShouldReplaceLossesWithReinforcements", "serialized_type": "bool"},
        {"file": operation, "expression": "kStream >> m_bShouldReplaceLossesWithReinforcements;", "field": "m_bShouldReplaceLossesWithReinforcements", "serialized_type": "bool"},
        [
            {"file": EXP2 + "CvPlayer.cpp", "expression": "pNewOperation->Init(m_iNextOperationID, m_eID, eEnemy, iArea, pTarget, pMuster);", "dispatch": "virtual Init after CreateOperation"},
            {"file": operation, "expression": "void CvAIOperationBasicCityAttack::Init(", "behavior": "override calls Reset without base CvAIOperation::Init"},
            {"file": operation, "expression": "m_bShouldReplaceLossesWithReinforcements = false;", "behavior": "base Init default bypassed by BasicCityAttack override"},
        ])

    # Validate ordered application and expose affected translation units for the builder.
    candidates = {}
    for file in sorted({patch["file"] for patch in rows}):
        text = baseline_text(file)
        for patch in rows:
            if patch["file"] == file:
                if text.count(patch["old"]) != patch["count"]:
                    raise RuntimeError("Save-count patch ordering mismatch: " + patch["id"])
                text = text.replace(patch["old"], patch["new"])
        candidates[file] = text

    report = {
        "status": "SDK_SAVE_RESTORE_PATCHES_PROPOSED_NOT_APPLIED",
        "baseline": {"path": str(BASE), "sha256": digest(BASE)},
        "recipe": {"path": str(Path(__file__).resolve()), "sha256": digest(Path(__file__).resolve())},
        "baseline_patch_count": len(json.loads(BASE.read_text(encoding="utf-8"))["patches"]),
        "added_patch_count": len(rows),
        "patches": rows,
        "target_files": sorted(candidates),
        "translation_units": [
            EXP2 + "CvPreGame.cpp",
            EXP2 + "CvTeam.cpp",
            EXP2 + "CvTraitClasses.cpp",
            EXP2 + "CvCultureClasses.cpp",
            EXP2 + "CvDiplomacyRequests.cpp",
            EXP2 + "CvPlayer.cpp",
            EXP2 + "CvCity.cpp",
            EXP2 + "CvEspionageClasses.cpp",
            EXP2 + "CvMilitaryAI.cpp",
            EXP2 + "CvAIOperation.cpp",
        ],
        "template_specialization_audit": [
            {"template": "WriteTypeArray(std::vector<TType>)", "specializations": ["MinorCivTypes", "PlayerColorTypes"], "translation_units": [EXP2 + "CvPreGame.cpp"]},
            {"template": "WriteHashedTypeArray(std::vector<TType>)", "specializations": ["ResourceTypes"], "translation_units": [EXP2 + "CvTeam.cpp"]},
            {"template": "WriteHashedDataArray(std::vector<TData>)", "specializations": ["ResourceTypes,int", "BuildingTypes,int", "PromotionTypes,int", "UnitTypes,int"], "argument_forms": ["std::vector<int>", "FAutoVariable<std::vector<int>> via operator const ObjectType&()"], "translation_units": [EXP2 + "CvPlayer.cpp", EXP2 + "CvCity.cpp", EXP2 + "CvTraitClasses.cpp"]},
        ],
        "wire_contract": "Affected legacy counts remain 32-bit int/uint; restored vectors replace defaults, new-game state uses existing SDK sentinel values, and no save schema/version changes.",
        "sdk_source_modified": False,
        "gamecore_loaded": False,
        "game_launched": False,
    }
    OUTPUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(report["status"])


if __name__ == "__main__":
    main()
