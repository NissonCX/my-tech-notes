# Go 高并发修改数据的处理方式

日期：2026-04-20
标签：Go, 并发, channel, 锁, 数据竞争

## 问题

多个 goroutine 同时修改一个数据，Go 如何处理？为什么推荐用 channel 而不是锁？

## 回答

### 场景：计数器

1000 个 goroutine 同时对计数器加 1，最终结果应该是 1000。

---

## 方案一：共享内存 + 锁

```go
package main

import (
    "fmt"
    "sync"
)

func main() {
    var counter int          // 共享内存
    var mu sync.Mutex        // 锁
    var wg sync.WaitGroup    // 等待所有 goroutine 完成
    
    for i := 0; i < 1000; i++ {
        wg.Add(1)
        go func() {
            mu.Lock()        // 加锁
            counter++        // 修改共享内存
            mu.Unlock()      // 解锁
            wg.Done()
        }()
    }
    
    wg.Wait()
    fmt.Println(counter)     // 输出：1000
}
```

**本质**：所有人抢一把钥匙，拿到钥匙的人才能进去改数据。

**问题**：
- 锁竞争：1000 个 goroutine 都要抢锁，大部分时间在等待
- 程序员必须记住：每次访问都要加锁，漏了就出 bug

---

## 方案二：channel（Go 推荐）

```go
package main

import "fmt"

func main() {
    requests := make(chan int, 100)   // 请求 channel
    results := make(chan int)         // 结果 channel
    
    // 启动 1000 个 goroutine 发送请求
    for i := 0; i < 1000; i++ {
        go func() {
            requests <- 1             // 发送"我要加1"的请求
        }()
    }
    
    // 一个 goroutine 作为"计数器管理员"
    go func() {
        counter := 0                  // 数据只有一个主人
        for i := 0; i < 1000; i++ {
            counter += <-requests     // 处理请求
        }
        results <- counter            // 发送最终结果
    }()
    
    final := <-results                // 主 goroutine 等待结果
    fmt.Println(final)                // 输出：1000
}
```

**本质**：数据只有一个主人（管理员 goroutine），其他人发送"请求"，主人处理请求。

---

## 本质对比

### 用类比理解

| 方案 | 类比 | 问题 |
|------|------|------|
| 锁 | 1000 人抢一把钥匙进房间改数据 | 大部分时间在排队，钥匙忘了归还就死锁 |
| channel | 1000 人写纸条扔进箱子，一人负责改数据 | 没人抢，数据安全，但要多一步"传递" |

**锁的本质**：把"访问权"限制为一个人，但"谁在访问"不确定。

**channel 的本质**：把"修改权"固定给一个人，其他人只能"请求"。

### 数据流动的结构

```
1000 个 goroutine           1 个管理员 goroutine         主 goroutine
     │                           │                           │
     │  requests <- 1            │  counter += <-requests    │
     │──────────────────────────►│                           │
     │                           │                           │
     │                           │  results <- counter       │
     │                           │──────────────────────────►│
     │                           │                           │  final := <-results
```

**本质**：数据流动形成清晰的管道，不存在"同时访问"。

---

## 性能对比

| 指标 | 锁 | channel |
|------|----|---------|
| 锁竞争 | 高（1000 人抢一把锁） | 无（数据只有一个主人） |
| 数据复制 | 无（直接修改） | 有（消息传递要复制） |
| 可扩展性 | 差（锁竞争加剧） | 好（增加管理员数量即可） |

**tradeoff**：
- channel 有数据复制的开销，但避免了锁竞争
- 对于简单计数器，锁可能更快（复制 1000 个 int 也有开销）
- 对于复杂逻辑，channel 更安全、更易维护

---

## 扩展：多个管理员

请求量太大时，可以启动多个管理员分片处理：

```go
package main

import "fmt"

func main() {
    requests := make(chan int, 1000)
    results := make(chan int, 10)
    
    // 启动 10 个管理员
    for i := 0; i < 10; i++ {
        go func() {
            counter := 0
            for req := range requests {    // 持续接收请求
                counter += req
            }
            results <- counter              // 发送自己的计数结果
        }()
    }
    
    // 发送 10000 个请求
    for i := 0; i < 10000; i++ {
        requests <- 1
    }
    close(requests)                        // 关闭 channel，通知管理员停止
    
    // 收集所有管理员的结果
    total := 0
    for i := 0; i < 10; i++ {
        total += <-results
    }
    fmt.Println(total)                     // 输出：10000
}
```

**本质**：把"一个管理员"扩展成"一组管理员"，数据分片处理。

类比：
```
锁：10000 人抢一把钥匙 → 拥堵
channel + 多管理员：10000 人把纸条扔进箱子，10 个管理员各自处理 → 分流
```

---

## 真实场景：银行转账

### 方案一：锁（容易出错）

```go
type Account struct {
    balance int
    mu      sync.Mutex
}

func Transfer(from, to *Account, amount int) {
    from.mu.Lock()
    to.mu.Lock()          // 如果另一个转账先锁了 to，再锁 from → 死锁！
    from.balance -= amount
    to.balance += amount
    to.mu.Unlock()
    from.mu.Unlock()
}
```

**问题**：
- 锁顺序不对 → 死锁（A→B 和 B→A 同时发生）
- 忘记解锁 → 死锁
- 加锁范围太大 → 性能差

### 方案二：channel（逻辑清晰）

```go
type Account struct {
    balance int
    ch      chan func(int) int   // "操作请求" channel
}

func (a *Account) Start() {
    go func() {
        for op := range a.ch {    // 只有这个 goroutine 能访问 balance
            a.balance = op(a.balance)
        }
    }()
}

func Transfer(from, to *Account, amount int) {
    from.ch <- func(b int) int { return b - amount }  // 发送"减钱"请求
    to.ch <- func(b int) int { return b + amount }    // 发送"加钱"请求
}
```

**本质**：
- 每个账户有一个"管理员 goroutine"
- 转账只是发送两个请求（一个减、一个加）
- 不存在死锁，因为没有人"等待锁"

---

## 一句话总结

**锁的本质**：强制排队，把复杂性推给程序员管理。

**channel 的本质**：固定主人，把复杂性封装在机制里，形成清晰的"请求-处理"管道。

**选择建议**：
- 简单计数器、高频更新 → 锁更快（数据复制开销大于锁开销）
- 复杂逻辑、多个资源、团队协作 → channel 更安全（逻辑清晰，不易出错）

---

## 相关问题

### channel 的缓冲大小怎么选择？
→ 无缓冲：强同步，发送方必须等接收方准备好。有缓冲：异步，缓冲区满了才阻塞。高频场景用缓冲区减少阻塞，但要防止缓冲区溢出。

### 多管理员方案怎么保证数据一致性？
→ 每个管理员只处理一部分请求，最后汇总。如果要保证实时一致性（比如查询余额），需要增加一个"查询 channel"，管理员返回当前值。

### channel 和消息队列（Kafka/RabbitMQ）有什么区别？
→ channel 是进程内的，消息队列是跨进程的。channel 用于 goroutine 间通信，消息队列用于服务间通信。channel 更轻量，消息队列更持久。