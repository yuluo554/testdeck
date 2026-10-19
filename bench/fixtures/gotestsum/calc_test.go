package demo

import "testing"

func TestAdd(t *testing.T) {
	if Add(2, 3) != 5 {
		t.Fatalf("Add(2,3) = %d, want 5", Add(2, 3))
	}
}

func TestDivByZero(t *testing.T) {
	if Div(1, 0) != 0 {
		t.Fatalf("Div(1,0) = %d, want 0", Div(1, 0))
	}
}

func TestIsEven(t *testing.T) {
	for _, n := range []int{2, 4, 6} {
		if !IsEven(n) {
			t.Errorf("IsEven(%d) = false, want true", n)
		}
	}
}

// TestNotImplementedYetSubtract 故意跳过：让产物里带一条 skipped。
func TestNotImplementedYetSubtract(t *testing.T) {
	t.Skip("not implemented yet: Subtract")
}

// TestDeliberateFailureFixture 故意失败：让产物里带一条 failure。
func TestDeliberateFailureFixture(t *testing.T) {
	t.Errorf("deliberate failure fixture: want 7, got 6")
}
