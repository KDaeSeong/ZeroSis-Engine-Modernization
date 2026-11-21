"""Inventory direct startup child owners and the limited concrete destructor evidence."""
import json
import re
from pathlib import Path
from collect_baseline import PROJECT
from probe_world_builder import artifact
from build_bootstrap_component import body
from define_startup_owners_patches import PLAYER,TEAM,UTILITY,baseline_text,player_owners


def deleted_fields(text):
    return sorted(set(re.findall(r'(?:SAFE_DELETE\(|delete\s+)(m_p\w+)',text)))


def main():
    root=PROJECT/'Source/SDK_BNW_x64'
    original=body(baseline_text(PLAYER),'CvPlayer::~CvPlayer()')
    player=(root/PLAYER).read_bytes().decode('latin1')
    candidate=body(player,'CvPlayer::~CvPlayer()')
    fields={r[0] for r in player_owners()}
    helpers=[]
    for relative,signatures in {
        'CvGameCoreDLL_Expansion2/CvCultureClasses.cpp':('CvPlayerCulture::CvPlayerCulture(void)','CvPlayerCulture::~CvPlayerCulture(void)'),
        'CvGameCoreDLL_Expansion2/CvTechClasses.cpp':('CvTeamTechs::CvTeamTechs()','CvTeamTechs::~CvTeamTechs(void)','void CvTeamTechs::Uninit()')}.items():
        p=root/relative;t=p.read_bytes().decode('latin1')
        for sig in signatures:helpers.append({'source':artifact(p),'signature':sig,'body':body(t,sig).replace('\r\n','\n')})
    report={'status':'STARTUP_DIRECT_OWNERS_INVENTORIED_NOT_TRANSITIVE_LIFETIME_PROOF',
            'auditor':artifact(Path(__file__).resolve()),'sources':[artifact(root/p) for p in (PLAYER,TEAM,UTILITY)],
            'player_owners':[{'field':f,'allocation':a,'type':t} for f,a,t in player_owners()],
            'original_missing_player_deletes':sorted(fields-set(deleted_fields(original))),
            'candidate_missing_player_deletes':sorted(fields-set(deleted_fields(candidate))),
            'candidate_scoped_children':re.findall(r'std::unique_ptr<\w+> owned_(m_p\w+)\(',body(player,'CvPlayer::CvPlayer()')),
            'player_uninit_deletes_culture':bool(re.search(r'(?:SAFE_DELETE\(|delete\s+)m_pCulture',body(player,'void CvPlayer::uninit()'))),
            'selected_concrete_child_bodies':helpers,'all_nested_child_destructors_audited':False,
            'whole_gc_lifecycle_verified':False,'gamecore_loaded':False,'game_launched':False}
    out=PROJECT/'evidence/startup_owners/source_audit.json'
    out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:report[k] for k in ('status','original_missing_player_deletes','candidate_missing_player_deletes')}))


if __name__=='__main__':main()
