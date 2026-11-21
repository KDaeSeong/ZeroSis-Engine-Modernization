"""Replace the original in-frame unit block with shared prepare/upload/draw calls."""
from pathlib import Path
import hashlib,json,sys
sys.dont_write_bytecode=True
stage=Path(__file__).absolute().parent;project=stage.parents[2]
path=project/'Source/Presentation/WorldTerrainRenderer.cpp';source=path.read_text('utf8')
begin='        if(!view.unitAssetsPath.empty()){\n'
assert source.count(begin)==1
start=source.index(begin);end=source.index('        cache.context->OMSetRenderTargets(0,nullptr,nullptr);',start)
old=source[start:end];assert 'std::map<unsigned,Group> unitGroups' in old and 'cache.context->Draw(' in old
new='''        if(!unitGroups.empty()){
            ID3D11RenderTargetView* target=surfaces.colorView.Get();cache.context->OMSetRenderTargets(1,&target,surfaces.depthView.Get());
            DrawTerrainUnits(cache,unitGroups);
        }
'''
result=source[:start]+new+source[end:]
assert result.count('PrepareTerrainUnits(view,cache,*groundData,result)')==1
path.write_text(result,encoding='utf8')
value=dict(status='PASS_UNIT_PREPARATION_AND_UPLOAD_SHARED_WITH_REFLECTION',removed_block_sha256=hashlib.sha256(old.encode()).hexdigest(),
    removed_block_bytes=len(old.encode()),replacement_sha256=hashlib.sha256(new.encode()).hexdigest(),
    helper_sha256=hashlib.sha256((project/'Source/Presentation/WorldTerrainUnits.inc').read_bytes()).hexdigest(),
    old_source_backup='source_before.json',new_sdk_or_rng_reads=False,new_native_execution=False)
with (stage/'unit_refactor_receipt.json').open('x',encoding='utf8') as f:json.dump(value,f,indent=2);f.write('\n')
print(json.dumps(dict(status=value['status'],retired_inline_code_bytes=value['removed_block_bytes'])))
