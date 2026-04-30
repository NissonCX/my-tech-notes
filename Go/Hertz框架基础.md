# Hertz 框架基础

日期：2026-04-20
标签：Go, HTTP框架, Hertz, CloudWeGo, 微服务

## 问题

Hertz 是什么？适合什么场景？它和 `net/http`、Gin、Kitex 分别是什么关系？

## 回答

### 核心结论

Hertz 是 CloudWeGo 提供的 Go HTTP 框架，定位是：

- 面向 **HTTP 服务开发**，不是 RPC 框架
- 强调 **工程化能力 + 高并发场景下的性能表现**
- API 设计上接近 Gin，便于 Go Web 开发者上手

如果只记一句话：

> Hertz 解决的是“如何更高效、更工程化地写 HTTP 服务”，Kitex 解决的是“服务之间如何做高性能 RPC 调用”。

### 它在架构里的位置

| 组件 | 定位 | 常见协议 | 适用场景 |
|------|------|----------|----------|
| `net/http` | Go 标准库 HTTP 基础设施 | HTTP/1.x | 小型服务、学习原理、极简场景 |
| Gin | 通用 Web/REST 框架 | HTTP/1.x | 中小型 API、后台系统、社区生态优先 |
| Hertz | 高性能 HTTP 框架 | HTTP | 对性能、扩展性、治理能力要求更高的服务 |
| Kitex | RPC 框架 | Thrift / Protobuf 等 | 微服务之间的内部调用 |

### Hertz 的价值点

| 维度 | 说明 |
|------|------|
| 开发体验 | 路由、中间件、分组等接口设计贴近 Gin，上手成本较低 |
| 性能潜力 | 在部分高并发场景下，配合 CloudWeGo 生态可获得更好的吞吐与延迟表现 |
| 工程扩展 | 适合接入统一中间件、治理、代码生成与服务规范 |
| 生态协同 | 与 CloudWeGo 的 Kitex、Netpoll、代码生成工具配合较自然 |

### 典型使用方式

```go
package main

import (
    "context"

    "github.com/cloudwego/hertz/pkg/app"
    "github.com/cloudwego/hertz/pkg/app/server"
    "github.com/cloudwego/hertz/pkg/common/utils"
    "github.com/cloudwego/hertz/pkg/protocol/consts"
)

func main() {
    h := server.Default(server.WithHostPorts(":8080"))

    h.GET("/ping", func(c context.Context, ctx *app.RequestContext) {
        ctx.JSON(consts.StatusOK, utils.H{"message": "pong"})
    })

    h.Spin()
}
```

上面这段代码体现了 Hertz 的常见使用方式：

- 启动一个 HTTP 服务
- 注册路由
- 在 handler 中读取请求、写回响应

### 路由分组与中间件

```go
func main() {
    h := server.Default()

    v1 := h.Group("/api/v1", authMiddleware)
    v1.GET("/users", listUsers)
    v1.POST("/users", createUser)

    h.Spin()
}

func authMiddleware(c context.Context, ctx *app.RequestContext) {
    if len(ctx.GetHeader("Authorization")) == 0 {
        ctx.AbortWithStatusJSON(consts.StatusUnauthorized, utils.H{"error": "missing token"})
        return
    }
    ctx.Next(c)
}
```

这个模型和 Gin 很像，本质上是在做三件事：

- **路由分发**：决定哪个请求进入哪个 handler
- **中间件编排**：把鉴权、日志、限流、恢复等通用逻辑前置/后置处理
- **请求上下文管理**：在一次请求生命周期内传递数据

### 什么时候适合用 Hertz？

| 场景 | 是否适合 | 原因 |
|------|----------|------|
| 对外提供 HTTP API 的微服务 | 适合 | 框架能力完整，开发体验较好 |
| 团队已在使用 CloudWeGo 生态 | 很适合 | 与 Kitex 等组件衔接自然 |
| 需要统一治理和中间件体系 | 适合 | 便于沉淀内部规范 |
| 个人练手、小工具脚本 | 未必需要 | `net/http` 或 Gin 往往更轻 |
| 内部服务间高性能调用 | 不合适 | 这类场景更应优先考虑 Kitex/gRPC |

### 使用 Hertz 的边界

不要把 Hertz 理解成“所有项目都比 Gin 更优”的通用答案。实际选择时更看重：

- 团队是否已经熟悉它
- 是否确实需要更强的工程化和性能优化空间
- 是否要与 CloudWeGo 体系协同

如果项目简单、接口数量少、团队更熟悉标准库或 Gin，那么继续使用原有方案通常更划算。

## 一句话总结

Hertz 是一个偏工程化、面向高并发 HTTP 服务的 Go 框架；它解决的是 HTTP 层问题，不替代 Kitex 这类 RPC 框架。

## 相关问题

- Hertz 和 Gin 的最大区别是什么？ → 都是 HTTP 框架，但 Hertz 更强调在 CloudWeGo 生态中的性能与工程扩展能力。
- Hertz 和 Kitex 能一起用吗？ → 可以，常见方式是网关层用 Hertz，对内微服务调用用 Kitex。
- 新手学 Go Web 要先学哪个？ → 先理解 `net/http` 基础，再学 Gin 或 Hertz，会更容易建立心智模型。

## 技术拓展

### 一个常见的服务分层方式

```text
客户端 / 前端
    ↓ HTTP
Hertz（网关 / API 层）
    ↓ RPC
Kitex（内部服务层）
    ↓
数据库 / 缓存 / 消息队列
```

### 官方资源

- GitHub：`https://github.com/cloudwego/hertz`
- 文档：`https://www.cloudwego.io/docs/hertz/`
