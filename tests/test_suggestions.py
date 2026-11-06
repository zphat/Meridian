import copy
import datetime as dt
import json
import tempfile
import unittest
import urllib.error
from io import BytesIO
from pathlib import Path
from unittest.mock import patch
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from meridian import Meridian, iso_now
from suggestions import collect, parse_followups


def fixture(now=None):
    now = now or dt.datetime.now(dt.timezone.utc)
    stamp = now.isoformat(timespec='seconds')
    run = dict(workflow_id=17, name='Windows release', status='completed', conclusion='failure',
               head_sha='a'*40, created_at=stamp, html_url='https://github.com/test/actions/runs/17')
    return dict(id='longitude', name='Longitude', repository='zphat/Longitude', sites=[
        dict(label='Browser editor', url='https://zphat.github.io/Longitude/app/', type='app',
             status=dict(success=1, status=200, tls_days=60, checked_at=stamp, error=''))],
        github=dict(checked_at=stamp, error='', data=dict(head_sha='a'*40, evidence_checked_at=stamp,
            workflows=[run], commits=[dict(sha='a'*40, message='Improve editor layout and export', date=stamp,
                url='https://github.com/test/commit/'+'a'*40)],
            issues=[dict(number=3, title='Export colors need review', labels=['priority:high'], url='https://github.com/test/issues/3')],
            roadmap=dict(status='ok', file='PROJECT_STATUS.md', open_items=['[low] Expand documentation'], url='https://github.com/test/roadmap', checked_at=stamp),
            followups=dict(status='missing', items=[]))))


class RankingTests(unittest.TestCase):
    def setUp(self):
        self.now = dt.datetime.now(dt.timezone.utc)
        self.project = fixture(self.now)

    def candidates(self):
        return collect(self.project, self.now)[0]

    def test_current_failure_ranks_above_issues_reviews_and_roadmap(self):
        items = sorted(self.candidates(), key=lambda c: -c['score'])
        self.assertEqual([i['kind'] for i in items], ['failure', 'reported', 'review', 'planned'])
        self.assertEqual(items[0]['verification_kind'], 'build')
        self.assertEqual(items[0]['verification_target'], '17')
        self.assertIn('small window', str(items[2]['guidance']))
        self.assertIn('Export a real project', str(items[2]['guidance']))
        self.assertEqual(items[-1]['title'], 'Expand documentation')
        self.assertEqual(items[-1]['priority'], 'low')

    def test_old_commit_pending_cancelled_skipped_and_success_are_not_failures(self):
        run = self.project['github']['data']['workflows'][0]
        for status, conclusion, head in [('completed','failure','old'),('in_progress',None,'a'*40),('completed','cancelled','a'*40),('completed','skipped','a'*40),('completed','success','a'*40)]:
            run.update(status=status, conclusion=conclusion, head_sha=head)
            self.assertFalse(any(i['kind']=='failure' for i in self.candidates()))

    def test_rate_limit_and_stale_evidence_do_not_create_failures(self):
        self.project['github']['error']='GitHub allowance paused'
        self.assertEqual(self.candidates(), [])
        self.project['github']['error']=''
        self.project['github']['data']['evidence_checked_at']=(self.now-dt.timedelta(hours=4)).isoformat()
        self.assertEqual(self.candidates(), [])

    def test_health_failure_is_critical_network_failure_is_investigation(self):
        self.project.update(id='sundial',name='Sundial',uptime_workflow_path='.github/workflows/uptime.yml')
        site=self.project['sites'][0];site['type']='health';site['status'].update(success=0,status=503,error='HTTP 503')
        item=next(i for i in self.candidates() if i['key'].startswith('sundial:endpoint:'))
        self.assertEqual(item['priority'],'critical');self.assertEqual(item['verification_kind'],'uptime')
        site['status'].update(status=None,error='DNS lookup failed')
        item=next(i for i in self.candidates() if ':endpoint:' in i['key'])
        self.assertEqual(item['priority'],'high');self.assertIn('connection',item['reason'])
        site['status']['checked_at']=(self.now-dt.timedelta(hours=1)).isoformat()
        self.assertFalse(any(':endpoint:' in i['key'] for i in self.candidates()))

    def test_certificate_warning_needs_manual_renewal_check(self):
        self.project['sites'][0]['status']['tls_days']=5
        item=next(i for i in self.candidates() if i['kind']=='maintenance')
        self.assertEqual(item['priority'],'high');self.assertEqual(item['verification_kind'],'manual')

    def test_pull_requests_not_issues_and_old_pushes_not_reviewed(self):
        data=self.project['github']['data'];data['issues'][0]['pull_request']=True
        data['commits'][0]['date']=(self.now-dt.timedelta(days=8)).isoformat()
        self.assertFalse(any(i['kind'] in ('reported','review') for i in self.candidates()))

    def test_invalid_or_unavailable_followups_are_unknown_not_empty(self):
        data=self.project['github']['data']
        for status in ['invalid','error']:
            data['followups']={'status':status};data['roadmap']={'status':status,'open_items':[]}
            known=collect(self.project,self.now)[1]
            self.assertNotIn('followups',known);self.assertNotIn('roadmap',known)

    def test_explicit_followups_keep_acceptance_and_stable_identity(self):
        item=dict(id='editor-narrow',title='Verify narrow editor',priority='high',reason='Resizing changed.',
                  steps=['Resize the editor to 800 pixels.'],acceptance=['Export remains reachable.'])
        parsed=parse_followups(json.dumps({'version':1,'suggestions':[item]}))
        self.project['github']['data']['followups']=dict(status='ok',items=parsed,url='https://github.com/test/followups',checked_at=iso_now())
        candidate=next(i for i in self.candidates() if i['kind']=='followup')
        self.assertEqual(candidate['key'],'longitude:followup:editor-narrow')
        self.assertEqual(candidate['guidance']['acceptance'],item['acceptance'])
        self.assertEqual(candidate['fingerprint'],'1')

    def test_followup_schema_rejects_bad_or_unbounded_inputs(self):
        base={'id':'one','title':'Test','reason':'Reason','priority':'high','acceptance':['Works']}
        for change in [{'id':'../path'},{'priority':'everything'},{'priority':{}},{'acceptance':[]},{'acceptance':['x'*801]},{'steps':[None]},{'state':'run'}]:
            with self.assertRaises(ValueError):parse_followups(json.dumps({'version':1,'suggestions':[{**base,**change}]}))
        with self.assertRaises(ValueError):parse_followups(json.dumps({'version':1,'suggestions':[base,base]}))
        with self.assertRaises(ValueError):parse_followups('{"version":2,"suggestions":[]}')
        self.assertEqual(parse_followups(json.dumps({'version':1,'suggestions':[{**base,'state':'done'}]})),[])


class SuggestionPersistenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.app=Meridian(self.tmp.name,start_worker=False)
        self.project=fixture();self.push()

    def tearDown(self):
        self.app.close();self.tmp.cleanup()

    def push(self):
        data=self.project['github']['data'];data['evidence_checked_at']=iso_now()
        self.app._cache('github:longitude',data,self.project['github']['error'])
        self.app.refresh_suggestions()

    def item(self,key='longitude:build:17'):
        return next(c for c in self.app.snapshot()['suggestions'] if c['key']==key)

    def action(self,action,key='longitude:build:17'):
        item=self.item(key)
        return self.app.suggestion_action(key,action,item['revision'])

    def test_add_is_idempotent_and_keeps_detailed_guidance_and_verification(self):
        count=len(self.app.snapshot()['goals'])
        first=self.action('add');again=self.action('add')
        self.assertEqual(first['goal_id'],again['goal_id'])
        state=self.app.snapshot();self.assertEqual(len(state['goals']),count+1)
        goal=next(g for g in state['goals'] if g['id']==first['goal_id'])
        self.assertEqual(goal['rule'],{'kind':'build','target':'17'})
        self.assertIn('first failing step',goal['guidance']['approach'][0])
        self.assertEqual(self.item()['state'],'tracked')

    def test_existing_goal_is_linked_instead_of_duplicated(self):
        id=self.app.insert('goals',dict(project='longitude',title='My existing release task',verification_kind='build',verification_target='17'))
        self.assertEqual(self.item()['goal_id'],id)
        self.assertEqual(self.action('add')['goal_id'],id)

    def test_same_failure_stays_completed_new_commit_can_reopen_explicitly(self):
        id=self.action('add')['goal_id'];self.app.change_goal(id,{'state':'done'})
        completed=next(g for g in self.app.snapshot()['goals'] if g['id']==id)['completed_at']
        self.push();self.assertEqual(self.item()['state'],'completed')
        self.project['github']['data']['head_sha']='b'*40
        self.project['github']['data']['workflows'][0]['head_sha']='b'*40
        self.push();self.assertEqual(self.item()['state'],'pending')
        self.assertEqual(next(g for g in self.app.snapshot()['goals'] if g['id']==id)['completed_at'],completed)
        result=self.action('add');self.assertEqual(result['goal_id'],id);self.assertTrue(result['reopened'])
        self.assertEqual(self.item()['state'],'tracked')

    def test_dismissed_survives_repeat_refresh_and_restart_then_regression_returns(self):
        self.action('dismiss');self.push();self.assertEqual(self.item()['state'],'dismissed')
        self.app.close();self.app=Meridian(self.tmp.name,start_worker=False)
        self.assertEqual(self.item()['state'],'dismissed')
        self.project['github']['data']['workflows'][0]['conclusion']='success';self.push()
        self.assertEqual(self.item()['state'],'inactive')
        self.project['github']['data']['workflows'][0]['conclusion']='failure';self.push()
        self.assertEqual(self.item()['state'],'pending')

    def test_source_outage_does_not_mean_problem_resolved(self):
        self.project['github']['error']='GitHub requests paused';self.push()
        item=self.item();self.assertEqual(item['state'],'pending');self.assertFalse(item['fresh'])
        with self.assertRaisesRegex(ValueError,'Refresh first'):self.action('add')
        self.project['github']['error']='';self.push();self.assertTrue(self.item()['fresh'])

    def test_snooze_expires_without_new_network_request(self):
        self.action('snooze');self.assertEqual(self.item()['state'],'snoozed')
        state=self.app.snapshot(include_suggestions=False)
        later=self.app.suggestions.view(state['projects'],state['goals'],dt.datetime.now(dt.timezone.utc)+dt.timedelta(hours=25))
        item=next(c for c in later if c['key']=='longitude:build:17')
        self.assertEqual(item['state'],'pending');self.assertFalse(item['fresh'])
        self.action('restore');self.assertEqual(self.item()['state'],'pending')

    def test_old_ui_revision_cannot_accept_changed_proposal(self):
        old=self.item()['revision'];self.project['github']['data']['head_sha']='b'*40
        self.project['github']['data']['workflows'][0]['head_sha']='b'*40;self.push()
        with self.assertRaisesRegex(ValueError,'changed'):self.app.suggestion_action('longitude:build:17','add',old)

    def test_new_push_updates_existing_plan_only_on_explicit_action(self):
        key='longitude:update-review';id=self.action('add',key)['goal_id']
        self.app.change_goal(id,{'state':'doing'})
        before=next(g for g in self.app.snapshot()['goals'] if g['id']==id)
        data=self.project['github']['data'];data['head_sha']='b'*40;data['commits'][0]['sha']='b'*40
        self.push();self.assertTrue(self.item(key)['goal_changed'])
        current=next(g for g in self.app.snapshot()['goals'] if g['id']==id)
        self.assertEqual(current['guidance'],before['guidance'])
        result=self.action('update',key);self.assertTrue(result['updated'])
        current=next(g for g in self.app.snapshot()['goals'] if g['id']==id)
        self.assertEqual(current['state'],'doing');self.assertIn('b'*40,str(current['guidance']))
        self.assertIn(before['description'],current['description'])
        self.assertFalse(self.item(key)['goal_changed'])
        self.action('update',key)
        self.assertEqual(next(g for g in self.app.snapshot()['goals'] if g['id']==id)['description'],current['description'])

    def test_reading_state_does_not_write_or_change_goals(self):
        writes=self.app.conn.total_changes;state=self.app.snapshot();self.app.snapshot()
        self.assertEqual(self.app.conn.total_changes,writes)
        self.assertEqual(len(state['goals']),13)

    def test_issue_pagination_does_not_forget_a_dismissal(self):
        self.action('dismiss','longitude:issue:3')
        original=copy.deepcopy(self.project['github']['data']['issues'])
        self.project['github']['data']['issues']=[];self.push()
        self.assertEqual(self.item('longitude:issue:3')['state'],'inactive')
        self.project['github']['data']['issues']=original;self.push()
        self.assertEqual(self.item('longitude:issue:3')['state'],'dismissed')

    def test_active_matching_goal_preferred_to_an_older_completed_duplicate(self):
        values=dict(project='longitude',title='Release fix',verification_kind='build',verification_target='17')
        active=self.app.insert('goals',values)
        self.app.insert('goals',{**values,'state':'done','priority':'critical'})
        self.assertEqual(self.item()['goal_id'],active)
        roadmap_id=self.app.insert('goals',dict(project='longitude',title='[low] Expand documentation'))
        planned=next(s for s in self.app.snapshot()['suggestions'] if s['kind']=='planned')
        self.assertEqual(planned['goal_id'],roadmap_id)

    def test_user_choice_after_restore_wins_over_restored_preference(self):
        self.action('dismiss');backup=self.app.backup();self.app.restore(backup)
        self.action('restore');self.push()
        self.assertEqual(self.item()['state'],'pending')

    def test_deleting_accepted_goal_dismisses_its_suggestion(self):
        id=self.action('add')['goal_id'];self.app.delete('goals',id)
        self.assertEqual(self.item()['state'],'dismissed')

    def test_backup_restores_plan_and_dismissals_on_another_installation(self):
        id=self.action('add')['goal_id'];self.app.change_goal(id,{'state':'done'})
        self.action('dismiss','longitude:issue:3');backup=self.app.backup()
        with tempfile.TemporaryDirectory() as dest:
            other=Meridian(dest,start_worker=False)
            try:
                other.restore(backup)
                other._cache('github:longitude',self.project['github']['data']);other.refresh_suggestions()
                state=other.snapshot();items={i['key']:i for i in state['suggestions']}
                self.assertEqual(items['longitude:issue:3']['state'],'dismissed')
                self.assertEqual(items['longitude:build:17']['state'],'completed')
                goal=next(g for g in state['goals'] if g['suggestion_key']=='longitude:build:17')
                self.assertIn('first failing step',goal['guidance']['approach'][0])
            finally:other.close()

    def test_invalid_backup_preferences_roll_back_workspace_restore(self):
        backup=self.app.backup();backup['goals']=[];backup['suggestion_preferences']=[{'decision':'explode'}]
        before=self.app.snapshot()['goals']
        with self.assertRaises(ValueError):self.app.restore(backup)
        self.assertEqual(self.app.snapshot()['goals'],before)

    def test_pinned_followup_file_cached_until_new_push(self):
        body=json.dumps({'version':1,'suggestions':[]}).encode()
        with patch('meridian.urllib.request.urlopen',side_effect=lambda *a,**k:BytesIO(body)) as request:
            self.assertEqual(self.app._followups('zphat/Longitude','a'*40)['status'],'ok')
            self.app._followups('zphat/Longitude','a'*40)
            self.assertEqual(request.call_count,1)
            self.app._followups('zphat/Longitude','b'*40)
            self.assertEqual(request.call_count,2)

    def test_missing_invalid_and_transient_followup_files_are_distinguished(self):
        with patch('meridian.urllib.request.urlopen',side_effect=urllib.error.HTTPError('url',404,'Missing',{},None)):
            self.assertEqual(self.app._followups('zphat/Longitude','missing')['status'],'missing')
        with patch('meridian.urllib.request.urlopen',return_value=BytesIO(b'{broken')):
            self.assertEqual(self.app._followups('zphat/Longitude','invalid')['status'],'invalid')
        with patch('meridian.urllib.request.urlopen',side_effect=urllib.error.URLError('offline')):
            self.assertEqual(self.app._followups('zphat/Longitude','offline')['status'],'error')


if __name__=='__main__':unittest.main()
