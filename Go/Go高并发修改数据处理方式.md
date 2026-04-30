# Go 高并发修改数据的处理方式

日期：2026-04-20
标签：Go, 并发, channel, 锁, atomic, 数据竞争

## 问题

多个 goroutine 同时修改同一份数据时，Go 应该怎么处理？什么时候用锁，什么时候用 channel？

## 回答

### 核心结论

先说结论：**Go 并不是“只推荐 channel，不推荐锁”**。真正重要的是根据共享数据的形态和业务模型来选。

常见选择逻辑：

- **临界区很小、共享状态简单**：优先考虑 `sync.Mutex`
- **只是做计数、标记位这类简单原子更新**：考虑 `atomic`
- **想把状态收口到单个 goroutine 管理，或天然是事件流模型**：考虑 `channel`

### 为什么会出问题

多个 goroutine 同时改同一个变量，如果没有同步机制，就会出现数据竞争。

例如：

```go
counter++
```

它不是单个不可分割动作，而通常可以理解成：

1. 读取旧值
2. 加一
3. 写回新值

多个 goroutine 交错执行时，就可能丢失更新。

### 方案一：互斥锁

```go
package main

import (
    "fmt"
    "sync"
)

func main() {
    var counter int
    var mu sync.Mutex
    var wg sync.WaitGroup

    for i := 0; i < 1000; i++ {
        wg.Add(1)
        go func() {
            defer wg.Done()
            mu.Lock()
            counter++
            mu.Unlock()
        }()
    }

    wg.Wait()
    fmt.Println(counter)
}
```

互斥锁的核心思想是：

- 数据可以被多个 goroutine 访问
- 但同一时刻只允许一个 goroutine 进入临界区

优点：

- 简单直接
- 对简单共享状态很高效

风险：

- 忘记加锁或解锁会出问题
- 锁顺序不当可能死锁
- 临界区过大时会放大竞争

### 方案二：atomic

```go
package main

import (
    "fmt"
    "sync"
    "sync/atomic"
)

func main() {
    var counter int64
    var wg sync.WaitGroup

    for i := 0; i < 1000; i++ {
        wg.Add(1)
        go func() {
            defer wg.Done()
            atomic.AddInt64(&counter, 1)
        }()
    }

    wg.Wait()
    fmt.Println(counter)
}
```

适用场景：

- 计数器
- 开关位
- 很简单的无锁状态更新

它不适合承载复杂业务规则；一旦需要跨多个字段维持一致性，`atomic` 往往就不够用了。

### 方案三：channel + 单 goroutine 管状态

```go
package main

import "fmt"

func main() {
    requests := make(chan int, 100)
    done := make(chan int)

    for i := 0; i < 1000; i++ {
        go func() {
            requests <- 1
        }()
    }

    go func() {
        counter := 0
        for i := 0; i < 1000; i++ {
            counter += <-requests
        }
        done <- counter
    }()

    fmt.Println(<-done)
}
```

这个模型的核心思想是：

- 不让所有 goroutine 直接碰共享数据
- 而是把“修改请求”发给唯一的状态持有者处理

它很像 actor 或事件循环思路，优点是状态边界清晰。

### 三种方式怎么选

| 方案 | 适合什么 | 优点 | 注意点 |
|------|----------|------|--------|
| `sync.Mutex` | 简单共享状态 | 直接、常常足够快 | 注意锁粒度与死锁 |
| `atomic` | 简单计数或标记位 | 开销低 | 只适合很小的原子更新 |
| `channel` | 所有权转移、事件流、状态收口 | 模型清晰 | 增加通信与编排成本 |

### 一个常见误区

很多人看到 Go 官方那句 “Do not communicate by sharing memory; instead, share memory by communicating.”，就误以为：

> 以后都不要用锁，只能用 channel。

这其实是误解。更准确的理解是：

- 当问题天然适合“通过消息传递来管理状态”时，channel 很优雅
- 当问题只是“保护一个很小的共享变量”时，锁往往更简单也更自然

### 银行转账例子怎么理解

如果你用两个账户余额举例，锁和 channel 的确都能建模，但要注意：

- 真正的转账问题往往不只是“扣一下、加一下”
- 还要考虑余额校验、失败回滚、一致性和事务边界

所以在教学例子里，channel 模型更适合用来说明：

> “让某个 goroutine 成为状态唯一所有者”

而不是说明“这样就天然等于完整事务方案”。

## 一句话总结

Go 并发修改数据时，没有绝对正确的唯一方案：简单共享状态优先锁，简单原子操作优先 `atomic`，需要把状态集中管理或按事件流处理时再优先考虑 `channel`。

## 相关问题

- `channel` 一定比锁更安全、更高级吗？ → 不一定，它更适合某些模型，但并不天然优于锁。
- 为什么简单计数器很多时候直接用锁或 `atomic`？ → 因为问题本身很小，没必要引入额外消息编排。
- 什么时候要警惕 channel 方案？ → 当通信链路过长、状态拆分过多、协程编排复杂时，代码也可能变难维护。

## 技术拓展

### 一个实用决策口诀

- 小共享状态：先想 `Mutex`
- 单数值更新：先想 `atomic`
- 状态归一个主人：再想 `channel`

先选最简单、最容易被团队正确维护的方案，通常比“追求风格纯粹”更重要。
