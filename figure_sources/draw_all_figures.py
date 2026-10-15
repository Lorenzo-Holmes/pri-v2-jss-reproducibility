"""Plot the five manuscript figures from the study data and analysis tables.

Run from the extracted code/data root:
    python figure_sources/draw_all_figures.py --output regenerated_figures
The output directory must not already exist.
Plotting dependencies are specified in requirements-plot.txt.
"""
from pathlib import Path
import argparse
import csv
import json
import statistics
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap, Normalize
from matplotlib.patches import Rectangle, FancyArrowPatch
from matplotlib.lines import Line2D
from matplotlib.ticker import PercentFormatter

ROOT = Path(__file__).resolve().parents[1]
BLUE = "#17689B"
ORANGE = "#C16A21"
INK = "#26333C"
GRAY = "#BBC4CA"
GRID = "#E0E5E8"
WIDTH = 6.45
NAMES = {1:"figure1_mechanism",2:"figure2_paired_interaction",
         3:"figure3_all_budgets",4:"figure4_robustness",5:"figure5_representation"}

TEMPLATE_LABELS = {
    "literal": "Literal replacement",
    "value_dependency": "Value dependency",
    "resource_chain": "Resource dependency chain",
    "delete_overwrite": "Delete overwrite",
    "branch_guard": "Branch condition",
    "early_return": "Early return",
    "control_bypass": "Control-flow bypass",
    "may_raise": "Exception-raising call",
    "high_write_only": "Branch-contained writes",
    "two_edits": "Two edits",
    "unknown": "Unmodelled API effects",
    "insertion": "Call insertion",
    "multiple_observers": "Multiple observations",
    "alias": "Object alias",
    "unreachable_correction": "Unreachable correction",
    "resource_correction": "Resource-mediated correction",
}
CONTEXT_LABELS = {
    "independent": "Independent\noutput write",
    "irrelevant": "Unrelated\nresource",
    "overwritten": "Overwritten\nwrite",
    "heap_alias": "Shared-object\nalias",
    "unreachable": "Unreachable\nbranch",
    "exception": "Exception\ncheck",
}

def load(name):
    return json.loads((ROOT / name).read_text(encoding="utf-8"))

def read_values(results_dir=None):
    results_dir = ROOT / "results" if results_dir is None else Path(results_dir)
    hist = load("data/robustness/paired_results.json")
    records = hist["records"]
    contexts = list(dict.fromkeys(r["context"] for r in records))
    templates = list(dict.fromkeys(r["template"] for r in records))
    index = {(r["template"],r["context"]):r for r in records}
    assert len(index)==len(records) and set(index)=={(t,c) for t in templates for c in contexts}
    with (results_dir/"candidate_analysis/construction_96.csv").open(encoding="utf-8") as f:
        table = {r["structure"]:r for r in csv.DictReader(f)}
    matrix=[]
    for template in templates:
        values=[]
        for context in contexts:
            r=index[template,context];v=r["states"]["STATE_VALID"];i=r["states"]["STATE_INVALID"]
            d=(i["T_E"]-i["T_reference"])-(v["T_E"]-v["T_reference"])
            assert d==r["interaction_delta"]==int(table[r["structure"]]["D"])
            values.append(d)
        matrix.append(values)
    with (results_dir/"secondary_analysis/all_integer_budgets.csv").open(encoding="utf-8") as f:
        budget=list(csv.DictReader(f))
    budget=[r for r in budget if r["representation"]=="original"]
    assert all(int(r["denominator"])==len(records) for r in budget)
    tie=load("data/robustness/TIE_ORDER_ROBUSTNESS.json")
    assert len(tie["aggregate_mean_draws"])==tie["aggregate_interaction_mean"]["n"]
    dedup=load("data/robustness/DEDUP_ROBUSTNESS.json")
    primary=next(r for r in dedup["variants"] if r["signature"]=="paired_contract_endpoint" and r["representative"]=="recorded")
    loo=load("data/robustness/LEAVE_ONE_TEMPLATE_OUT.json")["records"]
    assert len(loo)==len(templates)
    menu=load("data/robustness/MENU_SIZE_ROBUSTNESS.json")["fractions"]
    representations=json.loads((results_dir/"secondary_analysis/analysis_results.json").read_text(encoding="utf-8"))["representations"]
    assert len(representations)==1+len(dedup["variants"])
    return dict(hist=hist,contexts=contexts,templates=templates,matrix=matrix,budget=budget,
                tie=tie["aggregate_interaction_mean"],dedup=primary,
                loo=[r["interaction"]["mean"] for r in loo],menu=menu,reps=representations)

def style():
    plt.rcParams.update({
        "font.family":"DejaVu Sans","font.size":9.5,"axes.labelsize":10,
        "axes.titlesize":10,"xtick.labelsize":9,"ytick.labelsize":9.5,
        "legend.fontsize":9.3,"text.color":INK,"axes.labelcolor":INK,
        "xtick.color":INK,"ytick.color":INK,"axes.edgecolor":INK,
        "axes.linewidth":.75,"lines.linewidth":1.45,"mathtext.fontset":"dejavusans",
        "pdf.fonttype":42,"ps.fonttype":42,"svg.fonttype":"path",
        "savefig.facecolor":"white",
        "figure.facecolor":"white","axes.facecolor":"white","text.usetex":False,
    })

def clean_axes(ax, grid="x"):
    ax.spines[["top","right"]].set_visible(False)
    ax.tick_params(width=.65,length=3)
    ax.set_axisbelow(True)
    if grid:ax.grid(axis=grid,color=GRID,linewidth=.55)

def save(fig,out,number):
    # Fixed physical width matches the manuscript's 164 mm text width.
    name=NAMES[number]
    fig.savefig(out/(name+".pdf"),metadata={"Title":name,"Creator":"Matplotlib",
                "CreationDate":None,"ModDate":None})
    fig.savefig(out/(name+".svg"),metadata={"Date":None})
    fig.savefig(out/(name+".png"),dpi=600)
    plt.close(fig)

def mechanism_values():
    """Calculate the four endpoints used in the illustrative example.

    The illustrative program fixes B=finish(True, True), A=goal(True), and B-before-A
    Reference priority. ToyAPI.goal/finish in the included reference source
    establish these final states. Sets index the single illustrated obligation.
    """
    rows=[]
    for initial in [7,0]:
        vb={'vault'} if initial!=7 else set()
        pair=[]
        for name,final,reference in [('B',7,1),('A',initial,2)]:
            e={'vault'} if final!=initial else set()
            vc={'vault'} if final!=7 else set()
            pair.append(dict(initial=initial,candidate=name,goal=True,vault=final,
                             V_b=sorted(vb),E=sorted(e),V_c=sorted(vc),
                             N=sorted(vc-vb),C=sorted(vb-vc),valid=not vc,
                             reference_rank=reference))
        order=sorted(pair,key=lambda x:(len(x['E']),x['reference_rank']))
        for rank,r in enumerate(order,1):r['exact_rank']=rank
        rows.extend(pair)
    return rows

def figure1(values,out):
    fig=plt.figure(figsize=(WIDTH,4.95))
    fig.text(.5,.985,"Repair requirements: goal = True; vault = 7",ha="center",va="top",fontsize=10)
    fig.text(.5,.941,"P-valid / P-invalid describe the unmodified endpoints; both fail the goal.",
             ha="center",va="top",fontsize=8.8)
    records=mechanism_values()
    show=lambda xs:"{"+", ".join(xs)+"}" if xs else "∅"
    for panel,initial in enumerate([7,0]):
        ax=fig.add_axes([.022+panel*.50,.16,.456,.665]);ax.set(xlim=(-.014,1.014),ylim=(0,1));ax.axis("off")
        ax.text(0,1.064,f"({chr(97+panel)}) Initial vault = {initial}",ha="left",va="bottom",weight="bold",fontsize=10)
        ax.text(.5,1.002,"P-valid unmodified endpoint" if initial==7 else "P-invalid unmodified endpoint",ha="center",va="top",fontsize=9.5)
        ax.add_patch(Rectangle((.12,.80),.76,.14,facecolor="white",edgecolor=GRAY,linewidth=.8))
        ax.text(.5,.895,f"goal = False; vault = {initial}",ha="center",va="center",fontsize=9)
        ax.text(.5,.846,"V$_b$ = "+show([] if initial==7 else ['vault']),ha="center",va="center",fontsize=9)
        pair=[r for r in records if r['initial']==initial]
        for x,r in zip([0,.53],pair):
            cx=x+.235;invalid=not r['valid']
            ax.add_patch(FancyArrowPatch((.5,.782),(cx,.707),arrowstyle="-|>",mutation_scale=9,
                                        color=INK,linewidth=.9,connectionstyle="arc3,rad=0"))
            ax.add_patch(Rectangle((x,.018),.47,.67,facecolor="white",edgecolor=ORANGE if invalid else GRAY,
                                   linewidth=1.5 if invalid else .8,linestyle=(0,(4,2)) if invalid else '-'))
            ax.text(cx,.643,"Candidate "+r['candidate'],ha="center",va="center",weight="bold",fontsize=9.5)
            ax.text(cx,.591,"finish(True, True)" if r['candidate']=='B' else "goal(True)",ha="center",va="center",fontsize=8.9)
            ax.text(cx,.510,f"goal = True\nvault = {r['vault']}",ha="center",va="center",fontsize=9.1,linespacing=1.3)
            for y,key,label in [(.415,'E','E'),(.365,'V_c','V$_c$'),(.315,'N','N'),(.265,'C','C')]:
                ax.text(cx,y,label+" = "+show(r[key]),ha="center",va="center",fontsize=9.1)
            ax.text(cx,.197,'Invalid repair' if invalid else 'Valid repair',ha="center",va="center",weight="bold",
                    color=ORANGE if invalid else BLUE,fontsize=9.4)
            ax.text(cx,.130,f"Reference rank {r['reference_rank']}",ha="center",va="center",fontsize=9)
            ax.text(cx,.073,f"Exact rank {r['exact_rank']}",ha="center",va="center",fontsize=9,
                    weight="bold" if invalid else "normal",color=ORANGE if invalid else INK)
    fig.text(.5,.106,"Shared relevance; Reference priority: B before A.",ha="center",fontsize=9)
    fig.text(.5,.062,"E: changed observations    V$_b$ / V$_c$: unmodified / candidate violations",ha="center",fontsize=8.7)
    fig.text(.5,.023,"N: new violations    C: corrected violations",ha="center",fontsize=8.7)
    save(fig,out,1)

def figure2(values,out):
    matrix=np.asarray(values['matrix']);n_templates,n_contexts=matrix.shape
    fig=plt.figure(figsize=(WIDTH,5.6))
    ax=fig.add_axes([.365,.19,.605,.66])
    cmap=LinearSegmentedColormap.from_list("effect",["#F7FAFC","#BBD8E8","#17689B","#083F66"])
    im=ax.imshow(matrix,cmap=cmap,norm=Normalize(0,12),aspect="auto",interpolation="nearest")
    ax.set_yticks(range(n_templates),[TEMPLATE_LABELS[s] for s in values['templates']],fontsize=8.8)
    ax.set_xticks(range(n_contexts),[CONTEXT_LABELS[s] for s in values['contexts']],fontsize=8.7)
    ax.xaxis.tick_top();plt.setp(ax.get_xticklabels(),rotation=25,ha="center",va="bottom",rotation_mode="default")
    ax.tick_params(axis="both",length=0,pad=7)
    ax.set_xticks(np.arange(-.5,n_contexts,1),minor=True);ax.set_yticks(np.arange(-.5,n_templates,1),minor=True)
    ax.grid(which="minor",color="white",linewidth=.7);ax.tick_params(which="minor",length=0)
    for spine in ax.spines.values():spine.set_visible(False)
    for i in range(n_templates):
        for j in range(n_contexts):
            ax.text(j,i,str(matrix[i,j]),ha="center",va="center",color="white" if matrix[i,j]>=8 else INK,fontsize=9.7)
        # One outline per contiguous run: adjacent changed cells retain their
        # single grid boundary, instead of receiving two near-parallel strokes.
        marked=matrix[i]!=matrix[i,0];j=0
        while j<n_contexts:
            if not marked[j]:j+=1;continue
            start=j
            while j<n_contexts and marked[j]:j+=1
            ax.add_patch(Rectangle((start-.44,i-.44),j-start-.12,.88,fill=False,edgecolor="white",linewidth=1.25))
    cax=fig.add_axes([.365,.102,.605,.020]);cb=fig.colorbar(im,cax=cax,orientation="horizontal",ticks=[0,2,4,6,8,10,12])
    cb.outline.set_visible(False);cb.ax.tick_params(labelsize=9,length=3)
    cb.set_label("Paired interaction D (candidate validations)",fontsize=10,labelpad=6)
    fig.text(.365,.148,"Outlines mark differences from independent output writes.",fontsize=8.2)
    save(fig,out,2)

def figure3(values,out):
    fig,axes=plt.subplots(1,2,figsize=(WIDTH,3.60),sharey=True)
    fig.subplots_adjust(left=.13,right=.975,bottom=.31,top=.865,wspace=.26)
    specs=[('STATE_VALID','success_R',BLUE,'-','P-valid / Reference'),
           ('STATE_VALID','success_E',BLUE,(0,(4,2)),'P-valid / Exact effect'),
           ('STATE_INVALID','success_R',ORANGE,'-','P-invalid / Reference'),
           ('STATE_INVALID','success_E',ORANGE,(0,(4,2)),'P-invalid / Exact effect')]
    handles=[]
    for ax,maxb,title in zip(axes,[60,19],['(a) All budgets: 0–60','(b) Early budgets: 0–19']):
        for state,key,color,ls,label in specs:
            rows=sorted((r for r in values['budget'] if r['state']==state),key=lambda r:int(r['budget']))
            x=[int(r['budget']) for r in rows];y=[int(r[key])/int(r['denominator']) for r in rows]
            assert x==list(range(61)) and all(a<=b for a,b in zip(y,y[1:]))
            line,=ax.step(x,y,where='post',color=color,linestyle=ls,label=label,linewidth=1.45)
            if ax is axes[0]:handles.append(line)
        ax.set(xlim=(0,maxb),ylim=(0,1.025),xlabel='Validation budget B')
        ax.set_title(title,loc='left',pad=9,weight='bold',fontsize=10)
        ax.set_xticks([0,10,20,30,40,50,60] if maxb==60 else [0,3,6,9,12,15,19])
        ax.set_yticks([0,.25,.5,.75,1]);ax.yaxis.set_major_formatter(PercentFormatter(1,decimals=0))
        clean_axes(ax,'y')
    axes[0].set_ylabel('Success (% of 96 structures)',fontsize=9.7);axes[1].tick_params(labelleft=True)
    fig.legend(handles,[s[4] for s in specs],loc='lower center',bbox_to_anchor=(.53,.012),ncol=2,
               frameon=False,columnspacing=1.6,handlelength=2.6,labelspacing=.55,fontsize=9.1)
    save(fig,out,3)

def figure4(values,out):
    fig,(a,b)=plt.subplots(2,1,figsize=(WIDTH,4.60),sharex=True)
    fig.subplots_adjust(left=.282,right=.80,top=.91,bottom=.12,hspace=.78)
    original=values['hist']['aggregate']['interaction']['mean'];tie=values['tie'];loo=values['loo']
    rows=[('Original',original,original,original,'o',BLUE),
          ('Tie-order',tie['median'],tie['percentiles']['5'],tie['percentiles']['95'],'D',BLUE),
          ('Recorded\nrepresentatives',values['dedup']['aggregate']['interaction']['mean'],values['dedup']['aggregate']['interaction']['mean'],values['dedup']['aggregate']['interaction']['mean'],'s',BLUE),
          ('Leave-one-\ntemplate-out',statistics.mean(loo),min(loo),max(loo),'^',ORANGE)]
    for y,(_,point,lo,hi,marker,color) in enumerate(rows):
        if lo!=hi:
            a.hlines(y,lo,hi,color=color,linewidth=1.2);a.vlines([lo,hi],y-.095,y+.095,color=color,linewidth=.9)
        a.plot(point,y,marker=marker,color=color,markersize=5.8,linestyle='none')
    a.set_yticks(range(4),[r[0] for r in rows]);a.set_title('(a) Ranking sensitivity analyses',loc='left',weight='bold',pad=12,fontsize=10)
    a.set(ylim=(3.6,-.55));a.tick_params(labelbottom=True)
    for y,r in enumerate(values['menu']):
        b.plot(r['interaction_mean']['median'],y,marker='o',markerfacecolor='white',markeredgecolor=BLUE,markeredgewidth=1.35,markersize=6,linestyle='none')
        b.text(1.08,y,f"{r['paired_coverage_fraction']['median']:.1%}",transform=b.get_yaxis_transform(),ha='left',va='center',fontsize=9.5)
    b.text(1.08,1.035,'Median\ncoverage',transform=b.transAxes,ha='left',va='bottom',fontsize=9)
    b.set_yticks(range(4),[f"Menu {r['fraction']:.0%}" for r in values['menu']])
    b.set_title('(b) Menu subsampling',loc='left',weight='bold',pad=12,fontsize=10)
    b.set(ylim=(3.55,-.55),xlim=(0,3.05),xlabel='Paired interaction D (candidate validations)')
    for ax in [a,b]:
        ax.set_xticks(np.arange(0,3.01,.5));clean_axes(ax,'x');ax.spines['left'].set_visible(False);ax.tick_params(axis='y',length=0,pad=8)
    save(fig,out,4)

def figure5(values,out):
    fig=plt.figure(figsize=(WIDTH,4.15))
    labels=fig.add_axes([.024,.145,.278,.745]);labels.set(xlim=(0,1),ylim=(0,8.4));labels.axis('off')
    ax=fig.add_axes([.32,.145,.665,.745]);ax.set(ylim=(0,8.4),xlim=(0,3.02))
    ys=[7.8,6.3,5.3,3.9,2.9,1.5,.5]
    for y,r in zip(ys,values['reps']):
        obs=r['observed_D']['mean'];exp=r['expected_D']['mean']
        ax.plot([exp,obs],[y,y],color=GRAY,linewidth=1.0,zorder=2)
        ax.plot(obs,y,'o',color=BLUE,markersize=5.8,zorder=4)
        ax.plot(exp,y,'s',color=ORANGE,markersize=5.6,zorder=3)
    labels.text(0,7.8,'Original',va='center',weight='bold',fontsize=9.5)
    for y,title in [(6.95,'Mechanical'),(4.55,'Full endpoint'),(2.15,'Paired-outcome')]:labels.text(0,y,title,va='center',weight='bold',fontsize=9.5)
    for y in [6.3,3.9,1.5]:labels.text(.10,y,'Recorded',va='center',fontsize=9.3)
    for y in [5.3,2.9,.5]:labels.text(.10,y,'Earliest priority',va='center',fontsize=9.3)
    for y in [7.3,4.9,2.5]:ax.axhline(y,color=GRID,linewidth=.55,zorder=0)
    ax.set_yticks([]);ax.set_xticks(np.arange(0,3.1,.5));ax.set_xlabel('Paired interaction D (candidate validations)')
    clean_axes(ax,'x');ax.spines['left'].set_visible(False)
    handles=[Line2D([],[],marker='o',color=BLUE,linestyle='none',markersize=5.8,label='Observed mean D'),
             Line2D([],[],marker='s',color=ORANGE,linestyle='none',markersize=5.6,label='Uniform-priority expected mean D')]
    fig.legend(handles=handles,loc='upper center',bbox_to_anchor=(.5,.995),ncol=2,frameon=False,
               handletextpad=.5,columnspacing=1.4,fontsize=9.1)
    save(fig,out,5)


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--output",type=Path,required=True)
    ap.add_argument("--results-dir",type=Path,default=ROOT/"results",
                    help="Calculated table directory; defaults to the supplied results")
    ap.add_argument("--figures",nargs="+",type=int,choices=range(1,6),default=[1,2,3,4,5])
    args=ap.parse_args()
    if args.output.exists():raise SystemExit("Choose a new output directory.")
    args.output.mkdir(parents=True)
    style();values=read_values(args.results_dir)
    for number in args.figures:globals()["figure"+str(number)](values,args.output)
    print("Wrote",len(args.figures),"figures as vector PDF/SVG and 600 dpi PNG to",args.output)
if __name__=="__main__":main()

