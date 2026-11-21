"""Compile exact GC/context lifecycle bodies with explicitly instrumented services."""
import json
import re
from pathlib import Path
from collect_baseline import PROJECT
from native_build import build_program, environment_for, checked_run
from probe_world_builder import artifact
from build_bootstrap_component import body
from define_gc_lifecycle_patches import BASE, GLOBALS, CONTEXT, TYPES, baseline_text, type_defaults

SIGNATURES = {GLOBALS: ('void CvGlobals::init()', 'void CvGlobals::uninit()'),
              CONTEXT: ('void CvDllGameContext::Init()', 'void CvDllGameContext::Uninit()',
                        'bool CvDllGameContext::SetDLLIFace(', 'bool CvDllGameContext::ShutdownSingleton()')}


def fixtures():
    original = {r: baseline_text(r) for r in (*SIGNATURES, TYPES)}
    candidate = {r: (PROJECT/'Source/SDK_BNW_x64'/r).read_bytes().decode('latin1') for r in original}
    def functions(sources): return '\n'.join(body(sources[r],s) for r,sigs in SIGNATURES.items() for s in sigs)
    init = body(original[GLOBALS], 'void CvGlobals::init()')
    owners = re.findall(r'SAFE_DELETE\((m_\w+)\)', body(original[GLOBALS], 'void CvGlobals::uninit()'))
    if len(owners) != 38: raise RuntimeError('Expected thirty-eight direct GC cleanup pointers')
    fields = '\n'.join('    Owner* ' + f + ' = nullptr;' for f in owners)
    methods = []
    for setter in re.findall(r'\b((?:set|Set)\w+)\(FNEW\(', init):
        method = body(original[GLOBALS], 'void CvGlobals::' + setter + '(')
        field = re.search(r'(m_\w+) = pVal;', method).group(1)
        methods.append('    void '+setter+'(Owner* pVal) { '+field+' = pVal; }')
    if len(methods) != 12: raise RuntimeError('Expected twelve direct pathfinder setters')
    declarations = original[TYPES][original[TYPES].index('//Static variables'):original[TYPES].index('void CvTypes::AcquireTypes(')]
    defaults = type_defaults()
    types = declarations + '\n' + body(candidate[TYPES], 'void CvTypes::ResetTypes() noexcept')
    types += '\nvoid CorruptTypes() {\n' + '\n'.join(n+' = 42;' for n,_ in defaults) + '\n}\n'
    types += 'bool TypesAreDefaults() { return ' + ' && '.join(n+' == '+v for n,v in defaults) + '; }\n'
    types += 'bool TypesArePopulated() { return ' + ' && '.join(n+' == 42' for n,_ in defaults) + '; }\n'
    return {n:t.replace('\r\n','\n') for n,t in {
        'gc_lifecycle_fields.h': fields + '\n' + '\n'.join(methods) + '\n',
        'gc_lifecycle_types.h': types,
        'gc_lifecycle_fixture.h': '#ifdef GC_LIFECYCLE_ORIGINAL\n' + functions(original) + '\n#else\n' + functions(candidate) + '\n#endif\n'}.items()}


def main():
    out,root=PROJECT/'Build/GCLifecycle/x64',PROJECT/'evidence/gc_lifecycle'
    out.mkdir(parents=True,exist_ok=True);root.mkdir(parents=True,exist_ok=True)
    headers=[]
    for name,text in fixtures().items():
        path=out/name;path.write_text(text,encoding='utf-8',newline='\n');headers.append(artifact(path))
    vs=Path(r'C:\Program Files\Microsoft Visual Studio\2022\Community');builds={}
    for name,defines in (('original',('GC_LIFECYCLE_ORIGINAL',)),('candidate',())):
        directory=out/name
        built=build_program(name='gc_lifecycle_'+name,architecture='x64',vs=vs,directory=directory,evidence=root,
                            source=PROJECT/'Tests/sdk_gc_lifecycle.cpp',includes=(out,PROJECT/'Source/Porting'),defines=defines,runtime='/MD')
        env,compiler=environment_for(vs,'x64',directory)
        result=checked_run([Path(compiler).with_name('dumpbin.exe'),'/dependents',built['path']],cwd=directory,env=env)
        log=root/(name+'_imports.log');log.write_bytes(result.stdout+result.stderr)
        deps=re.findall(r'^\s+([\w.-]+\.dll)\s*$',result.stdout.decode('ascii',errors='replace'),re.M|re.I)
        allowed={'kernel32.dll','msvcp140.dll','vcruntime140.dll','vcruntime140_1.dll'}
        if not deps or any(d.lower() not in allowed and not d.lower().startswith('api-ms-win-crt-') for d in deps): raise RuntimeError('Unexpected lifecycle consumer import')
        builds[name]={'executable':built,'imports':{'dependencies':deps,'log':artifact(log)}}
    sources=[PROJECT/'Tests/sdk_gc_lifecycle.cpp',PROJECT/'Source/Porting/ZeroSisGlobalsLifecycle.h',PROJECT/'Source/Porting/ZeroSisHostBinding.h',
             PROJECT/'tools/define_gc_lifecycle_patches.py',PROJECT/'tools/build_bootstrap_component.py']
    report={'status':'GC_LIFECYCLE_COMPONENTS_BUILT','builds':builds,'fixtures':headers,'sources':[artifact(p) for p in sources],
            'sdk_sources':[artifact(PROJECT/'Source/SDK_BNW_x64'/r) for r in (*SIGNATURES,TYPES)],
            'baseline':artifact(BASE),'builder':artifact(Path(__file__).resolve()),'gamecore_loaded':False,'game_launched':False,
            'scope':'EXACT_GC_AND_CONTEXT_LIFECYCLE_BODIES_AND_TYPE_RESET_WITH_INSTRUMENTED_GAME_CHILDREN_HOST_AND_DATABASE'}
    (root/'build_result.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8');print(report['status'])


if __name__=='__main__': main()
