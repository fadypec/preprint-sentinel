# Preprint Sentinel -- Analyst Onboarding Guide

This guide is for biosecurity analysts who will use Preprint Sentinel to review flagged papers. No technical background is required.

---

## What Preprint Sentinel Does

Preprint Sentinel is an early-warning system that monitors life sciences preprint servers and published literature daily. It screens thousands of papers for dual-use research of concern (DURC) indicators and surfaces only those with genuine risk signals for human review.

The system does NOT make decisions. It produces risk assessments with reasoning chains that you, as a qualified analyst, will evaluate. The goal is to reduce the volume of literature you must read by approximately 99%, letting you focus on papers that actually warrant attention.

**Data sources monitored:** bioRxiv, medRxiv, PubMed, Europe PMC, arXiv, Research Square, ChemRxiv, Zenodo, and SSRN.

**What it screens for:** Papers that may involve enhancement of pathogen capabilities, lowering of barriers to creating biological threats, work with select agents or potential pandemic pathogens, novel dual-use techniques, information hazards, or inadequate discussion of dual-use risks. See the [Scoring Rubric](SCORING-RUBRIC.md) for the full criteria.

---

## Using the Dashboard

### Daily Feed

The main page shows a reverse-chronological list of papers that passed the initial screening. Each paper card displays:

- **Title** (linked to the original paper on its source server)
- **Authors, institution, and posted date**
- **Source server badge** (e.g., bioRxiv, medRxiv, PubMed)
- **Risk tier badge** (colour-coded: green for Low, amber for Medium, orange for High, red for Critical)
- **Aggregate score** (0-18)
- **Summary** (2-3 sentences explaining why the paper was flagged)

Click or expand a card to see the full dimension-by-dimension scores and justifications.

Papers are sorted by risk tier (Critical first) and then by score within each tier, so the most concerning papers appear at the top.

### Filters

You can narrow the feed using several filters:

- **Risk tier:** Select one or more tiers (Low, Medium, High, Critical) to show only papers at those levels.
- **Date range:** Show papers from a specific time period.
- **Source server:** Filter by where the paper was posted.
- **Subject category:** Filter by scientific discipline.
- **Specific risk dimension:** For example, show all papers scoring 2 or higher on "information hazard."
- **Author, institution, or country:** Search for papers from specific groups.
- **Full-text search:** Search across titles, abstracts, and assessment summaries. Type your query and press Enter.

Filters apply instantly. Multiple filters can be combined.

### Paper Detail View

Clicking into a paper shows:

- Full metadata (authors, affiliations, DOI, posted date, source)
- The complete Stage 2 (methods analysis) and Stage 3 (adjudication) assessments with reasoning
- Link to the original paper
- The methods section (if retrieved), with passages of concern noted in the assessment
- Author and institution context from OpenAlex (publication history, h-index, affiliations)
- Related papers by the same author or topic
- **Analyst notes field** (editable -- see below)
- **Status workflow** controls

---

## Interpreting Risk Scores

Each paper that passes the initial screen is assessed against 6 risk dimensions, each scored 0-3. These scores are summed to produce an aggregate score (0-18).

### The 6 Risk Dimensions

| Dimension | What It Measures | Plain Language |
|-----------|-----------------|----------------|
| **Pathogen Enhancement** | Whether the paper describes making a pathogen more dangerous (more transmissible, more virulent, able to infect new hosts, able to evade immunity or drugs) | "Does this make a pathogen worse?" |
| **Synthesis/Reconstruction Barrier Lowering** | Whether the methods make it easier to create or reconstruct dangerous pathogens -- simplified protocols, novel shortcuts, unusually detailed instructions | "Does this make dangerous work easier to do?" |
| **Select Agent / PPP Relevance** | Whether the work involves pathogens on official watch lists (CDC Select Agents, Australia Group, WHO priority pathogens, Hazard Group 3/4) | "Is this about a known dangerous pathogen?" |
| **Novelty of Dual-Use Technique** | Whether the paper introduces a genuinely new method, tool, or approach that could be misused | "Is this a new capability that could be misused?" |
| **Information Hazard** | Whether the paper provides specific, actionable information that could be directly exploited (exact genetic sequences, step-by-step protocols, synthesis routes) | "Could someone follow these instructions to cause harm?" |
| **Defensive Framing Adequacy** (inverse scoring) | Whether the authors discuss dual-use implications and risk mitigation. Higher scores mean LESS adequate framing | "Did the authors acknowledge the risks?" |

### What 0-3 Scores Mean

| Score | Meaning |
|-------|---------|
| **0** | Not applicable or no concern on this dimension |
| **1** | Indirect relevance or minor concern |
| **2** | Moderate concern; methods could be adapted or repurposed |
| **3** | Direct and significant concern on this dimension |

Note: For "Defensive Framing Adequacy," the scoring is inverted. A score of 0 means the paper has robust discussion of dual-use risks. A score of 3 means there is no mention of risks despite clearly dual-use methods.

---

## Risk Tiers

The aggregate score (sum of all 6 dimensions, maximum 18) determines the risk tier:

| Tier | Score Range | What It Means | Recommended Action |
|------|------------|---------------|-------------------|
| **Low** | 0-4 | No significant dual-use concern identified | Archive. No further action needed. |
| **Medium** | 5-8 | Some dual-use relevance but likely within normal research bounds | Monitor. Included in weekly summary for awareness. |
| **High** | 9-13 | Significant dual-use concern identified | Review. Included in daily digest. Requires your attention. |
| **Critical** | 14-18 | Serious dual-use concern across multiple dimensions | Escalate. Immediate notification. Requires senior analyst review. See [Escalation Protocol](ESCALATION-TEMPLATE.md). |

---

## Status Workflow

Every paper has a review status that you control. The workflow is:

```
Unreviewed --> Under Review --> Confirmed Concern
                            --> False Positive
                            --> Archived
```

- **Unreviewed:** Default state for all newly flagged papers. Start here.
- **Under Review:** You are actively evaluating this paper. Set this when you begin reading.
- **Confirmed Concern:** You have determined this paper raises legitimate dual-use concerns. This is a significant designation -- see guidance below.
- **False Positive:** The system flagged this paper but you have determined it does not warrant concern. This is valuable feedback.
- **Archived:** Paper has been fully processed and no longer needs attention.

### When to Mark "Confirmed Concern"

Mark a paper as Confirmed Concern when:

- The paper describes work that clearly falls within established DURC categories (gain-of-function on pandemic pathogens, barrier-lowering for select agent work, etc.)
- The dual-use risk is not adequately mitigated by the defensive context (institutional oversight, biosafety measures, etc.)
- You would recommend this paper for discussion at an institutional biosafety committee or equivalent body
- Another qualified analyst should review your assessment

Do NOT mark Confirmed Concern just because the score is high. The AI scoring is a starting point -- your expert judgment is what matters.

### When to Mark "False Positive"

Mark a paper as False Positive when:

- The paper was flagged due to keyword overlap but the actual research poses no dual-use concern
- The dual-use aspects are well-known, well-governed, and adequately discussed in the paper
- The methods described are standard practice in the field and do not lower any barriers
- The AI misunderstood the paper's content (this happens, especially with highly technical abstracts)

Marking false positives is valuable -- it helps identify where the system's screening could be improved.

---

## Using Analyst Notes Effectively

The analyst notes field on each paper is free-text. Use it to:

- Record your reasoning for the status you assigned
- Note specific passages or methods that concerned you (or that you determined were benign)
- Flag papers for follow-up (e.g., "Check if published version addresses dual-use concerns")
- Note if you consulted a subject matter expert and what they said
- Record any external context not captured by the system (e.g., "This group's previous work was reviewed by NSABB")

Good notes make your work auditable and help other analysts understand your decisions.

---

## Known Limitations

Be aware of the following limitations when using the system:

1. **Language translation:** Non-English papers are machine-translated before screening. Translation quality varies, especially for highly technical content. If a translated paper seems oddly phrased, check the original language version.

2. **Figures and supplementary data:** The system can only analyse text. It cannot assess figures, tables, supplementary materials, or data files. A paper with benign text but concerning supplementary protocols would be missed.

3. **LLM scoring blind spots:** The AI models have knowledge cutoffs and may not recognize very novel techniques that post-date their training data. Entirely new classes of dual-use risk may not be scored appropriately.

4. **Papers without abstracts:** The initial coarse filter requires an abstract to function. Papers posted without abstracts (rare but possible) will be skipped entirely.

5. **Full-text retrieval gaps:** Only 60-75% of flagged papers yield usable full text through legal, open-access channels. Papers without full text are scored on abstracts alone, which provides less information for the methods analysis stage.

6. **Preprint vs. published versions:** Preprints may be revised before journal publication. The system screens the preprint version. If a paper is later published with significant changes, the published version is not automatically re-screened.

7. **Context limitations:** The system uses publicly available metadata for author and institutional context. It cannot access internal institutional review records, IBC approvals, or funding agency DURC reviews.

---

## Escalation: What to Do When a Critical-Tier Paper Appears

When a paper is classified as Critical (aggregate score 14-18):

1. The system sends an immediate notification (email and/or Slack, depending on your organisation's configuration).
2. Open the paper in the dashboard and set its status to "Under Review."
3. Read the full assessment carefully, including all dimension justifications and the adjudication reasoning.
4. Access the original paper and read the relevant sections yourself.
5. Follow your organisation's escalation protocol. See [Escalation Protocol Template](ESCALATION-TEMPLATE.md) for the recommended process.

Do not delay reviewing Critical-tier papers. The system is configured to prioritise recall over precision, so not all Critical papers will be genuine emergencies, but each one warrants prompt attention.

---

## Getting Help

- **Technical issues with the dashboard:** Contact your system administrator.
- **Questions about the scoring rubric:** See the [Scoring Rubric](SCORING-RUBRIC.md) document.
- **Full system documentation:** See the [Development Guide](DEVELOPMENT.md) for technical details.
- **Operational procedures:** See the [Operations Guide](OPERATIONS.md).
