"""Tiny file-only sidecar fixtures; no game, Host, SDK, window or network."""
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

PROJECT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(PROJECT/'tools'))
import retained_menu_suite_host_input as menu
from retained_host_runtime_input import _Files


class SidecarTests(unittest.TestCase):
    def setUp(self):
        self.root=Path(tempfile.mkdtemp(prefix='menu-sidecar-fixture-',dir=PROJECT/'Build'))
        self.addCleanup(self.tearDown)
        self.identifier='20990101T000000Z_0123456789ab'
        self.source=self.root/'Source/Assets/TinyPack'
        self.frozen=self.root/'Build/UiWindowHost'/self.identifier/'final/UIFrontEnd'
        self.source.mkdir(parents=True);self.frozen.mkdir(parents=True)
        self.entries=[]
        for name,data in [('background.packet',b'tiny-packet'),('textures/one.dds',b'tiny-texture')]:
            src=self.source/name;dst=self.frozen/name;src.parent.mkdir(parents=True,exist_ok=True);dst.parent.mkdir(parents=True,exist_ok=True)
            src.write_bytes(data);os.link(src,dst);os.chmod(src,stat.S_IREAD)
            self.entries.append(dict(relative_path=name,source=self.artifact(src),frozen=self.artifact(dst)))
        manifest=self.root/'assets.json'
        manifest.write_text(json.dumps(dict(schema='zerosis.original_frontend.assets.v1',native_execution=False,sdk_loaded=False,
            files=[e['source'] for e in self.entries])),encoding='utf-8')
        self.descriptor=dict(schema='zerosis.retained_menu_host.required_sidecar.v1',relative_root='UIFrontEnd',
            source_root=str(self.source),frozen_root=str(self.frozen),manifest=self.artifact(manifest),
            manifest_schema='zerosis.original_frontend.assets.v1',file_count=2,files=self.entries)

    def tearDown(self):
        # All aliases here belong to this tiny fixture. Never change an attribute
        # on a project/game/runtime source or a protected external donor.
        if not self.root.exists():return
        assert self.root.parent==PROJECT/'Build' and self.root.name.startswith('menu-sidecar-fixture-')
        assert self.root.resolve(strict=True).is_relative_to(PROJECT/'Build')
        for path in self.root.rglob('*'):
            assert not path.is_symlink() and not getattr(path.lstat(),'st_file_attributes',0)&0x400
            if path.is_file():os.chmod(path,stat.S_IREAD|stat.S_IWRITE)
        shutil.rmtree(self.root)

    @staticmethod
    def artifact(path):
        data=path.read_bytes()
        return _Files(check_metadata=True).verify(dict(path=str(path),bytes=len(data),sha256=hashlib.sha256(data).hexdigest()))

    def validate(self,descriptor=None):
        return menu.validate_required_sidecars(self.root,self.identifier,descriptor or self.descriptor,_Files(check_metadata=True))

    def test_dynamic_count_and_no_launch(self):
        with patch('subprocess.Popen',side_effect=AssertionError('launch forbidden')),patch('os.system',side_effect=AssertionError('launch forbidden')):
            result=self.validate()
        self.assertEqual(result['file_count'],2)
        self.assertFalse(result['host_sdk_clr_hwnd_gpu_game_executed'])
        self.assertFalse(result['actual_current_compiler_or_assets_approved'])

    def test_altered_source_bytes(self):
        src=Path(self.entries[0]['source']['path']);os.chmod(src,stat.S_IREAD|stat.S_IWRITE);src.write_bytes(b'altered')
        with self.assertRaises((RuntimeError,OSError)):self.validate()

    def test_missing_inventory(self):
        value=deepcopy(self.descriptor);value['files'].pop()
        with self.assertRaises(RuntimeError):self.validate(value)

    def test_extra_inventory(self):
        value=deepcopy(self.descriptor);value['files'].append(deepcopy(value['files'][0]))
        with self.assertRaises(RuntimeError):self.validate(value)

    def test_extraneous_tree_file(self):
        (self.frozen/'unexpected.packet').write_bytes(b'extra')
        with self.assertRaises(RuntimeError):self.validate()

    def test_extraneous_empty_directory(self):
        (self.frozen/'unexpected').mkdir()
        with self.assertRaises(RuntimeError):self.validate()

    def test_missing_frozen_file(self):
        dst=Path(self.entries[0]['frozen']['path']);os.chmod(dst,stat.S_IREAD|stat.S_IWRITE);dst.unlink()
        with self.assertRaises((RuntimeError,OSError)):self.validate()

    def test_alias_same_bytes_different_identity(self):
        dst=Path(self.entries[0]['frozen']['path']);data=dst.read_bytes()
        os.chmod(dst,stat.S_IREAD|stat.S_IWRITE);dst.unlink();dst.write_bytes(data);os.chmod(dst,stat.S_IREAD)
        os.chmod(Path(self.entries[0]['source']['path']),stat.S_IREAD)
        with self.assertRaises(RuntimeError):self.validate()

    def test_mutable_source_rejected(self):
        os.chmod(Path(self.entries[0]['source']['path']),stat.S_IREAD|stat.S_IWRITE)
        with self.assertRaises(RuntimeError):self.validate()

    def test_reparse_metadata_rejected(self):
        target=Path(self.entries[0]['frozen']['path']);original=Path.lstat
        def lstat(path):
            value=original(path)
            if path==target:
                fields={name:getattr(value,name) for name in dir(value) if name.startswith('st_')}
                fields['st_file_attributes']=fields.get('st_file_attributes',0)|0x400
                return SimpleNamespace(**fields)
            return value
        with patch.object(Path,'lstat',lstat),self.assertRaises(RuntimeError):self.validate()

    def test_wrong_frozen_root(self):
        value=deepcopy(self.descriptor);value['frozen_root']=str(self.root/'foreign')
        with self.assertRaises(RuntimeError):self.validate(value)

    def test_bool_count_not_integer(self):
        value=deepcopy(self.descriptor);value['file_count']=True
        with self.assertRaises(RuntimeError):self.validate(value)

    def test_path_aliases(self):
        for value in ('../x','x/../y','/x','C:/x','x\\y','x:stream','a//b','CON.txt','LPT1','x.','x ','x/*','x/\0'):
            with self.subTest(value=value),self.assertRaises(RuntimeError):menu.sidecar_relative_path(value)

    def test_inventory_path_traversal(self):
        value=deepcopy(self.descriptor);value['files'][0]['relative_path']='../escape'
        with self.assertRaises(RuntimeError):self.validate(value)

    def test_source_frozen_runtime_hardlink_transport(self):
        runtime=self.root/'Build/InteractiveGameRuntime/20990101T010000Z_0123456789ab';runtime.mkdir(parents=True)
        result=menu.materialize_required_sidecars(self.root,self.identifier,self.descriptor,runtime,_Files(check_metadata=True))
        self.assertEqual(result['file_count'],2);self.assertEqual(result['additional_unique_payload_bytes'],0)
        check=menu.verify_runtime_required_sidecars(self.root,self.identifier,self.descriptor,runtime,result,_Files(check_metadata=True))
        self.assertEqual(check['file_count'],2)
        self.assertEqual([Path(row['runtime']['path']).stat().st_ino for row in result['files']],
                         [Path(row['source']['path']).stat().st_ino for row in result['files']])
        with self.assertRaises(RuntimeError):menu.materialize_required_sidecars(self.root,self.identifier,self.descriptor,runtime,_Files(check_metadata=True))

    def test_runtime_extra_member_rejected(self):
        runtime=self.root/'Build/InteractiveGameRuntime/20990101T010000Z_0123456789ab';runtime.mkdir(parents=True)
        result=menu.materialize_required_sidecars(self.root,self.identifier,self.descriptor,runtime,_Files(check_metadata=True))
        (runtime/'UIFrontEnd/foreign.packet').write_bytes(b'foreign')
        with self.assertRaises(RuntimeError):menu.verify_runtime_required_sidecars(self.root,self.identifier,self.descriptor,runtime,result,_Files(check_metadata=True))

    def test_custom_staging_uses_dynamic_shared_gate(self):
        import contextlib,io
        import stage_original_menu_sidecar as stage
        identifier='20990101T020000Z_0123456789ab';root=self.root/'Build/UiWindowHost'/identifier
        image=root/'final/ZeroSisHost_x64.exe';image.parent.mkdir(parents=True);image.write_bytes(b'file-only fixture never loaded')
        report=self.root/'evidence/ui_window_host'/identifier/'build_result.json';report.parent.mkdir(parents=True)
        doc=dict(build_id=identifier,status='UI_WINDOW_HOST_CANDIDATE_BUILT',executable=self.artifact(image),
            **{field:False for field in menu.OFFLINE_FIELDS})
        report.write_text(json.dumps(doc),encoding='utf-8');output=self.root/'evidence/sidecar.json'
        with (patch.object(stage.build,'PROJECT',self.root),patch('subprocess.Popen',side_effect=AssertionError('launch forbidden')),
                contextlib.redirect_stdout(io.StringIO())):
            stage.main(['--build-report',str(report),'--report-sha256',hashlib.sha256(report.read_bytes()).hexdigest(),
                '--asset-manifest',self.descriptor['manifest']['path'],'--asset-manifest-sha256',self.descriptor['manifest']['sha256'],
                '--source-root',str(self.source),'--output',str(output)])
        result=json.loads(output.read_text());self.assertEqual(result['hardlinked_files'],2)
        self.assertEqual(result['sidecar_validation']['file_count'],2)


if __name__=='__main__':unittest.main()
