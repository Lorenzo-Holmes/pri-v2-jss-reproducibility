"""Reconstruct ranks and sensitivity summaries from controlled records."""
from pathlib import Path
from collections import Counter, defaultdict
from fractions import Fraction
import argparse, ast, csv, json, math, statistics
from input_data import ROOT, record_key

PRESERVATION_STATES = ('STATE_VALID', 'STATE_INVALID')
METHODS = ('reference', 'union', 'complex', 'exact')
CONTROLLED_DATA_DIR = 'data/controlled/'
ROBUSTNESS_DIR = 'data/robustness/'

def signs(xs): return dict(harm=sum(x > 0 for x in xs), tie=sum(x == 0 for x in xs), benefit=sum(x < 0 for x in xs))
def percentile(xs, p):
    xs = sorted(xs)
    k = (len(xs)-1)*p
    lo = int(k)
    hi = math.ceil(k)
    return xs[lo] + (xs[hi]-xs[lo])*(k-lo)
def summary(xs):
    return {'n':len(xs), 'sum':sum(xs), 'mean':statistics.mean(xs), 'median':statistics.median(xs),
            'minimum':min(xs), 'maximum':max(xs), 'p05':percentile(xs,.05), 'p95':percentile(xs,.95)}
def write_csv(path, rows):
    with path.open('w', encoding='utf-8', newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
def rank(rows, method):
    key=lambda r: (-r['relevance'], 0 if method=='reference' else len(r['E']) if method=='exact' else len(r['predictions'][method]['observers']), r['base_rank'])
    return next((i for i,r in enumerate(sorted(rows,key=key),1) if r['contract_valid']), None)
def state_metrics(rows):
    tr,te=rank(rows,'reference'),rank(rows,'exact')
    good=[r for r in rows if r['contract_valid']]
    d=None if tr is None else te-tr
    r={'menu_size':len(rows),'valid_count':len(good),'T_R':tr,'T_E':te,'delta':d}
    if not good:return r
    rel=max(x['relevance'] for x in good)
    good=[x for x in good if x['relevance']==rel]
    e={len(x['E']) for x in good}
    assert len(e)==1
    e=e.pop()
    bad=[x for x in rows if not x['contract_valid'] and x['relevance']==rel]
    v=len(good)
    km=sum(len(x['E'])<e for x in bad)
    kz=sum(len(x['E'])==e for x in bad)
    kp=sum(len(x['E'])>e for x in bad)
    mu=Fraction(v*km-kp,v+1)
    # An independent sum of marginal precedences checks the finite-order formula.
    alt=sum((1 if len(x['E'])<e else 0 if len(x['E'])>e else Fraction(1,v+1))-Fraction(1,v+1) for x in bad)
    assert mu==alt
    firstbase=min(x['base_rank'] for x in good)
    j=sum(x['base_rank']<firstbase for x in bad)
    u=sum(len(x['E'])==e and x['base_rank']<firstbase for x in bad)
    h=sum(x['relevance']>rel for x in rows)
    assert tr==h+j+1 and te==h+km+u+1 and d==km+u-j
    r.update(bucket_relevance=rel,v=v,k_minus=km,k_zero=kz,k_plus=kp,J=j,U=u,higher_prefix=h,mu=float(mu),mu_fraction=str(mu))
    return r

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--data-root',type=Path,default=ROOT)
    ap.add_argument('--output',type=Path,required=True)
    args=ap.parse_args()
    assert not args.output.exists(), 'Use a fresh output directory.'
    names=[CONTROLLED_DATA_DIR+n+'.json' for n in ['programs','observations','predictions']]
    names += [ROBUSTNESS_DIR+n+'.json' for n in ['DEDUP_ROBUSTNESS','MENU_SIZE_ROBUSTNESS','LEAVE_ONE_TEMPLATE_OUT','TIE_ORDER_ROBUSTNESS']]
    names += ['data/summaries/pddl_retained_summary.json']
    inputs={n:(args.data_root/n).read_bytes() for n in names}
    source_records,observations,predictions,representations,menu,loo,tie,pddl=[json.loads(inputs[n]) for n in names]
    families={f['family_id']:f for f in source_records['families']}
    assert len(families)==len(source_records['families'])
    predictions_by_candidate={(r['family_id'],r['candidate_id']):r for r in predictions['rows']}
    observations_by_state={(r['family_id'],r['condition'],r['candidate_id']):r for r in observations['rows']}
    assert len(predictions_by_candidate)==len(predictions['rows']) and len(observations_by_state)==len(observations['rows'])
    grouped=defaultdict(list)
    endpoint_sig={}
    relation=defaultdict(Counter)
    extras=defaultdict(Counter)
    checks=Counter()
    changes=Counter()
    unmodified_executions={x['state_id']:x['execution'] for x in observations['initials']}
    unmodified_checks={'count':len(unmodified_executions),'no_error_goal_false':sum(x['error'] is None and x['state']['goal'] is False for x in unmodified_executions.values()),'with_error':sum(x['error'] is not None for x in unmodified_executions.values()),'G_true':sum(x['error'] is None and x['state']['goal'] is True for x in unmodified_executions.values())}
    for fid,f in families.items():
        valid_definition,invalid_definition=[s['definition'] for s in f['states']]
        assert {k:v for k,v in valid_definition.items() if k!='initial_state'}=={k:v for k,v in invalid_definition.items() if k!='initial_state'}
        assert {k:v for k,v in valid_definition['initial_state'].items() if k!='vault'}=={k:v for k,v in invalid_definition['initial_state'].items() if k!='vault'}
        assert (valid_definition['initial_state']['vault'],invalid_definition['initial_state']['vault'])==(7,0)
        for si,s in enumerate(f['states']):
            assert s['condition']==PRESERVATION_STATES[si];m=s['definition']
            for priority,c in enumerate(f['candidates'],1):
                cid=c['candidate_id'];r=observations_by_state[fid,s['condition'],cid];pr=predictions_by_candidate[fid,cid]
                assert r['predictions']==pr['predictions']
                assert r['base_rank']==pr['base_rank']==priority
                assert r['relevance']==pr['relevance']
                assert r['patched_source']==pr['patched_source']==c['patched_source']
                assert r['original_execution']==unmodified_executions[s['state_id']]
                ex,bo=r['candidate_execution'],r['original_execution']['observers'];obs=ex['observers'];p=m['independent_P']
                bv={k for k,v in p.items() if bo[k]!=v};vc={k for k,v in p.items() if obs[k]!=v};e={k for k in p if obs[k]!=bo[k]}
                d={'E':e,'V':vc,'N':vc-bv,'C':bv-vc,'initial_V':bv}
                for k,v in d.items():assert set(r[k])==v
                assert bool(bv)==(s['condition']=='STATE_INVALID')
                edits_allowed=c['cost']<=m['B'] and all(ed['op'] in m['independent_A']['allowed_ops'].get(ed['site'],[]) for ed in c['edits'])
                goal=ex['error'] is None and ex['state']['goal'] is True
                valid=bool(edits_allowed and goal and not vc);assert valid==r['contract_valid']
                checks['G_P_A_and_E_V_N_C_rows']+=1
                checks['allowed_candidate_state_rows']+=edits_allowed
                if valid:assert e==bv;checks['valid_endpoint_effect_equalities']+=1
                co=set(pr['predictions']['complex']['observers']);un=set(pr['predictions']['union']['observers'])
                assert e<=co<=un
                kind=('E=Complex' if e==co else 'E<Complex')+('=Union' if co==un else '<Union')
                for st in (s['condition'],'ALL'):
                    relation[st][kind]+=1;extras[st]['union']+=len(un-e);extras[st]['complex']+=len(co-e)
                endpoint_sig[fid,s['condition'],cid]={'G':goal,'A':edits_allowed,'error':ex['error'],'observers':obs,'repair_valid':valid,**{k:sorted(v) for k,v in d.items()}}
                grouped[fid,s['condition']].append(r)
        va={r['candidate_id'] for r in grouped[fid,PRESERVATION_STATES[0]] if r['contract_valid']};vb={r['candidate_id'] for r in grouped[fid,PRESERVATION_STATES[1]] if r['contract_valid']}
        changes['families_with_valid_set_change']+=va!=vb
        changes['families_with_highest_repairable_bucket_change']+=max(r['relevance'] for r in grouped[fid,PRESERVATION_STATES[0]] if r['contract_valid'])!=max(r['relevance'] for r in grouped[fid,PRESERVATION_STATES[1]] if r['contract_valid'])
        for c in f['candidates']:
            a,b=[observations_by_state[fid,s,c['candidate_id']] for s in PRESERVATION_STATES]
            changes['candidate_identities_validity_changed']+=a['contract_valid']!=b['contract_valid']
            changes['candidate_identities_E_cardinality_changed']+=len(a['E'])!=len(b['E'])
            control=lambda x:[{k:v for k,v in t.items() if k not in ['before','after']} for t in x['candidate_execution']['trace']]
            changes['candidate_control_sequences_changed']+=control(a)!=control(b)
    checks['prediction_records']=len(predictions_by_candidate)
    checks['endpoint_records']=len(observations_by_state)
    checks['strict_complex_subset_union_predictions']=sum(set(r['predictions']['complex']['observers'])<set(r['predictions']['union']['observers']) for r in predictions['rows'])
    invalid_lower=Counter()
    for fid in families:
        rr=grouped[fid,PRESERVATION_STATES[1]];rv=max(r['relevance'] for r in rr if r['contract_valid']);emin=min(len(r['E']) for r in rr if r['contract_valid'] and r['relevance']==rv)
        for r in rr:
            if r['relevance']==rv and not r['contract_valid'] and len(r['E'])<emin:
                invalid_lower['lower_effect_invalid_in_highest_repairable_bucket']+=1
                goal=r['candidate_execution']['error'] is None and r['candidate_execution']['state']['goal'] is True
                invalid_lower['G_true_P_violated']+=bool(goal and r['V'])
                invalid_lower['G_false']+=not goal
    # Full first-valid distributions and all integer budgets for four existing orders.
    ranks=[]
    rank_summary=[]
    hist=[]
    transitions=[]
    budgets=[]
    for (fid,s),rs in grouped.items():
        ranks.append({'family_id':fid,'template':families[fid]['mechanism'],'context':families[fid]['context'],'state':s,'menu_size':len(rs),**{m:rank(rs,m) for m in METHODS}})
    for s in PRESERVATION_STATES:
        sr=[r for r in ranks if r['state']==s]
        for m in METHODS:
            xx=[r[m] for r in sr];rank_summary.append({'state':s,'method':m,**summary(xx)})
            hist += [{'state':s,'method':m,'first_valid_rank':k,'structure_count':v,'denominator':len(sr)} for k,v in sorted(Counter(xx).items())]
        for before,after in [('reference','union'),('reference','complex'),('reference','exact'),('union','complex'),('complex','exact'),('union','exact')]:
            ds=[r[after]-r[before] for r in sr]
            transitions.append({'state':s,'before':before,'after':after,'denominator':len(sr),**signs(ds),**{'delta_'+k:v for k,v in summary(ds).items()}})
        for b in range(61):budgets.append({'state':s,'budget':b,'denominator':len(sr),**{m:sum(r[m]<=b for r in sr) for m in METHODS}})
    # Reconstruct endpoint partitions, load recorded representatives, and verify earliest-priority selection.
    reps={'original':{fid:set(c['candidate_id'] for c in f['candidates']) for fid,f in families.items()}}
    rep_details=[]
    for variant in representations['variants']:
        name=variant['signature']+'/'+variant['representative'];reps[name]={}
        for saved in variant['equivalence_classes']:
            fid=saved['structure'];f=families[fid];groups=defaultdict(list)
            for c in f['candidates']:
                cid=c['candidate_id'];rel=predictions_by_candidate[fid,cid]['relevance']
                if variant['signature']=='mechanical':value=ast.dump(ast.parse(c['patched_source']),include_attributes=False)
                else:
                    ends=[]
                    for s in PRESERVATION_STATES:
                        es=dict(endpoint_sig[fid,s,cid])
                        if variant['signature']=='full_endpoint':es['state']=observations_by_state[fid,s,cid]['candidate_execution']['state']
                        ends.append(es)
                    value=[f['states'][0]['definition']['independent_A'],ends]
                groups[record_key([rel,value])].append(cid)
            assert {frozenset(v) for v in groups.values()}=={frozenset(g['members']) for g in saved['groups']}
            assert len(groups)==saved['retained']
            chosen=set()
            for g in saved['groups']:
                cid = g['representative']
                assert cid in g['members']
                if variant['representative'] != 'recorded':
                    assert cid == min(g['members'],key=lambda c:predictions_by_candidate[fid,c]['base_rank'])
                chosen.add(cid)
                rep_details.append({'representation':name,'family_id':fid,'class_members':';'.join(sorted(g['members'])),'representative':cid,'base_rank':predictions_by_candidate[fid,cid]['base_rank']})
            reps[name][fid]=chosen
    rep_states=[]
    rep_pairs=[]
    rep_summary=[]
    rep_metrics={}
    for name,select in reps.items():
        rep_metrics[name]={}
        for fid in families:
            sm={s:state_metrics([r for r in grouped[fid,s] if r['candidate_id'] in select[fid]]) for s in PRESERVATION_STATES}
            rep_metrics[name][fid]=sm
            for s in PRESERVATION_STATES:rep_states.append({'representation':name,'family_id':fid,'state':s,**sm[s]})
            a,b=[sm[s] for s in PRESERVATION_STATES];d=b['delta']-a['delta'];mu=Fraction(b['mu_fraction'])-Fraction(a['mu_fraction'])
            rep_pairs.append({'representation':name,'family_id':fid,'template':families[fid]['mechanism'],'context':families[fid]['context'],'menu_size':a['menu_size'],'D':d,'D_divided_by_own_menu':d/a['menu_size'],'expected_D':float(mu),'expected_D_fraction':str(mu),'delta_valid':a['delta'],'delta_invalid':b['delta']})
        prs=[p for p in rep_pairs if p['representation']==name];d=[p['D'] for p in prs]
        row={'representation':name,'structures':len(prs),'candidate_identities':sum(p['menu_size'] for p in prs),'mean_D':statistics.mean(d),'sum_D':sum(d),'D_positive':sum(x>0 for x in d),'D_zero':sum(x==0 for x in d),'D_negative':sum(x<0 for x in d),'mean_D_divided_by_own_menu':statistics.mean(p['D_divided_by_own_menu'] for p in prs),'ratio_sum_D_to_sum_menu':sum(d)/sum(p['menu_size'] for p in prs),'mean_expected_D':statistics.mean(p['expected_D'] for p in prs),'positive_D_without_invalid_harm':sum(p['D']>0 and p['delta_invalid']<=0 for p in prs),'positive_D_with_invalid_tie':sum(p['D']>0 and p['delta_invalid']==0 for p in prs),'positive_D_with_invalid_benefit':sum(p['D']>0 and p['delta_invalid']<0 for p in prs)}
        for s in PRESERVATION_STATES:
            ms=[x[s] for x in rep_metrics[name].values()];statekey='valid' if s==PRESERVATION_STATES[0] else 'invalid'
            row.update({statekey+'_'+k:v for k,v in {'T_R_sum':sum(x['T_R'] for x in ms),'T_E_sum':sum(x['T_E'] for x in ms),'mean_delta':statistics.mean(x['delta'] for x in ms),'mean_delta_over_own_menu':statistics.mean(x['delta']/x['menu_size'] for x in ms),'mean_expected_delta':float(sum(Fraction(x['mu_fraction']) for x in ms)/len(ms)),'positive_expected_delta':sum(x['mu']>0 for x in ms),**signs([x['delta'] for x in ms])}.items()})
        rep_summary.append(row)
    # Reconstruct all 38,400 saved deterministic menu subsets; no new draw.
    menu_index={(r[0],r[1],r[2]):dict(zip(menu['table_columns'],r)) for r in menu['table']}
    menu_replicates=[]
    menu_summary=[]
    for frac in [.25,.5,.75,1.0]:
        saved_frac=next(x for x in menu['fractions'] if x['fraction']==frac)
        for rep in range(100):
            ds=[];nd=[];paired_repairable=0
            for fid,f in families.items():
                ids=[c['candidate_id'] for c in f['candidates']]
                saved=menu_index[frac,rep,fid]
                chosen=set(saved['members'])
                assert chosen <= set(ids) and len(chosen)==len(saved['members'])==max(1,math.ceil(frac*len(ids)))
                ss=[state_metrics([r for r in grouped[fid,s] if r['candidate_id'] in chosen]) for s in PRESERVATION_STATES]
                a,b=ss;d=None if a['delta'] is None or b['delta'] is None else b['delta']-a['delta']
                assert [a['menu_size'],a['valid_count'],b['valid_count'],a['T_R'],a['T_E'],b['T_R'],b['T_E'],d]==[saved[k] for k in ['menu_size','valid_endpoints_valid','valid_endpoints_invalid','T_ref_valid','T_E_valid','T_ref_invalid','T_E_invalid','interaction']]
                checks['saved_menu_subset_rows_reconstructed']+=1
                if d is not None:paired_repairable+=1;ds.append(d);nd.append(d/len(chosen))
            avg=statistics.mean(ds);old=saved_frac['replicates'][rep]
            assert paired_repairable==old['aggregate']['paired_coverage'] and abs(avg-old['aggregate']['interaction']['mean'])<1e-12
            menu_replicates.append({'fraction':frac,'replicate':rep,'denominator':len(families),'paired_repairable':paired_repairable,'paired_repairable_fraction':paired_repairable/len(families),'conditional_mean_D':avg,'conditional_mean_D_over_menu':statistics.mean(nd)})
        xx=[r for r in menu_replicates if r['fraction']==frac]
        menu_summary.append({'fraction':frac,'replicates':len(xx),'median_conditional_mean_D':statistics.median(r['conditional_mean_D'] for r in xx),'median_paired_repairable_fraction':statistics.median(r['paired_repairable_fraction'] for r in xx),'p05_D':percentile([r['conditional_mean_D'] for r in xx],.05),'p95_D':percentile([r['conditional_mean_D'] for r in xx],.95)})
    # Template concentration and leave-one-template-out, from independently sorted ranks.
    original=[r for r in rep_pairs if r['representation']=='original']
    template_rows=[]
    loo_rows=[]
    for t in sorted({f['mechanism'] for f in families.values()}):
        rows=[r for r in original if r['template']==t]
        template_rows.append({'template':t,'structures':len(rows),'sum_D':sum(r['D'] for r in rows),'mean_D':statistics.mean(r['D'] for r in rows),'distinct_D_values':len({r['D'] for r in rows}),'context_D':';'.join(r['context']+':'+str(r['D']) for r in rows)})
        rest=[r['D'] for r in original if r['template']!=t];x=next(r for r in loo['records'] if r['dropped_template']==t)
        assert len(rest)==x['structures'] and abs(statistics.mean(rest)-x['interaction']['mean'])<1e-12
        loo_rows.append({'dropped_template':t,'structures':len(rest),'mean_D':statistics.mean(rest)})
    # Retained tie draws: exact means compared algebraically, no PCG64 draws added.
    tie_rows=[]
    for r in tie['records']:
        ds=[(v[3]-v[2])-(v[1]-v[0]) for v in r['values']]
        v,i=[rep_metrics['original'][r['structure']][s] for s in PRESERVATION_STATES]
        exactmean=Fraction(i['mu_fraction'])-Fraction(v['mu_fraction']);retained=Fraction(sum(ds),len(ds))
        if r['method']=='EXACT':assert exactmean==retained;checks['exact_enumeration_means_matched']+=1
        tie_rows.append({'family_id':r['structure'],'method':r['method'],'draws':len(ds),'historical_D':i['delta']-v['delta'],'negative':sum(d<0 for d in ds),'nonpositive':sum(d<=0 for d in ds),'analytic_mean':float(exactmean),'retained_mean':float(retained)})
    positive=[r for r in tie_rows if r['historical_D']>0]
    tie_report={'historical_positive_structures':len(positive),'negative_draws':sum(r['negative'] for r in positive),'retained_draw_denominator_for_positive_structures':sum(r['draws'] for r in positive),'structures_with_negative_draw':sum(r['negative']>0 for r in positive),'equal_structure_negative_rate':float(sum(Fraction(r['negative'],r['draws']) for r in positive)/len(positive)),'equal_structure_nonpositive_rate':float(sum(Fraction(r['nonpositive'],r['draws']) for r in positive)/len(positive)),'retained_aggregate_draws':len(tie['aggregate_mean_draws']),'retained_aggregate_mean_summary':summary(tie['aggregate_mean_draws'])}
    # PDDL comparisons use the available per-case summaries; candidate-level execution records are unavailable.
    pddl_report=[]
    for name,rs in [('original',pddl['records'])]:
        defined=[r['endpoint']['delta'] for r in rs if r['endpoint']['delta'] is not None]
        for r in rs:
            e=r['endpoint'];assert (e['delta'] is None)==(e['valid_endpoints']==0)
            if e['delta'] is not None:assert e['delta']==e['T_E']-e['T_reference']
        pddl_report.append({'representation':name,'catalogue_denominator':len(rs),'repairable':len(defined),'nonrepairable':len(rs)-len(defined),'candidate_count':sum(r['endpoint']['menu_size'] for r in rs),'mean_delta_conditional_on_repairable':statistics.mean(defined),**signs(defined),'calculation_scope':'recomputed retained per-case summary arithmetic; original task/candidate truth not supplied'})
    for x in pddl['dedup']:
        a=x['aggregate'];d=a['delta'];assert abs((a['rank_sum_E']-a['rank_sum_reference'])/a['repairable']-d['mean'])<1e-12
        pddl_report.append({'representation':x['signature']+'/'+x['representative'],'catalogue_denominator':a['combinations'],'repairable':a['repairable'],'nonrepairable':a['no_valid_endpoint'],'candidate_count':a['candidate_count'],'mean_delta_conditional_on_repairable':d['mean'],'harm':d['signs']['positive'],'tie':d['signs']['zero'],'benefit':d['signs']['negative'],'calculation_scope':'aggregate-only retained summary; mean checked against saved rank sums; class membership and per-case dedup records absent'})
    result={'calculation':'saved_record_analysis',
        'input_files':sorted(inputs),'counts':dict(checks),'paired_state_changes':dict(changes),
        'design':{'families':len(families),'templates':len({f['mechanism'] for f in families.values()}),'contexts':len({f['context'] for f in families.values()}),'template_context_counts':dict(Counter(f['mechanism'] for f in families.values()))},'initial_G_checks':unmodified_checks,'invalid_lower_effect_candidate_checks':dict(invalid_lower),
        'endpoint_relation_counts':{s:dict(c) for s,c in relation.items()},'extra_labels_by_state':{s:dict(c) for s,c in extras.items()},
        'prediction_source':{'source':'saved_records','methods':['Union','Complex'],'analysis_modes':dict(Counter(r['predictions']['union']['analysis_mode'] for r in predictions['rows']))},
        'first_valid_summary':rank_summary,'first_valid_transitions':transitions,'representation_summary':rep_summary,'tie_summary':tie_report,'menu_summary':menu_summary,
        'template_concentration':{'templates_constant_D_across_contexts':sum(r['distinct_D_values']==1 for r in template_rows),'largest_three_D_sum':sum(sorted((r['sum_D'] for r in template_rows),reverse=True)[:3]),'total_D_sum':sum(r['sum_D'] for r in template_rows)},
        'pddl_retained_summary_arithmetic':pddl_report}
    args.output.mkdir(parents=True)
    (args.output/'rank_summary.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    for name,rows in [('first_valid_ranks',ranks),('first_valid_distribution',hist),('first_valid_transitions',transitions),('four_order_all_budgets',budgets),('representation_representatives',rep_details),('representation_states',rep_states),('representation_pairs',rep_pairs),('representation_summary',rep_summary),('menu_replicates',menu_replicates),('menu_summary',menu_summary),('template_summary',template_rows),('leave_one_template_out',loo_rows),('retained_tie_counts',tie_rows),('pddl_summary_arithmetic',pddl_report)]:write_csv(args.output/(name+'.csv'),rows)
    print(json.dumps({k:result[k] for k in ['counts','paired_state_changes','endpoint_relation_counts','extra_labels_by_state','first_valid_summary','template_concentration']},ensure_ascii=False,indent=2))

if __name__=='__main__':main()
