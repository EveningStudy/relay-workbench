"""Strict third-look latency gate; does not regenerate global reports or media."""
import json
from pathlib import Path
import yaml


def assess(folder,display_mode='crisp'):
    if display_mode not in ('crisp','voxel'):raise ValueError('Unknown display mode')
    folder=Path(folder);raw=json.loads((folder/'raw.json').read_text())
    before=Path('data/perf/m17_final/nominal/raw.json')
    old=json.loads(before.read_text());after=raw['stages_ms']['capture_dom']
    style=yaml.safe_load((folder/'ui.yaml').read_text())
    browser=json.loads((folder/'browser.json').read_text())
    final_load=json.loads((folder/'contention.json').read_text())
    criteria={
        'p95_strictly_below_150_ms':after['p95'] is not None and after['p95']<150,
        'nonempty_cohort':after['n']>0,
        'idle_preflight_known':raw['load']['gpu_util_before'] is not None,
        'no_detected_contention':not raw['load']['contended'] and not final_load['contended'],
        'requested_display_default':bool(style['crisp_live']['enabled'])==(display_mode=='crisp'),
        'requested_display_nonempty':((raw['crisp_live']['points']['max'] or 0)>0 if display_mode=='crisp' else
            any(s.get('live_display_mode')=='voxel' and s.get('live_voxel_points',0)>0 for s in browser['samples'])),
        'requested_mode_throughout':all(s.get('live_display_mode', 'crisp')==display_mode for s in browser['samples']),
        'browser_healthy':not browser['page_errors'] and not browser['console_errors'],
    }
    result={'pass':all(criteria.values()),'criteria':criteria,'display_mode':display_mode,
        'before':{'source':str(before),'capture_dom_ms':old['stages_ms']['capture_dom']},
        'after':{'source':str(folder/'raw.json'),'capture_dom_ms':after,'display_cost':raw['crisp_live']},
        'style':style,'target_ms':150,
        'scope':'Same nominal profile. Historical baseline is not a paired same-day control. DOM batch proxy only; crisp display pixel wait and cost reported separately. No physical display timing claim.'}
    (folder/'m22_gate.json').write_text(json.dumps(result,indent=2))
    return result
