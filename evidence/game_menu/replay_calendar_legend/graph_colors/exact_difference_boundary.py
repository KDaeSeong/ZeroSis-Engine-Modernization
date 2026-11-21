"""One exact 3000-distance Lua/C++ equality witness; reuse the passed component."""
from pathlib import Path
import json
import sys

STAGE=Path(__file__).resolve().parent
PROJECT=STAGE.parents[3]
sys.path[:0]=[str(PROJECT/'tools'),str(PROJECT/'Tests')]
import menu_replay_graph_colors as fixture
from menu_frontend_skin import artifact,require
from native_build import run


def main():
    target=STAGE/'exact_difference_boundary.json'
    require(not target.exists(),'Completed exact-boundary witness must not be repeated')
    previous=STAGE/'fixture_result.json';previous_pin=artifact(previous)
    receipt=json.loads(previous.read_text('utf8'))
    executable=Path(receipt['build']['path']);executable_pin=artifact(executable)
    require(executable_pin['sha256']==receipt['build']['sha256'],'Passed C++14 component bytes differ')
    header=artifact(fixture.HEADER)
    require(header['sha256']=='7d70fb0df70a0dc806363587eaa3b22f276245a9960c5a07c21f8838f34b2fc0',
            'Exact-boundary test must use the frozen verified selector')
    body,source=fixture.original_block()
    catalogs={'exact':[fixture.color('FIRST',0.5,0.5,0.5),
        fixture.color('EXACT_EDGE',0.5-10/255,0.5-14/255,0.5-52/255),
        fixture.color('SAFE',1,0,1)]}
    cases=[dict(name='difference_distance_exact_3000_is_unique',catalog='exact',
        roster=[dict(PrimaryColor='FIRST',SecondaryColor='SAFE'),
                dict(PrimaryColor='EXACT_EDGE',SecondaryColor='SAFE')],
        probes=[dict(left='EXACT_EDGE',right='FIRST')])]
    expected=fixture.goldens(body,catalogs,cases)
    require(expected[0]['distances']==[3000] and
        [row['type'] for row in expected[0]['selected']]==['FIRST','EXACT_EDGE'],
        'Original Lua no longer accepts the exact inclusive 3000-distance boundary')
    temporary=STAGE/'component/exact_difference_boundary.bin'
    require(not temporary.exists(),'Prior exact-boundary temporary input must be inspected')
    fixture.fixture_bytes(temporary,catalogs,cases,expected)
    temporary_pin=artifact(temporary)
    result=run([executable,temporary],cwd=temporary.parent,timeout=30)
    require(result.returncode==0,'Exact-boundary C++14 mismatch: '+
            (result.stdout+result.stderr).decode('utf8',errors='replace'))
    actual=json.loads(result.stdout.decode('utf8'))
    require(actual['cases']==1 and actual['matched_selected_colors']==2,'Exact-boundary C++ fixture count differs')
    cleanup=[]
    for path in (temporary,STAGE/'component/read_build_environment.cmd'):
        if not path.exists():continue
        require(path.absolute().parent==(STAGE/'component').absolute() and not path.is_symlink(),
                'Exact graph color intermediate cleanup escaped its owned component')
        row=artifact(path);path.unlink();cleanup.append(dict(**row,result='DELETED_OWNED_GRAPH_COLOR_INTERMEDIATE'))
    require(artifact(previous)==previous_pin and artifact(executable)==executable_pin and
            artifact(fixture.HEADER)==header,'Existing verified graph color results changed')
    value=dict(schema='zerosis.replay_graph_colors.exact_difference_boundary.v1',
        status='PASS_ORIGINAL_LUA_AND_CPP_EXACT_3000_DISTANCE_IS_UNIQUE',
        original_source=source,header=header,previous_384_case_report=previous_pin,
        reused_cpp14_component=executable_pin,synthetic_catalog=catalogs['exact'],
        original_lua_expected=expected[0],actual_cpp14=actual,cleanup=cleanup,
        original_384_case_report_preserved=True,synthetic_colors_are_test_inputs_only=True,
        native_host_or_sdk_or_window_executed=False,clr_or_gpu_executed=False)
    target.write_text(json.dumps(value,indent=2,ensure_ascii=False)+'\n',encoding='utf8')
    print(json.dumps(dict(status=value['status'],actual_distance=expected[0]['distances'][0],
        selected=[row['type'] for row in expected[0]['selected']],cleaned_files=len(cleanup),report=artifact(target))))


if __name__=='__main__':main()
