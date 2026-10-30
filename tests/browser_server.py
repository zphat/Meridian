"""Disposable browser fixture. No network calls, production data or real mail."""
import datetime as dt
import sys,tempfile
from pathlib import Path
from http.server import ThreadingHTTPServer
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from meridian import Meridian,Handler,PROJECTS
from unittest.mock import patch

class QuietHandler(Handler):
    def log_message(self,*args):pass

with tempfile.TemporaryDirectory() as data:
    app=Meridian(data,start_worker=False)
    app.auth._send_resend=lambda cfg,url:'fixture-email-reference'
    now=dt.datetime.now(dt.timezone.utc)
    with app.lock,app.conn:
        for p,config in PROJECTS.items():
            for index,(label,url,typ) in enumerate(config['sites']):
                for age in reversed(range(48)):
                    stamp=(now-dt.timedelta(minutes=30*age)).isoformat(timespec='seconds')
                    ok=0 if p=='sundial' and index==2 and age in (8,9) else 1
                    app.conn.execute('INSERT INTO site_samples(project,label,url,checked_at,success,status,latency_ms,tls_days,error) VALUES(?,?,?,?,?,?,?,?,?)',(p,label,url,stamp,ok,200 if ok else 503,120+index*35+age%7*18,62,'' if ok else 'HTTP 503'))
            for day in reversed(range(8)):
                stamp=(now-dt.timedelta(days=day)).isoformat(timespec='seconds')
                app.conn.execute('INSERT INTO downloads(project,release_tag,asset,counted_at,total) VALUES(?,?,?,?,?)',(p,app.snapshot()['projects'][list(PROJECTS).index(p)]['github']['data']['release']['tag_name'],'Setup.exe',stamp,500-day*17))
                app.conn.execute('INSERT INTO web_analytics(project,date,visitors,pageviews) VALUES(?,?,?,?)',(p,stamp[:10],30+day*2,70+day*6))
    server=ThreadingHTTPServer(('127.0.0.1',0),QuietHandler);server.meridian=app
    print(server.server_port,flush=True)
    try:
        with patch('auth.secrets.randbelow',return_value=13572468):server.serve_forever()
    finally:server.server_close();app.close()
