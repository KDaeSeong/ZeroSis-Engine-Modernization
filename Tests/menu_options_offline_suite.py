"""One bounded offline verification pass; never launches Host/GameCore/GUI."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

PROJECT=Path(__file__).resolve().parents[1]
EVIDENCE=PROJECT/'evidence/game_menu/offline_menu_suite/options_touch'


def main():
    inputs=[PROJECT/'Source/Host/UiScene.lua',PROJECT/'Source/Presentation/UiPresentationInput.lua',
        PROJECT/'Source/Presentation/UiMenuOptions.lua',PROJECT/'Source/Presentation/UiMapMenu.lua',
        *(PROJECT/'tools'/name for name in ('ui_pixel_scene.py','interactive_ui_driver.py','render_ui_popup.py'))]
    before={str(path):hashlib.sha256(path.read_bytes()).hexdigest() for path in inputs}
    commands=[(name,[sys.executable,'-B',str(PROJECT/'Tests'/name)]) for name in (
        'menu_options_contract.py','test_save_menu.py','menu_options_scene.py','menu_options_map_scene.py',
        'menu_options_renderer_contract.py','menu_options_lifecycle_source.py')]
    for module in ('owned_save_delete_scene','owned_save_overwrite_scene'):
        code=("import sys,json;sys.path.insert(0,"+repr(str(PROJECT/'Tests'))+");import "+module+
              " as m;r=m.verify_component();print(json.dumps({k:r[k] for k in ('status','checks','original_sources_unchanged')}))")
        commands.append((module,[sys.executable,'-B','-c',code]))
    rows=[];EVIDENCE.mkdir(parents=True,exist_ok=True)
    for name,command in commands:
        started=time.monotonic()
        result=subprocess.run(command,cwd=PROJECT,capture_output=True,timeout=180,
                              creationflags=subprocess.CREATE_NO_WINDOW)
        output=(result.stdout+result.stderr).decode('utf-8',errors='replace')
        log=EVIDENCE/(name.replace('.py','')+'_suite.log')
        log.write_text(output,encoding='utf-8')
        rows.append(dict(test=name,exit_code=result.returncode,elapsed_seconds=round(time.monotonic()-started,3),
            log=str(log),log_sha256=hashlib.sha256(log.read_bytes()).hexdigest(),log_bytes=log.stat().st_size))
        print(json.dumps(dict(test=name,exit_code=result.returncode)),flush=True)
        if result.returncode:break
    unchanged=before=={str(path):hashlib.sha256(path.read_bytes()).hexdigest() for path in inputs}
    passed=unchanged and len(rows)==len(commands) and all(row['exit_code']==0 for row in rows)
    report=dict(schema='zerosis.private_menu.offline_suite.v1',status='PASS' if passed else 'FAIL',tests=rows,
        shared_source_sha256=before,shared_sources_unchanged=unchanged,host_executed=False,sdk_executed=False,
        hwnd_created=False,gpu_executed=False,images_rendered=False,retail_settings_or_saves_written=False)
    (EVIDENCE/'offline_suite_tests.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    if not passed:raise SystemExit(1)


if __name__=='__main__':main()
