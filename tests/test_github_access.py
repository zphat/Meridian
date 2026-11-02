import io
import json
import tempfile
import time
import unittest
import urllib.error
from unittest.mock import patch
from meridian import Meridian
from github_access import GitHubError

TOKEN='github_pat_'+'fixture_'*5
class Response:
    def __init__(self,data,headers=None):self.data=json.dumps(data).encode();self.headers=headers or {}
    def __enter__(self):return self
    def __exit__(self,*args):pass
    def read(self,n=-1):return self.data[:n] if n>=0 else self.data

def error(code,headers=None,message='Request rejected'):
    return urllib.error.HTTPError('https://api.github.com/repos/example/test',code,'Error',headers or {},io.BytesIO(json.dumps({'message':message}).encode()))

class GitHubAccessTests(unittest.TestCase):
    def setUp(self):
        self.env=patch.dict('os.environ',{'MERIDIAN_GITHUB_TOKEN':''});self.env.start()
        self.temp=tempfile.TemporaryDirectory();self.app=Meridian(self.temp.name,start_worker=False)
        self.path='/repos/zphat/Latitude/commits?per_page=15'
    def tearDown(self):self.app.close();self.temp.cleanup();self.env.stop()
    def restart(self):self.app.close();self.app=Meridian(self.temp.name,start_worker=False)
    def test_cached_requests_survive_restart_without_spending_budget(self):
        with patch('github_access.urllib.request.urlopen',return_value=Response([{'sha':'first'}],{'ETag':'"v1"'})) as request:
            self.app._github_get(self.path);self.restart()
            self.assertEqual(self.app._github_get(self.path),[{'sha':'first'}]);self.assertEqual(request.call_count,1)
    def test_fresh_check_revalidates_etag_and_timestamp(self):
        with patch('github_access.urllib.request.urlopen',return_value=Response([{'sha':'first'}],{'ETag':'"v1"'})):
            self.app._github_get(self.path)
        before=self.app.github_access.validated_at(self.path)
        with patch('github_access.urllib.request.urlopen',side_effect=error(304)) as request:
            result=self.app._github_get(self.path,force=True)
        self.assertEqual(result,[{'sha':'first'}])
        self.assertEqual(request.call_args.args[0].get_header('If-none-match'),'"v1"')
        self.assertGreaterEqual(self.app.github_access.validated_at(self.path),before)
    def test_rate_pause_is_shared_persistent_and_sanitized(self):
        reset=int(time.time()+600)
        with patch('github_access.urllib.request.urlopen',side_effect=error(403,{'X-RateLimit-Remaining':'0','X-RateLimit-Reset':str(reset)},'API rate limit exceeded for 192.0.2.1')) as request:
            with self.assertRaises(GitHubError) as failure:self.app._github_get(self.path)
            self.assertNotIn('192.0.2.1',str(failure.exception))
            self.restart()
            with self.assertRaises(GitHubError):self.app._github_get('/repos/zphat/Sundial')
            self.app.check_updates()
            self.assertEqual(request.call_count,1)
        self.assertEqual(self.app.snapshot()['github_access']['state'],'rate_limited')
    def test_secondary_retry_after_is_honored(self):
        with patch('github_access.urllib.request.urlopen',side_effect=error(403,{'Retry-After':'700'},'Secondary rate limit exceeded')):
            with self.assertRaises(GitHubError):self.app._github_get(self.path)
        self.assertGreater(self.app.github_access.state['pause_until'],time.time()+690)
    def test_permission_error_is_not_misreported_as_rate_limit(self):
        with patch('github_access.urllib.request.urlopen',side_effect=error(403)):
            with self.assertRaisesRegex(GitHubError,'permissions'):self.app._github_get(self.path)
        self.assertEqual(self.app.github_access.status()['state'],'ready')
    def test_validated_token_is_private_persistent_and_removable(self):
        data={'resources':{'core':{'limit':5000,'remaining':4999,'reset':int(time.time()+300)}}}
        with patch('github_access.urllib.request.urlopen',return_value=Response(data)) as request:
            self.app.github_access.save_token(TOKEN)
            self.assertEqual(request.call_args.args[0].get_header('Authorization'),'Bearer '+TOKEN)
        self.restart()
        self.assertTrue(self.app.snapshot()['github_access']['authenticated'])
        self.assertNotIn(TOKEN,json.dumps(self.app.snapshot()))
        self.assertNotIn(TOKEN,json.dumps(self.app.backup()))
        self.app.github_access.remove_token();self.restart()
        self.assertFalse(self.app.github_access.status()['authenticated'])
    def test_failed_validation_keeps_existing_token(self):
        with patch('github_access.urllib.request.urlopen',return_value=Response({'resources':{'core':{'limit':5000}}})):
            self.app.github_access.save_token(TOKEN)
        with patch('github_access.urllib.request.urlopen',side_effect=error(401)):
            with self.assertRaises(ValueError):self.app.github_access.save_token('github_pat_'+'new_'*10)
        self.assertEqual(self.app.github_access.token(),TOKEN)
    def test_invalid_token_pauses_without_echoing_provider_body(self):
        with patch('github_access.urllib.request.urlopen',side_effect=error(401,message=TOKEN)):
            with self.assertRaises(GitHubError) as failure:self.app._github_get(self.path)
        self.assertNotIn(TOKEN,str(failure.exception));self.assertEqual(self.app.github_access.status()['state'],'invalid_token')
    def test_public_background_schedule_leaves_room_for_manual_checks(self):
        self.assertEqual(self.app.github_access.poll_seconds('balanced'),3600)
        self.assertEqual(self.app.github_access.poll_seconds('quiet'),5400)
        with patch.dict('os.environ',{'MERIDIAN_GITHUB_TOKEN':TOKEN}):
            self.assertEqual(self.app.github_access.poll_seconds('balanced'),1800)
            self.assertEqual(self.app.github_access.status()['source'],'environment')
            with self.assertRaises(ValueError):self.app.github_access.save_token(TOKEN)

if __name__=='__main__':unittest.main()
