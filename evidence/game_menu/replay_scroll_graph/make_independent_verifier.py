"""Adapt the preserved prior independent verifier; never edit its original file."""
import hashlib
from pathlib import Path

STAGE=Path(__file__).absolute().parent
PROJECT=STAGE.parents[2]
source=PROJECT/'evidence/game_menu/replay_calendar_legend/verify_prepared_files.py'
assert hashlib.sha256(source.read_bytes()).hexdigest()=='70c83920212ed242925d9aae1d21b1d66cfa264353b840ebf99b32d44acaf914'
text=source.read_text('utf8')
begin=text.index("BUILD = '")
end=text.index('\n\n\ndef read',begin)
replacement='''import argparse
import re
cli=argparse.ArgumentParser()
for name in ('build','run','report-sha','profile-sha','host-sha'):
    cli.add_argument('--'+name,required=True)
args=cli.parse_args()
assert all(re.fullmatch(r'[0-9]{8}T[0-9]{6}Z_[0-9a-f]{12}',v) for v in (args.build,args.run))
assert all(re.fullmatch(r'[0-9a-f]{64}',v) for v in (args.report_sha,args.profile_sha,args.host_sha))
BUILD,RUN=args.build,args.run
REPORT_SHA,PROFILE_SHA,HOST_SHA=args.report_sha,args.profile_sha,args.host_sha
SDK_SHA='430f3122d0b555d6daae14aa7c011ef43ce8f978270477c8af596ca4b0493ab9' '''.rstrip()
text=text[:begin]+replacement+text[end:]
text=text.replace('zerosis.replay_calendar_legend.prepared_pair.v1','zerosis.replay_scroll_graph.prepared_pair.v1')
output=STAGE/'verify_prepared_files.py'
assert not output.exists()
with output.open('x',encoding='utf8') as stream:stream.write(text)
print('CREATED_NEW_INDEPENDENT_FILE_ONLY_VERIFIER')
