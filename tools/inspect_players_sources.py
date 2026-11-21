"""Inspect copied BNW slot initialization and contiguous Player parser sources.

Import and inspect are read-only. No child process, native library, installed
game, user save or private Host stream is used. CLI output is a compact summary.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

sys.dont_write_bytecode = True
from inspect_player_end_sources import inspect as inspect_player_end
from inspect_player_post_traits_sources import _Sources, _operands, _ordered, _require


_CORE = "CvGameCoreDLL_Expansion2/"
_SEMANTIC_FLAGS = ("objectReferencesVerified", "completeSaveVerified",
                   "rulesetCompatibilityVerified", "restoreApproved")
_SUPPORTING_SHA = "6791e41c2c9266aeade39d5bbde360cf6fc09b486561f663e0ae2ca4bb716bc8"


def _text(files, path):
    files.artifact(path)
    return Path(path).read_bytes().decode("latin1").replace("\r\n", "\n")


def _pair(files, roots, relative, signature, equal=True):
    witnesses, bodies = [], {}
    for kind, root in roots.items():
        meta, body = files.body(root / relative, signature)
        witnesses.append(dict(kind=kind, method=meta))
        bodies[kind] = body
    if equal:
        _require(bodies["original"] == bodies["current"],
                 "unclassified slot-initialization change: " + signature)
    return dict(signature=signature, witnesses=witnesses,
                identical_normalized_bodies=equal), bodies


def _parser_body(files, path, signature):
    """Skip default-argument braces before locating an inline function body."""
    source = files.artifact(path)
    raw = Path(path).read_bytes().decode("latin1")

    def extract(text):
        _require(text.count(signature) == 1, "ambiguous portable parser signature")
        start = text.index(signature)
        cursor = text.index("(", start)
        depth = 1
        cursor += 1
        while depth:
            _require(cursor < len(text), "unterminated portable parser parameters")
            if text[cursor] == "(":
                depth += 1
            elif text[cursor] == ")":
                depth -= 1
            cursor += 1
        cursor = text.index("{", cursor) + 1
        depth = 1
        while depth:
            _require(cursor < len(text), "unterminated portable parser body")
            if text[cursor] == "{":
                depth += 1
            elif text[cursor] == "}":
                depth -= 1
            cursor += 1
        return start, text[start:cursor]

    start, raw_body = extract(raw)
    body = raw_body.replace("\r\n", "\n")
    encoded, raw_encoded = body.encode("latin1"), raw_body.encode("latin1")
    return dict(source=source, signature=signature, line=raw[:start].count("\n") + 1,
                body_bytes=len(encoded), body_sha256=hashlib.sha256(encoded).hexdigest(),
                raw_body_bytes=len(raw_encoded), raw_body_sha256=hashlib.sha256(raw_encoded).hexdigest(),
                normalization="CRLF to LF only; default-argument braces excluded from body selection"), body


def _block(body, marker, expected_count=1):
    _require(body.count(marker) == expected_count, "ambiguous initialization branch: " + marker)
    start = body.index("{", body.index(marker))
    depth = 1
    end = start + 1
    while depth:
        _require(end < len(body), "unterminated initialization branch")
        if body[end] == "{":
            depth += 1
        elif body[end] == "}":
            depth -= 1
        end += 1
    return body[start:end]


def _direct(block, token):
    _require(block.count(token) == 1, "missing or repeated direct initialization: " + token)
    prefix = block[:block.index(token)]
    _require(prefix.count("{") - prefix.count("}") == 1,
             "catalog initialization acquired a nested condition: " + token)


def _previous(files):
    path = files.project / "evidence/retail_save_container/player_end/source_conformance.json"
    artifact = files.artifact(path)
    previous = json.loads(path.read_text(encoding="utf-8-sig"))
    _require(previous["schema"] == "zerosis.retail.player_end_source_conformance.v1" and
             previous["status"] == "SOURCE_ORDER_AND_WIRE_CONFORMANCE_RECORDED" and
             len(previous["inputs"]) == 40, "unexpected published Player end source contract")
    _require(inspect_player_end(files.project) == previous,
             "published Player end source conformance no longer recomputes equally")
    for row in previous["inputs"]:
        _require(set(row) == {"path", "bytes", "sha256"}, "non-flat inherited source artifact")
        files.pin(row)
    return dict(artifact=artifact, input_artifacts=40, recomputed_equal=True,
                source_inputs_reused_without_nested_report=True)


def _initialization(files, roots):
    rows = []

    def method(cpp, signature, equal=True):
        row, bodies = _pair(files, roots, _CORE + cpp, signature, equal)
        rows.append(row)
        return row, bodies

    statics_row, statics = method("CvPlayerAI.cpp", "void CvPlayerAI::initStatics()", False)
    guard = '\tif(m_aPlayers != NULL) throw std::logic_error("CvPlayerAI static array is already initialized");\n'
    _require(statics["current"].count(guard) == 1 and guard not in statics["original"] and
             statics["current"].replace(guard, "", 1) == statics["original"],
             "PlayerAI static initialization differs beyond the duplicate-initialization guard")
    statics_row["classified_current_difference"] = "reject duplicate static-array initialization"
    _ordered(statics["original"], ["FNEW(CvPlayerAI[MAX_PLAYERS]", "iI < MAX_PLAYERS",
                                    "m_aPlayers[iI].m_eID = ((PlayerTypes)iI);"])
    _, init_players = method("CvGame.cpp", "void CvGame::InitPlayers()")
    loop = _block(init_players["original"][init_players["original"].rindex(
        "for(iI = 0; iI < MAX_PLAYERS; iI++)"):], "for(iI = 0; iI < MAX_PLAYERS; iI++)")
    _ordered(loop, ["const PlayerTypes ePlayer = static_cast<PlayerTypes>(iI);",
                    "CvPlayerAI& kPlayer = GET_PLAYER(ePlayer);", "kPlayer.init(ePlayer);"])
    _direct(loop, "kPlayer.init(ePlayer);")
    _, init = method("CvPlayer.cpp", "void CvPlayer::init(PlayerTypes eID)")
    _ordered(init["original"], ["reset(eID);", "SlotStatus s = CvPreGame::slotStatus(p);",
                                "if((s == SS_TAKEN) || (s == SS_COMPUTER))", "setAlive(true);"])
    reset_row, reset = method("CvPlayer.cpp",
        "void CvPlayer::reset(PlayerTypes eID, bool bConstructorCall)", False)
    scope = "    ZeroSisLuaBorrowed::SuspensionScope borrowedState(this);\n"
    _require(reset["current"].count(scope) == 1 and scope not in reset["original"] and
             reset["current"].replace(scope, "", 1) == reset["original"],
             "Player reset differs beyond the classified borrowed-state scope")
    reset_row["classified_current_difference"] = "one borrowed-state SuspensionScope at entry"
    calls = ["m_pWonderProductionAI->Init(GC.GetGameBuildings(), this, false);",
             "m_pGrandStrategyAI->Init(GC.GetGameAIGrandStrategies(), this);",
             "m_pPlayerTechs->Init(GC.GetGameTechs(), this, false);", "m_pMinorCivAI->Init(this);"]
    for kind in roots:
        branch = _block(reset[kind], "if(!bConstructorCall)", 2)
        _ordered(branch, calls)
        for call in calls:
            _direct(branch, call)
        text = _text(files, roots[kind] / _CORE / "CvPlayer.cpp")
        _require(text.count("reset(NO_PLAYER, true);") == 1, "constructor reset profile changed")
        declaration = _text(files, roots[kind] / _CORE / "CvPlayer.h")
        _require("void reset(PlayerTypes eID = NO_PLAYER, bool bConstructorCall = false);" in declaration,
                 "Player read/init reset defaults changed")
        defines = _text(files, roots[kind] / "CvGameCoreDLLUtil/include/CvDLLUtilDefines.h")
        for name, value in (("MAX_CIV_PLAYERS", r"63"), ("MAX_MAJOR_CIVS", r"22"),
                            ("MAX_PLAYERS", r"MAX_CIV_PLAYERS \+ 1")):
            _require(re.search(r"#define\s+" + name + r"\s+\(" + value + r"\)", defines),
                     "BNW player width changed: " + name)
        _require(re.search(r"#define\s+BARBARIAN_PLAYER\s+\(\(PlayerTypes\)MAX_CIV_PLAYERS\)", defines),
                 "BNW barbarian slot changed")
    _, read = method("CvPlayer.cpp", "void CvPlayer::Read(FDataStream& kStream)", False)
    for body in read.values():
        _ordered(body, ["reset();", "kStream >> uiVersion;", "m_pWonderProductionAI->Read(kStream);",
                        "m_pGrandStrategyAI->Read(kStream);", "m_pPlayerTechs->Read(kStream);",
                        "m_pMinorCivAI->Read(kStream);"])
    _, dead = method("CvPlayer.cpp", "void CvPlayer::setAlive(bool bNewValue, bool bNotify)")
    _require("killUnits();" in dead["original"] and "killCities();" in dead["original"] and
             not re.search(r"\b(?:uninit|Uninit)\s*\(", dead["original"]),
             "death now changes the initialized AI-object lifecycle")

    for cpp, signature, tokens in (
        ("CvWonderProductionAI.cpp",
         "void CvWonderProductionAI::Init(CvBuildingXMLEntries* pBuildings, CvPlayer* pPlayer, bool bIsCity)",
         ["m_pBuildings = pBuildings;", "Reset();"]),
        ("CvTechClasses.cpp", "void CvPlayerTechs::Init(CvTechXMLEntries* pTechs, CvPlayer* pPlayer, bool bIsCity)",
         ["m_pTechs = pTechs;", "const int iNumTechs = m_pTechs->GetNumTechs();", "Reset();"]),
        ("CvGrandStrategyAI.cpp", "void CvGrandStrategyAI::Init(CvAIGrandStrategyXMLEntries* pAIGrandStrategies, CvPlayer* pPlayer)",
         ["m_pAIGrandStrategies = pAIGrandStrategies;",
          "m_paiGrandStrategyPriority = FNEW(int[m_pAIGrandStrategies->GetNumAIGrandStrategies()]", "Reset();"]),
        ("CvMinorCivAI.cpp", "void CvMinorCivAI::Init(CvPlayer* pPlayer)", ["m_pPlayer = pPlayer;", "Reset();"]),
        ("CvMinorCivAI.cpp", "void CvMinorCivAI::Reset()", ["ResetQuestList();", "if(GetPlayer()->isMinorCiv())"]),
    ):
        _, bodies = method(cpp, signature)
        _ordered(bodies["original"], tokens)
    _, quests = method("CvMinorCivAI.cpp", "void CvMinorCivAI::ResetQuestList()")
    _ordered(quests["original"], ["m_QuestsGiven.clear();", "iNewEntry < MAX_MAJOR_CIVS",
                                  "m_QuestsGiven.push_back(vQuestList);"])
    _require("if(" not in quests["original"] and "if (" not in quests["original"],
             "minor quest-list construction acquired a conditional")
    _, minor_write = method("CvMinorCivAI.cpp", "void CvMinorCivAI::Write(FDataStream& kStream) const")
    _ordered(minor_write["original"], ["m_QuestsGiven.size() == MAX_MAJOR_CIVS",
        "itr_player = m_QuestsGiven.begin(); itr_player != m_QuestsGiven.end();", "kStream << iQuestEntriesToWrite;"])
    _, minor_read = method("CvMinorCivAI.cpp", "void CvMinorCivAI::Read(FDataStream& kStream)")
    _ordered(minor_read["original"], ["ResetQuestList();", "iPlayerEntriesToRead = MAX_MAJOR_CIVS;",
                                      "iPlayerLoop < iPlayerEntriesToRead", "kStream >> iQuestEntriesToRead;"])
    _, wonder_write = method("CvWonderProductionAI.cpp", "void CvWonderProductionAI::Write(FDataStream& kStream) const")
    _ordered(wonder_write["original"], ["if(m_pBuildings)", "int iNumBuildings = m_pBuildings->GetNumBuildings();",
                                        "kStream << iNumBuildings;"])
    _, tech_write = method("CvTechClasses.cpp", "void CvPlayerTechs::Write(FDataStream& kStream)")
    _ordered(tech_write["original"], ["if(m_pTechs != NULL)", "const int iNumTechs = m_pTechs->GetNumTechs();",
                                      "WriteHashedDataArray<TechTypes, bool>", "m_pTechAI->Write(kStream);"])
    _require(tech_write["original"].count("CvInfosSerializationHelper::WriteHashedDataArray<") == 7,
             "initialized Player tech-array branch changed")
    _, grand_write = method("CvGrandStrategyAI.cpp", "void CvGrandStrategyAI::Write(FDataStream& kStream)")
    _require("kStream << ArrayWrapper<int>(m_pAIGrandStrategies->GetNumAIGrandStrategies(), m_paiGrandStrategyPriority);"
             in grand_write["original"], "external grand-strategy width changed")
    return dict(methods=rows, max_players=64, max_major_civs=22, barbarian_slot=63,
        init_players_calls_every_slot_before_alive_filter=True,
        initialized_catalogs_and_minor_quests_apply_to_dead_unused_and_barbarian_slots=True,
        minor_quest_outer_lists=22, minor_quest_writer_asserts_but_writes_no_outer_count=True,
        null_building_catalog_omits_count_and_rows=True, null_tech_catalog_omits_seven_arrays=True,
        constructor_only_state_supported=False,
        initialized_profile_conditions=["CvGame::InitPlayers or non-constructor CvPlayer::reset completed",
            "global building, tech and grand-strategy catalogs were available during reset",
            "the writer uses the retained BNW serializer versions and catalog profile"],
        grand_strategy_count="caller must supply the writer's global catalog width; 4 is an explicit hypothesis",
        original_retail_top_level_player_loop_verified=False)


def _city_projects(files, roots):
    rows = []
    for signature in ("void CvProjectProductionAI::Reset()", "void CvProjectProductionAI::Read(FDataStream& kStream)",
                      "void CvProjectProductionAI::Write(FDataStream& kStream) const"):
        row, bodies = _pair(files, roots, _CORE + "CvProjectProductionAI.cpp", signature)
        _require("i < GC.GetGameProjects()->GetNumProjects()" in bodies["original"],
                 "city project width is no longer the global catalog")
        if "::Write(" in signature:
            _require(_operands(bodies["original"], "<<") == ["uiVersion", "m_ProjectAIWeights.GetWeight(i)"] and
                     "uint uiVersion = 1;" in bodies["original"], "project AI acquired a wire count or another field")
        rows.append(row)
    for signature in ("void CvCityStrategyAI::Init(CvAICityStrategies* pAICityStrategies, CvCity* pCity, bool bIsCity)",
                      "void CvCityStrategyAI::Write(FDataStream& kStream)"):
        row, bodies = _pair(files, roots, _CORE + "CvCityStrategyAI.cpp", signature)
        _require(("m_pProjectProductionAI = FNEW(CvProjectProductionAI(pCity)" if "::Init(" in signature
                  else "m_pProjectProductionAI->Write(kStream);") in bodies["original"],
                 "City strategy project-object forwarding changed")
        rows.append(row)
    host = files.project / "Source/Host"
    meta, body = _parser_body(files, host / "RetailSavePlayerCities.h", "static RetailSavePlayerCitiesInspection InspectAt(")
    _ordered(body, ["ValidateCityProfile(input, profile);", "ReadFreeListHeader(input)",
                    "i < result.pool.liveCount", "ReadCityAI(input, profile)"])
    _require(body.count("ReadCityAI(input, profile)") == 1, "city pool parser has another object path")
    project_meta, project = files.body(host / "RetailSaveCityServices.h",
        "inline void ReadCityProjectProductionAI(Reader& reader, std::uint32_t projectCount)")
    _ordered(project, ["reader.Version(1);", "reader.Fixed(projectCount, 4);"])
    profile_meta, validate = files.body(host / "RetailSaveCity.h",
        "inline void ValidateCityProfile(Reader& input, const RetailSaveCityProfile& profile)")
    _require("projectCount" not in validate and "InitializedBuildingsAndUnits" in validate,
             "zero-city profile validation changed")
    return dict(methods=rows, pool_parser=meta, project_parser=project_meta, profile_guard=profile_meta,
        project_count_is_global_and_has_no_wire_count=True,
        zero_live_cities_consume_no_project_weight_payload=True,
        zero_live_cities_still_validate_the_city_catalog_and_yield_profile=True,
        project_count="caller must supply the writer's global project catalog width for every live city")


def _players_parser(files):
    path = files.project / "Source/Host/RetailSavePlayers.h"
    text = _text(files, path)
    enum = re.search(r"enum class RetailPlayerBlockProfile\s*\{\s*(\w+)\s*\};", text)
    _require(enum is not None and enum[1] == "Bnw64InSlotOrder", "explicit player-block profile changed")
    _require("std::array<RetailSavePlayerSlotInspection, 64> players{};" in text,
             "bounded 64-slot summary storage changed")
    meta, body = _parser_body(files, path, "static RetailSavePlayersInspection InspectAt(")
    _ordered(body, ["profile.blockProfile != RetailPlayerBlockProfile::Bnw64InSlotOrder",
        "RetailStateErrorCode::UnsupportedProfile", "auto remaining = limits;", "auto cursor = start;",
        "for (std::uint32_t slot = 0; slot < 64; ++slot)",
        "RetailSavePlayer::InspectAt(data, size, cursor, profile.playerProfile, remaining)",
        "player.playerId != static_cast<std::int32_t>(slot)", "player.whole.offset != cursor",
        "player.nextInflatedOffset <= cursor", "player.nextInflatedOffset > size || !player.completePlayerWireFramed",
        "player.arrayRecords > remaining.maxTotalRecords", "remaining.maxTotalRecords -= player.arrayRecords;",
        "result.arrayRecords += player.arrayRecords;", "cursor = player.nextInflatedOffset;", "++result.playerCount;",
        "result.whole = {start, cursor - start};", "result.nextInflatedOffset = cursor;",
        "result.allExpectedPlayersWireFramed = true;"])
    for token in ("auto remaining = limits;", "RetailSavePlayer::InspectAt(",
                  "remaining.maxTotalRecords -= player.arrayRecords;", "result.arrayRecords += player.arrayRecords;"):
        _require(body.count(token) == 1, "player-block budget or parsing path duplicated: " + token)
    _require("Reader" not in body and "remaining = limits;" not in body[body.index("for ("):],
             "player-block parser acquired an outer wire reader or per-slot budget reset")
    for flag in _SEMANTIC_FLAGS:
        _require("bool " + flag + " = false;" in text and
                 not re.search(r"\b" + flag + r"\s*=\s*true", text),
                 "player-block wire framing promotes an unsupported semantic claim: " + flag)
    return dict(header=files.artifact(path), method=meta, explicit_profile="Bnw64InSlotOrder",
        fixed_player_count=64, exact_slot_id_order=True, contiguous_boundaries=True,
        one_shared_record_budget=True, no_serialized_outer_count=True, semantic_flags_remain_false=True,
        top_level_retail_placement_inferred=False)


def _supporting(files, roots):
    serializers, bodies = [], {}
    specs = (
        ("game_read", "CvGame.cpp", "void CvGame::ReadSupportingClassData(FDataStream& kStream)"),
        ("game_write", "CvGame.cpp", "void CvGame::WriteSupportingClassData(FDataStream& kStream)"),
        ("barbarians_read", "CvBarbarians.cpp", "void CvBarbarians::Read(FDataStream& kStream, uint uiParentVersion)"),
        ("barbarians_write", "CvBarbarians.cpp", "void CvBarbarians::Write(FDataStream& kStream)"),
        ("goody_read", "CvGoodyHuts.cpp", "void CvGoodyHuts::Read(FDataStream& kStream, uint uiParentVersion)"),
        ("goody_write", "CvGoodyHuts.cpp", "void CvGoodyHuts::Write(FDataStream& kStream)"),
    )
    for name, cpp, signature in specs:
        row, pair = _pair(files, roots, _CORE + cpp, signature)
        row["name"] = name
        serializers.append(row)
        bodies[name] = pair["original"]
    for direction, suffix in ((">>", "read"), ("<<", "write")):
        game = bodies["game_" + suffix]
        _require(_operands(game, direction) == ["uiVersion"], "Supporting class prefix changed")
        _ordered(game, ["kStream " + direction + " uiVersion;",
                        "CvBarbarians::" + suffix.title() + "(kStream" ,
                        "CvGoodyHuts::" + suffix.title() + "(kStream"])
        barbarian_operands = ["uiVersion", "ArrayWrapper<short>(iWorldNumPlots, m_aiPlotBarbCampSpawnCounter)",
                              "ArrayWrapper<short>(iWorldNumPlots, m_aiPlotBarbCampNumUnitsSpawned)"]
        barbarian = bodies["barbarians_" + suffix]
        _require(_operands(barbarian, direction) == barbarian_operands and
                 "int iWorldNumPlots = GC.getMap().numPlots();" in barbarian,
                 "Supporting barbarian width/order or unprefixed arrays changed")
        goody = bodies["goody_" + suffix]
        _require(_operands(goody, direction) == ["uiVersion",
                 "ArrayWrapper<int>(NUM_GOODIES_REMEMBERED, m_aaiPlayerGoodyHutResults[iI])"] and
                 "for (int iI = 0; iI < MAX_MAJOR_CIVS; iI++)" in goody,
                 "Supporting goody dimensions or unprefixed rows changed")
    _ordered(bodies["barbarians_read"], ["GC.getMap().numPlots();", "MapInit(iWorldNumPlots);",
                                        "kStream >> ArrayWrapper<short>"])
    _ordered(bodies["goody_read"], ["Reset();", "kStream >> uiVersion;"])
    for name in ("game_write", "barbarians_write", "goody_write"):
        _require("uint uiVersion = 1;" in bodies[name], "Supporting latest writer version changed")
    codecs, wrappers = [], []
    stream = "FirePlace/include/FireWorks/FDataStream.h"
    for direction, signature in (
        ("<<", "FDataStream & operator<<(FDataStream & saveTo, const ArrayWrapper<ValueType> & v)"),
        (">>", "FDataStream & operator>>(FDataStream & loadFrom, ArrayWrapper<ValueType> & v)"),
    ):
        row, pair = _pair(files, roots, stream, signature)
        body = pair["original"]
        _require(_operands(body, direction) == ["values[i]"] and "int count = v.getCount();" in body and
                 "for(i = 0; i < count; ++i)" in body,
                 "ArrayWrapper acquired a serialized count or a different traversal")
        codecs.append(row)
    for method, suffix in (("Read", ""), ("Write", " const")):
        signature = "void CvDllGame::" + method + "SupportingClassData(FDataStream& kStream)" + suffix
        row, pair = _pair(files, roots, _CORE + "CvDllGame.cpp", signature)
        _require("m_pGame->" + method + "SupportingClassData(kStream);" in pair["original"],
                 "Supporting DLL wrapper forwarding changed")
        wrappers.append(row)
    declarations = []
    for kind, root in roots.items():
        barbarian_header = root / _CORE / "CvBarbarians.h"
        barbarian = _text(files, barbarian_header)
        for field in ("m_aiPlotBarbCampSpawnCounter", "m_aiPlotBarbCampNumUnitsSpawned"):
            _require("static short* " + field + ";" in barbarian, "Supporting short array declaration changed")
        goody_header = root / _CORE / "CvGoodyHuts.h"
        goody = _text(files, goody_header)
        _require(re.search(r"#define\s+NUM_GOODIES_REMEMBERED\s+\(3\)", goody) and
                 "static int** m_aaiPlayerGoodyHutResults;" in goody,
                 "Supporting goody count/type declaration changed")
        header = _text(files, root / stream)
        for token in ("void Write(const INT16 &);", "void Read(INT16 &);",
                      "void Write(const INT32 &);", "void Read(INT32 &);"):
            _require(token in header, "Supporting fixed-width scalar overload changed")
        declarations.append(dict(kind=kind, barbarian=files.artifact(barbarian_header),
                                 goody=files.artifact(goody_header), data_stream=files.artifact(root / stream)))
    path = files.project / "Source/Host/RetailSaveSupporting.h"
    header = files.artifact(path)
    _require(header["sha256"] == _SUPPORTING_SHA, "retained Supporting parser changed")
    read_meta, read_body = files.body(path, "inline void ReadSupporting(Reader& reader, std::size_t plotCount)")
    calls = [name + "(" + re.sub(r"\s+", "", args) + ")" for name, args in
             re.findall(r"\breader\.(Version|Fixed)\(([^()]*)\)", read_body)]
    _require(calls == ["Version(1)", "Version(1)", "Fixed(plotCount,2)", "Fixed(plotCount,2)",
                       "Version(1)", "Fixed(22u*3u,4)"], "Supporting portable wire order changed")
    inspect_meta, inspect_body = _parser_body(files, path, "static RetailInflatedSpan InspectAt(")
    _ordered(inspect_body, ["RetailStateDetail::Reader reader(data, size, limits);",
        "plotCount > limits.maxMapPlots", "RetailStateErrorCode::MapPlotLimit", "reader.Skip(start);",
        "RetailStateDetail::ReadSupporting(reader, plotCount);", "return reader.SpanFrom(start);"])
    return dict(serializers=serializers, array_wrapper_codecs=codecs, dll_forwarding=wrappers,
        declarations=declarations, parser=dict(header=header, read=read_meta, inspect_at=inspect_meta,
            unchanged_retained_header=True, caller_supplies_plot_count_explicitly=True,
            plot_count_must_match_previously_framed_map=True),
        wire=dict(supporting_version=1, barbarian_version=1, goody_version=1,
            barbarian_arrays=2, barbarian_element_bytes=2, goody_rows=22,
            goodies_remembered=3, goody_elements=66, goody_element_bytes=4,
            fixed_bytes=276, bytes_per_map_plot=4, size_formula="276 + 4 * map_plot_count",
            array_wrapper_writes_length=False, signed_negative_values_are_valid=True),
        identical_serializer_blocks=6, identical_array_wrapper_blocks=2,
        identical_dll_forwarding_blocks=2, top_level_retail_placement_inferred=False)


def inspect(project: Path) -> dict:
    """Return deterministic source evidence and flat path/bytes/sha256 inputs."""
    files = _Sources(project)
    files.artifact(files.project / "tools/inspect_players_sources.py")
    previous = _previous(files)
    roots = {"original": files.project / "Source/SDK_BNW_Original",
             "current": files.project / "Source/SDK_BNW_x64"}
    initialization = _initialization(files, roots)
    city_projects = _city_projects(files, roots)
    players = _players_parser(files)
    supporting = _supporting(files, roots)
    files.finish()
    return dict(schema="zerosis.retail.players_source_conformance.v1",
        status="SOURCE_ORDER_AND_WIRE_CONFORMANCE_RECORDED", previous_player_end=previous,
        scope="Copied original/current BNW initialization and portable 64-slot parser source only",
        initialization=initialization, city_projects=city_projects, players_parser=players,
        supporting=supporting, supporting_source_conformance_pending=False,
        limits=["The original retail executable's top-level whole-save loop remains unavailable",
            "The fixed 64-slot order is an explicit caller profile, not inferred from bytes",
            "Grand-strategy and city-project widths require the writer's external catalogs",
            "Static source conformance is not serializer execution, semantic verification or restore approval",
            "No installed game, user save, native Host, GameCore, process or private .zssave is accessed"],
        complete_save_verified=False, ruleset_compatibility_verified=False, restore_approved=False,
        full_engine_goal_complete=False, inputs=list(files.rows.values()))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path, default=Path(__file__).resolve().parents[1])
    arguments = parser.parse_args()
    result = inspect(arguments.project)
    print(json.dumps(dict(status=result["status"], input_artifacts=len(result["inputs"]),
        inherited_player_end_inputs=result["previous_player_end"]["input_artifacts"],
        fixed_player_count=result["players_parser"]["fixed_player_count"],
        supporting_size_formula=result["supporting"]["wire"]["size_formula"],
        supporting_source_conformance_pending=result["supporting_source_conformance_pending"])))


if __name__ == "__main__":
    main()
