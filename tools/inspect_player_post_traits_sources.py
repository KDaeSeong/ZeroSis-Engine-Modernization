"""Read copied SDK source witnesses for the Player post-Traits boundary.

The sole entry point returns metadata. Import and inspection write no files,
start no child processes, and load no native libraries. Historical compiler
records identify source witnesses; this helper does not execute or approve them.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import stat

from publish_retail_team_stage import writer_body


_PLAN_SHA = "cf05557b4e1e09b184188e4ba9e8af922147eca53db7f434bbfb6585ee877e82"
_BUILD_SHA = "dc7dd791816a870a1e6b55778b5f718ebf8f04418edf9e9a7eac5527f82bd303"
_COUNT_PLAN_SHA = "8425da60fcdc0a9d5b86adeaf4ea0ab4167885b9ca1b1f41cb5720622e09f2de"
_INITIALIZER_SPEC_SHA = "a06213e3cc305952506c7f6dca41cd238822efaad9f9d6470b79a842bf43de98"
_INITIALIZERS = {
    "CvEspionageClasses": "restore_espionage_ai_static_vectors_before_read",
    "CvCultureClasses": "initialize_culture_public_opinion_before_first_save",
}
_STATES = (
    ("spy", "CvEspionageClasses.cpp", "CvEspionageSpy", 1, 30),
    ("espionage", "CvEspionageClasses.cpp", "CvPlayerEspionage", 0, 216),
    ("espionage_ai", "CvEspionageClasses.cpp", "CvEspionageAI", 0, 37),
    ("trade", "CvTradeClasses.cpp", "CvPlayerTrade", 2, 12),
    ("trade_ai", "CvTradeClasses.cpp", "CvTradeAI", 0, 8),
    ("league_ai", "CvVotingClasses.cpp", "CvLeagueAI", 2, 8),
    ("culture", "CvCultureClasses.cpp", "CvPlayerCulture", 6, 238),
    ("notifications", "CvNotifications.cpp", "CvNotifications", 2, 4120),
    ("treasury", "CvTreasury.cpp", "CvTreasury", 1, 52),
)


def _require(value, message):
    if not value:
        raise RuntimeError("Player post-Traits source conformance: " + message)


def _key(path):
    return os.path.normcase(os.path.abspath(os.fspath(path)))


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _lf(value):
    return value.replace("\r\n", "\n")


class _Sources:
    def __init__(self, project):
        self.project = Path(project).absolute()
        self.rows = {}
        self.snapshots = {}

    def artifact(self, path):
        path = Path(path)
        _require(path.is_absolute() and ".." not in path.parts and
                 path.is_relative_to(self.project), "source escaped the project")
        for parent in (path, *path.parents):
            info = parent.lstat()
            _require(not stat.S_ISLNK(info.st_mode) and
                     not getattr(info, "st_file_attributes", 0) & 0x400, "reparse source path")
        before = path.stat()
        _require(stat.S_ISREG(before.st_mode), "source is not a regular file")
        raw = path.read_bytes()
        after = path.stat()
        snapshot = lambda info: (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns)
        _require(snapshot(before) == snapshot(after), "source changed while reading")
        row = dict(path=str(path), bytes=len(raw), sha256=_sha(raw))
        previous = self.rows.setdefault(_key(path), row)
        _require(previous["sha256"] == row["sha256"] and previous["bytes"] == row["bytes"],
                 "source changed during inspection")
        self.snapshots[_key(path)] = snapshot(after)
        return row

    def pin(self, row):
        actual = self.artifact(Path(row["path"]))
        _require(actual["sha256"] == row["sha256"] and
                 ("bytes" not in row or actual["bytes"] == row["bytes"]), "retained artifact drift")
        return actual

    def json(self, relative, expected):
        path = self.project / relative
        self.pin(dict(path=str(path), sha256=expected))
        return json.loads(path.read_text(encoding="utf-8-sig"))

    def body(self, path, signature):
        source = self.artifact(path)
        normalized = writer_body(path, signature)
        text = Path(path).read_bytes().decode("latin1")
        pattern = "\\r?\\n".join(re.escape(part) for part in normalized.decode("latin1").split("\n"))
        matches = list(re.finditer(pattern, text))
        _require(len(matches) == 1, "ambiguous raw serializer body")
        match = matches[0]
        raw = match.group().encode("latin1")
        return dict(source=source, signature=signature,
                    line=text[:match.start()].count("\n") + 1,
                    body_bytes=len(normalized), body_sha256=_sha(normalized),
                    raw_body_bytes=len(raw), raw_body_sha256=_sha(raw),
                    normalization="CRLF to LF only"), normalized.decode("latin1")

    def finish(self):
        for key, row in list(self.rows.items()):
            info = Path(row["path"]).stat()
            _require(self.snapshots[key] == (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns),
                     "input changed before inspection ended")


def _signatures(class_name):
    if class_name in {"CvLeagueAI", "CvNotifications", "CvTreasury"}:
        suffix = " const" if class_name == "CvNotifications" else ""
        return (f"void {class_name}::Read(FDataStream& kStream)",
                f"void {class_name}::Write(FDataStream& kStream){suffix}")
    return (f"FDataStream& operator>>(FDataStream& loadFrom, {class_name}& writeTo)",
            f"FDataStream& operator<<(FDataStream& saveTo, const {class_name}& readFrom)")


def _operands(body, direction):
    return [re.sub(r"\s+", " ", value).strip() for value in re.findall(
        r"(?m)^[ \t]*(?:saveTo|loadFrom|kStream)\s*" + re.escape(direction) + r"\s*([^;]+);", body)]


def _count_replay(original, current, file_plan):
    """Authenticate the already retained five direct-count edits in RAM."""
    preflight = _lf(file_plan["preflight"])
    _require(original.count("{\n") >= 1, "missing writer entry")
    expected = original.replace("{\n", "{\n" + preflight, 1)
    if file_plan["cpp"] == "CvCultureClasses.cpp":
        old = ("\tvector<CvPlot *>::const_iterator it;\n"
               "\tsaveTo << readFrom.m_aDigCompletePlots.size();\n"
               "\tfor(it = readFrom.m_aDigCompletePlots.begin(); it != readFrom.m_aDigCompletePlots.end(); it++)")
        new = ("\tsaveTo << iNumDigCompletePlots;\n"
               "\tvector<CvPlot *>::const_iterator it = readFrom.m_aDigCompletePlots.begin();\n"
               "\tfor(int iPlot = 0; iPlot < iNumDigCompletePlots; iPlot++, it++)")
        _require(expected.count(old) == 1, "culture counted iterator baseline changed")
        expected = expected.replace(old, new, 1)
    else:
        for site in file_plan["sites"]:
            _require(site["checked_type"] == "int", "unexpected direct-count type")
            expression, local = site["size_expression"], site["local"]
            old, new = "saveTo << " + expression + ";", "saveTo << " + local + ";"
            _require(expected.count(old) == 1, "count-write baseline changed")
            expected = expected.replace(old, new, 1)
            old = f"for(uint ui = 0; ui < {expression}; ui++)"
            new = f"for(int ui = 0; ui < {local}; ui++)"
            _require(expected.count(old) == 1, "counted-loop baseline changed")
            expected = expected.replace(old, new, 1)
    _require(expected == current, "unclassified current writer difference")
    _require(file_plan["original_prewrite_prefix_unchanged"] is True and
             file_plan["noncount_stream_operands_unchanged"] is True, "retained count-edit scope differs")
    return dict(kind="retained_checked_int32_count_preflight_and_loop_bounds",
                site_count=len(file_plan["sites"]), exact_original_to_current_replay=True,
                locals=[site["local"] for site in file_plan["sites"]])


def _ordered(body, tokens):
    positions = []
    start = 0
    for token in tokens:
        position = body.find(token, start)
        _require(position >= 0, "missing or reordered Player field: " + token)
        positions.append(position)
        start = position + len(token)
    return positions


def _player_order(files, roots):
    read_tokens = ["m_pTraits->Read(kStream);", "kStream >> *m_pEspionage;",
        "kStream >> *m_pEspionageAI;", "kStream >> *m_pTrade;", "kStream >> *m_pTradeAI;",
        "m_pLeagueAI->Read(kStream);", "kStream >> *m_pCulture;", "kStream >> bReadNotifications;",
        "if(bReadNotifications)", "m_pNotifications->Read(kStream);", "m_pTreasury->Read(kStream);"]
    write_tokens = ["m_pTraits->Write(kStream);", "kStream << *m_pEspionage;",
        "kStream << *m_pEspionageAI;", "kStream << *m_pTrade;", "kStream << *m_pTradeAI;",
        "m_pLeagueAI->Write(kStream);", "kStream << *m_pCulture;", "if(m_pNotifications)",
        "kStream << true;", "m_pNotifications->Write(kStream);", "kStream << false;",
        "m_pTreasury->Write(kStream);"]
    tail_members = ("m_ppaaiSpecialistExtraYield", "m_ppaaiImprovementYieldChange", "m_UnitCycle",
        "m_researchQueue", "m_bEverPoppedGoody", "m_bEverTrainedBuilder", "m_eEndTurnBlockingType",
        "m_iEndTurnBlockingNotificationIndex", "m_cityNames", "m_cities")
    witnesses = []
    for label, root in roots.items():
        path = root / "CvGameCoreDLL_Expansion2/CvPlayer.cpp"
        read_meta, read = files.body(path, "void CvPlayer::Read(FDataStream& kStream)")
        write_meta, write = files.body(path, "void CvPlayer::Write(FDataStream& kStream) const")
        _ordered(read, read_tokens + ["kStream >> " + name + ";" for name in tail_members])
        _ordered(write, write_tokens + ["kStream << " + name + ";" for name in tail_members])
        text = path.read_text(encoding="latin1")
        _require("const int g_CurrentCvPlayerVersion = 16;" in text,
                 "Player writer version changed")
        declaration = root / "CvGameCoreDLL_Expansion2/CvPlayer.h"
        files.artifact(declaration)
        declared = declaration.read_text(encoding="latin1")
        for member in ("FAutoVariable< std::vector< Firaxis::Array<int, NUM_YIELD_TYPES > >, CvPlayer> m_ppaaiSpecialistExtraYield;",
                       "FAutoVariable< std::vector< Firaxis::Array<int, NUM_YIELD_TYPES > >, CvPlayer> m_ppaaiImprovementYieldChange;",
                       "CLinkList<TechTypes> m_researchQueue;", "CLinkList<CvString> m_cityNames;"):
            _require(member in declared, "Player tail declaration changed")
        witnesses.append(dict(kind=label, read=read_meta, write=write_meta,
            read_order=[dict(expression=t, line=read_meta["line"] + read[:read.find(t)].count("\n"))
                        for t in read_tokens],
            write_order=[dict(expression=t, line=write_meta["line"] + write[:write.find(t)].count("\n"))
                         for t in write_tokens]))
    return dict(player_version=16, witnesses=witnesses,
                boundary_after="m_pTraits", stop_before="m_cities", tail_members=list(tail_members[:-1]))


def _codecs(files, roots):
    specs = (
        ("unit_cycler", "CvGameCoreDLL_Expansion2/CvUnitCycler.cpp",
         "FDataStream & operator>>(FDataStream & loadFrom, CvUnitCycler & writeTo)",
         "FDataStream & operator<<(FDataStream & saveTo, const CvUnitCycler & readFrom)"),
        ("linked_list", "CvGameCoreDLLUtil/include/LinkedList.h",
         "inline void CLinkList< T >::Read( FDataStream& kStream )",
         "inline void CLinkList< T >::Write( FDataStream& kStream ) const"),
        ("stl_sequence", "FirePlace/include/FireWorks/FStlContainerSerialization.h",
         "void SerializeToSequenceContainer(FDataStream & loadFrom, ContainerType & container)",
         "SerializeFromSequenceContainer(FDataStream & saveTo, const ContainerType & container)"),
        ("fixed_array", "FirePlace/include/FireWorks/FDataStream.h",
         "FDataStream & operator >> ( FDataStream & kStream, Firaxis::Array<T, ARRAY_SIZE> & kArray )",
         "FDataStream & operator << (FDataStream & kStream, const Firaxis::Array< T, ARRAY_SIZE > & kArray )"),
        ("auto_vector", "FirePlace/include/FireWorks/FAutoVector.h",
         "void FAutoVariable<std::vector<ElementType>, ClassContainer>::load(FDataStream & loadFrom)",
         "void FAutoVariable<std::vector<ElementType>, ClassContainer>::save(FDataStream & saveTo) const"),
    )
    result = []
    for name, relative, read_signature, write_signature in specs:
        witnesses = []
        for label, root in roots.items():
            path = root / relative
            read_meta, read = files.body(path, read_signature)
            write_meta, write = files.body(path, write_signature)
            if name == "unit_cycler":
                _require("loadFrom >> writeTo.m_kNodeList;" in read and "saveTo << readFrom.m_kNodeList;" in write,
                         "UnitCycler codec changed")
                header = root / "CvGameCoreDLL_Expansion2/CvUnitCycler.h"
                files.artifact(header)
                _require("typedef CLinkList<int> NodeList;" in header.read_text(encoding="latin1"),
                         "UnitCycler element type changed")
            elif name == "linked_list":
                _require("int iLength;" in read and "int iLength = getLength();" in write and
                         "kStream >>  *pData ;" in read and "kStream << pNode->m_data ;" in write,
                         "linked-list count or payload codec changed")
            elif name == "stl_sequence":
                if label == "original":
                    _require("ContainerType::size_type count = 0;" in read and
                             "m_saveTo << container.size();" in write, "original STL codec changed")
                else:
                    _require("unsigned int count = 0;" in read and
                             "m_saveTo << CvChecked::Integer<unsigned int>(container.size());" in write,
                             "current STL uint32 codec changed")
            elif name == "fixed_array":
                _require("kStream >> kArray[i];" in read and "kStream << kArray[i];" in write and
                         len(_operands(read, ">>")) == len(_operands(write, "<<")) == 1,
                         "fixed array acquired an extra count")
            else:
                _require("saveTo << m_value;" in write, "automatic vector writer codec changed")
                if label == "original":
                    _require("loadFrom >> m_value;" in read, "original automatic vector reader changed")
                else:
                    _require("std::vector<ElementType> next;" in read and "loadFrom >> next;" in read and
                             "m_value.swap(next);" in read, "current transactional vector reader changed")
            witness = dict(kind=label, read=read_meta, write=write_meta)
            if name == "auto_vector":
                witness["read_storage"] = ("direct member vector" if label == "original" else
                    "existing transactional temporary vector, then swap; same sequence wire codec")
            witnesses.append(witness)
        result.append(dict(name=name, witnesses=witnesses,
            wire=("signed int32 count and serialized elements" if name == "linked_list" else
                  "CLinkList<int32>; no extra header" if name == "unit_cycler" else
                  "uint32 sequence count; original Win32 size_type, current checked uint32" if name == "stl_sequence" else
                  "six int32 values with no row count" if name == "fixed_array" else
                  "direct vector codec; no archive or version prefix")))
    return result


def inspect(project: Path) -> dict:
    """Return compact source artifacts and precise framing facts; write nothing."""
    files = _Sources(project)
    project = files.project
    # Include both reused helpers in the caller's post-inspection hash ledger.
    for relative in ("tools/inspect_player_post_traits_sources.py",
                     "tools/publish_retail_team_stage.py", "tools/verify_retail_save_header.py"):
        files.artifact(project / relative)
    roots = {"original": project / "Source/SDK_BNW_Original",
             "current": project / "Source/SDK_BNW_x64"}
    plan = files.json("evidence/sdk_runtime_current/overlay_plan.json", _PLAN_SHA)
    build = files.json("evidence/sdk_runtime_current/build_result.json", _BUILD_SHA)
    counts = files.json("evidence/serialization/direct_stream_counts/plan.json", _COUNT_PLAN_SHA)
    initializer_spec = files.json("Source/Porting/save_restore_patches.json", _INITIALIZER_SPEC_SHA)
    _require(build["status"] == "PASS_CURRENT_RUNTIME_SDK_CANDIDATE_COMPILED_LINKED_NOT_LOADED" and
             build["plan"]["sha256"] == _PLAN_SHA, "retained runtime build is unrelated")
    selected = {row["name"]: row for row in plan["sdk_units"] if row["name"] in _INITIALIZERS}
    compiled = {row["name"]: row for row in build["compiled_units"] if row["name"] in _INITIALIZERS}
    _require(set(selected) == set(compiled) == set(_INITIALIZERS), "missing compiled source witness")
    runtime, runtime_records = {}, []
    for name, patch_id in _INITIALIZERS.items():
        unit, cell = selected[name], compiled[name]
        expected_path = project / "Build/SDKIncremental/x64/runtime_candidate/source/CvGameCoreDLL_Expansion2" / (name + ".cpp")
        _require(_key(unit["source"]["path"]) == _key(expected_path) and unit["source"] == cell["source"] and
                 cell["returncode"] == 0 and cell["role"] == "sdk_overlay" and cell["language_standard"] == "c++14",
                 "compiled source identity or role differs")
        files.pin(unit["source"])
        files.pin(unit["base_source"])
        files.pin(cell["object"])
        generation = unit["generation"]
        _require(generation["operation"] == "runtime_initializer_only_on_current_base" and
                 generation["patch_ids"] == [patch_id] and generation["old_count_and_include_patches_reapplied"] is False,
                 "runtime generation scope changed")
        patches = [patch for patch in initializer_spec["patches"] if patch["id"] == patch_id]
        _require(len(patches) == 1 and patches[0]["count"] == 1, "ambiguous runtime initializer patch")
        patch = patches[0]
        base = Path(unit["base_source"]["path"]).read_bytes()
        old, new = patch["old"].encode("latin1"), patch["new"].encode("latin1")
        _require(base.count(old) == 1 and base.replace(old, new, 1) == expected_path.read_bytes(),
                 "runtime source differs from the one retained initializer patch")
        runtime[name + ".cpp"] = expected_path
        runtime_records.append(dict(name=name, source=unit["source"], current_source=unit["base_source"],
            compiled_object=cell["object"], patch_id=patch_id,
            source_replay="exact whole-source current plus one retained initializer patch",
            patch_old_sha256=_sha(old), patch_new_sha256=_sha(new),
            source_count=1, patch_count=1, compiler_returncode=cell["returncode"]))
    count_plans = {row["cpp"]: row for row in counts["file_plans"]
                   if row["cpp"] in {"CvEspionageClasses.cpp", "CvCultureClasses.cpp"}}
    _require(len(count_plans) == 2 and sum(len(row["sites"]) for row in count_plans.values()) == 5,
             "retained direct-count site set changed")
    states, differences = [], []
    for name, cpp, class_name, version, minimum in _STATES:
        read_signature, write_signature = _signatures(class_name)
        witnesses, bodies = [], {}
        paths = {label: root / "CvGameCoreDLL_Expansion2" / cpp for label, root in roots.items()}
        if cpp in runtime:
            paths["compiled_runtime_source"] = runtime[cpp]
        for label, path in paths.items():
            read_meta, read = files.body(path, read_signature)
            write_meta, write = files.body(path, write_signature)
            _require(re.search(r"\b(?:uint|int)\s+[ui]*Version\s*=\s*" + str(version) + r"\s*;", write),
                     "writer version changed: " + name)
            witnesses.append(dict(kind=label, read=read_meta, write=write_meta))
            bodies[label] = read, write, read_meta, write_meta
        _require(bodies["original"][0] == bodies["current"][0], "unclassified current reader difference: " + name)
        if bodies["original"][1] != bodies["current"][1]:
            _require(name in {"espionage", "culture"}, "unclassified writer change: " + name)
            file_plan = count_plans[cpp]
            _require(bodies["current"][3]["source"]["sha256"] == file_plan["after_sha256"],
                     "direct-count file plan no longer names current source")
            difference = _count_replay(bodies["original"][1], bodies["current"][1], file_plan)
            differences.append(dict(state=name, **difference))
        if "compiled_runtime_source" in bodies:
            _require(bodies["current"][1] == bodies["compiled_runtime_source"][1],
                     "runtime initializer changed serialized writer: " + name)
            if name != "espionage_ai":
                _require(bodies["current"][0] == bodies["compiled_runtime_source"][0],
                         "unclassified runtime reader difference: " + name)
            else:
                _require(_operands(bodies["current"][0], ">>") ==
                         _operands(bodies["compiled_runtime_source"][0], ">>"),
                         "runtime reset patch changed a serialized operand")
                differences.append(dict(state=name, kind="seven_vectors_cleared_before_existing_counted_reads",
                    serialized_operand_order_equal=_operands(bodies["current"][0], ">>") ==
                        _operands(bodies["compiled_runtime_source"][0], ">>"),
                    patch_id=_INITIALIZERS["CvEspionageClasses"]))
            if name in {"espionage", "culture"}:
                proof = [row for row in plan["semantic_proof"]["checked_count_writer_bodies"]
                         if row["name"] == Path(cpp).stem]
                _require(len(proof) == 1 and proof[0]["identical"] is True and
                         proof[0]["before_sha256"] == bodies["current"][3]["raw_body_sha256"] and
                         proof[0]["after_sha256"] == bodies["compiled_runtime_source"][3]["raw_body_sha256"],
                         "compiled writer-preservation metadata differs from actual bodies")
        states.append(dict(name=name, latest_writer_version=version, minimum_bytes=minimum,
            nested_only=name == "spy", witnesses=witnesses,
            original_read_operands=_operands(bodies["original"][0], ">>"),
            original_write_operands=_operands(bodies["original"][1], "<<"),
            legacy_reader_predicates=re.findall(r"if\s*\(\s*(uiVersion\s*(?:>=|<=|>|<|==)\s*\d+)\s*\)", bodies["original"][0])))
    constants = []
    for label, root in roots.items():
        defines = root / "CvGameCoreDLLUtil/include/CvDLLUtilDefines.h"
        yields = root / "CvGameCoreDLL_Expansion2/CvGameCoreEnums.h"
        notifications = root / "CvGameCoreDLL_Expansion2/CvNotifications.cpp"
        for path in (defines, yields, notifications):
            files.artifact(path)
        _require(re.search(r"#define\s+MAX_MAJOR_CIVS\s+\(22\)", defines.read_text(encoding="latin1")),
                 "major civilization width changed")
        _require(re.search(r"#define\s+MAX_NOTIFICATIONS\s+100\b", notifications.read_text(encoding="latin1")),
                 "notification slot width changed")
        enum = yields.read_text(encoding="latin1")
        _require(re.search(r"YIELD_FOOD,\s*YIELD_PRODUCTION,\s*YIELD_GOLD,\s*YIELD_SCIENCE,\s*YIELD_CULTURE,\s*YIELD_FAITH,\s*NUM_YIELD_TYPES", enum),
                 "six-yield row width changed")
        constants.append(dict(kind=label, major_civilizations=22, notification_slots=100, yields=6))
    player = _player_order(files, roots)
    codecs = _codecs(files, roots)
    files.finish()
    return dict(schema="zerosis.retail.player_post_traits_source_conformance.v1",
        status="SOURCE_ORDER_AND_WIRE_CONFORMANCE_RECORDED",
        scope="Copied original/current serializers and finite retained runtime source witnesses; stop before cities",
        states=states, player_order=player, codecs=codecs, constants=constants,
        pre_city_tail=dict(minimum_bytes=30, fields=[
            "two uint32-counted matrices of unprefixed six-int32 rows",
            "signed-counted UnitCycle int32 list", "signed-counted research TechTypes int32 list",
            "two bools", "EndTurnBlockingTypes int32", "notification index int32",
            "signed-counted city-name string list"], external_catalog_count="not required for framing"),
        minimum_extents=dict(through_treasury_notifications_absent=572,
            through_treasury_notifications_present=4692, through_pre_city_notifications_absent=602,
            through_pre_city_notifications_present=4722,
            basis="Empty variable payloads, canonical encoded 22 dimensions, and latest supported writer versions"),
        known_differences=differences, retained_runtime_sources=runtime_records,
        evidence_counts=dict(top_level_states=8, nested_spy_states=1, direct_count_sites=5,
                             runtime_initializer_patches=2, compiled_source_witness_files=2),
        limits=["No city, unit, army, operation, full Player, complete save, ruleset, or restore result",
                "Count fields and fixed widths describe source wire framing, not valid gameplay values"],
        inputs=list(files.rows.values()))
