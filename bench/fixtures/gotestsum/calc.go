// Package demo 是 gotestsum fixture 的被测代码。
//
// 只用标准库：这样 `go test` 不需要模块代理，fixture 在离线环境也能重跑。
package demo

// Add 返回两数之和。
func Add(a, b int) int { return a + b }

// Div 返回整数商；除数为 0 时返回 0（避免 panic，让测试只关心断言）。
func Div(a, b int) int {
	if b == 0 {
		return 0
	}
	return a / b
}

// IsEven 报告 n 是否为偶数。
func IsEven(n int) bool { return n%2 == 0 }
