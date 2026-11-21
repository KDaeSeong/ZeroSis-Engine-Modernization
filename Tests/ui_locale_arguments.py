"""Controlled console check: retail Locale argument dispatch with the existing Lua 5.1 provider.

Compiles Tests/ui_locale_arguments.cpp against Source/Host/UiLocaleArguments.h and the existing
ZeroSis Lua 5.1 x64 provider library, runs the console fixture, and binds the result to the pinned
retail Locale.Lookup/ConvertTextKey probe and to the production UiPopupContext::Localize source.
No Host, GameCore, SDK DLL, Localization library, window, GPU, audio or game process is started.
"""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import re
import sys

sys.dont_write_bytecode = True
PROJECT = Path(__file__).absolute().parents[1]
sys.path.insert(0, str(PROJECT / 'tools'))
from native_build import environment_for, run
from collect_baseline import pe_header
import build_exit_confirm_host as common
from menu_suite_storage import storage

STAGE = PROJECT / 'evidence/game_menu/native_offline_followup/locale_arguments'
BUILD = PROJECT / 'Build/UiLocaleArguments/current'
SDK = PROJECT / 'Source/SDK_BNW_x64'
PROBE = PROJECT / 'evidence/game_menu/replay_season_wheel/retail_static_probe.json'
PROBE_SHA = '5707b107e28f370352fc05eea1334504ccb3e620c76d7bca6a817766a5556f6c'
LUA_REPORT = PROJECT / 'evidence/lua_provider/build_result.json'
SOURCES = ['Tests/ui_locale_arguments.cpp', 'Tests/ui_locale_arguments.py', 'Source/Host/UiLocaleArguments.h',
           'Source/Host/UiPopupContext.h']
LEAVES = ['UiLocaleArguments.exe', 'UiLocaleArguments.obj', 'UiLocaleArguments.map', 'compile.rsp', 'read_build_environment.cmd']


def require(value, message):
    if not value:
        raise ValueError(message)


def retail_dispatch():
    require(hashlib.sha256(PROBE.read_bytes()).hexdigest() == PROBE_SHA, 'Pinned retail locale probe differs')
    probe = json.loads(PROBE.read_text('utf8'))
    require(probe.get('executed') is False and probe['exe']['sha256'] ==
            'b7c8977ebab33ba6c1abf65d63fa310f8d096341465e0fc419f1b4da0fcd8818', 'Locale probe is not the static pinned-EXE record')
    rows = {}
    for name in ('Lookup', 'ConvertTextKey'):
        function = probe['locale']['functions'][name]
        require('boolean->PushArgument(int), number->PushArgument(double), string->PushArgument(const char*)' in function['finding'],
                name + ' argument dispatch finding differs')
        text = [row['text'] for row in function['listing']]
        for sequence in (['sub eax, 1', 'je'], ['sub eax, 2', 'je'], ['sub eax, 1', 'je']):
            require(any(text[i] == sequence[0] and text[i + 1].startswith(sequence[1]) for i in range(len(text) - 1)),
                    name + ' lua_type switch differs')
        require('fstp qword ptr [esp]' in text, name + ' number argument is not pushed as a double')
        rows[name] = dict(function=function['function'], finding=function['finding'])
    return rows


def production_binding():
    context = (PROJECT / 'Source/Host/UiPopupContext.h').read_text('utf8')
    start = context.index('    static std::string Localize(lua_State* state){')
    body = context[start:context.index('    static int PushText(lua_State* state){', start)]
    require('PushRetailLocaleArgument(state,index,value,' in body and 'Localization::Lookup(Text(state,at))' in body,
            'UiPopupContext::Localize does not use the retail argument dispatch')
    require('static_cast<int>(number)' not in body and 'LUA_TNUMBER' not in body, 'Localize keeps a private number path')
    require('#include "UiLocaleArguments.h"' in context, 'UiPopupContext does not include the retail dispatch header')
    return dict(function='ZeroSisHost::UiPopupContext::Localize', dispatch='ZeroSisHost::PushRetailLocaleArgument')


def build(directory, evidence):
    lua = json.loads(LUA_REPORT.read_text('utf-8-sig'))
    library = Path(lua['library']['path'])
    require(lua['status'] == 'LUA51_X64_MD_PROVIDER_BUILT' and common.artifact(library)['sha256'] == lua['library']['sha256'],
            'Existing Lua 5.1 provider differs from its build record')
    environment, compiler = environment_for(Path(r'C:/Program Files/Microsoft Visual Studio/2022/Community'), 'x64', directory)
    compiler = Path(compiler)
    executable = directory / 'UiLocaleArguments.exe'
    flags = ['/nologo', '/std:c++14', '/EHsc', '/W4', '/WX', '/O2', '/fp:strict', '/MD', '/utf-8', '/external:W0',
             f'/I"{PROJECT / "Source/Host"}"', f'/external:I"{SDK / "ThirdPartyLibs/Lua51/include"}"',
             f'"{PROJECT / "Tests/ui_locale_arguments.cpp"}"', f'"{library}"',
             f'/Fo"{directory / "UiLocaleArguments.obj"}"', f'/Fe"{executable}"']
    link = ['/INCREMENTAL:NO', '/Brepro', '/WX', '/OPT:REF', '/OPT:ICF', '/MACHINE:X64', f'/MAP:{directory / "UiLocaleArguments.map"}',
            'kernel32.lib']
    response = directory / 'compile.rsp'
    response.write_text('\n'.join(flags) + '\n', encoding='utf8')
    result = run([compiler, '@' + str(response), '/link', *link], cwd=directory, env=environment, timeout=180)
    output = (result.stdout + result.stderr).decode('mbcs', errors='replace')
    log = evidence / 'compile_UiLocaleArguments_x64_cxx14.txt'
    log.write_text(output, encoding='utf8')
    require(not result.returncode and not re.search(r'\bwarning\s+[A-Z]+\d+|경고\s+[A-Z]+\d+', output, re.I),
            'Locale argument fixture build failed or warned: ' + output[:4000])
    require(pe_header(executable)['architecture'] == 'x64', 'Wrong fixture architecture')
    imported = run([compiler.with_name('dumpbin.exe'), '/dependents', executable], cwd=directory, env=environment, timeout=30)
    names = sorted(set(re.findall(r'^\s+([A-Za-z0-9_.-]+\.dll)\s*$', imported.stdout.decode('mbcs', errors='replace'), re.M)))
    allowed = {'kernel32.dll', 'vcruntime140.dll', 'vcruntime140_1.dll', 'msvcp140.dll'}
    require(not imported.returncode and names and all(n.lower() in allowed or n.lower().startswith('api-ms-win-crt-') for n in names),
            'Unexpected fixture imports: ' + repr(names))
    return dict(executable=common.artifact(executable), compiler=common.artifact(compiler), flags=flags + ['/link'] + link,
                response=common.artifact(response), log=common.artifact(log), lua_provider=common.artifact(library),
                imported_dlls=names, compiler_and_linker_warnings=0, cpp_dialect='c++14')


def main():
    paths = [PROJECT / name for name in SOURCES] + [PROBE, LUA_REPORT]
    before = [common.artifact(path) for path in paths]
    signature = hashlib.sha256(json.dumps(before, sort_keys=True).encode()).hexdigest()[:16]
    stage = STAGE / signature
    stage.mkdir(parents=True, exist_ok=True)
    receipt = stage / 'result.json'
    require(not receipt.exists(), 'Inspect the existing result instead of repeating this exact input set')
    BUILD.mkdir(parents=True, exist_ok=True)
    require(not any((BUILD / name).exists() for name in LEAVES), 'Inspect retained prior fixture intermediates')
    report = dict(schema='zerosis.native_offline_followup.locale_arguments.v1', inputs_before=before,
                  host_or_sdk_executed=False, localization_library_loaded=False, native_window_execution=False,
                  gpu_execution=False, audio_execution=False)
    try:
        report['retail_dispatch'] = retail_dispatch()
        report['production_binding'] = production_binding()
        report['build'] = build(BUILD, stage)
        result = run([BUILD / 'UiLocaleArguments.exe'], cwd=BUILD, timeout=30)
        require(not result.returncode, (result.stdout + result.stderr).decode('utf8', errors='replace'))
        report.update(json.loads(result.stdout))
        report['inputs_after'] = [common.artifact(path) for path in paths]
        require(report['inputs_after'] == before, 'Source or pinned evidence changed during the controlled check')
        report['protected_inputs_unchanged'] = True
    except Exception as error:
        report.update(status='FAIL_RETAIL_LOCALE_ARGUMENT_DISPATCH', error=str(error))
        raise
    finally:
        removed = []
        for leaf in LEAVES:
            path = BUILD / leaf
            if not path.exists():
                continue
            info = storage.ordinary(path)
            if path.absolute().parent != BUILD.absolute() or info.st_nlink != 1:
                raise ValueError('Cleanup escaped exact unshared fixture intermediates')
            row = dict(**common.artifact(path), allocated_bytes=storage.allocated(path))
            path.unlink()
            row['result'] = 'DELETED_EXACT_OWNED_REGENERABLE_LOCALE_FIXTURE_INTERMEDIATE'
            removed.append(row)
        report['owned_intermediate_cleanup'] = removed
        with receipt.open('x', encoding='utf8') as stream:
            json.dump(report, stream, indent=2)
            stream.write('\n')
    print(json.dumps({key: report.get(key) for key in ('status', 'checks', 'protected_inputs_unchanged')}))


if __name__ == '__main__':
    main()
