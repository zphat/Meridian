"""Private single-owner email magic links. Never commit owner config or keys."""
import base64, hashlib, hmac, json, os, re, secrets, time, urllib.request, urllib.error, urllib.parse
from html import escape
from pathlib import Path
from http.cookies import SimpleCookie

class AuthError(Exception):
    def __init__(self, message, status=400):
        super().__init__(message); self.status=status

class AuthManager:
    def __init__(self,data_dir,connection,lock):
        self.path=Path(data_dir)/'auth.json'; self.conn=connection; self.lock=lock
        with self.lock,self.conn:
            self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS auth_magic(token_hash TEXT PRIMARY KEY,expires INTEGER NOT NULL,used INTEGER NOT NULL DEFAULT 0);
            CREATE TABLE IF NOT EXISTS auth_sessions(token_hash TEXT PRIMARY KEY,expires INTEGER NOT NULL);
            CREATE TABLE IF NOT EXISTS auth_handoff(challenge_hash TEXT PRIMARY KEY,magic_hash TEXT UNIQUE NOT NULL,expires INTEGER NOT NULL,approved INTEGER NOT NULL DEFAULT 0);
            CREATE TABLE IF NOT EXISTS auth_codes(challenge_hash TEXT PRIMARY KEY,code_hash TEXT NOT NULL,expires INTEGER NOT NULL,attempts INTEGER NOT NULL DEFAULT 0);
            CREATE TABLE IF NOT EXISTS auth_attempts(id INTEGER PRIMARY KEY,at INTEGER NOT NULL,category TEXT NOT NULL);
            """)
    def configured(self): return self.path.is_file()
    def _get_config(self): return json.loads(self.path.read_text(encoding='utf-8')) if self.configured() else None
    @staticmethod
    def _hash(token):return hashlib.sha256(token.encode('ascii')).hexdigest()
    def configure(self,email,password,resend_api_key):
        with self.lock:
            if self.configured():raise AuthError('Meridian authentication is already configured',409)
            if not all(isinstance(x,str) for x in (email,password,resend_api_key)):raise AuthError('All setup fields are required')
            email=email.strip().lower();resend_api_key=resend_api_key.strip()
            if not email or len(email)>254 or email.count('@')!=1:raise AuthError('Enter a valid authorized email')
            if not 7<=len(password)<=200:raise AuthError('Password must be at least 7 characters')
            if not resend_api_key.startswith('re_') or len(resend_api_key)<12:raise AuthError('Enter a valid Resend API key')
            salt=secrets.token_bytes(16)
            digest=hashlib.scrypt(password.encode(),salt=salt,n=16384,r=8,p=1,dklen=32)
            config={'email':email,'salt':base64.b64encode(salt).decode(),
                    'password_hash':base64.b64encode(digest).decode(),
                    'resend_key':resend_api_key,'from':'Meridian <onboarding@resend.dev>'}
            temp=self.path.with_name('auth.json.pending')
            fd=os.open(str(temp),os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
            try:
                with os.fdopen(fd,'w',encoding='utf-8') as out:json.dump(config,out)
                os.replace(str(temp),str(self.path))
                try:os.chmod(self.path,0o600)
                except OSError:pass
            except Exception:
                try:temp.unlink(missing_ok=True)
                except OSError:pass
                raise
    def rollback_setup(self):
        with self.lock,self.conn:
            self.path.unlink(missing_ok=True)
            self.conn.execute('DELETE FROM auth_magic')
            self.conn.execute('DELETE FROM auth_codes')
            self.conn.execute('DELETE FROM auth_handoff')
            self.conn.execute('DELETE FROM auth_attempts')
    def check_session(self,cookie_header):
        if not self.configured() or not cookie_header:return False
        try:
            c=SimpleCookie();c.load(cookie_header);m=c.get('meridian_session')
            if not m or not m.value or len(m.value)>256:return False
            token_hash=self._hash(m.value)
        except (ValueError,KeyError,TypeError):return False
        with self.lock:
            row=self.conn.execute('SELECT expires FROM auth_sessions WHERE token_hash=?',(token_hash,)).fetchone()
            return bool(row and row[0]>int(time.time()))
    def _recent(self,category,seconds):
        return self.conn.execute('SELECT COUNT(*) FROM auth_attempts WHERE category=? AND at>=?',(category,int(time.time())-seconds)).fetchone()[0]
    def issue_link(self,email,password,origin_url,sender=None,challenge=None):
        if not self.configured():raise AuthError('Set up Meridian authentication first',503)
        if not isinstance(email,str) or not isinstance(password,str):raise AuthError('Invalid sign-in details',401)
        cfg=self._get_config()
        with self.lock:
            if self._recent('attempt',900)>=12:raise AuthError('Too many attempts; try again later',429)
            self.conn.execute('INSERT INTO auth_attempts(at,category) VALUES(?,?)',(int(time.time()),'attempt'))
            # Persist failed attempts BEFORE verifying credentials. Otherwise an
            # AuthError inside a connection context rolls back the rate limit.
            self.conn.commit()
            salt=base64.b64decode(cfg['salt']);expected=base64.b64decode(cfg['password_hash'])
            result=hashlib.scrypt(password.encode(),salt=salt,n=16384,r=8,p=1,dklen=32)
            if not hmac.compare_digest(result,expected) or not hmac.compare_digest(email.strip().lower(),cfg['email']):
                raise AuthError('Email or password not recognized',401)
            if self._recent('mail',86400)>=3 or self._recent('mail',300)>0:
                raise AuthError('A sign-in link was recently sent; wait before requesting another',429)
            # Challenge belongs only to the waiting app window; never include it in the email.
            if challenge is not None and (not isinstance(challenge,str) or not re.fullmatch(r'[A-Za-z0-9_-]{43}',challenge)):
                raise AuthError('Invalid desktop sign-in challenge',400)
            token=secrets.token_urlsafe(32);url=origin_url.rstrip('/')+'/auth/verify?token='+token
            code=f'{secrets.randbelow(100000000):08d}' if challenge else None
            deliver=sender or self._send_resend
            deliver({**cfg,'_one_time_code':code},url)
            expires=int(time.time())+600
            self.conn.execute('INSERT INTO auth_magic(token_hash,expires) VALUES(?,?)',(self._hash(token),expires))
            if challenge is not None:
                challenge_hash=self._hash(challenge)
                self.conn.execute('INSERT OR REPLACE INTO auth_handoff(challenge_hash,magic_hash,expires,approved) VALUES(?,?,?,0)',(challenge_hash,self._hash(token),expires))
                self.conn.execute('INSERT OR REPLACE INTO auth_codes(challenge_hash,code_hash,expires,attempts) VALUES(?,?,?,0)',(challenge_hash,self._hash(challenge+':'+code),expires))
            self.conn.execute('INSERT INTO auth_attempts(at,category) VALUES(?,?)',(int(time.time()),'mail'))
            self.conn.commit()
            return {'ok':True,'message':'A one-time sign-in link was sent to the authorized inbox.'}
    @staticmethod
    def _send_resend(cfg,url):
        # Auth emails must not contain clickable HTML links: provider click
        # tracking can rewrite them through blocked third-party redirects.
        code=cfg.get('_one_time_code')
        token=urllib.parse.parse_qs(urllib.parse.urlsplit(url).query).get('token',[''])[0]
        desktop_url='meridian://approve?token='+urllib.parse.quote(token,safe='')
        content=(
            ('Your Meridian verification code:\n\n'+code+'\n\n' if code else '')+
            'Enter the code into the Meridian window that requested it.\n'
            'The code expires in 10 minutes and works only once.\n\n'
            'Optional desktop sign-in link (may be blocked by some email clients):\n'+desktop_url+'\n\n'
            'Browser fallback (same computer only):\n'+url+'\n\n'
            'You do not need to click any link to enter the code.\n'
            'If you did not request this, ignore the email.'
        )
        html=(
            '<!doctype html><html><body style="font-family:Arial,sans-serif;color:#18231b;line-height:1.6">'
            '<h2>Meridian sign-in</h2><p>Enter this code in your open Meridian window:</p>'
            '<p style="font-size:32px;letter-spacing:.2em;font-weight:700">'+escape(code or '')+'</p>'
            '<p>Expires in 10 minutes. Works once. No link needed.</p>'
            '<p style="font-size:12px">If you did not request this, ignore the email.</p>'
            '</body></html>'
        )
        data=json.dumps({'from':cfg['from'],'to':[cfg['email']],
            'subject':'Your Meridian sign-in code','text':content,'html':html}).encode()
        req=urllib.request.Request('https://api.resend.com/emails',data=data,headers={
            'Authorization':'Bearer '+cfg['resend_key'],'Content-Type':'application/json',
            'User-Agent':'Meridian/0.2.12'},method='POST')
        try:
            with urllib.request.urlopen(req,timeout=12) as response:
                if response.status not in (200,201,202):raise AuthError('Email service unavailable',502)
        except (urllib.error.URLError,TimeoutError) as e:
            raise AuthError('Email delivery failed. Check the Resend account and API key.',502) from e

    def confirm_code(self,challenge,code):
        """Redeem a one-time code only into its original waiting app window."""
        if not isinstance(challenge,str) or not re.fullmatch(r'[A-Za-z0-9_-]{43}',challenge):
            raise AuthError('Invalid sign-in request',400)
        if not isinstance(code,str) or not re.fullmatch(r'[0-9]{8}',code):
            raise AuthError('Enter the eight-digit code from your email',400)
        key=self._hash(challenge);now=int(time.time())
        with self.lock,self.conn:
            row=self.conn.execute('SELECT code_hash,expires,attempts FROM auth_codes WHERE challenge_hash=?',(key,)).fetchone()
            if not row or row[1]<=now:raise AuthError('Code expired. Request a new sign-in email.',401)
            if row[2]>=5:raise AuthError('Too many incorrect codes. Request a new sign-in email.',429)
            self.conn.execute('UPDATE auth_codes SET attempts=attempts+1 WHERE challenge_hash=?',(key,))
            if not hmac.compare_digest(row[0],self._hash(challenge+':'+code)):
                raise AuthError('Incorrect code. Check your email and try again.',401)
            pending=self.conn.execute('SELECT magic_hash FROM auth_handoff WHERE challenge_hash=? AND expires>?',(key,now)).fetchone()
            if not pending:raise AuthError('Sign-in request expired.',401)
            self.conn.execute('DELETE FROM auth_codes WHERE challenge_hash=?',(key,))
            self.conn.execute('DELETE FROM auth_handoff WHERE challenge_hash=?',(key,))
            self.conn.execute('DELETE FROM auth_magic WHERE token_hash=?',(pending[0],))
            cookie=secrets.token_urlsafe(40)
            self.conn.execute('INSERT INTO auth_sessions(token_hash,expires) VALUES(?,?)',(self._hash(cookie),now+43200))
            return cookie

    def redeem(self,token):
        """Use an email token once; prefer unlocking its waiting app over browser login.

        Returns None for a desktop handoff; otherwise a browser session cookie
        for deliberate remote/browser-only sign-in.
        """
        if not isinstance(token,str) or not 30<=len(token)<=256:raise AuthError('Invalid or expired sign-in link',401)
        now=int(time.time()); token_hash=self._hash(token)
        with self.lock,self.conn:
            cur=self.conn.execute('UPDATE auth_magic SET used=1 WHERE token_hash=? AND used=0 AND expires>?',(token_hash,now))
            if cur.rowcount!=1:raise AuthError('Invalid, expired or already used sign-in link',401)
            handoff=self.conn.execute(
                'UPDATE auth_handoff SET approved=1 WHERE magic_hash=? AND approved=0 AND expires>?',
                (token_hash,now)
            ).rowcount==1
            cookie=None
            if not handoff:
                cookie=secrets.token_urlsafe(40)
                self.conn.execute('INSERT INTO auth_sessions(token_hash,expires) VALUES(?,?)',(self._hash(cookie),now+43200))
            self.conn.execute('DELETE FROM auth_magic WHERE expires<? OR used=1',(now,))
            self.conn.execute('DELETE FROM auth_handoff WHERE expires<?',(now,))
            self.conn.execute('DELETE FROM auth_codes WHERE expires<?',(now,))
            self.conn.execute('DELETE FROM auth_sessions WHERE expires<?',(now,))
            self.conn.execute('DELETE FROM auth_attempts WHERE at<?',(now-86400,))
            return cookie
    def redeem_handoff(self,challenge):
        """Issue one desktop-only session after the emailed link approves its random challenge."""
        if not isinstance(challenge,str) or not re.fullmatch(r'[A-Za-z0-9_-]{43}',challenge):
            raise AuthError('Invalid desktop sign-in challenge',400)
        now=int(time.time())
        with self.lock,self.conn:
            cur=self.conn.execute('DELETE FROM auth_handoff WHERE challenge_hash=? AND approved=1 AND expires>?',(self._hash(challenge),now))
            if cur.rowcount!=1:return None
            cookie=secrets.token_urlsafe(40)
            self.conn.execute('INSERT INTO auth_sessions(token_hash,expires) VALUES(?,?)',(self._hash(cookie),now+43200))
            return cookie

    def logout(self,cookie_header):
        try:
            c=SimpleCookie();c.load(cookie_header);s=c.get('meridian_session')
            if s:
                with self.lock,self.conn:self.conn.execute('DELETE FROM auth_sessions WHERE token_hash=?',(self._hash(s.value),))
        except (ValueError,KeyError,TypeError):pass
