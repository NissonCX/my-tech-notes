---
date: 2026-10-31
tags: [Go, 接口, 方法接收者, 依赖注入]
---

# Go 方法接收者与接口

## 问题

Go 没有 Java 的 class，`func (s *Service) List(...)` 到底是什么？类型、实例、构造器、接口和具体方法如何连接？

## 回答

### 核心结论

1. Go 方法就是带显式接收者的函数。类型定义数据形状和方法集，实例提供方法执行时使用的字段值。
2. Go 接口由方法集隐式满足。编译器比较方法名、参数和返回值；函数体不参与接口匹配。
3. 小服务通常在 `main` 中从底层依赖向上显式装配：`sql.DB -> Store -> Service -> caller`。

### 方法、接收者和实例

```go
func (s *Service) List(ctx context.Context) ([]WorkOrder, error)
```

- `Service` 是基础类型。
- `*Service` 是接收者类型。
- `s` 是接收者变量，类型为 `*Service`。
- `List` 属于 `*Service` 的方法集。
- `s` 只存在于方法体内部。

方法调用仍然需要具体实例：

```go
service := NewService(store, actors)
orders, err := service.List(ctx)
```

此时 `service` 的指针作为接收者传入方法。

### 构造器不是语言关键字

`NewService`、`NewHandler` 是 Go 的命名约定，不是特殊语法。

```go
func NewHandler(service *Service) *Handler {
	return &Handler{service: service}
}
```

等价于：

```go
func NewHandler(service *Service) *Handler {
	handler := Handler{}
	handler.service = service
	return &handler
}
```

构造器只负责创建实例和填写字段。它不负责自动查找依赖。

### 接口如何连接具体方法

接口声明：

```go
type Store interface {
	List(ctx context.Context, tenantID int64) ([]StoredWorkOrder, error)
}
```

具体实现：

```go
func (s *MySQLStore) List(
	ctx context.Context,
	tenantID int64,
) ([]StoredWorkOrder, error) {
	// SQL、Scan 和错误处理
}
```

去掉接收者后，二者具有相同方法签名：

```text
List(context.Context, int64) ([]StoredWorkOrder, error)
```

因此 `*MySQLStore` 自动满足 `Store`。不需要写 `implements Store`。

### 为什么同名 List 会产生混淆

项目里实际有三个不同的方法：

```text
Handler.List        HTTP 适配器
Service.List        业务用例
MySQLStore.List     数据库查询
```

调用关系：

```text
Handler.List
  -> h.service.List(...)
  -> Service.List
  -> s.store.List(...)
  -> MySQLStore.List
```

`Service.List` 不属于 `Store`。它通过 `s.store` 调用另一个类型的 `List`。

### 从零装配

```text
读取配置
-> 打开 sql.DB
-> 创建 MySQLStore 和 ActorProvider
-> 创建 Service
-> 创建调用方 Handler
-> 启动 HTTP Server
```

```go
db, err := platform.OpenMySQL(ctx, dsn)
if err != nil {
	return err
}

store := workorder.NewMySQLStore(db)
actorProvider := identity.NewDemoProvider(db)
service := workorder.NewService(store, actorProvider)
handler := workorder.NewHandler(service)
```

创建方向从底层向上，运行时调用方向从外向内。

### 新 Service 的思考顺序

1. 定义业务输入和输出。
2. 写 Service 需要完成的步骤。
3. 从步骤中识别它需要调用哪些外部方法。
4. 把这些调用提取成窄接口。
5. 在 MySQL/其他适配器中实现这些方法。
6. 在 `main` 中创建具体实现并传给 Service。

接口应根据 Service 的真实调用产生，不要提前创建万能 Repository。

## 常见误解

| 误解 | 纠正 |
|---|---|
| Go 没有对象 | Go 有类型实例；只是没有 Java 式 class/Object 根类型 |
| `s` 的类型是 `Service` | 本例中 `s` 的类型是 `*Service` |
| 方法真的挂载到每个实例上 | 方法在编译期关联到类型；实例只保存字段 |
| Service.List 和 MySQLStore.List 是同一方法 | 同名，但接收者类型不同，是不同方法 |
| 接口只写方法名就够 | 必须写完整方法签名 |
| 方法体必须与接口一致 | 只比较方法名、参数和返回值，函数体不参与匹配 |
| 构造器会自动注入依赖 | `NewXxx` 只是普通函数，依赖必须由调用方传入 |

## 相关问题

- **为什么用 `*Service`？** → 避免复制 Service，并让同一实例的字段和方法调用保持一致。
- **没有 Spring 还能依赖注入吗？** → 能，构造器参数和字段赋值就是依赖注入。
- **接口应该定义在哪里？** → 定义在真正使用该行为的调用方附近，只包含调用方需要的方法。
- **HTTP 和这整套关系有关吗？** → 无关。Handler 只是一个外部调用方，同一 Service 也可以由 CLI 或测试直接调用。

## 延伸阅读

- [Go Specification: Method declarations](https://go.dev/ref/spec#Method_declarations)
- [Go Specification: Method sets](https://go.dev/ref/spec#Method_sets)
- [Go Specification: Interface types](https://go.dev/ref/spec#Interface_types)
- [[Go项目结构与CRUD分层调研]]
- FixFlow Go: [`service.go`](../../../projects/fixflow-go/internal/workorder/service.go)
- FixFlow Go: [`store_mysql.go`](../../../projects/fixflow-go/internal/workorder/store_mysql.go)
