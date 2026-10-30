"""Authentication tests use local fake email delivery: no real emails sent."""
import http.client,json,tempfile,threading,unittest
from pathlib import Path
from unittest.mock import patch
from http.server import ThreadingHTTPServer
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from meridian import Meridian,Handler
from auth import AuthError,AuthManager

class AuthUnitTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.app=Meridian(self.tmp.name,start_worker=False)
    def tearDown(self):self.app.close();self.tmp.cleanup()
    def test_config_never_stores_plain_password(self):
        self.app.auth.configure('owner@example.com','a long test secret','re_test_valid_token_12345')
        assert 'a long test secret' not in (Path(self.tmp.name)/'auth.json').read_text()
    def test_invalid_credentials_cannot_send_email(self):
        self.app.auth.configure('owner@example.com','a long test secret','re_test_valid_token_12345')
        sent=[]
        for email,password in [('wrong@example.com','a long test secret'),('owner@example.com','bad')]:
            with self.assertRaises(AuthError):
                self.app.auth.issue_link(email,password,'http://127.0.0.1:8765',lambda c,u:sent.append(u))
        self.assertEqual(sent,[])
    def test_single_use_magic_link_and_logout(self):
        self.app.auth.configure('owner@example.com','a long test secret','re_test_valid_token_12345')
        sent=[]
        self.app.auth.issue_link('owner@example.com','a long test secret','http://127.0.0.1:8765',lambda c,u:sent.append(u))
        token=sent[0].split('token=')[1]
        cookie=self.app.auth.redeem(token)
        self.assertTrue(self.app.auth.check_session('meridian_session='+cookie))
        with self.assertRaises(AuthError):self.app.auth.redeem(token)
        self.app.auth.logout('meridian_session='+cookie)
        self.assertFalse(self.app.auth.check_session('meridian_session='+cookie))
    def test_mail_throttle(self):
        self.app.auth.configure('owner@example.com','a long test secret','re_test_valid_token_12345')
        sent=[]
        self.app.auth.issue_link('owner@example.com','a long test secret','http://127.0.0.1:8765',lambda c,u:sent.append(u))
        with self.assertRaises(AuthError) as caught:
            self.app.auth.issue_link('owner@example.com','a long test secret','http://127.0.0.1:8765',lambda c,u:sent.append(u))
        self.assertEqual(caught.exception.status,429)
        self.assertEqual(len(sent),1)

class AuthHttpTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.app=Meridian(self.tmp.name,start_worker=False)
        self.server=ThreadingHTTPServer(('127.0.0.1',0),Handler);self.server.meridian=self.app
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join();self.app.close();self.tmp.cleanup()
    def req(self,method,path,payload=None,headers=None):
        conn=http.client.HTTPConnection('127.0.0.1',self.server.server_port,timeout=5)
        head={'Host':'127.0.0.1:'+str(self.server.server_port)}
        if payload is not None:head['Content-Type']='application/json';payload=json.dumps(payload)
        head.update(headers or {})
        conn.request(method,path,payload,headers=head)
        r=conn.getresponse();body=r.read();result=(r.status,dict(r.getheaders()),body);conn.close();return result
    def test_all_private_endpoints_locked(self):
        self.assertEqual(self.req('GET','/api/state')[0],401)
        self.assertEqual(self.req('GET','/api/backup')[0],401)
        self.assertIn(b'Sign in',self.req('GET','/')[2])
        self.assertEqual(self.req('GET','/api/health')[0],200)
    def test_local_setup_and_signin(self):
        sent=[]
        with patch.object(AuthManager,'_send_resend',staticmethod(lambda c,u:sent.append(u))):
            status,_,_=self.req('POST','/api/auth/setup',{'email':'owner@example.com','password':'a long test secret','resend_key':'re_test_valid_token_12345'})
        self.assertEqual(status,201)
        self.assertEqual(len(sent),1)
        token=sent[0].split('token=')[1]
        status,headers,_=self.req('GET','/auth/verify?token='+token)
        self.assertEqual(status,303)
        self.assertIn('HttpOnly',headers['Set-Cookie'])
        cookie=headers['Set-Cookie'].split(';')[0]
        self.assertEqual(self.req('GET','/api/state',headers={'Cookie':cookie})[0],200)
        self.assertEqual(self.req('GET','/api/state')[0],401)
        self.assertEqual(self.req('POST','/api/auth/logout',{},headers={'Cookie':cookie})[0],204)
        self.assertEqual(self.req('GET','/api/state',headers={'Cookie':cookie})[0],401)
    def test_setup_rollback_if_mail_fails(self):
        def failing(c,u):raise AuthError('email unavailable',502)
        with patch.object(AuthManager,'_send_resend',staticmethod(failing)):
            status,_,_=self.req('POST','/api/auth/setup',{'email':'owner@example.com','password':'a long test secret','resend_key':'re_test_valid_token_12345'})
        self.assertEqual(status,502)
        self.assertFalse(self.app.auth.configured())

if __name__=='__main__':unittest.main()
