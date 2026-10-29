package main

import (
 "fmt"
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
func main(){
 exe,err:=os.Executable();if err!=nil {message("Unable to find Meridian installation: "+err.Error());return}
 root:=filepath.Dir(exe)
 py:=filepath.Join(root,"runtime","python.exe")
 app:=filepath.Join(root,"meridian.py")
 if _,err:=os.Stat(py);err!=nil {message("Meridian's internal runtime is missing. Run the Meridian installer again.");return}
 if _,err:=os.Stat(app);err!=nil {message("Meridian application files are missing. Run the installer again.");return}
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
 }
}
