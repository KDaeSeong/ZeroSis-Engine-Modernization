"""Read finite copied SDK and retained component witnesses for Unit framing.

Import and inspect write no files, start no processes, and load no native code.
The original archive's component exchange is not a whole-game save proof.
"""
from __future__ import annotations

from pathlib import Path
import re
import struct

from inspect_player_post_traits_sources import _Sources, _ordered, _operands, _require


_ARCHIVE_CONFORMANCE_SHA = "d27cd2ca797f9a9877c3fea64f11fc0490714ae3646e92500ea9628dc42f5ba1"
_ARCHIVE_BUILD_SHA = "7d3d6109bf673b2b8ccf8bd19af150202c99e8b79adef596310916dda5dce544"
_RAW_TYPES = {"int", "PlayerTypes", "UnitTypes", "DirectionTypes", "TacticalAIMoveTypes",
              "InvisibleTypes", "GreatPeopleDirectiveTypes", "MissionAITypes", "ActivityTypes",
              "AutomateTypes", "UnitAITypes"}
_GROUPS = [("raw32", 14), ("bool", 1), ("raw32", 10), ("bool", 1),
           ("raw32", 88), ("bool", 9), ("raw32", 6), ("string", 2),
           ("int_vector", 10), ("raw32", 6)]
_TAIL_INTS = ("m_iEmbarkedAllWaterCount", "m_iEmbarkExtraVisibility", "m_iEmbarkDefensiveModifier",
    "m_iCapitalDefenseModifier", "m_iCapitalDefenseFalloff", "m_iCityAttackPlunderModifier",
    "m_iReligiousStrengthLossRivalTerritory", "m_iTradeMissionInfluenceModifier",
    "m_iTradeMissionGoldModifier", "m_iEnemyDamageChance", "m_iNeutralDamageChance",
    "m_iEnemyDamage", "m_iNeutralDamage", "m_iNearbyEnemyCombatMod", "m_iNearbyEnemyCombatRange",
    "m_iHealOnPillageCount", "m_iFlankAttackModifier", "m_iGoldenAgeValueFromKills",
    "m_iGreatGeneralReceivesMovementCount", "m_iGreatGeneralCombatModifier",
    "m_iIgnoreGreatGeneralBenefit", "m_iIgnoreZOC", "m_iSapperCount", "m_iCanHeavyCharge",
    "m_iNumExoticGoods", "m_iCityAttackOnlyCount", "m_iCaptureDefeatedEnemyCount", "m_iGreatAdmiralCount")


def _text(files, path):
    files.artifact(path)
    return path.read_text(encoding="latin1").replace("\r\n", "\n")


def _pair(files, roots, relative, signatures, name, suspension=False):
    witnesses, bodies = [], {}
    for kind, root in roots.items():
        read_meta, read = files.body(root / relative, signatures[0])
        write_meta, write = files.body(root / relative, signatures[1])
        witnesses.append(dict(kind=kind, read=read_meta, write=write_meta))
        bodies[kind] = read, write
    normalized = bodies["current"][0]
    if suspension:
        line = "    ZeroSisLuaBorrowed::SuspensionScope borrowedState(this);\n"
        _require(normalized.count(line) == 1 and line not in bodies["original"][0],
                 "Unit suspension declaration changed")
        normalized = normalized.replace(line, "", 1)
    _require(normalized == bodies["original"][0] and
             bodies["current"][1] == bodies["original"][1], "unclassified Unit serializer change: " + name)
    return dict(name=name, witnesses=witnesses,
        reader_normalization="remove exactly one Unit::read SuspensionScope line" if suspension else "none",
        original_read_operands=_operands(bodies["original"][0], ">>"),
        original_write_operands=_operands(bodies["original"][1], "<<")), bodies


def _archive_exchange(files):
    proof = files.json("evidence/auto_archive/conformance.json", _ARCHIVE_CONFORMANCE_SHA)
    build = files.json("evidence/auto_archive/build_result.json", _ARCHIVE_BUILD_SHA)
    _require(proof["status"] == "SDK_AUTO_ARCHIVE_CONFORMANCE_PASS" and proof["failures"] == [] and
        proof["scope"] == "FINAL_RELEASE_ACTUAL_SDK_ARCHIVE_AND_TEMPLATE_COMPONENTS_NOT_GAME_SYNCHRONIZATION" and
        proof["game_launched"] is False and proof["full_save_compatibility_verified"] is False and
        proof["trace_model_matches"] == 6 and proof["exchange_wire_matches"] == 12 and
        proof["cross_architecture_payload_reads"] == 24, "retained archive proof scope changed")
    _require(build["status"] == "AUTO_ARCHIVE_PROVIDERS_BUILT" and build["game_launched"] is False,
             "retained archive build changed")
    files.pin(proof["build"])
    disassembly = files.pin(proof["sdk_disassembly"])
    disassembly_text = _text(files, Path(disassembly["path"]))
    # This retained disassembly contains remove/delta routines, not the full
    # save/load body. The map and actual exchange below are separate witnesses.
    _require("?saveDelta@FAutoArchive@@" in disassembly_text and
             "?remove@FAutoArchive@@" in disassembly_text and
             "?save@FAutoArchive@@" not in disassembly_text and
             "?load@FAutoArchive@@" not in disassembly_text, "retained disassembly selection changed")
    source_artifacts = [files.pin(row) for row in build["sources"]
                        if Path(row["path"]).name in {"SdkAutoArchive.cpp", "SdkAutoArchiveIncludes.h",
                            "SdkAutoVariable.cpp", "sdk_auto_archive_trace.cpp"}]
    _require(len(source_artifacts) == 4, "archive source identity set changed")
    libraries = [files.pin(row) for row in build["x86"]["libraries"]]
    _require({Path(row["path"]).name for row in libraries} ==
             {"FireWorksWin32.lib", "CvGameCoreDLLUtilWin32.lib"}, "original archive libraries changed")
    original_map = files.pin(build["x86"]["map"])
    map_text = _text(files, Path(original_map["path"]))
    map_lines = []
    for symbol in ("?add@FAutoArchive@@", "?save@FAutoArchive@@", "?load@FAutoArchive@@"):
        matches = [line.strip() for line in map_text.splitlines()
                   if symbol in line and "FireWorksWin32:FAutoArchive.obj" in line]
        _require(len(matches) == 1, "original archive map provider is ambiguous")
        map_lines.extend(matches)
    outputs = {str(Path(row["path"])): row for row in proof["outputs"]}
    exchanges = []
    for endian in (0, 1, 2):
        pair = []
        expected = struct.pack(("<" if endian == 1 else ">") + "7i", *(10 + i * 101 for i in range(7)))
        for arch in ("x86", "x64"):
            path = files.project / f"evidence/auto_archive/exchange_{arch}_e{endian}/full.bin"
            row = files.pin(outputs[str(path)])
            payload = path.read_bytes()
            _require(payload == expected and len(payload) == 28, "archive full scalar exchange changed")
            pair.append(row)
        exchanges.append(dict(endian=endian, artifacts=pair, bytes=28, ordered_raw_ints=7,
                              count_or_name_or_index_header_bytes=0))
    exchange_runs = [row for row in proof["runs"] if row.get("mode") == "exchange"]
    _require(len(exchange_runs) == 12 and all(row["returncode"] == 0 for row in exchange_runs),
             "retained cross-architecture reads changed")
    for row in exchange_runs:
        files.pin(row["log"])
    harness = _text(files, files.project / "Tests/sdk_auto_archive_trace.cpp")
    _ordered(harness, ["struct Seven", "Variable(name,archive,static_cast<int>(10+i*101))",
        "static void exchange", "owner.archive.save(full)", "owner.archive.load(full)", "require(full.AtEnd())"])
    return dict(conformance=files.artifact(files.project / "evidence/auto_archive/conformance.json"),
        build=files.artifact(files.project / "evidence/auto_archive/build_result.json"),
        original_libraries=libraries, original_map=original_map, map_provider_lines=map_lines,
        inspected_provider_and_harness_sources=source_artifacts, retained_disassembly=disassembly,
        retained_disassembly_scope="selected remove/delta bodies; full save/load bodies are not in this text",
        full_scalar_exchanges=exchanges, cross_architecture_payload_reads=24,
        operations_per_architecture_per_endian=proof["operations_per_architecture_per_endian"],
        scope="Retained FINAL_RELEASE archive/template component exchanges, not CvUnit or whole-save execution",
        partial_load_behavior=proof["partial_load_behavior"])


def inspect(project: Path) -> dict:
    """Return compact source contracts with a flat, complete input-artifact list."""
    files = _Sources(project)
    project = files.project
    for name in ("inspect_unit_object_sources.py", "inspect_player_post_traits_sources.py",
                 "publish_retail_team_stage.py", "verify_retail_save_header.py"):
        files.artifact(project / "tools" / name)
    parser_headers = [files.artifact(project / "Source/Host" / name) for name in
        ("RetailSavePlayerUnits.h", "RetailSaveUnit.h", "RetailSaveUnitArchive.h",
         "RetailSaveUnitServices.h", "RetailSaveFreeList.h", "RetailSaveStateWire.h")]
    roots = {"original": project / "Source/SDK_BNW_Original", "current": project / "Source/SDK_BNW_x64"}
    core = "CvGameCoreDLL_Expansion2/"
    unit, unit_bodies = _pair(files, roots, core + "CvUnit.cpp",
        ("void CvUnit::read(FDataStream& kStream)", "void CvUnit::write(FDataStream& kStream) const"), "unit", True)
    _require("uint uiVersion = 9;" in unit_bodies["original"][1], "Unit latest version changed")
    unit["latest_writer_version"] = 9
    unit["legacy_reader_predicates"] = re.findall(r"if\s*\(\s*(uiVersion\s*(?:>=|>|==)\s*\d+)\s*\)",
                                                   unit_bodies["original"][0])
    states = [unit]
    for name, cpp, cls, read_name, write_name, version, minimum in (
        ("promotions", "CvPromotionClasses.cpp", "CvUnitPromotions", "Read", "Write", 1, 12),
        ("promotion_array", "CvPromotionClasses.cpp", "PromotionArrayHelpers", "Read", "Write", None, 4),
        ("religion", "CvReligionClasses.cpp", "CvUnitReligion", None, None, 2, 16)):
        if name == "religion":
            signatures = ("FDataStream& operator>>(FDataStream& loadFrom, CvUnitReligion& writeTo)",
                          "FDataStream& operator<<(FDataStream& saveTo, const CvUnitReligion& readFrom)")
        elif name == "promotion_array":
            signatures = ("void PromotionArrayHelpers::Read(FDataStream& kStream, CvBitfield& kPromotions)",
                "void PromotionArrayHelpers::Write(FDataStream& kStream, const CvBitfield& kPromotions, int iArraySize)")
        else:
            signatures = (f"void {cls}::{read_name}(FDataStream& kStream)",
                          f"void {cls}::{write_name}(FDataStream& kStream) const")
        row, bodies = _pair(files, roots, core + cpp, signatures, name)
        if version is not None:
            _require(f"uint uiVersion = {version};" in bodies["original"][1], "Unit nested version changed")
        row.update(latest_writer_version=version, minimum_bytes=minimum)
        if name == "promotion_array":
            _ordered(bodies["original"][1], ["int iCount = 0;", "++iCount;", "kStream << iCount;",
                                             "kStream << uiHash;", "kStream << bValue;"])
            _require("kStream >> iNumEntries;" in bodies["original"][0] and
                     bodies["original"][0].count("kStream >> b") == 3, "promotion bool branches changed")
        states.append(row)
        for root in roots.values():
            files.artifact(root / core / cpp.replace(".cpp", ".h"))

    declarations, constructors, pools = [], [], []
    previous_declarations = None
    for kind, root in roots.items():
        header = _text(files, root / core / "CvUnit.h")
        matches = list(re.finditer(r"FAutoVariable<(.+?),\s*CvUnit>\s+(\w+)\s*;", header))
        fields = []
        for match in matches:
            type_name, name = " ".join(match[1].split()), match[2]
            category = ("raw32" if type_name in _RAW_TYPES else
                        {"bool": "bool", "CvString": "string", "std::vector<int>": "int_vector"}.get(type_name))
            _require(category is not None, "unclassified automatic Unit member type")
            fields.append(dict(name=name, type=type_name, codec=category,
                               line=header[:match.start()].count("\n") + 1))
        identity = [(row["name"], row["type"]) for row in fields]
        _require(len(fields) == 147 and (previous_declarations is None or identity == previous_declarations),
                 "automatic Unit declarations changed")
        previous_declarations = identity
        _require(not re.search(r"(?m)^\s*#", header[matches[0].start():matches[-1].end()]),
                 "conditional archive declaration needs a profile")
        expected_categories = [category for category, count in _GROUPS for _ in range(count)]
        _require([row["codec"] for row in fields] == expected_categories and
            [row["name"] for row in fields[:6]] == ["m_eOwner", "m_eOriginalOwner", "m_eUnitType", "m_iX", "m_iY", "m_iID"],
            "automatic Unit declaration-order groups changed")
        ctor_meta, ctor = files.body(root / core / "CvUnit.cpp", "CvUnit::CvUnit() :")
        registered = re.findall(r'\b(m_\w+)\s*\(\s*"[^"\n]+"\s*,\s*m_syncArchive\b', ctor)
        _require(len(registered) == 147 and set(registered) == {row["name"] for row in fields},
                 "Unit constructor registration membership changed")
        _require(not re.search(r"(?m)^\s*#", ctor), "conditional Unit registration needs a profile")
        if constructors:
            _require(ctor_meta["body_sha256"] == constructors[0]["body"]["body_sha256"], "Unit constructor changed")
        constructors.append(dict(kind=kind, body=ctor_meta, registered_members=147,
                                 initializer_list_is_not_registration_order=True))
        declarations.append(dict(kind=kind, source=files.artifact(root / core / "CvUnit.h"), fields=fields))
        _require("std::vector<int> m_extraDomainModifiers;" in header and
                 "typedef MissionData MissionQueueNode;" in header and
                 "typedef FFastSmallFixedList< MissionQueueNode, 12, true, c_eCiv5GameplayDLL > MissionQueue;" in header,
                 "Unit explicit container type changed")
        read, write = unit_bodies[kind]
        for direction, body in ((">>", read), ("<<", write)):
            _ordered(body, ["kStream " + direction + " m_syncArchive;", "kStream " + direction + " m_iLastMoveTurn;",
                "m_Promotions." + ("Read" if direction == ">>" else "Write") + "(kStream);",
                *["kStream " + direction + " " + value + ";" for value in
                    ("m_combatUnit.eOwner", "m_combatUnit.iID", "m_transportUnit.eOwner", "m_transportUnit.iID",
                     "m_missionAIUnit.eOwner", "m_missionAIUnit.iID", "m_extraDomainModifiers",
                     "m_iEverSelectedCount", "m_iMapLayer", "m_iNumGoodyHutsPopped", "m_bIgnoreDangerWakeup", *_TAIL_INTS,
                     "m_strName", "m_iScenarioData", "*m_pReligion")]])
        _ordered(write, ["if (m_eGreatWork != NO_GREAT_WORK)", "db && db->Execute(kQuery,",
            "if(kQuery.Step())", "kStream << FString::Hash(kQuery.GetText(0));", "kStream << (uint)0;",
            "kStream << m_iTourismBlastStrength;", "kStream << m_missionQueue.getLength();",
            "kStream << pNode->eMissionType;", "kStream << pNode->iData1;", "kStream << pNode->iData2;",
            "kStream << pNode->iFlags;", "kStream << pNode->iPushTurn;"])
        _ordered(read, ["uint uiGreatWorkType = 0;", "kStream >> uiGreatWorkType;",
            "kStream >> m_iTourismBlastStrength;", "UINT uSize;", "kStream >> uSize;",
            "kStream >> Node.eMissionType;", "kStream >> Node.iData1;", "kStream >> Node.iData2;",
            "kStream >> Node.iFlags;", "kStream >> Node.iPushTurn;"])
        for signature, call in (("FDataStream& operator<<(FDataStream& saveTo, const CvUnit& readFrom)", "readFrom.write(saveTo);"),
                               ("FDataStream& operator>>(FDataStream& loadFrom, CvUnit& writeTo)", "writeTo.read(loadFrom);")):
            _, body = files.body(root / core / "CvUnit.cpp", signature)
            _require(call in body, "free-list Unit dispatch changed")
        player_header = _text(files, root / core / "CvPlayer.h")
        for name, cls in (("m_cities", "CvCityAI"), ("m_units", "CvUnit"), ("m_armyAIs", "CvArmyAI")):
            _require(f"FFreeListTrashArray<{cls}> {name};" in player_header, "Player pool type changed")
        player_witnesses = []
        for signature, direction in (("void CvPlayer::Read(FDataStream& kStream)", ">>"),
                                     ("void CvPlayer::Write(FDataStream& kStream) const", "<<")):
            meta, body = files.body(root / core / "CvPlayer.cpp", signature)
            _ordered(body, [f"kStream {direction} {value};" for value in ("m_cityNames", "m_cities", "m_units", "m_armyAIs")])
            player_witnesses.append(meta)
        pools.append(dict(kind=kind, player=player_witnesses, order=["m_cities", "m_units", "m_armyAIs"]))
        mission = _text(files, root / core / "CvStructs.h")
        _ordered(mission[mission.index("struct MissionData"):], ["MissionTypes eMissionType;", "int iData1;",
                                                               "int iData2;", "int iFlags;", "int iPushTurn;"])
        fast = _text(files, root / "FirePlace/include/FireWorks/FFastVector.h")
        _require(re.search(r"int\s+getLength\(\) const\s*\{\s*return mVec.size\(\);\s*\}", fast),
                 "MissionQueue count return type changed")
        files.artifact(root / "CvGameCoreDLLUtil/include/CvEnumSerialization.h")

    codecs = []
    for name, path, signatures in (
        ("auto_scalar", "FAutoVariable.h", ("void FAutoVariable<ObjectType, ContainerType>::load(FDataStream & loadFrom)",
            "void FAutoVariable<ObjectType, ContainerType>::save(FDataStream & saveTo) const")),
        ("archive_container", "FAutoArchiveClassContainer.h", (
            "FDataStream & operator>>(FDataStream & loadFrom, FAutoArchiveClassContainer<ClassType> & writeTo)",
            "FDataStream & operator<<(FDataStream & saveTo, const FAutoArchiveClassContainer<ClassType> & readFrom)")),
        ("free_list", "FFreeListTrashArray.h", (
            "FDataStream & operator>>(FDataStream & readFrom, FFreeListTrashArray<T> & writeTo)",
            "FDataStream & operator<<(FDataStream & writeTo, const FFreeListTrashArray<T> & readFrom)"))):
        row, bodies = _pair(files, roots, "FirePlace/include/FireWorks/" + path, signatures, name)
        codecs.append(row)
        if name == "free_list":
            _ordered(bodies["original"][1], ["writeTo << readFrom.GetNumSlots();", "writeTo << readFrom.GetLastIndex();",
                "writeTo << readFrom.GetFreeListHead();", "writeTo << readFrom.GetFreeListCount();",
                "writeTo << readFrom.GetCurrentID();", "writeTo << readFrom.GetNextFreeIndex( i );",
                "writeTo << readFrom.GetCount();", "writeTo << entry;"])
    vectors = []
    for kind, root in roots.items():
        path = root / "FirePlace/include/FireWorks/FAutoVector.h"
        rm, rb = files.body(path, "void FAutoVariable<std::vector<ElementType>, ClassContainer>::load(FDataStream & loadFrom)")
        wm, wb = files.body(path, "void FAutoVariable<std::vector<ElementType>, ClassContainer>::save(FDataStream & saveTo) const")
        expected = ("\tclear();\n\tm_commands.clear();\n\tloadFrom >> m_value;\n\tm_commands.clear();" if kind == "original" else
            "    std::vector<ElementType> next;\n    loadFrom >> next;\n"
            "    m_owner.touch(*this); // Preserve successful full-load dirty marking from the SDK clear().\n"
            "    m_value.swap(next);\n    m_commands.clear();")
        _require(rb[rb.index("{\n") + 2:rb.rindex("\n}")] == expected and "saveTo << m_value;" in wb,
                 "unclassified automatic vector storage change")
        sm, sb = files.body(root / "FirePlace/include/FireWorks/FStlContainerSerialization.h",
                            "SerializeFromSequenceContainer(FDataStream & saveTo, const ContainerType & container)")
        lm, lb = files.body(root / "FirePlace/include/FireWorks/FStlContainerSerialization.h",
                            "void SerializeToSequenceContainer(FDataStream & loadFrom, ContainerType & container)")
        _require(("m_saveTo << container.size();" in sb and "ContainerType::size_type count = 0;" in lb) if kind == "original" else
            ("m_saveTo << CvChecked::Integer<unsigned int>(container.size());" in sb and "unsigned int count = 0;" in lb),
            "automatic vector count width changed")
        vectors.append(dict(kind=kind, read=rm, write=wm, sequence_read=lm, sequence_write=sm,
            storage_change="none" if kind == "original" else "exact existing next/swap transactional read body",
            wire="original Windows32 size_type and current checked uint32 count, then int32 values"))
        archive_header = _text(files, root / "FirePlace/include/FireWorks/FAutoArchive.h")
        _require("void load(FDataStream & loadFrom);" in archive_header and
                 "void save(FDataStream & saveTo) const;" in archive_header, "copied archive declarations changed")
        files.artifact(root / "FirePlace/include/FireWorks/FAutoVariableBase.h")
        files.artifact(root / "FirePlace/include/FireWorks/FDataStream.h")
        files.artifact(root / "FirePlace/include/FireWorks/FFreeListArrayBase.h")
    codecs.append(dict(name="automatic_int_vectors", witnesses=vectors))

    provider = project / "Source/Providers/AutoArchive/SdkAutoArchive.cpp"
    provider_methods = []
    for signature, required in (("void FAutoArchive::add(FAutoVariableBase& variable)", "m_contents.push_back(&variable);"),
        ("void FAutoArchive::load(FDataStream& stream)", "for (size_t i = 0; i != m_contents.size(); ++i) m_contents[i]->load(stream);"),
        ("void FAutoArchive::save(FDataStream& stream) const", "for (size_t i = 0; i != m_contents.size(); ++i) m_contents[i]->save(stream);"),
        ("void FAutoArchive::saveDelta(FDataStream& stream, std::vector<std::pair<std::string, std::string> >& callStacks) const",
         "stream << wireCount(m_deltas.size());")):
        meta, body = files.body(provider, signature)
        _require(required in body, "current archive provider contract changed")
        provider_methods.append(meta)
    enums = _text(files, project / "Source/Providers/Serialization/SdkEnumTypes.inc")
    enum_source = _text(files, project / "Source/Providers/Serialization/SdkEnumSerialization.cpp")
    for type_name in (_RAW_TYPES - {"int"}) | {"MissionTypes", "ReligionTypes"}:
        _require("SDK_ENUM(" + type_name + ")" in enums and "SDK_ENUM_BYTE(" + type_name + ")" not in enums,
                 "Unit enum width changed")
    _require("INT32 bits; memcpy(&bits,&value,sizeof(bits)); stream << bits;" in enum_source,
             "current raw enum provider changed")
    retained = _archive_exchange(files)
    files.finish()
    return dict(schema="zerosis.retail.unit_object_source_conformance.v1",
        status="SOURCE_ORDER_AND_WIRE_CONFORMANCE_RECORDED", states=states, constructors=constructors,
        archive_declarations=declarations, codecs=codecs, player_pools=pools, parser_headers=parser_headers,
        current_archive_provider_methods=provider_methods, retained_archive_component=retained,
        wire=dict(unit_version=9, archive_registered_fields=147, archive_groups=[dict(codec=c, count=n) for c, n in _GROUPS],
            archive_full_header_bytes=0, archive_string_count=2, archive_int_vector_count=10,
            explicit_unit_type_hash="one uint32 even when zero; archive UnitTypes remains a raw enum",
            promotions_version=1, promotion_count="signed catalog metadata then signed sparse-row count",
            promotion_row="uint32 hash and bool for every row, including zero/FFFFFFFF/unknown/OLIGARCHY hashes",
            religion_version=2, religion_payload="three raw32 values, no presence or count",
            explicit_state_ints_after_ignore_danger=list(_TAIL_INTS),
            mission_count="writer int getLength; reader UINT; negative signed count is rejected",
            mission_row_bytes=20, mission_inline_capacity=12, mission_inline_capacity_is_not_a_wire_limit=True,
            free_list_header_bytes="24 + 4*capacity", free_list_capacity_sixteen_header_bytes=88,
            free_list_no_object_length=True, object_order="ascending occupied slots; real Unit bodies must be consumed"),
        minimum_extents=dict(archive=555, unit_version=4, type_and_last_move=8, promotions=12,
            promotion_row=5, explicit_state=161, religion=16, great_work_and_tourism=8, missions=4,
            mission_row=20, unit=768),
        required_profile="Bnw9CompleteGreatWorkHashWord: no GreatWork or a successful GreatWorks Type lookup emits one hash word",
        limits=["The copied original FAutoArchive header declares full save/load; its implementation body is not copied source",
            "Original component map and exchanged bytes support the codec, not execution of the actual CvUnit serializer",
            "The retained disassembly does not contain the full archive save/load bodies",
            "GreatWork lookup failure can omit the word in the SDK writer and is outside the explicit complete-word profile",
            "Source conformance alone does not establish occupied public Unit framing, ruleset resolution or restoration",
            "No Host, GameCore, game UI or native process is loaded or run by this inspection"], inputs=list(files.rows.values()))
