import datetime as dt
import sqlite3
import tempfile
import threading
import unittest
from pathlib import Path
from meridian import Meridian, PROJECTS, iso_now
from goal_guidance import evaluate, rule_for, guidance, UPTIME_GOAL

class GoalEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.now=iso_now()
        self.old=(dt.datetime.now(dt.timezone.utc)-dt.timedelta(days=2)).isoformat()
        self.goal=dict(id=1,project='sundial',title=UPTIME_GOAL,description='Investigate',state='todo')
        run=dict(workflow_id=7,name='Tests',status='completed',conclusion='success',head_sha='current',created_at=self.now,html_url='https://github.com/example/run/7')
        self.p={'id':'sundial','sites':[{'label':'Sync API','url':'https://sync.sundial.services/v1/health','type':'health','status':{'success':True,'status':200,'checked_at':self.now,'error':''}}],
            'github':{'checked_at':self.now,'error':'','data':{'head_sha':'current','workflows':[run], 'uptime_workflow':dict(run,name='Uptime')}}}
    def check(self):return evaluate(self.goal,self.p,self.now,self.now)
    def test_uptime_needs_both_live_health_and_recent_monitor(self):
        self.assertEqual(self.check()['state'],'verified')
        self.p['github']['data']['uptime_workflow']['conclusion']='failure'
        self.assertEqual(self.check()['state'],'failed')
        self.p['github']['data']['uptime_workflow']['conclusion']='success'
        self.p['sites'][0]['status']['success']=False
        self.assertEqual(self.check()['state'],'failed')
    def test_stale_or_error_cache_cannot_verify(self):
        self.p['github']['error']='API rate limit';self.assertEqual(self.check()['state'],'blocked')
        self.p['github']['error']='';self.p['github']['checked_at']=self.old
        self.assertEqual(self.check()['state'],'blocked')
        self.p['github']['checked_at']=self.now;self.p['sites'][0]['status']['checked_at']=self.old
        self.assertEqual(self.check()['state'],'blocked')
    def test_no_connection_is_unknown_not_a_proven_regression(self):
        self.p['sites'][0]['status'].update(success=False,status=None,error='Connection timed out')
        result=self.check()
        self.assertEqual(result['state'],'blocked')
        self.assertIn('Connection timed out',result['evidence'][0]['detail'])
    def test_old_or_running_monitor_cannot_verify(self):
        self.p['github']['data']['uptime_workflow']['created_at']=self.old
        self.assertEqual(self.check()['state'],'blocked')
        self.p['github']['data']['uptime_workflow'].update(created_at=self.now,status='in_progress',conclusion=None)
        self.assertEqual(self.check()['state'],'blocked')
    def test_build_must_be_selected_workflow_on_current_commit(self):
        self.goal.update(verification_kind='build',verification_target='7')
        self.assertEqual(self.check()['state'],'verified')
        self.p['github']['data']['workflows'][0]['head_sha']='previous'
        self.assertEqual(self.check()['state'],'blocked')
        self.p['github']['data']['workflows'][0]['head_sha']='current'
        self.goal['verification_target']='999'
        self.assertEqual(self.check()['state'],'blocked')
    def test_cancelled_or_skipped_build_is_not_verified(self):
        self.goal.update(verification_kind='build',verification_target='7')
        for outcome in ('cancelled','skipped','neutral',None):
            self.p['github']['data']['workflows'][0]['conclusion']=outcome
            self.assertEqual(self.check()['state'],'blocked')
    def test_manual_hardware_goal_is_not_verified_by_green_build(self):
        self.goal.update(title='Verify macOS recording, permissions and export on real hardware',project='latitude')
        self.assertEqual(self.check()['state'],'manual')
        self.assertIn('real Mac',' '.join(guidance(self.goal)['approach']))
    def test_custom_site_rule_requires_exact_monitored_url(self):
        self.goal.update(verification_kind='site',verification_target=self.p['sites'][0]['url'])
        self.assertEqual(self.check()['state'],'verified')
        self.goal['verification_target']='https://unrelated.example'
        self.assertEqual(self.check()['state'],'blocked')

class GoalPersistenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.app=Meridian(self.tmp.name,start_worker=False)
        self.since=iso_now()
        self.url=PROJECTS['latitude']['sites'][0][1]
        self.id=self.app.insert('goals',dict(project='latitude',title='Repair landing page',verification_kind='site',verification_target=self.url))
    def tearDown(self):self.app.close();self.tmp.cleanup()
    def goal(self):return next(g for g in self.app.snapshot()['goals'] if g['id']==self.id)
    def probe(self,ok):
        with self.app.conn:self.app.conn.execute('INSERT INTO site_samples(project,label,url,checked_at,success,status,error) VALUES(?,?,?,?,?,?,?)',('latitude','Landing page',self.url,iso_now(),int(ok),200 if ok else 503,'' if ok else 'HTTP 503'))
    def test_verified_goal_completes_and_regression_reopens(self):
        self.probe(True);self.app.verify_goals(self.since,self.id)
        self.assertEqual((self.goal()['state'],self.goal()['completion_source']),('done','verified'))
        self.app.close();self.app=Meridian(self.tmp.name,start_worker=False)
        self.assertEqual(self.goal()['check']['state'],'verified')
        self.probe(False);self.app.verify_goals(self.since,self.id)
        self.assertEqual((self.goal()['state'],self.goal()['check']['state']),('todo','failed'))
        self.assertEqual(self.app.verification_report['reopened'],1)
    def test_manual_completion_is_not_silently_reversed(self):
        self.app.change_goal(self.id,{'state':'done'});self.probe(False);self.app.verify_goals(self.since,self.id)
        self.assertEqual(self.goal()['state'],'done');self.assertEqual(self.goal()['check']['state'],'failed')
    def test_connection_loss_does_not_reopen_verified_goal(self):
        self.probe(True);self.app.verify_goals(self.since,self.id)
        self.probe(False)
        with self.app.conn:self.app.conn.execute('UPDATE site_samples SET status=NULL,error=? WHERE id=(SELECT MAX(id) FROM site_samples)',('Connection timed out',))
        self.app.verify_goals(self.since,self.id)
        self.assertEqual(self.goal()['state'],'done')
        self.assertEqual(self.goal()['check']['state'],'blocked')
    def test_editing_acceptance_invalidates_old_verification(self):
        self.probe(True);self.app.verify_goals(self.since,self.id)
        self.app.change_goal(self.id,{'description':'A different acceptance requirement'})
        self.assertEqual(self.goal()['state'],'todo');self.assertIsNone(self.goal()['check'])
    def test_backup_restores_rules_without_trusting_old_proof(self):
        self.probe(True);self.app.verify_goals(self.since,self.id)
        backup=self.app.backup();self.app.restore(backup)
        g=next(g for g in self.app.snapshot()['goals'] if g['title']=='Repair landing page')
        self.assertEqual(g['rule'],{'kind':'site','target':self.url});self.assertIsNone(g['check'])
    def test_invalid_rule_is_rejected_without_changing_goal(self):
        before=self.goal()
        with self.assertRaises(ValueError):self.app.change_goal(self.id,{'verification_target':'http://127.0.0.1/private'})
        self.assertEqual(self.goal()['verification_target'],before['verification_target'])
    def test_duplicate_refresh_is_not_started_and_other_projects_not_fetched(self):
        started=threading.Event();release=threading.Event();seen=[]
        def github(pid=None):seen.append(pid);started.set();release.wait(2)
        self.app.github_sync=github;self.app.site_sync=lambda pid=None:self.probe(True)
        self.assertTrue(self.app.refresh_async(verify=True,goal_id=self.id));self.assertTrue(started.wait(1))
        self.assertFalse(self.app.refresh_async(verify=True,goal_id=self.id))
        release.set();self.app._manual_worker.join(3)
        self.assertEqual(seen,['latitude']);self.assertEqual(self.goal()['check']['state'],'verified')
    def test_legacy_database_migrates_without_losing_notes(self):
        self.app.close()
        db=Path(self.tmp.name)/'meridian.sqlite3'
        conn=sqlite3.connect(db)
        for column in ('verification_kind','verification_target','completion_source'):conn.execute('ALTER TABLE goals DROP COLUMN '+column)
        conn.execute("INSERT INTO notes(project,title,body,created_at) VALUES('latitude','Keep this','My note',?)",(iso_now(),));conn.commit();conn.close()
        self.app=Meridian(self.tmp.name,start_worker=False)
        self.assertTrue(any(n['title']=='Keep this' for n in self.app.snapshot()['notes']))
        self.assertEqual(self.goal()['rule']['kind'],'manual')

if __name__=='__main__':unittest.main()
