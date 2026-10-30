# Meridian 0.2.14

A local development dashboard for Latitude, Longitude and Sundial. Your goals, notes, decisions and email credentials stay on your computer.

## Install or upgrade

Download the Windows installer or Linux package from [GitHub Releases](https://github.com/zphat/Meridian/releases/latest). Windows installs per user and downloads a pinned, SHA-256-verified Python runtime on the first installation. The Windows installer is not code signed.

Version 0.2.14 fixes the `Meridian.exe: Access is denied` upgrade failure. Setup prepares the new files, closes only this installation's native window and backend, waits for them to exit, and replaces the application. If replacement fails, the previous application files are restored. Notes, authentication settings and the database are outside the installation directory and are preserved. Running setup again repairs a partially completed earlier installation.

The native WebView2 window, Start Menu link and desktop shortcut share the lime asterisk icon and `Meridian.Desktop` identity. A second launch focuses the existing window. External HTTPS links open in your default browser. Windows may keep a separately pinned old Edge shortcut; remove that obsolete pin and pin the new Meridian window if needed.

## Private access

On first launch, enter your authorized email, choose a password and supply a Resend Sending access API key. With the default `onboarding@resend.dev` sender, the recipient must be the email registered to the Resend account. Nothing is bundled with your private credentials.

Enter the emailed eight-digit code in the same Meridian window. Codes expire after ten minutes, work once and allow five wrong-code attempts. A pending request survives a page reload in that window. Optional email links remain compatible with previous releases, but the code avoids mail-provider link redirects. Sessions expire after twelve hours; use **Lock** to end one sooner.

Email requests allow one per minute and six per rolling 24 hours. The UI shows the actual remaining cooldown. Wrong passwords have a separate limit; cooldown clicks and delivery errors do not consume it. Resend acceptance is not proof of inbox delivery: check spam and the Resend email log if needed. Provider rejections explain whether the problem concerns the key, recipient, sender, quota or connection. An email reference is shown when the provider accepts the request.

To repair a key, open **Fix email delivery** on the local sign-in screen. Your authorized email and password are still required. A replacement key is saved only after Resend accepts the email; it cannot change the authorized inbox or bypass email verification. Upgrades retain an already configured key. Never commit `auth.json`, `.env` files, backups or SQLite data to GitHub.

## Lightweight monitoring

Settings offers three modes:

| Mode | Endpoint probes | GitHub refresh |
| --- | --- | --- |
| Balanced | Every 5 minutes | Every 30 minutes |
| Quiet | Every 15 minutes | Every hour |
| Paused | Manual only | Manual only |

The UI stops polling while hidden and checks every thirty seconds when visible, briefly faster during a refresh. Unchanged state returns no dashboard payload and does not rebuild the page. The backend sleeps until the next scheduled job. GitHub uses conditional requests and respects API rate-limit resets. Certificate-expiry checks are reused for six hours. Release checks continue every six hours in every mode.

Endpoint samples retain fourteen days; download snapshots retain ninety days; imported events are bounded. Personal notes and goals are not pruned. Settings shows local database size and service uptime. These policies limit background work and storage growth; total memory also includes the system WebView2 runtime.

## Useful, measured analytics

- Project and 7/30-day filters for observed download increases and imported visitor/pageview data.
- Download growth compares the same release asset across snapshots; new baselines and counter resets are excluded. Missing samples stay unknown. Increases spanning a gap are identified as observations, not exact daily totals.
- Recent default-branch build pass rates, with cancelled/skipped jobs excluded.
- Last-24-hour successful probe counts, average/slowest successful response time, and latest certificate-expiry readings.
- Goals marked completed during the selected period, latest releases, open priorities and an activity timeline.
- A 48-hour availability strip with missing hours shown as unmeasured.

Downloads are requests, not installations or users. Probe reliability is sampled while the app runs, not a continuous uptime guarantee. Traffic requires a CSV import with `date,visitors,pageviews`; daily visitor counts cannot establish unique people across a longer period.

## Development and verification

Production Python uses the standard library. The frontend is plain JavaScript/CSS with no external scripts, fonts or chart runtime.

```
python meridian.py --offline
python -m unittest discover -s tests -v
node tests/metrics.test.cjs
```

Browser tests use disposable data and mock email delivery. Install test-only Playwright with `npm install --no-save playwright@1.58.2`, run `npx playwright install chromium`, then `node tests/browser_smoke.cjs`.

The Windows workflow builds and installs the app on Windows, tests file-lock rollback, shortcut and native icon identity, upgrades while the real native window is open, verifies notes/key preservation, leaves unrelated Python processes running, reopens the app and checks duplicate launch behavior. Linux packages are built and checked separately. Live Resend delivery with the owner's locally stored key requires verification on the owner's computer.

For remote use, place Meridian behind a properly configured private Tailscale connection. It binds to loopback by default; a trusted-host allowlist is not a substitute for authentication. Back up planning data from Settings.
