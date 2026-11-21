"""Actual immutable font/skin bank checks using only C++14 file/CPU code."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import re
import struct
import sys

PROJECT=Path(__file__).resolve().parents[1]
sys.dont_write_bytecode=True
sys.path[:0]=[str(PROJECT/'tools'),str(PROJECT/'Tests')]
from menu_replay_legend_assets import MANIFEST,V2,V3,STAGE,CURRENT_FONT,GAME,OFFLINE,artifact,preflight,bank_sections
from menu_replay_restoration import build_cxx14
from native_build import run
from menu_suite_storage import storage


def preserved_faces(raw,count):
    pos=8
    def word():
        nonlocal pos
        value,=struct.unpack_from('<I',raw,pos);pos+=4;return value
    def text():
        nonlocal pos
        size=word();pos+=size
    for _ in range(word()):pos+=36;text();text()
    if word()!=count:raise ValueError('Actual font bank count differs')
    result=[]
    for _ in range(6):
        start=pos;word();text();pos+=12;layers=word();glyphs=word();pos+=20*layers+40*glyphs;result.append(raw[start:pos])
    return result


def main(argv=None):
    cli=argparse.ArgumentParser(description=__doc__)
    cli.add_argument('--revision')
    args=cli.parse_args(argv)
    if args.revision is not None and re.fullmatch('[a-z0-9_]{1,64}',args.revision) is None:cli.error('Revision must be a canonical owned label')
    stage=STAGE if args.revision is None else STAGE/'revisions'/args.revision
    stage.mkdir(parents=True,exist_ok=True);receipt=stage/'component_result.json'
    if receipt.exists():raise ValueError('Historical component receipt is immutable; choose a new revision')
    manifest=json.loads(MANIFEST.read_text('utf8'));gate=preflight()
    if any(manifest.get(name) is not value for name,value in OFFLINE.items()):raise ValueError('Offline manifest boundary differs')
    old=(V2/'frontend.bin').read_bytes();new=(V3/'frontend.bin').read_bytes()
    if preserved_faces(old,6)!=preserved_faces(new,7):raise ValueError('An immutable old face byte changed')
    files=[PROJECT/'Source/Host/MenuFrontEndAssets.h',Path(__file__),PROJECT/'Tests/menu_replay_legend_assets.cpp',
        PROJECT/'tools/menu_replay_legend_assets.py',PROJECT/'tools/menu_frontend_skin.py',PROJECT/'tools/menu_frontend_skin_pages.py',MANIFEST]
    files += [Path(row['path']) for row in manifest['files']]
    files += [GAME/relative for relative in CURRENT_FONT]
    files += [path for path in V2.rglob('*') if path.is_file()]
    before=[artifact(path) for path in files]
    build=PROJECT/'Build/MenuReplayLegendAssets'
    if args.revision is not None:build=build/args.revision
    build.mkdir(parents=True,exist_ok=True)
    report=dict(schema='zerosis.replay_legend.full_font_component.v1',**OFFLINE,
        cpp_dialect='c++14',source_manifest=artifact(MANIFEST),actual_sidecar_count=gate['file_count'],
        old_six_face_records_byte_identical=True,inputs_before=before,revision=args.revision,
        previous_delivery_preserved=artifact(STAGE/'delivery.json') if (STAGE/'delivery.json').exists() else None)
    cleanup=['menu_replay_legend_assets.obj','menu_replay_legend_assets.map','compile.rsp','read_build_environment.cmd']
    try:
        compiled=build_cxx14('menu_replay_legend_assets',build,stage,PROJECT/'Tests/menu_replay_legend_assets.cpp',
            [PROJECT/'Source/Host',PROJECT/'Tests'])
        report['build']=compiled
        imports=run([Path(compiled['compiler']).with_name('dumpbin.exe'),'/dependents',compiled['path']],cwd=build,timeout=30)
        names=sorted(set(re.findall(r'^\s+([A-Za-z0-9_.-]+\.dll)\s*$',imports.stdout.decode('mbcs',errors='replace'),re.M)))
        if imports.returncode or {name.lower() for name in names}!={'kernel32.dll'}:raise ValueError('Unexpected component imports: '+repr(names))
        report['imported_dlls']=names
        result=run([compiled['path'],V3,V2,PROJECT/'Source/Assets/UIFrontEnd'],cwd=build,timeout=60)
        if result.returncode:raise ValueError((result.stdout+result.stderr).decode('utf8',errors='replace'))
        report.update(json.loads(result.stdout))
        report['inputs_after']=[artifact(path) for path in files]
        if before!=report['inputs_after']:raise ValueError('Exact production, old pack or original inputs changed during fixture')
    except Exception as error:
        report.update(status='FAIL_REPLAY_LEGEND_FULL_FONT_COMPONENT',error=str(error));raise
    finally:
        removed=[]
        for leaf in cleanup:
            path=build/leaf
            if not path.exists():continue
            info=storage.ordinary(path)
            if path.absolute().parent!=build.absolute() or info.st_nlink!=1:raise ValueError('Cleanup target escaped exact private component intermediates')
            row=dict(artifact(path),allocated_bytes=storage.allocated(path));path.unlink()
            row['result']='DELETED_EXACT_OWNED_REGENERABLE_COMPONENT_INTERMEDIATE';removed.append(row)
        report['owned_intermediate_cleanup']=removed
        receipt.write_text(json.dumps(report,indent=2)+'\n',encoding='utf8')
    print(json.dumps(dict(status=report['status'],checks=report['checks'],texture_bank=report['texture_bank'],
        report=str(receipt),removed_intermediate_count=len(removed))))
    return 0


if __name__=='__main__':raise SystemExit(main())
