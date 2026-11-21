"""File-only CPU diagnostic line ordering, compositing and bounds regression.

This checks the software diagnostic convention. It neither imports nor executes
the game, SDK, native renderer, window or GPU, and is not native pixel acceptance.
"""
from __future__ import annotations
import ast
import gzip
import hashlib
import json
from pathlib import Path
import struct
import sys
import types
import zlib

sys.dont_write_bytecode=True
PROJECT=Path(__file__).absolute().parents[1]
sys.path.insert(0,str(PROJECT/'tools'))
import menu_frontend_cpu as cpu
from menu_frontend_assets import artifact
from menu_suite_storage import storage

ROOT=PROJECT/'evidence/game_menu/replay_scroll_graph/cpu_lines'
SOURCE=PROJECT/'tools/menu_frontend_cpu.py'
LEGACY=PROJECT/'evidence/game_menu/replay_scroll_graph/source_before/tools__menu_frontend_cpu.py.88c41cfac7d7b0ad.gz'
LEGACY_SHA='88c41cfac7d7b0ad7e65762b427496b22e6c53f59d8ec87c53c4bdac40b105f4'


def packet(sprites=(),textures=(),hits=(),scrolls=()):
    out=bytearray(b'ZSUPIX02'+struct.pack('<6I',1920,1080,len(textures),len(sprites),len(hits),len(scrolls)))
    for path in textures:
        text=str(path.absolute()).encode('utf8');out+=struct.pack('<I',len(text))+text
    for texture,target,clip,tint in sprites:
        out+=struct.pack('<IQ16f',texture,0,0,0,2,2,*target,*clip,*tint)
    for key,rect in (*hits,*scrolls):out+=struct.pack('<Q4f',key,*rect)
    return bytes(out)


def line(start=(1,5),end=(10,5),width=1,rgba=(0,0,1,1),clip=(0,0,20,20),anchor=0):
    return dict(start=list(start),end=list(end),width=width,rgba=list(rgba),clip=list(clip),beforeSprite=anchor)


def png_pixels(data):
    if data[:8]!=b'\x89PNG\r\n\x1a\n':raise ValueError('Fixture did not emit PNG')
    cursor=8;compressed=bytearray();size=None
    while cursor<len(data):
        length=struct.unpack_from('>I',data,cursor)[0];kind=data[cursor+4:cursor+8];payload=data[cursor+8:cursor+8+length]
        if kind==b'IHDR':size=struct.unpack_from('>2I',payload)
        elif kind==b'IDAT':compressed+=payload
        cursor+=12+length
    width,height=size;raw=zlib.decompress(compressed);pitch=width*4+1
    if len(raw)!=pitch*height or any(raw[y*pitch] for y in range(height)):raise ValueError('Unexpected CPU PNG rows')
    return b''.join(raw[y*pitch+1:(y+1)*pitch] for y in range(height))


def pixel(data,x,y):
    offset=(y*1920+x)*4;return tuple(data[offset:offset+4])


def nonempty(data):
    return {(x,y) for y in range(24) for x in range(24) if pixel(data,x,y)[3]}


def main():
    before=[artifact(path) for path in (SOURCE,Path(__file__),LEGACY,PROJECT/'tools/civ5_ui_assets.py',PROJECT/'tools/menu_frontend_assets.py',PROJECT/'tools/menu_suite_storage.py')]
    signature=hashlib.sha256(json.dumps(before,sort_keys=True).encode()).hexdigest()[:20]
    output=ROOT/('attempt_'+signature);report_path=output/'result.json'
    if report_path.exists():
        old=json.loads(report_path.read_text('utf8'))
        if old.get('status')=='PASS_CPU_DIAGNOSTIC_LINES_AND_LEGACY_SPRITES' and old.get('inputs_before')==before:
            print(json.dumps(dict(status=old['status'],report=str(report_path),reused_existing_identical_inputs=True)));return 0
        raise ValueError('Existing fixture result cannot be overwritten')
    output.mkdir(parents=True,exist_ok=True);work=output/'owned_temp';work.mkdir()
    report=dict(schema='zerosis.cpu_scene_line_test.v1',input_signature=signature,inputs_before=before,
        native_host_sdk_window_gpu_executed=False,visual_acceptance=False,
        limitations=['Pixel comparisons prove the explicitly documented CPU DDA/square-stroke/nearest diagnostic convention only.',
                    'Native antialiasing, line caps, filtering and actual displayed frames remain untested.'])
    checks=0;cases=[];files=[]
    def check(value,message):
        nonlocal checks
        checks+=1
        if not value:raise AssertionError(message)
    def write(path,data):
        if path.exists():raise ValueError('Owned test file unexpectedly exists')
        path.write_bytes(data);files.append(path);return path
    def draw(name,lines=None,sprites=(),scrolls=(),module=cpu):
        inp=write(work/(name+'.packet'),packet(sprites=sprites,scrolls=scrolls));image=work/(name+'.png')
        line_path=None
        if lines is not None:line_path=write(work/(name+'.lines.json'),json.dumps(dict(schema='zerosis.scene_line.diagnostic.v1',lines=lines),allow_nan=True).encode())
        try:
            result=module.render(inp,image,work,line_path) if module is not legacy else module.render(inp,image,work)
        finally:
            if image.exists():files.append(image)
        cases.append(dict(name=name,lines=len(lines or ()),sprites=len(sprites)))
        check(result.get('runtime_pixel_acceptance') is False,'Diagnostic declared native pixel acceptance')
        return png_pixels(image.read_bytes()),image.read_bytes()
    def reject(name,lines,message,sprites=()):
        try:draw(name,lines,sprites=sprites)
        except ValueError as error:
            check(message in str(error),'Unexpected diagnostic rejection: '+str(error));return
        raise AssertionError('Malformed line fixture was accepted: '+name)
    try:
        legacy_source=gzip.decompress(LEGACY.read_bytes());check(hashlib.sha256(legacy_source).hexdigest()==LEGACY_SHA,'Legacy baseline source changed')
        legacy=types.ModuleType('retained_cpu_sprite_baseline');exec(compile(legacy_source,str(LEGACY),'exec'),legacy.__dict__)
        words=[0]*32;words[0]=int.from_bytes(b'DDS ','little');words[1]=124;words[2]=0x100f;words[3:8]=[2,2,8,0,1]
        words[19:27]=[32,0x41,0,32,0xff0000,0xff00,0xff,0xff000000];words[27]=0x1000
        texture=write(work/'fixture.dds',struct.pack('<32I',*words)+bytes((0,0,255,255,0,255,0,128,255,0,0,255,255,255,255,64)))
        defaults=[(0xffffffff,(2,2,8,6),(3,3,7,7),(1,0,0,.5)),(0,(4,4,8,8),(4,4,7,8),(.5,.75,1,.75))]
        # Use a real two-by-two bounded DDS and nontrivial tint, overlap and crop.
        inp=write(work/'legacy.packet',packet(defaults,[texture]));paths=[]
        for name,module,kwargs in [('legacy',legacy,{}),('default',cpu,{}),('empty_lines',cpu,{'line_records':write(work/'empty.lines.json',b'{"schema":"zerosis.scene_line.diagnostic.v1","lines":[]}')})]:
            dest=work/(name+'.png');result=module.render(inp,dest,work,**kwargs);files.append(dest);paths.append(dest)
            check(result['runtime_pixel_acceptance'] is False,'Legacy comparison declared pixel acceptance')
        check(paths[0].read_bytes()==paths[1].read_bytes()==paths[2].read_bytes(),'Default or empty-line sprite rendering differs from retained legacy bytes')
        cases.append(dict(name='legacy_default_and_empty_line_png_byte_identity',baseline_uncompressed_sha256=LEGACY_SHA,texture_pixels=4))
        red=(0xffffffff,(10,10,15,15),(0,0,20,20),(1,0,0,1))
        before_pixels,_=draw('before_sprite',[line((8,12),(17,12),anchor=0)],[red])
        after_pixels,_=draw('after_sprite',[line((8,12),(17,12),anchor=1)],[red])
        check(pixel(before_pixels,12,12)==(255,0,0,255) and pixel(before_pixels,8,12)==(0,0,255,255),'Line did not paint before its anchored sprite')
        check(pixel(after_pixels,12,12)==(0,0,255,255),'Trailing line did not paint after final sprite')
        translucent,_=draw('alpha_after_sprite',[line((8,12),(17,12),rgba=(0,0,1,.5),anchor=1)],[red])
        check(pixel(translucent,12,12)==(127,0,128,255),'Straight alpha source-over composition changed')
        ordered,_=draw('equal_anchor_order',[line((1,5),(10,5)),line((1,5),(10,5),rgba=(0,1,0,1))])
        check(pixel(ordered,5,5)==(0,255,0,255),'Equal-anchor line order changed')
        clipped,_=draw('fractional_clip',[line((-100,5),(100,5),clip=(3.2,4.1,8.8,6.9))])
        check(nonempty(clipped)=={(x,5) for x in range(4,9)},'Fractional clip escaped or removed owned integer pixels')
        reversed_pixels,_=draw('reverse_vertical',[line((5,10),(5,-10),clip=(4,3,7,8))])
        check(nonempty(reversed_pixels)=={(5,y) for y in range(3,8)},'Reversed line clipping changed')
        diagonal,_=draw('diagonal_clip',[line((0,0),(10,10),clip=(2,2,7,7))])
        check(nonempty(diagonal)=={(p,p) for p in range(2,7)},'Diagnostic diagonal escaped its half-open clip')
        thick,_=draw('thick_alpha_once',[line((1,5),(10,5),width=3,rgba=(1,1,1,.5))])
        check(bool(nonempty(thick)) and all(pixel(thick,x,y)==(255,255,255,128) for x,y in nonempty(thick)),'Overlapping DDA steps blended one stroke more than once')
        blank,_=draw('degenerate_and_outside',[line((5,5),(5,5)),line((-100,30),(100,30))])
        check(not any(blank),'Degenerate or clipped-out stroke changed pixels')
        transparent,_=draw('transparent',[line(rgba=(1,1,1,0))])
        check(not any(transparent),'Zero-alpha line changed pixels')
        scrolled,_=draw('scroll_table_length',[line()],scrolls=[(1,(0,0,20,20))])
        check(pixel(scrolled,5,5)==(0,0,255,255),'Bounded scroll packet table was not accepted')
        upper,_=draw('maximum_degenerate_line_count',[line((1,1),(1,1)) for _ in range(8192)])
        check(not any(upper),'Exact maximum line count did not preserve degenerate behavior')
        reject('over_count',[line() for _ in range(8193)],'line count')
        reject('negative_anchor',[line(anchor=-1)],'diagnostic line')
        reject('past_anchor',[line(anchor=1)],'diagnostic line')
        reject('unordered_anchor',[line(anchor=1),line(anchor=0)],'diagnostic line',sprites=[red])
        reject('boolean_anchor',[line(anchor=True)],'diagnostic line')
        for name,value in [('zero_width',0),('negative_width',-1),('wide_stroke',256.1),('nan_width',float('nan'))]:reject(name,[line(width=value)],'diagnostic')
        for name,color in [('low_color',(-.1,0,0,1)),('high_color',(0,1.1,0,1)),('nonfinite_color',(0,0,0,float('inf')))]:reject(name,[line(rgba=color)],'diagnostic')
        reject('empty_clip',[line(clip=(0,0,0,20))],'stroke')
        reject('reversed_clip',[line(clip=(10,0,0,20))],'stroke')
        reject('nan_endpoint',[line(start=(float('nan'),0))],'diagnostic line')
        reject('large_finite_endpoint',[line(start=(-1e308,0),end=(1e308,1))],'diagnostic')
        reject('out_of_contract_clip',[line(clip=(-10000001,0,20,20))],'diagnostic')
        # Exercise the actual budget decrement/failure without allocating or
        # painting twenty million pixels. Only its single configured constant
        # changes in an in-memory AST clone; production bytes remain untouched.
        tree=ast.parse(SOURCE.read_text('utf8'));budget_nodes=[n for n in ast.walk(tree) if isinstance(n,ast.Constant) and n.value==20000000]
        check(len(budget_nodes)==1,'Production pixel budget is not exactly twenty million')
        budget_nodes[0].value=8;fault=types.ModuleType('cpu_budget_fault_injection');exec(compile(ast.fix_missing_locations(tree),str(SOURCE),'exec'),fault.__dict__)
        try:draw('pixel_budget_fault',[line((1,5),(10,5))],module=fault)
        except ValueError as error:check('pixel budget exceeded' in str(error),'Injected budget failed outside the actual budget guard')
        else:raise AssertionError('Actual pixel budget guard did not reject ninth pixel')
        report.update(status='PASS_CPU_DIAGNOSTIC_LINES_AND_LEGACY_SPRITES',checks=checks,cases=cases,
            legacy_sprite_output_byte_identical=True,legacy_texture_pixels=4,
            budget_probe=dict(production_pixels=20000000,in_memory_fault_pixels=8,production_source_modified=False),
            inputs_after=[artifact(path) for path in (SOURCE,Path(__file__),LEGACY,PROJECT/'tools/civ5_ui_assets.py',PROJECT/'tools/menu_frontend_assets.py',PROJECT/'tools/menu_suite_storage.py')])
        if report['inputs_after']!=before:raise ValueError('CPU fixture inputs changed during execution')
    except Exception as error:
        report.update(status='FAIL_CPU_DIAGNOSTIC_LINES_AND_LEGACY_SPRITES',checks=checks,cases=cases,error=str(error));raise
    finally:
        removed=[]
        for path in files:
            info=storage.ordinary(path)
            if path.absolute().parent!=work.absolute() or info.st_nlink!=1:raise ValueError('Unsafe CPU fixture cleanup')
            row=dict(artifact(path),file_identity=[info.st_dev,info.st_ino],allocated_bytes=storage.allocated(path))
            if storage.metadata(info)!=storage.metadata(storage.ordinary(path)):raise ValueError('CPU fixture cleanup identity changed')
            path.unlink();row['result']='DELETED_EXACT_OWNED_CPU_DIAGNOSTIC_TEMP';removed.append(row)
        if any(work.iterdir()):raise ValueError('Unexpected files remain in owned CPU test directory')
        work.rmdir();report['owned_intermediate_cleanup']=removed
        report['cleaned_logical_bytes']=sum(row['bytes'] for row in removed)
        report['cleaned_allocated_bytes']=sum(row['allocated_bytes'] for row in removed)
        report_path.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(json.dumps(dict(status=report['status'],checks=checks,report=str(report_path),cleaned_logical_bytes=report['cleaned_logical_bytes'])));return 0


if __name__=='__main__':raise SystemExit(main())
