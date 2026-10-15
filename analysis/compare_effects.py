"""Compare predicted effect sets, observed endpoints, and first-valid ranks."""
from pathlib import Path
from collections import Counter, defaultdict
import argparse, csv, json
from input_data import ROOT

METHODS = ['reference', 'union', 'complex', 'exact']
def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--data-root',type=Path,default=ROOT)
    ap.add_argument('--output',type=Path,required=True)
    args=ap.parse_args()
    if args.output.exists(): raise SystemExit('Output already exists; use a fresh directory.')
    prefix=args.data_root/'data/controlled'
    inputs={n:(prefix/n).read_bytes() for n in ['programs.json','predictions.json','observations.json']}
    recorded=json.loads(inputs['programs.json']);prediction=json.loads(inputs['predictions.json'])
    observations=json.loads(inputs['observations.json']);rows=observations['rows'];pred=prediction['rows']
    families={f['family_id']:f for f in recorded['families']}
    candidates={(f['family_id'],c['candidate_id']):c for f in recorded['families'] for c in f['candidates']}
    definitions={s['state_id']:s['definition'] for f in recorded['families'] for s in f['states']}
    pm={(r['family_id'],r['candidate_id']):r for r in pred}
    assert len(pm)==len(pred), 'Duplicate prediction identities'
    assert len(families)==len(recorded['families']), 'Duplicate structure identities'
    assert set(pm)==set(candidates), 'Predictions and candidate menus differ'
    expected={(f['family_id'],s['condition'],c['candidate_id']) for f in recorded['families'] for s in f['states'] for c in f['candidates']}
    actual={(r['family_id'],r['condition'],r['candidate_id']) for r in rows}
    assert len(actual)==len(rows) and actual==expected, 'Observation identities differ from paired candidate menus'
    counts=Counter();extra=Counter();totals=defaultdict(Counter);groups=defaultdict(list);pairs=defaultdict(dict)
    for r in rows:
        ident=(r['family_id'],r['candidate_id']);pr=pm[ident];definition=definitions[r['state_id']]
        assert r['predictions']==pr['predictions']
        assert (r['relevance'],r['base_rank'],r['patched_source'])==(pr['relevance'],pr['base_rank'],pr['patched_source'])
        e=set(r['E']);co=set(pr['predictions']['complex']['observers']);un=set(pr['predictions']['union']['observers'])
        assert e<=co<=un, (ident,r['state_id'])
        counts['nested_endpoint_rows']+=1
        extra['union']+=len(un-e);extra['complex']+=len(co-e)
        ex=r['candidate_execution'];base=r['original_execution']
        normative=definition['independent_P']
        eb={k for k in normative if ex['observers'][k]!=base['observers'][k]}
        vb={k for k,v in normative.items() if base['observers'][k]!=v}
        vc={k for k,v in normative.items() if ex['observers'][k]!=v}
        assert (eb,vc,vc-vb,vb-vc)==(e,set(r['V']),set(r['N']),set(r['C']))
        c=candidates[ident];allowed=definition['independent_A']['allowed_ops']
        edits_allowed=c['cost']<=definition['B'] and all(edit['op'] in allowed.get(edit['site'],[]) for edit in c['edits'])
        valid=edits_allowed and not ex['error'] and bool(ex['state']['goal']) and not vc
        assert valid==r['contract_valid'], (ident,'validity')
        counts['independently_recomputed_G_P_A_labels']+=1
        groups[r['state_id']].append(r);pairs[ident][r['condition']]=r
    for pr in pred:
        counts['strict_complex_subset_union_prediction_rows']+=set(pr['predictions']['complex']['observers'])<set(pr['predictions']['union']['observers'])
    rankrows=[];rankmap={}
    for sid,rs in sorted(groups.items()):
        assert len({r['base_rank'] for r in rs})==len(rs), 'Reference priority not unique'
        out={'family_id':rs[0]['family_id'],'state':rs[0]['condition'],'state_id':sid,'candidate_count':len(rs),'valid_count':sum(r['contract_valid'] for r in rs)}
        for method in METHODS:
            def key(r):
                effect=[] if method=='reference' else r['E'] if method=='exact' else pm[(r['family_id'],r['candidate_id'])]['predictions'][method]['observers']
                return (-r['relevance'],len(effect),r['base_rank'])
            ordered=sorted(rs,key=key)
            first=next((i,r) for i,r in enumerate(ordered,1) if r['contract_valid'])
            out[method]=first[0];out[method+'_first_candidate']=first[1]['candidate_id']
            totals[out['state']][method]+=first[0]
        rankrows.append(out);rankmap[sid]=out
    changes={}
    for state in ['STATE_VALID','STATE_INVALID']:
        for before,after in [('reference','union'),('reference','complex'),('reference','exact'),('union','complex'),('complex','exact')]:
            ds=[r[after]-r[before] for r in rankrows if r['state']==state]
            changes[state+':'+before+'->'+after]={'harm':sum(d>0 for d in ds),'tie':sum(d==0 for d in ds),'benefit':sum(d<0 for d in ds)}
    control_keys=['api','args','kwargs','result','error','exception','scalar_return']
    for pair in pairs.values():
        a,b=pair['STATE_VALID'],pair['STATE_INVALID']
        counts['paired_validity_changed']+=a['contract_valid']!=b['contract_valid']
        counts['paired_E_cardinality_changed']+=len(a['E'])!=len(b['E'])
        controls=lambda r:[{k:t.get(k) for k in control_keys} for t in r['candidate_execution']['trace']]
        counts['paired_candidate_control_sequence_changed']+=controls(a)!=controls(b)
    counts['trace_events_in_unmodified_and_candidate_executions']=sum(len(r['candidate_execution']['trace']) for r in rows)+sum(len(b['execution']['trace']) for b in observations['initials'])
    totals=dict(totals)
    result={'prediction_source':'saved_records',
        'input_files':sorted(inputs),
        'counts':dict(counts),'extra_labels_summed_over_candidate_state_endpoints':dict(extra),
        'first_valid_totals':{k:dict(v) for k,v in totals.items()},'pairwise_order_changes':changes}
    args.output.mkdir(parents=True,exist_ok=False)
    (args.output/'effect_summary.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    with (args.output/'first_valid_by_state.csv').open('w',encoding='utf-8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=rankrows[0].keys());w.writeheader();w.writerows(rankrows)
    with (args.output/'first_valid_totals.csv').open('w',encoding='utf-8',newline='') as f:
        w=csv.writer(f);w.writerow(['state','structures']+METHODS)
        for state in ['STATE_VALID','STATE_INVALID']:w.writerow([state,96]+[totals[state][m] for m in METHODS])
    print(json.dumps(result,ensure_ascii=False,indent=2))
if __name__=='__main__': main()
