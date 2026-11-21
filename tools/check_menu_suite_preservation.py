"""Rehash protected originals and explain every retained hardlink increment."""
from __future__ import annotations
import argparse
from collections import Counter
import json
import os
from pathlib import Path
import re
import stat

import menu_suite_storage as audit


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--run-id',required=True);args=parser.parse_args()
    assert re.fullmatch(r'[0-9]{8}T[0-9]{6}Z_[0-9a-f]{12}',args.run_id)
    before=audit.storage.read(audit.STAGE/'protection_before.json')
    roots=[audit.PROJECT/'Build/UiWindowHost'/identifier for identifier in (
        '20261101T071815Z_de1c20f8b14d','20261101T074006Z_c2fd2fe9be38')]
    roots.extend((audit.PROJECT/'Build/InteractiveGameRuntime'/args.run_id,
                  audit.PROJECT/'evidence/interactive_game'/args.run_id))
    assert all(root.is_dir() and root.is_relative_to(audit.PROJECT) for root in roots)
    new_links=Counter()
    for root in roots:
        for directory,dirs,files in os.walk(root):
            for name in dirs:
                info=os.stat(Path(directory)/name,follow_symlinks=False)
                assert not info.st_file_attributes&stat.FILE_ATTRIBUTE_REPARSE_POINT
            for name in files:
                value=audit.storage.ordinary(Path(directory)/name)
                new_links[(value.st_dev,value.st_ino)]+=1
    value=audit.verify()
    assert value['status']=='PASS',value['content_or_identity_differences']
    changes={audit.storage.key(row['path']):row for row in value['observed_link_count_changes']}
    expected_changes=[]
    for row in before['protected_artifacts']:
        increment=new_links[tuple(row['file_identity'])]
        current=audit.storage.metadata(audit.storage.ordinary(row['path']))
        assert current['links']-row['links']==increment,(row['path'],row['links'],current['links'],increment)
        if increment:expected_changes.append(dict(path=row['path'],added_owned_aliases=increment,before=row['links'],after=current['links']))
    value.update(schema='zerosis.menu_suite.protection_after.v1',run_id=args.run_id,
                 observed_link_changes_match_exact_owned_roots=True,owned_link_roots=list(map(str,roots)),
                 expected_link_changes=expected_changes,protected_unique_ids=before['unique_file_ids'],
                 protected_unique_allocated_bytes=before['unique_allocated_bytes'])
    audit.write_new(audit.STAGE/'protection_after.json',value)
    print(json.dumps(dict(status=value['status'],protected_paths=value['protected_paths'],
                         protected_unique_ids=before['unique_file_ids'],explained_alias_paths=len(expected_changes),
                         source_default_originals_and_saves_unchanged=True)))


if __name__=='__main__':main()
