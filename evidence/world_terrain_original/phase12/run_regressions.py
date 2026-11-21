"""Reuse reviewed CPU/FXC cases in fresh outputs; historical mains stay untouched."""
from pathlib import Path
import argparse,hashlib,importlib.util,json,sys
sys.dont_write_bytecode=True
ROOT=Path(__file__).absolute().parent
PROJECT=ROOT.parents[2]
sys.path[:0]=[str(PROJECT/'Tests'),str(PROJECT/'tools')]


def load(relative,name):
    path=PROJECT/relative
    spec=importlib.util.spec_from_file_location(name,path);module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module,path


def assets():
    m,driver=load('evidence/world_terrain_original/phase10/cache_regressions/asset_cpu_regressions.py','retained_asset_cpu')
    m.ROOT=ROOT/'cache_regressions';m.ROOT.mkdir()
    # Preserve all existing model cases. Only the old unquantized-average
    # expectation is replaced with the independently calculated u16 golden.
    old=m.PINNED['original_terrain_model.cpp']
    m.PINNED['original_terrain_model.cpp']=m.ref(PROJECT/'Tests/original_terrain_model.cpp')['sha256']
    tests=m.pinned_tests();original,original_ref=m.library();inputs=m.closure()+tests+[original_ref,m.ref(driver),m.ref(__file__)]
    stage=m.ROOT/'asset_cpu01';stage.mkdir()
    m.write_new(stage/'derivation.json',dict(retained_driver=m.ref(driver),output_root_override=str(m.ROOT),
        original_model_sha256=old,current_model_test=m.ref(PROJECT/'Tests/original_terrain_model.cpp'),
        only_expected_heightmap_golden_updated=True,original_driver_main_executed=False,old_evidence_modified=False))
    cases=[m.execute_case(kind,stage,inputs,original) for kind in ('model','geometry')]
    passed=all(row[1]['status'].startswith('PASS_') for row in cases)
    result=dict(status='PASS_CURRENT_HEIGHTMAP_TERRAIN_MODEL_GEOMETRY_REGRESSIONS' if passed else 'FAIL_TERRAIN_REGRESSION',
        cases=[row[0] for row in cases],checks=sum(row[1].get('checks',0) for row in cases),
        legacy_test_cases_preserved=True,native_execution=False)
    m.write_new(stage/'asset_result.json',result)
    print(json.dumps(dict(status=result['status'],checks=result['checks'])))
    assert passed


def main():
    parser=argparse.ArgumentParser();parser.add_argument('case',choices=['assets','parallel','field-shaders']);args=parser.parse_args()
    if args.case=='assets':return assets()
    if args.case=='parallel':
        m,driver=load('Tests/deterministic_terrain_vertices.py','current_parallel_cpu')
        m.STAGE=ROOT/'multicore';m.STAGE.mkdir()
        m.write_new(m.STAGE/'derivation.json',dict(driver=m.common.artifact(driver),output_root_override=str(m.STAGE),
            original_driver_main_executed=False,native_execution=False))
        m.main('01')
    else:
        m,driver=load('Tests/original_lighting_field_shader.py','current_field_shader')
        m.ROOT=ROOT/'field_shader';m.ROOT.mkdir()
        m.write_new(m.ROOT/'derivation.json',dict(driver=m.ref(driver),output_root_override=str(m.ROOT),
            historical_output_paths_modified=False,native_execution=False))
        sys.argv=[str(driver),'--attempt','attempt01'];m.main()


if __name__=='__main__':main()
