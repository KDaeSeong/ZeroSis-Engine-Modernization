"""Run only after the exact final build report/hash has been supplied by root."""
from file_only_reuse import STAGE, PROJECT, BUILDER_SHA, load, current_builder
import argparse
import json


def main():
    current_builder()
    module = load('evidence/game_menu/offline_menu_suite/pair_preparation/attest_current_candidate.py',
        'ebe5a2a7d259d91c7a15f61cafe3902aace4c03c6cc37aaf7a38eb2eeda0ebc3',
        '_original_menu_final_attestor')
    if module.PROJECT != PROJECT:raise RuntimeError('Unexpected reused attestor project')
    module.STAGE = STAGE
    module.BUILDER_SHA = BUILDER_SHA
    module.main()
    cli = argparse.ArgumentParser(add_help=False)
    cli.add_argument('--build-report',required=True)
    cli.add_argument('--report-sha256',required=True)
    options = cli.parse_args()
    from pathlib import Path
    build = json.loads(Path(options.build_report).read_text(encoding='utf-8'))
    draft_path = STAGE/build['build_id']/'profile_draft.json'
    draft = json.loads(draft_path.read_text(encoding='utf-8'))
    draft.update(kind='compile_only_unregistered_menu_candidate',registered=False,
        eligible_for_registration=False,required_frontend_sidecar_count=62,
        prepared_runtime_sidecar_transport_integrated=False,
        preserved_active_profile='20261101T074006Z_c2fd2fe9be38',
        preserved_active_profile_matches_current_production_sources=False,
        full_native_or_original_ui_acceptance=False)
    draft['pending_fields'] += ['required_frontend_sidecar_manifest_and_transport_support']
    draft_path.write_text(json.dumps(draft,indent=2)+'\n',encoding='utf-8')


if __name__ == '__main__':main()
