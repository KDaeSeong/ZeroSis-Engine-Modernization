"""Review exact asset sources and destinations before the file-only overlay."""
from __future__ import annotations
import ast
import json
from pathlib import Path
from asset_input_review import artifact, verify_ref, require, read, PROJECT, OUT, OLD, NAMES, HASHES, MAGIC, HOST, SDK


def run():
    planpath=OUT.parent/'overlay/plan.json'
    planref=artifact(planpath)
    require(planref['sha256']=='c4dc9a5c36f8fab3c333037950f79aac44d6300cf77f9c95b801652047fcfd12','Pinned overlay plan SHA differs')
    plan=read(planpath)
    root=PROJECT/'Build/InteractiveGameRuntime/20261115T134603Z_aa8853762399'
    require(plan['runtime_directory']==str(root) and plan['run_id']==root.name,'Overlay destination differs')
    require(plan['new_game_only'] and not plan['native_execution_allowed'] and not plan['default_or_registration_changed'],'Overlay isolation scope differs')
    binding=read(verify_ref(plan['compiled_asset_binding'])['path'])
    require(binding['host']['sha256']==HOST and set(plan['packages'])==set(NAMES),'Latest Host/five-role contract differs')
    baseline=read(OUT/'asset_input_review.json')
    oldinputs={row['role']:row['artifact'] for row in baseline['packages']}
    packages=[]
    for role,row in plan['packages'].items():
        source=verify_ref(row['source'])
        require(all(source[key]==oldinputs[role][key] for key in ('path','bytes','sha256','file_identity','mtime_ns','file_attributes')),'Asset source drift: '+role)
        require(source['sha256']==HASHES[role] and source['file_attributes']==32,'Asset pin or attributes differ: '+role)
        require(row['target_path']==str(root/NAMES[role]) and row['method']=='hardlink' and not row['read_only'] and row['immutability_policy']=='READ_ONLY_USE_NO_ATTRIBUTE_CHANGE','Asset link policy differs: '+role)
        require(source['file_identity'][0]==root.stat().st_dev,'Asset source volume differs')
        require(role=='terrain' or not Path(row['target_path']).exists(),'Unexpected pre-existing new asset path')
        packages.append(dict(role=role,source=source,target=row['target_path'],method='hardlink',attribute_changes=0))
    require(not (root/'WorldAssets').exists() and not (root/'sessions').exists(),'Fresh runtime already overlaid or executed')
    support=[]
    expected={'interactive_ui_support/assets/prepared.json','interactive_ui_support/assets/inline_icons.json'}
    expected.update('interactive_ui_support/tools/'+row['name'] for row in baseline['frozen_support']['tools'])
    require({row['relative_path'] for row in plan['shared_support']}==expected and len(expected)==8,'Exact eight support inputs differ')
    for row in plan['shared_support']:
        source,target=verify_ref(row['source']),verify_ref(row['target'])
        name=row['relative_path']
        require(source['path']==str(OLD/name) and target['path']==str(root/name),'Support source/destination escaped expected runtimes')
        require(source['sha256']==target['sha256'] and source['bytes']==target['bytes'] and source['file_identity']!=target['file_identity'],'Support pre-link copies differ')
        require(source['file_attributes']==target['file_attributes']==32 and target['links']==1 and row['method']=='hardlink','Support link/attribute contract differs')
        support.append(dict(relative_path=name,source=source,target_before=target,planned_method='hardlink'))
    terrain=verify_ref(plan['base_terrain'])
    require(terrain['path']==str(root/'terrain-assets.bin') and terrain['sha256']=='2bee85c22c77b0342896f827989ca7d6f4ca3ae8f4dfe3a2179faaab4d689b13','Exact superseded terrain alias differs')
    validator=verify_ref(plan['validator_source'])
    pins={}
    for node in ast.parse(Path(validator['path']).read_text('utf8')).body:
        if isinstance(node,ast.Assign) and len(node.targets)==1 and isinstance(node.targets[0],ast.Name) and node.targets[0].id in {'HOST','SDK','EXPECTED'}:
            pins[node.targets[0].id]=ast.literal_eval(node.value)
    require(pins==dict(HOST=HOST,SDK=SDK,EXPECTED={role:(NAMES[role],HASHES[role],MAGIC[role][0]) for role in NAMES}),'Validator semantic pins differ')
    adapter=verify_ref(plan['adapter_source'])
    require(plan['native_execution_allowed'] is False,'Native launch scope differs')
    return dict(schema='zerosis.phase9.asset_overlay_plan_review.v1',status='PASS_EXACT_FIVE_PACK_EIGHT_SUPPORT_FILE_ONLY_OVERLAY_PLAN',scope='NoNative0',plan=planref,
                runtime_directory=str(root),packages=packages,shared_support=support,retired_terrain_alias=terrain,validator_source=validator,adapter_source=adapter,
                validator_newline_representation_accepted=True,validator_pins_parsed_as_source_only=True,native_host_gamecore_clr_hwnd_gpu_audio_or_game_attempts=0,
                planned_new_asset_payload_copies=0,planned_original_or_donor_attribute_changes=0,ui_font_or_unit_content_changes=0,
                verifier_source=artifact(__file__))


def main():
    output=OUT/'asset_overlay_plan_review.json'
    require(not output.exists(),'Do not overwrite prior evidence')
    proof=run()
    with output.open('x',encoding='utf8') as stream:
        json.dump(proof,stream,indent=2);stream.write('\n')
    print(json.dumps(dict(status=proof['status'],scope=proof['scope'],packages=5,support=8,output=artifact(output))))


if __name__=='__main__':
    main()
