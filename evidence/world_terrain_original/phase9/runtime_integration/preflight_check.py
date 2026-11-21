"""Exercise the file-only CLI and four invalid invocations without launching native inputs."""
from contextlib import redirect_stdout
from pathlib import Path
import importlib.util,io,json,os,sys
sys.dont_write_bytecode=True
STAGE=Path(__file__).absolute().parent
PROJECT=STAGE.parents[3]
sys.path.insert(0,str(PROJECT/'tools'))
import build_exit_confirm_host as common

def main():
    result=json.loads((STAGE/'overlay/result.json').read_text('utf8'))
    root=Path(result['runtime_directory']);manifest=Path(result['asset_manifest']['path']);validator=root/'WorldAssets/verify_assets.py'
    before=[common.artifact(path)for path in(manifest,validator,root/'ZeroSisHost_x64.exe',root/'CvGameCoreDLL_Expansion2_x64.dll')]
    assert before[0]['sha256']==result['asset_manifest']['sha256']
    spec=importlib.util.spec_from_file_location('phase9_file_validator',validator);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    old=sys.argv;sys.argv=[str(validator),'--root',str(root),'--manifest',str(manifest),'--manifest-sha256',before[0]['sha256']]
    stream=io.StringIO()
    try:
        with redirect_stdout(stream):module.main()
    finally:sys.argv=old
    valid=json.loads(stream.getvalue());assert valid['status']=='PASS_FIVE_RUNTIME_PACKS_AND_ATTESTED_PAIR_FILE_ONLY'and not valid['host_or_sdk_executed']
    cases=[('wrong SHA',root,manifest,'0'*64),('malformed SHA',root,manifest,'bad'),
        ('manifest path outside fixed location',root,root/'assets.manifest.json',before[0]['sha256']),
        ('invalid runtime identity',root.parent/'invalid-runtime',root.parent/'invalid-runtime/WorldAssets/assets.manifest.json',before[0]['sha256'])]
    rejections=[]
    for name,base,path,digest in cases:
        try:module.verify(base,path,digest)
        except ValueError as error:rejections.append(dict(case=name,error=str(error)))
        else:raise AssertionError('Invalid invocation accepted: '+name)
    assert before==[common.artifact(row['path'])for row in before]
    value=dict(status='PASS_ACTUAL_FILE_ONLY_PREFLIGHT_AND_FOUR_REJECTIONS',validator=before[1],asset_manifest=before[0],
        observed_valid_cli_status=valid['status'],negative_cases=rejections,rejections=len(rejections),
        native_host_sdk_clr_hwnd_gpu_audio_or_game_executed=False,source_or_runtime_files_modified=False)
    target=STAGE/'overlay/preflight_verification.json'
    with target.open('x',encoding='utf8')as f:json.dump(value,f,indent=2);f.write('\n')
    print(json.dumps(dict(status=value['status'],packages=5,rejections=len(rejections),native_attempts=0)))

if __name__=='__main__':main()
