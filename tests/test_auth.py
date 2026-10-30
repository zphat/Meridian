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
    def test_seven_character_password(self):
        self.app.auth.configure('owner@example.com','abc123!','re_test_valid_token_12345')
        sent=[]
        self.app.auth.issue_link('owner@example.com','abc123!','http://127.0.0.1:8765',lambda c,u:sent.append(u))
        self.assertEqual(len(sent),1)
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
    def test_failed_attempts_persist_and_are_rate_limited(self):
        self.app.auth.configure('owner@example.com','a long test secret','re_test_valid_token_12345')
        for i in range(12):
            with self.assertRaises(AuthError) as caught:
                self.app.auth.issue_link('owner@example.com','incorrect','http://127.0.0.1:8765',lambda c,u:None)
            self.assertEqual(caught.exception.status,401)
        with self.assertRaises(AuthError) as locked:
            self.app.auth.issue_link('owner@example.com','a long test secret','http://127.0.0.1:8765',lambda c,u:None)
        self.assertEqual(locked.exception.status,429)
        self.assertEqual(self.app.conn.execute("SELECT COUNT(*) FROM auth_attempts WHERE category='attempt'").fetchone()[0],12)
    def test_email_contains_desktop_and_explicit_browser_fallback(self):
        import urllib.request
        payload=[]
        class FakeHTTP:
            status=200
            def __enter__(self):return self
            def __exit__(self,*args):return False
        def fake_send(request,timeout=None):
            payload.append(json.loads(request.data))
            return FakeHTTP()
        with patch.object(urllib.request,'urlopen',side_effect=fake_send):
            AuthManager._send_resend(
                {'from':'Meridian <onboarding@resend.dev>','email':'owner@example.com','resend_key':'re_test_valid_token_12345'},
                'http://127.0.0.1:8765/auth/verify?token='+('A'*43)
            )
        self.assertEqual(len(payload),1)
        self.assertIn('meridian://approve?token=',payload[0]['text'])
        self.assertIn('http://127.0.0.1:8765/auth/verify?token=',payload[0]['text'])
        self.assertNotIn('<a href=',payload[0]['html'])
        self.assertIn('No link needed',payload[0]['html'])

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
    def test_magic_link_handoff_unlocks_waiting_window(self):
        self.app.auth.configure('owner@example.com','a long test secret','re_test_valid_token_12345')
        sent=[];challenge='B'*43
        with patch.object(AuthManager,'_send_resend',staticmethod(lambda c,u:sent.append(u))):
            status,_,_=self.req('POST','/api/auth/request',{'email':'owner@example.com','password':'a long test secret','challenge':challenge})
        self.assertEqual(status,200)
        self.assertIn(b'false',self.req('POST','/api/auth/handoff',{'challenge':challenge})[2])
        self.assertIn(b'false',self.req('POST','/api/auth/handoff',{'challenge':'C'*43})[2])
        self.assertEqual(self.req('POST','/api/auth/handoff',{'challenge':'short'})[0],400)
        token=sent[0].split('token=')[1]
        status,headers,_=self.req('GET','/auth/verify?token='+token)
        self.assertEqual(status,303)
        self.assertEqual(headers['Location'],'/auth/complete')
        # The email-opening browser must not be issued an authenticated session.
        self.assertNotIn('Set-Cookie',headers)
        self.assertEqual(self.req('GET','/api/state')[0],401)
        self.assertIn(b'Email link confirmed',self.req('GET','/auth/complete')[2])
        status,headers,payload=self.req('POST','/api/auth/handoff',{'challenge':challenge})
        self.assertEqual(status,200)
        self.assertTrue(json.loads(payload)['authenticated'])
        self.assertIn('HttpOnly',headers['Set-Cookie'])
        desktop_cookie=headers['Set-Cookie'].split(';')[0]
        self.assertEqual(self.req('GET','/api/state',headers={'Cookie':desktop_cookie})[0],200)
        self.assertIn(b'false',self.req('POST','/api/auth/handoff',{'challenge':challenge})[2])
        self.assertEqual(self.req('GET','/api/state')[0],401)
        stored=[r[0] for r in self.app.conn.execute('SELECT challenge_hash FROM auth_handoff')]
        self.assertNotIn(challenge,stored)

    def test_otp_confirm_then_replay_and_wrong_code(self):
        self.app.auth.configure('owner@example.com','test-password-123!','re_test_valid_token_12345')
        captured=[];challenge='Y'*43
        with patch.object(AuthManager,'_send_resend',staticmethod(lambda cfg,url:captured.append(cfg['_one_time_code']))):
            status,_,_=self.req('POST','/api/auth/request',{'email':'owner@example.com','password':'test-password-123!','challenge':challenge})
        self.assertEqual(status,200)
        code=captured[0]
        self.assertEqual(len(code),8)
        self.assertTrue(code.isdecimal())
        wrong='00000000' if code!='00000000' else '11111111'
        self.assertEqual(self.req('POST','/api/auth/confirm-code',{'challenge':challenge,'code':wrong})[0],401)
        status,headers,_=self.req('POST','/api/auth/confirm-code',{'challenge':challenge,'code':code})
        self.assertEqual(status,200)
        cookie=headers['Set-Cookie'].split(';')[0]
        self.assertEqual(self.req('GET','/api/state',headers={'Cookie':cookie})[0],200)
        self.assertEqual(self.req('GET','/api/state')[0],401)
        self.assertEqual(self.req('POST','/api/auth/confirm-code',{'challenge':challenge,'code':code})[0],401)

    def test_setup_rollback_if_mail_fails(self):
        def failing(c,u):raise AuthError('email unavailable',502)
        with patch.object(AuthManager,'_send_resend',staticmethod(failing)):
            status,_,_=self.req('POST','/api/auth/setup',{'email':'owner@example.com','password':'a long test secret','resend_key':'re_test_valid_token_12345'})
        self.assertEqual(status,502)
        self.assertFalse(self.app.auth.configured())

if __name__=='__main__':unittest.main()
)
        status,_,_=self.req('POST','/api/auth/confirm-code',{'challenge':challenge,'code':'a'*8})
        self.assertEqual(status,400)
        wrong='00000000' if code!='00000000' else '11111111'
        status,_,_=self.req('POST','/api/auth/confirm-code',{'challenge':challenge,'code':wrong})
        self.assertEqual(status,401)
        status,headers,result=self.req('POST','/api/auth/confirm-code',{'challenge':challenge,'code':code})
        self.assertEqual(status,200)
        cookie=headers['Set-Cookie'].split(';')[0]
        self.assertEqual(self.req('GET','/api/state',headers={'Cookie':cookie})[0],200)
        self.assertEqual(self.req('GET','/api/state')[0],401)
        self.assertEqual(self.req('POST','/api/auth/confirm-code',{'challenge':challenge,'code':code})[0],401)
        self.assertEqual(self.req('GET','/auth/verify?token=no-longer-valid')[0],200)
        self.assertEqual(self.req('POST','/api/auth/confirm-code',{'challenge':'Z'*43,'code':code})[0],401)
    def test_otp_attempts_lock_after_five_failures(self):
        self.app.auth.configure('owner@example.com','test-password-123!','re_test_valid_token_12345')
        captured=[];challenge='C'*43
        with patch.object(AuthManager,'_send_resend',staticmethod(lambda cfg,url:captured.append(cfg['_one_time_code']))):
            self.req('POST','/api/auth/request',{'email':'owner@example.com','password':'test-password-123!','challenge':challenge})
        wrong='00000000' if captured[0]!='00000000' else '11111111'
        for _ in range(5):
            self.assertEqual(self.req('POST','/api/auth/confirm-code',{'challenge':challenge,'code':wrong})[0],401)
        self.assertEqual(self.req('POST','/api/auth/confirm-code',{'challenge':challenge,'code':captured[0]})[0],429)

    def test_setup_rollback_if_mail_fails(self):
        def failing(c,u):raise AuthError('email unavailable',502)
        with patch.object(AuthManager,'_send_resend',staticmethod(failing)):
            status,_,_=self.req('POST','/api/auth/setup',{'email':'owner@example.com','password':'a long test secret','resend_key':'re_test_valid_token_12345'})
        self.assertEqual(status,502)
        self.assertFalse(self.app.auth.configured())

if __name__=='__main__':unittest.main()
