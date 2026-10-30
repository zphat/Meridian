# Meridian 0.2.9

Local-first personal control center for Latitude, Longitude, and Sundial.

## What is new

- Labeled green, amber, red monitoring lights with stale checks shown as unverified
- Actual 48-hour hourly availability samples, not invented uptime
- Per-project installer download totals and imported visitor counts
- Smaller actionable goal lists and collapsible completed tasks
- Copyable ChatGPT/Claude troubleshooting prompts using available monitoring evidence

## Windows

Run `Meridian-Setup-0.2.9.exe` (compiled, x64). It installs to your user profile with Start Menu and desktop links, and fetches a pinned, verified Python embeddable runtime during first installation. Requires internet at first install. It is not code signed.

## GitHub updates

The updater checks `zphat/Meridian` on startup and periodically. This repository is public. Meridian checks its public GitHub Releases feed at launch and periodically, shows a notification when a newer version is available, and lets you choose whether to install it. A published release containing the Windows installer is required before the channel can report an available update. No GitHub token is embedded in the installer.

## Local project data

Notes, goals, decisions, samples, downloads and snapshots are stored in the local user's `.meridian/meridian.sqlite3` and aren't shipped with builds or uploaded to GitHub. Back up data from Settings.

## Development

`python meridian.py --offline` to run without network; `python -m unittest discover -s tests` for backend tests. The local service defaults to loopback and may optionally be exposed via a carefully configured Tailscale Serve proxy.



## Private owner sign-in (v0.2.9)

Meridian now protects the entire dashboard and private API behind an authorized email and password followed by a one-time email magic link. On first local launch, register a free [Resend](https://resend.com/signup) account using the authorized inbox. Create a **Sending access** key in [Resend API Keys](https://resend.com/api-keys). Enter that key, your email, and chosen password in Meridian's local-only setup screen. The first magic link is sent immediately; if the provider rejects the key or recipient, setup rolls back without deleting project notes.

The authorized email, password and API key **must not** be committed to GitHub. They are never built into the public installers. The password is kept as a salted scrypt verifier, the Resend key is stored in the owner's local user-data directory, and magic-link/session tokens are short-lived. Links last 10 minutes and work once. Sign-in is limited to three emails per 24 hours, with a five-minute cooldown. An authenticated session lasts 12 hours. Use Tailscale rather than exposing the local service directly to the public Internet.

For the Resend test sender `onboarding@resend.dev`, mail is limited to the address associated with the Resend account unless a sending domain is verified. Open emailed `localhost` links on the Windows PC running Meridian; to log in from another device, open Meridian through your trusted Tailscale hostname and request a link there.

If provider credentials change and you cannot log in, exit Meridian and remove only `%USERPROFILE%\\.meridian\\auth.json` from your local computer. Your SQLite project notes remain intact. The Windows installer upgrade retains local data.

## Windows first-run fix (v0.2.9)

The installer stops an older background Meridian process before upgrading, then opens the new application automatically. Before configuration, the home screen presents a one-time setup form for the authorized email address, an access password, and a Resend Sending access key. Project notes and other local data survive upgrades. Existing authentication settings remain in place and will show the normal sign-in form rather than setup.

If you already installed v0.2.8 but see the old dashboard, quit old Meridian processes and install v0.2.9. The launcher now refuses to silently open an outdated background version.
