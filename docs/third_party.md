# Sources and dependencies

## Project code and controlled data

The parser, patcher, and edit types in `research/` are author-written
implementations. The controlled study uses the project's local API, program
templates, finite candidate edits, recorded executions, and calculated results.
No AppWorld code, protected benchmark tasks, model weights, or vendor binaries
are distributed here. The code does not require an AppWorld or tau2 runtime.

## PDDL domain sources

The PDDL numerical summaries in `data/summaries/` and their derived statistics
were calculated and assembled by project code. The 84 cases comprise three
domains crossed with four fault classes and seven project-generated initial
states. The domain definitions, unlike those problem instances and numerical
summaries, came from the following fixed version of
[LLMs-Planning](https://github.com/karthikv792/LLMs-Planning/tree/fc638a1aff7df3fe7a1a1d289fa2c04cc24dc284).

| Domain | Upstream file |
| --- | --- |
| Blocksworld | [plan-bench/instances/blocksworld/generated_domain.pddl](https://github.com/karthikv792/LLMs-Planning/blob/fc638a1aff7df3fe7a1a1d289fa2c04cc24dc284/plan-bench/instances/blocksworld/generated_domain.pddl) |
| Logistics | [plan-bench/instances/logistics/generated_domain.pddl](https://github.com/karthikv792/LLMs-Planning/blob/fc638a1aff7df3fe7a1a1d289fa2c04cc24dc284/plan-bench/instances/logistics/generated_domain.pddl) |
| Depots | [plan-bench/instances/depots/generated_domain.pddl](https://github.com/karthikv792/LLMs-Planning/blob/fc638a1aff7df3fe7a1a1d289fa2c04cc24dc284/plan-bench/instances/depots/generated_domain.pddl) |

That version carries an MIT licence with copyright (c) 2024 Valmeekam Karthik.
The unchanged notice is retained in
[licenses/LLMs-Planning-MIT.txt](../licenses/LLMs-Planning-MIT.txt).
It documents the upstream domain source and does not license the project's
own code or data. Domain definitions and original problem instances are not
bundled. The supplied commands recalculate retained summary arithmetic; they
do not rerun the original PDDL tasks or candidate executions.

The earlier file-by-file ownership chain of the domain definitions remains
unverified. Those domain bodies continue to be excluded. The project's MIT and CC BY 4.0 licences do not extend to those upstream
materials.

## Python dependencies

Core study calculations use the Python standard library. Plotting requires
the versions pinned in `requirements-plot.txt`. These packages are obtained
from their own distributions rather than copied into this repository.

| Dependency | Version | Upstream licence information |
| --- | --- | --- |
| Matplotlib | 3.10.8 | [Matplotlib licence, based on the PSF licence](https://pypi.org/project/matplotlib/3.10.8/) |
| NumPy | 1.26.4 | [BSD-3-Clause; distribution also contains third-party notices](https://pypi.org/project/numpy/1.26.4/) |
| ContourPy | 1.2.0 | [BSD-3-Clause](https://pypi.org/project/contourpy/1.2.0/) |
| Cycler | 0.11.0 | [BSD](https://pypi.org/project/cycler/0.11.0/) |
| fonttools | 4.58.4 | [MIT](https://pypi.org/project/fonttools/4.58.4/) |
| kiwisolver | 1.4.7 | [BSD-3-Clause](https://pypi.org/project/kiwisolver/1.4.7/) |
| packaging | 24.2 | [Apache-2.0 or BSD-2-Clause](https://pypi.org/project/packaging/24.2/) |
| Pillow | 11.0.0 | [MIT-CMU; distribution also contains third-party notices](https://pypi.org/project/pillow/11.0.0/) |
| pyparsing | 3.1.2 | [MIT](https://pypi.org/project/pyparsing/3.1.2/) |
| python-dateutil | 2.9.0.post0 | [Apache-2.0 or BSD-3-Clause](https://pypi.org/project/python-dateutil/2.9.0.post0/) |
| six | 1.17.0 | [MIT](https://pypi.org/project/six/1.17.0/) |

Each dependency's own distribution supplies its applicable copyright and
licence notices. These dependency licences do not determine the licence for
this research package; the current terms are in [RIGHTS.txt](../RIGHTS.txt).
