# Meridian — release status

Meridian is a personal local-first development control center for Latitude, Longitude and Sundial. It tracks credible green/yellow/red component checks, 48-hour monitoring samples, Github release download counts, imported website visitors, manageable goals and copyable AI troubleshooting prompts.

## Verification
- Python backend unit tests: 23 passed locally.
- JavaScript frontend syntax: passed locally.
- Native Windows executable: compiled locally for x86-64.
- Windows GitHub Actions workflow: installs the built installer on a Windows runner and checks the dashboard, three configured projects and note persistence before publishing.
- The latest passing build artifacts and public release are at https://github.com/zphat/Meridian/releases.

## Automatic updates
The GitHub repository is **public**, and Meridian checks `https://api.github.com/repos/zphat/Meridian/releases/latest` automatically. Update notifications appear when a newer supported release is published. Installers are user-approved: Meridian does not silently run downloaded executables.

## Privacy
- Project notes, SQLite databases, tokens and customer data must **never** be committed to this repository.
- The source uses optional tokens from local environment variables; no token is bundled.
- Remote access should be via an authenticated private network (such as Tailscale Serve), not an unauthenticated public website.

## Next work
- Verify a Windows install on the user's actual PC.
- Continue collecting real data for 48-hour availability and GitHub download charts.
- Add a matching release workflow and install test for Fedora Linux.
- Connect privacy-respecting website-visitor analytics with user-granted credentials.

Traffic analytics cannot appear retroactively unless they were already collected. A successful website probe is not proof that local desktop application instances are running.
