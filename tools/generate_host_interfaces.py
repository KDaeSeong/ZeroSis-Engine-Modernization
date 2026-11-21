"""Generate explicit unsupported host slots from the current frozen SDK interfaces."""
import json,re
from pathlib import Path
from collect_baseline import PROJECT
from probe_world_builder import artifact
from build_bootstrap_component import body

SPECS=(('EngineServicesBase','ICvEngineUtility4','ICvDLLUtility.h',('ICvEngineUtility1','ICvEngineUtility2','ICvEngineUtility3','ICvEngineUtility4')),
       ('UserInterfaceBase','ICvUserInterface2','ICvDLLUserInterface.h',('ICvUserInterface1','ICvUserInterface2')),
       ('ContextFixtureBase','ICvGameContext3','CvDllInterfaces.h',('ICvGameContext1',)))


def inventory():
    root=PROJECT/'Source/SDK_BNW_x64/CvGameCoreDLLUtil/include'
    result=[]
    for derived,base,file,classes in SPECS:
        sources=[root/file]
        groups=[(root/file,classes)]
        if derived=='ContextFixtureBase':groups.append((root/'CvDllInterfaces2.h',('ICvGameContext2','ICvGameContext3')));sources.append(root/'CvDllInterfaces2.h')
        methods=[]
        for path,names in groups:
            text=path.read_bytes().decode('latin1')
            for name in names:
                part=body(text,'class '+name+' :')
                part=re.sub(r'/\*.*?\*/|//[^\r\n]*','',part,flags=re.S)
                for declaration in re.findall(r'virtual\s+([^;{}]+?)\s*=\s*0\s*;',part,re.S):
                    declaration=' '.join(declaration.split()).replace('DECLSPEC_DEPRECATED ','')
                    # Preserve the exact parameter types/defaults/const/calling convention.
                    method=re.search(r'(\w+)\s*\(',declaration)
                    if not method:raise RuntimeError('Unparsed host method: '+declaration)
                    methods.append({'interface':name,'name':method[1],'declaration':declaration})
        methods[:0]=[{'interface':'ICvUnknown','name':'QueryInterface','declaration':'void* DLLCALL QueryInterface(GUID guidInterface)'},
                     {'interface':'ICvUnknown','name':'Destroy','declaration':'void DLLCALL Destroy()'}]
        result.append({'class':derived,'base':base,'sources':[artifact(p) for p in sources],'methods':methods})
    return result


def generated(rows):
    text='#pragma once\n#include "SdkHostIncludes.h"\n// Generated ABI declarations. Unsupported slots always identify and reject the call.\n#pragma warning(push)\n#pragma warning(disable:4100) // SDK parameter names are retained for review.\nnamespace ZeroSisHost {\n'
    for row in rows:
        if row['class']=='ContextFixtureBase':continue
        text+='class '+row['class']+' : public '+row['base']+' {\npublic:\n'
        for m in row['methods']:text+='    '+m['declaration']+' override { Unsupported("'+m['interface']+'::'+m['name']+'"); }\n'
        text+='};\n'
    return text+'}\n#pragma warning(pop)\n'


def main():
    rows=inventory();out=PROJECT/'Source/Host/GeneratedHostInterfaces.h';out.write_text(generated(rows),encoding='utf-8')
    fixture='#pragma once\n#pragma warning(push)\n#pragma warning(disable:4100)\nnamespace ZeroSisHost {\nclass ContextFixtureBase : public ICvGameContext3 {\npublic:\n'
    for row in rows[-1]['methods']:fixture+='    '+row['declaration']+' override { Unsupported("'+row['interface']+'::'+row['name']+'"); }\n'
    fixture+='};\n}\n#pragma warning(pop)\n'
    test=PROJECT/'Tests/host_context_fixture.h';test.write_text(fixture,encoding='utf-8')
    root=PROJECT/'evidence/host';root.mkdir(parents=True,exist_ok=True)
    report={'status':'SDK_HOST_INTERFACE_INVENTORY','generator':artifact(Path(__file__).resolve()),'generated':artifact(out),
            'context_test_fixture':artifact(test),'interfaces':rows,'scope':'SDK_COMPILE_TIME_ABI_AND_EXPLICIT_UNSUPPORTED_SLOTS_NOT_IMPLEMENTATION_COVERAGE'}
    (root/'interfaces.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'classes':[(r['class'],len(r['methods'])) for r in rows]}))


if __name__=='__main__':main()
