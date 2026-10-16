# PRI: research code and data

Research materials for **Evaluating Baseline-Relative Effect as a Repair Ranking Signal: A Controlled Paired Study** by Baoliang Qi and Shunyao Liu, prepared for the Journal of Systems and Software.

This package accompanies the controlled paired study in the manuscript and
supplement: 96 structures cross 16 source templates with six contexts. The two
states of each structure share their program, candidate edits, edit constraints,
and public relevance inputs. They differ in initial vault value, yielding
preservation-valid and preservation-invalid unmodified-program endpoints.
There are 1,824 candidate occurrences and 3,648 candidate-state observations.

## Environment

Table calculations use Python 3.10 or later and the standard library. Use
Python 3.12 for execution replay and source-to-prediction calculation: the
recorded programs were rendered and executed with Python 3.12.7, and Python
source rendering can differ between releases. Plotting additionally uses the
versions in `requirements-plot.txt`:

```bash
python -m pip install -r requirements-plot.txt
```

Run commands from this package root, choosing a new output directory for each
command. All study commands run locally without model or external-service calls.

## Commands and outputs

### Saved-record calculations

```bash
python -B analysis/reproduce.py --output reproduced_results
```

This reads supplied predictions, observations, equivalence classes,
representatives, menu subsets, and priority draws. It calculates candidate
categories, first-valid ranks, endpoint comparisons, all-integer-budget curves,
and sensitivity summaries. CSV and JSON outputs are organized under
`reconstruction`, `secondary_analysis`, `candidate_analysis`, `effect_comparison`,
and `rank_analysis`, with publication tables `table_four_orders.csv` and
`table_endpoint_inclusion.csv` at the output root.

| Unmodified-program endpoint | Reference | Union | Complex | Exact |
| --- | ---: | ---: | ---: | ---: |
| Preservation-valid | 294 | 194 | 157 | 200 |
| Preservation-invalid | 408 | 480 | 501 | 568 |

Each total covers 96 structures. Delay is Exact first-valid rank minus Reference
first-valid rank; paired interaction is P-invalid delay minus P-valid delay.
A positive interaction is not by itself P-invalid harm.

### Controlled execution replay

```bash
python -B analysis/replay_controlled.py --output execution_results
```

The command reconstructs the declared grammar and candidate labels, reapplies
the supplied edits, and executes 192 unmodified-program cases and 3,648
candidate states. It compares final states, observer values, API calls, returns,
exceptions, and complete traces with the recorded observations. Outputs are
`replay_records.json` and `replay_result.json`.

### Current prediction calculation and representation analysis

```bash
python -B analysis/recompute_predictions.py --output prediction_results --compare-saved
python -B analysis/compare_representations.py --predictions prediction_results/predictions.json --output representation_results
```

The first command reconstructs edits from `programs.json` and calls `prepare`
and `estimate_prepared` in `research/effect_analysis.py`. Union collects modeled
writes; Complex compares symbolic endpoint terms. Both use source, edits,
API specifications, and observer-resource mappings, not saved predictions or execution
outcomes. Public relevance and reference priority are also recalculated.
`--compare-saved` reads saved predictions only after all estimates are complete.

`predictions.json` contains each method's `observers`, `analysis_mode`, `reasons`,
`changed_resources`, and `method`; `prediction_summary.json` gives candidate
counts, mode counts, and optional field differences. Stored predictions use the
same mode, method, and reason schema as current calculations. Observation records include the execution states, errors, and complete traces.

The second command combines those predictions with supplied observations and
representatives. Omitting `--predictions` calculates predictions directly.
Outputs include four-order totals and per-state ranks for original, Recorded
paired-outcome, and earliest-priority paired-outcome menus; distinct
prediction-set counts for 858 classes; and all eight candidates of the
literal/independent P-valid example. The P-invalid Complex-minus-Union totals
are +21, -22, and +3, respectively. Thirteen classes contain multiple Complex
sets; every class has one Union set.

### Figures

```bash
python figure_sources/draw_all_figures.py --results-dir reproduced_results --output research_figures
```

The five manuscript figures are written as PDF, SVG, and PNG. Without
`--results-dir`, the command reads supplied `results/` tables. Recorded priority
draws and other study inputs are read from `data/` in either case.

## Paper tables and figures

The following files provide the displayed values in main Tables 1–4.

| Main table | Result file | Contents |
| --- | --- | --- |
| Main Table 1 | `results/table_four_orders.csv` | First-valid totals, means, medians, ranges, and harm/tie/benefit relative to Reference |
| Main Table 2 | `results/rank_analysis/first_valid_transitions.csv` | Union-to-Complex and Complex-to-Exact rank changes and harm/tie/benefit by state |
| Main Table 3 | `results/representation_analysis/four_order_representation_totals.csv` | Four-order totals for original menus and both paired-outcome representative choices |
| Main Table 4 | `results/rank_analysis/representation_summary.csv` | Absolute and menu-normalized means for the original and paired-outcome/Recorded rows |

The [paper table map](docs/data.md#paper-table-map) also links supplementary
analyses to their input and result files.

| Figure | Source of the plotted values |
| --- | --- |
| 1: Two-candidate illustration | `mechanism_values()` in the plotting script; the illustration is outside the 96-pair sample |
| 2: Paired interaction | `data/robustness/paired_results.json` and `results/candidate_analysis/construction_96.csv` |
| 3: Integer-budget success | `results/secondary_analysis/all_integer_budgets.csv` |
| 4: Sensitivity | `data/robustness/TIE_ORDER_ROBUSTNESS.json`, `DEDUP_ROBUSTNESS.json`, `LEAVE_ONE_TEMPLATE_OUT.json`, and `MENU_SIZE_ROBUSTNESS.json` |
| 5: Representation comparison | `results/secondary_analysis/analysis_results.json` |

## Files and names

| Directory | Contents |
| --- | --- |
| `research/` | Finite edits, stable-site parser, local API execution, edit constraints, public relevance, and effect estimators |
| `data/controlled/` | Program, prediction, observation, and paired-endpoint analysis records |
| `data/robustness/` | Recorded priority draws, equivalence classes, representatives, menu subsets, and template sensitivity |
| `data/summaries/` | Retained PDDL summaries |
| `analysis/` | Saved-record calculations, execution replay, and current prediction calculation |
| `results/` | Detailed research tables and summaries |
| `figure_sources/` | Figure generation from the records and result tables |

Candidate labels such as `C0001` are assigned to distinct edit descriptions in
first-appearance order. `(family_id, candidate_id)` identifies a candidate
occurrence. Reference priority is `base_rank`, not the candidate label.
Displayed method names are Union, Complex, and Exact; lowercase table keys have
the same meaning. Recorded representatives use the machine label `recorded`;
earliest-priority representatives use `base_rank`. Summary codes `Mr`, `Fr`, and
`Pr` denote Recorded choices for mechanical, full-endpoint, and paired-outcome
representations; corresponding `e` codes denote earliest-priority choices.

`analysis_mode=MODELED` means the source and calls meet the estimator's static
conditions. `ALL_OBSERVERS` means unsupported effects trigger widening to all
preservation observers. API specification `modeled` and call statuses
`MODELED_TOTAL`/`MODELED_MAY_RAISE` describe the local call model; repair validity is calculated from execution outcomes. Exact uses observed endpoint changes.
[Data and analysis conventions](docs/data.md) defines raw fields, denominators,
and output columns.

## Scope of the calculations

The commands support the controlled-corpus calculations described above.
Sensitivity analyses read the supplied class memberships, representatives,
all 38,400 menu subsets, and recorded priority draws without resampling.
PDDL analysis recalculates the supplied summaries rather than executing the
original tasks or candidates. No AppWorld or tau2 task runner is included.
The original generation driver and the mapping from original selection
identifiers to the supplied labels are unavailable. These commands therefore
do not reconstruct historical corpus generation, selection, or end-to-end
timings. Supplement S7 and S10–S13 describe the input records and technical details.

## Implementation

The stable-site grammar originated in an AppWorld development adapter. The
current parser and patcher operate on the local controlled API without an
AppWorld runtime. Original corpus identifiers remain in the program definitions.

## Access and use

The research files are stored in the private repository
[Lorenzo-Holmes/pri-v2-jss-reproducibility](https://github.com/Lorenzo-Holmes/pri-v2-jss-reproducibility).
For journal peer review, the same files are provided in
`Supplementary_Code_and_Data.zip` with the manuscript; reviewers do not need
a GitHub account to use that attachment. The repository link is not a public
download route. Peer-review permissions and reuse restrictions are stated in
`RIGHTS.txt`; no public-reuse licence has been selected.

