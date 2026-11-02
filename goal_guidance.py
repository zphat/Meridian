"""Small, offline goal plans and conservative verification of collected evidence."""
import datetime as dt
import json

UPTIME_GOAL = 'Diagnose repeated sync-server uptime-check failures'

# These plans are guidance, not claims that the repository still has a problem.
PLANS = {
 'Verify macOS recording, permissions and export on real hardware': (
  ['Inspect the macOS capture, permission and export paths and the packaged app entitlements.',
   'On a real Mac, test first-run screen/microphone permission approval, denial, and later recovery in System Settings.',
   'Record a short screen + desktop-audio + microphone session; stop, reopen it, and export with separate audio tracks. Repeat a second recording without restarting.',
   'Check exported playback, duration, audio/video sync and each isolated track; record the Mac model, macOS version and exact app build.'],
  ['The installed app completes recording → stop → reopen → export on real hardware.', 'Permission denial gives a usable recovery path; exported media plays with the expected independent tracks.']),
 'Test Latitude Editor in narrow and non-maximized windows': (
  ['Find the editor panels, resize handles, timeline and minimum-window-size rules.',
   'Exercise an actual session at 1280×800, 1024×768 and 800×600, including OS display scaling; move between sizes while a clip is selected.',
   'Try panel resizing, timeline scrolling/zoom, drag-and-drop, trim, undo/redo, keyboard shortcuts and export without maximizing.',
   'Keep primary controls reachable, prevent accidental drag targets, and preserve the selection and scroll position during resizing.'],
  ['The timeline, preview and export controls remain usable at the documented minimum size.', 'A real trim/edit/export flow works in a small window; screenshots and tested sizes are recorded.']),
 'Run Windows/Linux recording-to-export regression tests': (
  ['Inspect the actual installed Windows and Linux packages and the existing recording/export tests.',
   'Record screen, microphone and desktop audio; pause/resume if supported, stop, reopen the session and export.',
   'Test separate audio tracks, microphone mute, a cancelled export, an unavailable input and a second recording in the same app session.',
   'Inspect the exported stream count, duration and audio/video sync, then play the output on both platforms.'],
  ['The installed packages complete the end-to-end workflow on both platforms.', 'Cancellation and missing devices recover without a hang or damage to recorded media.']),
 'Gather and triage beta feedback before 1.0': (
  ['Review existing issues and authorized feedback; group duplicates by the actual user-visible symptom.',
   'Record app version, OS, reproduction steps, expected behavior and severity for each reproducible report.',
   'Prioritize data loss, launch failures, recording/export failures and accessibility blockers; separate feature requests.',
   'Turn confirmed bugs into focused fixes with a regression check, and document which reports still need reproduction.'],
  ['Each release blocker has reproducible evidence and a verified outcome.', 'Unverified reports remain visibly unresolved; feedback is not dismissed merely because CI passes.']),
 'Review editor usability and test a complete real thumbnail workflow': (
  ['Trace import, layer selection, background removal, text editing, undo/history and export.',
   'Build a real cover with an imported image, background removal, two text layers and an overlay; resize and reorder layers.',
   'Test the workflow in a smaller window, undo and redo several actions, then save/reopen if supported.',
   'Export PNG and JPEG and inspect dimensions, transparency, font rendering and final composition.'],
  ['A usable thumbnail can be created and exported without hidden or unreachable controls.', 'The exported image matches the preview, and failed imports/exports retain the work.']),
 'Test Windows installer and browser editor independently': (
  ['Test a fresh Windows installation and an upgrade with a saved project; verify the installed app actually renders.',
   'Run the import → edit → export flow in the installed app, then separately in the deployed browser editor.',
   'Test an offline relaunch where supported and move a saved project between the two environments.',
   'Check file pickers, image decoding, fonts, clipboard behavior and downloads in both environments.'],
  ['Both delivery paths independently pass the complete workflow.', 'Upgrades preserve saved work, and unsupported offline behavior is clearly explained.']),
 'Build a cohesive clip-art/graphic asset library': (
  ['Inventory the existing asset system, supported vector/raster formats and import/export behavior.',
   'Define a small useful set of arrows, labels, frames, badges and geometric accents with consistent visual rules.',
   'Record source and redistribution rights for every asset; avoid adding a large runtime dependency or downloading everything at launch.',
   'Test transparent backgrounds, recoloring where supported, thumbnails, search/categories and export quality.'],
  ['Assets are discoverable, render sharply and export correctly.', 'Each asset has documented redistribution rights and the library stays lightweight.']),
 'Launch longitude.pictures when the domain is purchased': (
  ['Check current domain ownership and deployment configuration before making DNS assumptions.',
   'Prepare the existing landing page for the custom domain, including canonical links, HTTPS and browser-editor/download links.',
   'After the domain is available, verify DNS resolution, certificate coverage, redirects and the actual published page.',
   'Check all download links and the editor from a clean browser; retain the existing working URL until the new one is verified.'],
  ['The owned custom domain serves the correct site over HTTPS with working links.', 'The transition preserves access through the existing published address.']),
 UPTIME_GOAL: (
  ['Open the latest failing uptime workflow and identify the exact failed step, URL, HTTP status, timeout or certificate error.',
   'Compare that run with a fresh direct probe of the sync health endpoint. Check DNS, TLS, routing and service logs when authorized.',
   'Determine whether the service, deployment, certificate or the monitor itself is wrong; preserve authentication and health validation.',
   'Fix the cause, rerun the same scheduled health workflow, and repeat the direct endpoint check. Keep the before/after evidence.'],
  ['The sync endpoint returns its expected healthy JSON over HTTPS.', 'The latest scheduled health workflow completes successfully; a build-only workflow is insufficient.']),
 'Configure and verify off-site backup storage': (
  ['Inspect the existing backup job and restore documentation; identify what data must be backed up and how secrets are supplied.',
   'Verify the intended storage account/bucket and narrowly scoped credentials without copying secrets into prompts or the repository.',
   'Run an authorized backup, confirm that the expected encrypted objects were written, and inspect retention and failure reporting.',
   'Download a test backup to an isolated environment and check its contents and integrity before claiming readiness.'],
  ['A dated off-site backup exists and its integrity has been checked.', 'Retention and failure handling are documented; public repository checks alone cannot verify private storage.']),
 'Perform a documented backup restore test': (
  ['Read the current backup/restore procedure and identify a recent valid backup and a disposable restore destination.',
   'Restore into the isolated destination without overwriting production data; capture the exact backup identifier and app/schema versions.',
   'Start the restored application and check representative records, attachments, credentials handling and application consistency.',
   'Record elapsed restore time, missing data, warnings and cleanup steps; fix the procedure and repeat if it fails.'],
  ['The restored service starts and representative data is intact in the isolated environment.', 'A dated restore report links the backup, commands, results and recovery time.']),
 'Finish web-bundle signing and verification': (
  ['Inspect bundle creation, signing, public-key distribution and signature verification before loading/executing a bundle.',
   'Check the positive path with a valid signed bundle and negative paths for a modified bundle, wrong key, missing signature and rollback where applicable.',
   'Keep private signing keys outside the repository and distributable app; document rotation and trusted-key handling.',
   'Test the packaged release path, not only a signing helper, and retain the exact artifact hash and verification output.'],
  ['A valid release bundle loads and tampered or untrusted bundles are rejected.', 'The published artifact is covered by the verification check and contains no private signing key.']),
 'Review signing options and Windows installer warnings': (
  ['Inspect the distributed installer signature, publisher metadata and the exact Windows warning on a clean test machine.',
   'Review applicable signing options, eligibility, recurring costs and certificate/key handling; distinguish signature validity from reputation.',
   'If signing is already available, verify signature validity and timestamp on the actual downloaded release artifact.',
   'Document what was tested and any remaining SmartScreen/reputation prompt without promising that signing removes every warning.'],
  ['The actual installer signature and clean-machine installation result are documented.', 'Costs and unresolved reputation warnings are explicit; private keys are never shipped.']),
}


def guidance(goal):
    try:
        custom=json.loads(goal.get('guidance_json') or '{}')
        if all(isinstance(custom.get(k),list) and 1<=len(custom[k])<=8 and all(isinstance(v,str) and 0<len(v)<=1600 for v in custom[k]) for k in ('approach','acceptance')):
            return {k:custom[k] for k in ('approach','acceptance')}
    except (ValueError,TypeError,AttributeError):pass
    approach, acceptance = PLANS.get(goal['title'], (
        ['Inspect the current repository, related issues and the exact behavior described in this goal before changing files.',
         'Record expected versus actual behavior, the affected version/environment and a minimal reproduction.',
         'Trace the failing path, make a focused fix that preserves existing features, and add a regression check for the observed failure.',
         'Test the installed or deployed result in the environment where it failed, and document evidence for each acceptance condition.'],
        ['The reported behavior is reproduced before the fix and succeeds afterward.',
         'Relevant regression checks pass on the exact changed version; any remaining device-only checks are listed.']))
    return {'approach': list(approach), 'acceptance': list(acceptance)}


def rule_for(goal):
    kind = goal.get('verification_kind') or ('uptime' if goal['project'] == 'sundial' and goal['title'] == UPTIME_GOAL else 'manual')
    return {'kind': kind, 'target': goal.get('verification_target') or ''}


def timestamp(value):
    try:
        value = dt.datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        return value if value.tzinfo else value.replace(tzinfo=dt.timezone.utc)
    except (ValueError, TypeError):
        return None


def evaluate(goal, project, since, now):
    """Only a selected, freshly collected check may automatically complete a goal."""
    rule = rule_for(goal)
    result = {'state': 'blocked', 'checked_at': now, 'summary': '', 'evidence': [], 'rule': rule}
    evidence = result['evidence']
    cutoff = timestamp(since)
    current = timestamp(now)
    github = project.get('github') or {}
    data = github.get('data') or {}

    def fresh(value):
        stamp = timestamp(value)
        return bool(stamp and cutoff and current and cutoff <= stamp <= current + dt.timedelta(seconds=5))

    def finish(state, summary):
        result.update(state=state, summary=summary)
        return result

    def site_check(site):
        status = (site or {}).get('status') or {}
        collected = fresh(status.get('checked_at'))
        # A timeout or unavailable local connection is not proof of a regression.
        # HTTP failures and invalid health responses are observable failures.
        state = 'blocked' if not collected or status.get('status') is None else 'verified' if status.get('success') else 'failed'
        evidence.append({'label': (site or {}).get('label', 'Endpoint'), 'state': state,
                         'detail': 'No fresh probe available.' if not collected else status.get('error') or ('HTTP ' + str(status.get('status'))),
                         'url': (site or {}).get('url', ''), 'checked_at': status.get('checked_at')})
        return state

    def workflow_check(run, require_head=False):
        state = 'blocked'
        detail = 'No current completed workflow is available.'
        if run:
            detail = str(run.get('name') or 'Workflow') + ': ' + str(run.get('conclusion') or run.get('status') or 'unknown')
            if github.get('error') or not fresh(data.get('evidence_checked_at',github.get('checked_at'))):
                detail = 'GitHub could not be refreshed; stored results cannot prove this fix.'
            elif require_head and (not data.get('head_sha') or run.get('head_sha') != data['head_sha']):
                detail = 'This workflow has not checked the current default-branch commit.'
            elif not require_head and (not timestamp(run.get('created_at')) or current - timestamp(run.get('created_at')) > dt.timedelta(hours=24)):
                detail = 'The latest monitor run is over 24 hours old; rerun it before verifying.'
            elif run.get('status') == 'completed':
                if run.get('conclusion') == 'success': state = 'verified'
                elif run.get('conclusion') in ('failure', 'timed_out', 'action_required', 'startup_failure'): state = 'failed'
        evidence.append({'label': 'GitHub workflow', 'state': state, 'detail': detail,
                         'url': (run or {}).get('html_url', ''), 'checked_at': data.get('evidence_checked_at',github.get('checked_at')),
                         'commit': (run or {}).get('head_sha', '')})
        return state

    if rule['kind'] == 'manual':
        return finish('manual', 'Needs a hands-on check. Use the acceptance checklist; a green build alone cannot verify this goal.')
    if rule['kind'] == 'site':
        site = next((s for s in project.get('sites', []) if s['url'] == rule['target']), None)
        if not site: return finish('blocked', 'Choose a monitored endpoint in Edit goal before checking.')
        state = site_check(site)
        return finish(state, {'verified': 'Selected endpoint is responding correctly now. This confirms the current probe, not continuous uptime.',
                              'failed': 'Selected endpoint still fails its check.', 'blocked': 'Could not confirm endpoint health; inspect the connection evidence below.'}[state])
    if rule['kind'] == 'build':
        run = next((r for r in data.get('workflows', []) if str(r.get('workflow_id')) == rule['target']), None)
        state = workflow_check(run, require_head=True)
        return finish(state, {'verified': 'Selected workflow passed for the current default-branch commit.',
                              'failed': 'Selected workflow still fails on the current commit.', 'blocked': 'Current-commit verification is unavailable; inspect the evidence below.'}[state])
    if rule['kind'] == 'uptime':
        site = next((s for s in project.get('sites', []) if s.get('type') == 'health'), None)
        states = [site_check(site), workflow_check(data.get('uptime_workflow'))]
        state = 'failed' if 'failed' in states else 'blocked' if 'blocked' in states else 'verified'
        return finish(state, {'verified': 'Sync health and the latest scheduled monitor both pass. Current health is verified.',
                              'failed': 'The sync endpoint or scheduled monitor still fails.', 'blocked': 'Both a fresh health probe and a recent successful monitor run are required.'}[state])
    return finish('blocked', 'Choose a supported verification method in Edit goal.')
