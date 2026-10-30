package main

import (
	"archive/zip"
	"bytes"
	"context"
	"crypto/sha256"
	"embed"
	"fmt"
	"io"
	"net"
	"net/http"
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
	"strings"
	"syscall"
	"time"
	"unsafe"
)

//go:embed payload.zip
var files embed.FS

//go:embed shortcut-properties.ps1
var shortcutProperties string

const (
	runtimeSHA256 = "4acbed6dd1c744b0376e3b1cf57ce906f9dc9e95e68824584c8099a63025a3c3"
	appVersion    = "0.2.14"
	pyURL         = "https://www.python.org/ftp/python/3.12.10/python-3.12.10-embed-amd64.zip"
	title         = "Meridian Setup"
)

var user32 = syscall.NewLazyDLL("user32.dll")

func message(body string, flags uintptr) int {
	proc := user32.NewProc("MessageBoxW")
	t, _ := syscall.UTF16PtrFromString(title)
	b, _ := syscall.UTF16PtrFromString(body)
	r, _, _ := proc.Call(0, uintptr(unsafe.Pointer(b)), uintptr(unsafe.Pointer(t)), flags)
	return int(r)
}
func path() (string, error) {
	local := os.Getenv("LOCALAPPDATA")
	if local == "" {
		return "", fmt.Errorf("Windows LOCALAPPDATA directory is unavailable")
	}
	return filepath.Join(local, "Programs", "Meridian"), nil
}

// Extract into a private staging directory. Never modify the installed app
// until all new files are ready and the old native window has released its EXE.
func installPayload(dir string) error {
	data, err := files.ReadFile("payload.zip")
	if err != nil {
		return err
	}
	r, err := zip.NewReader(bytes.NewReader(data), int64(len(data)))
	if err != nil {
		return err
	}
	for _, f := range r.File {
		n := filepath.Clean(filepath.FromSlash(f.Name))
		if filepath.IsAbs(n) || n == ".." || strings.HasPrefix(n, ".."+string(os.PathSeparator)) {
			return fmt.Errorf("unsafe embedded path: %q", f.Name)
		}
		target := filepath.Join(dir, n)
		if f.FileInfo().IsDir() {
			if err := os.MkdirAll(target, 0755); err != nil {
				return err
			}
			continue
		}
		if err := os.MkdirAll(filepath.Dir(target), 0755); err != nil {
			return err
		}
		src, err := f.Open()
		if err != nil {
			return err
		}
		temp := target + ".new"
		dst, err := os.OpenFile(temp, os.O_WRONLY|os.O_CREATE|os.O_TRUNC, 0644)
		if err != nil {
			src.Close()
			return err
		}
		_, copyErr := io.Copy(dst, src)
		c1 := dst.Close()
		c2 := src.Close()
		if copyErr != nil {
			return copyErr
		}
		if c1 != nil {
			return c1
		}
		if c2 != nil {
			return c2
		}
		if err := os.Remove(target); err != nil && !os.IsNotExist(err) {
			return err
		}
		if err := os.Rename(temp, target); err != nil {
			return err
		}
	}
	return nil
}
func downloadRuntime(target string) error {
	sentinel := filepath.Join(target, ".meridian-python-ready")
	if _, e := os.Stat(sentinel); e == nil {
		return nil
	}
	if err := os.MkdirAll(target, 0755); err != nil {
		return err
	}
	client := http.Client{Timeout: 4 * time.Minute, CheckRedirect: func(req *http.Request, via []*http.Request) error {
		if len(via) > 5 {
			return fmt.Errorf("too many redirects")
		}
		if req.URL.Scheme != "https" {
			return fmt.Errorf("redirect to insecure URL refused")
		}
		return nil
	}}
	res, err := client.Get(pyURL)
	if err != nil {
		return fmt.Errorf("could not download the official Python runtime: %w", err)
	}
	defer res.Body.Close()
	if res.StatusCode != 200 {
		return fmt.Errorf("python.org returned HTTP %d", res.StatusCode)
	}
	const max = 35 << 20
	data, err := io.ReadAll(io.LimitReader(res.Body, max+1))
	if err != nil {
		return err
	}
	if len(data) > max || len(data) < 5<<20 {
		return fmt.Errorf("unexpected runtime download size: %d bytes", len(data))
	}
	hash := fmt.Sprintf("%x", sha256.Sum256(data))
	if !strings.EqualFold(hash, runtimeSHA256) {
		return fmt.Errorf("Python download failed official SHA-256 validation; refusing installation")
	}
	r, err := zip.NewReader(bytes.NewReader(data), int64(len(data)))
	if err != nil {
		return fmt.Errorf("invalid Python distribution: %w", err)
	}
	foundPy, foundSqlite := false, false
	for _, f := range r.File {
		n := filepath.Clean(filepath.FromSlash(f.Name))
		if filepath.IsAbs(n) || n == ".." || strings.HasPrefix(n, ".."+string(os.PathSeparator)) {
			return fmt.Errorf("unsafe Python archive path: %s", f.Name)
		}
		if strings.EqualFold(n, "python.exe") {
			foundPy = true
		}
		if strings.Contains(strings.ToLower(n), "_sqlite3.pyd") {
			foundSqlite = true
		}
	}
	if !foundPy || !foundSqlite {
		return fmt.Errorf("Python download is missing required components")
	}
	for _, f := range r.File {
		n := filepath.Clean(filepath.FromSlash(f.Name))
		dest := filepath.Join(target, n)
		if f.FileInfo().IsDir() {
			if err := os.MkdirAll(dest, 0755); err != nil {
				return err
			}
			continue
		}
		if err := os.MkdirAll(filepath.Dir(dest), 0755); err != nil {
			return err
		}
		source, err := f.Open()
		if err != nil {
			return err
		}
		temp := dest + ".part"
		out, err := os.Create(temp)
		if err != nil {
			source.Close()
			return err
		}
		_, copyErr := io.Copy(out, source)
		c1 := out.Close()
		c2 := source.Close()
		if copyErr != nil {
			return copyErr
		}
		if c1 != nil {
			return c1
		}
		if c2 != nil {
			return c2
		}
		if err := os.Remove(dest); err != nil && !os.IsNotExist(err) {
			return err
		}
		if err := os.Rename(temp, dest); err != nil {
			return err
		}
	}
	// The Python embeddable distro includes a ._pth file restricting the sys.path.
	// Our entry point is specified explicitly and stdlib/sqlite3 remain available.
	return os.WriteFile(sentinel, []byte("CPython 3.12.10 verified with SHA-256: "+hash+"\n"), 0644)
}
func quiet(name string, args ...string) error {
	ctx, cancel := context.WithTimeout(context.Background(), 45*time.Second)
	defer cancel()
	cmd := exec.CommandContext(ctx, name, args...)
	cmd.SysProcAttr = &syscall.SysProcAttr{HideWindow: true}
	out, e := cmd.CombinedOutput()
	if e != nil {
		return fmt.Errorf("%s: %w: %s", name, e, strings.TrimSpace(string(out)))
	}
	return nil
}
func psQuote(s string) string { return "'" + strings.ReplaceAll(s, "'", "''") + "'" }
func shortcuts(dir string, remove bool) error {
	appData := os.Getenv("APPDATA")
	profile := os.Getenv("USERPROFILE")
	if appData == "" || profile == "" {
		return fmt.Errorf("Windows profile directories not found")
	}
	start := filepath.Join(appData, "Microsoft", "Windows", "Start Menu", "Programs", "Meridian.lnk")
	desktop := filepath.Join(profile, "Desktop", "Meridian.lnk")
	var script string
	if remove {
		script = "Remove-Item -LiteralPath " + psQuote(start) + " -Force -ErrorAction SilentlyContinue; Remove-Item -LiteralPath " + psQuote(desktop) + " -Force -ErrorAction SilentlyContinue"
	} else {
		exe := filepath.Join(dir, "Meridian.exe")
		ico := filepath.Join(dir, "assets", "meridian-desktop-2026.ico")
		script = "$w=New-Object -ComObject WScript.Shell; $paths=@(" + psQuote(start) + "); $desk=[Environment]::GetFolderPath('DesktopDirectory'); if($desk -and (Test-Path -LiteralPath $desk)){$paths+=Join-Path $desk 'Meridian.lnk'}; foreach($p in $paths){ $s=$w.CreateShortcut($p); $s.TargetPath=" + psQuote(exe) + "; $s.WorkingDirectory=" + psQuote(dir) + "; $s.IconLocation=" + psQuote(ico) + "; $s.Description='Meridian Development Control Center'; $s.Save() }"
	}
	if !remove {
		script = shortcutProperties + "\n" + script + `; foreach($p in $paths){[MeridianShortcutProperties]::SetAppId($p,'Meridian.Desktop')}; [MeridianShortcutProperties]::Refresh()`
	}
	return quiet("powershell.exe", "-NoProfile", "-NonInteractive", "-Command", "$ErrorActionPreference='Stop'; "+script)
}
func registry(dir string, remove bool) error {
	key := `HKCU\Software\Microsoft\Windows\CurrentVersion\Uninstall\Meridian`
	if remove {
		return quiet("reg.exe", "delete", key, "/f")
	}
	pairs := [][3]string{
		{"DisplayName", "REG_SZ", "Meridian"},
		{"DisplayVersion", "REG_SZ", appVersion},
		{"Publisher", "REG_SZ", "Meridian"},
		{"InstallLocation", "REG_SZ", dir},
		{"UninstallString", "REG_SZ", `"` + filepath.Join(dir, "Uninstall-Meridian.exe") + `" --uninstall`},
		{"DisplayIcon", "REG_SZ", filepath.Join(dir, "assets", "meridian-desktop-2026.ico")},
		{"NoModify", "REG_DWORD", "1"},
	}
	for _, kv := range pairs {
		if err := quiet("reg.exe", "add", key, "/v", kv[0], "/t", kv[1], "/d", kv[2], "/f"); err != nil {
			return err
		}
	}
	return nil
}

// Register the per-user URL scheme; this stores no secrets.
func registerProtocol(dir string, remove bool) error {
	key := `HKCU\Software\Classes\meridian`
	if remove {
		return quiet("reg.exe", "delete", key, "/f")
	}
	command := `"` + filepath.Join(dir, "Meridian.exe") + `" "%1"`
	commands := [][]string{
		{"add", key, "/ve", "/t", "REG_SZ", "/d", "URL:Meridian sign-in link", "/f"},
		{"add", key, "/v", "URL Protocol", "/t", "REG_SZ", "/d", "", "/f"},
		{"add", key + `\shell\open\command`, "/ve", "/t", "REG_SZ", "/d", command, "/f"},
	}
	for _, args := range commands {
		if err := quiet("reg.exe", args...); err != nil {
			return err
		}
	}
	return nil
}

// Match full installation paths, not process names. v0.2.12 introduced a
// long-lived Meridian.exe window; stopping only Python leaves its EXE locked.
func stopPreviousMeridian(dir string) error {
	script := `$ErrorActionPreference='Stop'; try {
$launcher=` + psQuote(filepath.Join(dir, "Meridian.exe")) + `;
$app=` + psQuote(filepath.Join(dir, "meridian.py")) + `;
$runtime=` + psQuote(filepath.Join(dir, "runtime")) + `;
$candidates=@(Get-CimInstance Win32_Process -Filter "Name='Meridian.exe' OR Name='python.exe' OR Name='pythonw.exe'");
$owned=@($candidates | Where-Object {
  ($_.Name -ieq 'Meridian.exe' -and $_.ExecutablePath -ieq $launcher) -or
  ($_.Name -imatch '^pythonw?\.exe$' -and (
    $_.ExecutablePath -ieq (Join-Path $runtime 'python.exe') -or
    $_.ExecutablePath -ieq (Join-Path $runtime 'pythonw.exe') -or
    ($_.CommandLine -and $_.CommandLine -imatch ('(?:^|[\s\x22])'+[regex]::Escape($app)+'(?:$|[\s\x22])'))))
});
# Close native windows first, allowing their normal cleanup to stop Python.
foreach($p in $owned | Where-Object Name -IEQ 'Meridian.exe') {
  $process=Get-Process -Id $p.ProcessId -ErrorAction SilentlyContinue;
  if($process){$null=$process.CloseMainWindow(); $null=$process.WaitForExit(3000)}
};
foreach($p in $owned) {
  $process=Get-Process -Id $p.ProcessId -ErrorAction SilentlyContinue;
  if($process){
    try {$process.Kill()} catch {if(-not $process.HasExited){throw}};
    if(-not $process.WaitForExit(5000)){throw 'Meridian did not release its installed files'}
  }
}
} catch { [Console]::Error.WriteLine($_.Exception.ToString()); exit 1 }
# Get-Process -ErrorAction SilentlyContinue sets $? to false when normal
# native-window cleanup has already stopped Python. That is successful cleanup,
# not a setup failure. Terminating errors above still return a nonzero exit.
exit 0`
	if e := quiet("powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script); e != nil {
		return fmt.Errorf("could not stop a previous Meridian instance: %w", e)
	}
	return nil
}
func ensurePortFree() error {
	for n := 0; n < 20; n++ {
		conn, e := net.DialTimeout("tcp", "127.0.0.1:8765", 250*time.Millisecond)
		if e != nil {
			return nil
		}
		conn.Close()
		time.Sleep(100 * time.Millisecond)
	}
	return fmt.Errorf("Meridian's port 8765 is still occupied by another application. No application files were replaced")
}

// Retry brief Windows sharing violations (including antivirus scanners), but
// retain every old file until the complete replacement has succeeded.
func renameRetry(src, dst string) error {
	var err error
	for n := 0; n < 30; n++ {
		if err = os.Rename(src, dst); err == nil {
			return nil
		}
		time.Sleep(100 * time.Millisecond)
	}
	return err
}
func replacePayload(stage, dir string) error {
	backup, err := os.MkdirTemp(filepath.Dir(dir), ".meridian-rollback-")
	if err != nil {
		return err
	}
	type change struct {
		relative string
		hadOld   bool
	}
	var changes []change
	err = filepath.WalkDir(stage, func(source string, entry os.DirEntry, walkErr error) error {
		if walkErr != nil {
			return walkErr
		}
		if entry.IsDir() {
			return nil
		}
		rel, e := filepath.Rel(stage, source)
		if e != nil {
			return e
		}
		target := filepath.Join(dir, rel)
		old := filepath.Join(backup, rel)
		if e = os.MkdirAll(filepath.Dir(target), 0755); e != nil {
			return e
		}
		hadOld := false
		if _, e = os.Stat(target); e == nil {
			if e = os.MkdirAll(filepath.Dir(old), 0755); e != nil {
				return e
			}
			if e = renameRetry(target, old); e != nil {
				return fmt.Errorf("close Meridian and retry; Windows has locked %s: %w", rel, e)
			}
			hadOld = true
		} else if !os.IsNotExist(e) {
			return e
		}
		changes = append(changes, change{rel, hadOld})
		return renameRetry(source, target)
	})
	if err != nil {
		var failures []string
		for i := len(changes) - 1; i >= 0; i-- {
			c := changes[i]
			target := filepath.Join(dir, c.relative)
			if e := os.Remove(target); e != nil && !os.IsNotExist(e) {
				failures = append(failures, c.relative)
				continue
			}
			if c.hadOld {
				if e := renameRetry(filepath.Join(backup, c.relative), target); e != nil {
					failures = append(failures, c.relative)
				}
			}
		}
		if len(failures) > 0 {
			return fmt.Errorf("%w; old application files retained for recovery at %s (%s)", err, backup, strings.Join(failures, ", "))
		}
		_ = os.RemoveAll(backup)
		return fmt.Errorf("%w; previous application files restored", err)
	}
	_ = os.RemoveAll(backup)
	return nil
}
func install(silent bool) error {
	dir, err := path()
	if err != nil {
		return err
	}
	name, _ := syscall.UTF16PtrFromString(fmt.Sprintf("Local\\Meridian-Setup-%x", sha256.Sum256([]byte(strings.ToLower(dir)))))
	handle, _, lockError := syscall.NewLazyDLL("kernel32.dll").NewProc("CreateMutexW").Call(0, 0, uintptr(unsafe.Pointer(name)))
	if handle == 0 {
		return fmt.Errorf("could not lock the Meridian installer")
	}
	defer syscall.CloseHandle(syscall.Handle(handle))
	if lockError == syscall.Errno(183) {
		return fmt.Errorf("another Meridian installer is already running; finish that installation first")
	}
	if !silent && message("Install Meridian "+appVersion+" to your Windows account?\n\nThis is a normal Start Menu/Desktop installation. It downloads its own official Python runtime once (~11 MB); no developer tools or Python installation required.\n\nYour notes and project data will remain untouched during upgrades.", 0x24) != 6 {
		return nil
	}
	if err := os.MkdirAll(dir, 0755); err != nil {
		return err
	}
	stage, err := os.MkdirTemp(filepath.Dir(dir), ".meridian-stage-")
	if err != nil {
		return err
	}
	defer os.RemoveAll(stage)
	if err := installPayload(stage); err != nil {
		return err
	}
	self, err := os.Executable()
	if err != nil {
		return err
	}
	if err := copyFile(self, filepath.Join(stage, "Uninstall-Meridian.exe")); err != nil {
		return err
	}
	if err := downloadRuntime(filepath.Join(dir, "runtime")); err != nil {
		return err
	}
	// Run a local self-test with the bundled interpreter before registering the installation.
	probe := exec.Command(filepath.Join(dir, "runtime", "python.exe"), "-c", "import sqlite3, ssl, json; print('Meridian runtime OK')")
	probe.Dir = dir
	probe.SysProcAttr = &syscall.SysProcAttr{HideWindow: true}
	if out, e := probe.CombinedOutput(); e != nil {
		return fmt.Errorf("bundled runtime validation failed: %w: %s", e, strings.TrimSpace(string(out)))
	}
	if err := stopPreviousMeridian(dir); err != nil {
		return err
	}
	if err := ensurePortFree(); err != nil {
		return err
	}
	if err := replacePayload(stage, dir); err != nil {
		return err
	}
	if err := shortcuts(dir, false); err != nil {
		return err
	}
	if err := registry(dir, false); err != nil {
		return err
	}
	if err := registerProtocol(dir, false); err != nil {
		return err
	}
	if !silent {
		message("Meridian "+appVersion+" is installed.\n\nThe application will open now. Enter your existing account password and request an eight-digit email code. First-time setup requires a Resend API key.\n\nYour notes and email settings have been preserved.", 0x40)
		cmd := exec.Command(filepath.Join(dir, "Meridian.exe"))
		cmd.Dir = dir
		cmd.SysProcAttr = &syscall.SysProcAttr{HideWindow: true}
		if err := cmd.Start(); err != nil {
			return fmt.Errorf("installed successfully, but couldn't open Meridian: %w", err)
		}
	}
	return nil
}
func copyFile(src, dst string) error {
	in, e := os.Open(src)
	if e != nil {
		return e
	}
	defer in.Close()
	out, e := os.Create(dst)
	if e != nil {
		return e
	}
	_, e = io.Copy(out, in)
	if e2 := out.Close(); e == nil {
		e = e2
	}
	return e
}
func uninstall() error {
	_, e := path()
	if e != nil {
		return e
	}
	if message("Uninstall Meridian?\n\nYour project notes and database will be preserved in your user profile.", 0x24) != 6 {
		return nil
	}
	self, e := os.Executable()
	if e != nil {
		return e
	}
	temp := filepath.Join(os.TempDir(), fmt.Sprintf("Meridian-Uninstall-%d.exe", time.Now().UnixNano()))
	if e := copyFile(self, temp); e != nil {
		return e
	}
	cmd := exec.Command(temp, "--uninstall-worker")
	cmd.SysProcAttr = &syscall.SysProcAttr{HideWindow: true}
	return cmd.Start()
}
func uninstallWorker() error {
	dir, e := path()
	if e != nil {
		return e
	}
	time.Sleep(1200 * time.Millisecond)
	if e := stopPreviousMeridian(dir); e != nil {
		return e
	}
	_ = shortcuts(dir, true)
	_ = registry(dir, true)
	_ = registerProtocol(dir, true)
	if e := os.RemoveAll(dir); e != nil {
		return e
	}
	message("Meridian has been uninstalled. Your notes and database were preserved.", 0x40)
	return nil
}
func main() {
	if runtime.GOOS != "windows" {
		fmt.Println("Windows only")
		return
	}
	var e error
	if len(os.Args) > 1 {
		switch os.Args[1] {
		case "--uninstall":
			e = uninstall()
		case "--uninstall-worker":
			e = uninstallWorker()
		case "--silent":
			e = install(true)
		default:
			e = fmt.Errorf("unknown argument")
		}
	} else {
		e = install(false)
	}
	if e != nil {
		body := "Meridian setup couldn't finish:\n\n" + e.Error() + "\n\nNo existing project notes have been deleted."
		logs := filepath.Join(os.Getenv("LOCALAPPDATA"), "Meridian", "logs")
		_ = os.MkdirAll(logs, 0700)
		_ = os.WriteFile(filepath.Join(logs, "setup.log"), []byte(time.Now().Format(time.RFC3339)+"\n"+body+"\n"), 0600)
		// Automated verification must fail promptly instead of hanging on a modal.
		if len(os.Args) < 2 || os.Args[1] != "--silent" {
			message(body, 0x10)
		}
		os.Exit(1)
	}
}
