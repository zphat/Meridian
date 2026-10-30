#!/usr/bin/env python3
"""Meridian: private, local-first development dashboard. Python 3.9+, no dependencies."""
from __future__ import annotations
import argparse
import sys
import base64
import csv
import datetime as dt
import io
import json
import os
import platform
import shutil
import subprocess
import re
import secrets
import socket
import sqlite3
import ssl
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from email.utils import parsedate_to_datetime
# Python's Windows embedded distribution excludes the application directory from
# sys.path, unlike a normal Python installation. Explicitly load bundled auth.py.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from auth import AuthManager, AuthError
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

VERSION = "0.2.9"
ROOT = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
STATIC = ROOT / "static"
DEFAULT_DATA = Path(os.environ.get("MERIDIAN_DATA_DIR", str(Path.home() / ".meridian"))).expanduser()
UA = f"MeridianDesktop/{VERSION} (+local personal dashboard)"
UPDATE_REPO = os.environ.get("MERIDIAN_UPDATE_REPO", "zphat/Meridian").strip()
TRUSTED_HOSTS = {x.strip().lower() for x in os.environ.get("MERIDIAN_TRUSTED_HOSTS", "").split(",") if x.strip()}
PROJECTS = {
    "latitude": {"id": "latitude", "name": "Latitude", "repository": "zphat/Latitude", "kind": "Screen recorder & editor", "stage": "Cross-platform beta", "sites": [("Landing page", "https://latitude.pictures", "landing")], "description": "Record, stream, edit and export. Local-first and podcast-oriented."},
    "longitude": {"id": "longitude", "name": "Longitude", "repository": "zphat/Longitude", "kind": "Image & cover editor", "stage": "Early release", "sites": [("Landing page", "https://zphat.github.io/Longitude/", "landing"), ("Browser editor", "https://zphat.github.io/Longitude/app/", "app")], "description": "Lightweight local-first editor for thumbnails and covers."},
    "sundial": {"id": "sundial", "name": "Sundial", "repository": "zphat/Sundial", "kind": "Planner & sync", "stage": "Public beta", "sites": [("Landing page", "https://sundial.services", "landing"), ("Web app", "https://app.sundial.services", "app"), ("Sync API", "https://sync.sundial.services/v1/health", "health")], "description": "Daily task planning with optional end-to-end encrypted sync."},
}
SEED_GOALS = [
    ("latitude", "Verify macOS recording, permissions and export on real hardware", "high", "Testing", "Hardware checks are not replaced by passing CI."),
    ("latitude", "Test Latitude Editor in narrow and non-maximized windows", "high", "Quality", "Check resizable panels, timeline, drag handles and shortcuts."),
    ("latitude", "Run Windows/Linux recording-to-export regression tests", "medium", "Testing", "Include isolated audio tracks, streaming and cancellation."),
    ("latitude", "Gather and triage beta feedback before 1.0", "medium", "Release", "Prioritize regressions and first-run problems."),
    ("longitude", "Review editor usability and test a complete real thumbnail workflow", "high", "Quality", "Open media, background removal, text, export and recovery."),
    ("longitude", "Test Windows installer and browser editor independently", "high", "Testing", "Confirm offline behavior and file portability."),
    ("longitude", "Build a cohesive clip-art/graphic asset library", "medium", "Creative", "Curate useful modern shapes and stickers, with licensing notes."),
    ("longitude", "Launch longitude.pictures when the domain is purchased", "low", "Website", "Use the current GitHub Pages site until then."),
    ("sundial", "Diagnose repeated sync-server uptime-check failures", "critical", "Operations", "CI health job has repeatedly failed; confirm whether service, TLS or check is at fault."),
    ("sundial", "Configure and verify off-site backup storage", "high", "Operations", "Roadmap reported Exoscale bucket pending; confirm current status."),
    ("sundial", "Perform a documented backup restore test", "high", "Operations", "A successful backup is not enough without a verified restore."),
    ("sundial", "Finish web-bundle signing and verification", "medium", "Security", "Listed as a loose end in the repository roadmap."),
    ("sundial", "Review signing options and Windows installer warnings", "medium", "Release", "Check current signing roadmap and eligibility."),
]
SEED_DECISIONS = [
    ("latitude", "Prioritize cross-platform verification and editor usability before expanding feature scope", "Initial planning decision; editable."),
    ("longitude", "Keep the editor local-first, prioritize usability, and defer purchasing longitude.pictures", "Domain launch depends on the purchase."),
    ("sundial", "Treat server health and restore readiness as release-critical", "Monitoring is distinct from desktop release builds."),
]
SEED_SNAPSHOTS = {
    "latitude": {"release": {"tag_name": "v0.9.4", "published_at": "2026-10-28T11:10:54Z", "prerelease": True, "html_url": "https://github.com/zphat/Latitude/releases/tag/v0.9.4", "assets": []}, "repo": {"pushed_at": "2026-10-29T01:08:26Z"}, "ci": {"name":"Tests", "conclusion":"success", "html_url":"https://github.com/zphat/Latitude/actions/runs/40798569221"}},
    "longitude": {"release": {"tag_name": "v0.1.1", "published_at": "2026-10-25T19:55:55Z", "prerelease": False, "html_url": "https://github.com/zphat/Longitude/releases/tag/v0.1.1", "assets": []}, "repo": {"pushed_at": "2026-10-26T10:27:16Z"}, "ci": {"name":"build", "conclusion":"success", "html_url":"https://github.com/zphat/Longitude/actions/runs/40307536761"}},
    "sundial": {"release": {"tag_name": "v0.1.42", "published_at": "2026-10-27T20:11:15Z", "prerelease": False, "html_url": "https://github.com/zphat/Sundial/releases/tag/v0.1.42", "assets": []}, "repo": {"pushed_at": "2026-10-27T20:06:13Z"}, "uptime_workflow": {"conclusion":"failure", "html_url":"https://github.com/zphat/Sundial/actions/runs/40842437787", "created_at":"2026-10-29T08:29:00Z"}},
}
DOWNLOAD_EXT = (".exe", ".dmg", ".flatpak", ".deb", ".rpm", ".appimage", ".msi", ".apk", ".zip")

def iso_now():
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")

def read_json(s, fallback=None):
    try: return json.loads(s)
    except (ValueError, TypeError): return fallback

def days_from_now(d):
    try:
        x = dt.datetime.fromisoformat(d.replace("Z", "+00:00"))
        return (dt.datetime.now(dt.timezone.utc) - x).days
    except (ValueError, TypeError): return 9999

def safe_download_asset(asset):
    n = str(asset.get("name", "")).lower()
    return n.endswith(DOWNLOAD_EXT) and not n.endswith("-sources.zip")

class Meridian:
    def __init__(self, data_dir=DEFAULT_DATA, start_worker=True):
        self.data_dir = Path(data_dir).expanduser().resolve()
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.data_dir / "meridian.sqlite3"), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.lock = threading.RLock()
        self.busy = False
        self.last_sync_error = ""
        self._stop = threading.Event()
        self.update_state = {"state": "not_checked", "current": VERSION, "repository": UPDATE_REPO, "checked_at": None, "release_url": None, "installer_url": None}
        self._update_busy = False
        self.tray_icon = None  # Windows packaged build can issue a system notification.
        self._initialize()
        self.auth = AuthManager(self.data_dir, self.conn, self.lock)
        if start_worker:
            self.worker = threading.Thread(target=self._loop, name="MeridianMonitor", daemon=True)
            self.worker.start()
        else: self.worker = None

    def _initialize(self):
        with self.lock, self.conn:
            self.conn.executescript("""
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS goals (id INTEGER PRIMARY KEY, project TEXT NOT NULL, title TEXT NOT NULL, priority TEXT NOT NULL DEFAULT 'medium', category TEXT NOT NULL DEFAULT 'General', description TEXT NOT NULL DEFAULT '', state TEXT NOT NULL DEFAULT 'todo', created_at TEXT NOT NULL, updated_at TEXT NOT NULL, completed_at TEXT);
            CREATE TABLE IF NOT EXISTS notes (id INTEGER PRIMARY KEY, project TEXT NOT NULL, title TEXT NOT NULL, body TEXT NOT NULL, created_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS decisions (id INTEGER PRIMARY KEY, project TEXT NOT NULL, title TEXT NOT NULL, reason TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS events (id INTEGER PRIMARY KEY, project TEXT NOT NULL, kind TEXT NOT NULL, external_id TEXT, title TEXT NOT NULL, detail TEXT NOT NULL DEFAULT '', link TEXT NOT NULL DEFAULT '', happened_at TEXT NOT NULL, UNIQUE(project,kind,external_id));
            CREATE TABLE IF NOT EXISTS cache (key TEXT PRIMARY KEY, json TEXT NOT NULL, checked_at TEXT NOT NULL, error TEXT NOT NULL DEFAULT '');
            CREATE TABLE IF NOT EXISTS site_samples (id INTEGER PRIMARY KEY, project TEXT NOT NULL, label TEXT NOT NULL, url TEXT NOT NULL, checked_at TEXT NOT NULL, success INTEGER NOT NULL, status INTEGER, latency_ms INTEGER, tls_days INTEGER, error TEXT NOT NULL DEFAULT '');
            CREATE TABLE IF NOT EXISTS downloads (id INTEGER PRIMARY KEY, project TEXT NOT NULL, release_tag TEXT NOT NULL, asset TEXT NOT NULL, counted_at TEXT NOT NULL, total INTEGER NOT NULL);
            CREATE TABLE IF NOT EXISTS web_analytics (project TEXT NOT NULL, date TEXT NOT NULL, visitors INTEGER NOT NULL, pageviews INTEGER NOT NULL, PRIMARY KEY(project,date));
            CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            """)
            if not self.conn.execute("SELECT COUNT(*) FROM goals").fetchone()[0]:
                now=iso_now()
                self.conn.executemany("INSERT INTO goals(project,title,priority,category,description,state,created_at,updated_at) VALUES(?,?,?,?,?,'todo',?,?)", [(*r,now,now) for r in SEED_GOALS])
            if not self.conn.execute("SELECT COUNT(*) FROM decisions").fetchone()[0]:
                self.conn.executemany("INSERT INTO decisions(project,title,reason,created_at) VALUES(?,?,?,?)", [(*r,iso_now()) for r in SEED_DECISIONS])
            if not self.conn.execute("SELECT COUNT(*) FROM cache").fetchone()[0]:
                for p,val in SEED_SNAPSHOTS.items():
                    self.conn.execute("INSERT INTO cache(key,json,checked_at,error) VALUES(?,?,?,?)", ("github:"+p,json.dumps(val),"2026-10-29T08:29:00+00:00","Initial verified snapshot; refresh pending"))
            for k, v in {"github_minutes":"30", "site_minutes":"5"}.items():
                self.conn.execute("INSERT OR IGNORE INTO settings(key,value) VALUES(?,?)",(k,v))

    def _get(self, sql, args=()):
        with self.lock: return [dict(r) for r in self.conn.execute(sql,args).fetchall()]

    def _cache(self, key, value, error=""):
        with self.lock, self.conn:
            previous = self.conn.execute("SELECT json FROM cache WHERE key=?",(key,)).fetchone()
            old = read_json(previous[0],{}) if previous else {}
            data = value if value is not None else old
            self.conn.execute("INSERT INTO cache(key,json,checked_at,error) VALUES(?,?,?,?) ON CONFLICT(key) DO UPDATE SET json=excluded.json,checked_at=excluded.checked_at,error=excluded.error",(key,json.dumps(data),iso_now(),error))

    def _settings(self):
        return {x["key"]:x["value"] for x in self._get("SELECT * FROM settings")}

    def _github_get(self, path):
        url="https://api.github.com"+path
        headers={"Accept":"application/vnd.github+json", "User-Agent": UA, "X-GitHub-Api-Version":"2022-11-28"}
        token=os.environ.get("MERIDIAN_GITHUB_TOKEN", "").strip()
        if token: headers["Authorization"]="Bearer "+token
        req=urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req,timeout=13) as resp:
                return json.loads(resp.read(1400000).decode("utf-8"))
        except urllib.error.HTTPError as e:
            msg=e.read(800).decode("utf-8",errors="replace")
            raise RuntimeError("GitHub HTTP %s: %s"%(e.code,msg[:160])) from e

    def _roadmap(self, repo, branch):
        """Fetch human-authored roadmap text when present; don't invent status."""
        for path in ("PROJECT_STATUS.md", "docs/ROADMAP.md"):
            url=f"https://raw.githubusercontent.com/{repo}/{urllib.parse.quote(branch)}/{path}"
            try:
                req=urllib.request.Request(url,headers={"User-Agent":UA})
                with urllib.request.urlopen(req,timeout=6) as resp:
                    body=resp.read(100000).decode("utf-8",errors="replace")
                if body.strip():
                    lines=[]
                    for line in body.splitlines():
                        match=re.match(r"^\s*[-*]\s*\[ \]\s+(.+)$",line)
                        if match:lines.append(match.group(1).strip()[:300])
                    return {"url":url,"text":body[:20000],"open_items":lines[:50],"file":path}
            except (urllib.error.HTTPError,urllib.error.URLError,TimeoutError):
                continue
        return None

    def _store_events(self,p,events):
        with self.lock,self.conn:
            for kind,key,title,detail,link,when in events:
                self.conn.execute("INSERT OR IGNORE INTO events(project,kind,external_id,title,detail,link,happened_at) VALUES(?,?,?,?,?,?,?)",(p,kind,str(key),title[:350],detail[:800],link[:600],when or iso_now()))

    def github_sync(self):
        for p,config in PROJECTS.items():
            name=config["repository"]
            try:
                repo=self._github_get("/repos/"+name)
                releases=self._github_get("/repos/"+name+"/releases?per_page=6")
                workflows=self._github_get("/repos/"+name+"/actions/runs?per_page=50")
                commits=self._github_get("/repos/"+name+"/commits?per_page=15")
                issues=self._github_get("/repos/"+name+"/issues?state=open&per_page=40")
                latest=releases[0] if releases else None
                runs=workflows.get("workflow_runs",[])
                ci=next((r for r in runs if r.get("name","").lower() not in ("uptime","health","monitor") and r.get("status")=="completed"),None)
                uptime=next((r for r in runs if r.get("name","").lower() in ("uptime","health","monitor")),None)
                relevant_releases=[{"tag_name":r.get("tag_name"),"name":r.get("name"),"published_at":r.get("published_at"),"html_url":r.get("html_url"),"prerelease":r.get("prerelease",False),"assets":[{"name":a.get("name"),"download_count":a.get("download_count",0)} for a in r.get("assets",[])]} for r in releases]
                obj={"repo":{"full_name":name,"description":repo.get("description"),"pushed_at":repo.get("pushed_at"),"open_issues_count":repo.get("open_issues_count"),"default_branch":repo.get("default_branch")},"release":relevant_releases[0] if relevant_releases else None,"releases":relevant_releases,"ci":({k:ci.get(k) for k in ("name","status","conclusion","html_url","created_at")} if ci else None),"uptime_workflow":({k:uptime.get(k) for k in ("name","status","conclusion","html_url","created_at")} if uptime else None),"commits":[{"sha":c.get("sha"),"message":c.get("commit",{}).get("message","").split("\n")[0],"date":c.get("commit",{}).get("committer",{}).get("date"),"url":c.get("html_url")} for c in commits],"issues":[{"number":i.get("number"),"title":i.get("title"),"url":i.get("html_url"),"pull_request":bool(i.get("pull_request"))} for i in issues],"roadmap":self._roadmap(name,repo.get("default_branch") or "main"),"fetched_at":iso_now()}
                self._cache("github:"+p,obj)
                events=[]
                for r in releases[:4]:
                    events.append(("release",r.get("id",r.get("tag_name")),"Released "+str(r.get("tag_name")),r.get("name") or "",r.get("html_url") or "",r.get("published_at") or iso_now()))
                for c in commits:
                    events.append(("commit",c.get("sha"),c.get("commit",{}).get("message","").split("\n")[0],"",c.get("html_url") or "",c.get("commit",{}).get("committer",{}).get("date") or iso_now()))
                self._store_events(p,events)
                with self.lock,self.conn:
                    for r in releases[:3]:
                        for a in r.get("assets",[]):
                            if safe_download_asset(a):
                                self.conn.execute("INSERT INTO downloads(project,release_tag,asset,counted_at,total) VALUES(?,?,?,?,?)",(p,r.get("tag_name",""),a["name"],iso_now(),int(a.get("download_count",0))))
                    self.conn.execute("DELETE FROM downloads WHERE id NOT IN (SELECT MAX(id) FROM downloads GROUP BY project,release_tag,asset,date(counted_at))")
            except Exception as e:
                self._cache("github:"+p,None,str(e))

    def check_url(self, url, health=False):
        started=time.monotonic(); result={"success":False,"status":None,"latency_ms":None,"tls_days":None,"error":""}
        try:
            req=urllib.request.Request(url,headers={"User-Agent":UA,"Accept":"application/json,text/html,*/*"})
            with urllib.request.urlopen(req,timeout=9) as response:
                result["status"]=response.status
                if health:
                    content=json.loads(response.read(20000).decode("utf-8"))
                    if content.get("ok") is not True or content.get("mode") != "hosted":
                        raise ValueError("Health response did not report healthy hosted mode")
                result["success"]=200<=response.status<400
        except urllib.error.HTTPError as e:
            result["status"]=e.code;result["error"]="HTTP "+str(e.code)
        except Exception as e:
            result["error"]=str(e)[:180]
        result["latency_ms"]=round((time.monotonic()-started)*1000)
        # HTTP probes validate TLS during connection. Read expiry separately so the
        # dashboard can warn about upcoming renewal failures, not just failures today.
        if result["success"] and urllib.parse.urlsplit(url).scheme == "https":
            try:
                host=urllib.parse.urlsplit(url).hostname
                port=urllib.parse.urlsplit(url).port or 443
                with socket.create_connection((host,port),timeout=4) as raw:
                    with ssl.create_default_context().wrap_socket(raw,server_hostname=host) as secured:
                        exp=ssl.cert_time_to_seconds(secured.getpeercert()["notAfter"])
                        result["tls_days"]=max(-999, int((exp-time.time())//86400))
            except (OSError,ValueError,KeyError,ssl.SSLError):
                pass  # A failed expiry lookup is unknown, not proof of bad TLS.
        return result

    def site_sync(self):
        for p,config in PROJECTS.items():
            for label,url,typ in config["sites"]:
                d=self.check_url(url,typ=="health")
                with self.lock,self.conn:
                    self.conn.execute("INSERT INTO site_samples(project,label,url,checked_at,success,status,latency_ms,tls_days,error) VALUES(?,?,?,?,?,?,?,?,?)",(p,label,url,iso_now(),int(d["success"]),d["status"],d["latency_ms"],d["tls_days"],d["error"]))
                    self.conn.execute("DELETE FROM site_samples WHERE id IN (SELECT id FROM site_samples WHERE project=? AND url=? ORDER BY id DESC LIMIT -1 OFFSET 600)",(p,url))

    def run_sync(self,kind="all"):
        with self.lock:
            if self.busy:return False
            self.busy=True
        try:
            if kind in ("all","github"):self.github_sync()
            if kind in ("all","sites"):self.site_sync()
            return True
        finally:
            self.busy=False

    def refresh_async(self,kind="all"):
        with self.lock:
            if self.busy:return False
        threading.Thread(target=self.run_sync,args=(kind,),name="ManualRefresh",daemon=True).start()
        return True

    def check_updates(self):
        """Read release metadata only; never download or run code without approval."""
        if not re.fullmatch(r"[a-zA-Z0-9_.-]+/[a-zA-Z0-9_.-]+", UPDATE_REPO):
            state={"state":"not_configured","detail":"Set a valid MERIDIAN_UPDATE_REPO (owner/repository)."}
        else:
            url=f"https://api.github.com/repos/{UPDATE_REPO}/releases/latest"
            headers={"Accept":"application/vnd.github+json", "User-Agent":UA,"X-GitHub-Api-Version":"2022-11-28"}
            token=os.environ.get("MERIDIAN_GITHUB_TOKEN", "").strip()
            if token: headers["Authorization"]="Bearer "+token
            try:
                with urllib.request.urlopen(urllib.request.Request(url,headers=headers),timeout=12) as res:
                    release=json.loads(res.read(500000).decode("utf-8"))
                latest=str(release.get("tag_name") or "").lstrip("vV")
                if not re.fullmatch(r"\d+\.\d+\.\d+",latest):
                    raise ValueError("Latest release tag must be a version such as v0.2.1")
                page=str(release.get("html_url") or "")
                if not page.startswith(f"https://github.com/{UPDATE_REPO}/releases/tag/"):
                    raise ValueError("Release link did not match the configured repository")
                available=tuple(map(int,latest.split('.')))>tuple(map(int,VERSION.split('.')))
                installer=None
                if available:
                    assets={str(a.get("name") or ""):str(a.get("browser_download_url") or "") for a in release.get("assets",[])}
                    if sys.platform.startswith("linux"):
                        try:
                            os_release=Path("/etc/os-release").read_text(encoding="utf-8").lower()
                        except OSError:
                            os_release=""
                        if any(x in os_release for x in ('id=fedora','id=opensuse','id_like="fedora','id_like="rhel','id=rhel')):
                            preferred=[f"Meridian-{latest}-1.noarch.rpm",f"Meridian-Linux-{latest}.run",f"Meridian-{latest}-all.deb"]
                        else:
                            preferred=[f"Meridian-{latest}-all.deb",f"Meridian-Linux-{latest}.run",f"Meridian-{latest}-1.noarch.rpm"]
                    elif sys.platform == "darwin":
                        preferred=[f"Meridian-Mac-{latest}.dmg",f"Meridian-{latest}-macOS.zip"]
                    else:
                        preferred=[f"Meridian-Setup-{latest}.exe"]
                    for name in preferred:
                        url=assets.get(name, "")
                        if url.startswith(f"https://github.com/{UPDATE_REPO}/releases/download/v{latest}/"):
                            installer=url
                            break
                state={"state":"available" if available else "up_to_date","latest":latest,"release_url":page,"installer_url":installer,"detail":("A newer installer is available. Open Settings to download it." if installer else "A newer release is available; see its release page for your platform.") if available else "You have the latest published version."}
            except urllib.error.HTTPError as e:
                if e.code==404:
                    state={"state":"private_or_unpublished", "detail":"GitHub returned 404. The Meridian repository is private or has no published release; private releases require an authenticated update feed, or a public release repository."}
                else:
                    state={"state":"error", "detail":f"GitHub returned HTTP {e.code}."}
            except (OSError, ValueError, json.JSONDecodeError) as e:
                state={"state":"error", "detail":str(e)[:170]}
        with self.lock:
            self.update_state={"current":VERSION,"repository":UPDATE_REPO,"checked_at":iso_now(),"release_url":None,"installer_url":None,**state}
            self._update_busy=False
        # Tell the desktop user once per new release. The notification does not
        # download, install, execute, or otherwise trust an installer.
        if state.get("state")=="available" and state.get("installer_url"):
            self._notify_new_update(str(state.get("latest")))
        return self.update_state

    def _notify_new_update(self, version):
        with self.lock:
            last=self.conn.execute("SELECT value FROM settings WHERE key='last_notified_version'").fetchone()
            if last and last[0]==version:
                return
        message=f"Meridian {version} is available. Open Settings to download the installer."
        if sys.platform == "win32":
            # pystray supplies a Windows tray notification in compiled builds.
            # If notifications are unavailable, the dashboard still shows the update.
            icon=self.tray_icon
            if icon is None:
                return
            try:
                icon.notify(message,"Meridian update available")
            except Exception:
                return
        elif sys.platform.startswith("linux"):
            if not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
                return
            if not shutil.which("notify-send"):
                return
            try:
                subprocess.run(["notify-send","--app-name=Meridian","--icon=meridian",
                    "Meridian update available",message],
                    timeout=4,check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            except (OSError,subprocess.TimeoutExpired,subprocess.CalledProcessError):
                return
        else:
            return
        with self.lock,self.conn:
            self.conn.execute("INSERT INTO settings(key,value) VALUES('last_notified_version',?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",(version,))

    def check_updates_async(self):
        with self.lock:
            if self._update_busy: return False
            self._update_busy=True
        threading.Thread(target=self.check_updates,daemon=True,name="MeridianUpdateCheck").start()
        return True

    def _loop(self):
        # First refresh on startup. Continue while the local dashboard is open.
        next_gh=0.;next_sites=0.;next_updates=0.
        while not self._stop.is_set():
            now=time.monotonic()
            if now>=next_updates:
                self.check_updates_async()
                next_updates=time.monotonic()+6*3600
            if now>=next_gh:
                self.run_sync("github")
                next_gh=time.monotonic()+1800
            if self._stop.is_set():break
            if time.monotonic()>=next_sites:
                self.run_sync("sites")
                next_sites=time.monotonic()+300
            self._stop.wait(5)

    def snapshot(self):
        with self.lock:
            cache={r["key"]:{"data":read_json(r["json"],{}),"checked_at":r["checked_at"],"error":r["error"]} for r in self.conn.execute("SELECT * FROM cache")}
            goals=self._get("SELECT * FROM goals ORDER BY CASE priority WHEN 'critical' THEN 0 WHEN 'high' THEN 1 WHEN 'medium' THEN 2 ELSE 3 END,id DESC")
            notes=self._get("SELECT * FROM notes ORDER BY id DESC LIMIT 250")
            decisions=self._get("SELECT * FROM decisions ORDER BY id DESC LIMIT 250")
            events=self._get("SELECT * FROM events ORDER BY happened_at DESC,id DESC LIMIT 170")
            sites=self._get("SELECT s.* FROM site_samples s INNER JOIN (SELECT project,url,MAX(id) mid FROM site_samples GROUP BY project,url) x ON x.mid=s.id ORDER BY s.project,s.id")
            analytics=self._get("SELECT * FROM web_analytics ORDER BY date DESC LIMIT 1200")
            dl=self._get("SELECT * FROM downloads WHERE id IN (SELECT MAX(id) FROM downloads GROUP BY project,release_tag,asset) ORDER BY counted_at DESC")
            dl_series=self._get("SELECT project,substr(counted_at,1,10) date,MAX(total) total FROM downloads GROUP BY project,release_tag,asset,substr(counted_at,1,10) ORDER BY date DESC LIMIT 3000")
            site_series=self._get("SELECT project,label,substr(checked_at,1,10) day,COUNT(*) checks,SUM(success) passed FROM site_samples GROUP BY project,label,substr(checked_at,1,10) ORDER BY day DESC LIMIT 210")
            # Forty-eight hourly groups from actual sampled checks, never interpolated.
            # Older periods and offline periods are absent and displayed as unknown.
            cutoff=(dt.datetime.now(dt.timezone.utc)-dt.timedelta(hours=48)).isoformat(timespec="seconds")
            site_48h=self._get("""SELECT project,url,substr(checked_at,1,13) hour,
                COUNT(*) checks,SUM(success) passed,
                MAX(checked_at) last_checked FROM site_samples
                WHERE checked_at>=? GROUP BY project,url,substr(checked_at,1,13)
                ORDER BY hour""",(cutoff,))
            # Preserve the asset name/tag in history. Summing daily MAX values across
            # different installer assets would otherwise lose which release they belong to.
            dl_series=self._get("""SELECT project,release_tag,asset,
                substr(counted_at,1,10) date,MAX(total) total
                FROM downloads GROUP BY project,release_tag,asset,substr(counted_at,1,10)
                ORDER BY date DESC LIMIT 3000""")
            project_details=[]
            for p,config in PROJECTS.items():
                gh=cache.get("github:"+p,{"data":{},"checked_at":None,"error":"Awaiting first sync"})
                obj=dict(config)
                obj["sites"]=[{"label":name,"url":url,"type":typ,"status":next((v for v in sites if v["project"]==p and v["url"]==url),None)} for name,url,typ in config["sites"]]
                obj["github"]=gh
                release=gh["data"].get("release") or {}
                obj["latest_downloads"]=sum(int(a.get("total",0)) for a in dl if a["project"]==p and a["release_tag"]==release.get("tag_name", ""))
                project_details.append(obj)
            return {"projects":project_details,"goals":goals,"notes":notes,"decisions":decisions,"events":events,"web_analytics":analytics,"download_assets":dl,"download_history":dl_series,"site_history":site_series,"site_48h":site_48h,"settings":self._settings(),"busy":self.busy,"data_dir":str(self.data_dir),"time":iso_now(),"app_version":VERSION,"mode":"local","updates":dict(self.update_state)}

    def insert(self,table,data):
        cols={"goals":{"project","title","priority","category","description","state"},"notes":{"project","title","body"},"decisions":{"project","title","reason"}}[table]
        allowed={k:v for k,v in data.items() if k in cols}
        if allowed.get("project") not in PROJECTS:raise ValueError("Choose a valid project")
        if not str(allowed.get("title","")).strip():raise ValueError("Title is required")
        for k,v in allowed.items():
            if not isinstance(v,str) or len(v)>12000:raise ValueError("Invalid field: "+k)
        if table=="goals":
            if allowed.get("state","todo") not in ("todo","doing","done"):raise ValueError("Invalid state")
            if allowed.get("priority","medium") not in ("critical","high","medium","low"):raise ValueError("Invalid priority")
        now=iso_now();allowed["created_at"]=now
        if table=="goals":allowed["updated_at"]=now
        names=",".join(allowed); marks=",".join("?" for _ in allowed)
        with self.lock,self.conn:
            cur=self.conn.execute(f"INSERT INTO {table} ({names}) VALUES ({marks})",list(allowed.values()))
            return cur.lastrowid

    def change_goal(self,id,data):
        allowed={k:v for k,v in data.items() if k in ("state","title","description","category","priority")}
        if not allowed:raise ValueError("No values supplied")
        if "state" in allowed and allowed["state"] not in ("todo","doing","done"):raise ValueError("Invalid state")
        if "priority" in allowed and allowed["priority"] not in ("critical","high","medium","low"):raise ValueError("Invalid priority")
        for v in allowed.values():
            if not isinstance(v,str) or len(v)>12000:raise ValueError("Invalid value")
        allowed["updated_at"]=iso_now()
        if allowed.get("state")=="done":allowed["completed_at"]=iso_now()
        elif "state" in allowed:allowed["completed_at"]=None
        with self.lock,self.conn:
            cur=self.conn.execute("UPDATE goals SET "+",".join(k+"=?" for k in allowed)+" WHERE id=?",(*allowed.values(),id))
            if not cur.rowcount:raise ValueError("Goal not found")

    def delete(self,table,id):
        if table not in ("goals","notes","decisions"):raise ValueError("Invalid item")
        with self.lock,self.conn:
            self.conn.execute(f"DELETE FROM {table} WHERE id=?",(id,))

    def import_csv(self,text,project):
        if project not in PROJECTS:raise ValueError("Invalid project")
        r=csv.DictReader(io.StringIO(text.lstrip("\ufeff")))
        if not r.fieldnames:raise ValueError("CSV is empty")
        def norm(s):return re.sub(r"[^a-z]","",s.lower())
        fields={norm(f):f for f in r.fieldnames}
        date_col=next((fields[k] for k in ("date","day") if k in fields),None)
        visitor_col=next((fields[k] for k in ("visitors","uniquevisitors","uniques","uniquevisits") if k in fields),None)
        page_col=next((fields[k] for k in ("pageviews","views","requests") if k in fields),None)
        if not all((date_col,visitor_col,page_col)):raise ValueError("Expected CSV columns: date, visitors, pageviews")
        rows=[]
        for row in r:
            if len(rows)>5000:raise ValueError("CSV exceeds 5000 rows")
            day=row[date_col].strip()[:10]
            try:
                dt.date.fromisoformat(day)
                visitors=int(float(row[visitor_col].replace(",","")))
                views=int(float(row[page_col].replace(",","")))
                if visitors<0 or views<0:raise ValueError()
            except (ValueError,TypeError):raise ValueError("Invalid date or counts on CSV row "+str(len(rows)+2))
            rows.append((project,day,visitors,views))
        with self.lock,self.conn:
            self.conn.executemany("INSERT INTO web_analytics(project,date,visitors,pageviews) VALUES(?,?,?,?) ON CONFLICT(project,date) DO UPDATE SET visitors=excluded.visitors,pageviews=excluded.pageviews",rows)
        return len(rows)

    def backup(self):
        data=self.snapshot()
        return {"format":"meridian-backup-v1","exported_at":iso_now(),"goals":data["goals"],"notes":data["notes"],"decisions":data["decisions"],"web_analytics":data["web_analytics"]}

    def restore(self,data):
        if data.get("format")!="meridian-backup-v1":raise ValueError("Not a Meridian backup")
        for table in ("goals","notes","decisions","web_analytics"):
            if not isinstance(data.get(table),list) or len(data[table])>20000:raise ValueError("Invalid backup data")
        # Clear and reinsert owned private content; automated data isn't touched.
        with self.lock,self.conn:
            for table in ("goals","notes","decisions","web_analytics"):
                self.conn.execute("DELETE FROM "+table)
                cols={"goals":("project","title","priority","category","description","state","created_at","updated_at","completed_at"),"notes":("project","title","body","created_at"),"decisions":("project","title","reason","created_at"),"web_analytics":("project","date","visitors","pageviews")}[table]
                for row in data[table]:
                    if not isinstance(row,dict) or row.get("project") not in PROJECTS:raise ValueError("Invalid backup project")
                    values=[row.get(k) for k in cols]
                    self.conn.execute(f"INSERT INTO {table} ({','.join(cols)}) VALUES ({','.join('?' for _ in cols)})",values)

    def close(self):
        self._stop.set()
        if self.worker:self.worker.join(timeout=1)
        with self.lock:self.conn.close()

class Handler(BaseHTTPRequestHandler):
    server_version="Meridian/0.2.9"
    def log_message(self,format,*args):
        if not self.path.startswith('/api/state') and '/auth/verify' not in self.path:super().log_message(format,*args)

    @property
    def app(self):return self.server.meridian

    def guard(self):
        host=self.headers.get("Host","")
        # Explicit trusted hosts permit access through a private HTTPS reverse
        # proxy such as Tailscale Serve. Never accept arbitrary Host headers.
        try:
            parsed=urllib.parse.urlsplit("//"+host)
            hostname=(parsed.hostname or "").lower()
        except ValueError:
            self.send_error(403,"Invalid hostname");return False
        if hostname not in ("127.0.0.1","localhost") and host.lower() not in TRUSTED_HOSTS and hostname not in TRUSTED_HOSTS:
            self.send_error(403,"Host is not on Meridian's allowlist");return False
        if self.command in ("POST","PATCH","DELETE"):
            if self.headers.get("Sec-Fetch-Site","").lower() == "cross-site":
                self.send_error(403,"Cross-site requests denied");return False
            origin=self.headers.get("Origin","")
            if origin:
                try:
                    parsed_origin=urllib.parse.urlsplit(origin)
                    origin_host=(parsed_origin.hostname or "").lower()
                    origin_port=parsed_origin.port
                    host_port=parsed.port
                    remote=hostname not in ("127.0.0.1","localhost")
                    valid_scheme=(parsed_origin.scheme=="https") if remote else (parsed_origin.scheme=="http")
                    same_port=(origin_port or (443 if remote else 80))==(host_port or (443 if remote else 80))
                    if not (valid_scheme and origin_host==hostname and same_port):
                        self.send_error(403,"Origin mismatch");return False
                except ValueError:
                    self.send_error(403,"Invalid origin");return False
            if self.headers.get("Content-Type","").split(";")[0]!="application/json":
                self.send_error(415,"Application/json required");return False
        return True

    def session_valid(self):
        return self.app.auth.check_session(self.headers.get('Cookie',''))

    def send_auth_html(self):
        raw=(STATIC/'auth.html').read_bytes()
        self.send_response(200)
        self.send_header('Content-Type','text/html; charset=utf-8')
        self.send_header('Content-Length',str(len(raw)))
        self.send_header('Cache-Control','no-store')
        self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('Referrer-Policy','no-referrer')
        self.send_header('Content-Security-Policy',"default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; connect-src 'self'; base-uri 'none'; frame-ancestors 'none'")
        self.end_headers();self.wfile.write(raw)

    def reply(self,value,code=200):
        raw=json.dumps(value,ensure_ascii=False).encode("utf-8")
        self.send_response(code);self.send_header("Content-Type","application/json; charset=utf-8");self.send_header("Cache-Control","no-store");self.send_header("Content-Length",str(len(raw)));self.send_header("X-Content-Type-Options","nosniff");self.send_header("Referrer-Policy","no-referrer");self.end_headers();self.wfile.write(raw)

    def body(self):
        size=int(self.headers.get("Content-Length","0"))
        if size<0 or size>2*1024*1024:raise ValueError("Request too large")
        obj=json.loads(self.rfile.read(size).decode("utf-8"))
        if not isinstance(obj,dict):raise ValueError("Expected JSON object")
        return obj

    def do_GET(self):
        if not self.guard():return
        path=urllib.parse.urlsplit(self.path).path
        if path=="/api/health":return self.reply({"ok":True,"app":"Meridian","version":VERSION,"local":True})
        if path=="/api/auth/status":
            return self.reply({"configured":self.app.auth.configured(),"authenticated":self.session_valid(),
                "local_setup":self.headers.get("Host","").split(":")[0].lower() in ("127.0.0.1","localhost")})
        if path=="/auth/verify":
            token=urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query).get("token",[""])[0]
            try:cookie=self.app.auth.redeem(token)
            except AuthError:return self.send_auth_html()
            remote=(urllib.parse.urlsplit('//'+self.headers.get('Host','')).hostname or '') not in ('127.0.0.1','localhost')
            self.send_response(303);self.send_header('Location','/')
            self.send_header('Set-Cookie','meridian_session='+cookie+'; HttpOnly; SameSite=Strict; Path=/; Max-Age=43200'+('; Secure' if remote else ''))
            self.send_header('Cache-Control','no-store');self.send_header('Referrer-Policy','no-referrer');self.end_headers();return
        if path in ('/auth.js','/auth.css','/favicon.svg'):return self.serve_static(path)
        if not self.session_valid():
            if path.startswith('/api/'):return self.reply({'error':'Sign-in required'},401)
            return self.send_auth_html()
        if path=="/api/state":return self.reply(self.app.snapshot())
        if path=="/api/backup":return self.reply(self.app.backup())
        if path=="/":path="/index.html"
        return self.serve_static(path)

    def serve_static(self,path):
        if not path.startswith("/"):return self.send_error(404)
        candidate=(STATIC/path.lstrip("/")).resolve()
        if not candidate.is_relative_to(STATIC.resolve()) or not candidate.is_file():return self.send_error(404)
        mime={".html":"text/html; charset=utf-8",".js":"application/javascript; charset=utf-8",".css":"text/css; charset=utf-8",".svg":"image/svg+xml",".png":"image/png"}.get(candidate.suffix,"application/octet-stream")
        raw=candidate.read_bytes();self.send_response(200);self.send_header("Content-Type",mime);self.send_header("Content-Length",str(len(raw)));self.send_header("Cache-Control","no-store");self.send_header("X-Content-Type-Options","nosniff");self.send_header("Referrer-Policy","no-referrer");self.send_header("Content-Security-Policy","default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; connect-src 'self'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'");self.end_headers();self.wfile.write(raw)

    def do_POST(self):self.mutate("POST")
    def do_PATCH(self):self.mutate("PATCH")
    def do_DELETE(self):self.mutate("DELETE")
    def mutate(self,method):
        if not self.guard():return
        path=urllib.parse.urlsplit(self.path).path
        try:
            body=self.body() if method!="DELETE" else self.body()
            if path=="/api/auth/setup" and method=="POST":
                if self.headers.get('Host','').split(':')[0].lower() not in ('127.0.0.1','localhost'):
                    return self.reply({'error':'Initial setup requires the local desktop'},403)
                email=body.get('email'); password=body.get('password')
                self.app.auth.configure(email,password,body.get('resend_key'))
                host=self.headers.get('Host','')
                try:self.app.auth.issue_link(email,password,'http://'+host)
                except AuthError:
                    self.app.auth.rollback_setup()
                    raise
                return self.reply({'ok':True,'link_sent':True},201)
            if path=="/api/auth/request" and method=="POST":
                host=self.headers.get('Host','')
                remote=(urllib.parse.urlsplit('//'+host).hostname or '') not in ('127.0.0.1','localhost')
                origin=('https://' if remote else 'http://')+host
                return self.reply(self.app.auth.issue_link(body.get('email'),body.get('password'),origin))
            if path=="/api/auth/logout" and method=="POST":
                self.app.auth.logout(self.headers.get('Cookie',''))
                self.send_response(204);self.send_header('Set-Cookie','meridian_session=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0')
                self.send_header('Cache-Control','no-store');self.end_headers();return
            if not self.session_valid():return self.reply({'error':'Sign-in required'},401)
            if path=="/api/refresh" and method=="POST":return self.reply({"started":self.app.refresh_async(body.get("kind","all"))})
            if path=="/api/updates/check" and method=="POST":return self.reply({"started":self.app.check_updates_async()})
            if path=="/api/analytics/import" and method=="POST":return self.reply({"imported":self.app.import_csv(body.get("csv",""),body.get("project",""))})
            if path=="/api/restore" and method=="POST":
                self.app.restore(body);return self.reply({"ok":True})
            if method=="POST" and path in ("/api/goals","/api/notes","/api/decisions"):
                return self.reply({"id":self.app.insert(path.split("/")[-1],body)},201)
            matched=re.fullmatch(r"/api/(goals|notes|decisions)/(\d+)",path)
            if matched:
                table,id=matched.group(1),int(matched.group(2))
                if method=="PATCH" and table=="goals":self.app.change_goal(id,body);return self.reply({"ok":True})
                if method=="DELETE":self.app.delete(table,id);return self.reply({"ok":True})
            return self.reply({"error":"No matching endpoint"},404)
        except AuthError as e:return self.reply({"error":str(e)},e.status)
        except (ValueError,KeyError,TypeError,sqlite3.Error) as e:return self.reply({"error":str(e)},400)
        except Exception as e:return self.reply({"error":"Unexpected operation error"},500)

def launch_window(url):
    """Prefer a dedicated app-like browser window; fall back to a normal tab."""
    candidates=[]
    if os.name=="nt":
        env=os.environ
        candidates.extend([
            os.path.join(env.get("PROGRAMFILES(X86)",""),"Microsoft","Edge","Application","msedge.exe"),
            os.path.join(env.get("PROGRAMFILES",""),"Microsoft","Edge","Application","msedge.exe"),
            os.path.join(env.get("LOCALAPPDATA",""),"Microsoft","Edge","Application","msedge.exe"),
            os.path.join(env.get("LOCALAPPDATA",""),"Google","Chrome","Application","chrome.exe"),
            os.path.join(env.get("PROGRAMFILES",""),"Google","Chrome","Application","chrome.exe"),
        ])
    else:
        for x in ("google-chrome-stable","google-chrome","chromium","chromium-browser","microsoft-edge"):
            found=shutil.which(x)
            if found:candidates.append(found)
    for exe in candidates:
        if not exe or not os.path.isfile(exe):continue
        try:
            subprocess.Popen([exe,"--app="+url,"--window-size=1320,940"],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            return
        except OSError:continue
    webbrowser.open(url)

def start_windows_tray(server,app,url):
    """Optional tray controls in the packaged Windows application."""
    if os.name!="nt" or not getattr(sys,"frozen",False):return None
    try:
        import pystray
        from PIL import Image
        artwork=Image.open(ROOT / "assets" / "meridian.png")
        icon=pystray.Icon("Meridian",artwork,"Meridian · Development Control Center")
        def open_dashboard(icon,item): launch_window(url)
        def check(icon,item): app.check_updates_async();launch_window(url+"#settings")
        def quit_app(icon,item):
            icon.stop()
            threading.Thread(target=server.shutdown,daemon=True).start()
        icon.menu=pystray.Menu(
            pystray.MenuItem("Open Meridian",open_dashboard,default=True),
            pystray.MenuItem("Check for updates",check),
            pystray.MenuItem("Quit Meridian",quit_app))
        app.tray_icon=icon
        threading.Thread(target=icon.run,name="MeridianTray",daemon=True).start()
        return icon
    except Exception as e:
        print("Tray unavailable:",e,flush=True)
        return None

def serve(args):
    try:
        server=ThreadingHTTPServer(("127.0.0.1",args.port),Handler)
    except OSError as err:
        if args.port:
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{args.port}/api/health",timeout=2) as response:
                    status=json.load(response)
                if status.get("app")=="Meridian":
                    current=str(status.get("version") or "unknown")
                    if current != VERSION:
                        raise RuntimeError(
                            f"An older Meridian instance (v{current}) is still running on port {args.port}. "
                            f"Close the old application and open v{VERSION} again. "
                            "The updated installer normally closes old instances automatically."
                        ) from err
                    if not args.no_browser:launch_window(f"http://127.0.0.1:{args.port}/")
                    print("Meridian is already running at the current version.",flush=True)
                    return
            except (OSError,ValueError,urllib.error.URLError): pass
        raise RuntimeError(f"Cannot start Meridian on port {args.port}: {err}. Use --port 0 for a free port.") from err
    app=Meridian(args.data_dir,start_worker=not args.offline)
    server.meridian=app
    url="http://127.0.0.1:%d/"%server.server_address[1]
    print("Meridian running at",url,"\nPersonal data:",app.data_dir,"\nUse the tray Quit command or Ctrl+C to exit.",flush=True)
    tray=start_windows_tray(server,app,url) if not args.no_tray else None
    if not args.no_browser:
        threading.Timer(0.6,lambda:webbrowser.open(url) if args.browser_tab else launch_window(url)).start()
    try:server.serve_forever(poll_interval=0.3)
    except KeyboardInterrupt:pass
    finally:
        if tray:tray.stop()
        server.server_close();app.close()

def main():
    parser=argparse.ArgumentParser(description="Meridian local development control center")
    parser.add_argument("--port",type=int,default=8765,help="Local port (0 selects a free port)")
    parser.add_argument("--data-dir",default=str(DEFAULT_DATA),help="Folder for private database")
    parser.add_argument("--no-browser",action="store_true")
    parser.add_argument("--browser-tab",action="store_true",help="Use a normal browser tab instead of app window")
    parser.add_argument("--offline",action="store_true",help="Disable network refresh (for testing)")
    parser.add_argument("--no-tray",action="store_true",help="Disable Windows tray controls")
    serve(parser.parse_args())
if __name__=="__main__":main()
