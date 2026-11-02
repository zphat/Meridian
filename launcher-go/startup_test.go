package main

import (
	"testing"
	"time"
)

func TestReadyWindowDoesNotRetry(t *testing.T) {
	ready, closed := make(chan struct{}), make(chan struct{})
	close(ready)
	guardStartup(ready, closed, time.Millisecond, 2*time.Millisecond,
		func() { t.Error("ready window was reloaded") }, func() { t.Error("ready window fell back") })
}

func TestClosedWindowDoesNotReopen(t *testing.T) {
	ready, closed := make(chan struct{}), make(chan struct{})
	close(closed)
	guardStartup(ready, closed, time.Millisecond, 2*time.Millisecond,
		func() { t.Error("closed window was reloaded") }, func() { t.Error("closing app opened a browser") })
}

func TestBlankWindowRetriesThenFallsBack(t *testing.T) {
	ready, closed := make(chan struct{}), make(chan struct{})
	var steps []string
	guardStartup(ready, closed, time.Millisecond, 20*time.Millisecond,
		func() { steps = append(steps, "retry") }, func() { steps = append(steps, "fallback") })
	if len(steps) != 2 || steps[0] != "retry" || steps[1] != "fallback" {
		t.Fatalf("blank-window recovery order: %v", steps)
	}
}

func TestRecoveredWindowStopsDeadline(t *testing.T) {
	ready, closed := make(chan struct{}), make(chan struct{})
	retried := false
	guardStartup(ready, closed, time.Millisecond, 20*time.Millisecond,
		func() { retried = true; close(ready) }, func() { t.Error("recovered window fell back") })
	if !retried {
		t.Fatal("did not retry")
	}
}
