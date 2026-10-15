"""Reconstruct paired ranks from recorded edits and endpoint observations."""
from __future__ import annotations

import argparse
import csv
import json
import statistics
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTROLLED_DATA_DIR = ROOT / 'data' / 'controlled'
PRESERVATION_STATES = ('STATE_VALID', 'STATE_INVALID')
BUDGETS = (1, 2, 4, 8, 'exhaustive')


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def read(name: str) -> dict:
    return json.loads((CONTROLLED_DATA_DIR / name).read_text(encoding='utf-8'))


def keyed(rows: list[dict], fields: tuple[str, ...]) -> dict:
    result = {tuple(row[k] for k in fields): row for row in rows}
    require(len(result) == len(rows), 'Duplicate recorded row keys: ' + ','.join(fields))
    return result


def first_valid(rows: list[dict], effect: bool) -> int | None:
    def key(r: dict) -> tuple:
        return (-r['relevance'], len(r['E']), r['base_rank']) if effect else (-r['relevance'], r['base_rank'])
    return next((i for i, r in enumerate(sorted(rows, key=key), 1) if r['valid']), None)


def reconstruct() -> tuple[dict, list[dict]]:
    source, observations, predictions = map(read, ('programs.json', 'observations.json', 'predictions.json'))
    truth_index = keyed(observations['rows'], ('family_id', 'condition', 'candidate_id'))
    pred_index = keyed(predictions['rows'], ('family_id', 'candidate_id'))
    expected_candidates = {(f['family_id'], c['candidate_id']) for f in source['families'] for c in f['candidates']}
    require(set(pred_index) == expected_candidates, 'Prediction identities do not match the candidate menus')
    require(len({f['family_id'] for f in source['families']}) == len(source['families']), 'Duplicate structure identifiers')
    counts, pairs, checked_rows = Counter(), [], 0
    for family in source['families']:
        fid = family['family_id']
        counts[family['mechanism']] += 1
        require(tuple(s['condition'] for s in family['states']) == PRESERVATION_STATES, fid + ': state order')
        a, b = [s['definition'] for s in family['states']]
        require({k:v for k,v in a.items() if k != 'initial_state'} ==
                {k:v for k,v in b.items() if k != 'initial_state'}, fid + ': requirements/program mismatch')
        require({k:v for k,v in a['initial_state'].items() if k != 'vault'} ==
                {k:v for k,v in b['initial_state'].items() if k != 'vault'}, fid + ': extra state difference')
        require((a['initial_state']['vault'], b['initial_state']['vault']) == (7, 0), fid + ': initial values')
        pair = {'structure': fid, 'template': family['mechanism'], 'context': family['context'], 'states': {}}
        ids = [c['candidate_id'] for c in family['candidates']]
        require(len(ids) == len(set(ids)), fid + ': duplicate candidate IDs')
        for state in family['states']:
            condition, definition = state['condition'], state['definition']
            rows = []
            for rank, candidate in enumerate(family['candidates'], 1):
                label = fid + '/' + condition + '/' + candidate['candidate_id']
                r = truth_index[(fid, condition, candidate['candidate_id'])]
                pr = pred_index[(fid, candidate['candidate_id'])]
                require(r['state_id'] == state['state_id'], label + ': state ID')
                require(r['base_rank'] == pr['base_rank'] == rank, label + ': priority')
                require(r['relevance'] == pr['relevance'], label + ': relevance')
                require(r['patched_source'] == candidate['patched_source'] == pr['patched_source'], label + ': source')
                allowed = definition['independent_A']['allowed_ops']
                edits_allowed = all(edit['op'] in allowed.get(edit['site'], []) for edit in candidate['edits']) and candidate['cost'] <= definition['B']
                require(edits_allowed, label + ': allowed edits and cost')
                execution, initial = r['candidate_execution'], r['original_execution']
                obs, bo, obligations = execution['observers'], initial['observers'], definition['independent_P']
                bv = {p for p, expected in obligations.items() if bo[p] != expected}
                v = {p for p, expected in obligations.items() if obs[p] != expected}
                e = {p for p in obligations if obs[p] != bo[p]}
                actual = {'E':e, 'V':v, 'N':v-bv, 'C':bv-v, 'initial_V':bv}
                for name, value in actual.items():
                    require(set(r[name]) == value, label + ': observer-derived ' + name)
                require(bool(bv) == (condition == 'STATE_INVALID'), label + ': initial P status')
                goal = execution['error'] is None and execution['state']['goal'] is True
                valid = bool(edits_allowed and goal and not v)
                require(r['contract_valid'] == valid, label + ': A/G/P validity')
                rows.append({'candidate_id':candidate['candidate_id'], 'base_rank':rank,
                             'relevance':r['relevance'], 'E':e, 'valid':valid})
                checked_rows += 1
            tr, te = first_valid(rows, False), first_valid(rows, True)
            require(tr is not None and te is not None, fid + ': original menu not repairable')
            pair['states'][condition] = {'menu_size':len(rows), 'valid_candidates':sum(r['valid'] for r in rows),
                                        'T_reference':tr, 'T_E':te, 'delta':te-tr}
        pair['D'] = pair['states']['STATE_INVALID']['delta'] - pair['states']['STATE_VALID']['delta']
        pairs.append(pair)
    require(checked_rows == len(truth_index), 'Unvisited saved observations rows')
    ds = [p['D'] for p in pairs]
    totals = {s:{'reference':sum(p['states'][s]['T_reference'] for p in pairs),
                 'E':sum(p['states'][s]['T_E'] for p in pairs)} for s in PRESERVATION_STATES}
    signs = {'positive':sum(d>0 for d in ds), 'zero':sum(d==0 for d in ds), 'negative':sum(d<0 for d in ds)}
    budgets = {str(b):{s:{'denominator':len(pairs),
                  'reference':sum(b=='exhaustive' or p['states'][s]['T_reference']<=b for p in pairs),
                  'E':sum(b=='exhaustive' or p['states'][s]['T_E']<=b for p in pairs)} for s in PRESERVATION_STATES} for b in BUDGETS}
    result = {'structures':len(pairs),
              'templates':len(counts), 'contexts_per_template':dict(counts),
              'candidate_state_rows':checked_rows, 'distinct_candidates':sum(len(f['candidates']) for f in source['families']),
              'totals':totals, 'interaction_signs':signs, 'interaction_mean':statistics.mean(ds),
              'interaction_median':statistics.median(ds), 'budgets':budgets,
              'input_files':['programs.json','observations.json','predictions.json']}
    return result, pairs


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, default=ROOT/'outputs')
    args = parser.parse_args()
    result, pairs = reconstruct()
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    (output/'reconstruction.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    (output/'paired_records.json').write_text(json.dumps(pairs,indent=2)+'\n',encoding='utf-8')
    columns = ['structure','template','context','menu_size','T_R_valid','T_E_valid','T_R_invalid','T_E_invalid','D']
    with (output/'paired_results.csv').open('w',newline='',encoding='utf-8') as f:
        w = csv.writer(f); w.writerow(columns)
        for p in pairs:
            v,i = [p['states'][s] for s in PRESERVATION_STATES]
            w.writerow([p['structure'],p['template'],p['context'],v['menu_size'],v['T_reference'],v['T_E'],i['T_reference'],i['T_E'],p['D']])
    print(json.dumps({k:result[k] for k in ('structures','templates','candidate_state_rows','distinct_candidates','totals','interaction_signs','interaction_mean','interaction_median')},indent=2))


if __name__ == '__main__':
    main()
