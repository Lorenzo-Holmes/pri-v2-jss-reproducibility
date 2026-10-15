"""Shared static checks and the Union and Complex effect estimators.

Union collects modeled writes; Complex compares symbolic endpoint terms.
Unsupported effect behavior widens both methods to all preservation observers.
"""

from __future__ import annotations
import ast
from dataclasses import dataclass, field
import math
from typing import Mapping
from research.observers import PreservationObserver
from research.parser import parse_program
from research.patching import apply_python_patch

SCALAR = frozenset({"none", "bool", "int", "float", "str", "bytes"})
UNKNOWN = frozenset({"unknown"})
TYPE_NAMES = {
    type(None): "none",
    bool: "bool",
    int: "int",
    float: "float",
    str: "str",
    bytes: "bytes",
}


class AnalysisInputError(ValueError):
    pass


@dataclass(frozen=True)
class ApiSpecification:
    parameters: tuple[tuple[str, frozenset[str]], ...]
    return_category: str
    reads: frozenset[str]
    writes: tuple[tuple[str, str], ...]
    may_raise: bool
    heap_behavior: str
    unknown: bool
    modeled: bool
    exception_atomic: bool

    @classmethod
    def from_dict(cls, data):
        return cls(
            parameters=tuple(
                (parameter["name"], frozenset(parameter["types"]))
                for parameter in data["parameters"]
            ),
            return_category=data["return_category"],
            reads=frozenset(data["reads"]),
            writes=tuple(sorted(data["writes"].items())),
            may_raise=data["may_raise"],
            heap_behavior=data["heap_behavior"],
            unknown=data["unknown"],
            modeled=data["modeled"],
            exception_atomic=data["exception_atomic"],
        )

    def bind(self, args, kwargs):
        names = [p[0] for p in self.parameters]
        if len(args) > len(names):
            return None
        values = dict(zip(names, args))
        for name, value in kwargs:
            if name is None or name not in names or name in values:
                return None
            values[name] = value
        return tuple(values[n] for n in names) if set(values) == set(names) else None


@dataclass(frozen=True)
class ApiModel:
    apis: Mapping[str, ApiSpecification]
    resource_types: Mapping[str, str]

    @classmethod
    def from_dict(cls, data):
        api_model = cls(
            apis={
                name: ApiSpecification.from_dict(specification)
                for name, specification in data["apis"].items()
            },
            resource_types=data["resource_types"],
        )
        for name, specification in api_model.apis.items():
            if (
                not name.startswith("apis.")
                or len({p[0] for p in specification.parameters}) != len(specification.parameters)
                or any(mode not in {"must", "may"} for _, mode in specification.writes)
                or any(
                    type(v) is not bool
                    for v in (
                        specification.may_raise,
                        specification.unknown,
                        specification.modeled,
                        specification.exception_atomic,
                    )
                )
                or any(
                    r not in api_model.resource_types
                    for r in (*specification.reads, *(r for r, _ in specification.writes))
                )
            ):
                raise AnalysisInputError("MALFORMED_API_SPECIFICATION:" + name)
            for _, ts in specification.parameters:
                if not ts or not ts <= SCALAR | {"scalar", "heap", "unknown"}:
                    raise AnalysisInputError("MALFORMED_ARGUMENT_TYPES:" + name)
            if specification.return_category not in SCALAR | {"scalar", "heap", "unknown"}:
                if not specification.return_category.startswith("arg:"):
                    raise AnalysisInputError("MALFORMED_RETURN_CATEGORY:" + name)
                try:
                    index = int(specification.return_category[4:])
                    assert 0 <= index < len(specification.parameters)
                except (ValueError, AssertionError):
                    raise AnalysisInputError("MALFORMED_RETURN_ARGUMENT:" + name)
        return api_model


@dataclass
class Prepared:
    original_tree: ast.FunctionDef
    candidate_tree: ast.FunctionDef
    analysis_mode: str
    reasons: tuple[str, ...]
    union_resources: frozenset[str]
    observers: tuple[PreservationObserver, ...]
    api_model: ApiModel


@dataclass(frozen=True)
class Estimate:
    method: str
    observers: frozenset[str]
    analysis_mode: str
    reasons: tuple[str, ...]
    changed_resources: frozenset[str] = frozenset()


def qname(n):
    if isinstance(n, ast.Name):
        return n.id
    if isinstance(n, ast.Attribute):
        prefix = qname(n.value)
        return prefix + "." + n.attr if prefix else None
    return None


def static_api(n):
    name = qname(n)
    return name if name and name.startswith("apis.") and name.count(".") >= 2 else None


class StaticChecks:
    def __init__(self, api_model):
        self.api_model = api_model
        self.wide = set()
        self.reject = set()
        self.calls = {}
        self.writes = set()

    def scalar(self, ts):
        if not ts <= SCALAR:
            self.wide.add("ARGUMENT_TYPE_UNKNOWN:non-scalar-control")

    def expr(self, n, env):
        if n is None:
            return frozenset({"none"})
        if isinstance(n, ast.Constant):
            category = TYPE_NAMES.get(type(n.value))
            if category is None or (isinstance(n.value, float) and not math.isfinite(n.value)):
                self.wide.add("NONSCALAR_OR_NONFINITE_LITERAL")
                return UNKNOWN
            return frozenset({category})
        if isinstance(n, ast.Name):
            return env.get(n.id, frozenset({"unbound"}))
        if isinstance(n, ast.Call):
            args = [self.expr(a, env) for a in n.args]
            kwargs = [(k.arg, self.expr(k.value, env)) for k in n.keywords]
            name = static_api(n.func)
            specification = self.api_model.apis.get(name)
            status = "MODELED_TOTAL"
            if specification is None or specification.unknown or not specification.modeled:
                status = "UNKNOWN_CALL"
            else:
                self.writes.update(r for r, _ in specification.writes)
                bound = specification.bind(args, kwargs)
                if bound is None:
                    status = "SIGNATURE_MISMATCH_POSSIBLE"
                else:
                    for actual, (_, allowed) in zip(bound, specification.parameters):
                        permitted = SCALAR if "scalar" in allowed else allowed
                        if not actual <= permitted:
                            status = (
                                "ARGUMENT_TYPE_UNKNOWN"
                                if actual & {"unknown", "opaque", "unbound", "api_namespace"}
                                else "ARGUMENT_TYPE_MISMATCH_POSSIBLE"
                            )
                            break
                if status.startswith("MODELED"):
                    if specification.heap_behavior != "none" or specification.return_category in {
                        "heap",
                        "unknown",
                    }:
                        status = "UNMODELED_HEAP_OR_RETURN"
                    elif specification.may_raise and not specification.exception_atomic:
                        status = "UNMODELED_EXCEPTION_ATOMICITY"
                    elif specification.may_raise:
                        status = "MODELED_MAY_RAISE"
            self.calls[id(n)] = {
                "api": name or ast.unparse(n.func),
                "line": n.lineno,
                "status": status,
            }
            if not status.startswith("MODELED"):
                self.wide.add(status + ":" + str(name))
            if specification is None:
                return UNKNOWN
            ret = specification.return_category
            if ret.startswith("arg:"):
                bound = specification.bind(args, kwargs)
                return bound[int(ret[4:])] if bound is not None else UNKNOWN
            return SCALAR if ret == "scalar" else frozenset({ret})
        if isinstance(n, ast.BoolOp):
            values = [self.expr(v, env) for v in n.values]
            for ts in values:
                self.scalar(ts)
            return frozenset().union(*values)
        if isinstance(n, ast.UnaryOp) and isinstance(n.op, ast.Not):
            self.scalar(self.expr(n.operand, env))
            return frozenset({"bool"})
        if isinstance(n, ast.Compare):
            values = [self.expr(v, env) for v in (n.left, *n.comparators)]
            for ts in values:
                self.scalar(ts)
            for op, a, b in zip(n.ops, values, values[1:]):
                if isinstance(op, (ast.Lt, ast.LtE, ast.Gt, ast.GtE)):
                    if not (
                        (a | b) <= {"int", "float", "bool"}
                        or a | b == {"str"}
                        or a | b == {"bytes"}
                    ):
                        self.wide.add("PARTIAL_COMPARISON")
                elif not isinstance(op, (ast.Eq, ast.NotEq)):
                    self.wide.add("UNSUPPORTED_COMPARISON")
            return frozenset({"bool"})
        if isinstance(n, ast.IfExp):
            self.scalar(self.expr(n.test, env))
            return self.expr(n.body, env) | self.expr(n.orelse, env)
        self.wide.add("WIDEN_EXPRESSION:" + type(n).__name__)
        for sub in ast.iter_child_nodes(n):
            if isinstance(sub, ast.expr):
                self.expr(sub, env)
        return UNKNOWN

    def block(self, body, initial):
        env = dict(initial)
        for n in body:
            if isinstance(n, ast.Assign):
                ts = self.expr(n.value, env)
                for target in n.targets:
                    if isinstance(target, ast.Name):
                        env[target.id] = ts
                    else:
                        self.expr(target, env)
            elif isinstance(n, ast.Expr):
                self.expr(n.value, env)
            elif isinstance(n, ast.If):
                self.scalar(self.expr(n.test, env))
                yes, no = self.block(n.body, env), self.block(n.orelse, env)
                env = {
                    k: yes.get(k, frozenset({"unbound"})) | no.get(k, frozenset({"unbound"}))
                    for k in set(yes) | set(no)
                }
            elif isinstance(n, (ast.Return, ast.Raise)):
                self.expr(n.value if isinstance(n, ast.Return) else n.exc, env)
                if isinstance(n, ast.Raise):
                    self.expr(n.cause, env)
            elif isinstance(n, ast.Pass):
                pass
            else:
                self.wide.add("WIDEN_STATEMENT:" + type(n).__name__)
                for sub in ast.iter_child_nodes(n):
                    if isinstance(sub, ast.expr):
                        self.expr(sub, env)
                    elif isinstance(sub, ast.stmt):
                        self.block([sub], env)
        return env

    def check(self, source):
        try:
            parse_program(source)
            tree = ast.parse(source)
        except (ValueError, SyntaxError, TypeError) as exc:
            raise AnalysisInputError("PROGRAM_SYNTAX:" + type(exc).__name__) from exc
        if len(tree.body) != 1 or not isinstance(tree.body[0], ast.FunctionDef):
            raise AnalysisInputError("MODULE_MUST_CONTAIN_ONLY_SOLUTION")
        fn = tree.body[0]
        a = fn.args
        if (
            fn.name != "solution"
            or [x.arg for x in a.args] not in [["apis"], ["apis", "requester"]]
            or a.posonlyargs
            or a.vararg
            or a.kwarg
            or a.kwonlyargs
            or a.defaults
            or a.kw_defaults
            or any(x.annotation for x in a.args)
            or fn.decorator_list
            or fn.returns
            or fn.type_comment
            or getattr(fn, "type_params", [])
        ):
            raise AnalysisInputError("FUNCTION_SIGNATURE")
        nodes = list(ast.walk(fn))
        allowed_statements = (ast.Expr, ast.Assign, ast.If, ast.Return, ast.Raise, ast.Pass)
        wide_statements = (
            ast.For,
            ast.Break,
            ast.Continue,
            ast.AugAssign,
            ast.AnnAssign,
            ast.Assert,
        )
        api_parts = set()
        for call in (x for x in nodes if isinstance(x, ast.Call) and static_api(x.func)):
            api_parts.update(id(x) for x in ast.walk(call.func))
        for n in nodes:
            if isinstance(n, ast.stmt) and n is not fn:
                if isinstance(n, wide_statements):
                    self.wide.add("WIDEN_SYNTAX:" + type(n).__name__)
                elif not isinstance(n, allowed_statements):
                    self.reject.add("UNSUPPORTED_STATEMENT:" + type(n).__name__)
            if isinstance(n, ast.Name) and n.id == "apis":
                if isinstance(n.ctx, (ast.Store, ast.Del)):
                    self.reject.add("API_NAMESPACE_REBIND")
                elif id(n) not in api_parts:
                    self.wide.add("API_NAMESPACE_ESCAPE")
            if isinstance(n, ast.Attribute):
                if isinstance(n.ctx, (ast.Store, ast.Del)) and (qname(n) or "").startswith("apis."):
                    self.reject.add("API_NAMESPACE_MUTATION")
                elif id(n) not in api_parts:
                    self.wide.add("HEAP_ATTRIBUTE")
            if isinstance(n, ast.Assign) and (
                len(n.targets) != 1 or not isinstance(n.targets[0], ast.Name)
            ):
                self.wide.add("COMPLEX_ASSIGNMENT")
            if isinstance(
                n,
                (
                    ast.Subscript,
                    ast.List,
                    ast.Tuple,
                    ast.Set,
                    ast.Dict,
                    ast.ListComp,
                    ast.DictComp,
                    ast.SetComp,
                    ast.GeneratorExp,
                    ast.Lambda,
                    ast.NamedExpr,
                    ast.Starred,
                ),
            ):
                self.wide.add("HEAP_OR_WIDE_EXPRESSION:" + type(n).__name__)
            if isinstance(n, (ast.BinOp, ast.UnaryOp)) and not (
                isinstance(n, ast.UnaryOp) and isinstance(n.op, ast.Not)
            ):
                self.wide.add("PARTIAL_PYTHON_OPERATION")
        if self.reject:
            raise AnalysisInputError(";".join(sorted(self.reject)))
        initial_types = {"apis": frozenset({"api_namespace"})}
        if len(a.args) == 2:
            initial_types["requester"] = frozenset({"opaque"})
        self.block(fn.body, initial_types)
        branches = sum(isinstance(n, (ast.If, ast.IfExp)) for n in nodes)
        branches += sum(len(n.values) - 1 for n in nodes if isinstance(n, ast.BoolOp))
        branches += sum(len(n.ops) - 1 for n in nodes if isinstance(n, ast.Compare))
        branches += sum(r["status"] == "MODELED_MAY_RAISE" for r in self.calls.values())
        if sum(isinstance(n, ast.stmt) for n in nodes) - 1 > 256 or branches > 8:
            self.wide.add("STATIC_PATH_OR_STATEMENT_LIMIT")
        return fn


def prepare(*, source, patch, api_model, observers, edit_constraints=None):
    if len({o.observer_id for o in observers}) != len(observers) or not observers:
        raise AnalysisInputError("INVALID_OBSERVERS")
    for o in observers:
        if not o.observer_id or any(r not in api_model.resource_types for r in o.resources):
            raise AnalysisInputError("UNKNOWN_OBSERVER_RESOURCE")
    old = StaticChecks(api_model)
    old_tree = old.check(source)
    try:
        candidate = apply_python_patch(source, patch, edit_constraints=edit_constraints)
    except (ValueError, TypeError, SyntaxError, KeyError) as exc:
        raise AnalysisInputError("INVALID_PATCH:" + type(exc).__name__) from exc
    new = StaticChecks(api_model)
    new_tree = new.check(candidate)
    reasons = tuple(sorted(old.wide | new.wide))
    return Prepared(
        old_tree,
        new_tree,
        "ALL_OBSERVERS" if reasons else "MODELED",
        reasons,
        frozenset(old.writes | new.writes),
        tuple(observers),
        api_model,
    )


class Terms:
    def __init__(self):
        self.nodes = []
        self.ids = {}

    def term(self, *key):
        if key not in self.ids:
            self.ids[key] = len(self.nodes)
            self.nodes.append(key)
        return self.ids[key]

    def literal(self, v):
        return self.term("lit", TYPE_NAMES[type(v)], v)

    def observations(self, x):
        n = self.nodes[x]
        if n[0] == "lit":
            return bool(n[2]), None, True
        if n[0] == "not":
            constant, atom, sign = self.observations(n[1])
            return (not constant, None, True) if atom is None else (None, atom, not sign)
        return None, self.term("truth", x), True

    def negate(self, x):
        constant, atom, sign = self.observations(x)
        return self.literal(not constant) if atom is None else self.term("not", x)

    def ite(self, atom, yes, no):
        return yes if yes == no else self.term("ite", atom, yes, no)


@dataclass
class State:
    env: dict
    resources: dict
    path: dict = field(default_factory=dict)
    done: bool = False

    def copy(self):
        return State(dict(self.env), dict(self.resources), dict(self.path), self.done)


class Transfer:
    def __init__(self, api_model, terms):
        self.api_model = api_model
        self.t = terms

    def split_atom(self, state, atom, sign=True):
        result = []
        for value in (True, False):
            actual = value if sign else not value
            if atom in state.path and state.path[atom] != actual:
                continue
            s = state.copy()
            s.path[atom] = actual
            result.append((value, s))
        return result

    def split(self, value, state):
        constant, atom, sign = self.t.observations(value)
        return [(constant, state)] if atom is None else self.split_atom(state, atom, sign)

    def expression(self, n, state):
        t = self.t
        if state.done:
            return [(t.literal(None), state)]
        if n is None:
            return [(t.literal(None), state)]
        if isinstance(n, ast.Constant):
            return [(t.literal(n.value), state)]
        if isinstance(n, ast.Name):
            if n.id not in state.env:
                s = state.copy()
                s.done = True
                return [(t.literal(None), s)]
            return [(state.env[n.id], state)]
        if isinstance(n, ast.Call):
            entries = [([], state)]
            exprs = list(n.args) + [k.value for k in n.keywords]
            for expr in exprs:
                entries = [
                    (values + [value], s2)
                    for values, s in entries
                    for value, s2 in self.expression(expr, s)
                ]
            out = []
            name = static_api(n.func)
            specification = self.api_model.apis[name]
            for values, s in entries:
                if s.done:
                    out.append((t.literal(None), s))
                    continue
                args = specification.bind(
                    values[: len(n.args)],
                    [(k.arg, v) for k, v in zip(n.keywords, values[len(n.args) :])],
                )
                reads = tuple((r, s.resources[r]) for r in sorted(specification.reads))
                context = (name, args, reads)
                branches = [(False, s)]
                if specification.may_raise:
                    atom = t.term("call_failure", *context)
                    branches = self.split_atom(s, atom)
                for failed, b in branches:
                    b = b.copy()
                    if failed:
                        b.done = True
                        out.append((t.literal(None), b))
                        continue
                    for r, mode in specification.writes:
                        b.resources[r] = (
                            t.term("write", r, *context)
                            if mode == "must"
                            else t.term("may_write", r, *context, s.resources[r])
                        )
                    result = (
                        t.literal(None)
                        if specification.return_category == "none"
                        else t.term("return", *context)
                    )
                    out.append((result, b))
            return out
        if isinstance(n, ast.UnaryOp):
            return [(t.negate(v), s) for v, s in self.expression(n.operand, state)]
        if isinstance(n, ast.BoolOp):
            entries = self.expression(n.values[0], state)
            for right in n.values[1:]:
                out = []
                for value, s in entries:
                    if s.done:
                        out.append((value, s))
                        continue
                    for observations, b in self.split(value, s):
                        if observations == isinstance(n.op, ast.And):
                            out.extend(self.expression(right, b))
                        else:
                            out.append((value, b))
                entries = out
            return entries
        if isinstance(n, ast.IfExp):
            out = []
            for v, s in self.expression(n.test, state):
                if s.done:
                    out.append((v, s))
                    continue
                for observations, b in self.split(v, s):
                    out.extend(self.expression(n.body if observations else n.orelse, b))
            return out
        if isinstance(n, ast.Compare):
            entries = self.expression(n.left, state)
            finished = []
            for i, (op, right) in enumerate(zip(n.ops, n.comparators)):
                out = []
                for left, s in entries:
                    for val, b in self.expression(right, s):
                        if b.done:
                            finished.append((t.literal(None), b))
                            continue
                        ln, rn = t.nodes[left], t.nodes[val]
                        if ln[0] == rn[0] == "lit":
                            a, c = ln[2], rn[2]
                            ops = {
                                ast.Eq: lambda: a == c,
                                ast.NotEq: lambda: a != c,
                                ast.Lt: lambda: a < c,
                                ast.LtE: lambda: a <= c,
                                ast.Gt: lambda: a > c,
                                ast.GtE: lambda: a >= c,
                            }
                            cmp = t.literal(ops[type(op)]())
                        else:
                            cmp = t.term("compare", type(op).__name__, left, val)
                        if i == len(n.ops) - 1:
                            finished.append((cmp, b))
                        else:
                            for observations, q in self.split(cmp, b):
                                (out if observations else finished).append(
                                    (val if observations else t.literal(False), q)
                                )
                entries = out
            return finished
        raise AssertionError("analysis_mode/transfer expression mismatch:" + type(n).__name__)

    def block(self, body, states):
        for n in body:
            out = []
            for state in states:
                if state.done:
                    out.append(state)
                    continue
                if isinstance(n, ast.Pass):
                    out.append(state)
                elif isinstance(n, ast.If):
                    for value, s in self.expression(n.test, state):
                        if s.done:
                            out.append(s)
                            continue
                        for observations, b in self.split(value, s):
                            out.extend(self.block(n.body if observations else n.orelse, [b]))
                else:
                    expr = n.value if isinstance(n, (ast.Expr, ast.Assign, ast.Return)) else n.exc
                    values = self.expression(expr, state)
                    if isinstance(n, ast.Raise) and n.cause is not None:
                        values = [
                            (value, q)
                            for value, s in values
                            for _, q in self.expression(n.cause, s)
                        ]
                    for value, s in values:
                        s = s.copy()
                        if isinstance(n, ast.Assign) and not s.done:
                            s.env[n.targets[0].id] = value
                        if isinstance(n, (ast.Return, ast.Raise)):
                            s.done = True
                        out.append(s)
            states = out
        return states

    def merge(self, states, resource, default):
        def reduce(entries):
            if not entries:
                return default
            values = {v for path, v in entries}
            if len(values) == 1:
                return next(iter(values))
            atoms = {a for path, v in entries for a in path}
            if not atoms:
                raise AssertionError("overlapping terminal states disagree")
            atom = min(atoms)
            children = []
            for sign in (True, False):
                subset = [
                    ({a: b for a, b in p.items() if a != atom}, v)
                    for p, v in entries
                    if p.get(atom, sign) == sign
                ]
                children.append(reduce(subset))
            return self.t.ite(atom, *children)

        return reduce([(s.path, s.resources[resource]) for s in states])


def estimate_prepared(prepared, method="complex"):
    p = prepared
    if method not in {"complex", "union"}:
        raise ValueError(method)
    if p.analysis_mode == "ALL_OBSERVERS":
        return Estimate(
            method, frozenset(o.observer_id for o in p.observers), p.analysis_mode, p.reasons
        )
    if method == "union":
        observers = frozenset(o.observer_id for o in p.observers if o.resources & p.union_resources)
        return Estimate(method, observers, p.analysis_mode, (), p.union_resources)
    terms = Terms()
    initial = {r: terms.term("initial_resource", r) for r in p.api_model.resource_types}
    env = {"apis": terms.term("immutable_namespace")}
    if len(p.original_tree.args.args) == 2:
        env["requester"] = terms.term("opaque_input", "requester")
    transfer = Transfer(p.api_model, terms)
    original = transfer.block(p.original_tree.body, [State(dict(env), dict(initial))])
    candidate = transfer.block(p.candidate_tree.body, [State(dict(env), dict(initial))])
    original_final = {r: transfer.merge(original, r, initial[r]) for r in initial}
    candidate_final = {r: transfer.merge(candidate, r, initial[r]) for r in initial}
    changed = frozenset(r for r in initial if original_final[r] != candidate_final[r])
    observers = frozenset(o.observer_id for o in p.observers if o.resources & changed)
    return Estimate(method, observers, p.analysis_mode, (), changed)
