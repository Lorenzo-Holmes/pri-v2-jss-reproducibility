"""Deterministic candidate-execution domain with explicit API semantics.

Executes the local API and records outcomes for effect and ranking analyses.
"""
from copy import deepcopy
from types import SimpleNamespace
from research import candidates as candidate_model

def execute(source,case):
    api=candidate_model.ToyAPI(case.initial)
    events=[]
    def wrap(name,fn,tick=False):
        def called(*args,**kwargs):
            event={"api":name,"args":deepcopy(args),"kwargs":deepcopy(kwargs),"before":dict(api.state)}
            events.append(event)
            try:
                if tick: api._tick()
                result=fn(*args,**kwargs)
                event["result"]=deepcopy(result)
                event["scalar_return"]=type(result) in (type(None),bool,int,float,str,bytes)
                return result
            except Exception as exc:
                event["exception"]=type(exc).__name__
                raise
            finally:
                event["after"]=dict(api.state)
        return called
    def put(resource,value):
        api.state[resource]=value
    def verify(ok):
        if not ok: raise ValueError("declared API exception")
    def mutate(box,v):
        box["x"]=v
    toy_names=("noop","goal","finish","set_vault","set_audit","commit_alias","make_alias",
               "set_buffer","flush","unknown")
    namespaces={"toy":SimpleNamespace(**{n:wrap("apis.toy."+n,getattr(api,n)) for n in toy_names})}
    for resource in ("mail","calendar","out"):
        namespaces[resource]=SimpleNamespace(
            get=wrap("apis."+resource+".get",lambda r=resource:api.state[r],True),
            set=wrap("apis."+resource+".set",lambda v,r=resource:put(r,v),True))
    namespaces["out"].write=wrap("apis.out.write",lambda v:put("out",v),True)
    namespaces["values"]=SimpleNamespace(
        pick=wrap("apis.values.pick",lambda v:v,True),
        box=wrap("apis.values.box",lambda v:{"x":v},True),
        mutate=wrap("apis.values.mutate",mutate,True),
        readbox=wrap("apis.values.readbox",lambda a:a["x"],True))
    namespaces["check"]=SimpleNamespace(
        verify=wrap("apis.check.verify",verify,True),
        mail=wrap("apis.check.mail",lambda:verify(api.state["mail"]>=0),True))
    namespaces["unknown"]=SimpleNamespace(mutate=wrap("apis.unknown.mutate",lambda v:put("calendar",v),True))
    namespace={"__builtins__":{}}
    error=None
    try:
        exec(compile(source,"<controlled_program>","exec"),namespace)
        namespace["solution"](SimpleNamespace(**namespaces))
    except Exception as exc:
        error=type(exc).__name__+": "+str(exc)
    return {"state":dict(api.state),"error":error,"api_calls":api.calls,"trace":events,
        "observers":{o:api.state[r] for o,r in candidate_model.OBSERVER_RESOURCES.items()}}

