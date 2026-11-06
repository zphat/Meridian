"""Disposable browser fixture. No network calls, production data or real mail."""
import datetime as dt
import copy
import json,time,urllib.error
from io import BytesIO
import sys,tempfile
from pathlib import Path
from http.server import ThreadingHTTPServer
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from meridian import Meridian,Handler,PROJECTS,iso_now
from unittest.mock import patch

class QuietHandler(Handler):
    def log_message(self,*args):pass
    def do_POST(self):
        # Test-only control. Never included in a packaged application.
        if self.path.startswith('/__test/checks/'):
            self.server.fail_checks=self.path.endswith('/fail')
            return self.reply({'ok':True})
        if self.path=='/__test/github-limit':
            self.server.meridian.github_access.state.update(reason='rate_limited',pause_until=time.time()+600,remaining=0,limit=60,reset_at=int(time.time()+600))
            self.server.meridian.github_access._persist()
            return self.reply({'ok':True})
        if self.path.startswith('/__test/suggestions'):
            app=self.server.meridian
            project=next(p for p in app.snapshot()['projects'] if p['id']=='longitude')
            data=copy.deepcopy(project['github']['data'])
            if self.path.endswith('/offline'):
                app._cache('github:longitude',None,'Temporary test connection failure')
            else:
                head='fixture-next-update' if self.path.endswith('/new-push') else 'fixture-editor-update'
                run=dict(workflow_id=27,name='Windows editor release',head_sha=head,status='completed',conclusion='failure',created_at=iso_now(),html_url='https://github.com/zphat/Longitude/actions/runs/27')
                data.update(head_sha=head,evidence_checked_at=iso_now(),workflows=[run],ci=run,
                    commits=[dict(sha=head,message='Improve editor layout and export recovery',date=iso_now(),url='https://github.com/zphat/Longitude/commit/'+head)],
                    issues=[dict(number=42,title='Review export colors',labels=['priority:medium'],body='<img src=x onerror="window.injected=true">',url='https://github.com/zphat/Longitude/issues/42')],
                    roadmap=dict(status='ok',file='PROJECT_STATUS.md',open_items=['[low] Improve keyboard help'],checked_at=iso_now(),url='https://github.com/zphat/Longitude/blob/main/PROJECT_STATUS.md'),
                    followups=dict(status='ok',checked_at=iso_now(),url='https://github.com/zphat/Longitude/blob/main/MERIDIAN_GOALS.json',items=[dict(id='narrow-editor',revision='1',title='Verify editor controls after the layout update',priority='high',reason='The new layout changes panel sizing. Test an actual editing session before considering it finished.',steps=['Open a real project in an 800-pixel window.','Resize panels, change text and export the result.'],acceptance=['Export and layer controls remain reachable.','The exported result matches the preview.'])]))
                app._cache('github:longitude',data)
            app.refresh_suggestions()
            return self.reply({'ok':True})
        return super().do_POST()

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
    server=ThreadingHTTPServer(('127.0.0.1',0),QuietHandler);server.meridian=app;server.fail_checks=False
    def github_sync(project_id=None,fresh=False):
        for p in app.snapshot()['projects']:
            if project_id and p['id']!=project_id:continue
            data=copy.deepcopy(p['github']['data'])
            run={'workflow_id':7,'name':'Packaged application tests','head_sha':'fixture-current-commit',
                 'status':'completed','conclusion':'failure' if server.fail_checks else 'success',
                 'created_at':iso_now(),'updated_at':iso_now(),'html_url':'https://github.com/'+p['repository']+'/actions/runs/7'}
            data.update(head_sha=run['head_sha'],workflows=[run],ci=run,
                        uptime_workflow=dict(run,workflow_id=8,name='Scheduled uptime monitor'))
            app._cache('github:'+p['id'],data)
    def check_url(url,health=False):
        ok=not server.fail_checks
        return {'success':ok,'status':200 if ok else 503,'latency_ms':140,'tls_days':62,
                'checked_at':iso_now(),'error':'' if ok else 'HTTP 503'}
    app.github_sync=github_sync;app.check_url=check_url
    class Response:
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def read(self,n=-1):return json.dumps({'resources':{'core':{'limit':5000,'remaining':4998,'reset':int(time.time()+3600)}}}).encode()
    def github_response(request,**kwargs):
        if request.full_url!='https://api.github.com/rate_limit':raise AssertionError('Unexpected fixture network request')
        if 'invalid' in request.get_header('Authorization',''):
            raise urllib.error.HTTPError(request.full_url,401,'Invalid token',{},BytesIO(b'{}'))
        return Response()
    print(server.server_port,flush=True)
    try:
        with patch('auth.secrets.randbelow',return_value=13572468),patch('github_access.urllib.request.urlopen',side_effect=github_response):server.serve_forever()
    finally:server.server_close();app.close()
