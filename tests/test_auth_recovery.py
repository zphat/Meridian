"""Regression tests for owner lockouts and safe email-provider recovery."""
import io
import json
import tempfile
import unittest
import urllib.error
from unittest.mock import patch
from auth import AuthError, AuthManager
from meridian import Meridian

class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.app=Meridian(self.temp.name,start_worker=False)
        self.auth=self.app.auth
        self.auth.configure('owner@example.test','owner-password','re_old_example_key')
    def tearDown(self):
        self.app.close();self.temp.cleanup()
    def request(self,**kw):
        return self.auth.issue_link('owner@example.test','owner-password','http://127.0.0.1:8765',challenge='R'*43,**kw)
    def test_cooldown_clicks_do_not_become_bad_password_attempts(self):
        self.request(sender=lambda c,u:'receipt')
        for _ in range(15):
            with self.assertRaises(AuthError) as error:self.request(sender=lambda c,u:self.fail('must not send'))
            self.assertEqual(error.exception.status,429)
            self.assertIn('recently',str(error.exception))
        count=self.app.conn.execute("SELECT COUNT(*) FROM auth_attempts WHERE category='attempt'").fetchone()[0]
        self.assertEqual(count,0)
        with self.app.conn:self.app.conn.execute("UPDATE auth_attempts SET at=at-61 WHERE category='mail'")
        self.assertTrue(self.request(sender=lambda c,u:'receipt2')['ok'])
    def test_provider_failure_does_not_consume_allowances_or_replace_key(self):
        old=self.auth.path.read_bytes()
        def fail(c,u):raise AuthError('provider refused',502)
        for _ in range(13):
            with self.assertRaises(AuthError):self.request(sender=fail,resend_api_key='re_replacement_key')
        self.assertEqual(self.auth.path.read_bytes(),old)
        self.assertEqual(self.app.conn.execute('SELECT COUNT(*) FROM auth_attempts').fetchone()[0],0)
    def test_successful_key_replacement_still_requires_email_code(self):
        sent=[]
        def sender(c,u):sent.append(c);return 'email-receipt'
        result=self.request(sender=sender,resend_api_key='re_replacement_key')
        self.assertEqual(result['email_id'],'email-receipt')
        self.assertEqual(self.auth._get_config()['resend_key'],'re_replacement_key')
        self.assertFalse(self.auth.check_session(''))
        cookie=self.auth.confirm_code('R'*43,sent[0]['_one_time_code'])
        self.assertTrue(self.auth.check_session('meridian_session='+cookie))
    def test_provider_errors_are_actionable_and_do_not_echo_secrets(self):
        cases=[(403,'You can only send testing emails to your own email address','test sender'),
               (401,'API key is invalid','rejected the API key'),(403,'invalid permission','denied sending'),
               (429,'Too many requests','rate-limiting'),(503,'down','temporarily unavailable')]
        cfg={'from':'Meridian <onboarding@resend.dev>','email':'owner@example.test','resend_key':'re_never_echo_this','_one_time_code':'12345678'}
        for status,message,expected in cases:
            raw=json.dumps({'message':message+' re_never_echo_this'}).encode()
            error=urllib.error.HTTPError('https://api.resend.com/emails',status,'failure',{},io.BytesIO(raw))
            with patch('urllib.request.urlopen',side_effect=error),self.assertRaises(AuthError) as got:
                self.auth._send_resend(cfg,'http://127.0.0.1:8765/auth/verify?token='+'X'*43)
            self.assertIn(expected,str(got.exception));self.assertNotIn('re_never_echo_this',str(got.exception))
    def test_expired_code_cannot_unlock(self):
        sent=[];self.request(sender=lambda c,u:sent.append(c['_one_time_code']))
        with self.app.conn:self.app.conn.execute('UPDATE auth_codes SET expires=0')
        with self.assertRaises(AuthError):self.auth.confirm_code('R'*43,sent[0])
