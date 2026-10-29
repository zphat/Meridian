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

The updater checks `zphat/Meridian` on startup and periodically. This repository is currently **private**. GitHub's public release endpoint cannot expose private assets to an unauthenticated installed app; update checks are not fully operational until a dedicated authenticated or public release feed is provided. Do not store a GitHub token inside distributed installation assets. The update checker shows a private/unpublished notice rather than claiming up-to-date.

## Local project data

Notes, goals, decisions, samples, downloads and snapshots are stored in the local user's `.meridian/meridian.sqlite3` and aren't shipped with builds or uploaded to GitHub. Back up data from Settings.

## Development

`python meridian.py --offline` to run without network; `python -m unittest discover -s tests` for backend tests. The local service defaults to loopback and may optionally be exposed via a carefully configured Tailscale Serve proxy.

> Repository sync incomplete: frontend, packaging and test files are provided in the downloadable source archive but are not all committed. No build release is published yet.
