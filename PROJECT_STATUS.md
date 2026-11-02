# Meridian — 0.2.16

This release reduces GitHub allowance exhaustion and separates daily goal completions from permanent history. Existing native startup recovery, detailed goal prompts, analytics and local data remain supported.

## Behavior

- All GitHub API reads share a serialized request queue, persistent response cache and retry state. Anonymous background polling is slower; explicit build/uptime verification still revalidates the proof. Permission failures, rejected credentials and rate limits remain distinguishable.
- Settings provides optional, validated GitHub token setup. Tokens remain in a local credentials file, never in state responses or workspace exports. Only an authenticated local session can change credentials; failed replacement keeps the existing setting.
- One rate-limit notice gives a local retry time and links to settings. Site probes and local planning remain usable while GitHub is paused.
- Completed today follows the computer's calendar day. Previous completions move into history without deleting goals or evidence. Local midnight, daylight-saving transitions, unchanged-state responses, reopening and repeated verification are covered.
- New-goal generation remains a future choice: ranked evidence-based suggestions, capped automatic additions, or optional AI prioritization. This release does not silently create extra goals or call an AI service.

## Verification scope

Offline backend regressions, date/analytics calculation checks and browser workflows cover cache persistence, conditional requests, shared backoff, token validation and confidentiality, local-only credential changes, midnight rollover, completion history and reopening. Existing Windows tests cover five installed native launches, forced blank-page recovery, sign-in, upgrade preservation and rollback. Linux installers are built and installed separately.

Live GitHub quotas depend on the owner's network/account. Automated token tests use fake credentials and mock responses. Device-only recording checks and private server backups still require their specific evidence.
