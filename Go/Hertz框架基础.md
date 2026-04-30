# Hertz Go HTTP 框架

日期：2026-04-20
标签：Go, HTTP框架, 微服务, CloudWeGo

## 问题
go的http框架hertz是什么

## 回答

Hertz 是 CloudWeGo（字节跳动开源）推出的 **高性能 Go HTTP 框架**，专为构建微服务设计。

### 核心特点

| 特性 | 说明 |
|------|------|
| **高易用性** | API 设计借鉴 Gin/Echo，学习曲线平滑 |
| **高性能** | 默认使用字节自研网络库 Netpoll，QPS 和延迟优于标准 Go Net |
| **高扩展性** | 分层架构，支持协议扩展（HTTP1.1/2/3）、网络库切换 |
| **生产级** | 字节跳动内部大规模使用，稳定可靠 |

### 架构设计

```
┌─────────────────────────────────────────┐
│              应用层 (Handler)            │
├─────────────────────────────────────────┤
│              中间件层                     │
├─────────────────────────────────────────┤
│            路由层 (Route)                │
├─────────────────────────────────────────┤
│   协议层 (HTTP1.1 / HTTP2 / HTTP3)       │
├─────────────────────────────────────────┤
│   网络层 (Netpoll / Go Net 可切换)       │
└─────────────────────────────────────────┘
```

### 基础使用示例

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
    // 创建服务器（自带 recovery 中间件）
    h := server.Default(server.WithHostPorts(":8080"))

    // 注册路由
    h.GET("/ping", func(c context.Context, ctx *app.RequestContext) {
        ctx.JSON(consts.StatusOK, utils.H{"message": "pong"})
    })

    // 启动服务（支持优雅关闭）
    h.Spin()
}
```

### 路由分组与中间件

```go
func main() {
    h := server.Default()

    // API v1 分组 + 认证中间件
    v1 := h.Group("/api/v1", authMiddleware)
    {
        v1.GET("/users", listUsers)
        v1.POST("/users", createUser)
    }

    h.Spin()
}

func authMiddleware(c context.Context, ctx *app.RequestContext) {
    token := ctx.GetHeader("Authorization")
    if len(token) == 0 {
        ctx.AbortWithStatusJSON(consts.StatusUnauthorized, utils.H{"error": "missing token"})
        return
    }
    ctx.Next(c)  // 继续执行后续 handler
}
```

### 与其他框架对比

| 框架 | 性能 | 易用性 | 适用场景 |
|------|------|--------|----------|
| **Hertz** | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ | 微服务、高并发 |
| **Gin** | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | Web 应用、API |
| **Echo** | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ | 轻量级服务 |
| **标准 net/http** | ⭐⭐⭐ | ⭐⭐⭐ | 简单场景 |

## 相关问题
- Hertz 支持哪些协议？ → HTTP1.1、HTTP2、HTTP3（通过 QUIC）
- 如何切换网络库？ → 使用 `server.WithTransport()` 配置
- Hertz 有哪些常用中间件？ → Recovery、JWT、RequestID、BasicAuth、CORS 等

## 技术拓展

### CloudWeGo 生态

Hertz 是 CloudWeGo 微服务生态的一部分，配套组件包括：

- **Kitex**：高性能 RPC 框架（Thrift/Protobuf）
- **Netpoll**：自研网络库，非阻塞 I/O
- **CWGo**：代码生成工具

### 安装方式

```bash
go get github.com/cloudwego/hertz
```

### 官方资源

- GitHub：https://github.com/cloudwego/hertz
- 文档：https://www.cloudwego.io/docs/hertz/