"""Format publication tables from the saved rank-analysis summary."""
from pathlib import Path
import argparse, csv, json

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--analysis',type=Path,default=Path(__file__).resolve().parents[1]/'results',
                   help='Directory containing the calculated analysis results')
    a=p.parse_args();x=json.loads((a.analysis/'rank_analysis/rank_summary.json').read_text())
    trans={(r['state'],r['before'],r['after']):r for r in x['first_valid_transitions']}
    rows=[]
    for r in x['first_valid_summary']:
        t=trans.get((r['state'],'reference',r['method']))
        rows.append({'state':r['state'],'method':r['method'],'n_structures':r['n'],'sum_T':r['sum'],'mean_T':r['mean'],'min_T':r['minimum'],'median_T':r['median'],'max_T':r['maximum'],'p05_T':r['p05'],'p95_T':r['p95'],'harm_vs_R':t['harm'] if t else 0,'tie_vs_R':t['tie'] if t else r['n'],'benefit_vs_R':t['benefit'] if t else 0})
    strict=[]
    for s,c in x['endpoint_relation_counts'].items():
        n=sum(c.values());ec=c.get('E=Complex=Union',0)+c.get('E=Complex<Union',0);eu=c.get('E=Complex=Union',0)
        strict.append({'state':s,'candidate_state_endpoint_denominator':n,'E_equal_Complex':ec,'E_strict_subset_Complex':n-ec,'E_equal_Union':eu,'E_strict_subset_Union':n-eu,'Complex_strict_subset_Union':c.get('E<Complex<Union',0)+c.get('E=Complex<Union',0)})
    for name,data in [('table_four_orders.csv',rows),('table_endpoint_inclusion.csv',strict)]:
        with (a.analysis/name).open('w',newline='',encoding='utf-8') as f:
            w=csv.DictWriter(f,fieldnames=list(data[0]));w.writeheader();w.writerows(data)


if __name__ == '__main__':
    main()
