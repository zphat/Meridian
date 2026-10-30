# Meridian — 0.2.14

This release repairs native Windows upgrades and email-code sign-in recovery, then refines the always-open dashboard.

## Behavior

- Setup stages application files, closes the installed native window/backend, and restores old files if replacement fails. It preserves user data and email configuration.
- Shortcuts and the native window share the asterisk icon and taskbar identity. Duplicate launch focuses the open window.
- Email rejections explain the cause; verified cooldown clicks do not become password failures. The local sign-in form can safely replace a failed Resend key.
- Balanced, quiet and paused monitoring; hidden UI polling stops, unchanged snapshots avoid rendering, and retained monitoring data is bounded.
- Filtered, measured download growth; traffic imports; build outcomes; endpoint latency and reliability; completed goals.

## Verification scope

Python regression tests, JavaScript calculation tests, and real browser tests cover setup, sign-in, navigation, smaller windows, data changes, monitoring preferences and hidden-page behavior. Windows CI covers installer rollback, real native-window upgrades, icon/shortcut identity, data preservation and reopening. Release packages publish only after the platform's required jobs pass.

Live delivery to the owner's inbox and the Windows shell cache on the owner's PC remain device-specific checks. No owner credentials are available to automated tests; mail is mocked there. Website analytics remain explicitly imported, and server backup status is not claimed to be connected.
