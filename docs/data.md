# Data and analysis conventions

Paths are relative to the package root. The analysis unit is a paired structure:
96 structures, 1,824 candidate occurrences, and 3,648 candidate-state observations.
The README distinguishes saved-record calculations, replay, and current prediction.

## Controlled inputs

| File under `data/controlled/` | Contents |
| --- | --- |
| `programs.json` | `families` holds template/context identifiers, two `states`, and an ordered `candidates` menu. Each state has a program definition; each candidate has edits, cost, size, identifier, and patched source. |
| `predictions.json` | 1,824 `rows` with patched source, reference priority, public relevance, and `union`/`complex` predictions. |
| `observations.json` | 3,648 candidate-state `rows`; 192 unmodified executions in `initials`. |
| `paired_endpoint_records.json` | Saved paired comparisons by structure, arm, budget, and endpoint; retained original records, not a dependency of current aggregate scripts. |

`family_id` and CSV `structure` identify the same paired structure. `candidate_id`
is matched within a structure; `condition` adds the state. `STATE_VALID` and
`STATE_INVALID` mean P-valid and P-invalid unmodified-program endpoints, not full
repair validity. `base_rank` is reference priority. Public `relevance` is twice
the indicator of a True literal in a new goal-writing call, plus indicators of a
new goal writer and an edited witness site. `not False` is not a True literal.

### Definition and execution fields

| Raw field | Meaning |
| --- | --- |
| `W_bad` | Stored unmodified source, read into `FiniteCase.source`. |
| `coverage` | Historical corpus identifier, read as `corpus_id`; not a measured rate. |
| `initial_state` | Input state supplied to execution. |
| `independent_A` | Edit policy identifier and allowed operations by site. |
| `independent_P` | Required observer values, all 7 in this corpus. |
| `B` | Maximum edit cost. |
| `grammar_menus` | Finite per-site operations and replacement tokens. |
| `failure_witness_sites` | Public sites used in relevance. |
| `original_execution` | Unmodified-program final state, error, API calls, trace, and observer values. |
| `candidate_execution` | The same fields after candidate application. |

`initials` holds unmodified executions, not input states. Traces retain arguments,
returns, exceptions, and before/after states. The declared error text is
`declared API exception`. The local API horizon is 64 calls.

### Endpoint sets

| Field | Definition |
| --- | --- |
| `E` | Observers changed between candidate and unmodified endpoints. |
| `V` | Preservation violations at the candidate endpoint. |
| `initial_V` | Violations at the unmodified-program endpoint. |
| `N` | Newly introduced violations: `V - initial_V`. |
| `C` | Corrected violations: `initial_V - V`. |
| `complex_FO`, `union_FO` | Omitted endpoint effects: `E - predicted_observers`. |
| `complex_FI`, `union_FI` | Extra predicted observers: `predicted_observers - E`. |

FO/FI fields are observer lists, not counts or rates. `contract_valid` requires
allowed edits within the cost limit, no execution error, final `goal=True`, and no violations. These
conditions are derived from the edit policy and observations, not prediction mode.

Stored predictions and recomputed predictions share five fields: `observers`,
`analysis_mode`, `reasons`, `changed_resources`, and `method`. Methods are `union`
and `complex`; modes are `MODELED` and `ALL_OBSERVERS`. `reasons` retains each
unsupported-behavior condition, with descriptive labels in lexical order.
Stored observations retain these sets for each candidate-state pairing.

## Robustness inputs

| File under `data/robustness/` | Contents |
| --- | --- |
| `paired_results.json` | Original per-structure state ranks and paired interactions. |
| `DEDUP_ROBUSTNESS.json` | Six representation variants, class members, selected representatives, and ranks. |
| `MENU_SIZE_ROBUSTNESS.json` | `table_columns` describes 38,400 `table` rows with explicit `members`; `fractions` contains replicate aggregates. |
| `TIE_ORDER_ROBUSTNESS.json` | Per-structure `columns`/`values` for retained priority draws; aggregate means and budget ensembles. |
| `LEAVE_ONE_TEMPLATE_OUT.json` | Sixteen results after omitting one template. |
| `TEMPLATE_HETEROGENEITY.json` | Per-structure and per-template summaries. |
| `BUDGET_ROBUSTNESS.json` | Original overall and template-level budget comparisons. |

Mechanical equivalence uses parsed source. Full-endpoint equivalence includes
final state. Paired-outcome equivalence uses the observations relevant to the repair requirements in
both states. Every partition retains relevance. Analyses read the saved class
members and representatives; earliest priority is checked against `base_rank`.
Full-menu first-valid ranks do not depend on the chosen validation budget;
success and capped-validation counts do. Each menu-subset record retains every
structure: missing first-valid ranks remain null, never successful imputations.
Rank and interaction means condition on paired repairability; all-case success
and exhaustion totals remain separate. Priority-ensemble aggregates give equal
weight to structures and use one retained order per structure per aggregate
row. Exact per-structure distributions are summarized exactly.
The endpoint identity is |N|-|C| = |V|-|initial_V|.

`data/summaries/pddl_retained_summary.json` contains 84 per-case endpoint
summaries, dedup aggregates, and domain leave-one-out results. `pddl_all_84.csv`
and `pddl_dedup.csv` are human-readable views used alongside the supplement.

## Output columns and denominators

`T_R`/`T_reference` and `T_E` are first-valid ranks under Reference and Exact.
`delta = T_E - T_R`; positive values mean more candidate validations under
Exact. `D = delta_invalid - delta_valid` is the paired interaction. Four-order
tables also give Union and Complex ranks. `harm`, `tie`, and `benefit` count
positive, zero, and negative differences.

Candidate-category columns describe the highest relevance bucket containing a
valid candidate: `v` counts valid candidates; `k_minus`, `k_zero`, and `k_plus`
count invalid candidates with smaller, equal, and larger effect cardinalities.
`higher_prefix` counts higher-relevance candidates. `J` counts invalid candidates
with earlier priority than the first valid candidate; `U` restricts that count
to equal-effect candidates. `mu = (v*k_minus-k_plus)/(v+1)` is finite-priority
expected delay, with exact rational `mu_fraction`; `priority_residual` is observed
delay minus expectation. Paired outputs give `expected_D` and its residual.

Budget tables cover every integer from 0 to 60. Budgets count candidate
validations, excluding offline effect-signal acquisition. The denominator is
96 structures unless explicitly conditioned on repairability. `paired_repairable`
counts structures repairable in both retained state menus;
`paired_repairable_fraction` divides it by 96. `median_paired_repairable_fraction`
summarizes that rate across replicates. Raw `paired_coverage` and
`paired_coverage_fraction` denote the same concept, not corpus-label `coverage`.

The PDDL output column `calculation_scope` distinguishes per-case summary
arithmetic from aggregate-only deduplication arithmetic. Original PDDL candidate
executions and per-case deduplication memberships are not available in this package.

`D_divided_by_own_menu` and `mean_D_divided_by_own_menu` normalize within each
structure before averaging. `ratio_sum_D_to_sum_menu` instead divides aggregate
interaction by aggregate menu size.

## Outputs and individual commands

| Subdirectory | Research content |
| --- | --- |
| `reconstruction/` | Original paired ranks and aggregate summary. |
| `secondary_analysis/` | Categories, paired mechanisms, representations, template summaries, budgets, and retained tie comparisons. |
| `candidate_analysis/` | Complete categories, construction, state-specific representation totals, tie signs, and worked examples. |
| `effect_comparison/` | Endpoint comparisons and four-order first-valid ranks. |
| `rank_analysis/` | Distributions, transitions, budgets, class representatives/members, per-state/per-pair effects, menu replicates, templates, and PDDL arithmetic. |
| `representation_analysis/` | Current-prediction representation totals/states, class heterogeneity, and complete literal example. |

```bash
python -B analysis/analyze_records.py --output secondary_results
python -B analysis/candidate_tables.py --output candidate_results
python -B analysis/compare_effects.py --output effect_results
python -B analysis/analyze_ranks.py --output rank_results
```

`four_order_representation_totals.csv` has six representation-state rows;
`four_order_representation_states.csv` has 576; `paired_outcome_prediction_counts.csv`
has 858 classes; `literal_example.csv` has eight candidates. In the example,
`base_rank` is tie-breaking priority while `Reference_rank` follows relevance
ordering. Candidate `C0005` has `base_rank=5` and `Reference_rank=4`. `Union`,
`Complex`, and `Exact` are set cardinalities; `_rank` columns are positions.
First-valid positions are 3, 1, 1, and 2 for Reference, Union, Complex, and Exact.

## Paper table map

| Paper location | File under `results/`, unless noted |
| --- | --- |
| Main Tables 1–2; Supplement S13 | `table_four_orders.csv`; `rank_analysis/first_valid_transitions.csv` |
| Supplement S5 | `data/summaries/pddl_all_84.csv` (input) |
| Supplement S9 | `candidate_analysis/construction_96.csv` |
| Supplement S10–S11 | `candidate_analysis/tie_sign_counts.csv`; `candidate_analysis/worked_examples.json` |
| Supplement S13, ranks and budgets | `rank_analysis/first_valid_ranks.csv`; `rank_analysis/four_order_all_budgets.csv` |
| Supplement S14 | `rank_analysis/representation_summary.csv` |
| Supplement S11, literal example | `representation_analysis/literal_example.csv` |
| Supplement S13, representation sensitivity | `representation_analysis/four_order_representation_totals.csv`; `representation_analysis/paired_outcome_prediction_counts.csv` |

## Stored labels and implementation names

The analysis reads historical labels directly: `contract_valid` means satisfaction
of the repair requirements. The historical `paired_contract_endpoint` label
denotes the paired-outcome representation in the controlled study and the
outcome representation in the single-state PDDL summaries. Active code uses `EditConstraints.policy_id`, while
`independent_A.source_id` remains the stored edit-policy key. The enum member
`EditOp.REPLACE_CONDITION` retains the recorded string value `REPLACE_GUARD`.
`audit` and `P_audit` name the original state resource and observer. These mappings
leave the stored data, source strings, and edit identities unchanged.

`research/api_model.json` contains the local API specifications consumed by
`ApiModel` and `ApiSpecification`. Its argument types, resource effects, returns,
and exception settings describe the supplied controlled execution API.
