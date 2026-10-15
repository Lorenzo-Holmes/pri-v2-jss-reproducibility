"""Candidate-category and construction tables from the retained controlled records."""
from pathlib import Path
import sys,json,csv,statistics,argparse
from fractions import Fraction
ROOT=Path(__file__).resolve().parents[1]
sys.dont_write_bytecode=True
sys.path.insert(0,str(ROOT/'analysis'))
import analyze_records as record_analysis

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,default=ROOT/'outputs/candidate_analysis')
    OUT=p.parse_args().output
    OUT.mkdir(parents=True,exist_ok=False)
    def write(n,x): (OUT/n).write_text(json.dumps(x,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    def table(n,rs):
        with (OUT/n).open('w',encoding='utf-8',newline='') as f:
            w=csv.DictWriter(f,fieldnames=list(rs[0]));w.writeheader();w.writerows(rs)
    read=lambda n:json.loads((ROOT/n).read_text(encoding='utf-8'))
    source_records,observations,predictions=[read(record_analysis.CONTROLLED_DATA_DIR+n+'.json') for n in ('programs','observations','predictions')]
    representations,tie=[read(record_analysis.ROBUSTNESS_DIR+n+'.json') for n in ('DEDUP_ROBUSTNESS','TIE_ORDER_ROBUSTNESS')]
    rows,meta=record_analysis.validate_inputs(source_records,observations,predictions)
    all_reps=[('original',None)]+[(v['signature']+'/'+v['representative'],record_analysis.dedup_ids(v,rows)) for v in representations['variants']]
    short=['O','Mr','Me','Fr','Fe','Pr','Pe']
    state_table=[]
    cat=[]
    family_table=[]
    rep_metrics={}
    for code,(name,ids) in zip(short,all_reps):
        metrics={}
        for fid,sides in rows.items():
            metrics[fid]={}
            for state,rr in sides.items():
                rr=[r for r in rr if ids is None or r['candidate_id'] in ids[fid]]
                m=record_analysis.state_metrics(rr);metrics[fid][state]=m
                cat.append({'representation':name,'structure':fid,'state':state,**m})
        rep_metrics[name]=metrics
        for state in record_analysis.PRESERVATION_STATES:
            mm=[x[state] for x in metrics.values()];ds=[x['delta'] for x in mm]
            state_table.append({'code':code,'representation':name,'state':state,'candidate_count':sum(x['menu_size'] for x in mm),'T_R':sum(x['T_R'] for x in mm),'T_E':sum(x['T_E'] for x in mm),'mean_delta':statistics.mean(ds),'mean_expected_delta':float(sum(Fraction(x['mu_fraction']) for x in mm)/96),'harm':sum(d>0 for d in ds),'tie':sum(d==0 for d in ds),'benefit':sum(d<0 for d in ds),'v':sum(x['v'] for x in mm),'k_minus':sum(x['k_minus'] for x in mm),'k_zero':sum(x['k_zero'] for x in mm),'k_plus':sum(x['k_plus'] for x in mm),'higher_prefix':sum(x['higher_prefix'] for x in mm)})
    table('state_specific_representations.csv',state_table)
    table('candidate_categories_full.csv',cat)
    o=rep_metrics['original']
    ch=rep_metrics['paired_contract_endpoint/recorded']
    for f in source_records['families']:
        fid=f['family_id'];s=rows[fid];v,i=[o[fid][x] for x in record_analysis.PRESERVATION_STATES]
        family_table.append({'structure':fid,'template':f['mechanism'],'context':f['context'],'edit_budget':f['states'][0]['definition']['B'],'menu':len(f['candidates']),'valid_Pvalid':sum(r['valid'] for r in s[record_analysis.PRESERVATION_STATES[0]]),'valid_Pinvalid':sum(r['valid'] for r in s[record_analysis.PRESERVATION_STATES[1]]),'unique_paired_endpoints':ch[fid][record_analysis.PRESERVATION_STATES[0]]['menu_size'],'D':i['delta']-v['delta']})
    table('construction_96.csv',family_table)
    # Exact numerators in retained per-structure distributions; rates are equally weighted by structure.
    pos=[]
    for rec in tie['records']:
        if rec['interaction']['original']<=0:continue
        ds=[(v[3]-v[2])-(v[1]-v[0]) for v in rec['values']]
        pos.append({'structure':rec['structure'],'method':rec['method'],'draws':len(ds),'negative':sum(d<0 for d in ds),'nonpositive':sum(d<=0 for d in ds)})
    table('tie_sign_counts.csv',pos)
    tie_summary={'positive_historical_structures':len(pos),'pooled_negative':sum(x['negative'] for x in pos),'pooled_draws':sum(x['draws'] for x in pos),'negative_structure_count':sum(x['negative']>0 for x in pos),'equal_structure_negative_rate_fraction':str(sum(Fraction(x['negative'],x['draws']) for x in pos)/len(pos)),'equal_structure_nonpositive_rate_fraction':str(sum(Fraction(x['nonpositive'],x['draws']) for x in pos)/len(pos)),'negative_structures':[x for x in pos if x['negative']]}
    write('tie_sign_summary.json',tie_summary)
    examples=[next(f for f in source_records['families'] if f['family_id']=='PRI_00_0_literal_independent'),next(f for f in source_records['families'] if f['family_id']=='PRI_13_0_alias_independent'),next(f for f in source_records['families'] if ch[f['family_id']]['STATE_INVALID']['delta']<0)]
    worked=[]
    for f in examples:
        fid=f['family_id'];worked.append({'family':f,'original':o[fid],'paired_outcome_recorded':ch[fid],'rows':rows[fid]})
    write('worked_examples.json',worked)
    print(json.dumps({'state_summary':state_table,'tie':tie_summary,'worked_examples':[{k:v for k,v in x.items() if k in ('original','paired_outcome_recorded')}|{'id':x['family']['family_id']} for x in worked]},indent=2))


if __name__ == '__main__':
    main()
