# Meridian 0.2.7

Local-first personal control center for Latitude, Longitude, and Sundial.

## What is new

- Labeled green, amber, red monitoring lights with stale checks shown as unverified
- Actual 48-hour hourly availability samples, not invented uptime
- Per-project installer download totals and imported visitor counts
- Smaller actionable goal lists and collapsible completed tasks
- Copyable ChatGPT/Claude troubleshooting prompts using available monitoring evidence

## Windows

Run `Meridian-Setup-0.2.7.exe` (compiled, x64). It installs to your user profile with Start Menu and desktop links, and fetches a pinned, verified Python embeddable runtime during first installation. Requires internet at first install. It is not code signed.

## GitHub updates

The updater checks `zphat/Meridian` on startup and periodically. This repository is public. Meridian checks its public GitHub Releases feed at launch and periodically, shows a notification when a newer version is available, and lets you choose whether to install it. A published release containing the Windows installer is required before the channel can report an available update. No GitHub token is embedded in the installer.

## Local project data

Notes, goals, decisions, samples, downloads and snapshots are stored in the local user's `.meridian/meridian.sqlite3` and aren't shipped with builds or uploaded to GitHub. Back up data from Settings.

## Development

`python meridian.py --offline` to run without network; `python -m unittest discover -s tests` for backend tests. The local service defaults to loopback and may optionally be exposed via a carefully configured Tailscale Serve proxy.

