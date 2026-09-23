## 2026-09-22 batch (no vps-state; verified from repo main@7800eaa + public URLs)

| task | profile | model class | outcome | failure pattern |
|---|---|---|---|---|
| #106 (t_d772d7a5) | platform-lead | deepseek-v4.1-flash | rework | report shape (5 sections missing); brief contained an invented step ("SHOW lc_collate", no source anywhere in repo or history) — platform-lead correctly flagged it. Pattern class: brief-invented-specific (product-owner/brief author), occurrence 1 |
| #110 (t_8af0b8ae) | backoffice | deepseek-v4.1-flash | rework | register row 6 restated the brief ("Art. 14 notice at 3 months") instead of checking code: notice is sent at recording; 3 months is retention. Platform rows sourced to "the issue and team operations" instead of the public repo. Pattern class: restates-brief-as-fact (backoffice, occurrence 1); brief-invented-specific (brief author, occurrence 2) |
| #111 (t_275e31a9) | recruiter-embedded | deepseek-v4.1-flash | rework | not a deliverable defect: request carried no sheet text and no vps-state exists, so the hard-fail row could not be judged; chief ran content check without a clean-context leaf. Pattern class: evidence-not-in-request (chief, occurrence 1 of this batch; #106/#110/#116 same root cause) |
| #116 (t_9728a279) | legal | deepseek-v4.1-flash | rework (mechanical, chief-only re-verify) | future check date 27-09-2026; rounds 1-2 were claim-vs-source mismatches (2x). Pattern class: provenance-claim-vs-source (legal, occurrence 2), mechanical-date (legal, occurrence 1). Recommended deliverable-check future-date rule |

Cross-issue: all four requests point at VPS paths that cannot be opened; until vps-state exists the review request must carry the deliverable text. Two briefs (#106, #110) contained specifics that are not in the code.
