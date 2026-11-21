"""Source-only City/CityAI/free-list conformance; inspection returns metadata.

No evidence files, processes, native libraries, or installed game inputs are
created or accessed. Complete object framing still requires the actual parsers.
"""
from __future__ import annotations

from pathlib import Path
import re

from inspect_player_post_traits_sources import _Sources, _ordered, _operands, _require


_STATES = (
    ("city", "CvCity.cpp", "CvCity", "read", "write", True, 6),
    ("city_ai", "CvCityAI.cpp", "CvCityAI", "read", "write", True, 1),
    ("buildings", "CvBuildingClasses.cpp", "CvCityBuildings", "Read", "Write", False, 1),
    ("strategy", "CvCityStrategyAI.cpp", "CvCityStrategyAI", "Read", "Write", False, 1),
    ("building_production", "CvBuildingProductionAI.cpp", "CvBuildingProductionAI", "Read", "Write", False, 1),
    ("unit_production", "CvUnitProductionAI.cpp", "CvUnitProductionAI", "Read", "Write", True, 1),
    ("project_production", "CvProjectProductionAI.cpp", "CvProjectProductionAI", "Read", "Write", True, 1),
    ("process_production", "CvProcessProductionAI.cpp", "CvProcessProductionAI", "Read", "Write", True, 1),
    ("citizens", "CvCityCitizens.cpp", "CvCityCitizens", "Read", "Write", False, 1),
    ("religions", "CvReligionClasses.cpp", "CvCityReligions", None, None, False, 3),
    ("religion_row", "CvReligionClasses.cpp", "CvReligionInCity", None, None, False, 2),
    ("emphases", "CvEmphasisClasses.cpp", "CvCityEmphases", "Read", "Write", False, 1),
    ("espionage", "CvEspionageClasses.cpp", "CvCityEspionage", None, None, False, 0),
)


def _signatures(cls, read, write, const):
    if read is None:
        return (f"FDataStream& operator>>(FDataStream& loadFrom, {cls}& writeTo)",
                f"FDataStream& operator<<(FDataStream& saveTo, const {cls}& readFrom)")
    return (f"void {cls}::{read}(FDataStream& kStream)",
            f"void {cls}::{write}(FDataStream& kStream)" + (" const" if const else ""))


def _pair(files, roots, relative, signatures, name, allow_city_scope=False):
    witnesses, bodies = [], {}
    for kind, root in roots.items():
        path = root / relative
        read_meta, read = files.body(path, signatures[0])
        write_meta, write = files.body(path, signatures[1])
        witnesses.append(dict(kind=kind, read=read_meta, write=write_meta))
        bodies[kind] = read, write
    current_read = bodies["current"][0]
    normalization = "none"
    if allow_city_scope:
        exact_line = "    ZeroSisLuaBorrowed::SuspensionScope borrowedState(this);\n"
        _require(current_read.count(exact_line) == 1 and exact_line not in bodies["original"][0],
                 "City reader suspension scope differs")
        current_read = current_read.replace(exact_line, "", 1)
        normalization = "remove exactly one retained SuspensionScope declaration in CvCity::read only"
    _require(current_read == bodies["original"][0] and bodies["current"][1] == bodies["original"][1],
             "unclassified City serializer change: " + name)
    return dict(name=name, witnesses=witnesses, reader_normalization=normalization,
                original_read_operands=_operands(bodies["original"][0], ">>"),
                original_write_operands=_operands(bodies["original"][1], "<<")), bodies


def inspect(project: Path) -> dict:
    """Inspect finite copied sources, return flat source pins and wire metadata."""
    files = _Sources(project)
    project = files.project
    for name in ("inspect_city_object_sources.py", "inspect_player_post_traits_sources.py",
                 "publish_retail_team_stage.py", "verify_retail_save_header.py"):
        files.artifact(project / "tools" / name)
    parser_headers = [files.artifact(project / "Source/Host" / name) for name in
        ("RetailSaveFreeList.h", "RetailSaveCity.h", "RetailSaveCityServices.h", "RetailSaveCityPopulation.h")]
    roots = {"original": project / "Source/SDK_BNW_Original", "current": project / "Source/SDK_BNW_x64"}
    states, state_bodies = [], {}
    for name, cpp, cls, read_name, write_name, const, version in _STATES:
        signatures = _signatures(cls, read_name, write_name, const)
        row, bodies = _pair(files, roots, "CvGameCoreDLL_Expansion2/" + cpp, signatures, name, name == "city")
        _require(re.search(r"\b(?:uint|int)\s+[ui]*Version\s*=\s*" + str(version) + r"\s*;", bodies["original"][1]),
                 "City writer version changed: " + name)
        row["latest_writer_version"] = version
        row["legacy_reader_predicates"] = re.findall(
            r"if\s*\(\s*(uiVersion\s*(?:>=|<=|>|<|==)\s*\d+)\s*\)", bodies["original"][0])
        states.append(row)
        state_bodies[name] = bodies
        for root in roots.values():
            files.artifact(root / "CvGameCoreDLL_Expansion2" / cpp.replace(".cpp", ".h"))

    city_order = []
    nested = ("m_pCityBuildings", "m_pCityStrategyAI", "m_pCityCitizens", "m_pCityReligions",
              "m_pEmphases", "m_pCityEspionage")
    for kind, root in roots.items():
        read, write = state_bodies["city"][kind]
        read_tokens = ["m_pCityBuildings->Read(kStream);", "m_pCityStrategyAI->Read(kStream);",
            "m_pCityCitizens->Read(kStream);", "kStream >> *m_pCityReligions;", "m_pEmphases->Read(kStream);",
            "kStream >> *m_pCityEspionage;", "kStream >> m_iExtraHitPoints;"]
        write_tokens = ["m_pCityBuildings->Write(kStream);", "m_pCityStrategyAI->Write(kStream);",
            "m_pCityCitizens->Write(kStream);", "kStream << *m_pCityReligions;", "m_pEmphases->Write(kStream);",
            "kStream << *m_pCityEspionage;", "kStream << m_iExtraHitPoints;"]
        _ordered(read, read_tokens)
        _ordered(write, write_tokens)
        ai_read, ai_write = state_bodies["city_ai"][kind]
        _ordered(ai_read, ["CvCity::read(kStream);", "kStream >> uiVersion;", "kStream >> m_bChooseProductionDirty;",
            "kStream >> m_iCachePlayerClosenessTurn;", "kStream >> m_iCachePlayerClosenessDistance;",
            "kStream >> m_aiPlayerCloseness;", "kStream >> m_aiNumPlotsAcquiredByOtherPlayers;"])
        _ordered(ai_write, ["CvCity::write(kStream);", "kStream << uiVersion;", "kStream << m_bChooseProductionDirty;",
            "kStream << m_iCachePlayerClosenessTurn;", "kStream << m_iCachePlayerClosenessDistance;",
            "kStream << m_aiPlayerCloseness;", "kStream << m_aiNumPlotsAcquiredByOtherPlayers;"])
        city_order.append(dict(kind=kind, nested_members=list(nested),
                              final_base_field="m_iExtraHitPoints", suffix="CvCityAI v1 after the complete CvCity v6"))
        ai_header = root / "CvGameCoreDLL_Expansion2/CvCityAI.h"
        header = ai_header.read_text(encoding="latin1")
        _require("int m_aiPlayerCloseness[REALLY_MAX_PLAYERS];" in header and
                 "int m_aiNumPlotsAcquiredByOtherPlayers[REALLY_MAX_PLAYERS];" in header,
                 "CityAI fixed-array declaration changed")
        defines = root / "CvGameCoreDLLUtil/include/CvDLLUtilDefines.h"
        files.artifact(defines)
        _require(re.search(r"#define\s+REALLY_MAX_PLAYERS\s+\(80\)", defines.read_text(encoding="latin1")),
                 "CityAI fixed-array width changed")
        player = root / "CvGameCoreDLL_Expansion2/CvPlayer.cpp"
        player_header = root / "CvGameCoreDLL_Expansion2/CvPlayer.h"
        files.artifact(player_header)
        declaration = player_header.read_text(encoding="latin1")
        for expected in ("FFreeListTrashArray<CvCityAI> m_cities;", "FFreeListTrashArray<CvUnit> m_units;",
                         "FFreeListTrashArray<CvArmyAI> m_armyAIs;"):
            _require(expected in declaration, "Player object-pool type changed")
        for signature, direction in (("void CvPlayer::Read(FDataStream& kStream)", ">>"),
                                     ("void CvPlayer::Write(FDataStream& kStream) const", "<<")):
            _, body = files.body(player, signature)
            _ordered(body, ["kStream " + direction + " " + member + ";" for member in
                            ("m_cityNames", "m_cities", "m_units", "m_armyAIs")])

    codec_specs = (
        ("free_list", "FirePlace/include/FireWorks/FFreeListTrashArray.h",
         "FDataStream & operator>>(FDataStream & readFrom, FFreeListTrashArray<T> & writeTo)",
         "FDataStream & operator<<(FDataStream & writeTo, const FFreeListTrashArray<T> & readFrom)"),
        ("building_array", "CvGameCoreDLL_Expansion2/CvBuildingClasses.cpp",
         "void BuildingArrayHelpers::Read(FDataStream& kStream, int* paiBuildingArray)",
         "void BuildingArrayHelpers::Write(FDataStream& kStream, int* paiBuildingArray, int iArraySize)"),
        ("hashed_2d", "CvGameCoreDLL_Expansion2/CvInfosSerializationHelper.h",
         "void ReadHashedDataArray(FDataStream& kStream, TData** ppaArray, int iSubArraySize, int iArraySize)",
         "void WriteHashedDataArray(FDataStream& kStream, TData** ppaArray, uint uiSubArraySize, uint uiArraySize)"),
        ("fixed_array", "FirePlace/include/FireWorks/FDataStream.h",
         "FDataStream & operator >> ( FDataStream & kStream, Firaxis::Array<T, ARRAY_SIZE> & kArray )",
         "FDataStream & operator << (FDataStream & kStream, const Firaxis::Array< T, ARRAY_SIZE > & kArray )"),
        ("raw_c_array", "FirePlace/include/FireWorks/FDataStream.h",
         "FDataStream & operator>>(FDataStream & loadFrom, ValueType (&writeTo)[count])",
         "FDataStream & operator<<(FDataStream & saveTo, const ValueType (&readFrom)[count])"),
    )
    codecs = []
    for name, path, read, write in codec_specs:
        row, bodies = _pair(files, roots, path, (read, write), name)
        codecs.append(row)
        if name == "free_list":
            _ordered(bodies["original"][1], ["writeTo << readFrom.GetNumSlots();",
                "writeTo << readFrom.GetLastIndex();", "writeTo << readFrom.GetFreeListHead();",
                "writeTo << readFrom.GetFreeListCount();", "writeTo << readFrom.GetCurrentID();",
                "writeTo << readFrom.GetNextFreeIndex( i );", "writeTo << readFrom.GetCount();", "writeTo << entry;"])
    for root in roots.values():
        for name in ("FFreeListArrayBase.h", "FAutoVector.h", "FStlContainerSerialization.h"):
            files.artifact(root / "FirePlace/include/FireWorks" / name)
        free_base = (root / "FirePlace/include/FireWorks/FFreeListArrayBase.h").read_text(encoding="latin1")
        _require("m_iLastIndex - m_iFreeListCount + 1" in free_base and
                 "m_iFreeListHead = FFreeList::FREE_LIST_INDEX;" in free_base,
                 "free-list constructor/count contract changed")

    # Automatic vector storage differs deliberately in the current SDK. Validate
    # its precise transactional temporary without changing the sequence codec.
    automatic = []
    for kind, root in roots.items():
        path = root / "FirePlace/include/FireWorks/FAutoVector.h"
        read_meta, read = files.body(path,
            "void FAutoVariable<std::vector<ElementType>, ClassContainer>::load(FDataStream & loadFrom)")
        write_meta, write = files.body(path,
            "void FAutoVariable<std::vector<ElementType>, ClassContainer>::save(FDataStream & saveTo) const")
        _require("saveTo << m_value;" in write and
                 ("loadFrom >> m_value;" in read if kind == "original" else
                  "loadFrom >> next;" in read and "m_value.swap(next);" in read), "automatic vector codec changed")
        automatic.append(dict(kind=kind, read=read_meta, write=write_meta,
                              storage="direct member" if kind == "original" else "existing transactional next then swap"))
    codecs.append(dict(name="auto_vector", witnesses=automatic, wire="unchanged counted sequence; no archive header"))
    sequence = []
    for kind, root in roots.items():
        path = root / "FirePlace/include/FireWorks/FStlContainerSerialization.h"
        read_meta, read = files.body(path,
            "void SerializeToSequenceContainer(FDataStream & loadFrom, ContainerType & container)")
        write_meta, write = files.body(path,
            "SerializeFromSequenceContainer(FDataStream & saveTo, const ContainerType & container)")
        _require(("ContainerType::size_type count = 0;" in read and "m_saveTo << container.size();" in write)
                 if kind == "original" else
                 ("unsigned int count = 0;" in read and
                  "m_saveTo << CvChecked::Integer<unsigned int>(container.size());" in write),
                 "STL sequence count width changed")
        sequence.append(dict(kind=kind, read=read_meta, write=write_meta))
    codecs.append(dict(name="stl_sequence", witnesses=sequence,
        wire="uint32 count: original Win32 size_type, existing current checked uint32"))
    files.finish()
    return dict(schema="zerosis.retail.city_object_source_conformance.v1",
        status="SOURCE_ORDER_AND_WIRE_CONFORMANCE_RECORDED", states=states, city_order=city_order,
        codecs=codecs, parser_headers=parser_headers,
        free_list=dict(metadata_int32=["capacity", "lastIndex", "freeHead", "freeCount", "currentId"],
            link_count="capacity", link_width=4, live_count="signed int32", header_bytes="24 + 4*capacity",
            maximum_slots=8192, source_capacity_eight_header_bytes=56,
            object_order="ascending occupied slot indexes; no per-object length or leading pool version",
            zero_capacity_constructor_head=-2, initialized_empty_head=-1,
            dormant_links="not traversed by the active free chain"),
        minimum_extents=dict(city_front=402, buildings=65, production_tables_and_ranks=96,
            strategy_constant=52, strategy_per_project=4, building_production=8, unit_production=8,
            project_production_constant=4, project_production_per_project=4, process_production=8,
            citizens=125, religions=13,
            religion_row=21, emphases=40, espionage=832, extra_hp=4, city_ai_suffix=653,
            city_base_constant=1629, city_ai_total_constant=2282, per_project=4,
            profile="Explicit project count, initialized Building/Unit production catalogs, explicit six yields"),
        wire_notes=["City base version 6 precedes CityAI suffix version 1",
            "BuildingArray skips an int only for hash zero; FFFFFFFF still has a value",
            "Hashed 2D row payload has the explicit six-yield profile width and no inner count",
            "ProjectProductionAI has no on-wire project count; ProcessProduction hash zero still has a weight",
            "CityAI two raw int arrays each use REALLY_MAX_PLAYERS=80 without length words"],
        limits=["Source conformance and declared framing extents only; no complete Player or state restoration result",
                "A pool header ending with liveCount zero reaches the next pool; otherwise actual object parsing is required"],
        inputs=list(files.rows.values()))
