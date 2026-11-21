"""Inspect copied Player suffix serializers and portable parser source only.

Import and inspect do not write, start child processes, load native libraries,
or access installed games, saves, runtime evidence, or the private save format.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re

from inspect_player_post_traits_sources import _Sources, _operands, _ordered, _require


_CORE = "CvGameCoreDLL_Expansion2/"
_ENUM_NAMES = ("CITY_CLOSE_DEFENSE", "RAPID_RESPONSE", "BASIC_CITY_ATTACK",
    "DESTROY_BARBARIAN_CAMP", "FOUND_CITY", "PILLAGE_ENEMY", "SNEAK_CITY_ATTACK",
    "SMALL_CITY_ATTACK", "MERCHANT_DELEGATION", "NAVAL_BOMBARDMENT", "NAVAL_SUPERIORITY",
    "COLONIZE", "QUICK_COLONIZE", "NAVAL_ATTACK", "NAVAL_SNEAK_ATTACK", "CITY_STATE_ATTACK",
    "CITY_STATE_NAVAL_ATTACK", "NUKE_ATTACK", "PURE_NAVAL_CITY_ATTACK", "CONCERT_TOUR")
_FACTORY_CLASSES = ("CvAIOperationCityCloseDefense", "CvAIOperationRapidResponse",
    "CvAIOperationBasicCityAttack", "CvAIOperationDestroyBarbarianCamp", "CvAIOperationFoundCity",
    "CvAIOperationPillageEnemy", "CvAIOperationSneakCityAttack", "CvAIOperationSmallCityAttack",
    "CvAIOperationMerchantDelegation", "CvAIOperationNavalBombardment", "CvAIOperationNavalSuperiority",
    "CvAINavalEscortedOperation", "CvAIOperationQuickColonize", "CvAIOperationNavalAttack",
    "CvAIOperationNavalSneakAttack", "CvAIOperationCityStateAttack", "CvAIOperationNavalCityStateAttack",
    "CvAIOperationNukeAttack", "CvAIOperationPureNavalCityAttack", "CvAIOperationConcertTour")
_BASE_OPERANDS = ["uiVersion", "m_iID", "m_eOwner", "m_eEnemy", "m_eCurrentState", "m_iDefaultArea",
    "m_bShouldReplaceLossesWithReinforcements", "m_eMoveType", "m_iTargetX", "m_iTargetY", "m_iMusterX",
    "m_iMusterY", "m_iStartCityX", "m_iStartCityY", "m_iLastTurnMoved", "m_viArmyIDs",
    "m_viListOfUnitsWeStillNeedToBuild", "m_viListOfUnitsCitiesHaveCommittedToBuild"]
_SERIALIZERS = {
    "CvAIOperation": (None, _BASE_OPERANDS[1:]),
    "CvAIOperationBasicCityAttack": ("CvAIOperation", []),
    "CvAIOperationDestroyBarbarianCamp": ("CvAIOperation", ["m_bCivilianRescue", "m_iUnitToRescue"]),
    "CvAIOperationPillageEnemy": ("CvAIOperation", []),
    "CvAIEscortedOperation": ("CvAIOperation", ["m_bEscorted", "m_eCivilianType", "m_iTargetArea"]),
    "CvAINavalOperation": ("CvAIOperation", []),
    "CvAIOperationNavalBombardment": ("CvAINavalOperation", []),
    "CvAIOperationNavalSuperiority": ("CvAINavalOperation", []),
    "CvAIOperationPureNavalCityAttack": ("CvAINavalOperation", []),
    "CvAIOperationCityCloseDefense": ("CvAIOperation", []),
    "CvAIOperationRapidResponse": ("CvAIOperation", []),
    "CvAINavalEscortedOperation": ("CvAIOperation", ["m_eCivilianType"]),
    "CvAIOperationNavalAttack": ("CvAINavalEscortedOperation", []),
    "CvAIOperationNukeAttack": ("CvAIOperation", ["m_iBestUnitID"]),
}
_TAIL = ["m_ReplayDataSets", "m_ReplayDataSetValues", "m_aVote", "m_aUnitExtraCosts"]


def _text(files, path):
    files.artifact(path)
    return path.read_text(encoding="latin1").replace("\r\n", "\n")


def _pair(files, roots, relative, signatures, name, equal=True):
    witnesses, bodies = [], {}
    for kind, root in roots.items():
        rm, read = files.body(root / relative, signatures[0])
        wm, write = files.body(root / relative, signatures[1])
        witnesses.append(dict(kind=kind, read=rm, write=wm))
        bodies[kind] = read, write
    if equal:
        _require(bodies["original"] == bodies["current"], "unclassified Player end change: " + name)
    return dict(name=name, witnesses=witnesses, original_read_operands=_operands(bodies["original"][0], ">>"),
                original_write_operands=_operands(bodies["original"][1], "<<")), bodies


def _methods(files, roots, cpp, cls, read="Read", write="Write", equal=True):
    return _pair(files, roots, _CORE + cpp,
        (f"void {cls}::{read}(FDataStream& kStream)", f"void {cls}::{write}(FDataStream& kStream) const"), cls, equal)


def _class_blocks(text):
    return {m[1]: (m[2], m[3]) for m in re.finditer(
        r"(?ms)^class (CvAI\w+)(?:\s*:\s*public (CvAI\w+))?\s*\n\{(.*?)^\};", text)}


def _operations(files, roots):
    states, factories, declarations, classes = [], [], [], None
    signature = "CvAIOperation* CvAIOperation::CreateOperation(AIOperationTypes eAIOperationType, PlayerTypes ePlayer)"
    factory_bodies = []
    for kind, root in roots.items():
        meta, body = files.body(root / _CORE / "CvAIOperation.cpp", signature)
        factories.append(dict(kind=kind, factory=meta))
        factory_bodies.append(body)
        header = _text(files, root / _CORE / "CvAIOperation.h")
        enum_match = re.search(r"enum AIOperationTypes\s*\{([^}]+)\}", header)
        _require(enum_match is not None, "operation type enum missing")
        entries = [part.strip() for part in enum_match[1].split(",") if part.strip()]
        expected = ["INVALID_AI_OPERATION = -1", *["AI_OPERATION_" + name for name in _ENUM_NAMES], "NUM_AI_OPERATIONS"]
        _require(entries == expected, "operation enum order changed")
        parsed = _class_blocks(header)
        identity = {name: (base, bool(re.search(r"\bvoid Read\(FDataStream", block)),
                    bool(re.search(r"\bvoid Write\(FDataStream", block))) for name, (base, block) in parsed.items()}
        _require(classes is None or identity == classes, "operation inheritance or override set changed")
        classes = identity
        _require({name for name, (_, read, write) in identity.items() if read or write} == set(_SERIALIZERS)
                 and all(read == write for _, read, write in identity.values()), "operation serializer declarations changed")
        for token in ("int m_iOperationID;", "int m_iArmyID;", "int m_iSlotID;", "std::vector<int> m_viArmyIDs;",
            "std::vector<OperationSlot> m_viListOfUnitsWeStillNeedToBuild;",
            "std::vector<OperationSlot> m_viListOfUnitsCitiesHaveCommittedToBuild;",
            "bool m_bShouldReplaceLossesWithReinforcements;", "bool m_bCivilianRescue;", "bool m_bEscorted;",
            "UnitAITypes m_eCivilianType;", "int m_iTargetArea;", "int m_iUnitToRescue;", "int m_iBestUnitID;"):
            _require(token in header, "operation member declaration changed: " + token)
        declarations.append(dict(kind=kind, header=files.artifact(root / _CORE / "CvAIOperation.h"),
                                 enum_values=[dict(name=name, value=i) for i, name in enumerate(expected[1:-1])]))
    _require(factory_bodies[0] == factory_bodies[1], "operation factory changed")
    body = factory_bodies[0]
    cases = list(re.finditer(r"case (AI_OPERATION_\w+):", body))
    _require(len(cases) == 20 and {m[1] for m in cases} == {"AI_OPERATION_" + name for name in _ENUM_NAMES},
             "operation factory case set changed")
    constructed = {}
    for i, match in enumerate(cases):
        section = body[match.end():cases[i + 1].start() if i + 1 < len(cases) else len(body)]
        constructed[match[1]] = re.findall(r"return FNEW\((CvAI\w+)\(\)", section)
    rows = []
    for i, (name, cls) in enumerate(zip(_ENUM_NAMES, _FACTORY_CLASSES)):
        expected = (["CvAIOperationQuickSneakCityAttack", cls] if i == 6 else [cls])
        _require(constructed["AI_OPERATION_" + name] == expected, "factory target changed: " + name)
        providers = []
        for concrete in expected:
            provider = concrete
            visited = set()
            while not classes[provider][1]:
                _require(provider not in visited and classes[provider][0] is not None, "operation inheritance cycle")
                visited.add(provider)
                provider = classes[provider][0]
            providers.append(provider)
        _require(len(set(providers)) == 1, "conditional factory branch has another wire serializer")
        chain, provider = [], providers[0]
        while provider:
            chain.insert(0, provider)
            provider = _SERIALIZERS[provider][0]
        rows.append(dict(type=i, enum="AI_OPERATION_" + name, factory_classes=expected, serializer_chain=chain))
    _require("GC.getGame().getGameTurn() < 50" in body and "GetBoldness() >= 5" in body,
             "conditional sneak factory predicate changed")
    cpp = _text(files, roots["original"] / _CORE / "CvAIOperation.cpp")
    signatures = re.findall(r"(?m)^void (CvAI\w+)::(?:Read|Write)\(FDataStream& kStream\)", cpp)
    _require(len(signatures) == 28 and set(signatures) == set(_SERIALIZERS), "operation serializer definition set changed")
    for cls, (parent, fields) in _SERIALIZERS.items():
        state, bodies = _methods(files, roots, "CvAIOperation.cpp", cls)
        read, write = bodies["original"]
        _require(_operands(read, ">>") == _operands(write, "<<") == ["uiVersion", *fields]
                 and "uint uiVersion = 1;" in write, "operation payload changed: " + cls)
        for method, value in (("Read", read), ("Write", write)):
            calls = re.findall(r"\b(CvAI\w+)::" + method + r"\(kStream\);", value)
            _require(calls == ([parent] if parent else []), "operation parent serializer changed: " + cls)
            if parent:
                _ordered(value, [parent + "::" + method + "(kStream);", "kStream " + (">>" if method == "Read" else "<<") + " uiVersion;"])
        state.update(latest_writer_version=1, parent_serializer=parent)
        states.append(state)
    slots, slot_bodies = _pair(files, roots, _CORE + "CvAIOperation.cpp",
        ("FDataStream& operator>>(FDataStream& loadFrom, OperationSlot& writeTo)",
         "FDataStream& operator<<(FDataStream& saveTo, const OperationSlot& readFrom)"), "OperationSlot")
    fields = ["m_iOperationID", "m_iArmyID", "m_iSlotID"]
    _require(_operands(slot_bodies["original"][0], ">>") == ["writeTo." + name for name in fields] and
             _operands(slot_bodies["original"][1], "<<") == ["readFrom." + name for name in fields], "operation slot wire changed")
    return dict(factory_witnesses=factories, declarations=declarations, factory_types=rows, serializers=states,
                slots=slots, identical_factory_and_serializer_blocks=29, base_minimum_bytes=69,
                minimum_body_bytes=73, minimum_record_bytes=81,
                abort_reason_is_not_serialized=True, slot_bytes=12)


def _army(files, roots):
    row, bodies = _methods(files, roots, "CvArmyAI.cpp", "CvArmyAI", "read", "write", False)
    original_read, original_write = bodies["original"]
    current_read, current_write = bodies["current"]
    prefix = ("\t// Validate every selected count before output; match the original reader width.\n"
              "\tconst int iNumFormationEntries = CvChecked::Integer<int>(m_FormationEntries.size());\n\n")
    expected = original_write.replace("{\n", "{\n" + prefix, 1)
    expected = expected.replace("kStream << (int)m_FormationEntries.size();", "kStream << iNumFormationEntries;", 1)
    expected = expected.replace("for(uint ui = 0; ui < m_FormationEntries.size(); ui++)", "for(int ui = 0; ui < iNumFormationEntries; ui++)", 1)
    _require(current_read == original_read and expected == current_write, "ArmyAI has an unclassified count change")
    fields = ["m_iID", "m_eOwner", "m_iCurrentX", "m_iCurrentY", "m_iGoalX", "m_iGoalY",
              "m_eDomainType", "m_iFormationIndex", "m_eAIState", "m_iOperationID"]
    _require("uint uiVersion = 1;" in original_write and
             _operands(original_read, ">>") == ["uiVersion", *fields, "iEntriesToRead", "slot"] and
             _operands(original_write, "<<") == ["uiVersion", *fields, "(int)m_FormationEntries.size()", "m_FormationEntries[ui]"],
             "ArmyAI field order changed")
    slots, slot_bodies = _pair(files, roots, _CORE + "CvArmyAI.cpp",
        ("FDataStream& operator>>(FDataStream& loadFrom, CvArmyFormationSlot& writeTo)",
         "FDataStream& operator<<(FDataStream& saveTo, const CvArmyFormationSlot& readFrom)"), "CvArmyFormationSlot")
    members = ["m_iUnitID", "m_iEstimatedTurnAtCheckpoint", "m_bStartedOnOperation"]
    _require(_operands(slot_bodies["original"][0], ">>") == ["writeTo." + name for name in members] and
             _operands(slot_bodies["original"][1], "<<") == ["readFrom." + name for name in members], "Army slot order changed")
    dispatch, dispatch_bodies = _pair(files, roots, _CORE + "CvArmyAI.cpp",
        ("FDataStream& operator>>(FDataStream& loadFrom, CvArmyAI& writeTo)",
         "FDataStream& operator<<(FDataStream& saveTo, const CvArmyAI& readFrom)"), "Army free-list dispatch")
    _require("writeTo.read(loadFrom);" in dispatch_bodies["original"][0] and
             "readFrom.write(saveTo);" in dispatch_bodies["original"][1], "Army pool dispatch changed")
    for root in roots.values():
        header = _text(files, root / _CORE / "CvArmyAI.h")
        for name in members + ["m_eDomainType", "m_eAIState"]:
            _require("int " + name + ";" in header, "Army raw int declaration changed")
        _require("PlayerTypes m_eOwner;" in header, "Army owner type changed")
    row.update(latest_writer_version=1, minimum_bytes=48, slot_bytes=12, slot_started_member_type="int32",
        current_difference="exact checked int32 count preflight and counted-loop replay", slots=slots, dispatch=dispatch)
    return row


def _player(files, roots):
    row, bodies = _methods(files, roots, "CvPlayer.cpp", "CvPlayer", equal=False)
    old_read, old_write = bodies["original"]
    new_read, new_write = bodies["current"]
    scope = "    ZeroSisLuaBorrowed::SuspensionScope borrowedState(this);\n"
    _require(new_read.count(scope) == 1 and scope not in old_read and new_read.replace(scope, "", 1) == old_read,
             "Player reader differs beyond SuspensionScope")
    count = "uint iSize = m_AIOperations.size();"
    _require(old_write.count(count) == 1 and old_write.replace(count,
        "uint iSize = CvChecked::Integer<unsigned int>(m_AIOperations.size());", 1) == new_write,
        "Player writer differs beyond operation count narrowing")
    for kind, root in roots.items():
        source = _text(files, root / _CORE / "CvPlayer.cpp")
        header = _text(files, root / _CORE / "CvPlayer.h")
        _require("const int g_CurrentCvPlayerVersion = 16;" in source, "Player version changed")
        for token in ("typedef std::map<unsigned int, int> TurnData;", "std::vector<CvString> m_ReplayDataSets;",
            "std::vector< TurnData > m_ReplayDataSetValues;", "std::vector< std::pair<int, PlayerVoteTypes> > m_aVote;",
            "std::vector< std::pair<UnitClassTypes, int> > m_aUnitExtraCosts;", "CvPlotsVector m_aiPlots;",
            "FAutoVariable<int, CvPlayer> m_iPopRushHurryCount;", "FAutoVariable<int, CvPlayer> m_iTotalImprovementsBuilt;",
            "ConqueredByBoolField m_bfEverConqueredBy;", "CvString m_strEmbarkedGraphicOverride;",
            "CvPlayerAchievements m_kPlayerAchievements;", "FFreeListTrashArray<CvArmyAI> m_armyAIs;"):
            _require(token in header, "Player suffix member type changed: " + token)
        for direction, body in zip((">>", "<<"), bodies[kind]):
            _ordered(body, ["kStream " + direction + " m_units;", "kStream " + direction + " m_armyAIs;",
                "kStream " + direction + " iSize;", *["kStream " + direction + " " + field + ";" for field in _TAIL],
                "kStream " + direction + " m_aiPlots[i];", "kStream " + direction + " m_iPopRushHurryCount;",
                "kStream " + direction + " m_iTotalImprovementsBuilt;", "kStream " + direction + " bValue;",
                "kStream " + direction + " m_strEmbarkedGraphicOverride;",
                "m_kPlayerAchievements." + ("Read" if direction == ">>" else "Write") + "(kStream);"])
        defines = _text(files, root / "CvGameCoreDLLUtil/include/CvDLLUtilDefines.h")
        _require(re.search(r"#define\s+MAX_CIV_PLAYERS\s+\(63\)", defines) and
                 re.search(r"#define\s+MAX_PLAYERS\s+\(MAX_CIV_PLAYERS \+ 1\)", defines), "64 Player profile changed")
    _ordered(old_read, ["kStream >> iID;", "kStream >> iOperationType;", "CvAIOperation::CreateOperation((AIOperationTypes)iOperationType, m_eID);",
        "pThisOperation->Read(kStream);", "m_AIOperations.insert(std::make_pair(pThisOperation->GetID(), pThisOperation));",
        "if (uiVersion <= 10)", "// Unused popup queue", "kStream >> m_ReplayDataSets;"])
    _ordered(old_write, ["uint iSize = m_AIOperations.size();", "kStream << iSize;", "kStream << it->first;",
        "kStream << pThisOperation->GetOperationType();", "pThisOperation->Write(kStream);", "kStream << m_ReplayDataSets;"])
    _ordered(old_write, ["int iSize = -1;", "for(int i = m_aiPlots.size() - 1; i >= 0; i--)", "if(m_aiPlots[i] != -1)",
        "iSize = i + 1;", "if(iSize < 0)", "iSize = 0;", "kStream << iSize;", "kStream << m_aiPlots[i];",
        "int iSize = MAX_PLAYERS;", "bool bValue = m_bfEverConqueredBy.GetBit(i);", "kStream << bValue;"])
    _require(old_write.rstrip().endswith("m_kPlayerAchievements.Write(kStream);\n}"), "base Player writer final field changed")
    row.update(latest_writer_version=16, known_differences=["one reader SuspensionScope line", "checked uint32 operation count"],
        end_fields=_TAIL + ["m_aiPlots", "m_iPopRushHurryCount", "m_iTotalImprovementsBuilt", "m_bfEverConqueredBy",
                           "m_strEmbarkedGraphicOverride", "m_kPlayerAchievements"],
        legacy_popup_count="reader-only uiVersion <= 10; excluded by the current-v16 writer profile",
        operation_outer_key="read and discarded; insertion uses the object's serialized ID", conquest_flags=64)
    return row


def _codecs(files, roots):
    specs = [
        ("sequence", "FirePlace/include/FireWorks/FStlContainerSerialization.h",
         "void SerializeToSequenceContainer(FDataStream & loadFrom, ContainerType & container)",
         "SerializeFromSequenceContainer(FDataStream & saveTo, const ContainerType & container)"),
        ("associative", "FirePlace/include/FireWorks/FStlContainerSerialization.h",
         "void SerializeToAssociativeContainer(FDataStream & loadFrom, ContainerType & container)",
         "SerializeFromAssociativeContainer(FDataStream & saveTo, ContainerType & container)"),
        ("pair", "FirePlace/include/FireWorks/FStlContainerSerialization.h",
         "FDataStream & operator>>(FDataStream & loadFrom, std::pair<FirstType, SecondType> & writeTo)",
         "FDataStream & operator<<(FDataStream & saveTo, const std::pair<FirstType, SecondType> & readFrom)"),
        ("auto_scalar", "FirePlace/include/FireWorks/FAutoVariable.h",
         "void FAutoVariable<ObjectType, ContainerType>::load(FDataStream & loadFrom)",
         "void FAutoVariable<ObjectType, ContainerType>::save(FDataStream & saveTo) const")]
    rows = []
    for name, relative, rs, ws in specs:
        row, bodies = _pair(files, roots, relative, (rs, ws), name, equal=name == "pair")
        for kind, (read, write) in bodies.items():
            if name in {"sequence", "associative"}:
                if kind == "original":
                    _require(("ContainerType::size_type count = 0;" if name == "sequence" else "size_t count = 0;") in read and
                        ("m_saveTo << container.size();" if name == "sequence" else "size_t count = container.size();") in write,
                        "original STL count type changed")
                else:
                    _require("unsigned int count = 0;" in read and
                        "CvChecked::Integer<unsigned int>(container.size())" in write, "checked uint32 STL count changed")
            elif name == "pair":
                _require(_operands(read, ">>") == ["writeTo.first", "writeTo.second"] and
                         _operands(write, "<<") == ["readFrom.first", "readFrom.second"], "STL pair framing changed")
            else:
                _require("saveTo << m_value;" in write and "loadFrom >> m_value;" in read, "automatic scalar framing changed")
        rows.append(row)
    for enum in ("AIOperationState", "AIOperationMovementType"):
        row, bodies = _pair(files, roots, _CORE + "CvAIOperation.cpp",
            (f"FDataStream& operator>>(FDataStream& loadFrom, {enum}& writeTo)",
             f"FDataStream& operator<<(FDataStream& saveTo, const {enum}& readFrom)"), enum)
        _require("static_cast<int>(readFrom)" in bodies["original"][1], "operation enum writer changed")
        rows.append(row)
    enums = _text(files, files.project / "Source/Providers/Serialization/SdkEnumTypes.inc")
    provider = _text(files, files.project / "Source/Providers/Serialization/SdkEnumSerialization.cpp")
    for name in ("PlayerTypes", "PlayerVoteTypes", "UnitClassTypes", "UnitAITypes"):
        _require("SDK_ENUM(" + name + ")" in enums and "SDK_ENUM_BYTE(" + name + ")" not in enums,
                 "Player suffix enum provider width changed")
    _require("INT32 bits; memcpy(&bits,&value,sizeof(bits)); stream << bits;" in provider,
             "raw enum provider changed")
    return rows


def _wire_calls(body):
    body = re.sub(r"//[^\n]*|/\*.*?\*/", "", body, flags=re.S)
    return [name + "(" + re.sub(r"\s+", "", arguments) + ")" for name, arguments in
            re.findall(r"\binput\.(Version|I32|Fixed|SignedCount|Count|String|Bool)\(([^()]*)\)", body)]


def _parsers(files, source_operations):
    headers = [files.artifact(files.project / "Source/Host" / name) for name in
        ("RetailSavePlayerEndFields.h", "RetailSavePlayerOperations.h", "RetailSavePlayerEnd.h", "RetailSavePlayer.h")]
    host = files.project / "Source/Host"
    expected = {
        ("RetailSavePlayerEndFields.h", "inline RetailSaveArmyAIInspection ReadArmyAI(Reader& input)"):
            ["Version(1)", "I32()", "I32()", "Fixed(8,4)", "SignedCount(ArmyFormationSlotBytes)", "Fixed(result.slotCount,ArmyFormationSlotBytes)"],
        ("RetailSavePlayerEndFields.h", "inline RetailSavePlayerEndFieldsInspection ReadPlayerFieldsAfterOperations("):
            ["Count(4)", "String()", "Count(4)", "Count(8)", "Fixed(turns,8)", "Count(8)", "Fixed(result.voteCount,8)",
             "Count(8)", "Fixed(result.unitCostCount,8)", "SignedCount(4)", "Fixed(result.plotCount,4)", "I32()", "I32()",
             "SignedCount(1)", "Bool()", "String()", "Version(1)", "Fixed(2,4)"],
        ("RetailSavePlayerOperations.h", "inline std::int32_t ReadPlayerOperationBase(Reader& input)"):
            ["Version(1)", "I32()", "Fixed(4,4)", "Bool()", "Fixed(8,4)", "Count(4)", "Fixed(armies,4)",
             "Count(12)", "Fixed(needed,12)", "Count(12)", "Fixed(committed,12)"],
    }
    methods = []
    for (header, signature), calls in expected.items():
        meta, body = files.body(host / header, signature)
        _require(_wire_calls(body) == calls, "portable suffix parser wire changed: " + signature)
        methods.append(meta)
    dm, derived = files.body(host / "RetailSavePlayerOperations.h", "inline void ReadPlayerOperationDerived(Reader& input, std::int32_t type)")
    cases = list(re.finditer(r"case (\d+):", derived))
    _require(sorted(int(m[1]) for m in cases) == list(range(20)), "portable operation case coverage changed")
    for case in cases:
        operation_type = int(case[1])
        section = derived[case.end():derived.index("return;", case.end())]
        calls = _wire_calls(section)
        chain = source_operations["factory_types"][operation_type]["serializer_chain"]
        _require(chain[0] == "CvAIOperation", "operation chain lost its base serializer")
        expected_calls = []
        for cls in chain[1:]:
            expected_calls.append("Version(1)")
            expected_calls.extend("Bool()" if field in {"m_bCivilianRescue", "m_bEscorted"} else "I32()"
                                  for field in _SERIALIZERS[cls][1])
        _require(calls == expected_calls, "portable operation inheritance framing changed")
    methods.append(dm)
    om, operations = files.body(host / "RetailSavePlayerOperations.h", "inline RetailSavePlayerOperationsInspection ReadPlayerOperations(Reader& input,")
    _ordered(operations, ["ValidatePlayerOperationsProfile(input, profile);", "input.Count(PlayerOperationMinimumRecordBytes)",
        "i < result.declaredCount", "input.I32(), type = input.I32()", "type < 0 || type >= 20",
        "ReadPlayerOperationBase(input)", "ReadPlayerOperationDerived(input, type)", "mapKey != bodyId"])
    methods.append(om)
    em, end = files.body(host / "RetailSavePlayerEnd.h", "inline RetailSavePlayerEndInspection ReadPlayerEnd(Reader& input,")
    _ordered(end, ["RetailPlayerOperationsProfile::BnwCurrentFactory20", "RetailPlayerEndWriterProfile::Current16With64Players",
        "ReadFreeListHeader(input)", "i < result.armyPool.liveCount", "ReadArmyAI(input)",
        "ReadPlayerOperations(input, profile.operationProfile)", "ReadPlayerFieldsAfterOperations(input, profile.fieldProfile)",
        "input.Version(1);", "result.playerAITrailer = input.SpanFrom(trailer);"])
    methods.append(em)
    composite = _text(files, host / "RetailSavePlayer.h")
    stages = re.findall(r"result\.(\w+) = RetailSave\w+::InspectAt\(data, size, cursor,", composite)
    _require(stages == ["prefix", "middle", "late", "postTraits", "cities", "units", "ending"], "Player assembly order changed")
    for stage in stages:
        _require(composite.count(f"advance(result.{stage}.nextInflatedOffset, result.{stage}.arrayRecords);") == 1,
                 "Player shared budget accounting changed")
    _ordered(composite, ["next < cursor || next > size", "records > remaining.maxTotalRecords",
        "remaining.maxTotalRecords -= records;", "result.arrayRecords += records;", "result.completePlayerWireFramed = true;"])
    fields = _text(files, host / "RetailSavePlayerEndFields.h")
    _require("result.everCount != 64u" in fields and
        "profile != RetailPlayerEndWriterProfile::Current16With64Players" in fields, "Player suffix profile guard changed")
    for row in headers:
        text = _text(files, Path(row["path"]))
        _require(not re.search(r"\b(?:completePlayerVerified|completeSaveVerified|rulesetCompatibilityVerified|restoreApproved)\s*=\s*true", text),
                 "wire parser promotes an unsupported semantic claim")
    return dict(headers=headers, methods=methods, operation_types_checked=20,
                assembled_stages=stages, shared_record_budget=True, semantic_flags_remain_false=True)


def inspect(project: Path) -> dict:
    """Return deterministic source contracts and a flat three-field input ledger."""
    files = _Sources(project)
    for name in ("inspect_player_end_sources.py", "inspect_player_post_traits_sources.py",
                 "publish_retail_team_stage.py", "verify_retail_save_header.py"):
        files.artifact(files.project / "tools" / name)
    roots = {"original": files.project / "Source/SDK_BNW_Original", "current": files.project / "Source/SDK_BNW_x64"}
    army = _army(files, roots)
    operations = _operations(files, roots)
    player = _player(files, roots)
    codecs = _codecs(files, roots)
    achievements, achievement_bodies = _methods(files, roots, "CvAchievementUnlocker.cpp", "CvPlayerAchievements")
    _require("int iVersion = 1;" in achievement_bodies["original"][1] and achievements["original_write_operands"] ==
        ["iVersion", "m_iAchievement_XP1_32_Progress", "m_iAchievement_XP1_33_Progress"], "achievement payload changed")
    ai, ai_bodies = _methods(files, roots, "CvPlayerAI.cpp", "CvPlayerAI")
    dll, dll_bodies = _methods(files, roots, "CvDllPlayer.cpp", "CvDllPlayer")
    for root in roots.values():
        _require("CvPlayerAI* m_pPlayer;" in _text(files, root / _CORE / "CvDllPlayer.h") and
            "class CvPlayerAI : public CvPlayer" in _text(files, root / _CORE / "CvPlayerAI.h"), "Player forwarding type changed")
        files.artifact(root / _CORE / "CvAchievementUnlocker.h")
    for method, direction, body in (("Read", ">>", ai_bodies["original"][0]), ("Write", "<<", ai_bodies["original"][1])):
        _ordered(body, ["CvPlayer::" + method + "(kStream);", "kStream " + direction + " uiVersion;"])
        _require(_operands(body, direction) == ["uiVersion"], "PlayerAI trailer acquired another operand")
    _require("uint uiVersion = 1;" in ai_bodies["original"][1] and
        "m_pPlayer->Read(kStream);" in dll_bodies["original"][0] and
        "m_pPlayer->Write(kStream);" in dll_bodies["original"][1], "PlayerAI or DLL forwarding changed")
    parsers = _parsers(files, operations)
    files.finish()
    return dict(schema="zerosis.retail.player_end_source_conformance.v1", status="SOURCE_ORDER_AND_WIRE_CONFORMANCE_RECORDED",
        scope="Copied original/current source comparison and portable parser source inspection only",
        army=army, operations=operations, player=player, achievements=achievements,
        player_ai=ai, dll_player_forwarding=dll, codecs=codecs, parsers=parsers,
        wire=dict(player_version=16, player_ai_trailer_version=1, player_ai_trailer_bytes=4,
            army_version=1, army_minimum_bytes=48, army_slot_bytes=12, operation_types=20,
            operation_base_minimum_bytes=69, operation_minimum_record_bytes=81,
            stl_counts="original Win32 size_t/size_type four-byte counts; current checked uint32",
            replay_turn_pair_bytes=8, vote_pair_bytes=8, unit_cost_pair_bytes=8,
            plot_count="signed int32; trailing -1 map suffix omitted", ever_conquered_count=64,
            ever_conquered_bool_bytes=1, achievement_bytes=12,
            player_fields_after_operations_minimum_bytes=112, player_end_minimum_bytes=144),
        evidence_counts=dict(identical_operation_factory_and_serializer_blocks=29, factory_types=20,
                             operation_serializer_classes=14, portable_parser_headers=4),
        limits=["The copied SDK does not supply an original top-level retail whole-save loop",
            "Source identity and declared wire framing are not execution of the original serializers",
            "No private .zssave section is used as retail save evidence",
            "No installed game, MODS, My Games, user save, native Host, GameCore or game process is accessed or executed",
            "No semantic Player verification, full save compatibility, ruleset identity, object references or restore approval"],
        inputs=list(files.rows.values()))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output", type=Path)
    arguments = parser.parse_args()
    result = inspect(arguments.project)
    if arguments.output is not None:
        output = arguments.output.absolute()
        _require(output.is_relative_to(arguments.project.absolute()) and ".." not in output.parts and
                 output.resolve().is_relative_to(arguments.project.resolve()),
                 "source conformance output escaped the project")
        _require(str(output).casefold() not in {row["path"].casefold() for row in result["inputs"]},
                 "source conformance output would overwrite an input")
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(dict(status=result["status"], input_artifacts=len(result["inputs"]),
        operation_types=result["wire"]["operation_types"], output=str(arguments.output) if arguments.output else None)))


if __name__ == "__main__":
    main()
