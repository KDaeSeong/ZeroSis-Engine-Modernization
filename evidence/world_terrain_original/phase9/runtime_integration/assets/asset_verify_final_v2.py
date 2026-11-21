"""Independent file-only audit of the phase8 isolated runtime asset overlay.

Never executes a launcher, Host, SDK, CLR, shader, audio or renderer. Root's
WorldAssets verifier is parsed as source and is not imported or executed.
"""
from __future__ import annotations
import argparse
import ast
import base64
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
import struct

PROJECT=Path(__file__).absolute().parents[5]
EVIDENCE=Path(__file__).absolute().parent
OLD=PROJECT/'Build/InteractiveGameRuntime/20261115T101941Z_99b3c393ee9a'
NAMES={'terrain':'terrain-assets.bin','fog':'WorldAssets/fog-assets.bin','water':'WorldAssets/water-assets.bin',
       'lean':'WorldAssets/water-lean-assets.bin','lighting':'WorldAssets/lighting-assets.bin'}
MAGIC={'terrain':(b'ZSTERR02',2),'fog':(b'ZSFOG001',1),'water':(b'ZSWATER1',1),'lean':(b'ZSWLEAN1',1),'lighting':(b'ZSLIGHT1',1)}
ENV={'fog':'ZEROSIS_FOG_ASSETS','water':'ZEROSIS_WATER_ASSETS','lean':'ZEROSIS_WATER_SURFACE_ASSETS','lighting':'ZEROSIS_LIGHTING_ASSETS'}
MANAGED={'Firaxis.Framework.dll','Firaxis.Framework.Granny.dll','Firaxis.Framework.FirePlace.dll'}
CHECKS=[]

def require(value,message):
    if not value:raise ValueError(message)

def canonical(path):
    path=Path(path).absolute();require('..'not in path.parts,'Noncanonical path')
    for part in(path,*path.parents):
        info=part.lstat();require(not stat.S_ISLNK(info.st_mode)and not getattr(info,'st_file_attributes',0)&0x400,'Reparse path:'+str(part))
    require(path.resolve()==path,'Resolved path differs');return path

def artifact(path):
    path=canonical(path);before=path.stat();require(stat.S_ISREG(before.st_mode),'Not ordinary file:'+str(path));h=hashlib.sha256()
    with path.open('rb')as stream:
        for raw in iter(lambda:stream.read(1024*1024),b''):h.update(raw)
    after=path.stat();require((before.st_dev,before.st_ino,before.st_size,before.st_mtime_ns)==(after.st_dev,after.st_ino,after.st_size,after.st_mtime_ns),'File changed while read')
    return dict(path=str(path),bytes=before.st_size,sha256=h.hexdigest(),file_identity=[before.st_dev,before.st_ino],mtime_ns=before.st_mtime_ns,
        file_attributes=getattr(before,'st_file_attributes',0),links=before.st_nlink)

def rowref(row):
    require(isinstance(row,dict),'Expected artifact dictionary');return row['artifact']if'path'not in row and'artifact'in row else row

def verify_ref(row):
    row=rowref(row);actual=artifact(row['path'])
    for key in('bytes','sha256','file_identity','mtime_ns','file_attributes'):
        if key in row:require(actual[key]==row[key],'Reference '+key+' mismatch:'+row['path'])
    return actual

def load(path):
    row=artifact(path);require(row['bytes']<=8*1024*1024,'Unbounded JSON');return json.loads(Path(row['path']).read_text('utf8')),row

def read_json(path):
    return load(path)[0]


def pick(data,*names):
    values=[data[n]for n in names if n in data];require(values,'Missing field:'+','.join(names));return values[0]

def local(root,relative):
    require(isinstance(relative,str)and relative.replace('\\','/')==relative and not relative.startswith('/')and ':'not in relative and'..'not in Path(relative).parts,'Unsafe relative asset path')
    path=canonical(root/relative);require(path.is_relative_to(root),'Asset escaped bundle');return path

def passed(name,**detail):CHECKS.append(dict(name=name,status='PASS',**detail))

def pe(path,managed=False,dll=True):
    row=artifact(path)
    with Path(path).open('rb')as f:
        dos=f.read(64);require(len(dos)==64 and dos[:2]==b'MZ','PE DOS header');at=struct.unpack_from('<I',dos,60)[0]
        require(64<=at<=row['bytes']-264 and at<=1024*1024,'PE offset bound');f.seek(at);head=f.read(24);require(head[:4]==b'PE\0\0','PE signature')
        machine,sections,_,_,_,optional_size,flags=struct.unpack_from('<HHIIIHH',head,4);optional=f.read(optional_size)
        require(0<sections<=96 and len(optional)==optional_size and bool(flags&0x2000)==dll,'PE shape/type')
        magic=struct.unpack_from('<H',optional)[0]
        if not managed:require(machine==0x8664 and magic==0x20b and optional_size>=240,'Native binary not AMD64 PE32+')
        else:
            require(machine==0x14c and magic==0x10b and optional_size>=224,'Managed dependency not PE32 AnyCPU')
            require(struct.unpack_from('<I',optional,92)[0]>14,'Managed directory absent');rva,size=struct.unpack_from('<II',optional,96+14*8);require(rva and size>=20,'CLR header absent')
            table=f.read(sections*40);found=None
            for i in range(sections):
                virtual_size,virtual_address,raw_size,raw_offset=struct.unpack_from('<IIII',table,i*40+8)
                if virtual_address<=rva and rva-virtual_address+20<=raw_size:
                    offset=raw_offset+rva-virtual_address;require(offset+20<=row['bytes'],'CLR offset outside file');f.seek(offset);clr=f.read(20);found=struct.unpack_from('<I',clr,16)[0];break
            require(found is not None and found&1 and not found&(2|0x10|0x20000),'Managed assembly not IL-only AnyCPU')
    return dict(name=Path(path).name,sha256=row['sha256'],machine=hex(machine),optional_magic=hex(magic),managed_metadata_only=managed,native_code_loaded=False)

def pure_validator(path):
    text=Path(path).read_text('utf8');tree=ast.parse(text,filename=str(path));bad=[]
    denied_imports={'subprocess','ctypes','winreg','socket','http','urllib','requests','multiprocessing','threading','importlib'}
    denied_attrs={'Popen','system','startfile','LoadLibrary','WinDLL','CDLL','CreateProcess','write_text','write_bytes','mkdir','unlink','rmdir','chmod','rename','link','symlink'}
    for node in ast.walk(tree):
        if isinstance(node,ast.Import):
            for name in node.names:
                if name.name.split('.')[0]in denied_imports:bad.append('import:'+name.name)
        if isinstance(node,ast.ImportFrom)and node.module and node.module.split('.')[0]in denied_imports:bad.append('import:'+node.module)
        if isinstance(node,ast.Call):
            if isinstance(node.func,ast.Attribute)and node.func.attr in denied_attrs:bad.append('call:'+node.func.attr)
            if isinstance(node.func,ast.Name)and node.func.id in('eval','exec','compile','__import__'):bad.append('call:'+node.func.id)
            if(isinstance(node.func,ast.Name)and node.func.id=='open')or(isinstance(node.func,ast.Attribute)and node.func.attr=='open'):
                modes=[k.value for k in node.keywords if k.arg=='mode']
                if len(node.args)>1 and isinstance(node.func,ast.Name):modes.append(node.args[1])
                elif node.args and isinstance(node.func,ast.Attribute):modes.append(node.args[0])
                for mode in modes:
                    if isinstance(mode,ast.Constant)and isinstance(mode.value,str):require(not any(c in mode.value for c in'wax+'),'Validator write-open')
    require(not bad,'Validator includes prohibited import/call:'+str(bad));return dict(ast_parsed=True,root_helper_imported=False,root_helper_executed=False,prohibited_constructs=bad)

def run(result_path):
    data,resultref=load(result_path);root=canonical(pick(data,'runtime_directory','runtime'));require(root.is_relative_to(PROJECT/'Build/InteractiveGameRuntime')and root.name==data['run_id'],'Unexpected isolated runtime root')
    audit,auditref=load(EVIDENCE/'asset_input_review.json');binding=verify_ref(audit['binding']);compiled,_=load(binding['path'])
    require(set(compiled['packages'])==set(NAMES),'Expected exact five compiled roles')
    manifestref=verify_ref(pick(data,'asset_manifest','asset_manifestref','asset_manifest_ref'));manifest,_=load(manifestref['path'])
    require(Path(manifestref['path']).is_relative_to(root),'Asset control manifest escaped isolated runtime')
    require(manifest['schema']=='zerosis.world_assets.runtime_binding.v1'and Path(manifest['runtime_directory'])==root,'Asset manifest schema/root')
    require(set(manifest['packages'])==set(NAMES),'Asset manifest role set')
    host=artifact(root/'ZeroSisHost_x64.exe');require(host['sha256']==compiled['host']['sha256']and host['bytes']==compiled['host']['bytes'],'Latest phase8 Host differs')
    require(verify_ref(manifest['host'])['path']==host['path'],'Asset manifest Host escaped bundle');gamecore=artifact(root/'CvGameCoreDLL_Expansion2_x64.dll')
    require(gamecore['sha256']=='430f3122d0b555d6daae14aa7c011ef43ce8f978270477c8af596ca4b0493ab9','GameCore baseline differs');require(verify_ref(manifest['gamecore'])['path']==gamecore['path'],'Manifest SDK escaped bundle')
    for label,actual in(('host',host),('gamecore',gamecore)):
        overlay=pick(data,label)
        if isinstance(overlay,dict)and'target'in overlay:
            require(verify_ref(overlay['target'])['path']==actual['path']and verify_ref(overlay['source'])['sha256']==actual['sha256'],'Overlay binary source/target differs:'+label)
        else:require(verify_ref(overlay)['path']==actual['path'],'Overlay binary reference differs:'+label)
    passed('phase8_compiled_binding_host_sdk',binding=binding,host=host,gamecore=gamecore)
    packages=[];overlay_packages=pick(data,'packages','asset_packages')
    require(isinstance(overlay_packages,dict)and set(overlay_packages)==set(NAMES),'Overlay exact role set')
    for role,relative in NAMES.items():
        entry=manifest['packages'][role];require(entry['relative_path']==relative,'Unexpected role target');target=artifact(local(root,relative));source=artifact(compiled['packages'][role]['path'])
        expected=compiled['packages'][role];require(target['sha256']==source['sha256']==entry['sha256']==expected['sha256']and target['bytes']==source['bytes']==entry['bytes']==expected['bytes'],'Asset bytes/SHA differ:'+role)
        require(target['file_identity']==source['file_identity']and target['links']>=2,'Asset not shared hardlink:'+role)
        original=next(r['artifact']for r in audit['packages']if r['role']==role)
        require(all(source[k]==original[k]for k in('file_identity','sha256','bytes','mtime_ns','file_attributes')),'Donor changed beyond link count:'+role)
        overlay=overlay_packages[role];overlay_source=verify_ref(overlay['source']);overlay_target=verify_ref(overlay['target'])
        require(overlay_source['sha256']==source['sha256']and overlay_source['file_identity']==source['file_identity']and overlay_target['path']==target['path'],'Overlay source/target refs differ')
        require(pick(overlay,'method','materialization_method')=='hardlink','Overlay method not hardlink')
        with Path(target['path']).open('rb')as stream:head=stream.read(12)
        require(head[:8]==MAGIC[role][0]and struct.unpack_from('<I',head,8)[0]==MAGIC[role][1],'Asset format differs:'+role)
        packages.append(dict(role=role,source=source,target=target,magic=head[:8].decode('ascii'),donor_attributes_unchanged=True))
    passed('five_packages_exact_hardlink_format',packages=packages,new_payload_copies=0)
    corelines=(root/'bundle.manifest').read_text('ascii').splitlines();require(corelines[0]=='ZEROSIS_HOST_BUNDLE_V4','Native manifest schema')
    core={}
    for line in corelines[1:]:
        name,sha=line.split('|');require(name not in core,'Duplicate native manifest row');core[name]=sha
    oldcore={r['name']:r['artifact']for r in audit['backend_files']};require(set(core)==set(oldcore)and len(core)==23,'Native manifest exact allowlist')
    binaries=[]
    for name,sha in core.items():
        target=artifact(root/name);expected=host['sha256']if name=='ZeroSisHost_x64.exe'else compiled['packages']['terrain']['sha256']if name=='terrain-assets.bin'else oldcore[name]['sha256']
        require(target['sha256']==sha==expected,'Native backend digest differs:'+name)
        if name.endswith(('.dll','.exe')):binaries.append(pe(root/name,name in MANAGED,name.endswith('.dll')))
        if name in('rules.db','localization.db'):require(target['file_identity']!=oldcore[name]['file_identity'],'Database seed is shared with donor')
    with(root/'unit-assets.bin').open('rb')as stream:require(stream.read(12)==b'ZSUNIT02\2\0\0\0','Unit V2 lost')
    passed('native23_unit_v2_private_db_and_pe_metadata',binaries=binaries,managed_anycpu_exceptions=sorted(MANAGED))
    profile=verify_ref(audit['current_profile']);profiledoc,_=load(profile['path']);sidecars=profiledoc['required_sidecar']['files'];require(len(sidecars)==154,'Sidecar profile count')
    expectedpaths=set()
    for item in sidecars:
        relative=item['relative_path'];expectedpaths.add(relative);target=artifact(local(root,'UIFrontEnd/'+relative));frozen=verify_ref(item['frozen'])
        require(target['sha256']==frozen['sha256']and target['bytes']==frozen['bytes'],'UI sidecar mismatch:'+relative)
    actualpaths={p.relative_to(root/'UIFrontEnd').as_posix()for p in(root/'UIFrontEnd').rglob('*')if p.is_file()};require(actualpaths==expectedpaths,'Extra/missing sidecar path')
    passed('ui154_frozen_profile',profile=profile,file_count=154)
    supportdir=root/'interactive_ui_support';support,supportref=load(supportdir/'support_manifest.json');require(set(support['tools'])=={r['name']for r in audit['frozen_support']['tools']},'Six support modules differ')
    for row in audit['frozen_support']['tools']:
        name=row['name'];target=artifact(supportdir/'tools'/name);entry=support['tools'][name];require(Path(entry['path'])==Path(target['path'])and target['sha256']==entry['sha256']==row['runtime']['sha256'],'Local UI tool differs:'+name)
    for key,name in(('inline_icons','inline_icons.json'),('asset_preparation_provenance','prepared.json')):
        target=artifact(supportdir/'assets'/name);entry=support[key];old=next(r['artifact']for r in audit['frozen_support']['assets']if r['name']==name)
        require(Path(entry['path'])==Path(target['path'])and target['sha256']==entry['sha256']==old['sha256'],'Support asset path/digest differs:'+name)
    driver=(supportdir/'tools/interactive_ui_driver.py').read_text('utf8');require('env = dict(os.environ)'in driver and'cwd=cwd, env=env'in driver,'Driver no longer preserves explicit asset environment')
    passed('support6_local_paths_and_driver_env',manifest=supportref,root_helpers_executed=False)
    prepared=read_json(support['asset_preparation_provenance']['path'])
    font=prepared['font_input_profile'];bank=prepared['shared_font_metrics']
    fontroot=canonical(font['asset_root']);require(fontroot.parent==PROJECT/'Build/SharedUiFontInputs','Owned font root escaped project cache')
    require(font['input_storage']=='CONTENT_ADDRESSED_ENGINE_OWNED_FONT_INPUTS' and len(font['original_inputs'])==15 and font['source_files_copied']==0,'Owned font reuse contract differs')
    require(bank['profileId']==font['profile_id'],'Shared glyph bank profile differs')
    fontrows=[verify_ref(row) for row in font['original_inputs']]
    inventory=[]
    for row in fontrows:
        path=Path(row['path']);require(path.is_relative_to(fontroot),'Owned font input escaped root')
        inventory.append((path.relative_to(fontroot).as_posix(),row['bytes'],row['sha256']))
    require(hashlib.sha256(json.dumps(sorted(inventory),separators=(',',':'),ensure_ascii=True).encode('ascii')).hexdigest()==fontroot.name,'Owned font content identity differs')
    capturepath=PROJECT/'evidence/goody_hut/owned_fonts/capture_result.json';capture=read_json(capturepath)
    require(capture['status']=='PASS' and capture['cache_root']==str(fontroot) and capture['owned_profile']['profile_id']==font['profile_id'],'Owned font capture provenance differs')
    require({row['path']:(row['bytes'],row['sha256']) for row in capture['owned_inputs']}=={row['path']:(row['bytes'],row['sha256']) for row in fontrows},'Pinned owned font provenance differs')
    require(font['manifest']['sha256']==capture['profile']['sha256'],'Frozen preparation profile provenance differs')
    pixelsource=(supportdir/'tools/ui_pixel_scene.py').read_text('utf8');render_source=(supportdir/'tools/render_ui_popup.py').read_text('utf8')
    pixeltree=ast.parse(pixelsource);functions={node.name:node for node in pixeltree.body if isinstance(node,ast.FunctionDef)}
    binding_source=ast.get_source_segment(pixelsource,functions['owned_font_input_binding'])
    require("prepared.get('font_input_profile')" in binding_source and "root = owned_font_root(metadata.get('asset_root', ''))" in binding_source and "sha256(path) == row['sha256']" in binding_source,'Font binding no longer reads and pins frozen prepared owned inputs')
    require('load_font(self.font_root, font_id, style)' in pixelsource and "self.font_root = self.game_root if font_root is None else owned_font_root(font_root)" in pixelsource,'Font loader root differs')
    require('font_binding = owned_font_input_binding(frozen_prepared)' in render_source and "font_root=font_binding['asset_root'] if font_binding is not None else None" in render_source,'Render preparation does not carry owned font root')
    passed('owned_font15_pinned_capture_and_static_loader_root',root=str(fontroot),profile_id=font['profile_id'],capture=artifact(capturepath),count=15,current_installed_font_equality_required=False,root_helpers_executed=False,readability_or_rendering_verified=False)

    verifierentry=manifest['validator'];require(verifierentry['relative_path']=='WorldAssets/verify_assets.py','Verifier relative path')
    verifier=artifact(local(root,verifierentry['relative_path']));require(all(verifier[k]==verifierentry[k]for k in('bytes','sha256')),'Validator digest differs');pure=pure_validator(verifier['path'])
    validator_tree=ast.parse(Path(verifier['path']).read_text('utf8'));pins={}
    for node in validator_tree.body:
        if isinstance(node,ast.Assign) and len(node.targets)==1 and isinstance(node.targets[0],ast.Name) and node.targets[0].id in {'EXPECTED','HOST','SDK'}:
            pins[node.targets[0].id]=ast.literal_eval(node.value)
    expected_pins={'HOST':host['sha256'],'SDK':gamecore['sha256'],'EXPECTED':{role:(NAMES[role],compiled['packages'][role]['sha256'],MAGIC[role][0]) for role in NAMES}}
    require(pins==expected_pins,'Runtime validator contains stale Host/SDK/five-pack pins')
    launcher=verify_ref(pick(data,'launcher','launcherref','launcher_ref'));require(Path(launcher['path'])==root/'Play.ps1','Wrong Play launcher')
    snapshotref=verify_ref(data['base_snapshot']);require(snapshotref['bytes']<=2*1024*1024,'Unbounded compressed control snapshot')
    with gzip.open(snapshotref['path'],'rb')as stream:decoded=stream.read(2*1024*1024+1)
    require(len(decoded)<=2*1024*1024,'Unbounded control snapshot');snapshot=json.loads(decoded)
    require(snapshot['run_id']==data['run_id']and Path(snapshot['runtime_directory'])==root,'Base control snapshot identity')
    controls={}
    for row in snapshot['files']:
        raw=base64.b64decode(row['data_base64'],validate=True);record=row['artifact'];require(len(raw)==record['bytes']and hashlib.sha256(raw).hexdigest()==record['sha256'],'Historical control snapshot differs')
        require(row['relative_path']not in controls,'Duplicate control snapshot name');controls[row['relative_path']]=raw
    require(set(controls)=={'request.json','bundle.manifest','Play.ps1'},'Control snapshot set differs')
    prefix=data['launcher_prefix'];require((root/'Play.ps1').read_bytes()==prefix.encode('utf8')+controls['Play.ps1'],'Original Play body changed beyond prefix')
    before_lines=controls['bundle.manifest'].decode('utf8').splitlines();expected_lines=['terrain-assets.bin|'+compiled['packages']['terrain']['sha256']if line.startswith('terrain-assets.bin|')else line for line in before_lines]
    require(corelines==expected_lines,'Native manifest changed beyond terrain replacement')
    play=(root/'Play.ps1').read_text('utf8');normalized=re.sub(r'[/\\]+','/',play);driverpos=play.index('interactive_ui_driver.py');verifierpos=play.index('verify_assets.py');require(verifierpos<driverpos,'Asset validation must precede Host driver')
    require('--root $PSScriptRoot'in play and'--manifest-sha256'in play and manifestref['sha256']in play,'Launcher missing bound verifier arguments')
    manifest_relative=Path(manifestref['path']).relative_to(root).as_posix();require(manifest_relative in normalized[:driverpos],'Launcher manifest is not bundle local')
    for role,name in ENV.items():
        line=re.findall(r'^\$env:'+name+r'\s*=([^\n]+)',normalized,re.M);require(len(line)==1 and'Join-Path'in line[0]and'$PSScriptRoot'in line[0]and NAMES[role]in line[0],'Launcher env not exact local role:'+name)
    require(str(OLD)not in play and str(OLD).replace("'","''")not in play,'Play still points to old runtime')
    between=play[verifierpos:driverpos];require('$LASTEXITCODE'in between and re.search(r'\b(throw|exit)\b',between),'Verifier failure does not stop launch')
    require(not re.search(r'SetEnvironmentVariable\([^\n]*(?:Machine|User)',play),'Persistent global environment mutation')
    require(not(root/'Session.ps1').exists(),'Unexpected extra Session launcher')
    resume=(root/'Resume.ps1').read_text('utf8');require('Save loading is disabled for this unexecuted current SDK candidate.'in resume and'--play-load'not in resume,'Resume must stay disabled')
    passed('four_fixed_envs_pure_verifier_before_driver',launcher=launcher,validator=verifier,validator_ast=pure,resume_native_blocked=True,
        original_play_body_byte_exact=True,base_control_snapshot=snapshotref,only_terrain_native_manifest_entry_changed=True)
    requestref=verify_ref(pick(data,'request','requestref','request_ref'));request,_=load(requestref['path']);require(request['run_id']==data['run_id']and Path(request['cwd'])==root,'Runtime request identity/cwd')
    require(request.get('smoke')is False and request.get('resume_from')is None,'Request must remain newgame-only non-smoke')
    command=request['command'];require(command[command.index('--host')+1]==str(root/'ZeroSisHost_x64.exe')and command[command.index('--runtime')+1]==str(root),'Driver request escaped bundle')
    for row in request['runtime_inputs']:verify_ref(row)
    require(verify_ref(request['terrain_assets']['package'])['sha256']==compiled['packages']['terrain']['sha256']and request['terrain_assets']['package_format']=='ZSTERR02','Request terrain provenance stale')
    require(verify_ref(request['presentation_asset_binding'])['sha256']==manifestref['sha256'],'Request asset manifest differs')
    for key in('play','selected'):require(verify_ref(request['launcher_control_metadata'][key])['sha256']==launcher['sha256'],'Request launcher metadata stale')
    require(not any((root/'sessions').rglob('*'))if(root/'sessions').exists()else True,'Runtime contains native session output')
    require(not any(root.glob('menu-options.*'))and not any(root.glob('interactive-ui-*.json')),'Unexpected native options/UI output')
    passed('request_private_session_no_native_output',request=requestref,original_settings_mods_saves_default_not_touched=True)
    return dict(schema='zerosis.phase9.asset_final_verification.v1',status='PASS_FILE_ONLY_PHASE8_RUNTIME_ASSET_BINDING',overlay_result=resultref,runtime_directory=str(root),run_id=data['run_id'],checks=CHECKS,
        scope='NoNative0',no_root_helper_import_or_execution=True,native_host_gamecore_clr_hwnd_gpu_audio_or_game_attempts=0,native_host_gamecore_clr_hwnd_gpu_audio_or_game_executed=False,original_mods_settings_saves_default_registration_changed=False,
        limitation='Filebytes,metadata,launcher/controlflow/source contracts only;actual Host/GPU/game/screens remain held')

def evidence_boundary(event,args):
    if event.startswith(('subprocess.','socket.','winreg.')) or event in ('os.system','os.startfile','ctypes.dlopen'):
        raise PermissionError('NoNative0 forbids native/process/network/registry execution')
    if event=='open':
        mode,flags=args[1],args[2]
        writing=isinstance(mode,str) and any(c in mode for c in 'wax+')
        writing|=isinstance(flags,int) and bool(flags&(os.O_WRONLY|os.O_RDWR|os.O_CREAT|os.O_TRUNC|os.O_APPEND))
        if writing:
            path=Path(os.fsdecode(args[0])).absolute()
            require(path.parent==EVIDENCE and path.name.startswith('asset_') and path.suffix=='.json','Write escaped owned evidence')
    elif event in ('os.mkdir','os.remove','os.rmdir','os.chmod','os.utime','os.rename','os.replace','os.link','os.symlink'):
        raise PermissionError('Independent verifier may not mutate runtime or source files')


def main():
    p=argparse.ArgumentParser();p.add_argument('--overlay-result',type=Path,required=True);p.add_argument('--output',type=Path,default=EVIDENCE/'asset_final_verification.json');a=p.parse_args()
    output=a.output.absolute();require(output.parent==EVIDENCE and output.name.startswith('asset_')and output.suffix=='.json','Output must stay in owned asset evidence')
    require(not output.exists(),'Do not overwrite prior audit');sys.addaudithook(evidence_boundary);proof=run(a.overlay_result)
    proof['verifier_source']=artifact(__file__)
    with output.open('x',encoding='utf8')as stream:json.dump(proof,stream,indent=2);stream.write('\n')
    print(json.dumps(dict(status=proof['status'],checks=len(CHECKS),run_id=proof['run_id'],output=artifact(output))))

if __name__=='__main__':main()
