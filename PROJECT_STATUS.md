# Meridian — 0.2.15

This release addresses intermittent blank native startup with a painted loading page, interface readiness acknowledgement, one timed navigation retry and bounded browser recovery. Goals now provide detailed repair prompts and fresh, explicit verification. It retains the 0.2.14 installer, sign-in and dashboard improvements.

## Behavior

- The native window waits for a rendered interface, retries blank navigation after eight seconds and opens browser recovery after twenty-five seconds if necessary. Recovery stops on success or close; it adds no idle worker.
- Every goal has a reviewable repair prompt with collected context, an investigation plan and acceptance checks. Evidence details show timestamps, source links and the checked commit when relevant.
- Refresh & check verifies all goals; project and individual checks are available. Selected endpoint/current-commit workflow checks can complete goals automatically. Failed rechecks reopen automatically completed goals; missing evidence stays unknown and manual completions remain explicit.
- Real-device testing and private backup restores show detailed hands-on checklists. No unrelated green CI run can silently verify these goals. Rules and latest results persist locally without an AI service or new runtime dependency.

- Setup stages application files, closes the installed native window/backend, and restores old files if replacement fails. It preserves user data and email configuration.
- Shortcuts and the native window share the asterisk icon and taskbar identity. Duplicate launch focuses the open window.
- Email rejections explain the cause; verified cooldown clicks do not become password failures. The local sign-in form can safely replace a failed Resend key.
- Balanced, quiet and paused monitoring; hidden UI polling stops, unchanged snapshots avoid rendering, and retained monitoring data is bounded.
- Filtered, measured download growth; traffic imports; build outcomes; endpoint latency and reliability; completed goals.

## Verification scope

Python regression tests, JavaScript calculation tests, and real browser tests cover setup, sign-in, navigation, smaller windows, data changes, monitoring preferences and hidden-page behavior. Goal tests cover fresh versus stale evidence, current-commit matching, automatic completion/regression reopening, legacy database migration, rule edits, restore safety, duplicate refreshes, prompt preview/copy and saved results. Windows CI checks five successive launches inside the installed WebView2 and recovery from an intentionally blank initial document, including sign-in and dashboard navigation afterward. It also covers installer rollback, native-window upgrades, icon/shortcut identity and data preservation. Release packages publish only after the platform's required jobs pass.

Live delivery to the owner's inbox and the Windows shell cache on the owner's PC remain device-specific checks. No owner credentials are available to automated tests; mail is mocked there. Website analytics remain explicitly imported, and server backup status is not claimed to be connected.
