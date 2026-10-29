# Meridian — project status (2026-10-29)

## Goal
A local-first Windows/Fedora development control center for Latitude, Longitude and Sundial, with credible uptime signals, a 48-hour probe timeline, downloads/visitor analytics, manageable goals and copyable ChatGPT/Claude repair prompts.

## Verified locally
- Meridian Python backend: 23 automated tests passing.
- JavaScript dashboard syntax check passes.
- HTTP smoke test: 3 project records, functional dashboard endpoint, ability to create a note and retrieve it.
- A Windows x64 PE installer was cross-compiled on Linux, with a bundled application payload.
- Real-world Windows installer execution has **not yet been verified**.

## GitHub publication — INCOMPLETE
The repository has the Python backend, initial static/index.html and a draft installer workflow. Missing source: static/app.js, static/styles.css, assets, Go installer/launcher sources, and unit tests. **Do not publish a release from an incomplete checkout.** The complete updated source is in the local source archive delivered in ChatGPT.

## Update channel — NOT YET LIVE
This repository is private. An unauthenticated installer cannot fetch its private GitHub release metadata. Either keep the repository private and configure an authenticated release read mechanism, or explicitly approve a public release channel. Do not bundle a long-lived GitHub token in the installer.

## Next milestone
1. Transfer the remaining source files to this repository and verify their checksums.
2. Build and install the compiled installer on a Windows GitHub Actions runner; prove launch and persistent notes.
3. Publish a versioned GitHub Release containing the actual Windows installer.
4. Implement an accessible update feed, then test an update notification end-to-end.
5. Follow with Fedora packaging and native installation tests.

Status labels in the UI must identify *what was checked*: a successful HTTP probe is not proof that local desktop instances are running. Unobserved hours in the 48-hour timeline must remain unknown, not green.
