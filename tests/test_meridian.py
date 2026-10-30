import datetime
import json
import tempfile
import unittest
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from meridian import Meridian, PROJECTS, safe_download_asset

class MeridianTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.app = Meridian(self.temp.name,start_worker=False)
    def tearDown(self):
        self.app.close()
        self.temp.cleanup()
    def test_seed_and_state(self):
        state=self.app.snapshot()
        self.assertEqual([p['name'] for p in state['projects']],['Latitude','Longitude','Sundial'])
        self.assertTrue(state['goals'])
        self.assertTrue(state['decisions'])
        self.assertEqual(state['projects'][0]['github']['data']['release']['tag_name'],'v0.9.4')
    def test_goal_lifecycle(self):
        id=self.app.insert('goals',dict(project='longitude',title='Smoke test',priority='low',description='',category='QA'))
        self.assertEqual(next(g for g in self.app.snapshot()['goals'] if g['id']==id)['state'],'todo')
        self.app.change_goal(id,dict(state='doing'))
        self.assertEqual(next(g for g in self.app.snapshot()['goals'] if g['id']==id)['state'],'doing')
        self.app.change_goal(id,dict(state='done'))
        self.assertIsNotNone(next(g for g in self.app.snapshot()['goals'] if g['id']==id)['completed_at'])
        self.app.delete('goals',id)
        self.assertFalse(any(g['id']==id for g in self.app.snapshot()['goals']))
    def test_notes_and_backup_roundtrip(self):
        self.app.insert('notes',dict(project='latitude',title='Sample',body='Test note'))
        saved=self.app.backup()
        self.app.delete('notes',self.app.snapshot()['notes'][0]['id'])
        self.app.restore(saved)
        self.assertEqual(self.app.snapshot()['notes'][0]['title'],'Sample')
    def test_csv_import_upsert(self):
        csv='date,visitors,pageviews\n2026-10-27,13,19\n2026-10-28,14,22\n'
        self.assertEqual(self.app.import_csv(csv,'latitude'),2)
        self.assertEqual(self.app.import_csv('date,visitors,pageviews\n2026-10-28,15,26\n','latitude'),1)
        rows=self.app.snapshot()['web_analytics']
        self.assertEqual(len(rows),2)
        self.assertEqual(next(x for x in rows if x['date']=='2026-10-28')['visitors'],15)
    def test_bad_csv_and_project_rejected(self):
        with self.assertRaises(ValueError):self.app.import_csv('bad,headers\n2,3','latitude')
        with self.assertRaises(ValueError):self.app.insert('notes',dict(project='bogus',title='x'))
    def test_event_dedup(self):
        event=('commit','abc123','Fix layout','','https://github.com/zphat/Latitude/commit/abc123','2026-10-29T08:29:00Z')
        self.app._store_events('latitude',[event,event])
        self.assertEqual(len(self.app.snapshot()['events']),1)
    def test_samples_reflect_latest(self):
        with self.app.lock,self.app.conn:
            for ok in (0,1):
                self.app.conn.execute('INSERT INTO site_samples(project,label,url,checked_at,success,status,latency_ms,error) VALUES(?,?,?,?,?,?,?,?)',('latitude','Landing page','https://latitude.pictures','2026-10-29T12:00:00Z',ok,200,120,''))
        s=self.app.snapshot()['projects'][0]['sites'][0]['status']
        self.assertEqual(s['success'],1)
    def test_download_extension_filter(self):
        self.assertTrue(safe_download_asset({'name':'LatitudeSetup.exe'}))
        self.assertFalse(safe_download_asset({'name':'SHA256SUMS.txt'}))
        self.assertFalse(safe_download_asset({'name':'tool-sources.zip'}))

if __name__=='__main__':unittest.main()
