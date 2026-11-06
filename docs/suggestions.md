# Recording useful follow-ups for Meridian

Meridian 0.2.17 observes the default branches of Latitude, Longitude and Sundial during its normal GitHub refresh. It ranks current failures, open issues, unchecked roadmap items and recent-change review hints. No hosted service, webhook or AI subscription is required.

## When finishing an update

Record concrete work that remains after testing. A follow-up should explain the observed limitation or unperformed check, why it matters, and what evidence would finish it. Do not invent filler, leave fixed issues labelled as broken, or expose credentials. A repository file can suggest work, but cannot execute commands or automatically complete a goal.

For a simple task, use an unchecked Markdown item in the root `PROJECT_STATUS.md` or `docs/ROADMAP.md`:

```markdown
- [ ] [high] Test the updated editor controls at 800 × 600 on Windows
```

Meridian reads the first available file in that order. Mark the checkbox complete after the actual test. `[critical]`, `[high]`, `[medium]`, `[low]` and `[p0]`–`[p3]` prefixes are supported. Unlabelled work defaults to medium priority.

## Detailed follow-ups

Put `MERIDIAN_GOALS.json` at the root of the companion repository and commit it with the update. Start with [this example](MERIDIAN_GOALS.example.json). It is a JSON object with `version: 1` and a `suggestions` list.

- Keep `id` stable for the same piece of work. It must be a unique name of up to 80 letters, numbers, dots, dashes or underscores, starting with a letter or number.
- `title`, `reason` and a nonempty `acceptance` list are required. Use a valid `priority`: critical, high, medium or low. `steps` may be omitted.
- `revision` defaults to `"1"`. Change it when new evidence materially changes the work or a previously completed check must be repeated. Changing a reason's wording alone does not undo a dismissal.
- `state` defaults to `"open"`. Use `"done"` after testing the acceptance conditions, or remove the item. This stops proposing the item; it does not silently mark a local goal verified.
- Limit the file to 64 KB and 50 items. Titles may have 240 characters and reasons 1,600. Steps and acceptance each allow up to eight strings of 800 characters.

Meridian pins this file to the observed commit and caches successful/missing/invalid documents until the head changes. Temporary connection failures retry at the next normal refresh. A missing file is normal; malformed files show a correction notice and cannot make previous evidence appear resolved.

## Ranking and completion

Observed health failures have critical priority when an HTTP failure was received. Other endpoint failures and current-commit failed workflows are high priority. Network problems are labelled as investigations, not proof of an outage. Certificate renewal gets high priority within seven days and medium within 21 days. Issue labels and explicit follow-up/roadmap priorities can raise or lower planned work. Within a priority, direct failures rank ahead of ordinary planning. The numbers on the cards are order, not invented confidence percentages.

GitHub evidence must be checked within three hours, endpoint evidence within 45 minutes, and scheduled health runs within 24 hours. A regression-review hint uses relevant commit messages from the past seven days and explicitly requires inspecting the actual diff. It does not scan arbitrary source code or claim that a commit's description is verified.

Suggestions are proposals. **Add to goals** attaches the plan and a matching verification rule where appropriate. Existing goals are reused, and reopening completed work is explicit. **Dismiss** persists for the current incident or revision; **Snooze 24h** is temporary. A fresh incident after recovery, another push, or a new explicit follow-up revision can warrant a new review. If a source becomes unavailable, old suggestions remain visible as needing refresh. A signal disappearing from a limited issue feed is not proof that the underlying task was completed.

Everything is evaluated locally during existing refreshes. Automatic goal creation, paid AI calls and independent background code audits are not enabled.
