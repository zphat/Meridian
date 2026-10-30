package main

import (
 "fmt"
 "net/http"
 "net/url"
 "regexp"
 "strings"
 "os"
 "os/exec"
 "path/filepath"
 "syscall"
 "time"
 "unsafe"
 "runtime"
 "encoding/json"

 webview2 "github.com/jchv/go-webview2"
)

func message(s string) {
 user32:=syscall.NewLazyDLL("user32.dll")
 p:=user32.NewProc("MessageBoxW")
 t,_:=syscall.UTF16PtrFromString(s)
 title,_:=syscall.UTF16PtrFromString("Meridian")
 p.Call(0,uintptr(unsafe.Pointer(t)),uintptr(unsafe.Pointer(title)),0x10)
}
// Windows delivers meridian://approve?token=... to this registered app
// rather than the user's default browser. The waiting app owns its own
// browser cookie and is unlocked through the one-time challenge handoff.
func approveDesktopLink(raw string) error {
 u,e:=url.Parse(raw)
 if e!=nil || !strings.EqualFold(u.Scheme,"meridian") || !strings.EqualFold(u.Host,"approve") || u.Path!="" {
  return fmt.Errorf("invalid Meridian sign-in link")
 }
 token:=u.Query().Get("token")
 if !regexp.MustCompile(`^[a-zA-Z0-9_-]{40,60}$`).MatchString(token){
  return fmt.Errorf("invalid or expired sign-in token")
 }
 client:=&http.Client{
  Timeout:6*time.Second,
  CheckRedirect:func(req *http.Request, via []*http.Request) error{return http.ErrUseLastResponse},
 }
 res,e:=client.Get("http://127.0.0.1:8765/auth/verify?token="+url.QueryEscape(token))
 if e!=nil {return fmt.Errorf("Meridian is not running. Open the installed Meridian window, request a new email link, and try again: %w",e)}
 defer res.Body.Close()
 if res.StatusCode!=http.StatusSeeOther || res.Header.Get("Location")!="/auth/complete"{
  return fmt.Errorf("Sign-in link could not be confirmed (status %d). Request a new one from Meridian",res.StatusCode)
 }
 return nil
}


const currentVersion = "0.2.13"
const localURL = "http://127.0.0.1:8765/"

func healthy() (string,bool) {
 client:=&http.Client{Timeout:800*time.Millisecond}
 resp,err:=client.Get(localURL+"api/health")
 if err!=nil{return "",false}
 defer resp.Body.Close()
 if resp.StatusCode!=200{return "",false}
 var state struct{App string; Version string}
 if json.NewDecoder(resp.Body).Decode(&state)!=nil{return "",false}
 if state.App!="Meridian"{return "",false}
 return state.Version,true
}

// Explicitly assign both icon sizes to the actual Win32 window and its
// registered class. The embedded EXE resource alone does not update this
// third-party WebView2 window class or the taskbar button.
func applyNativeIcon(w webview2.WebView, icoFile string) error {
 hwnd:=uintptr(w.Window())
 if hwnd==0{return fmt.Errorf("Meridian window handle is missing")}
 name,e:=syscall.UTF16PtrFromString(icoFile)
 if e!=nil{return e}
 lib:=syscall.NewLazyDLL("user32.dll")
 load:=lib.NewProc("LoadImageW")
 msg:=lib.NewProc("SendMessageW")
 class:=lib.NewProc("SetClassLongPtrW")
 big,_,_:=load.Call(0,uintptr(unsafe.Pointer(name)),1,32,32,0x10)
 small,_,_:=load.Call(0,uintptr(unsafe.Pointer(name)),1,16,16,0x10)
 if big==0 || small==0{return fmt.Errorf("could not load Meridian taskbar artwork from "+icoFile)}
 msg.Call(hwnd,0x80,1,big)
 msg.Call(hwnd,0x80,0,small)
 bigIndex:=int32(-14)
 smallIndex:=int32(-34)
 class.Call(hwnd,uintptr(bigIndex),big)
 class.Call(hwnd,uintptr(smallIndex),small)
 return nil
}

func presentNativeWindow(root string) {
 runtime.LockOSThread()
 defer runtime.UnlockOSThread()
 // A native application model ID groups running windows with Meridian's
 // own Start Menu shortcut, rather than Edge's taskbar identity.
 appID,_:=syscall.UTF16PtrFromString("Meridian.Desktop")
 syscall.NewLazyDLL("shell32.dll").NewProc("SetCurrentProcessExplicitAppUserModelID").
  Call(uintptr(unsafe.Pointer(appID)))
 userData:=filepath.Join(os.Getenv("LOCALAPPDATA"),"Meridian","WebView2")
 _=os.MkdirAll(userData,0700)
 w:=webview2.NewWithOptions(webview2.WebViewOptions{
  Debug:false,AutoFocus:true,DataPath:userData,
  WindowOptions:webview2.WindowOptions{
    Title:"Meridian",Width:1280,Height:850,IconId:2,Center:true,
  },
 })
 if w==nil{
  message("The native Meridian window needs Microsoft Edge WebView2 Runtime. Opening the dashboard in your browser instead.")
  _=exec.Command("rundll32.exe","url.dll,FileProtocolHandler",localURL).Start()
  return
 }
 defer w.Destroy()
 if err:=applyNativeIcon(w,filepath.Join(root,"assets","meridian-desktop-2026.ico"));err!=nil {
  message("Meridian's native window could not set its application icon: "+err.Error())
 }
 w.Navigate(localURL)
 w.Run()
}

func main(){
 exe,err:=os.Executable()
 if err!=nil {message("Could not locate Meridian application: "+err.Error());return}
 root:=filepath.Dir(exe)
 py:=filepath.Join(root,"runtime","python.exe")
 app:=filepath.Join(root,"meridian.py")
 if _,err:=os.Stat(py);err!=nil {message("The Meridian internal runtime is missing. Run the installer again.");return}
 if _,err:=os.Stat(app);err!=nil {message("Meridian application files are missing. Run the installer again.");return}

 if len(os.Args)>1 && strings.HasPrefix(strings.ToLower(os.Args[1]),"meridian:"){
   if e:=approveDesktopLink(os.Args[1]);e!=nil {message(e.Error());os.Exit(1)}
   return
 }

 logPath:=filepath.Join(os.Getenv("LOCALAPPDATA"),"Meridian","logs")
 _=os.MkdirAll(logPath,0700)
 log,err:=os.OpenFile(filepath.Join(logPath,"startup.log"),os.O_CREATE|os.O_APPEND|os.O_WRONLY,0600)
 if err!=nil {message("Cannot open Meridian startup log: "+err.Error());return}
 defer log.Close()
 fmt.Fprintf(log,"\n--- Meridian native window %s ---\n",time.Now().Format(time.RFC3339))

 var child *exec.Cmd
 if version,ok:=healthy();ok{
   if version!=currentVersion{message("A different Meridian version ("+version+") is still running. Close it and reopen Meridian "+currentVersion+".");return}
 }else{
   child=exec.Command(py,app,"--no-browser","--no-tray")
   child.Dir=root
   child.SysProcAttr=&syscall.SysProcAttr{HideWindow:true}
   child.Stdout=log;child.Stderr=log
   if e:=child.Start();e!=nil {message("Could not start Meridian: "+e.Error());return}
   defer func(){if child.Process!=nil{_ = child.Process.Kill();_ = child.Wait()}}()
   ready:=false
   for n:=0;n<80;n++{
     time.Sleep(150*time.Millisecond)
     if version,ok:=healthy();ok{
       if version==currentVersion{ready=true;break}
       message("Another Meridian version ("+version+") is already using the dashboard port.")
       return
     }
   }
   if !ready{message("Meridian service did not start. Details: "+filepath.Join(logPath,"startup.log"));return}
 }
 presentNativeWindow(root)
}
