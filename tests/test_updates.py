import json
import sys
import tempfile
import threading
import unittest
import urllib.error
from http.server import ThreadingHTTPServer
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import meridian

class FakeResponse:
    def __init__(self,obj):self.buf=BytesIO(json.dumps(obj).encode())
    def __enter__(self):return self
    def __exit__(self,*args):pass
    def read(self,n=-1):return self.buf.read(n)

class UpdateTests(unittest.TestCase):
    def setUp(self):
        self.data=tempfile.TemporaryDirectory()
        self.app=meridian.Meridian(self.data.name,start_worker=False)
    def tearDown(self):
        self.app.close()
        self.data.cleanup()
    def test_available_and_asset_detection(self):
        payload={"tag_name":"v0.3.0","html_url":"https://github.com/zphat/Meridian/releases/tag/v0.3.0","assets":[{"name":"Meridian-Setup-0.3.0.exe","browser_download_url":"https://github.com/zphat/Meridian/releases/download/v0.3.0/Meridian-Setup-0.3.0.exe"}]}
        with patch.object(meridian.sys, 'platform', 'win32'), patch.object(meridian.urllib.request,'urlopen',return_value=FakeResponse(payload)):
            state=self.app.check_updates()
        self.assertEqual(state['state'],'available')
        self.assertTrue(state['installer_url'].endswith('Meridian-Setup-0.3.0.exe'))
        self.assertEqual(self.app.snapshot()['updates']['latest'],'0.3.0')
    def test_up_to_date_and_malformed(self):
        payload={'tag_name':f'v{meridian.VERSION}','html_url':f'https://github.com/zphat/Meridian/releases/tag/v{meridian.VERSION}','assets':[]}
        with patch.object(meridian.urllib.request,'urlopen',return_value=FakeResponse(payload)):
            self.assertEqual(self.app.check_updates()['state'],'up_to_date')
        payload['tag_name']='surprise-script'
        with patch.object(meridian.urllib.request,'urlopen',return_value=FakeResponse(payload)):
            self.assertEqual(self.app.check_updates()['state'],'error')
    def test_linux_update_asset_preferred(self):
        payload={"tag_name":"v0.3.0","html_url":"https://github.com/zphat/Meridian/releases/tag/v0.3.0","assets":[
            {"name":"Meridian-0.3.0-all.deb","browser_download_url":"https://github.com/zphat/Meridian/releases/download/v0.3.0/Meridian-0.3.0-all.deb"},
            {"name":"Meridian-Linux-0.3.0.run","browser_download_url":"https://github.com/zphat/Meridian/releases/download/v0.3.0/Meridian-Linux-0.3.0.run"},
            {"name":"Meridian-0.3.0-1.noarch.rpm","browser_download_url":"https://github.com/zphat/Meridian/releases/download/v0.3.0/Meridian-0.3.0-1.noarch.rpm"}]}
        with patch.object(meridian.urllib.request,'urlopen',return_value=FakeResponse(payload)), patch.object(meridian.sys,'platform','linux'):
            state=self.app.check_updates()
        self.assertEqual(state['state'],'available')
        self.assertTrue(state['installer_url'].endswith('.deb') or state['installer_url'].endswith('.rpm'))

    def test_windows_system_update_notification_once_per_version(self):
        from unittest.mock import MagicMock
        tray=MagicMock()
        self.app.tray_icon=tray
        with patch.object(meridian.sys, 'platform','win32'):
            self.app._notify_new_update('0.3.0')
            self.app._notify_new_update('0.3.0')
            self.app._notify_new_update('0.3.1')
        self.assertEqual(tray.notify.call_count,2)
        self.assertIn('0.3.1',tray.notify.call_args[0][0])

    def test_update_notification_only_once_per_version(self):
        # No notification without a desktop, and no repeat for the same release.
        with patch.object(meridian.sys,'platform','linux'), \
             patch.dict(meridian.os.environ,{'DISPLAY':':0'}), \
             patch.object(meridian.shutil,'which',return_value='/usr/bin/notify-send'), \
             patch.object(meridian.subprocess,'run') as run:
            self.app._notify_new_update('0.3.0')
            self.app._notify_new_update('0.3.0')
            self.app._notify_new_update('0.3.1')
            self.assertEqual(run.call_count,2)

    def test_fedora_update_prefers_rpm(self):
        payload={'tag_name':'v0.3.0',
                 'html_url':'https://github.com/zphat/Meridian/releases/tag/v0.3.0',
                 'assets':[{'name':'Meridian-0.3.0-1.noarch.rpm',
                            'browser_download_url':'https://github.com/zphat/Meridian/releases/download/v0.3.0/Meridian-0.3.0-1.noarch.rpm'}]}
        orig_read=Path.read_text
        def mock_read(path,*args,**kw):
            return 'NAME=Fedora\nID=fedora\n' if str(path)=='/etc/os-release' else orig_read(path,*args,**kw)
        with patch.object(meridian.sys,'platform','linux'), \
             patch.object(meridian.urllib.request,'urlopen',return_value=FakeResponse(payload)), \
             patch.object(meridian.Path,'read_text',autospec=True,side_effect=mock_read), \
             patch.object(meridian.os,'environ',dict(meridian.os.environ,DISPLAY='')):
            state=self.app.check_updates()
        self.assertEqual(state['state'],'available')
        self.assertTrue(state['installer_url'].endswith('noarch.rpm'))

    def test_unpublished_release_channel(self):
        url='https://api.github.com/repos/zphat/Meridian/releases/latest'
        err=urllib.error.HTTPError(url,404,'Not Found',{},None)
        with patch.object(meridian.urllib.request,'urlopen',side_effect=err):
            state=self.app.check_updates()
        self.assertEqual(state['state'],'private_or_unpublished')
        self.assertIsNone(state['installer_url'])
    def test_database_persists_between_app_instances(self):
        self.app.insert('notes',{'project':'longitude','title':'Remember project decision','body':'Keep editor local first'})
        self.app.close()
        reopened=meridian.Meridian(self.data.name,start_worker=False)
        try:
            self.assertEqual(reopened.snapshot()['notes'][0]['title'],'Remember project decision')
        finally:reopened.close()
        self.app.close=lambda:None

class AccessControlTests(unittest.TestCase):
    def setUp(self):
        self.data=tempfile.TemporaryDirectory()
        self.app=meridian.Meridian(self.data.name,start_worker=False)
        self.server=ThreadingHTTPServer(('127.0.0.1',0),meridian.Handler)
        self.server.meridian=self.app
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True)
        self.thread.start()
    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join(timeout=2)
        self.app.close();self.data.cleanup()
    def request(self,host):
        import http.client
        conn=http.client.HTTPConnection('127.0.0.1',self.server.server_port,timeout=5)
        try:
            conn.request('GET','/api/health',headers={'Host':host})
            resp=conn.getresponse();return resp.status,resp.read()
        finally:conn.close()
    def test_unapproved_host_rejected(self):
        status,_=self.request('attacker.example')
        self.assertEqual(status,403)
    def test_explicit_tailscale_host_allowed(self):
        with patch.object(meridian,'TRUSTED_HOSTS',{'meridian-pc.tailnet.ts.net'}):
            status,body=self.request('meridian-pc.tailnet.ts.net')
        self.assertEqual(status,200)
        self.assertEqual(json.loads(body)['app'],'Meridian')
    def test_tailscale_same_origin_can_edit_notes(self):
        import http.client
        host='meridian-pc.tailnet.ts.net'
        body=json.dumps({'project':'latitude','title':'Remote note','body':'Saved through Serve'})
        self.app.auth.configure('owner@example.com','a long test password','re_fake_testing_key_000')
        sent=[]
        self.app.auth.issue_link('owner@example.com','a long test password','https://'+host,lambda c,u:sent.append(u))
        session=self.app.auth.redeem(sent[0].split('token=')[1])
        with patch.object(meridian,'TRUSTED_HOSTS',{host}):
            conn=http.client.HTTPConnection('127.0.0.1',self.server.server_port,timeout=5)
            try:
                conn.request('POST','/api/notes',body,headers={'Host':host,'Origin':'https://'+host,'Content-Type':'application/json','Sec-Fetch-Site':'same-origin','Cookie':'meridian_session='+session})
                response=conn.getresponse()
                self.assertEqual(response.status,201,response.read().decode())
                response.read()
                self.assertEqual(self.app.snapshot()['notes'][0]['title'],'Remote note')
            finally:
                conn.close()
    def test_tailscale_cross_origin_cannot_edit_notes(self):
        import http.client
        host='meridian-pc.tailnet.ts.net'
        with patch.object(meridian,'TRUSTED_HOSTS',{host}):
            conn=http.client.HTTPConnection('127.0.0.1',self.server.server_port,timeout=5)
            try:
                conn.request('POST','/api/notes','{}',headers={'Host':host,'Origin':'https://different.ts.net','Content-Type':'application/json'})
                response=conn.getresponse()
                self.assertEqual(response.status,403)
                response.read()
            finally:conn.close()

    def test_localhost_kept(self):
        status,_=self.request('127.0.0.1:'+str(self.server.server_port))
        self.assertEqual(status,200)

if __name__=='__main__':unittest.main()
