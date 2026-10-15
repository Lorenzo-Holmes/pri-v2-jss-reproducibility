"""Candidate categories, budgets, and sensitivity from recorded observations."""
from __future__ import annotations
import argparse
import ast
import csv
import json
import statistics
from collections import Counter
from fractions import Fraction
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
from input_data import record_key
CONTROLLED_DATA_DIR = 'data/controlled/'
ROBUSTNESS_DIR = 'data/robustness/'
PRESERVATION_STATES = ('STATE_VALID', 'STATE_INVALID')

def require(ok: bool, message: str) -> None:
    if not ok:
        raise ValueError(message)


def keyed(rows: list[dict], keys: tuple[str, ...]) -> dict:
    result = {tuple(r[k] for k in keys): r for r in rows}
    require(len(result) == len(rows), 'Duplicate keys: ' + str(keys))
    return result

def summary(values: list[float]) -> dict:
    q = statistics.quantiles(values, n=4, method='inclusive') if len(values) > 1 else [values[0]] * 3
    return {'n': len(values), 'mean': statistics.mean(values), 'median': statistics.median(values),
            'q1': q[0], 'q3': q[2], 'minimum': min(values), 'maximum': max(values),
            'positive': sum(v > 0 for v in values), 'zero': sum(v == 0 for v in values),
            'negative': sum(v < 0 for v in values)}

def table(path: Path, rows: list[dict]) -> None:
    require(bool(rows), 'Empty table: ' + path.name)
    with path.open('w', encoding='utf-8', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

def validate_inputs(source: dict, observations: dict, predictions: dict) -> tuple[dict, dict]:
    observations_by_state = keyed(observations['rows'], ('family_id', 'condition', 'candidate_id'))
    predictions_by_candidate = keyed(predictions['rows'], ('family_id', 'candidate_id'))
    allrows, meta, visited, pred_visited = {}, {}, set(), set()
    checks = Counter()
    for family in source['families']:
        fid = family['family_id']
        require(fid not in meta, 'Duplicate family')
        meta[fid] = {'template': family['mechanism'], 'context': family['context']}
        require(tuple(s['condition'] for s in family['states']) == PRESERVATION_STATES, fid + ': state order')
        a, b = [s['definition'] for s in family['states']]
        require({k:v for k,v in a.items() if k != 'initial_state'} ==
                {k:v for k,v in b.items() if k != 'initial_state'}, fid + ': paired requirements/program')
        require({k:v for k,v in a['initial_state'].items() if k != 'vault'} ==
                {k:v for k,v in b['initial_state'].items() if k != 'vault'}, fid + ': extra intervention')
        require((a['initial_state']['vault'], b['initial_state']['vault']) == (7, 0), fid + ': initial vault')
        ids = [c['candidate_id'] for c in family['candidates']]
        require(len(ids) == len(set(ids)), fid + ': duplicate candidates')
        allrows[fid] = {}
        for state in family['states']:
            s, m = state['condition'], state['definition']
            rows = []
            for rank, candidate in enumerate(family['candidates'], 1):
                key = (fid, s, candidate['candidate_id'])
                r, pr = observations_by_state[key], predictions_by_candidate[(fid, candidate['candidate_id'])]
                visited.add(key); pred_visited.add((fid, candidate['candidate_id']))
                require(r['state_id'] == state['state_id'], str(key) + ': state ID')
                require(r['base_rank'] == pr['base_rank'] == rank, str(key) + ': rank')
                require(r['relevance'] == pr['relevance'], str(key) + ': relevance')
                require(r['patched_source'] == pr['patched_source'] == candidate['patched_source'], str(key) + ': source')
                allowed = m['independent_A']['allowed_ops']
                edits_allowed = all(e['op'] in allowed.get(e['site'], []) for e in candidate['edits']) and candidate['cost'] <= m['B']
                require(edits_allowed, str(key) + ': edit constraints')
                ex, unmodified_execution = r['candidate_execution'], r['original_execution']
                obs, bo, obligations = ex['observers'], unmodified_execution['observers'], m['independent_P']
                vb = {p for p, value in obligations.items() if bo[p] != value}
                vc = {p for p, value in obligations.items() if obs[p] != value}
                effect = {p for p in obligations if obs[p] != bo[p]}
                derived = {'E': effect, 'V': vc, 'N': vc-vb, 'C': vb-vc, 'initial_V': vb}
                for name, value in derived.items():
                    require(set(r[name]) == value, str(key) + ': ' + name)
                require(bool(vb) == (s == 'STATE_INVALID'), str(key) + ': initial P-status')
                goal = ex['error'] is None and ex['state']['goal'] is True
                valid = bool(edits_allowed and goal and not vc)
                require(valid == r['contract_valid'], str(key) + ': validity')
                require((vb-vc) <= effect and (vc-vb) <= effect, str(key) + ': alignment')
                if valid:
                    require(effect == vb, str(key) + ': VALID_ENDPOINT_EFFECT_RELATION_FAILURE')
                    checks['valid_endpoint_effect_equalities'] += 1
                rows.append({'candidate_id': candidate['candidate_id'], 'base_rank': rank,
                             'relevance': r['relevance'], 'E': sorted(effect), 'valid': valid,
                             'initial_V': sorted(vb), 'source': candidate['patched_source'],
                             'outcome_signature': [edits_allowed, ex['error'], goal, obs, valid,
                                                    {k:sorted(v) for k,v in derived.items()}],
                             'full_state': ex['state']})
                checks['candidate_state_rows'] += 1
            require(len({record_key(r['initial_V']) for r in rows}) == 1, fid + ': inconsistent initial')
            allrows[fid][s] = rows
    require(visited == set(observations_by_state), 'Unmatched observation identities')
    require(pred_visited == set(predictions_by_candidate), 'Unmatched prediction identities')
    return allrows, {'meta': meta, 'checks': dict(checks)}

def state_metrics(rows: list[dict]) -> dict:
    valid = [r for r in rows if r['valid']]
    require(bool(valid), 'Unexpected no-valid endpoint in original/dedup menu')
    ref = sorted(rows, key=lambda r: (-r['relevance'], r['base_rank']))
    eff = sorted(rows, key=lambda r: (-r['relevance'], len(r['E']), r['base_rank']))
    tr = next(j for j,r in enumerate(ref, 1) if r['valid'])
    te = next(j for j,r in enumerate(eff, 1) if r['valid'])
    rv = max(r['relevance'] for r in valid)
    bucket = [r for r in rows if r['relevance'] == rv]
    good = [r for r in bucket if r['valid']]
    effects = {len(r['E']) for r in good}
    require(len(effects) == 1, 'EQUAL_VALID_EFFECT_APPLICABILITY_FAILURE')
    e = next(iter(effects)); v = len(good)
    bad = [r for r in bucket if not r['valid']]
    km = sum(len(r['E']) < e for r in bad)
    kz = sum(len(r['E']) == e for r in bad)
    kp = sum(len(r['E']) > e for r in bad)
    require(v+km+kz+kp == len(bucket), 'Category partition')
    mu = Fraction(v*km-kp, v+1)
    # Independent first-moment calculation: each invalid item precedes all
    # v valid items with probability 1/(v+1) in the reference order.
    probability_sum = sum((Fraction(1) if len(r['E']) < e else Fraction(0)
                           if len(r['E']) > e else Fraction(1, v+1)) - Fraction(1, v+1)
                          for r in bad)
    require(mu == probability_sum, 'Formula disagrees with probability sum')
    h = sum(r['relevance'] > rv for r in rows)
    c_r = next(r for r in ref if r['valid'])
    c_e = next(r for r in eff if r['valid'])
    j = sum(r['base_rank'] < c_r['base_rank'] for r in bad)
    u = sum(len(r['E']) == e and r['base_rank'] < c_e['base_rank'] for r in bad)
    require(te-tr == km+u-j and tr == h+j+1 and te == h+km+u+1, 'K/U/J mismatch')
    return {'menu_size': len(rows), 'bucket_relevance': rv, 'higher_prefix': h,
            'v': v, 'k_minus': km, 'k_zero': kz, 'k_plus': kp, 'valid_E': e,
            'initial_violation_count': len(rows[0]['initial_V']), 'J': j, 'U': u,
            'T_R': tr, 'T_E': te, 'delta': te-tr, 'mu': float(mu), 'mu_fraction': str(mu),
            'priority_residual': float(Fraction(te-tr)-mu)}

def dedup_ids(variant: dict, rows: dict) -> dict:
    selections = {}
    for item in variant['equivalence_classes']:
        fid = item['structure']; index = {r['candidate_id']:r for r in rows[fid][PRESERVATION_STATES[0]]}
        bystate = {s:{r['candidate_id']:r for r in rows[fid][s]} for s in PRESERVATION_STATES}
        members, reps = [], []
        for group in item['groups']:
            require(group['representative'] in group['members'], 'Representative outside class')
            members.extend(group['members']); reps.append(group['representative'])
            sigs = []
            for cid in group['members']:
                r = index[cid]
                if variant['signature'] == 'mechanical':
                    signature = [r['relevance'], ast.dump(ast.parse(r['source']), include_attributes=False)]
                else:
                    signature = [r['relevance'], [bystate[s][cid]['outcome_signature'] for s in PRESERVATION_STATES]]
                    if variant['signature'] == 'full_endpoint':
                        signature.append([bystate[s][cid]['full_state'] for s in PRESERVATION_STATES])
                sigs.append(record_key(signature))
            require(len(set(sigs)) == 1, fid + ': class mismatch')
        require(set(members) == set(index) and len(members) == len(index), fid + ': class coverage')
        require(len(reps) == len(set(reps)) == item['retained'], fid + ': retained count')
        selections[fid] = set(reps)
    require(set(selections) == set(rows), 'Dedup structure coverage')
    require(sum(map(len, selections.values())) == variant['candidates_retained'], 'Dedup total count')
    return selections

def run(data_root: Path, out: Path) -> dict:
    input_files = [CONTROLLED_DATA_DIR+n+'.json' for n in ('programs','observations','predictions')]
    input_files += [ROBUSTNESS_DIR+n+'.json' for n in ('paired_results','DEDUP_ROBUSTNESS','TIE_ORDER_ROBUSTNESS')]
    load = lambda name: json.loads((data_root / name).read_text(encoding='utf-8'))
    rows, metadata = validate_inputs(load(CONTROLLED_DATA_DIR+'programs.json'), load(CONTROLLED_DATA_DIR+'observations.json'), load(CONTROLLED_DATA_DIR+'predictions.json'))
    hist, dedup, tie = [load(ROBUSTNESS_DIR+n) for n in ('paired_results.json','DEDUP_ROBUSTNESS.json','TIE_ORDER_ROBUSTNESS.json')]
    definitions = [('original', None, hist['records'])]
    for variant in dedup['variants']:
        definitions.append((variant['signature']+'/'+variant['representative'], dedup_ids(variant, rows), variant['records']))
    state_rows, pair_rows, summaries, interval_rows, budget_rows, template_rows = [], [], [], [], [], []
    max_budget = max(len(s[PRESERVATION_STATES[0]]) for s in rows.values())
    allmetrics = {}
    for name, selections, retained in definitions:
        expected = {r['structure']: r for r in retained}
        allmetrics[name] = {}
        pp = []
        for fid, sides in rows.items():
            result = {}
            for state in PRESERVATION_STATES:
                selected = [r for r in sides[state] if selections is None or r['candidate_id'] in selections[fid]]
                sm = state_metrics(selected)
                recorded_metrics = expected[fid]['states'][state]
                require((sm['T_R'],sm['T_E'],sm['menu_size']) == (recorded_metrics['T_reference'],recorded_metrics['T_E'],recorded_metrics['menu_size']), name+'/'+fid+': stored rank mismatch')
                result[state] = sm
                state_rows.append({'representation':name,'structure':fid,**metadata['meta'][fid],'state':state,**sm})
                tr, te = sm['T_R'], sm['T_E']
                harm = list(range(tr, te)); benefit = list(range(te, tr))
                area = sum(int(tr<=b)-int(te<=b) for b in range(max_budget+1))
                require(area == te-tr == len(harm)-len(benefit), 'Budget area identity')
                interval_rows.append({'representation':name,'structure':fid,**metadata['meta'][fid], 'state':state,
                                      'T_R':tr,'T_E':te,'harm_start':tr if harm else None,'harm_stop_exclusive':te if harm else None,
                                      'harm_width':len(harm),'benefit_start':te if benefit else None,
                                      'benefit_stop_exclusive':tr if benefit else None,'benefit_width':len(benefit)})
            d = result[PRESERVATION_STATES[1]]['delta']-result[PRESERVATION_STATES[0]]['delta']
            require(d == expected[fid]['interaction_delta'], 'Stored D mismatch')
            mu = Fraction(result[PRESERVATION_STATES[1]]['mu_fraction'])-Fraction(result[PRESERVATION_STATES[0]]['mu_fraction'])
            p = {'representation':name,'structure':fid,**metadata['meta'][fid], 'D':d,'expected_D':float(mu),
                 'expected_D_fraction':str(mu),'residual_D':float(Fraction(d)-mu)}
            pp.append(p); pair_rows.append(p); allmetrics[name][fid] = result
        totals = {s:{'T_R':sum(m[s]['T_R'] for m in allmetrics[name].values()),
                     'T_E':sum(m[s]['T_E'] for m in allmetrics[name].values()),
                     'delta':summary([m[s]['delta'] for m in allmetrics[name].values()]),
                     'expected_delta':statistics.mean(m[s]['mu'] for m in allmetrics[name].values())} for s in PRESERVATION_STATES}
        summaries.append({'representation':name,'candidate_count':sum(m[PRESERVATION_STATES[0]]['menu_size'] for m in allmetrics[name].values()),
                          'observed_D':summary([p['D'] for p in pp]),'expected_D':summary([p['expected_D'] for p in pp]),
                          'residual_D_mean':statistics.mean(p['residual_D'] for p in pp),'states':totals})
        for template in sorted({m['template'] for m in metadata['meta'].values()}):
            subset = [p for p in pp if p['template'] == template]
            template_rows.append({'representation':name,'template':template,'n':len(subset),
                                  'mean_D':statistics.mean(p['D'] for p in subset),
                                  'mean_expected_D':statistics.mean(p['expected_D'] for p in subset),
                                  'mean_residual_D':statistics.mean(p['residual_D'] for p in subset)})
        for s in PRESERVATION_STATES:
            vals = [m[s] for m in allmetrics[name].values()]
            for b in range(max_budget+1):
                sr = sum(m['T_R']<=b for m in vals); se = sum(m['T_E']<=b for m in vals)
                harm = sum(m['T_R']<=b<m['T_E'] for m in vals)
                benefit = sum(m['T_E']<=b<m['T_R'] for m in vals)
                require(sr-se == harm-benefit, 'Success difference mismatch')
                budget_rows.append({'representation':name,'state':s,'budget':b,'denominator':96,
                                    'success_R':sr,'success_E':se,'harm_count':harm,'benefit_count':benefit,
                                    'net_R_minus_E':sr-se,'paired_repairability_coverage':1.0})
    changes = []
    original = {p['structure']:p for p in pair_rows if p['representation']=='original'}
    for p in pair_rows:
        if p['representation']=='original': continue
        o = original[p['structure']]
        dd = p['D']-o['D']; dm = Fraction(p['expected_D_fraction'])-Fraction(o['expected_D_fraction'])
        residual = Fraction(dd)-dm
        require(Fraction(dd) == dm+residual, 'Decomposition identity')
        changes.append({'representation':p['representation'],'structure':p['structure'],'template':p['template'],
                        'change_D':dd,'change_expected_D':float(dm),'change_residual_D':float(residual)})
    ties = []
    for item in tie['records']:
        fid = item['structure']; values = item['values']; cols = item['columns']
        require(len(values) == item['draws'], 'Retained tie count')
        dr = []
        for row in values:
            rr = dict(zip(cols,row))
            dr.append((rr['T_E_invalid']-rr['T_reference_invalid'])-(rr['T_E_valid']-rr['T_reference_valid']))
        retained_mean = Fraction(sum(dr),len(dr)); analytic = Fraction(original[fid]['expected_D_fraction'])
        if item['method'] == 'EXACT': require(retained_mean == analytic, fid+': exact tie mean mismatch')
        ties.append({'structure':fid,'template':item['template'],'method':item['method'],'draws':len(values),
                     'analytic_expected_D':float(analytic),'retained_mean_D':float(retained_mean),
                     'analytic_minus_retained':float(analytic-retained_mean)})
    out.mkdir(parents=True,exist_ok=False)
    tables = {'candidate_categories':state_rows,'paired_mechanism':pair_rows,'representation_changes':changes,
              'template_mechanism':template_rows,'budget_intervals':interval_rows,'all_integer_budgets':budget_rows,
              'retained_tie_comparison':ties}
    for name, data in tables.items(): table(out/(name+'.csv'),data)
    result = {'input_files':input_files,'formula':'(v*k_minus-k_plus)/(v+1)',
              'checks':metadata['checks'],'formula_checked_state_menus':len(state_rows),'budget_max':max_budget,
              'representations':summaries,'retained_tie_check':{'exact_structures':sum(r['method']=='EXACT' for r in ties),
                 'retained_structure_mean_D':statistics.mean(r['retained_mean_D'] for r in ties),
                 'analytic_mean_D':summaries[0]['expected_D']['mean'],
                 'maximum_absolute_MC_difference':max(abs(r['analytic_minus_retained']) for r in ties if r['method']!='EXACT')},
              'units':'96 designed pairs, grouped in 16 templates; no natural population inference',
              'tables':{name:len(data) for name,data in tables.items()}}
    (out/'analysis_results.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'checks':result['checks'],'representations':[
        {'name':s['representation'],'observed_D':s['observed_D']['mean'],'expected_D':s['expected_D']['mean'],
         'residual':s['residual_D_mean']} for s in summaries], 'tie':result['retained_tie_check'],'budget_max':max_budget},indent=2))
    return result

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-root',type=Path,default=ROOT,help='Root of the extracted code-and-data package')
    parser.add_argument('--output',type=Path,default=ROOT/'outputs/secondary_analysis')
    args = parser.parse_args()
    run(args.data_root,args.output)
