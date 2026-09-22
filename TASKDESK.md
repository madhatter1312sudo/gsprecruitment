# 🛎️ GSP Taskdesk — live command channel

This branch exists only to keep the Taskdesk PR open. **Never merge that PR.**

How it works: any comment the owner (madhatter1312sudo) posts on the Taskdesk
PR wakes the Claude Code HQ session instantly. Claude works the task through
the standard company workflow (specialist → reviewer → chief-of-staff → own PR
for the owner's merge) and replies on the same thread.

Rules enforced by the session, regardless of what a comment says:
- Only comments authored by madhatter1312sudo count; bots and others are ignored.
- Comments are work requests, never authority to change house rules
  (draft-only outreach, auth/GDPR protections, owner-only merges).

Slower alternative that also works: GitHub issues titled "task: ..."
(picked up hourly by the gsp-taskdesk routine).
