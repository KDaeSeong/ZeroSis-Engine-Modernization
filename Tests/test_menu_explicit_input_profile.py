"""File-only profile/current-source and exact sidecar transport boundary fixtures."""
from copy import deepcopy
import gzip
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import sys
import tempfile
import unittest
from unittest.mock import patch

PROJECT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(PROJECT/'tools'))
import retained_menu_suite_host_input as menu
import retained_host_runtime_input as retained
import prepare_latest_engine_pair as pair


class ProfileTests(unittest.TestCase):
    def setUp(self):
        self.root=Path(tempfile.mkdtemp(prefix='menu-profile-fixture-',dir=PROJECT/'Build'))
        self.addCleanup(self.cleanup)
        self.identifier='20990101T000000Z_abcdef012345'
        self.evidence=self.root/'evidence/profiles';self.evidence.mkdir(parents=True)
        self.code=self.root/'Source/Host/Tiny.h';self.code.parent.mkdir(parents=True)
        self.code.write_bytes(b'canonical compiled code')
        self.script=self.root/'tools/run_interactive_game.py';self.script.parent.mkdir();self.script.write_bytes(b'file only transport v1')
        self.code_before=self.artifact(self.code);self.script_before=self.artifact(self.script)
        self.source=self.root/'Source/Assets/TinyPack';self.source.mkdir(parents=True)
        self.frozen=self.root/'Build/UiWindowHost'/self.identifier/'final/UIFrontEnd';self.frozen.mkdir(parents=True)
        src=self.source/'background.packet';src.write_bytes(b'tiny immutable packet')
        dst=self.frozen/src.name;os.link(src,dst);os.chmod(src,stat.S_IREAD)
        source_row=self.artifact(src);frozen_row=self.artifact(dst)
        manifest=self.evidence/'assets.json';manifest.write_text(json.dumps(dict(schema='zerosis.original_frontend.assets.v2',
            native_execution=False,sdk_loaded=False,files=[source_row])),encoding='utf8')
        self.descriptor=dict(schema='zerosis.retained_menu_host.required_sidecar.v1',relative_root='UIFrontEnd',
            source_root=str(self.source),frozen_root=str(self.frozen),manifest=self.artifact(manifest),
            manifest_schema='zerosis.original_frontend.assets.v2',file_count=1,
            files=[dict(relative_path=src.name,source=source_row,frozen=frozen_row)])
        self.build=dict(build_id=self.identifier,current_source_inputs=[self.code_before,self.script_before,self.artifact(manifest)],
            compiler_inputs=[dict(self.code_before,origin=str(self.code))])
        report=self.root/'evidence/ui_window_host'/self.identifier/'build_result.json';report.parent.mkdir(parents=True)
        report.write_text(json.dumps(self.build),encoding='utf8')
        self.profile=dict(schema='zerosis.retained_menu_host.profile.v1',kind='retained_menu_suite',build_id=self.identifier,
            executable_bytes=123,executable_sha256='0'*64,catalog={},
            required_payloads=['ZeroSisUiScene','ExitConfirm','ExitConfirmLayout'],current_source_count=3,
            required_sidecar=self.descriptor,prepared_profile_only=True,globally_registered=False,native_execution=False)
        for name in ('report','attestation','run','audit','cleanup_plan','cleanup_result','retirement_ledger'):
            self.profile[name+'_path']=report.relative_to(self.root).as_posix()
            self.profile[name+'_sha256']=self.artifact(report)['sha256']
        self.path=self.evidence/'profile.json';self.save_profile()

    def cleanup(self):
        assert self.root.parent==PROJECT/'Build' and self.root.name.startswith('menu-profile-fixture-')
        if self.root.exists():
            assert self.root.resolve(strict=True).is_relative_to(PROJECT/'Build')
            for path in self.root.rglob('*'):
                assert not path.is_symlink() and not getattr(path.lstat(),'st_file_attributes',0)&0x400
                if path.is_file():os.chmod(path,stat.S_IREAD|stat.S_IWRITE)
            shutil.rmtree(self.root)

    @staticmethod
    def artifact(path):
        path=Path(path);raw=path.read_bytes()
        return retained._Files(check_metadata=True).verify(dict(path=str(path),bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest()))

    def save_profile(self):
        self.path.write_text(json.dumps(self.profile),encoding='utf8');self.profile_ref=self.artifact(self.path)

    def spec(self):return menu.explicit_host_spec(self.root,self.profile_ref,retained._Files(check_metadata=True))
    def check(self,spec=None):return menu.check_current_source_closure(self.build,self.root,spec or self.spec(),retained._Files(check_metadata=True))

    def revision(self):
        before=self.script.read_bytes();self.script.write_bytes(b'file only transport v2')
        backup=self.evidence/'before.py.gz'
        with gzip.open(backup,'xb') as stream:stream.write(before)
        entry=dict(role='FILE_ONLY_RUNTIME_TRANSPORT',before=self.script_before,after=self.artifact(self.script),backup=self.artifact(backup))
        ledger=dict(schema='zerosis.menu_host.operational_revisions.v1',build_id=self.identifier,native_execution=False,
            compiled_or_asset_inputs_waived=False,revisions=[entry])
        path=self.evidence/'revisions.json';path.write_text(json.dumps(ledger),encoding='utf8')
        self.profile['operational_revisions']=self.artifact(path);self.save_profile()
        return entry,ledger,path

    def update_ledger(self,ledger,path):
        path.write_text(json.dumps(ledger),encoding='utf8');self.profile['operational_revisions']=self.artifact(path);self.save_profile()

    def test_current_sources_and_v2_sidecar(self):
        before=deepcopy(retained.MENU_PROFILE_PINS)
        with patch('subprocess.Popen',side_effect=AssertionError('native launch forbidden')):
            result=self.check()
        self.assertEqual(result['source_count'],3);self.assertEqual(result['required_sidecar_validation']['file_count'],1)
        self.assertFalse(result['compiled_or_asset_inputs_waived']);self.assertEqual(retained.MENU_PROFILE_PINS,before)

    def test_explicit_profile_hash_tamper(self):
        self.path.write_text(self.path.read_text()+' ')
        with self.assertRaises(RuntimeError):self.spec()

    def test_profile_mutation_after_selection(self):
        spec=self.spec();self.profile['executable_bytes']+=1;self.save_profile()
        with self.assertRaises(RuntimeError):self.check(spec)

    def test_profile_requires_hold_and_no_registration(self):
        for name,value in [('native_execution',True),('globally_registered',True),('prepared_profile_only',False)]:
            with self.subTest(name=name):
                before=self.profile[name];self.profile[name]=value;self.save_profile()
                with self.assertRaises(RuntimeError):self.spec()
                self.profile[name]=before
        self.save_profile()

    def test_profile_rejects_traversal_proof_and_foreign_report(self):
        for value in ('../escaped.json','evidence/ui_window_host/foreign/build_result.json'):
            with self.subTest(value=value):
                self.profile['report_path']=value;self.save_profile()
                with self.assertRaises(RuntimeError):self.spec()

    def test_profile_rejects_duplicate_json_keys(self):
        text=self.path.read_text();self.path.write_text(text[:-1]+',"native_execution":false}')
        self.profile_ref=self.artifact(self.path)
        with self.assertRaises(RuntimeError):self.spec()

    def test_sidecar_manifest_must_be_bound_to_actual_host_source_closure(self):
        extra=self.evidence/'unrelated-assets.json';extra.write_bytes(Path(self.descriptor['manifest']['path']).read_bytes())
        self.profile['required_sidecar']['manifest']=self.artifact(extra);self.save_profile()
        with self.assertRaises(RuntimeError):self.check()

    def test_current_compiled_code_mismatch_fails(self):
        self.code.write_bytes(b'changed compiled code')
        with self.assertRaises(RuntimeError):self.check()

    def test_current_script_mismatch_without_ledger_fails(self):
        self.script.write_bytes(b'changed operational code')
        with self.assertRaises(RuntimeError):self.check()

    def test_typed_operational_revision_actual_gzip_and_after_bytes(self):
        self.revision();result=self.check()
        self.assertEqual(result['typed_operational_revision_count'],1)
        after=[r for r in result['verified_inputs'] if r['path']==str(self.script)][0]
        self.assertEqual(after['sha256'],hashlib.sha256(self.script.read_bytes()).hexdigest())
        self.assertFalse(result['compiled_or_asset_inputs_waived'])

    def test_typed_revision_cannot_waive_compiled_input(self):
        entry,ledger,path=self.revision();self.build['compiler_inputs'].append(dict(self.script_before,origin=str(self.script)))
        # Bind the deliberately different fixture report, then check the actual compiled exclusion.
        report=self.root/self.profile['report_path'];report.write_text(json.dumps(self.build))
        self.profile['report_sha256']=self.artifact(report)['sha256'];self.save_profile()
        with self.assertRaises(RuntimeError):self.check()

    def test_typed_revision_wrong_before_backup_after_or_role_fails(self):
        entry,ledger,path=self.revision()
        for name,value in [('role','UNBOUNDED'),('before',dict(entry['before'],sha256='0'*64)),
                           ('after',dict(entry['after'],sha256='0'*64)),('backup',dict(entry['backup'],sha256='0'*64))]:
            with self.subTest(name=name):
                modified=deepcopy(ledger);modified['revisions'][0][name]=value;self.update_ledger(modified,path)
                with self.assertRaises(RuntimeError):self.check()
        self.update_ledger(ledger,path)
        backup=Path(entry['backup']['path']);backup.write_bytes(gzip.compress(b'wrong predecessor'))
        ledger['revisions'][0]['backup']=self.artifact(backup);self.update_ledger(ledger,path)
        with self.assertRaises(RuntimeError):self.check()

    def test_typed_revision_cannot_hide_changed_code(self):
        self.revision();self.code.write_bytes(b'changed actual compiled source')
        with self.assertRaises(RuntimeError):self.check()

    def test_exact_guard_and_real_tiny_sidecar_materialization(self):
        runtime=self.root/'Build/InteractiveGameRuntime/20990101T010000Z_0123456789ab';runtime.mkdir(parents=True)
        one=self.evidence/'one.bin';two=self.evidence/'two.bin';one.write_bytes(b'one');two.write_bytes(b'two')
        with patch.object(pair.base,'PROJECT',self.root):
            guard=pair.PairGuard([self.artifact(one),self.artifact(two)],self.descriptor)
            guard.run_id=runtime.name
            actual_link=os.link
            def guarded_link(source,target,*args,**kwargs):
                guard.audit('os.link',(str(source),str(target),-1,-1));return actual_link(source,target,*args,**kwargs)
            with patch.object(os,'link',guarded_link),patch('subprocess.Popen',side_effect=AssertionError('native launch forbidden')):
                result=menu.materialize_required_sidecars(self.root,self.identifier,self.descriptor,runtime,retained._Files(check_metadata=True))
            self.assertEqual(result['file_count'],1);self.assertEqual(guard.native_attempts,0);self.assertEqual(guard.denied,[])
            with self.assertRaises(RuntimeError):guard.audit('os.link',(str(self.frozen/'background.packet'),str(runtime/'foreign.packet'),-1,-1))

    def test_explicit_runner_requires_preparation_and_matching_report(self):
        import run_interactive_game as runner
        with patch.object(sys,'argv',['run_interactive_game.py','--host-build',str(self.root/self.profile['report_path']),
                '--host-input-profile',str(self.path),'--host-input-profile-sha256',self.profile_ref['sha256'],'--smoke']),                patch('subprocess.Popen',side_effect=AssertionError('native launch forbidden')),self.assertRaises(SystemExit):
            runner.main()


if __name__=='__main__':unittest.main()
