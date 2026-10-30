package main

import (
	"os"
	"path/filepath"
	"syscall"
	"testing"
)

func TestReplacementRollsBackWhenWindowsLocksAFile(t *testing.T) {
	root := t.TempDir()
	stage := filepath.Join(root, "stage")
	installed := filepath.Join(root, "app")
	for _, dir := range []string{stage, installed} {
		if e := os.Mkdir(dir, 0755); e != nil {
			t.Fatal(e)
		}
	}
	for _, name := range []string{"a.txt", "z.exe"} {
		if e := os.WriteFile(filepath.Join(stage, name), []byte("new"), 0644); e != nil {
			t.Fatal(e)
		}
		if e := os.WriteFile(filepath.Join(installed, name), []byte("original"), 0644); e != nil {
			t.Fatal(e)
		}
	}
	file, _ := syscall.UTF16PtrFromString(filepath.Join(installed, "z.exe"))
	handle, e := syscall.CreateFile(file, syscall.GENERIC_READ, 0, nil, syscall.OPEN_EXISTING, 0, 0)
	if e != nil {
		t.Fatal(e)
	}
	err := replacePayload(stage, installed)
	syscall.CloseHandle(handle)
	if err == nil {
		t.Fatal("locked file should fail replacement")
	}
	for _, name := range []string{"a.txt", "z.exe"} {
		b, e := os.ReadFile(filepath.Join(installed, name))
		if e != nil || string(b) != "original" {
			t.Fatalf("%s was not restored: %s %v", name, b, e)
		}
	}
}
func TestReplacementKeepsUnrelatedFiles(t *testing.T) {
	root := t.TempDir()
	stage := filepath.Join(root, "stage")
	installed := filepath.Join(root, "app")
	os.Mkdir(stage, 0755)
	os.Mkdir(installed, 0755)
	os.WriteFile(filepath.Join(stage, "app.txt"), []byte("updated"), 0644)
	os.WriteFile(filepath.Join(installed, "keep.txt"), []byte("preserved"), 0644)
	if err := replacePayload(stage, installed); err != nil {
		t.Fatal(err)
	}
	if b, e := os.ReadFile(filepath.Join(installed, "keep.txt")); e != nil || string(b) != "preserved" {
		t.Fatal("unrelated file changed")
	}
	if b, e := os.ReadFile(filepath.Join(installed, "app.txt")); e != nil || string(b) != "updated" {
		t.Fatal("new file not installed")
	}
}
