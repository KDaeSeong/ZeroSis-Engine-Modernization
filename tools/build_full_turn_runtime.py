"""Build the real BNW SDK, shared workers, providers and headless Host in a private build tree."""
import argparse
import json
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

from collect_baseline import PROJECT as root, digest, pe_header
from verify_found_value_shared_bridge import initialize_msvc
from prepare_current_sdk_runtime import SAVE_IDS, apply_patches
import define_new_game_patches as new_game
import build_found_value_shared_sdk_candidate as found
import build_explore_sdk_candidate as explore
import build_city_site_sdk_candidate as city

build = root / 'Build/FullTurnBenchmark'
source = root / 'Source'
sdk = source / 'SDK_BNW_x64'
game = sdk / 'CvGameCoreDLL_Expansion2'
overlay = build / 'sdk_overlay'
modules = build / 'modules'
cl: Path
link: Path
env: dict
includes = [overlay, game, source/'Concurrency', source/'Diagnostics', source/'Porting', source/'LuaBorrowed']
includes += [sdk/p for p in ['CvWorldBuilderMap/include','CvGameCoreDLLUtil/include','CvLocalization/include',
            'CvGameDatabase/include','FirePlace/include','FirePlace/include/FireWorks','ThirdPartyLibs/Lua51/include']]
flags = ['/nologo','/c','/std:c++14','/EHsc','/MD','/O2','/fp:strict','/bigobj','/W3','/FC',
         '/DFXS_IS_DLL','/DWIN32','/DNDEBUG','/D_WINDOWS','/D_USRDLL','/DCVGAMECOREDLL_EXPORTS',
         '/DFINAL_RELEASE','/D_CRT_SECURE_NO_WARNINGS','/D_SILENCE_STDEXT_HASH_DEPRECATION_WARNINGS']

def command(folder, name, tool, args):
    folder.mkdir(parents=True,exist_ok=True)
    response = folder/(name+'.rsp')
    response.write_text(subprocess.list2cmdline([str(v) for v in args]),encoding='utf8')
    log = folder/(name+'.log')
    with log.open('wb') as stream:
        result = subprocess.run([str(tool), '@'+str(response)], env=env, cwd=folder, stdout=stream,
                                stderr=subprocess.STDOUT, creationflags=subprocess.CREATE_NO_WINDOW)
    if result.returncode:
        lines = log.read_text(encoding='mbcs',errors='replace').splitlines()
        raise RuntimeError(name + '\n' + '\n'.join(([l for l in lines if 'error' in l.lower()] or lines)[-18:]))
    print(name,'ok',flush=True)

def core_objects():
    manifest=json.loads((root/'patches/sdk-bnw-inputs.json').read_bytes())
    for key, tree in [('baseline',source/'SDK_BNW_Original'),('modified',sdk)]:
        rows=manifest[key]
        if len(rows)!=1105 or any(digest(tree/r['path'])!=r['sha256'] for r in rows):
            raise RuntimeError('Restored SDK manifest mismatch: '+key)
    overlay.mkdir(exist_ok=True)
    # Replay the checked-in port, then require byte equality with the restored
    # two actual SDK units before applying the independent new-game recipe.
    new_game.BASE=source/'Porting/sdk_x64_patches.json'
    for name in (new_game.GAME, new_game.MAP_GENERATOR):
        if new_game.baseline_text(name).encode('latin1') != (sdk/name).read_bytes():
            raise ValueError('New-game recipe baseline differs: '+name)
    patches=new_game.patches()
    initializers=[r for r in json.loads((source/'Porting/save_restore_patches.json').read_bytes())['patches'] if r['id'] in SAVE_IDS]
    if len(patches)!=18 or len(initializers)!=5: raise RuntimeError('Unexpected SDK overlay')
    replacements = patches + initializers
    overlay_units = set()
    for rel in sorted({row['file'] for row in replacements}):
        name = Path(rel).name
        rows = [row for row in replacements if row['file'] == rel]
        (overlay/name).write_bytes(apply_patches((sdk/rel).read_bytes(), rows))
        overlay_units.add(name)
    transforms = {
        'CvPlayerAI.cpp': found.prepare_player,
        'CvSiteEvaluationClasses.h': found.prepare_header,
        'CvCitySpecializationAI.cpp': city.prepare_source,
        'CvEconomicAI.cpp': lambda data: explore.prepare_economic_source(data.decode('latin1')).encode('latin1'),
        'CvSiteEvaluationClasses.cpp': lambda data: data + b'\n#include "FoundValueSharedSdkCapture.inc"\n',
    }
    for name, transform in transforms.items():
        (overlay/name).write_bytes(transform((game/name).read_bytes()))
        overlay_units.add(name)
    for name in ('CvGameCoreDLLPCH.h','_precompile.cpp'):
        shutil.copyfile(game/name,overlay/name)
    folder=build/'core_obj'
    names=sdk_unit_names()
    sources=[(overlay/name if name in overlay_units else game/name) for name in names if name!='_precompile.cpp']
    args=flags+['/I'+str(i) for i in includes]+['/Fp'+str(folder/'game.pch'),'/Fo'+str(folder)+'/']
    command(folder,'pch',cl,args+['/YcCvGameCoreDLLPCH.h',overlay/'_precompile.cpp'])
    # Use the exact same physical PCH header with the overlay class declaration in all units.
    command(folder,'units',cl,args+['/YuCvGameCoreDLLPCH.h','/MP4',*sources])
    command(folder,'bridges',cl,[f.replace('/std:c++14','/std:c++17') for f in flags]+['/I'+str(i) for i in includes]+['/MP4','/Fo'+str(folder)+'/',*bridge_sources()])


def sdk_unit_names():
    project = ET.parse(game/'CvGameCoreDLL_Expansion2.vs2013.vcxproj')
    names = [node.attrib['Include'] for node in project.findall('.//{*}ClCompile[@Include]')]
    if len(names) != 161 or len({Path(name).stem.casefold() for name in names}) != len(names):
        raise ValueError('Unexpected BNW translation unit set')
    return names


def bridge_sources():
    names = ('ExploreScoreBridge.cpp', 'CitySiteScoreBridge.cpp', 'FoundValueSharedBridge.cpp')
    return [source/'Concurrency'/name for name in names] + [source/'Diagnostics/CitySiteCpuTrace.cpp']

def provider_objects():
    folder=build/'provider_obj'
    provider=source/'Providers'
    cpp=[p for p in sorted(provider.glob('*/*.cpp')) if p.parent.name not in ('Database','Localization')]
    dirs=includes+[p for p in provider.iterdir() if p.is_dir()]+[source/'Lua51_x64/src',sdk/'FirePlace/include/FireWorks/Flua/include']
    command(folder,'providers',cl,flags+['/MP4','/Gy','/Gw','/Fo'+str(folder)+'/']+['/I'+str(i) for i in dirs]+cpp)
    objects = [folder/(p.stem+'.obj') for p in cpp]
    command(folder,'library',cl.with_name('lib.exe'),['/nologo','/MACHINE:X64','/Brepro','/OUT:'+str(folder/'providers.lib'),*sorted(objects)])

def lua_dll():
    folder=build/'lua_obj'
    lua=source/'Lua51_x64/src'
    sources=[(source/'SharedLua/ldo.c' if p.name=='ldo.c' else p) for p in sorted(lua.glob('*.c')) if p.name not in ('lua.c','luac.c','print.c')]
    command(folder,'lua',cl,['/nologo','/c','/TC','/MP4','/O2','/MD','/fp:strict','/W3','/WX','/D_CRT_SECURE_NO_WARNINGS','/DLUA_BUILD_AS_DLL','/I'+str(lua),'/Fo'+str(folder)+'/',*sources])
    command(folder,'callback',cl,['/nologo','/c','/EHsc','/std:c++14','/O2','/MD','/DLUA_BUILD_AS_DLL','/DLUA_CORE','/I'+str(lua),source/'SharedLua/ZeroSisLuaCallback.cpp'])
    objects = [folder/(p.stem+'.obj') for p in sources] + [folder/'ZeroSisLuaCallback.obj']
    command(folder,'lua-link',link,['/NOLOGO','/DLL','/MACHINE:X64','/INCREMENTAL:NO','/Brepro','/OUT:'+str(modules/'ZeroSisLua51_x64.dll'),'/IMPLIB:'+str(folder/'lua.lib'),*sorted(objects),'kernel32.lib','user32.lib'])

def libraries():
    return [build/'provider_obj/providers.lib',root/'Build/Database/x64/ZeroSisDatabase_x64.lib',
            root/'Build/Localization/provider_x64/ZeroSisLocalization_x64.lib',build/'lua_obj/lua.lib']

def link_core():
    from link_current_sdk_base import PLATFORM
    folder=build/'core_obj'
    objects=sorted(folder/(Path(p).stem+'.obj') for p in [*sdk_unit_names(),*bridge_sources()])
    if any(not p.is_file() for p in objects):
        raise ValueError('Incomplete current SDK and shared bridge object set')
    command(folder,'core-link',link,['/nologo','/DLL','/MACHINE:X64','/INCREMENTAL:NO','/Brepro','/OPT:REF','/OPT:ICF',
        '/DEF:'+str(game/'CvGameCoreDLL.def'),'/MAP:'+str(folder/'gamecore.map'),'/OUT:'+str(modules/'CvGameCoreDLL_Expansion2_x64.dll'),
        '/IMPLIB:'+str(folder/'gamecore.lib'),*objects,*libraries(),*PLATFORM])

def host():
    folder=build/'host_obj'
    sdk_includes=[i for i in includes if i not in (overlay,source/'Concurrency',source/'Diagnostics')]
    command(folder,'host-compile',cl,['/nologo','/c','/std:c++14','/EHsc','/MD','/fp:strict','/O2','/W4','/WX',
        '/DWIN32','/DNDEBUG','/DFINAL_RELEASE','/DLUA_BUILD_AS_DLL','/DZEROSIS_SHARED_LUA_RUNTIME=1',
        '/DZEROSIS_HEADLESS_TURN_HOST=1','/DZEROSIS_NEW_GAME_TRACE=1','/D_CRT_SECURE_NO_WARNINGS',
        '/D_SILENCE_STDEXT_HASH_DEPRECATION_WARNINGS','/D_SILENCE_TR1_NAMESPACE_DEPRECATION_WARNING',
        '/source-charset:windows-1252','/external:W0', *['/external:I'+str(i) for i in sdk_includes],
        '/I'+str(source/'Host'),'/I'+str(source/'Porting'),'/Fo'+str(folder)+'/','/sourceDependencies',
        str(folder/'compiler-inputs.json'),source/'Host/HostMain.cpp'])
    command(folder,'host-link',link,['/nologo','/MACHINE:X64','/INCREMENTAL:NO','/Brepro','/OPT:REF','/OPT:ICF',
        '/OUT:'+str(modules/'ZeroSisHost_x64.exe'),folder/'HostMain.obj',*libraries(),'kernel32.lib','bcrypt.lib','user32.lib','advapi32.lib'])

def dependencies(icu_data):
    if icu_data is None:
        raise ValueError('Pass --icu-data with the installed Locale/icudt44l.dat')
    vs=Path(r'C:\Program Files\Microsoft Visual Studio\2022\Community')
    for name, arguments in (
        ('build_database_provider.py', ['--vs', str(vs)]),
        ('fetch_icu44_source.py', []), ('build_icu44.py', []), ('build_localization_icu.py', []),
        ('build_localization_provider.py', ['--icu-data', str(icu_data.resolve(strict=True))])
    ):
        subprocess.run([sys.executable,root/'tools'/name,*arguments],cwd=root,check=True)


def publish_modules():
    for folder, name in ((root/'Build/Database/x64','ZeroSisDatabase_x64.dll'),
                         (root/'Build/Localization/provider_x64','ZeroSisLocalization_x64.dll')):
        shutil.copyfile(folder/name,modules/name)
        if digest(folder/name)!=digest(modules/name):
            raise RuntimeError('Provider copy mismatch: '+name)
    names=('ZeroSisHost_x64.exe','CvGameCoreDLL_Expansion2_x64.dll','ZeroSisDatabase_x64.dll',
           'ZeroSisLocalization_x64.dll','ZeroSisLua51_x64.dll')
    files={name:{'sha256':digest(modules/name),'pe':pe_header(modules/name)} for name in names}
    if any(row['pe']['architecture']!='x64' for row in files.values()):
        raise RuntimeError('Non-x64 module in benchmark runtime')
    core_units = sdk_unit_names()
    bridges = bridge_sources()
    obj = build/'core_obj'
    objects = [obj/(Path(item).stem+'.obj') for item in [*core_units, *bridges]]
    if any(not p.is_file() for p in objects):
        raise ValueError('Cannot publish an incomplete SDK object set')
    recipes = [obj/(n+'.rsp') for n in ('pch','units','bridges','core-link')]
    recipes += [build/'host_obj'/(n+'.rsp') for n in ('host-compile','host-link')]
    report=dict(status='HEADLESS_RUNTIME_LINKED',compiler=str(cl),compiler_sha256=digest(cl),flags=flags,
                modules=files,sdk_objects=len(core_units),shared_bridge_objects=len(bridges),
                object_sha256={p.name:digest(p) for p in objects},
                compiler_response_sha256={str(p.relative_to(build)):digest(p) for p in recipes},
                overlay_sha256={p.name:digest(p) for p in sorted(overlay.iterdir()) if p.is_file()},
                gamecore_map_sha256=digest(build/'core_obj/gamecore.map'),
                host_dependencies=json.loads((build/'host_obj/compiler-inputs.json').read_text(encoding='utf-8-sig'))['Data'])
    (build/'runtime_build.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf8')


def main():
    global cl,link,env
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('phase',nargs='?',choices=('all','dependencies','core','providers','lua','link','host','publish'),default='all')
    parser.add_argument('--icu-data',type=Path)
    args=parser.parse_args()
    modules.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(dir=build) as envdir:
        cl,link,env=initialize_msvc(Path(envdir)/'vs')
    env['VSLANG']='1033'
    for key in ('CL','_CL_','LINK','_LINK_'):
        env.pop(key,None)
    phases={'dependencies':lambda:dependencies(args.icu_data),'core':core_objects,'providers':provider_objects,
            'lua':lua_dll,'link':link_core,'host':host,'publish':publish_modules}
    for name in phases if args.phase=='all' else [args.phase]:
        phases[name]()


if __name__=='__main__':
    main()
