"""Reuse the audited file-only preparation/overlay with explicit new pins."""
from pathlib import Path
import hashlib,json,sys
sys.dont_write_bytecode=True
STAGE=Path(__file__).absolute().parent
PROJECT=STAGE.parents[3]
OLD=PROJECT/'evidence/world_terrain_original/phase9/runtime_integration'

def transform(name,replacements):
    path=OLD/name;before=path.read_text('utf8');after=before
    for a,b in replacements:
        assert a in after,(name,a)
        after=after.replace(a,b)
    target=STAGE/name
    assert not target.exists();target.write_text(after,encoding='utf8')
    return dict(source=str(path),source_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        target=str(target),target_sha256=hashlib.sha256(target.read_bytes()).hexdigest(),
        changes=[dict(before=a,after=b) for a,b in replacements])

def main():
    assert not (STAGE/'adaptation.json').exists()
    host='20261116T114748Z_014dd63ad3bc';old='20261115T121456Z_dbb01a1f4f50'
    profile='evidence/world_terrain_original/phase10/pair_preparation/'+host+'/prepared_profile.json'
    assert hashlib.sha256((PROJECT/profile).read_bytes()).hexdigest()=='3e2ad9b8d1205f087b1ead5de5b846923035821b794691f26d42d21e2dec2c89'
    rows=[]
    rows.append(transform('work.py',[
        ('phase8/current_work.json','phase10/current_work.json'),
        ("'20261115T121456Z_dbb01a1f4f50', '20261115T093013Z_23c5037b12b9'", "'20261116T114748Z_014dd63ad3bc', '20261115T121456Z_dbb01a1f4f50', '20261115T093013Z_23c5037b12b9'"),
        ("'20261115T101941Z_99b3c393ee9a', '20261115T011241Z_4c8fd55e99db'", "'20261115T134603Z_aa8853762399', '20261115T101941Z_99b3c393ee9a', '20261115T011241Z_4c8fd55e99db'"),
        ("roots += [PROJECT / 'evidence/world_terrain_original/phase8',", "roots += [PROJECT / 'evidence/world_terrain_original/phase10', PROJECT / 'evidence/world_terrain_original/phase9/runtime_integration', PROJECT / 'evidence/world_terrain_original/phase8',"),
        ('phase8/cleanup_summary.json','phase10/cleanup_summary.json'),
        ('five asset packages reused','six asset packages reused'),
        ('WORKING_PHASE9_LATEST_PHASE8_ISOLATED_RUNTIME_INTEGRATION','WORKING_PHASE11_LATEST_PHASE10_ISOLATED_RUNTIME_INTEGRATION')]))
    rows.append(transform('prepare_base.py',[
        ('phase8/pair_preparation/'+old,'phase10/pair_preparation/'+host),
        ('f351d6ae32fa1d69788a9f945a59c0799ff1c51e3a96cee61952a16d25f5a959','3e2ad9b8d1205f087b1ead5de5b846923035821b794691f26d42d21e2dec2c89'),
        (old,host)]))
    rows.append(transform('verify_assets.py',[
        ("HOST = '8e67b0fc6c90c354c6341dfcc39f87b5ae030dd564da9bb1210ad602ba3a70e5'", "HOST = 'c3bb5ffc2e57630d28a8305f288b501352c03f0e1970b1dc5b321d6ba0683383'"),
        ("}\nHOST =", "    'screen_light': ('WorldAssets/screen-light-assets.bin', 'f02165b489bfe80557e1fd0246c0a2423f5494a28f4974d935120ea14528a0e0', b'ZSSCRL01'),\n}\nHOST ="),
        ('Five original packages are required','Six original packages are required'),
        ('PASS_FIVE_RUNTIME_PACKS_AND_ATTESTED_PAIR_FILE_ONLY','PASS_SIX_RUNTIME_PACKS_AND_ATTESTED_PAIR_FILE_ONLY'),
        ('packages=5','packages=6')]))
    rows.append(transform('overlay.py',[
        (old,host),('20261115T101941Z_99b3c393ee9a','20261115T134603Z_aa8853762399'),
        ('phase8/compiled_asset_binding.json','phase10/compiled_asset_binding.json'),
        ("'ZEROSIS_LIGHTING_ASSETS':'lighting-assets.bin'}", "'ZEROSIS_LIGHTING_ASSETS':'lighting-assets.bin', 'ZEROSIS_SCREEN_LIGHT_ASSETS':'screen-light-assets.bin'}"),
        ('packages=5','packages=6'),('direct_asset_links=5','direct_asset_links=6'),
        ('FIVE_ASSETS','SIX_ASSETS'),('zerosis.phase9.','zerosis.phase11.')]))
    with (STAGE/'adaptation.json').open('x',encoding='utf8') as stream:
        json.dump(dict(status='PASS_FILE_ONLY_WRAPPER_AND_SIX_PACK_OVERLAY_PREPARED',files=rows,
            existing_source_tools_or_packages_modified=False,native_execution_allowed=False),stream,indent=2)
        stream.write('\n')
    print(json.dumps(dict(status='PASS_FILE_ONLY_ADAPTERS_PREPARED',files=len(rows),native_execution=False)))

if __name__=='__main__':main()
