# Escalation Protocol Template

**This is a template, not a policy.** Organizations deploying Preprint Sentinel must customize this document to fit their institutional structure, legal obligations, and governance framework. The suggestions below are starting points based on common biosecurity oversight practices.

---

## When Escalation Is Triggered

Escalation is triggered when:

- A paper receives a **Critical** risk tier (aggregate score 14-18 out of 18)
- The system's recommended action is **"escalate"**
- An analyst manually determines that a paper warrants escalation regardless of automated scoring

The system sends immediate notifications (email and/or Slack) when a Critical-tier paper is detected. Do not wait for the daily digest to begin review.

---

## Suggested Notification Chain

Customize this chain to match your organization's structure.

```
1. Automated system notification
   --> Senior analyst on duty (within 1 hour of notification)

2. Senior analyst initial review
   --> Biosecurity officer / DURC review committee chair (within 4 hours)

3. Biosecurity officer assessment
   --> Institutional biosafety committee (IBC) or equivalent (within 24 hours)

4. Institutional committee review
   --> External notification if required by policy (timeline per institutional policy)
```

### Roles to Define

| Role | Responsibility | Your Organization's Contact |
|------|---------------|-----------------------------|
| Senior Analyst | Initial review and triage of Critical-tier papers | _Fill in_ |
| Biosecurity Officer | Determines if institutional response is needed | _Fill in_ |
| IBC Chair | Convenes committee review if warranted | _Fill in_ |
| External Liaison | Handles notifications to funding agencies, regulatory bodies | _Fill in_ |

---

## Response Timeline Suggestions

| Action | Suggested Timeline |
|--------|--------------------|
| Acknowledge notification | Within 1 hour during business hours |
| Initial analyst review complete | Within 4 hours |
| Decision on whether to convene committee | Within 24 hours |
| Committee review (if convened) | Within 1 week |
| External notification (if required) | Per institutional policy and regulatory requirements |

These timelines assume the paper is a preprint (not yet published in a journal). If the paper has already been published, timelines may need to be compressed.

---

## Documentation Requirements

For every escalated paper, document the following:

1. **Paper identification:** Title, DOI, authors, source server, posted date
2. **System assessment:** Full Stage 2 and Stage 3 assessment outputs (preserved automatically in the assessment_logs table)
3. **Analyst assessment:** The reviewing analyst's independent evaluation, including:
   - Which risk dimensions they agree/disagree with
   - Their own risk tier determination
   - Specific passages or methods of concern
4. **Decision record:** What action was taken and why
5. **Committee minutes** (if committee was convened)
6. **External communications** (if any were made)

All of this should be recorded in the dashboard's analyst notes field and in your organization's records system.

---

## De-escalation Criteria

A paper may be de-escalated (moved from Critical to a lower tier) when:

- The analyst determines the automated scoring was incorrect after reading the full paper
- Additional context reveals the work is conducted under robust DURC oversight (IBC approval, funding agency DURC review, etc.)
- The paper is a false positive caused by keyword overlap or AI misinterpretation
- Subject matter expert consultation determines the methods described do not pose the level of risk indicated by the automated assessment
- The paper is a revised version of a previously reviewed paper where concerns have been addressed

When de-escalating, document the reasoning thoroughly in the analyst notes. Set the paper status to "False Positive" or "Archived" as appropriate.

---

## Incident Response

This section addresses scenarios where the system itself experiences problems that affect its reliability or safety.

### Scenario 1: Discovery of False Negatives

If you learn that a paper with genuine DURC concerns was NOT flagged by the system (e.g., a colleague identifies a concerning paper that Preprint Sentinel missed):

1. **Immediately review the paper** using the standard workflow -- add it manually to your review queue if possible.
2. **Investigate why it was missed.** Was it filtered out at Stage 1 (coarse filter)? Was it from a source not yet monitored? Was it in a language the system handles poorly? Did it lack an abstract?
3. **Report the miss** to the system administrator so the screening criteria can be evaluated.
4. **Check for similar papers** that may also have been missed for the same reason.
5. **Document the incident** including the paper, the root cause, and any corrective actions.

### Scenario 2: System Compromise

If there is evidence that the system has been tampered with, or that unauthorized parties have accessed the database:

1. **Notify your IT security team** immediately.
2. **Do not trust system outputs** until the integrity of the pipeline and database has been verified.
3. **Preserve logs.** Do not delete or modify assessment logs, pipeline run records, or access logs.
4. **Review recent classification changes** for signs of manipulation (e.g., Critical papers reclassified as Low, assessment logs modified).
5. **Consider whether notification is required** under your organization's data breach or security incident policies.

### Scenario 3: LLM Produces Harmful Output

If the AI model produces output that itself constitutes an information hazard (e.g., generates detailed harmful instructions in an assessment summary rather than merely describing a paper's content):

1. **Do not share the output** beyond those who need to see it for incident response.
2. **Flag the specific assessment** in the dashboard and note the issue.
3. **Report to the system administrator** so the prompt can be reviewed and the output can be investigated.
4. **The assessment log is preserved** in the database for audit purposes. Determine with your security team whether it should be redacted or retained under access controls.

### Scenario 4: Sustained Pipeline Failure

If the pipeline fails to run for more than 24 hours:

1. **Check the pipeline runs page** in the dashboard for error details.
2. **Notify the system administrator.**
3. **Be aware of the gap** in coverage. Papers posted during the outage will be picked up on the next successful run, but there may be a delay in flagging time-sensitive findings.
4. **After recovery,** verify that the backfill covers the missed period by checking the date range of the first successful run after the outage.

---

## Customization Checklist

Before deploying this protocol, your organization should:

- [ ] Assign specific individuals to each role in the notification chain
- [ ] Set response timelines appropriate to your organization's operating hours and staffing
- [ ] Determine which external parties (if any) should be notified for confirmed concerns
- [ ] Establish how escalation records will be stored (dashboard only, or also in an external records system)
- [ ] Review and align with existing institutional DURC policies and IBC procedures
- [ ] Conduct a tabletop exercise to test the escalation process
- [ ] Schedule periodic review of this protocol (suggested: annually)
