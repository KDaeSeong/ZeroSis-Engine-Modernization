"""Extract actual SDK ownership callers and release dispatch into isolated tests."""
import json
import re
from pathlib import Path
from collect_baseline import PROJECT
from native_build import build_program, environment_for, checked_run
from probe_world_builder import artifact
from build_bootstrap_component import body
from define_host_binding_patches import BASE, CONTEXT, DLL, baseline_text, patches

UNKNOWN = 'CvGameCoreDLLUtil/include/CvDllInterfaces.h'
UTILITY = 'CvGameCoreDLLUtil/include/ICvDLLUtility.h'
SIGNATURES = {CONTEXT: ('bool CvDllGameContext::SetDLLIFace(', 'bool CvDllGameContext::ShutdownSingleton()'),
              DLL: ('bool DestroyContext() noexcept override',)}


def fixtures():
    original = {name: baseline_text(name) for name in SIGNATURES}
    candidate = {name: (PROJECT / 'Source/SDK_BNW_x64' / name).read_bytes().decode('latin1') for name in SIGNATURES}
    def callers(sources):
        return '\n'.join(body(sources[CONTEXT], sig) for sig in SIGNATURES[CONTEXT]) + '\nstruct Backend final : BackendBase {\n' + body(sources[DLL], SIGNATURES[DLL][0]) + '\n};\n'
    fixture = '#ifdef HOST_BINDING_ORIGINAL\n' + callers(original) + '\n#else\n' + callers(candidate) + '\n#endif\n'
    unknown, utility = baseline_text(UNKNOWN), baseline_text(UTILITY)
    abi = body(unknown, 'static const GUID guidICvUnknown =') + ';\n'
    abi += body(utility, 'static const GUID guidICvEngineUtility4 =') + ';\n'
    # Start after the forward declarations. Preserve the actual release dispatcher.
    abi += body(unknown, 'class ICvUnknown\r\n{') + ';\n'
    return {name: text.replace('\r\n', '\n') for name, text in {
        'host_binding_fixture.h': fixture, 'host_binding_abi.h': abi}.items()}


def main():
    out, root = PROJECT / 'Build/HostBinding/x64', PROJECT / 'evidence/host_binding'
    out.mkdir(parents=True, exist_ok=True)
    root.mkdir(parents=True, exist_ok=True)
    headers = []
    for name, text in fixtures().items():
        path = out / name
        path.write_text(text, encoding='utf-8', newline='\n')
        headers.append(artifact(path))
    vs = Path(r'C:\Program Files\Microsoft Visual Studio\2022\Community')
    builds = {}
    for name, defines in (('original', ('HOST_BINDING_ORIGINAL',)), ('candidate', ())):
        directory = out / name
        built = build_program(name='host_binding_' + name, architecture='x64', vs=vs, directory=directory,
                              evidence=root, source=PROJECT / 'Tests/sdk_host_binding.cpp',
                              includes=(out, PROJECT / 'Source/Porting'), defines=defines, runtime='/MD')
        env, compiler = environment_for(vs, 'x64', directory)
        result = checked_run([Path(compiler).with_name('dumpbin.exe'), '/dependents', built['path']], cwd=directory, env=env)
        log = root / (name + '_imports.log')
        log.write_bytes(result.stdout + result.stderr)
        deps = re.findall(r'^\s+([\w.-]+\.dll)\s*$', result.stdout.decode('ascii', errors='replace'), re.M | re.I)
        allowed = {'kernel32.dll', 'msvcp140.dll', 'vcruntime140.dll', 'vcruntime140_1.dll'}
        if not deps or any(d.lower() not in allowed and not d.lower().startswith('api-ms-win-crt-') for d in deps):
            raise RuntimeError('Unexpected host binding test import')
        builds[name] = {'executable': built, 'imports': {'dependencies': deps, 'log': artifact(log)}}
    sources = ['Tests/sdk_host_binding.cpp', 'Source/Porting/ZeroSisHostBinding.h', 'Source/Porting/ZeroSisGlobalsLifecycle.h',
               'tools/define_host_binding_patches.py', 'tools/build_bootstrap_component.py', 'tools/native_build.py']
    sources += ['Source/SDK_BNW_x64/' + name for name in SIGNATURES]
    sources += ['Source/SDK_BNW_Original/' + name for name in (*SIGNATURES, UNKNOWN, UTILITY)]
    report = {'status': 'HOST_BINDING_COMPONENTS_BUILT', 'builds': builds, 'fixtures': headers,
              'sources': [artifact(PROJECT / p) for p in sources], 'baseline': artifact(BASE),
              'builder': artifact(Path(__file__).resolve()), 'gamecore_loaded': False, 'game_launched': False,
              'scope': 'EXACT_SDK_BINDING_SHUTDOWN_AND_ICVUNKNOWN_DISPATCH_WITH_INSTRUMENTED_HOST_AND_CONTEXT'}
    (root / 'build_result.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(report['status'])


if __name__ == '__main__':
    main()
