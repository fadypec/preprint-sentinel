# Changelog

This changelog tracks changes to Preprint Sentinel's **classification logic** -- prompt templates, scoring criteria, risk tier thresholds, and pipeline behavior that affects how papers are assessed. General feature additions, UI changes, and infrastructure updates are not tracked here unless they affect classification outcomes.

For a complete history of all changes, see the git log.

## Format

Each entry includes:
- The component affected (coarse filter, methods analysis, adjudication, pipeline)
- The version number change
- A description of what changed and why
- Whether re-scoring of recent papers is recommended

---

## Current Versions

| Component | Version | Last Updated |
|-----------|---------|-------------|
| Coarse Filter | v1.1 | See below |
| Methods Analysis | v1.0 | Initial release |
| Adjudication | v1.0 | Initial release |

---

## [v1.1] Coarse Filter -- Scope Refinement

**Component:** Coarse Filter (Stage 1)
**Prompt version:** COARSE_FILTER_VERSION = "v1.1"

### Changed
- Added explicit exclusion criteria for non-biological dual-use research: pure synthetic/organic chemistry, forensic chemistry, analytical chemistry not involving biological agents
- Added exclusion for illicit drug synthesis, controlled substance characterisation, and pharmaceutical chemistry where no biological system is involved
- Added exclusion for explosives, energetic materials, radiological, nuclear, or chemical weapons research
- Clarified that biosynthesis of controlled substances using engineered organisms IS relevant (biological DURC)
- Refined toxin-related inclusion criteria to specify "biological toxins, venoms, or biologically-derived compounds" rather than generic "toxins"

### Why
- The v1.0 coarse filter was flagging chemistry papers and drug synthesis papers that fall outside the scope of biological DURC, generating unnecessary false positives for analysts.

### Re-scoring
- Not required. This change only narrows the filter, so previously excluded papers remain excluded. Some previously flagged papers would now be correctly excluded, but re-running the coarse filter on historical data is low priority.

---

## [v1.0] Methods Analysis -- Initial Release

**Component:** Methods Analysis (Stage 2)
**Prompt version:** METHODS_ANALYSIS_VERSION = "v1.0"

### Added
- 6-dimension risk rubric: pathogen enhancement, synthesis barrier lowering, select agent relevance, novel technique, information hazard, defensive framing adequacy
- Risk tier thresholds: Low (0-4), Medium (5-8), High (9-13), Critical (14-18)
- Recommended actions per tier: archive, monitor, review, escalate

---

## [v1.0] Adjudication -- Initial Release

**Component:** Adjudication (Stage 3)
**Prompt version:** ADJUDICATION_VERSION = "v1.0"

### Added
- Contextual adjudication considering author credibility, institutional context, funding oversight, and research context
- Tier adjustment capability (up or down) based on contextual factors
- Enrichment completeness tracking with confidence reduction for partial data

---

## Template for Future Entries

```markdown
## [vX.Y] Component Name -- Brief Description

**Component:** Coarse Filter | Methods Analysis | Adjudication
**Prompt version:** VERSION_CONSTANT = "vX.Y"

### Changed / Added / Removed
- Description of change

### Why
- Reason for the change

### Re-scoring
- Whether recent papers should be re-assessed and why
```
