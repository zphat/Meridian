"""Read-only GitHub requests with persistent caching and shared rate backoff."""
import datetime as dt
import hashlib
import json
import os
import re
import tempfile
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path


class GitHubError(RuntimeError):
    def __init__(self, message, status=0):
        super().__init__(message)
        self.status=status


def stamp(epoch):
    return dt.datetime.fromtimestamp(epoch,dt.timezone.utc).isoformat() if epoch else None


class GitHubAccess:
    def __init__(self, data_dir, conn, lock, user_agent):
        self.path=Path(data_dir)/'github-credentials.json'
        self.conn,self.lock,self.user_agent=conn,lock,user_agent
        self.network_lock=threading.RLock()
        self._saved_token=''
        try:self._saved_token=json.loads(self.path.read_text()).get('token','')
        except (OSError,ValueError,AttributeError):pass
        with lock,conn:
            conn.executescript('''
            CREATE TABLE IF NOT EXISTS github_http_cache(path TEXT PRIMARY KEY,etag TEXT,json TEXT NOT NULL,validated_at REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS github_request_state(id INTEGER PRIMARY KEY CHECK(id=1),json TEXT NOT NULL);
            ''')
            row=conn.execute('SELECT json FROM github_request_state WHERE id=1').fetchone()
            try:self.state=json.loads(row[0]) if row else {}
            except ValueError:self.state={}
        if self.state.get('identity')!=self._identity():self._reset()

    def token(self):
        return os.environ.get('MERIDIAN_GITHUB_TOKEN','').strip() or self._saved_token

    def _identity(self):
        return hashlib.sha256(self.token().encode()).hexdigest()[:16]

    def _persist(self):
        with self.lock,self.conn:
            self.conn.execute('INSERT OR REPLACE INTO github_request_state VALUES(1,?)',(json.dumps(self.state),))

    def _reset(self):
        self.state={'identity':self._identity(),'pause_until':0,'reason':''}
        self._persist()

    def status(self):
        with self.lock:
            s=dict(self.state)
            token=self.token()
        paused=s.get('pause_until',0)>time.time()
        return {'authenticated':bool(token),'source':'environment' if os.environ.get('MERIDIAN_GITHUB_TOKEN','').strip() else 'local' if token else 'public',
                'state':s.get('reason') if paused else 'ready', 'remaining':s.get('remaining'), 'limit':s.get('limit'),
                'reset_at':stamp(s.get('reset_at')), 'retry_at':stamp(s.get('pause_until')) if paused else None,
                'last_checked':stamp(s.get('last_checked')), 'saved_token':bool(self._saved_token)}

    def poll_seconds(self, mode):
        return (3600 if mode=='quiet' else 1800) if self.token() else (5400 if mode=='quiet' else 3600)

    def _headers(self, response_headers):
        headers=response_headers or {}
        for header,key in [('X-RateLimit-Remaining','remaining'),('X-RateLimit-Limit','limit'),('X-RateLimit-Reset','reset_at')]:
            try:self.state[key]=int(headers.get(header))
            except (ValueError,TypeError):pass
        self.state['last_checked']=time.time()
        self._persist()

    @staticmethod
    def ttl(path):
        if '/actions/runs?' in path or '/commits?' in path:return 120
        if '/releases' in path or '/issues?' in path:return 900
        return 21600

    def validated_at(self,path):
        with self.lock:
            row=self.conn.execute('SELECT validated_at FROM github_http_cache WHERE path=?',(path,)).fetchone()
        return row[0] if row else None

    def get(self,path,force=False):
        # Release checks and project refreshes share the same queue and budget.
        with self.network_lock:
            if self.state.get('identity')!=self._identity():self._reset()
            with self.lock:
                row=self.conn.execute('SELECT * FROM github_http_cache WHERE path=?',(path,)).fetchone()
                cached=dict(row) if row else None
            now=time.time()
            if cached and not force and now-cached['validated_at']<self.ttl(path):return json.loads(cached['json'])
            if now<self.state.get('pause_until',0):
                raise GitHubError('GitHub requests are paused. See GitHub access in Settings for the retry time.')
            headers={'Accept':'application/vnd.github+json','User-Agent':self.user_agent,'X-GitHub-Api-Version':'2022-11-28'}
            if self.token():headers['Authorization']='Bearer '+self.token()
            if cached and cached['etag']:headers['If-None-Match']=cached['etag']
            request=urllib.request.Request('https://api.github.com'+path,headers=headers)
            try:
                with urllib.request.urlopen(request,timeout=13) as response:
                    payload=response.read(1400000)
                    result=json.loads(payload.decode('utf-8'))
                    response_headers=getattr(response,'headers',{})
                    self._headers(response_headers)
                    etag=response_headers.get('ETag')
            except urllib.error.HTTPError as error:
                self._headers(error.headers)
                if error.code==304 and cached:
                    result=json.loads(cached['json']);etag=cached['etag']
                else:
                    self._failure(error)
            except (urllib.error.URLError,TimeoutError,OSError):
                raise GitHubError('Cannot reach GitHub. Saved project data is still available.') from None
            with self.lock,self.conn:
                self.conn.execute('INSERT OR REPLACE INTO github_http_cache VALUES(?,?,?,?)',(path,etag,json.dumps(result),time.time()))
                self.conn.execute('DELETE FROM github_http_cache WHERE validated_at<?',(time.time()-30*86400,))
            self.state.update(pause_until=0,reason='',secondary_attempts=0)
            if self.state.get('remaining')==0 and self.state.get('reset_at',0)>time.time():
                self.state.update(pause_until=self.state['reset_at']+2,reason='rate_limited')
            self._persist()
            return result

    def _failure(self,error):
        headers=error.headers or {}
        try:message=json.loads(error.read(3000)).get('message','').lower()
        except (ValueError,AttributeError,TypeError):message=''
        if error.code in (403,429) and (headers.get('X-RateLimit-Remaining')=='0' or error.code==429 or 'rate limit' in message):
            attempts=min(self.state.get('secondary_attempts',0)+1,7)
            wait=min(3600,60*2**(attempts-1))
            try:wait=max(wait,float(headers.get('Retry-After',0)))
            except (TypeError,ValueError):pass
            until=time.time()+wait
            if headers.get('X-RateLimit-Remaining')=='0':
                try:until=max(until,float(headers.get('X-RateLimit-Reset'))+2)
                except (TypeError,ValueError):until=max(until,time.time()+3600)
            self.state.update(pause_until=until,reason='rate_limited',secondary_attempts=attempts)
            self._persist()
            raise GitHubError('GitHub request allowance reached. Saved data remains available; requests resume automatically.',error.code) from None
        if error.code==401:
            self.state.update(pause_until=time.time()+300,reason='invalid_token');self._persist()
            raise GitHubError('GitHub rejected the saved token. Replace or remove it in Settings.',401) from None
        if error.code==403:raise GitHubError('GitHub denied read access. Check the token permissions in Settings.',403) from None
        if error.code==404:raise GitHubError('GitHub could not find this public resource.',404) from None
        raise GitHubError('GitHub returned HTTP '+str(error.code)+'. Saved project data remains available.',error.code) from None

    def save_token(self, token):
        if os.environ.get('MERIDIAN_GITHUB_TOKEN','').strip():
            raise ValueError('GitHub access is configured by MERIDIAN_GITHUB_TOKEN. Update that environment variable first.')
        if not isinstance(token,str) or not re.fullmatch(r'[A-Za-z0-9_]{20,255}',token.strip()):
            raise ValueError('Enter a valid GitHub personal access token.')
        token=token.strip()
        with self.network_lock:
            # Test before replacing a working credential. Never return the token.
            headers={'Accept':'application/vnd.github+json','User-Agent':self.user_agent,'Authorization':'Bearer '+token}
            try:
                request=urllib.request.Request('https://api.github.com/rate_limit',headers=headers)
                with urllib.request.urlopen(request,timeout=13) as response:result=json.loads(response.read(50000))
                core=result['resources']['core']
                if not isinstance(core,dict) or not isinstance(core.get('limit'),int):raise ValueError('Invalid rate-limit response')
            except urllib.error.HTTPError:
                raise ValueError('GitHub did not accept this token. Check its value and expiration; the existing setting was kept.') from None
            except (urllib.error.URLError,OSError,ValueError,KeyError,TypeError):
                raise ValueError('Could not validate GitHub access. Try again when GitHub is reachable; the existing setting was kept.') from None
            fd,temp=tempfile.mkstemp(prefix='github-credentials.',suffix='.pending',dir=self.path.parent)
            try:
                with os.fdopen(fd,'w',encoding='utf-8') as out:json.dump({'token':token},out)
                os.replace(temp,self.path)
                try:os.chmod(self.path,0o600)
                except OSError:pass
            finally:
                Path(temp).unlink(missing_ok=True)
            self._saved_token=token;self._reset()
            self.state.update(remaining=core.get('remaining'),limit=core.get('limit'),reset_at=core.get('reset'),last_checked=time.time())
            self._persist()

    def remove_token(self):
        with self.network_lock:
            self.path.unlink(missing_ok=True);self._saved_token='';self._reset()
