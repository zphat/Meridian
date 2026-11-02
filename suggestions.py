"""Evidence-based next steps. Standard library only; never calls an AI service."""
import datetime as dt
import hashlib
import json
import re

PRIORITIES = {'critical': 100, 'high': 75, 'medium': 45, 'low': 20}
FAILURES = {'failure', 'timed_out', 'action_required', 'startup_failure'}


def instant(value):
    try:
        parsed = dt.datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=dt.timezone.utc)
    except (ValueError, TypeError):
        return None


def fresh(value, now, seconds):
    parsed = instant(value)
    return bool(parsed and -300 <= (now - parsed).total_seconds() <= seconds)


def normalized(value):
    value = re.sub(r'^\s*\[(critical|high|medium|low|p[0-3])\]\s*', '', str(value), flags=re.I)
    return re.sub(r'[^\w]+', ' ', value.lower()).strip()


def digest(value):
    return hashlib.sha256(str(value).encode()).hexdigest()[:24]


def source(label, url, when, detail=''):
    return dict(label=label, url=url or '', checked_at=when, detail=str(detail)[:800])


def parse_followups(body):
    """Repository text is data, never instructions to execute or remote URLs to fetch."""
    data = json.loads(body)
    if not isinstance(data, dict) or data.get('version') != 1 or not isinstance(data.get('suggestions'), list):
        raise ValueError('Expected version 1 and a suggestions list')
    if len(data['suggestions']) > 50:
        raise ValueError('At most 50 follow-ups are supported')
    items, ids = [], set()
    for item in data['suggestions']:
        if not isinstance(item, dict):
            raise ValueError('Each follow-up must be an object')
        key = item.get('id')
        if not isinstance(key, str) or not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9._-]{0,79}', key) or key in ids:
            raise ValueError('Follow-up IDs must be unique, stable names')
        ids.add(key)
        if item.get('state', 'open') not in ('open', 'done'):
            raise ValueError('Follow-up state must be open or done')
        if item.get('state') == 'done':
            continue
        clean = {'id': key, 'revision': str(item.get('revision', '1'))[:80]}
        for name, limit in (('title', 240), ('reason', 1600)):
            value = item.get(name)
            if not isinstance(value, str) or not value.strip() or len(value) > limit:
                raise ValueError('Follow-ups need a short title and a reason')
            clean[name] = value.strip()
        priority = item.get('priority', 'medium')
        if not isinstance(priority, str) or priority not in PRIORITIES:
            raise ValueError('Unknown follow-up priority')
        clean['priority'] = priority
        for name in ('steps', 'acceptance'):
            values = item.get(name, [])
            if not isinstance(values, list) or len(values) > 8 or any(not isinstance(x, str) or not x.strip() or len(x) > 800 for x in values):
                raise ValueError('Steps and acceptance must be lists of up to eight short strings')
            clean[name] = [v.strip() for v in values]
        if not clean['acceptance']:
            raise ValueError('Each follow-up needs at least one acceptance check')
        items.append(clean)
    return items


def priority_label(labels, default='medium'):
    values = {re.sub(r'^(priority|severity)[\s:/-]*', '', str(x).strip().lower()) for x in labels}
    for priority, aliases in [('critical', {'critical', 'p0', 'blocker'}), ('high', {'high', 'p1', 'urgent', 'security'}), ('medium', {'medium', 'p2', 'bug'}), ('low', {'low', 'p3', 'enhancement', 'nice to have'})]:
        if values & aliases:
            return priority
    return default


def collect(project, now):
    """Return candidates and the scopes for which absence is supported by fresh data."""
    pid, name = project['id'], project['name']
    candidates, known = [], set()
    repo_url = 'https://github.com/' + project['repository']

    def add(key, scope, kind, title, priority, reason, evidence, approach, acceptance,
            verification_kind='manual', verification_target='', fingerprint='1', bonus=0):
        candidates.append(dict(key=pid + ':' + key, project=pid, scope=scope, kind=kind,
            title=title[:300], priority=priority, score=PRIORITIES[priority] + bonus,
            reason=reason[:2000], sources=evidence, guidance=dict(approach=approach, acceptance=acceptance),
            verification_kind=verification_kind, verification_target=verification_target,
            fingerprint=str(fingerprint), observed_at=max((x['checked_at'] or '' for x in evidence), default='')))

    for site in project.get('sites', []):
        status = site.get('status') or {}
        scope = 'site:' + site['url']
        if not fresh(status.get('checked_at'), now, 45 * 60):
            continue
        known.add(scope)
        evidence = [source(site['label'], site['url'], status['checked_at'],
                           'HTTP ' + str(status.get('status') or 'unknown') + (' · ' + status['error'] if status.get('error') else ''))]
        if not status.get('success'):
            critical = site['type'] == 'health' and status.get('status') is not None
            priority = 'critical' if critical else 'high'
            uptime = site['type'] == 'health' and bool(project.get('uptime_workflow_path'))
            add('endpoint:' + digest(site['url']), scope, 'failure', 'Investigate ' + name + ' ' + site['label'].lower() + ' check failure', priority,
                'The latest direct probe failed. Confirm whether the service or this computer’s connection is responsible before changing anything.', evidence,
                ['Repeat the request to ' + site['url'] + ' and record the status, response, and timestamp.',
                 'Compare with the deployed service and, if needed, another connection. Inspect DNS, TLS, routing and service logs to isolate the cause.',
                 'Fix the confirmed cause and rerun the same check without weakening authentication or the health contract.'],
                ['The exact monitored endpoint returns its expected successful response.', 'The direct health probe and latest scheduled monitor both pass.' if uptime else 'A fresh Meridian check passes after the deployed fix.'],
                verification_kind='uptime' if uptime else 'site', verification_target='' if uptime else site['url'], bonus=8)
        elif isinstance(status.get('tls_days'), int) and status['tls_days'] <= 21:
            days = status['tls_days']
            add('certificate:' + digest(site['url']), scope, 'maintenance', 'Check certificate renewal for ' + site['label'], 'high' if days <= 7 else 'medium',
                'The observed TLS certificate has ' + str(days) + ' days remaining. Confirm renewal before it interrupts access.', evidence,
                ['Inspect the certificate currently served by ' + site['url'] + ' and the configured renewal job.', 'Confirm automatic renewal, deploy the renewed certificate if necessary, and inspect the certificate served to a new client.'],
                ['A fresh connection serves the renewed, valid certificate with more than 21 days remaining.', 'Renewal configuration and any remaining provider steps are documented.'])

    github = project.get('github') or {}
    data = github.get('data') or {}
    checked = data.get('evidence_checked_at') or github.get('checked_at')
    if github.get('error') or not fresh(checked, now, 3 * 3600):
        return candidates, known

    head = data.get('head_sha')
    if head:
        known.add('builds')
        for run in data.get('workflows', []):
            wid = str(run.get('workflow_id') or '')
            if not re.fullmatch(r'[0-9]{1,16}', wid) or run.get('head_sha') != head or run.get('status') != 'completed' or run.get('conclusion') not in FAILURES:
                continue
            add('build:' + wid, 'builds', 'failure', 'Repair ' + str(run.get('name') or 'workflow') + ' on the current commit', 'high',
                'This default-branch workflow failed on ' + head[:12] + '. A failure on an older commit is not used to create this suggestion.',
                [source(run.get('name') or 'Workflow', run.get('html_url'), checked, str(run.get('conclusion')) + ' · commit ' + head[:12])],
                ['Open the linked run and identify the first failing step and its actual error.', 'Reproduce on commit ' + head + ', fix the cause, and add a regression check for the failing behavior.', 'Rerun this workflow on the current default-branch commit and test the installed or deployed result affected by the fix.'],
                ['The selected workflow completes successfully on the current default-branch commit.', 'The original failing behavior passes its regression check.'],
                verification_kind='build', verification_target=wid, fingerprint=head, bonus=12)

    monitor = data.get('uptime_workflow') or {}
    if project.get('uptime_workflow_path') and fresh(monitor.get('created_at'), now, 86400):
        known.add('monitor')
        if monitor.get('status') == 'completed' and monitor.get('conclusion') in FAILURES:
            add('monitor', 'monitor', 'failure', 'Investigate the ' + name + ' scheduled health failure', 'critical',
                'The latest scheduled health monitor failed. Compare it with a direct health probe; a green release build does not resolve an uptime failure.',
                [source('Scheduled health monitor', monitor.get('html_url'), checked, monitor.get('conclusion'))],
                ['Read the failing health job’s step, URL, response and timestamp.', 'Compare with the live sync health endpoint and investigate the service, TLS, routing or monitor configuration.', 'Repair the confirmed cause, rerun the scheduled health job, and repeat the direct health probe.'],
                ['The direct health probe passes its expected JSON contract.', 'The latest scheduled health monitor succeeds within the past 24 hours.'], verification_kind='uptime', bonus=5)

    known.add('issues')
    for issue in data.get('issues', []):
        if issue.get('pull_request') or type(issue.get('number')) is not int:
            continue
        labels = issue.get('labels') or []
        priority = priority_label(labels)
        title = str(issue.get('title') or 'Untitled issue')
        add('issue:' + str(issue['number']), 'issues', 'reported', title, priority,
            'Open GitHub issue #' + str(issue['number']) + ('. Priority follows its labels: ' + ', '.join(labels) if labels else '. Medium priority until triaged; the report has not been independently verified.'),
            [source('Issue #' + str(issue['number']), issue.get('url'), data.get('issues_checked_at') or checked, (issue.get('body') or '')[:800])],
            ['Read the linked issue and reproduce its expected versus actual behavior on the current version.', 'Inspect the affected implementation and make a focused change only if the issue still applies.', 'Test the reported scenario and nearby regressions, then record the result and any remaining device checks.'],
            ['The issue’s acceptance conditions are tested on the current version.', 'The outcome is documented with reproduction details and test evidence.'])

    roadmap = data.get('roadmap') or {}
    if roadmap.get('status') in ('ok', 'missing') or (not roadmap.get('status') and 'open_items' in roadmap):
        known.add('roadmap')
        for raw in roadmap.get('open_items', [])[:50]:
            match = re.match(r'^\[(critical|high|medium|low|p[0-3])\]\s*(.+)$', raw, re.I)
            priority = priority_label([match[1]]) if match else 'medium'
            title = match[2] if match else raw
            add('roadmap:' + digest(normalized(title)), 'roadmap', 'planned', title, priority,
                'An unchecked item in ' + str(roadmap.get('file') or 'the project roadmap') + '. Confirm that it is still needed; unchecked documentation is not proof of a bug.',
                [source(roadmap.get('file') or 'Project roadmap', roadmap.get('url'), roadmap.get('checked_at') or checked, raw)],
                ['Read this item in context and compare it with the current implementation and existing goals.', 'Define a small, testable outcome and complete the missing work without expanding unrelated scope.', 'Test the result and update the source checkbox with the actual outcome.'],
                ['The documented outcome works in the intended environment.', 'The roadmap records verified progress and any remaining manual checks.'])

    followups = data.get('followups') or {}
    if followups.get('status') in ('ok', 'missing'):
        known.add('followups')
        for item in followups.get('items', []):
            add('followup:' + item['id'], 'followups', 'followup', item['title'], item['priority'], item['reason'],
                [source('Update follow-up · MERIDIAN_GOALS.json', followups.get('url'), followups.get('checked_at') or checked, 'Repository-authored follow-up; verify before marking complete.')],
                item['steps'] or ['Inspect the referenced change and current implementation.', 'Complete the stated acceptance checks and record evidence in the project status.'],
                item['acceptance'], fingerprint=item['revision'])

    known.add('update')
    commits = data.get('commits') or []
    latest = next((c for c in commits if c.get('sha') == head), None)
    if latest and fresh(latest.get('date'), now, 7 * 86400):
        # One review per project, not a new task for every commit. Only use recent
        # messages as hints; they cannot prove a shipped feature or an observed bug.
        recent = [c for c in commits if fresh(c.get('date'), now, 7 * 86400)][:8]
        messages = ' '.join(str(c.get('message') or '') for c in recent)
        checks = []
        for pattern, check in [
            (r'\b(record|recording|audio|capture|microphone|mic)\b', 'Record a short session, replay it, and inspect each expected audio track.'),
            (r'\b(editor|timeline|resize|layout|panel|rename|ui)\b', 'Exercise the changed controls in a small window, including keyboard access, resizing and undo where applicable.'),
            (r'\b(export|render|encoding|finaliz\w*)\b', 'Export a real project and inspect playback, dimensions, timing and retained source data.'),
            (r'\b(auth|login|sign.in|session|token|password)\b', 'Test sign-in, rejected or expired credentials, recovery and sign-out without exposing secrets.'),
            (r'\b(sync|backup|restore|database|migration)\b', 'Verify data survives the changed sync or storage path; use an isolated restore destination where needed.'),
            (r'\b(install\w*|launch\w*|startup|update|release)\b', 'Test a clean launch and an upgrade with saved work using the published installer, if one exists.')]:
            if re.search(pattern, messages, re.I):
                checks.append(check)
        if checks:
            add('update-review', 'update', 'review', 'Review ' + name + ' after the latest push', 'medium',
                'Recent commit messages point to changes worth testing. This is a regression review, not a detected failure. Current head: ' + head[:12] + '.',
                [source('Latest push · ' + head[:12], latest.get('url') or repo_url, checked, latest.get('message') or '')],
                ['Inspect the actual diff on ' + head + ' and confirm which changes reached the build you are testing.'] + checks[:4],
                ['The affected workflows pass the focused checks above on the identified version or commit.', 'Record the tested build, results and any hardware-only checks still outstanding.'], fingerprint=head, bonus=-5)
    return candidates, known


class SuggestionStore:
    def __init__(self, conn, lock):
        self.conn, self.lock = conn, lock
        with lock, conn:
            conn.execute('''CREATE TABLE IF NOT EXISTS suggestions (
                key TEXT PRIMARY KEY, project TEXT NOT NULL, scope TEXT NOT NULL,
                fingerprint TEXT NOT NULL, generation INTEGER NOT NULL DEFAULT 1,
                json TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 1,
                decision TEXT NOT NULL DEFAULT 'pending', snoozed_until TEXT,
                first_seen TEXT NOT NULL, last_seen TEXT NOT NULL)''')
            conn.execute('''CREATE TABLE IF NOT EXISTS suggestion_preferences (
                key TEXT PRIMARY KEY, fingerprint TEXT NOT NULL, generation INTEGER NOT NULL,
                decision TEXT NOT NULL, snoozed_until TEXT)''')

    def refresh(self, projects, now):
        stamp = now.isoformat(timespec='seconds')
        with self.lock, self.conn:
            for project in projects:
                candidates, known = collect(project, now)
                seen = {c['key'] for c in candidates}
                old = {r['key']: dict(r) for r in self.conn.execute('SELECT * FROM suggestions WHERE project=?', (project['id'],))}
                for candidate in candidates:
                    row = old.get(candidate['key'])
                    returned_incident = bool(row and not row['active'] and candidate['kind'] in ('failure', 'maintenance'))
                    changed = bool(row and (returned_incident or row['fingerprint'] != candidate['fingerprint']))
                    generation = row['generation'] + int(changed) if row else 1
                    decision = 'pending' if changed or not row else row['decision']
                    first = stamp if changed or not row else row['first_seen']
                    until = None if changed or not row else row['snoozed_until']
                    restored = self.conn.execute('SELECT * FROM suggestion_preferences WHERE key=?', (candidate['key'],)).fetchone()
                    if restored:
                        if restored['fingerprint'] == candidate['fingerprint']:
                            generation, decision, until = restored['generation'], restored['decision'], restored['snoozed_until']
                        self.conn.execute('DELETE FROM suggestion_preferences WHERE key=?', (candidate['key'],))
                    self.conn.execute('''INSERT OR REPLACE INTO suggestions
                        (key,project,scope,fingerprint,generation,json,active,decision,snoozed_until,first_seen,last_seen)
                        VALUES(?,?,?,?,?,?,1,?,?,?,?)''',
                        (candidate['key'], project['id'], candidate['scope'], candidate['fingerprint'], generation,
                         json.dumps(candidate), decision, until, first, stamp))
                for key, row in old.items():
                    if key not in seen and row['scope'] in known and row['active']:
                        self.conn.execute('UPDATE suggestions SET active=0,last_seen=? WHERE key=?', (stamp, key))
            # Keep deliberate dismissals/snoozes. Only forgotten, inactive proposals age out.
            cutoff = (now - dt.timedelta(days=180)).isoformat(timespec='seconds')
            self.conn.execute("DELETE FROM suggestions WHERE active=0 AND decision='pending' AND last_seen<?", (cutoff,))

    @staticmethod
    def linked_goal(candidate, goals):
        goals = sorted(goals, key=lambda g: g['state'] == 'done')
        exact = next((g for g in goals if g.get('suggestion_key') == candidate['key']), None)
        if exact:
            return exact
        for goal in goals:
            if goal['project'] != candidate['project']:
                continue
            rule = goal.get('rule') or {}
            if normalized(goal['title']) == normalized(candidate['title']):
                return goal
            if candidate['verification_kind'] != 'manual' and rule.get('kind') == candidate['verification_kind'] and str(rule.get('target') or '') == candidate['verification_target']:
                return goal
        return None

    def view(self, projects, goals, now):
        valid = {}
        for project in projects:
            candidates, _ = collect(project, now)
            valid.update({c['key']: c for c in candidates})
        result = []
        with self.lock:
            rows = [dict(r) for r in self.conn.execute('SELECT * FROM suggestions')]
        for row in rows:
            candidate = json.loads(row['json'])
            candidate.update(revision=row['fingerprint'] + ':' + str(row['generation']),
                             first_seen=row['first_seen'], last_seen=row['last_seen'], snoozed_until=row['snoozed_until'])
            current = valid.get(row['key'])
            candidate['fresh'] = bool(row['active'] and current and current['fingerprint'] == row['fingerprint'])
            state = 'pending'
            if not row['active']:
                state = 'inactive'
            elif row['decision'] == 'dismissed':
                state = 'dismissed'
            elif row['decision'] == 'snoozed' and instant(row['snoozed_until']) and instant(row['snoozed_until']) > now:
                state = 'snoozed'
            goal = self.linked_goal(candidate, goals)
            candidate['goal_id'] = goal['id'] if goal else None
            candidate['goal_state'] = goal['state'] if goal else None
            candidate['goal_changed'] = bool(goal and goal.get('suggestion_key') == candidate['key'] and goal.get('suggestion_revision') != candidate['revision'])
            if goal and row['active'] and state == 'pending':
                if goal['state'] != 'done':
                    state = 'tracked'
                elif goal.get('suggestion_key') == candidate['key']:
                    if goal.get('suggestion_revision') == candidate['revision']:
                        state = 'completed'
                elif candidate['kind'] not in ('failure', 'review') or (instant(goal.get('completed_at')) or now) >= instant(row['first_seen']):
                    state = 'completed'
            candidate['state'] = state
            result.append(candidate)
        return sorted(result, key=lambda c: (not c['fresh'], -c['score'], c['first_seen'], c['key']))

    def decide(self, key, action, now):
        if action not in ('dismiss', 'snooze', 'restore'):
            raise ValueError('Choose add, dismiss, snooze or restore')
        with self.lock, self.conn:
            if not self.conn.execute('SELECT key FROM suggestions WHERE key=?', (key,)).fetchone():
                raise ValueError('Suggestion not found')
            self.conn.execute('DELETE FROM suggestion_preferences WHERE key=?', (key,))
            until = (now + dt.timedelta(days=1)).isoformat(timespec='seconds') if action == 'snooze' else None
            self.conn.execute('UPDATE suggestions SET decision=?,snoozed_until=? WHERE key=?',
                              ({'dismiss': 'dismissed', 'snooze': 'snoozed', 'restore': 'pending'}[action], until, key))

    def preferences(self):
        with self.lock:
            rows = {r['key']: dict(r) for r in self.conn.execute('SELECT key,fingerprint,generation,decision,snoozed_until FROM suggestions')}
            rows.update({r['key']: dict(r) for r in self.conn.execute('SELECT * FROM suggestion_preferences')})
            return list(rows.values())

    def restore_preferences(self, preferences):
        if not isinstance(preferences, list) or len(preferences) > 10000:
            raise ValueError('Invalid suggestion preferences')
        for p in preferences:
            if (not isinstance(p, dict) or p.get('decision') not in ('pending', 'dismissed', 'snoozed')
                    or not isinstance(p.get('key'), str) or not 1 <= len(p['key']) <= 300
                    or not isinstance(p.get('fingerprint'), str) or len(p['fingerprint']) > 300
                    or type(p.get('generation')) is not int or not 1 <= p['generation'] <= 1000000
                    or (p.get('snoozed_until') is not None and not instant(p['snoozed_until']))):
                raise ValueError('Invalid suggestion preference')
        # Called inside the workspace-restore transaction. Do not commit partial restores.
        self.conn.execute('DELETE FROM suggestion_preferences')
        self.conn.execute("UPDATE suggestions SET decision='pending',snoozed_until=NULL")
        for p in preferences:
            values = (p['key'], p['fingerprint'], p['generation'], p['decision'], p.get('snoozed_until'))
            self.conn.execute('INSERT OR REPLACE INTO suggestion_preferences VALUES(?,?,?,?,?)', values)
            self.conn.execute('UPDATE suggestions SET generation=?,decision=?,snoozed_until=? WHERE key=? AND fingerprint=?',
                              (p['generation'], p['decision'], p.get('snoozed_until'), p['key'], p['fingerprint']))
