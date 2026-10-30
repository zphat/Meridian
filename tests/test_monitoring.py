import datetime as dt
import tempfile
import unittest
from meridian import Meridian, PROJECTS, safe_download_asset

class MonitoringTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.app=Meridian(self.tmp.name,start_worker=False)
    def tearDown(self):self.app.close();self.tmp.cleanup()
    def test_modes_persist_and_invalid_modes_are_rejected(self):
        self.app.set_monitor_mode('quiet')
        self.assertEqual(self.app.snapshot()['settings']['monitor_mode'],'quiet')
        with self.assertRaises(ValueError):self.app.set_monitor_mode('unbounded')
        self.app.close();self.app=Meridian(self.tmp.name,start_worker=False)
        self.assertEqual(self.app._settings()['monitor_mode'],'quiet')
    def test_reliability_only_uses_last_day_and_successful_latencies(self):
        now=dt.datetime.now(dt.timezone.utc)
        with self.app.conn:
            for age,success,latency in [(1,1,100),(2,1,200),(3,0,9000),(26,1,1000)]:
                self.app.conn.execute('INSERT INTO site_samples(project,label,url,checked_at,success,latency_ms) VALUES(?,?,?,?,?,?)',('latitude','Landing page','https://latitude.pictures',(now-dt.timedelta(hours=age)).isoformat(),success,latency))
        m=self.app.snapshot()['site_metrics'][0]
        self.assertEqual((m['checks'],m['passed'],m['avg_latency_ms'],m['max_latency_ms']),(3,2,150,200))
    def test_retention_keeps_a_week_of_probes_and_removes_old_samples(self):
        now=dt.datetime.now(dt.timezone.utc)
        with self.app.conn:
            for age in (1,7,15):
                self.app.conn.execute('INSERT INTO site_samples(project,label,url,checked_at,success,latency_ms) VALUES(?,?,?,?,?,?)',('latitude','Landing page','https://latitude.pictures',(now-dt.timedelta(days=age)).isoformat(),1,100))
        self.app.check_url=lambda *args:{'success':True,'status':200,'latency_ms':50,'tls_days':60,'error':''}
        self.app.site_sync()
        rows=self.app.conn.execute("SELECT checked_at FROM site_samples WHERE project='latitude'").fetchall()
        self.assertEqual(len(rows),3)
        self.assertTrue(any(r[0].startswith((now-dt.timedelta(days=7)).date().isoformat()) for r in rows))
    def test_state_revision_changes_after_note_or_monitoring_edit(self):
        initial=self.app.state_revision()
        self.app.insert('notes',dict(project='latitude',title='Revision',body='Changed'))
        self.assertNotEqual(initial,self.app.state_revision())
        revision=self.app.state_revision();self.app.set_monitor_mode('paused')
        self.assertNotEqual(revision,self.app.state_revision())
