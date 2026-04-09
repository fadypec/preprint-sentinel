# Risk Dimensions: Alignment with the Fink Report

## How the six dimensions relate to the Fink Report

The Fink Report (NRC, 2004) defined seven categories of **experiments of concern**:

| # | Fink category | Our coverage |
|---|---|---|
| 1 | Render a vaccine ineffective | **Pathogen enhancement** (immune evasion) |
| 2 | Confer resistance to antibiotics/antivirals | **Pathogen enhancement** (drug resistance) |
| 3 | Enhance virulence or render a nonpathogen virulent | **Pathogen enhancement** (virulence) |
| 4 | Increase transmissibility | **Pathogen enhancement** (transmissibility) |
| 5 | Alter host range | **Pathogen enhancement** (host range) |
| 6 | Enable evasion of diagnostic/detection modalities | Partially under **pathogen enhancement**, but not explicitly scored |
| 7 | Enable weaponisation of a biological agent or toxin | Split across **synthesis barrier lowering** and **information hazard**, but no dedicated dimension |

The key structural difference: **Fink categorises by what you do to a pathogen. Our rubric categorises by what kind of risk the paper represents.** Fink's seven categories are experiment-type taxonomies; our six dimensions are risk-factor axes.

## What we collapse

Fink categories 1-5 all map to our single **pathogen enhancement** dimension. This is deliberate for a screening tool -- these categories frequently co-occur (a paper on H5N1 airborne transmission touches transmissibility, host range, and immune evasion simultaneously), and distinguishing between them is exactly the kind of expert judgment the human analyst should be making, not the automated screen.

## What we add beyond Fink

Three of our six dimensions have no Fink equivalent:

**Synthesis/reconstruction barrier lowering** -- Fink was written in 2004, before the 2005 H1N1 reconstruction, the 2012 H5N1 GOF controversy, and the explosion of synthetic biology tooling. The concern about *democratisation of dangerous capabilities* (simplified reverse genetics, benchtop pathogen synthesis, cell-free systems) has become central to DURC policy but didn't exist as a discrete category in Fink. The 2014 US GOF moratorium and the 2024 NSABB DURC policy revision both emphasise this axis.

**Novelty of dual-use technique** -- Captures whether the paper describes a methodological advance that creates new dual-use capabilities (CRISPR-based gene drives, AI-guided protein design, automated directed evolution). Fink couldn't have anticipated the pace of enabling technology. This dimension helps distinguish "established GOF work with known oversight" from "entirely new capability that oversight hasn't caught up with."

**Defensive framing adequacy** (inverse scoring) -- A meta-dimension about responsible conduct. A paper describing identical methods but with robust dual-use discussion, IBC approval, and risk mitigation is categorically less concerning for triage purposes than one with no mention of biosafety. This helps analysts prioritise: papers scoring high here deserve earlier attention because they may indicate researchers who haven't engaged with the dual-use implications of their own work.

## What we reframe

**Select agent/PPP relevance** isn't a Fink category but provides a severity axis that Fink assumed implicitly. Working with variola (HG4) is categorically different from working with seasonal influenza (HG2) even if the experiment type is identical. By scoring this separately, we let the aggregate score reflect both "what was done" and "how dangerous is the agent involved."

**Information hazard** partially maps to Fink #7 (weaponisation) but is really about publication risk -- how specific, actionable, and reproducible is the information in the paper? This is closer to the Bostrom information hazard framework and the debate around whether the Fouchier/Kawaoka H5N1 papers should have been published. A paper could score 0 on pathogen enhancement (purely computational) but 3 on information hazard (provides a complete recipe).

## What's arguably missing

Three gaps worth considering:

1. **Detection/diagnostic evasion** (Fink #6) is subsumed under "pathogen enhancement" but is arguably distinct. Engineering a pathogen to evade environmental biosurveillance or clinical diagnostics is a weaponisation concern, not a biological enhancement in the traditional sense. A dedicated dimension here would catch papers on stealth modifications, antigen masking, or environmental persistence that don't neatly fit "enhancement."

2. **Delivery and weaponisation** (Fink #7) is split across synthesis barrier lowering and information hazard but has no dedicated dimension. Work on aerosolisation, environmental dispersal, stabilisation, or novel delivery vectors (nanoparticles, insect vectors) is a distinct concern from pathogen enhancement. The coarse filter mentions "novel delivery mechanisms" as a flag, but the methods analysis doesn't score it separately.

3. **Ecological/agricultural threats** are mentioned in the coarse filter but don't have dedicated scoring. Agricultural bioweapons (crop pathogens, livestock diseases, gene drives in wild populations) are a significant DURC concern addressed in the Australia Group lists but underrepresented in a rubric centred on human pathogens.

## Why six?

Six is a pragmatic choice, not a principled one. Enough dimensions to capture meaningfully different risk axes without making the aggregate score noisy or making it hard for an LLM to score consistently. Each additional dimension adds both signal and noise -- the LLM must understand and apply each one correctly, and the analyst must review each justification.

If expanding, the strongest candidates would be:
- Split **detection evasion** out of pathogen enhancement (Fink #6)
- Add **delivery/weaponisation** as a dedicated dimension (Fink #7)

That would give 8 dimensions (max score 24) and full Fink coverage plus the modern additions. The tradeoff is slightly more API cost per paper at the Sonnet stage and more for the analyst to review per paper.

## Re-running is cheap

There are currently only ~30 papers at methods_analysed/adjudicated stage. Re-running Stage 3 on those with a revised rubric would cost under $1 in Sonnet calls. If the dimensions are revised, now is the time -- before the backlog of 217 coarse-filter-passed papers gets processed.
