"""Compare four orders under original and paired-outcome representations.

Predictions are calculated from source unless --predictions supplies the output
of recompute_predictions.py. Endpoint observations and representative selections
remain the supplied study inputs.
"""
from pathlib import Path
from collections import Counter
import argparse
import csv
import json

from recompute_predictions import ROOT, calculate, load_json, require

ORDERS = ("Reference", "Union", "Complex", "Exact")
CONDITIONS = ("STATE_VALID", "STATE_INVALID")
EXAMPLE = "PRI_00_0_literal_independent"


def ordered(rows, method):
    return sorted(rows, key=lambda row: (-row["relevance"],
                  0 if method == "Reference" else row[method], row["base_rank"]))


def write_csv(path, rows):
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def run(output, predictions=None):
    output = Path(output).resolve()
    require(not output.exists(), "Choose a new output directory")
    supplied = calculate() if predictions is None else load_json(predictions)
    predicted = {(row["family_id"], row["candidate_id"]): row for row in supplied["rows"]}
    require(len(predicted) == len(supplied["rows"]), "Repeated prediction identity")
    families = load_json(ROOT / "data/controlled/programs.json")["families"]
    expected = {(family["family_id"], candidate["candidate_id"])
                for family in families for candidate in family["candidates"]}
    require(set(predicted) == expected, "Prediction identities differ from program candidates")
    observed = load_json(ROOT / "data/controlled/observations.json")["rows"]
    executions = {(row["family_id"], row["condition"], row["candidate_id"]): row for row in observed}
    require(len(executions) == len(observed) == 2 * len(expected), "Observation identities differ")
    menus = {}
    candidate_records = {}
    nested, extra = 0, Counter()
    for family in families:
        fid = family["family_id"]
        for state in family["states"]:
            definition = state["definition"]
            preservation_requirements = definition["independent_P"]
            rows = []
            for priority, candidate in enumerate(family["candidates"], 1):
                cid = candidate["candidate_id"]
                candidate_records[fid, cid] = candidate
                record = executions[fid, state["condition"], cid]
                prediction = predicted[fid, cid]
                require(prediction["base_rank"] == priority == record["base_rank"], "Reference priority differs")
                require(prediction["relevance"] == record["relevance"], "Relevance differs")
                start, end = record["original_execution"], record["candidate_execution"]
                effects = {key for key in preservation_requirements if start["observers"][key] != end["observers"][key]}
                violations = {key for key, value in preservation_requirements.items() if end["observers"][key] != value}
                edits_allowed = (candidate["cost"] <= definition["B"] and
                              all(edit["op"] in definition["independent_A"]["allowed_ops"].get(edit["site"], [])
                                  for edit in candidate["edits"]))
                valid = edits_allowed and end["error"] is None and end["state"]["goal"] is True and not violations
                require(valid == record["contract_valid"], "Calculated repair validity differs")
                union = set(prediction["predictions"]["union"]["observers"])
                complex_ = set(prediction["predictions"]["complex"]["observers"])
                require(effects <= complex_ <= union, "Endpoint inclusion does not hold")
                nested += 1
                extra["Union"] += len(union - effects)
                extra["Complex"] += len(complex_ - effects)
                rows.append({"candidate_id": cid, "base_rank": priority, "relevance": prediction["relevance"],
                             "contract_valid": bool(valid), "goal": end["state"]["goal"],
                             "preservation_valid": not violations, "error": end["error"],
                             "Union": len(union), "Complex": len(complex_), "Exact": len(effects),
                             "union_observers": sorted(union), "complex_observers": sorted(complex_),
                             "exact_observers": sorted(effects)})
            menus[fid, state["condition"]] = rows

    variants = load_json(ROOT / "data/robustness/DEDUP_ROBUSTNESS.json")["variants"]
    representations = {"original": None}
    heterogeneity = {"classes": 0, "Union": 0, "Complex": 0}
    class_rows = []
    for variant in variants:
        if variant["signature"] != "paired_contract_endpoint":
            continue
        choice = variant["representative"]
        name = {"recorded": "recorded", "base_rank": "earliest"}[choice]
        member_map = {}
        for family in variant["equivalence_classes"]:
            fid = family["structure"]
            flattened = [cid for group in family["groups"] for cid in group["members"]]
            require(len(flattened) == len(set(flattened)) and
                    set(flattened) == {row["candidate_id"] for row in menus[fid, CONDITIONS[0]]},
                    "Class members do not partition the original menu")
            member_map[fid] = {group["representative"] for group in family["groups"]}
            for number, group in enumerate(family["groups"], 1):
                require(group["representative"] in group["members"], "Representative is outside its class")
                if choice == "base_rank":
                    earliest = min(group["members"], key=lambda cid: predicted[fid, cid]["base_rank"])
                    require(group["representative"] == earliest, "Earliest representative differs from reference priority")
                else:
                    heterogeneity["classes"] += 1
                    class_row = {"family_id": fid, "class_number": number,
                                 "members": json.dumps(group["members"]), "recorded": group["representative"]}
                    for method in ("Union", "Complex"):
                        sets = {tuple(predicted[fid, cid]["predictions"][method.lower()]["observers"])
                                for cid in group["members"]}
                        heterogeneity[method] += len(sets) > 1
                        class_row[method + "_distinct_sets"] = len(sets)
                    class_rows.append(class_row)
        require(set(member_map) == {family["family_id"] for family in families}, "Representation structures differ")
        representations[name] = member_map
    require(set(representations) == {"original", "recorded", "earliest"}, "Missing paired-outcome representation")

    totals, state_ranks = [], []
    for representation, members in representations.items():
        for condition in CONDITIONS:
            total = {"representation": representation, "condition": condition, "structures": len(families)}
            sums = Counter()
            for family in families:
                fid = family["family_id"]
                rows = menus[fid, condition]
                selected = rows if members is None else [row for row in rows if row["candidate_id"] in members[fid]]
                rank_row = {"representation": representation, "family_id": fid,
                            "condition": condition, "menu_size": len(selected)}
                require(any(row["contract_valid"] for row in selected), "Representation has no valid candidate")
                for method in ORDERS:
                    first = next(rank for rank, row in enumerate(ordered(selected, method), 1) if row["contract_valid"])
                    rank_row[method] = first
                    sums[method] += first
                state_ranks.append(rank_row)
            total.update({method: sums[method] for method in ORDERS})
            total["Complex_minus_Union"] = sums["Complex"] - sums["Union"]
            totals.append(total)

    example_rows = menus[EXAMPLE, "STATE_VALID"]
    sequences = {method: [row["candidate_id"] for row in ordered(example_rows, method)] for method in ORDERS}
    example = []
    for row in example_rows:
        full = {"family_id": EXAMPLE, "condition": "STATE_VALID", "candidate_id": row["candidate_id"],
                "edits": json.dumps(candidate_records[EXAMPLE, row["candidate_id"]]["edits"]),
                **{key: value for key, value in row.items() if key != "candidate_id"}}
        for field in ("union_observers", "complex_observers", "exact_observers"):
            full[field] = json.dumps(full[field])
        full.update({method + "_rank": sequences[method].index(row["candidate_id"]) + 1 for method in ORDERS})
        example.append(full)
    first_valid = {method: next(rank for rank, row in enumerate(ordered(example_rows, method), 1)
                               if row["contract_valid"]) for method in ORDERS}
    summary = {"prediction_source": "calculated from source" if predictions is None else "supplied recomputation output",
               "endpoint_inclusion": {"satisfied": nested, "candidate_states": len(observed)},
               "extra_labels": dict(extra), "rank_totals": totals,
               "paired_outcome_prediction_heterogeneity": heterogeneity,
               "literal_independent_P_valid": {"candidate_count": len(example), "sequences": sequences,
                                                "first_valid": first_valid}}
    output.mkdir(parents=True)
    write_csv(output / "four_order_representation_totals.csv", totals)
    write_csv(output / "four_order_representation_states.csv", state_ranks)
    write_csv(output / "paired_outcome_prediction_counts.csv", class_rows)
    write_csv(output / "literal_example.csv", example)
    (output / "representation_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "outputs/representations")
    parser.add_argument("--predictions", type=Path,
                        help="predictions.json written by recompute_predictions.py; otherwise calculate from source")
    args = parser.parse_args()
    run(args.output, args.predictions)
