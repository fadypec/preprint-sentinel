# Preprint Sentinel -- Scoring Rubric

This document describes the classification pipeline and scoring criteria used by Preprint Sentinel to assess papers for dual-use research of concern (DURC). It is intended for auditors, oversight bodies, and analysts who need to understand exactly how papers are scored.

**Important:** This document must be kept in sync with `pipeline/triage/prompts.py`, which contains the actual prompt text sent to the AI models. If there is any discrepancy, `prompts.py` is authoritative.

---

## Pipeline Overview

Papers are assessed in three stages, each using a different AI model at a different cost/capability tier. This tiered approach keeps costs manageable while ensuring thorough analysis of papers that warrant it.

```
Stage 1: Coarse Filter (Haiku) -- binary pass/fail on ~5,000 papers/day
    |
    v  (~5% pass)
Stage 2: Methods Analysis (Sonnet) -- 6-dimension scoring on ~250 papers/day
    |
    v  (Medium-High and above)
Stage 3: Adjudication (Opus) -- contextual review on ~5-20 papers/day
```

---

## Stage 1: Coarse Filter

**Model:** Claude Haiku (fast, inexpensive)
**Input:** Title and abstract only
**Output:** Binary relevant/not-relevant classification with confidence score
**Current version:** v1.1

The coarse filter is designed for **high recall** -- it should catch virtually every paper with any dual-use relevance, at the cost of also passing through some false positives. A paper only needs to be *plausibly* relevant to pass this stage.

### Inclusion Criteria (flag as RELEVANT)

A paper is flagged if its abstract suggests ANY of the following:

- Enhancement of pathogen transmissibility, virulence, host range, or immune evasion
- Reconstruction or synthesis of dangerous pathogens (select agents, potential pandemic pathogens, or novel threats)
- Novel methods for producing biological toxins, venoms, or biologically-derived compounds with harm potential (not illicit drugs or purely synthetic chemicals)
- Techniques that could lower barriers to creating biological weapons (simplified reverse genetics, benchtop synthesis protocols, democratised access to dangerous capabilities)
- Gain-of-function research on potential pandemic pathogens
- Novel delivery mechanisms for biological agents (aerosol, vector-based, environmental release)
- Identification of novel vulnerabilities in human, animal, or plant biology that could be exploited
- Work on agents listed under the Australia Group, BWC, or national select agent regulations
- De novo protein design or directed evolution of proteins with potential toxin-like or pathogen-enhancing functions
- Dual-use research on prions, mirror-life organisms, or xenobiology
- AI/ML methods specifically applied to pathogen enhancement, toxin design, or bioweapon-relevant optimisation

### Exclusion Criteria (flag as NOT RELEVANT)

A paper is excluded if it is:

- Standard clinical research, epidemiology, or public health surveillance (unless involving enhanced pathogens)
- Drug discovery, vaccine development, or diagnostics (unless the methods themselves are dual-use)
- Basic molecular biology, structural biology, or biochemistry with no obvious dual-use application
- Ecology, environmental science, or agriculture (unless involving biological control agents with crossover potential)
- Pure computational biology or bioinformatics methods papers (unless specifically applied to the above)
- Pure synthetic/organic chemistry, forensic chemistry, or analytical chemistry not involving biological agents, toxins, or pathogens
- Purely chemical synthesis of illicit drugs, controlled substance characterisation, or pharmaceutical chemistry where no biological system is involved in production. However, biosynthesis of controlled substances using engineered organisms IS relevant
- Explosives, energetic materials, radiological, nuclear, or chemical weapons research (security concerns but not biological DURC)

### Filtering Threshold

Papers are discarded when the model is confident (above the configured threshold, default 0.8) that the paper is not relevant. When there is ANY ambiguity, the model is instructed to flag the paper as relevant.

**Expected filter rate:** approximately 95% of papers are discarded at this stage.

---

## Stage 2: Methods Analysis

**Model:** Claude Sonnet (balanced capability and cost)
**Input:** Methods section (preferred) or full text, plus abstract
**Output:** Structured 6-dimension risk assessment
**Current version:** v1.0

Papers that pass the coarse filter are assessed against six risk dimensions. Each dimension is scored 0-3. The scores are summed to produce an aggregate score (0-18) which determines the risk tier.

### Dimension 1: Pathogen Enhancement

**What it measures:** Whether the paper describes experimental enhancement of pathogen capabilities.

| Score | Criteria |
|-------|----------|
| **0** | No enhancement work described. |
| **1** | Indirect relevance -- e.g., characterisation work that could inform enhancement but does not perform it. |
| **2** | Methods described could be adapted for enhancement, even if that is not the paper's stated purpose. |
| **3** | Direct enhancement of pathogen transmissibility, virulence, host range, immune evasion, or drug resistance is described. |

### Dimension 2: Synthesis/Reconstruction Barrier Lowering

**What it measures:** Whether the methods lower technical barriers to synthesising or reconstructing dangerous pathogens.

| Score | Criteria |
|-------|----------|
| **0** | No barrier lowering. Methods are standard and well-established. |
| **1** | Minor simplifications or optimisations to existing protocols. |
| **2** | Significant simplification -- makes previously difficult work substantially more accessible. Protocols are unusually detailed. |
| **3** | Transformative barrier lowering -- novel techniques that make dangerous work accessible to a much wider range of actors. |

### Dimension 3: Select Agent / PPP Relevance

**What it measures:** Whether the work involves pathogens on official watch lists or potential pandemic pathogens.

| Score | Criteria |
|-------|----------|
| **0** | No relevant agents. Work involves non-pathogenic organisms or well-characterised, low-risk agents. |
| **1** | Hazard Group 2 or non-select agents. Agents with limited pathogenic potential. |
| **2** | Hazard Group 3 or CDC Select Agents. Agents that can cause serious disease but for which treatments exist. |
| **3** | Hazard Group 4, potential pandemic pathogens (PPPs), or Tier 1 Select Agents. Agents that cause severe disease with no effective treatment or vaccine, or that pose a pandemic risk. |

**Reference lists:** WHO priority pathogens, Australia Group common control lists, US CDC/APHIS Select Agents and Toxins list, UK ACDP Hazard Groups.

### Dimension 4: Novelty of Dual-Use Technique

**What it measures:** Whether the paper introduces genuinely new methods, tools, or approaches with dual-use potential.

| Score | Criteria |
|-------|----------|
| **0** | Well-established methods only. No novel dual-use potential. |
| **1** | Incremental improvements to existing methods. Marginal increase in dual-use relevance. |
| **2** | Significant methodological advance with clear dual-use potential. |
| **3** | Transformative new capability -- a genuinely novel technique, tool, or approach that could substantially alter the dual-use landscape. |

### Dimension 5: Information Hazard

**What it measures:** Whether the paper provides specific, actionable information that could be directly misused.

| Score | Criteria |
|-------|----------|
| **0** | Information is generic, conceptual, or already widely known in the field. |
| **1** | Some specific details but not sufficient for direct misuse without substantial additional expertise. |
| **2** | Detailed protocols or data that meaningfully reduce the effort required for misuse. |
| **3** | The paper is essentially a recipe -- exact sequences, step-by-step protocols, or detailed synthesis routes that could be directly followed. |

### Dimension 6: Defensive Framing Adequacy (Inverse Scoring)

**What it measures:** Whether the paper adequately discusses dual-use implications and risk mitigation. Note that this dimension uses **inverse scoring** -- higher scores indicate LESS adequate framing.

| Score | Criteria |
|-------|----------|
| **0** | Robust dual-use discussion. Risk mitigation measures described. Defensive context is clear and thorough. |
| **1** | Some mention of dual-use concerns or biosafety measures, but not comprehensive. |
| **2** | Minimal acknowledgement of dual-use implications. Biosafety discussion is cursory or absent for work that clearly warrants it. |
| **3** | No mention of dual-use risks whatsoever, despite clearly dual-use methods being described. |

---

## Aggregate Score and Risk Tiers

The aggregate score is the sum of all 6 dimension scores. Maximum possible score is 18.

| Risk Tier | Score Range | Recommended Action | Description |
|-----------|-----------|-------------------|-------------|
| **Low** | 0-4 | Archive | No significant dual-use concern. No further action needed. |
| **Medium** | 5-8 | Monitor | Some dual-use relevance. Include in weekly summary for analyst awareness. |
| **High** | 9-13 | Review | Significant dual-use concern. Include in daily digest. Requires analyst attention. |
| **Critical** | 14-18 | Escalate | Serious dual-use concern across multiple dimensions. Immediate notification. Requires senior analyst review. |

---

## Stage 3: Adjudication

**Model:** Claude Opus (highest capability)
**Input:** Full text, Stage 2 assessment, and enrichment data (author profiles, institutional context, funding information)
**Output:** Contextual assessment that may adjust the risk tier up or down
**Current version:** v1.0

Adjudication is triggered for papers scoring Medium-High or above from Stage 2. It considers contextual factors that the methods analysis cannot assess:

### Contextual Factors Considered

1. **Author credibility:** Is the research group well-established in this field? Considers h-index, citation counts, publication volume, and institutional affiliation (sourced from OpenAlex).

2. **Institutional context:** Is the institution known for responsible dual-use research? Is it a major research university, government laboratory, or biodefense facility with established oversight structures?

3. **Funding oversight:** Is the work funded by an agency with DURC review processes (e.g., NIH, BARDA, DTRA, BBSRC, Wellcome Trust)? Funded research at these agencies undergoes institutional biosafety committee (IBC) review.

4. **Research context:** Does the work duplicate or extend previously published research? Is this incremental work within a well-governed research programme, or a concerning new direction from an unexpected source?

5. **Enrichment completeness:** If enrichment data is partial (some external sources failed to respond), the adjudicator notes which sources were unavailable and reduces confidence accordingly.

### Tier Adjustment

The adjudicator may adjust the risk tier UP or DOWN based on context:

- **Downgrade example:** A paper from a well-known virology laboratory with NIH funding and IBC approval described in the methods may be downgraded from High to Medium.
- **Upgrade example:** A paper with no institutional affiliation, no ORCID identifiers, and unusually detailed protocols may be upgraded.

The adjustment reasoning is always documented and visible to the analyst in the paper detail view.

---

## Keeping This Document Current

This rubric reflects the prompts in `pipeline/triage/prompts.py` as of the versions listed above. When prompts are modified:

1. Update the version constants in `prompts.py`.
2. Update this document to reflect any changes to scoring criteria.
3. Add an entry to `CHANGELOG.md` documenting the change.
4. Consider re-running recent assessments to check for regression.
