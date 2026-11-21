"""Six frozen Python siblings must import without project producer fallbacks."""
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

PROJECT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(PROJECT/'tools'))
import prepare_latest_engine_pair as pair
import prepare_current_sdk_play as base


class FrozenSupportTests(unittest.TestCase):
    @contextmanager
    def frozen(self):
        root=Path(tempfile.mkdtemp(prefix='menu-support-closure-fixture-',dir=PROJECT/'Build'))
        try:
            assert root.parent==PROJECT/'Build' and root.resolve().is_relative_to(PROJECT/'Build')
            folder=root/'tools';folder.mkdir()
            inventory={}
            for name in base.TOOLS:
                path=folder/name;shutil.copy2(PROJECT/'tools'/name,path)
                inventory[name]=dict(path=str(path),bytes=path.stat().st_size,sha256=hashlib.sha256(path.read_bytes()).hexdigest())
            yield folder,inventory
        finally:
            assert root.resolve(strict=True).is_relative_to(PROJECT/'Build') and root.name.startswith('menu-support-closure-fixture-')
            for path in root.rglob('*'):
                assert not path.is_symlink() and not getattr(path.lstat(),'st_file_attributes',0)&0x400
            shutil.rmtree(root)

    def test_actual_six_import_graph_has_no_build_producer_fallback(self):
        with self.frozen() as (folder,inventory):
            result=pair.audit_python_support_closure(folder,inventory)
        self.assertEqual(result['module_count'],6)
        self.assertFalse(result['live_project_tools_fallback'])
        self.assertFalse(result['dynamic_imports'])
        self.assertNotIn('menu_options_assets.py',result['local_import_edges']['ui_pixel_scene.py'])
        self.assertEqual(result['local_import_edges']['civ5_ui_assets.py'],[])

    def test_isolated_python_actually_imports_all_six_exact_frozen_siblings(self):
        with self.frozen() as (folder,inventory):
            script="""
import hashlib,importlib,json,pathlib,sys
root=pathlib.Path(sys.argv[1]).resolve();sys.path.insert(0,str(root))
names=json.loads(sys.argv[2]);loaded={}
for name in names:
 module=importlib.import_module(pathlib.Path(name).stem)
 path=pathlib.Path(module.__file__).resolve()
 assert path.parent==root and path.name==name
 loaded[name]=hashlib.sha256(path.read_bytes()).hexdigest()
import civ5_ui_assets as shared
assert shared.supported_original_menu_handlers.__module__=='civ5_ui_assets'
assert shared.menu_slider_style.__module__=='civ5_ui_assets'
assert 'menu_options_assets' not in sys.modules and 'prepare_ui_popup_assets' not in sys.modules
assert not any('steamapps' in p.casefold() or 'Firaxis ModBuddy' in p and str(root) not in p for p in sys.path)
print(json.dumps(loaded,sort_keys=True))
"""
            result=subprocess.run([sys.executable,'-I','-B','-X','utf8','-c',script,str(folder),json.dumps(list(inventory))],
                cwd=folder,capture_output=True,text=True,encoding='utf8',timeout=30,check=False)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertEqual(json.loads(result.stdout),{name:row['sha256'] for name,row in inventory.items()})
            self.assertFalse(any(folder.rglob('__pycache__')))

    def test_missing_producer_import_is_rejected_by_actual_ast_closure(self):
        with self.frozen() as (folder,inventory):
            path=folder/'ui_pixel_scene.py';path.write_text(path.read_text()+'\nfrom menu_options_assets import menu_slider_style\n')
            inventory[path.name]=dict(path=str(path),bytes=path.stat().st_size,sha256=hashlib.sha256(path.read_bytes()).hexdigest())
            with self.assertRaisesRegex(RuntimeError,'menu_options_assets'):
                pair.audit_python_support_closure(folder,inventory)


if __name__=='__main__':unittest.main()
