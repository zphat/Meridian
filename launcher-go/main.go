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

func main(){
 exe,err:=os.Executable();if err!=nil {message("Unable to find Meridian installation: "+err.Error());return}
 root:=filepath.Dir(exe)
 py:=filepath.Join(root,"runtime","python.exe")
 app:=filepath.Join(root,"meridian.py")
 if _,err:=os.Stat(py);err!=nil {message("Meridian's internal runtime is missing. Run the Meridian installer again.");return}
 if _,err:=os.Stat(app);err!=nil {message("Meridian application files are missing. Run the installer again.");return}
 if len(os.Args)>1 && strings.HasPrefix(strings.ToLower(os.Args[1]),"meridian:"){
  if err:=approveDesktopLink(os.Args[1]);err!=nil {message(err.Error());os.Exit(1)}
  return
 }
 logPath:=filepath.Join(os.Getenv("LOCALAPPDATA"),"Meridian","logs")
 _=os.MkdirAll(logPath,0700)
 log,err:=os.OpenFile(filepath.Join(logPath,"startup.log"),os.O_CREATE|os.O_APPEND|os.O_WRONLY,0600)
 if err!=nil {message("Cannot open Meridian startup log: "+err.Error());return}
 defer log.Close()
 fmt.Fprintf(log,"\n--- Meridian launch %s ---\n",time.Now().Format(time.RFC3339))
 cmd:=exec.Command(py,app)
 cmd.Dir=root
 cmd.SysProcAttr=&syscall.SysProcAttr{HideWindow:true}
 cmd.Stdout=log;cmd.Stderr=log
 if err:=cmd.Start();err!=nil {message("Could not launch Meridian: "+err.Error());return}
 exited:=make(chan error,1)
 go func(){exited<-cmd.Wait()}()
 select {
 case e:=<-exited:
  if e!=nil {message("Meridian failed to start. Details: "+filepath.Join(logPath,"startup.log")+"\n"+e.Error())}
 case <-time.After(1800*time.Millisecond):
  // Python continues independently after this launcher closes.
 }
}
