"""Calculate Union and Complex predictions from controlled source and edits."""
from pathlib import Path
from collections import Counter
import argparse
import json
import platform
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from research.candidates import generate_candidates, patch_record, OBSERVER_RESOURCES
from research.design import case_from_record
from research.features import public_relevance
from research.observers import PreservationObserver
from research.effect_analysis import ApiModel, prepare, estimate_prepared

FIELDS = ("observers", "analysis_mode", "reasons", "changed_resources", "method")
METHODS = ("union", "complex")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def calculate(root=ROOT):
    """Return predictions without reading saved predictions or observations."""
    root = Path(root)
    families = load_json(root / "data/controlled/programs.json")["families"]
    api_specifications = load_json(root / "research/api_model.json")
    api_model = ApiModel.from_dict(api_specifications)
    observers = tuple(PreservationObserver(name, frozenset([resource]))
                      for name, resource in OBSERVER_RESOURCES.items())
    rows = []
    identities = set()
    for family in families:
        case = case_from_record(family["states"][0])
        for state in family["states"][1:]:
            other = case_from_record(state)
            require((case.source, case.menus, case.edit_constraints, case.witness_sites) ==
                    (other.source, other.menus, other.edit_constraints, other.witness_sites),
                    "Paired source, edits, policy, or relevance inputs differ")
        patches = generate_candidates(case)
        require(len(patches) == len(family["candidates"]), "Candidate counts differ")
        for priority, (patch, candidate) in enumerate(zip(patches, family["candidates"]), 1):
            identity = (family["family_id"], candidate["candidate_id"])
            require(identity not in identities, "Repeated candidate identity")
            identities.add(identity)
            require(patch_record(patch) == {key: candidate[key] for key in ("edits", "cost", "size")},
                    "Generated edits differ from the supplied candidate")
            prepared = prepare(source=case.source, patch=patch, api_model=api_model,
                               observers=observers, edit_constraints=case.edit_constraints)
            estimates = {}
            for method in METHODS:
                estimate = estimate_prepared(prepared, method)
                estimates[method] = {
                    "observers": sorted(estimate.observers),
                    "analysis_mode": estimate.analysis_mode,
                    "reasons": list(estimate.reasons),
                    "changed_resources": sorted(estimate.changed_resources),
                    "method": estimate.method,
                }
            relevance = public_relevance(candidate["edits"], case.witness_sites, api_specifications["apis"])
            rows.append({"family_id": identity[0], "candidate_id": identity[1],
                         "base_rank": priority, "relevance": relevance, "predictions": estimates})
    return {"prediction_source": "current_source_calculation",
            "prediction_fields": list(FIELDS), "rows": rows}


def compare_saved(generated, path):
    """Compare only the fields calculated by this entry point."""
    saved = load_json(path)["rows"]
    expected = {(row["family_id"], row["candidate_id"]): row for row in saved}
    require(len(expected) == len(saved), "Repeated saved candidate identity")
    actual_ids = {(row["family_id"], row["candidate_id"]) for row in generated["rows"]}
    require(actual_ids == set(expected), "Saved and generated candidate identities differ")
    differences = []
    for row in generated["rows"]:
        identity = (row["family_id"], row["candidate_id"])
        old = expected[identity]
        for field in ("base_rank", "relevance"):
            if row[field] != old[field]:
                differences.append({"family_id": identity[0], "candidate_id": identity[1], "field": field,
                                    "calculated": row[field], "saved": old[field]})
        for method in METHODS:
            for field in FIELDS:
                new = row["predictions"][method][field]
                previous = old["predictions"][method][field]
                if new != previous:
                    differences.append({"family_id": identity[0], "candidate_id": identity[1],
                                        "method": method, "field": field, "calculated": new, "saved": previous})
    return differences


def run(output, compare=False):
    output = Path(output).resolve()
    require(not output.exists(), "Choose a new output directory")
    generated = calculate()
    summary = {"prediction_source": generated["prediction_source"], "python": platform.python_version(),
               "candidate_identities": len(generated["rows"]),
               "methods_each": len(generated["rows"]), "prediction_fields": list(FIELDS),
               "analysis_modes": dict(Counter(row["predictions"]["union"]["analysis_mode"]
                                          for row in generated["rows"]))}
    if compare:
        differences = compare_saved(generated, ROOT / "data/controlled/predictions.json")
        summary["saved_field_comparison"] = {"prediction_fields_per_method": list(FIELDS),
                                             "candidate_fields": ["base_rank", "relevance"],
                                             "differences": differences}
    output.mkdir(parents=True)
    (output / "predictions.json").write_text(json.dumps(generated, indent=2) + "\n", encoding="utf-8")
    (output / "prediction_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    if compare:
        require(not differences, "Calculated prediction fields differ from saved values")
    return generated


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "outputs/predictions")
    parser.add_argument("--compare-saved", action="store_true",
                        help="Compare saved fields only after calculating every prediction")
    args = parser.parse_args()
    run(args.output, args.compare_saved)
