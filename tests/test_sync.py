import json
import tempfile
import unittest
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from meridian import Meridian

class SyncTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.app=Meridian(self.tmp.name,start_worker=False)
    def tearDown(self):
        self.app.close();self.tmp.cleanup()
    def test_live_github_collection_and_dedup(self):
        def github(path):
            if path.endswith('/releases?per_page=6'):
                return [dict(id=1,tag_name='v5.0.0',name='Release 5',published_at='2026-10-29T12:00:00Z',html_url='https://github.com/test/releases/tag/v5.0.0',prerelease=False,assets=[dict(name='Setup.exe',download_count=7),dict(name='SHA256SUMS.txt',download_count=120)])]
            if path.endswith('/actions/runs?per_page=50'):
                return dict(workflow_runs=[dict(name='uptime',status='completed',conclusion='failure',html_url='https://github.com/example/uptime',created_at='2026-10-29T12:30:00Z'),dict(name='Tests',status='completed',conclusion='success',html_url='https://github.com/example/tests',created_at='2026-10-29T12:00:00Z')])
            if path.endswith('/commits?per_page=15'):
                return [dict(sha='abc',commit=dict(message='Improve timeline\nAdditional text',committer=dict(date='2026-10-29T12:00:00Z')),html_url='https://github.com/example/commit/abc')]
            if path.endswith('/issues?state=open&per_page=40'):
                return [dict(number=2,title='Fix a bug',html_url='https://github.com/example/issues/2')]
            return dict(description='Repo',pushed_at='2026-10-29T12:00:00Z',open_issues_count=1,default_branch='main')
        self.app._github_get=github
        self.app._roadmap=lambda repo,branch:{'file':'PROJECT_STATUS.md','url':'https://github.com/example/PROJECT_STATUS.md','open_items':['One thing'],'text':'# Project'}
        self.app.github_sync()
        state=self.app.snapshot()
        self.assertEqual(len(state['events']),6)
        self.assertEqual(state['projects'][0]['github']['data']['release']['tag_name'],'v5.0.0')
        self.assertEqual(state['projects'][0]['latest_downloads'],7)
        self.assertEqual(state['projects'][2]['github']['data']['uptime_workflow']['conclusion'],'failure')
        self.assertEqual(len(state['projects'][1]['github']['data']['issues']),1)
        self.assertEqual(state['projects'][1]['github']['data']['roadmap']['open_items'][0],'One thing')
        self.app.github_sync()
        self.assertEqual(len(self.app.snapshot()['events']),6)
    def test_site_health_persistence(self):
        self.app.check_url=lambda url,health=False:{'success':True,'status':200,'latency_ms':60,'tls_days':None,'error':''}
        self.app.site_sync()
        state=self.app.snapshot()
        self.assertEqual(sum(len(p['sites']) for p in state['projects']),6)
        self.assertTrue(all(s['status']['success']==1 for p in state['projects'] for s in p['sites']))
        self.assertEqual(len(state['site_history']),6)

if __name__=='__main__':unittest.main()
