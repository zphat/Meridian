# Meridian — 0.2.17

Adds ranked, evidence-based suggestions while preserving the GitHub request budget, daily goal history, detailed repair prompts and native startup recovery.

## Behavior

- Suggestions have project and status filters, priority order, source evidence, a detailed plan, and explicit Add to goals / Reopen goal actions. Existing matching work is reused. Snooze and dismissal are reversible and persist locally.
- Current-commit build failures, fresh endpoint and scheduled-monitor failures, certificate expiry, labelled issues and unchecked roadmap items supply useful signals. Old builds, stale data, cancelled/skipped runs and rate-limit errors do not invent new failures.
- Recent pushes can propose focused regression reviews. Specific findings from an update can travel with the source in MERIDIAN_GOALS.json; see [the follow-up guide](docs/suggestions.md). Commit messages and repository-authored plans are labelled as hints requiring verification.
- Accepted goals retain their checklist and relevant automatic verification rule. Completion suppresses the same proposal. A new incident, push or explicitly revised follow-up can offer reopening without silently changing the user's completed work.
- Unavailable sources keep earlier suggestions visibly stale; adoption requires fresh evidence. A disappearing feed item is not proof that a goal was completed.
- No AI service, runtime dependency, webhook, or extra polling process. Optional follow-up files are pinned to commits and cached across restarts. Source reads reuse existing GitHub/endpoint scheduling.

## Verification

Backend regressions cover ranking, current-commit evidence, stale/unavailable sources, follow-up validation, duplicate prevention, dismissal/snooze persistence, recurring failures, goal guidance, restore atomicity, cross-installation backup restoration and pinned-document caching. Browser checks cover the full suggestion flow at three widths alongside auth, goal verification, GitHub token handling and midnight history rollover.

Windows CI builds and installs the packaged application, exercises repeated native WebView2 launches and deliberate blank-page recovery, and verifies upgrade preservation and rollback. Linux installers are built and installed separately. Live device-only and private-server tests continue to require their specific evidence.
