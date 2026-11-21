"""Independent file-backed review of a completed ExitConfirm Host build."""
import argparse
import ast
import hashlib
import json
from pathlib import Path
import re
import stat
import sys
import types

STAGE=Path(__file__).resolve().parent
PROJECT=STAGE.parents[2]
PARSER_SHA='723e8d4594ce148336149f34c2ee535512c14ad283165b4fd729473eb302123f'
HELPER_SHA='07f50b1ab7482591792b44cc8767f27c709884f5f487b0eada7459f28c8da558'
MARKER=b'NATIVE_RESTORE_CONTRACT_VERIFIED=SOURCE_ORDER_V1|'


def key(value):
    return str(Path(value).absolute()).casefold()


def artifact(path):
    path=Path(path);raw=path.read_bytes();info=path.stat()
    assert info.st_ino and not info.st_file_attributes&0x400
    return dict(path=str(path),bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())


def sealed(row):
    actual=artifact(row['path'])
    assert actual['bytes']==row['bytes'] and actual['sha256']==row['sha256'], row['path']
    return Path(row['path']).read_bytes()


def pure(path,expected,name):
    raw=Path(path).read_bytes();assert hashlib.sha256(raw).hexdigest()==expected
    module=types.ModuleType(name);module.__file__=str(path);sys.modules[name]=module
    exec(compile(raw,str(path),'exec'),module.__dict__)
    return module


def parse69(parser,raw):
    source=Path(parser.__file__).read_text(encoding='utf-8-sig')
    tree=ast.parse(source)
    node=next(item for item in tree.body if isinstance(item,ast.FunctionDef) and item.name=='parse_catalog')
    original=ast.dump(node,include_attributes=False)
    class ExactCount(ast.NodeTransformer):
        count=0
        def visit_Constant(self,item):
            if type(item.value) is int and item.value==67:
                self.count+=1
                return ast.copy_location(ast.Constant(69),item)
            return item
    change=ExactCount();node=change.visit(node);assert change.count==1
    namespace=dict(parser.__dict__)
    exec(compile(ast.fix_missing_locations(ast.Module(body=[node],type_ignores=[])),'<independent-exact69-adapter>','exec'),namespace)
    arrays,order=namespace['parse_catalog'](raw)
    assert len(arrays)==len(order)==69 and {'ExitConfirm','ExitConfirmLayout'}<=set(order)
    return arrays,order,dict(original_module_sha256=PARSER_SHA,adapted_integer_count=1,old_count=67,new_count=69,
                             original_function_ast_sha256=hashlib.sha256(original.encode()).hexdigest())


def main():
    cli=argparse.ArgumentParser(description=__doc__);cli.add_argument('--report',type=Path,required=True)
    options=cli.parse_args();assert sys.dont_write_bytecode
    report=json.loads(options.report.read_bytes());assert report['status']=='UI_WINDOW_HOST_CANDIDATE_BUILT'
    identifier=report['build_id'];root=PROJECT/'Build/UiWindowHost'/identifier
    parent=json.loads(sealed(report['baseline_build']));parent_root=PROJECT/'Build/UiWindowHost'/parent['build_id']
    assert parent['build_id']=='20261024T082423Z_b604cddf0d2d'
    parser=pure(PROJECT/'evidence/goody_hut/owned_fonts/verify_candidate.py',PARSER_SHA,'exit_independent_pe')
    helper=pure(PROJECT/'tools/build_native_restore_host.py',HELPER_SHA,'exit_independent_build_helpers')
    header=PROJECT/'Source/Host/UiPopupAssets.generated.h'
    arrays,order,adapter=parse69(parser,header.read_bytes())
    old_header=next(row for row in parent['compiler_inputs'] if key(row['original_path'])==key(header))
    old_arrays,old_order=parser.parse_catalog(sealed(old_header))
    assert [name for name in order if name not in ('ExitConfirm','ExitConfirmLayout')]==old_order
    assert [name for name in old_order if old_arrays[name]!=arrays[name]]==['ZeroSisUiScene']
    assert arrays['ExitConfirm']==(PROJECT/'Source/Assets/UI/Assets/UI/FrontEnd/ExitConfirm.lua').read_bytes()
    scene=(PROJECT/'Source/Host/UiScene.lua').read_bytes()+b'\n'+(PROJECT/'Source/Presentation/UiPresentationInput.lua').read_bytes()
    for flag,name in [('hasRetainedCityUi','UiCityView.lua'),('hasRetainedUnitUi','UiUnitPanel.lua'),
                      ('hasRetainedSocialPolicyUi','UiSocialPolicy.lua'),('hasRetainedEconomicUi','UiEconomicOverview.lua'),
                      ('hasRetainedActionInfoUi','UiActionInfoPanel.lua'),('hasRetainedNotificationUi','UiNotificationPanel.lua')]:
        scene+=b'\nif '+flag.encode()+b' then\n'+(PROJECT/'Source/Presentation'/name).read_bytes()+b'\nend\n'
    assert scene==arrays['ZeroSisUiScene']
    for name in ['ProductionCommandGuard','ResearchCommandGuard']:
        assert arrays[name]==(PROJECT/'Source/Host'/(name+'.lua')).read_bytes()
    image=sealed(report['executable']);pe=parser.PE(image)
    catalog=helper.catalog_summary(pe.catalog(arrays,order));assert catalog==report['catalog']
    assert catalog['entry_count']==69
    imports=pe.imports();assert set(imports)==set(parent['imports']['dependencies'])==set(report['imports']['dependencies'])
    assert len(imports)==24 and len(pe.occurrences(MARKER))==1
    actual_rows={}
    for group in ['compiler_inputs','sources','provider_inputs','system_libraries','implicit_libraries','build_tools']:
        for row in report[group]:
            sealed(row);assert Path(row['path']).is_relative_to(root)
            actual_rows[key(row['path'])]=row
    for row in [*report['provider_reports'].values(),report['shared_lua_build'],report['ui_assets']]:
        sealed(row);assert Path(row['path']).is_relative_to(root);actual_rows[key(row['path'])]=row
    assert len(actual_rows)==len(report['current_source_inputs'])==601
    for row in report['current_source_inputs']:
        sealed(row)
    compiler={key(row['path']) for row in report['compiler_inputs']};union=set()
    assert len(compiler)==550 and len(report['sources'])==88 and len(report['build_tools'])==8
    counts=[];object_names=[]
    for current,prior in zip(report['final_compilation']['translation_units'],parent['final_compilation']['translation_units']):
        assert current['translation_unit']==prior['translation_unit']
        sealed(current['response']);sealed(current['log'])
        assert current['returncode']==0
        data=json.loads(sealed(current['dependency_report']).decode('utf-8-sig'))['Data']
        paths={key(value) for value in [data['Source'],*data['Includes']]}
        old=json.loads(sealed(prior['dependency_report']).decode('utf-8-sig'))['Data']
        expected={key(root/Path(value).relative_to(parent_root)) for value in [old['Source'],*old['Includes']]}
        assert paths==expected and not paths-compiler
        counts.append(len(paths));union.update(paths)
        raw=sealed(current['object']);parser.coff(raw)
        assert helper.object_defaults(raw)==prior['default_libraries']==current['default_libraries']
        object_names.append(current['object']['path'])
    assert counts==[466,266,270,279,301] and union==compiler
    link=sealed(report['link_response']).decode('utf-8-sig')
    linked_objects=[key(value) for value in re.findall(r'"([^"\r\n]+\.obj)"',link,re.I)]
    assert len(linked_objects)==5 and set(linked_objects)=={key(value) for value in object_names}
    assert str(parent_root) not in link and parent_root.as_posix() not in link
    sealed(report['link_log']);sealed(report['map']);sealed(report['started'])
    assert report['source_inputs_unchanged'] and report['provider_inputs_unchanged']
    for name in ['host_runtime_executed','gamecore_loaded','sdk_linked','mods_updated','stage_updated','default_promoted','sdk_restore_verified','native_restore_approved','full_engine_goal_complete']:
        assert report[name] is False,name
    reuse=report['frozen_input_reuse'];assert (reuse['hardlinked_files'],reuse['copied_files'])==(585,16)
    result=dict(schema='zerosis.exit_host_build.independent_attestation.v1',status='PASS_INDEPENDENT_CURRENT_EXIT_HOST_BYTES_AND_INPUTS',
                build_result=artifact(options.report),image=artifact(report['executable']['path']),header=artifact(header),
                catalog=catalog,catalog_parser_adapter=adapter,imports=imports,restore_marker_readonly_occurrences=1,
                unchanged_prior_payloads=66,current_scene_exact_all_eight_files=True,original_exit_script_exact_raw=True,
                actual_tu_dependency_counts=counts,compiler_input_count=550,frozen_input_count=601,current_input_count=601,
                code_objects_checked=5,hardlinked_files=585,private_copies=16,
                host_or_sdk_or_dll_or_window_execution=False,full_native_or_original_ui_acceptance=False)
    path=STAGE/'independent_attestation.json';assert not path.exists()
    path.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({key:result[key] for key in ['status','build_result','compiler_input_count','frozen_input_count']}))


if __name__=='__main__':
    main()
