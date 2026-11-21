"""Run only the pinned Python file verifier, with native/write operations denied."""
from pathlib import Path
from contextlib import redirect_stdout
import importlib.util,io,json,sys
sys.dont_write_bytecode=True
STAGE=Path(__file__).absolute().parent
PROJECT=STAGE.parents[3]
sys.path.insert(0,str(PROJECT/'tools'))
import build_exit_confirm_host as common

def main():
    result=json.loads((STAGE/'overlay/result.json').read_text('utf8'))
    assert common.artifact(STAGE/'overlay/result.json')['sha256']=='5dd86bd8ac3717b38004e0dc7ceba92aa535c2fbe2b8eac9173dbf3452294abf'
    root=Path(result['runtime_directory']);manifest=Path(result['asset_manifest']['path'])
    validator=Path(result['validator']['path']);assert common.artifact(validator)['sha256']==result['validator']['sha256']
    before=[common.artifact(path) for path in (validator,manifest,root/'Play.ps1',Path(result['request']['path']))]
    native=[]
    def boundary(event,args):
        if event.startswith(('subprocess.','socket.','winreg.')) or event in ('os.system','os.startfile','ctypes.dlopen'):
            native.append(event);raise PermissionError('Only Python file verification is authorized')
        if event=='open':
            mode,flags=args[1],args[2]
            writing=(isinstance(mode,str) and any(c in mode for c in 'wax+')) or (isinstance(flags,int) and flags&0x40b)
            if writing:
                path=Path(args[0]).absolute()
                if path!=STAGE/'preflight_verification.json':raise PermissionError('No runtime or input writes are authorized')
        if event in ('os.chmod','os.utime','os.link','os.remove','os.rmdir','os.mkdir','os.rename','os.replace'):
            raise PermissionError('File mutation is not authorized during preflight validation')
    spec=importlib.util.spec_from_file_location('_pinned_six_pack_file_preflight',validator)
    module=importlib.util.module_from_spec(spec)
    sys.addaudithook(boundary);spec.loader.exec_module(module)
    valid=module.verify(root,manifest,result['asset_manifest']['sha256'])
    assert valid['packages']==6 and valid['host_or_sdk_executed'] is False
    old_argv=sys.argv
    sys.argv=[str(validator),'--root',str(root),'--manifest',str(manifest),'--manifest-sha256',result['asset_manifest']['sha256']]
    capture=io.StringIO()
    try:
        with redirect_stdout(capture):module.main()
    finally:sys.argv=old_argv
    assert json.loads(capture.getvalue())['packages']==6
    rejected=[]
    for name,args in (
        ('wrong_manifest_pin',(root,manifest,'0'*64)),
        ('missing_complete_pin',(root,manifest,'abcd')),
        ('manifest_path_outside_binding',(root,root/'bundle.manifest',result['asset_manifest']['sha256'])),
        ('different_runtime_identity',(root.parent,manifest,result['asset_manifest']['sha256']))):
        try:module.verify(*args)
        except ValueError:rejected.append(name)
        else:raise AssertionError('Invalid preflight input was accepted: '+name)
    assert len(rejected)==4 and not native
    assert all(common.artifact(row['path'])==row for row in before)
    with (STAGE/'preflight_verification.json').open('x',encoding='utf8') as stream:
        json.dump(dict(status='PASS_PINNED_SIX_PACK_PREFLIGHT_FUNCTION_AND_CLI',run_id=result['run_id'],
            result=common.artifact(STAGE/'overlay/result.json'),validator=before[0],passed=valid,rejected=rejected,
            native_attempts=0,runtime_or_source_writes=0,protected_controls=before),stream,indent=2)
        stream.write('\n')
    print(json.dumps(dict(status='PASS_PINNED_SIX_PACK_PREFLIGHT_FUNCTION_AND_CLI',rejected=len(rejected),native_attempts=0)))

if __name__=='__main__':main()
