package main

import "time"

// A native HWND is not proof that the browser has loaded the app. This guard
// stops as soon as the styled, interactive page acknowledges readiness, or
// the user closes the window. It does no recurring work after startup.
func guardStartup(ready, closed <-chan struct{}, retryAfter, giveUpAfter time.Duration, retry, fallback func()) {
	retryTimer := time.NewTimer(retryAfter)
	deadline := time.NewTimer(giveUpAfter)
	defer retryTimer.Stop()
	defer deadline.Stop()
	for {
		select {
		case <-ready:
			return
		case <-closed:
			return
		case <-retryTimer.C:
			retry()
		case <-deadline.C:
			// Prefer an acknowledgement/close that arrived at the same instant.
			select {
			case <-ready:
				return
			case <-closed:
				return
			default:
				fallback()
				return
			}
		}
	}
}

const startupHTML = `<!doctype html><html><head><meta charset="utf-8"><title>Opening Meridian</title>
<style>html{color-scheme:dark}body{margin:0;background:#101512;color:#edf1eb;font:16px system-ui,sans-serif;display:grid;place-items:center;min-height:100vh}main{max-width:440px;padding:40px}b{color:#bcf65a;font-size:14px;letter-spacing:.18em}h1{font-size:28px;font-weight:600;margin-top:25px}p{color:#a9b3a7;line-height:1.6}</style>
</head><body><main id="meridian-startup"><b>MERIDIAN</b><h1>Opening your workspace…</h1><p>This usually takes a few seconds. Meridian will retry automatically if startup gets stuck.</p></main></body></html>`

// Wait for two rendered frames, loaded CSS and the app's own readiness marker.
// The marker is set only after auth status or dashboard data has been handled.
// The initial local HTML proves that the embedded renderer is running before
// we navigate to the dashboard; navigation is dispatched through the UI loop.
const startupScript = `(() => {
 if(window.top!==window)return;
 let checks=0;
 function report(){
  if(typeof window.meridianNativeReady!=='function'){if(checks++<300)setTimeout(report,100);return;}
  if(location.href==='about:blank' && document.querySelector('#meridian-startup')){
   window.meridianNativeReady('loading',innerWidth,innerHeight);return;
  }
  if(location.origin==='http://127.0.0.1:8765'){
   const view=document.documentElement.dataset.meridianReady;
   const bg=document.body&&getComputedStyle(document.body).backgroundColor;
   const form=document.querySelector(view==='auth'?'#heading':'#page h1');
   if((view==='auth'||view==='dashboard')&&form&&form.getBoundingClientRect().width>0&&innerWidth>0&&innerHeight>0&&bg!=='rgba(0, 0, 0, 0)'&&bg!=='rgb(255, 255, 255)'){
    window.meridianNativeReady(view,innerWidth,innerHeight);return;
   }
  }
  if(checks++<300)setTimeout(report,100);
 }
 const start=()=>document.hidden?setTimeout(report,100):requestAnimationFrame(()=>requestAnimationFrame(report));
 if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',start,{once:true});else start();
})();`
