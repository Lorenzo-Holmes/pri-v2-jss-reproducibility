"""Reapply recorded edits and compare complete controlled execution traces."""

from pathlib import Path
import sys, json, argparse, platform, ast

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
from input_data import json_value

sys.path.insert(0, str(ROOT))
from research.design import generate
from research.design import case_from_record
from research.domain import execute
from research import candidates as candidate_model
from research.patching import apply_python_patch
from research.features import public_relevance


def require(condition, message):
    if not condition:
        raise ValueError(message)


def run(out):
    require(not out.exists(), "Choose a new output directory")
    out.mkdir(parents=True)
    get = lambda k: json.loads(
        (ROOT / "data/controlled" / (k + ".json")).read_text(encoding="utf-8")
    )
    data, observations, predictions = get("programs"), get("observations"), get("predictions")
    api_specifications = json.loads((ROOT / "research/api_model.json").read_text())["apis"]
    generated = json_value(generate())
    require(
        generated == data["families"], "Full grammar reconstruction differs from recorded corpus"
    )
    observations_by_state = {
        (r["family_id"], r["condition"], r["candidate_id"]): r for r in observations["rows"]
    }
    unmodified_executions = {r["state_id"]: r["execution"] for r in observations["initials"]}
    predictions_by_candidate = {(r["family_id"], r["candidate_id"]): r for r in predictions["rows"]}
    expected_candidates = {
        (f["family_id"], c["candidate_id"]) for f in generated for c in f["candidates"]
    }
    expected_states = {s["state_id"] for f in generated for s in f["states"]}
    expected_observations = {
        (f["family_id"], s["condition"], c["candidate_id"])
        for f in generated
        for s in f["states"]
        for c in f["candidates"]
    }
    require(
        len(predictions_by_candidate) == len(predictions["rows"])
        and set(predictions_by_candidate) == expected_candidates,
        "Prediction identities differ from candidate menus",
    )
    require(
        len(unmodified_executions) == len(observations["initials"])
        and set(unmodified_executions) == expected_states,
        "Unmodified execution identities differ",
    )
    require(
        len(observations_by_state) == len(observations["rows"])
        and set(observations_by_state) == expected_observations,
        "Candidate-state execution identities differ",
    )
    counts = {
        "families_regenerated": len(generated),
        "candidate_sources_reapplied": 0,
        "initial_executions": 0,
        "candidate_executions": 0,
        "public_relevance_checks": 0,
        "complete_trace_comparisons": 0,
        "repair_requirement_evaluations": 0,
    }
    records = []
    mismatches = []

    def compare(actual, expected, location):
        if actual != expected:
            mismatches.append(location)

    for f in generated:
        for state in f["states"]:
            case = case_from_record(state)
            unmodified_execution = json_value(execute(case.source, case))
            counts["initial_executions"] += 1
            compare(
                unmodified_execution, unmodified_executions[state["state_id"]], state["state_id"]
            )
            counts["complete_trace_comparisons"] += 1
            input_state = case.initial.copy()
            candidates = candidate_model.generate_candidates(case)
            require(len(candidates) == len(f["candidates"]), "Reconstructed menu size differs")
            for patch, c in zip(candidates, f["candidates"]):
                require(
                    json_value(candidate_model.patch_record(patch))
                    == {k: v for k, v in c.items() if k not in ("patched_source", "candidate_id")},
                    "Reconstructed edit descriptor differs",
                )
                source = apply_python_patch(
                    case.source, patch, edit_constraints=case.edit_constraints
                )
                require(source == c["patched_source"], "Reapplied candidate source differs")
                counts["candidate_sources_reapplied"] += 1
                tree = ast.parse(source)
                require(
                    not any(
                        isinstance(
                            n,
                            (
                                ast.Import,
                                ast.ImportFrom,
                                ast.For,
                                ast.While,
                                ast.With,
                                ast.AsyncFunctionDef,
                            ),
                        )
                        for n in ast.walk(tree)
                    ),
                    "Candidate contains syntax outside the controlled corpus",
                )
                execution = json_value(execute(source, case))
                counts["candidate_executions"] += 1
                r = observations_by_state[f["family_id"], state["condition"], c["candidate_id"]]
                compare(
                    execution,
                    r["candidate_execution"],
                    "/".join((f["family_id"], state["condition"], c["candidate_id"])),
                )
                compare(
                    unmodified_execution,
                    r["original_execution"],
                    "/".join(
                        (
                            f["family_id"],
                            state["condition"],
                            c["candidate_id"],
                            "unmodified execution",
                        )
                    ),
                )
                require(case.initial == input_state, "Execution mutated the input-state definition")
                counts["complete_trace_comparisons"] += 1
                rel = public_relevance(c["edits"], case.witness_sites, api_specifications)
                require(
                    rel
                    == r["relevance"]
                    == predictions_by_candidate[f["family_id"], c["candidate_id"]]["relevance"],
                    "Public relevance differs from the records",
                )
                counts["public_relevance_checks"] += 1
                obligations = state["definition"]["independent_P"]
                obs = execution["observers"]
                unmodified_observers = unmodified_execution["observers"]
                unmodified_violations = {
                    k for k, v in obligations.items() if unmodified_observers[k] != v
                }
                vc = {k for k, v in obligations.items() if obs[k] != v}
                e = {k for k in obligations if obs[k] != unmodified_observers[k]}
                for name, value in {
                    "E": e,
                    "V": vc,
                    "N": vc - unmodified_violations,
                    "C": unmodified_violations - vc,
                    "initial_V": unmodified_violations,
                }.items():
                    require(sorted(value) == sorted(r[name]), "Recorded endpoint set differs")
                valid = (
                    case.edit_constraints.allows_patch(patch)
                    and execution["error"] is None
                    and execution["state"]["goal"] is True
                    and not vc
                )
                require(bool(valid) == r["contract_valid"], "Derived repair validity differs")
                counts["repair_requirement_evaluations"] += 1
                records.append(
                    {
                        "family_id": f["family_id"],
                        "state": state["condition"],
                        "candidate_id": c["candidate_id"],
                        "execution": execution,
                        "valid": bool(valid),
                    }
                )
    result = {
        "calculation": "controlled_execution_replay",
        "python": platform.python_version(),
        "platform": platform.platform(),
        "counts": counts,
        "mismatches": len(mismatches),
        "input_files": [
            "programs.json",
            "observations.json",
            "predictions.json",
            "research/api_model.json",
        ],
        "regenerated_observation_fields": [
            "state",
            "error",
            "api_calls",
            "trace (arguments, returns, exceptions, before/after)",
            "observers",
        ],
    }
    if mismatches:
        result["mismatch_details"] = mismatches
    (out / "replay_result.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    (out / "replay_records.json").write_text(json.dumps(records, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
    require(
        not mismatches,
        str(len(mismatches)) + " execution observations differ from the supplied records",
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output", type=Path, default=ROOT / "outputs/replay")
    run(p.parse_args().output)
