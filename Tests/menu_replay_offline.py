"""Compile/run only a static-CRT SDK-free replay fixture with exact SDK writer bodies."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import re
import sys

PROJECT=Path(__file__).absolute().parents[1]
sys.dont_write_bytecode=True
sys.path.insert(0,str(PROJECT/'tools'))
from native_build import build_program,run
from menu_replay_assets import artifact,freeze_replay_sources,source_profile
from menu_suite_storage import storage

STAGE=PROJECT/'evidence/game_menu/original_menu_followup/replay'
BUILD=PROJECT/'Build/MenuReplayComponent/current'


def block(source,marker):
    if source.count(marker)!=1:raise ValueError('Expected one exact SDK writer declaration: '+marker)
    start=source.index(marker);brace=source.index('{',start);depth=1;at=brace+1
    while depth and at<len(source):
        if source[at]=='{':depth+=1
        elif source[at]=='}':depth-=1
        at+=1
    if depth:raise ValueError('Unbalanced actual SDK writer body')
    if source[at:at+1]==';':at+=1
    return source[start:at]


def extract_writer():
    cpp=PROJECT/'Source/SDK_BNW_x64/CvGameCoreDLL_Expansion2'
    container=PROJECT/'Source/SDK_BNW_x64/FirePlace/include/FireWorks/FStlContainerSerialization.h'
    provider=PROJECT/'Source/Providers/Streams/SdkDataStream.cpp'
    pairs=[(provider,'unsigned int stringCount(size_t count)'),
        (provider,'template<class C> unsigned int writeText(FDataStream& s, const C* text, size_t length)'),
        (container,'template<typename FirstType, typename SecondType>\nFDataStream & operator<<(FDataStream & saveTo, const std::pair<FirstType, SecondType> & readFrom)'),
        (container,'template<typename ElementType, typename ContainerType>\nstruct SerializeFromSequenceContainer'),
        (container,'template<typename ElementType> \nFDataStream & operator<<(FDataStream & saveTo, const std::vector<ElementType> & readFrom)'),
        (container,'template<typename ElementType, typename ContainerType>\nstruct SerializeFromAssociativeContainer'),
        (container,'template<typename KeyType, typename ElementType>\nFDataStream & operator<<(FDataStream & saveTo, const std::map<KeyType, ElementType> & readFrom)'),
        (cpp/'CvReplayInfo.cpp','void CvReplayInfo::write(FDataStream& kStream) const'),
        (cpp/'CvReplayInfo.cpp','FDataStream& operator<<(FDataStream& saveTo, const CvReplayInfo::PlayerInfo& readFrom)'),
        (cpp/'CvReplayInfo.cpp','FDataStream& operator<<(FDataStream& saveTo, const CvReplayInfo::PlotState& readFrom)'),
        (cpp/'CvReplayInfo.cpp','FDataStream& operator<<(FDataStream& saveTo, const CvReplayInfo::TurnData& readFrom)'),
        (cpp/'CvReplayMessage.cpp','void CvReplayMessage::write(FDataStream& kStream) const')]
    bodies=[];refs=[]
    for path,marker in pairs:
        # Source decoding preserves every original byte; selected writer bodies are ASCII.
        text=path.read_bytes().decode('latin1').replace('\r\n','\n');body=block(text,marker)
        bodies.append(body);refs.append(dict(source=artifact(path),declaration=marker,
            first_line=text.count('\n',0,text.index(marker))+1,
            extracted_sha256=hashlib.sha256(body.encode('ascii')).hexdigest(),bytes=len(body.encode('ascii'))))
    target=BUILD/'sdk_replay_writer.inc';target.write_text('\n\n'.join(bodies)+'\n',encoding='ascii')
    return dict(extracted=artifact(target),methods=refs,source_bodies_verbatim=True,
        primitive_fixture_stream='little-endian integral widths + exact provider writeText; GameTypes signed byte',
        sdk_headers_or_objects_linked=False)


def cleanup_owned(names):
    rows=[]
    for name in names:
        path=BUILD/name
        if not path.exists():continue
        info=storage.ordinary(path)
        if path.absolute().parent!=BUILD.absolute() or info.st_nlink!=1:raise RuntimeError('Fixture cleanup scope changed')
        row=dict(artifact(path),file_identity=[info.st_dev,info.st_ino],allocated_bytes=storage.allocated(path))
        path.unlink();row['result']='DELETED_EXACT_OWNED_REGENERABLE_INTERMEDIATE';rows.append(row)
    return rows


def main():
    BUILD.mkdir(parents=True,exist_ok=True);STAGE.mkdir(parents=True,exist_ok=True)
    receipt=STAGE/'offline_result.json'
    if receipt.exists():raise RuntimeError('Inspect existing replay component proof before rerunning')
    sources=freeze_replay_sources();profile=source_profile(sources)
    (STAGE/'original_sources.json').write_text(json.dumps(profile,indent=2)+'\n',encoding='utf8')
    protected=[artifact(PROJECT/p) for p in (
        'Build/UiWindowHost/20261101T074006Z_c2fd2fe9be38/final/ZeroSisHost_x64.exe',
        'Build/UnitGreatWorkSaveSDK/2bdcdf80a1695780f864/CvGameCoreDLL_Expansion2_x64.dll',
        'evidence/interactive_game/20261101T080450Z_424fb64608b2/request.json',
        'tools/Start-Engine.ps1','Play/EarlyAccess/release.json')]
    report=dict(schema='zerosis.menu_replay.sdk_free_component.v1',native_host_or_sdk_execution=False,
        window_or_gpu_created=False,synthetic_fixture_history=True,original_replay_sources=sources,
        protected_before=protected)
    try:
        report['actual_sdk_writer_extraction']=extract_writer()
        built=build_program(name='MenuReplayComponent',architecture='x64',
            vs=Path(r'C:\Program Files\Microsoft Visual Studio\2022\Community'),directory=BUILD,evidence=STAGE,
            source=PROJECT/'Tests/menu_replay_fixture.cpp',includes=[PROJECT/'Source/Host',BUILD])
        report['build']=built
        imported=run([Path(built['compiler']).with_name('dumpbin.exe'),'/dependents',built['path']],cwd=BUILD,timeout=30)
        names=sorted(set(re.findall(r'^\s+([A-Za-z0-9_.-]+\.dll)\s*$',imported.stdout.decode('mbcs',errors='replace'),re.M)))
        if imported.returncode or not names or {x.lower() for x in names}-{'kernel32.dll'}:
            raise RuntimeError('SDK-free fixture imports unexpected modules: '+repr(names))
        report['imported_dlls']=names
        output=run([built['path'],BUILD/'sdk_writer_fixture.bin'],cwd=BUILD,timeout=30)
        if output.returncode:raise RuntimeError((output.stdout+output.stderr).decode('utf8',errors='replace'))
        report.update(json.loads(output.stdout));report['preserved_writer_fixture']=artifact(BUILD/'sdk_writer_fixture.bin')
        report['production_sources']=[artifact(PROJECT/name) for name in ('Source/Host/MenuReplayData.h','Source/Host/MenuReplayTimeline.h')]
        after=[artifact(row['path']) for row in protected]
        if after!=protected:raise RuntimeError('Protected original Host/SDK/default/prepared pair changed')
        report['protected_after']=after
    except Exception as error:
        report.update(status='FAIL_SDK_FREE_REPLAY_COMPONENT',error=str(error));raise
    finally:
        report['owned_intermediate_cleanup']=cleanup_owned(('MenuReplayComponent.obj','MenuReplayComponent.map',
            'compile.rsp','read_build_environment.cmd','sdk_replay_writer.inc'))
        receipt.write_text(json.dumps(report,indent=2)+'\n',encoding='utf8')
    print(json.dumps(dict(status=report['status'],checks=report['checks'],report=str(receipt),native_host_or_sdk_execution=False)))
    return 0


if __name__=='__main__':raise SystemExit(main())
