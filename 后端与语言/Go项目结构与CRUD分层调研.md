---
date: 2026-10-31
tags: [Go, 后端架构, CRUD, 分层架构, 依赖注入, MySQL, 多租户]
---

# Go 项目结构与 CRUD 分层调研

## 核心结论

1. Go 没有官方规定的 Controller -> Service -> DAO 目录模板；官方更关心 package 边界、显式依赖、接口由消费者定义，以及错误和 `context` 的传递。
2. 分层思想仍然成立，但落点是“HTTP 适配器 -> application/use case -> domain -> store/repository -> MySQL”，事务边界由业务原子性决定，不需要 Spring 式容器或 `@Transactional`。
3. 对 FixFlow 的第一版，建议使用 `net/http`、`database/sql`、手工构造依赖、package-by-feature；把 handler、service、repository 先放在同一个 feature package 的不同文件中，等复杂度出现后再拆子包或引入 Chi、sqlc、Fx 等工具。

## 先给 Java 开发者一个映射

这不是一一等价，但可以作为阅读 Go 服务代码的起点：

| Java / Spring 常见角色 | Go 中常见对应物 | 关键差异 |
|---|---|---|
| `Controller` | `http.HandlerFunc` 或框架 handler | HTTP 解码、路径参数、状态码通常留在 handler；不要默认创建 `Controller` 接口 |
| `@Service` / use case | 普通 struct + 方法，例如 `workorder.Service` | 没有注解扫描；依赖从构造函数参数进入 |
| Repository / DAO | concrete store/repository，通常是 struct | SQL、行扫描、数据库错误翻译都在这一层 |
| Entity / DTO | domain struct / HTTP DTO / row struct | 不必全项目共用一个大 Model；边界处做简单映射 |
| Spring IoC | `main` 中的构造器调用 | 显式依赖优先；大型程序才需要 Wire/Fx |
| `@Transactional` | `BeginTx`/`Commit`、`WithTx(ctx, fn)` 等 | 事务边界要写出来；数据库事务通常通过 `*sql.Tx` 或 context 传播 |
| `@ControllerAdvice` | handler 层的错误映射函数 | 用 `errors.Is/As` 分类，不比较错误字符串 |
| JPA / MyBatis Mapper | `database/sql`、sqlx、sqlc、GORM 等 | Go 没有必须使用 ORM 的默认规则 |

Go 的结构通常不是“先用接口描述所有类”，而是“先写 concrete type，在真正需要替换或测试的边界再引入小接口”。官方 Go Code Review Comments 明确建议：接口一般放在使用它的 package，而不是实现它的 package；实现方通常返回 concrete type，并且不要在真正使用前预定义接口（[Go Code Review Comments: Interfaces](https://go.dev/wiki/CodeReviewComments#interfaces)）。

## 官方规范到底规定了什么

### 1. 官方只给布局下限，不给分层模板

Go 官方《Organizing a Go module》对 server project 的建议是：服务器逻辑的 Go package 放在 `internal`，可执行命令放在 `cmd`。它还建议尽量把 package 放进 `internal`，这样外部模块不能依赖内部 API，重构更自由（[Organizing a Go module](https://go.dev/doc/modules/layout#server-project)）。

官方没有说必须创建 `controller/`、`service/`、`repository/`、`domain/`、`dto/` 五层目录。相反，Go 博客《Organizing Go code》提醒：package 既要避免变成什么都装的 grab bag，也不要拆得过细，否则会陷入接口设计而不是完成任务；package 大小没有硬性规则（[Organizing Go code](https://go.dev/blog/organizing-go-code)）。

结论：

- `cmd/` 和 `internal/` 是有明确 Go 语义的约定。
- `controller/service/repository` 是常见工程分层，不是语言要求。
- “每个 struct 一个接口、每个接口一个 mock、每个实体一个 repository”不是 Go 默认风格。
- Google Go Style 还建议避免 `util`、`common`、`helper`、`model` 这类缺乏信息量的 package 名，因为 package 名应当是内容的有效前缀（[Google Go Style: Package names](https://google.github.io/styleguide/go/decisions#package-names)）。这也是小服务不宜先造一排放之四海而皆准的技术层 package 的原因之一。

### 2. 接口是行为边界，不是 Java 类型的替代品

Effective Go 把接口定义为“能做什么”的描述，并指出单方法或双方法接口在 Go 中很常见（[Effective Go: Interfaces](https://go.dev/doc/effective_go#interfaces_and_types)）。因此更常见的 Go 接口形状是：

```go
type workOrderStore interface {
    CreateWithEvent(ctx context.Context, wo WorkOrder, event Event) (WorkOrder, error)
}
```

而不是给每个 entity 自动生成：

```go
type WorkOrderService interface {
    Create(...)
    Get(...)
    Update(...)
    Delete(...)
    List(...)
}
```

后者不是错误，但通常没有收益，直到调用方确实存在多个实现或需要稳定解耦。

### 3. 错误、上下文和取消是控制流的一部分

官方建议用 `errors.Is` / `errors.As` 沿错误链判断类别和类型（[errors package](https://pkg.go.dev/errors#Is)）。Uber Go Style Guide 也给出了相同的工程规则：调用方需要匹配错误时，使用 sentinel error 或具体错误类型；在上文需要保留时用 `%w` 包装（[Uber Go Style Guide: Errors](https://github.com/uber-go/guide/blob/1d60a91aa5e87d443002e23c21903c49489dbde5/style.md#error-types)）。

`context.Context` 用来传请求作用域的取消信号、截止时间和少量请求元数据，例如身份和授权 token；不要把它当成全局变量袋（[Go Concurrency Patterns: Context](https://go.dev/blog/context)）。数据库调用应使用 `ExecContext`、`QueryContext`、`BeginTx` 这类带 `ctx` 的 API（[database/sql](https://pkg.go.dev/database/sql)）。

## `project-layout` 不是官方标准

`golang-standards/project-layout` 是社区维护的布局集合，不是 Go 核心团队定义的标准。它的 README 原文写明：

> This is **NOT an official standard defined by the core Go dev team**.

它还明确说，如果是学习 Go、PoC 或简单项目，这套结构是 overkill；对简单项目，一个 `main.go` 加 `go.mod` 就足够（[project-layout README, pinned commit](https://github.com/golang-standards/project-layout/blob/a9d6fae7015527b10550ebb6d6b71a71b1ef5ea7/README.md#L25-L37)）。

因此：

- 可以参考它认识 `cmd/`、`internal/`、`pkg/` 等目录。
- 不要因为名字里有 “standards” 就认定它是官方标准。
- 更不要把 `pkg/`、`configs/`、`deployments/`、`test/`、`scripts/` 全部初始化一遍；FixFlow 只需要当前真正使用的目录。

## 成熟项目里的真实做法

以下结论来自源码快照，不是对项目整体架构的完美化描述。大型项目通常同时存在新设计、legacy 代码和迁移期代码。

### Grafana：按 feature 组织，API、service、store 分开

Grafana 的 team 功能是一个较清楚的 feature package：

1. HTTP 适配层在 `pkg/services/team/teamapi`。`createTeam` 绑定请求到 `CreateTeamCommand`，从认证上下文设置 `OrgID`，调用 `teamService.CreateTeam`，再把 sentinel error 映射成 HTTP 状态（[`teamapi/team.go` L36-L50](https://github.com/grafana/grafana/blob/4c66b8bc919aa7fc7e2b5e8c4c9a94dac5f3a148/pkg/services/team/teamapi/team.go#L36-L50)）。
2. service contract 放在 feature package，`team.Service` 描述 create/update/delete/search 等用例（[`team/team.go` L12-L25](https://github.com/grafana/grafana/blob/4c66b8bc919aa7fc7e2b5e8c4c9a94dac5f3a148/pkg/services/team/team.go#L12-L25)）。
3. `LegacyService` 持有 `store`，service 编排业务调用；例如创建成功后发布 watch event（[`teamimpl/legacy_team.go` L28-L59](https://github.com/grafana/grafana/blob/4c66b8bc919aa7fc7e2b5e8c4c9a94dac5f3a148/pkg/services/team/teamimpl/legacy_team.go#L28-L59)）。
4. SQL 和数据库事务在 `xormStore`。`Create` 在一个事务中做名称唯一性检查和插入；删除也在一个事务中删除 team、membership 和关联 ACL（[`teamimpl/store.go` L60-L87](https://github.com/grafana/grafana/blob/4c66b8bc919aa7fc7e2b5e8c4c9a94dac5f3a148/pkg/services/team/teamimpl/store.go#L60-L87)、[`L154-L207`](https://github.com/grafana/grafana/blob/4c66b8bc919aa7fc7e2b5e8c4c9a94dac5f3a148/pkg/services/team/teamimpl/store.go#L154-L207)）。
5. 依赖装配用 provider function。`ProvideTeamAPI` 接收 service、access control、config 等参数并注册路由；service 也有 `ProvideService`，代码注释直接提到 wire sets（[`teamapi/api.go` L24-L80](https://github.com/grafana/grafana/blob/4c66b8bc919aa7fc7e2b5e8c4c9a94dac5f3a148/pkg/services/team/teamapi/api.go#L24-L80)、[`teamimpl/team.go` L25-L68](https://github.com/grafana/grafana/blob/4c66b8bc919aa7fc7e2b5e8c4c9a94dac5f3a148/pkg/services/team/teamimpl/team.go#L25-L68)）。

这说明大型 Go 项目也会保留 service interface，但与 Java 不同的点是：依赖由 provider graph 显式构造，HTTP handler 不直接接触 SQL，事务通常在一个明确的 store method 中结束。

### Gitea：顶层技术分层，事务常由 service/use case 控制

Gitea 的 repository 创建路径很典型：

1. API handler 用 `web.GetForm` 解码 `CreateRepoOption`，然后调用 `repo_service.CreateRepository`；成功后重新读数据库并通过 `convert.ToRepo` 转成 API response（[`routers/api/v1/repo/repo.go` L281-L305](https://github.com/go-gitea/gitea/blob/eb3bc196ec00efd184b663dead91ca89ca2ee0c3/routers/api/v1/repo/repo.go#L281-L305)、[`L242-L278`](https://github.com/go-gitea/gitea/blob/eb3bc196ec00efd184b663dead91ca89ca2ee0c3/routers/api/v1/repo/repo.go#L242-L278)）。
2. service 层负责跨步骤编排。创建 repository 时，数据库操作被包在 `db.WithTx` 中，Git 文件和外部初始化步骤放在事务外，并用 cleanup 处理后半段失败（[`services/repository/create.go` L251-L267](https://github.com/go-gitea/gitea/blob/eb3bc196ec00efd184b663dead91ca89ca2ee0c3/services/repository/create.go#L251-L267)）。
3. issue 创建更直接：`services/issue.NewIssue` 在 `db.WithTx` 内创建 issue、assignee 和 project 关联，事务外再处理 mention 和通知（[`services/issue/issue.go` L27-L76](https://github.com/go-gitea/gitea/blob/eb3bc196ec00efd184b663dead91ca89ca2ee0c3/services/issue/issue.go#L27-L76)）。
4. `db.WithTx` 创建事务 session，把 engine 放进 context；后续 `db.GetEngine(ctx)` 会复用该事务。这样 repository helper 不必把 `*sql.Tx` 暴露到每条调用链（[`models/db/context.go` L141-L175](https://github.com/go-gitea/gitea/blob/eb3bc196ec00efd184b663dead91ca89ca2ee0c3/models/db/context.go#L141-L175)）。

Gitea 顶层是 `routers/`、`services/`、`models/` 这种技术分层，但 `services/` 内部仍按 repository、issue、user 等领域继续分组。它证明“技术分层”和“按功能组织”可以同时存在，不必二选一。

### Mattermost：`api4 -> App -> Store -> sqlstore`

Mattermost 的 post 创建路径是另一种规模化选择：

1. `server/channels/api4/post.go` 中的 `createPost` 做 JSON 解码、输入清理、检查、audit 和响应编码，然后调用 `App.CreatePostAsUserWithFlags`（[`api4/post.go` L111-L162](https://github.com/mattermost/mattermost/blob/4df6bbc764dc5b4e199a6ef0caaa86c9d44c8218/server/channels/api4/post.go#L111-L162)）。
2. `App` 层继续做 channel 存在性、权限相关规则、去重和业务编排，再向下调用 store（[`app/post.go` L38-L99](https://github.com/mattermost/mattermost/blob/4df6bbc764dc5b4e199a6ef0caaa86c9d44c8218/server/channels/app/post.go#L38-L99)）。
3. `Store` 用按领域拆分的方法暴露持久化能力，例如 `Post()` 返回 `PostStore`（[`store/store.go` L24-L28](https://github.com/mattermost/mattermost/blob/4df6bbc764dc5b4e199a6ef0caaa86c9d44c8218/server/channels/store/store.go#L24-L28)、[`L402-L410`](https://github.com/mattermost/mattermost/blob/4df6bbc764dc5b4e199a6ef0caaa86c9d44c8218/server/channels/store/store.go#L402-L410)）。
4. `SqlPostStore.SaveMultiple` 在 store 内启动事务，同时写 Posts、Threads、priority 等关联表（[`sqlstore/post_store.go` L275-L303](https://github.com/mattermost/mattermost/blob/4df6bbc764dc5b4e199a6ef0caaa86c9d44c8218/server/channels/store/sqlstore/post_store.go#L275-L303)）。

这里值得注意的不是“照抄 Mattermost 的巨型 App 层”，而是它体现了两点：

- 大型 monolith 可以长期保留显式的 api / app / store 结构。
- 当一次存储操作自身包含多表原子性时，事务放在 store method 内完全合理。

Mattermost 的 HTTP handler 也包含权限检查和 audit，说明真实企业代码不是教科书式的纯粹分层。对 FixFlow 更合适的做法仍是把 HTTP 传输问题和业务授权规则尽量分开，而不是拿超大型项目的体量当作小项目模板。

### 三个项目的共同点与分歧

共同点：

- HTTP 层不直接拼业务 SQL。
- 业务调用和持久化之间有一个明确的方法边界。
- 依赖从外向内传入，而不是 service 内部 `new` 数据库。
- 错误会被翻译成 HTTP 语义。

分歧：

- Grafana 更偏 feature package，API、service、store 都在 team feature 下。
- Gitea 保留大型顶层技术分层，service 常拥有跨模型事务。
- Mattermost 保留 `api4` / `App` / `Store` 大层，store 可以拥有局部多表事务。

因此，“Go 企业项目采用哪一层做事务”没有统一答案。稳定原则是：**业务原子性决定了事务范围，物理事务应尽可能靠近需要原子执行的数据库操作，并避免把外部网络调用放进事务。**

## 每个关注点应该放哪里

| 关注点 | 建议位置 | 说明 |
|---|---|---|
| Router、middleware | `cmd/api` 或 `internal/http` | 认证、请求 ID、恢复、CORS 等横切能力放在 HTTP 边界 |
| JSON decode / encode | HTTP handler | 使用 request/response DTO；不要让 HTTP DTO 进入 domain |
| 路径参数和分页参数解析 | HTTP handler | 转成 application command/query 后再交给 service |
| 身份认证 | middleware | 从 token/session 得到 actor，并放入 typed context key |
| 细粒度授权策略 | service + domain | 依赖当前状态、tenant、角色、assignee 的规则不能只靠路由 middleware |
| 业务校验和不变量 | domain method / application service | 纯规则优先做成无 I/O 的函数或 entity method |
| 跨多个依赖的 use case 编排 | application service | 例如“创建工单 + 写审计事件 + 发通知 intent” |
| 事务边界 | service/use case 或明确的 store method | 由原子性决定；不要由 handler 决定 |
| SQL、行扫描、锁 | store/repository | 不让 SQL 出现在 handler 和 domain |
| 数据库错误翻译 | repository | `sql.ErrNoRows` 转成 `ErrWorkOrderNotFound` 等 |
| HTTP 状态码映射 | handler / HTTP error mapper | 用 `errors.Is/As`，不泄露 SQL 错误 |
| DTO 映射 | 边界处 | handler 负责 HTTP DTO；repository 负责 row struct |
| 接口 | 消费者侧、真实边界 | service 定义自己需要的 store/access interface；实现方返回 concrete type |
| 依赖装配 | composition root，通常是 `main` | 构造器注入；不要在业务包里用全局 singleton |

## 一个完整的 CRUD 调用路径

下面的 `POST /v1/work-orders` 是示意代码，省略配置加载、日志、OpenTelemetry 和完整的 FixFlow schema 适配。它保留了关键边界：HTTP 解码、tenant/actor、业务校验、MySQL 事务、审计事件和 JSON 映射。

### 1. Handler：只处理 HTTP 和错误映射

```go
// internal/workorder/handler.go
package workorder

import (
    "encoding/json"
    "errors"
    "net/http"

    "fixflow/internal/identity"
)

type Handler struct {
    service *Service
}

type createWorkOrderRequest struct {
    BranchPublicID    string `json:"branchId"`
    CustomerPublicID  string `json:"customerId"`
    EquipmentPublicID string `json:"equipmentId"`
    ContactName       string `json:"contactName"`
    ContactPhone      string `json:"contactPhone"`
    Title             string `json:"title"`
    Description       string `json:"description"`
    Priority          string `json:"priority"`
}

type workOrderResponse struct {
    ID          string `json:"id"`
    Title       string `json:"title"`
    Description string `json:"description"`
    Priority    string `json:"priority"`
    Status      string `json:"status"`
    Version     int64  `json:"version"`
}

func NewHandler(service *Service) *Handler {
    return &Handler{service: service}
}

func (h *Handler) Create(w http.ResponseWriter, r *http.Request) {
    actor, ok := identity.ActorFromContext(r.Context())
    if !ok {
        writeError(w, http.StatusUnauthorized, "unauthenticated")
        return
    }

    r.Body = http.MaxBytesReader(w, r.Body, 1<<20)
    dec := json.NewDecoder(r.Body)
    dec.DisallowUnknownFields()

    var req createWorkOrderRequest
    if err := dec.Decode(&req); err != nil {
        writeError(w, http.StatusBadRequest, "invalid_json")
        return
    }

    wo, err := h.service.Create(r.Context(), actor, CreateCommand{
        BranchPublicID:    req.BranchPublicID,
        CustomerPublicID:  req.CustomerPublicID,
        EquipmentPublicID: req.EquipmentPublicID,
        ContactName:       req.ContactName,
        ContactPhone:      req.ContactPhone,
        Title:             req.Title,
        Description:       req.Description,
        Priority:          req.Priority,
    })
    if err != nil {
        var invalid *ValidationError
        switch {
        case errors.As(err, &invalid):
            writeError(w, http.StatusBadRequest, invalid.Error())
        case errors.Is(err, ErrForbidden):
            writeError(w, http.StatusForbidden, "forbidden")
        case errors.Is(err, ErrReferenceNotFound):
            writeError(w, http.StatusUnprocessableEntity, "invalid_reference")
        default:
            writeError(w, http.StatusInternalServerError, "internal_error")
        }
        return
    }

    writeJSON(w, http.StatusCreated, workOrderResponse{
        ID:          wo.PublicID,
        Title:       wo.Title,
        Description: wo.Description,
        Priority:    wo.Priority,
        Status:      wo.Status,
        Version:     wo.Version,
    })
}

func writeJSON(w http.ResponseWriter, status int, v any) {
    w.Header().Set("Content-Type", "application/json; charset=utf-8")
    w.WriteHeader(status)
    _ = json.NewEncoder(w).Encode(v)
}

func writeError(w http.ResponseWriter, status int, code string) {
    writeJSON(w, status, map[string]string{"error": code})
}
```

关键点：

- `tenantId` 不出现在 request body。
- tenant 和 membership 来自认证 middleware 写入的 typed context value。
- handler 只做 HTTP DTO 映射，不判断工单状态机，也不访问数据库。
- HTTP 状态码只在边界映射，不把 `http.StatusXxx` 带进 domain。

### 2. Service：业务规则和用例边界

```go
// internal/workorder/service.go
package workorder

import (
    "context"
    "fmt"
    "strings"

    "fixflow/internal/identity"
)

type CreateCommand struct {
    BranchPublicID    string
    CustomerPublicID  string
    EquipmentPublicID string
    ContactName       string
    ContactPhone      string
    Title             string
    Description       string
    Priority          string
}

type WorkOrder struct {
    ID                   int64
    TenantID             int64
    PublicID             string
    BranchPublicID       string
    CustomerPublicID     string
    EquipmentPublicID    string
    CreatedByMemberID    int64
    ContactName          string
    ContactPhone         string
    Title                string
    Description          string
    Priority             string
    Status               string
    Version              int64
}

type Event struct {
    TenantID      int64
    WorkOrderID   int64
    Version       int64
    CommandType   string
    FromStatus    *string
    ToStatus      string
    ActorMemberID int64
}

type WorkOrderStore interface {
    CreateWithEvent(
        ctx context.Context,
        wo WorkOrder,
        event Event,
    ) (WorkOrder, error)
}

type AccessChecker interface {
    CanCreateWorkOrder(ctx context.Context, actor identity.Actor) error
}

type Service struct {
    store  WorkOrderStore
    access AccessChecker
    newID  func() string
}

func NewService(
    store WorkOrderStore,
    access AccessChecker,
    newID func() string,
) *Service {
    return &Service{store: store, access: access, newID: newID}
}

func (s *Service) Create(
    ctx context.Context,
    actor identity.Actor,
    cmd CreateCommand,
) (WorkOrder, error) {
    if err := s.access.CanCreateWorkOrder(ctx, actor); err != nil {
        return WorkOrder{}, err
    }

    cmd.Title = strings.TrimSpace(cmd.Title)
    cmd.Description = strings.TrimSpace(cmd.Description)
    cmd.ContactName = strings.TrimSpace(cmd.ContactName)
    cmd.ContactPhone = strings.TrimSpace(cmd.ContactPhone)

    if cmd.Title == "" {
        return WorkOrder{}, &ValidationError{Field: "title", Reason: "required"}
    }
    if len([]rune(cmd.Title)) > 200 {
        return WorkOrder{}, &ValidationError{Field: "title", Reason: "too_long"}
    }
    if !validPriority(cmd.Priority) {
        return WorkOrder{}, &ValidationError{Field: "priority", Reason: "invalid"}
    }

    wo := WorkOrder{
        TenantID:          actor.TenantID,
        PublicID:          s.newID(),
        BranchPublicID:    cmd.BranchPublicID,
        CustomerPublicID:  cmd.CustomerPublicID,
        EquipmentPublicID: cmd.EquipmentPublicID,
        CreatedByMemberID: actor.MembershipID,
        ContactName:       cmd.ContactName,
        ContactPhone:      cmd.ContactPhone,
        Title:             cmd.Title,
        Description:       cmd.Description,
        Priority:          cmd.Priority,
        Status:            "OPEN",
        Version:           1,
    }

    event := Event{
        TenantID:      actor.TenantID,
        WorkOrderID:   0, // store 在拿到数据库自增 ID 后填入
        Version:       1,
        CommandType:   "CREATE",
        FromStatus:    nil,
        ToStatus:      "OPEN",
        ActorMemberID: actor.MembershipID,
    }

    saved, err := s.store.CreateWithEvent(ctx, wo, event)
    if err != nil {
        return WorkOrder{}, fmt.Errorf("create work order: %w", err)
    }
    return saved, nil
}

func validPriority(p string) bool {
    switch p {
    case "P1", "P2", "P3", "P4":
        return true
    default:
        return false
    }
}
```

这里把“创建工单和创建 CREATE 审计事件必须同时成功”定义成用例语义。service 不知道 SQL 细节，但它明确要求 store 提供一个原子操作。

### 3. Repository：SQL、tenant 过滤和事务

```go
// internal/workorder/errors.go
package workorder

import "errors"

var (
    ErrReferenceNotFound = errors.New("work order reference not found")
    ErrForbidden         = errors.New("forbidden")
)

type ValidationError struct {
    Field  string
    Reason string
}

func (e *ValidationError) Error() string {
    return e.Field + ": " + e.Reason
}
```

```go
// internal/workorder/store_mysql.go
package workorder

import (
    "context"
    "database/sql"
    "fmt"
)

type SQLStore struct {
    db *sql.DB
}

func NewSQLStore(db *sql.DB) *SQLStore {
    return &SQLStore{db: db}
}

func (s *SQLStore) CreateWithEvent(
    ctx context.Context,
    wo WorkOrder,
    event Event,
) (WorkOrder, error) {
    tx, err := s.db.BeginTx(ctx, nil)
    if err != nil {
        return WorkOrder{}, fmt.Errorf("begin create work order: %w", err)
    }
    defer func() { _ = tx.Rollback() }()

    result, err := tx.ExecContext(ctx, `
        INSERT INTO work_order (
            tenant_id, branch_id, public_uuid, customer_id, equipment_id,
            created_by_membership_id, reported_contact_name,
            reported_contact_phone, title, description, priority,
            status, aggregate_version
        )
        SELECT
            ?, b.id, ?, c.id, e.id,
            ?, ?, ?, ?, ?, ?, ?, 1
        FROM branch b
        JOIN customer c
          ON c.tenant_id = b.tenant_id
         AND c.public_uuid = ?
         AND c.status = 'ACTIVE'
        JOIN equipment e
          ON e.tenant_id = c.tenant_id
         AND e.customer_id = c.id
         AND e.public_uuid = ?
         AND e.status = 'ACTIVE'
        WHERE b.tenant_id = ?
          AND b.public_uuid = ?
          AND b.status = 'ACTIVE'
    `,
        wo.TenantID, wo.PublicID,
        event.ActorMemberID,
        wo.ContactName, wo.ContactPhone,
        wo.Title, wo.Description, wo.Priority, wo.Status,
        wo.CustomerPublicID,
        wo.EquipmentPublicID,
        wo.TenantID, wo.BranchPublicID,
    )
    if err != nil {
        return WorkOrder{}, fmt.Errorf("insert work order: %w", err)
    }

    affected, err := result.RowsAffected()
    if err != nil {
        return WorkOrder{}, fmt.Errorf("work order rows affected: %w", err)
    }
    if affected != 1 {
        return WorkOrder{}, ErrReferenceNotFound
    }

    id, err := result.LastInsertId()
    if err != nil {
        return WorkOrder{}, fmt.Errorf("work order last insert id: %w", err)
    }
    wo.ID = id
    event.WorkOrderID = id

    _, err = tx.ExecContext(ctx, `
        INSERT INTO work_order_event (
            tenant_id, work_order_id, aggregate_version, command_type,
            from_status, to_status, actor_membership_id
        ) VALUES (?, ?, ?, ?, NULL, ?, ?)
    `,
        wo.TenantID, event.WorkOrderID, event.Version, event.CommandType,
        event.ToStatus, event.ActorMemberID,
    )
    if err != nil {
        return WorkOrder{}, fmt.Errorf("insert work order event: %w", err)
    }

    if err := tx.Commit(); err != nil {
        return WorkOrder{}, fmt.Errorf("commit create work order: %w", err)
    }
    return wo, nil
}
```

这个 store method 同时承担三类细节：tenant 范围解析、复合外键有效性检查、`work_order` 与 `work_order_event` 的同一事务写入。它返回的 `ErrReferenceNotFound` 是可被 service 和 handler 识别的稳定错误，而不是 MySQL driver error。

实际项目中还应把 MySQL duplicate-key、deadlock 等 driver error 翻译成 feature 级错误，并在 handler 映射成 409 或可重试响应。不要让 HTTP 层 import MySQL driver 判断错误码。

### 4. Composition root：不用 Spring 也能装配

```go
// cmd/api/main.go
package main

import (
    "database/sql"
    "log"
    "net/http"
    "os"

    "github.com/google/uuid"
    _ "github.com/go-sql-driver/mysql"

    "fixflow/internal/identity"
    "fixflow/internal/workorder"
)

func main() {
    db, err := sql.Open("mysql", os.Getenv("FIXFLOW_MYSQL_DSN"))
    if err != nil {
        log.Fatal(err)
    }
    defer db.Close()

    store := workorder.NewSQLStore(db)
    access := identity.NewAccessChecker(db)
    service := workorder.NewService(store, access, uuid.NewString)
    handler := workorder.NewHandler(service)

    mux := http.NewServeMux()
    mux.Handle(
        "POST /v1/work-orders",
        identity.RequireTenant(http.HandlerFunc(handler.Create)),
    )

    server := &http.Server{
        Addr:    ":8080",
        Handler: mux,
    }
    log.Fatal(server.ListenAndServe())
}
```

这就是 Go 里最基础的 dependency wiring：

- 数据库由 `main` 创建。
- store 由 `main` 注入 service。
- service 由 `main` 注入 handler。
- handler 注册到 router。
- 测试可以给 service 注入 fake store，给 HTTP handler 注入 fake service 或真实 service + fake store。

不需要 `@Autowired`，也不需要全局 `DB` 变量。

## 事务到底应该放哪

### 证据

- Grafana 把 team 的局部事务放在 store method 中：名称唯一性检查和插入是一个原子存储操作；delete 的多表清理也是（[Grafana store](https://github.com/grafana/grafana/blob/4c66b8bc919aa7fc7e2b5e8c4c9a94dac5f3a148/pkg/services/team/teamimpl/store.go#L60-L87)）。
- Mattermost 把 Posts、Threads、priority 等写入包在 `SqlPostStore.SaveMultiple` 的事务里（[Mattermost SaveMultiple](https://github.com/mattermost/mattermost/blob/4df6bbc764dc5b4e199a6ef0caaa86c9d44c8218/server/channels/store/sqlstore/post_store.go#L275-L303)）。
- Gitea 在 service 层用 `db.WithTx` 包住 issue 创建和关联写入（[Gitea issue service](https://github.com/go-gitea/gitea/blob/eb3bc196ec00efd184b663dead91ca89ca2ee0c3/services/issue/issue.go#L27-L76)），并通过 context 让底层 helper 复用同一个事务（[Gitea db context](https://github.com/go-gitea/gitea/blob/eb3bc196ec00efd184b663dead91ca89ca2ee0c3/models/db/context.go#L141-L175)）。
- `database/sql` 的 `Tx` 明确要求最终以 `Commit` 或 `Rollback` 结束；`BeginTx` 接受 context 和 `TxOptions`（[database/sql: Tx](https://pkg.go.dev/database/sql#Tx)、[DB.BeginTx](https://pkg.go.dev/database/sql#DB.BeginTx)）。

### 建议

把事务分成两个问题：

1. **业务事务边界**：哪些状态变化必须一起成功？由 application service 或显式的 store method 表达。
2. **物理数据库事务**：在哪里 `BeginTx`、`Commit`、`Rollback`？由最接近 SQL 的 adapter 实现。

对 FixFlow 第一版，推荐以下规则：

- 如果一次命令只涉及一个内聚聚合，且 repository/store 方法自然拥有多表写入，例如创建 `work_order` + `work_order_event`，让这个 store method 自己开事务。
- 如果一次命令要调用多个 repository，例如工单变更还要修改 inventory 和创建 outbox record，让 application service 使用 `WithTx(ctx, fn)`，把事务绑定的 store 传给回调。
- handler 永远不负责 `Begin/Commit/Rollback`。
- 事务内不做邮件、HTTP、对象存储、消息队列等外部调用。
- 事务提交后再做通知；必须保证消息可靠时使用 transactional outbox，而不是把网络调用塞进数据库事务。
- 更新工单状态时，用 `WHERE tenant_id = ? AND id = ? AND aggregate_version = ?` 的乐观锁，并在同一事务追加 `work_order_event`。`RowsAffected == 0` 翻译成并发冲突或未找到。

Gitea 的 repository 创建也说明了这条规则：数据库创建先放在 `db.WithTx`，Git 文件初始化在事务外，失败时做补偿清理（[Gitea repository service](https://github.com/go-gitea/gitea/blob/eb3bc196ec00efd184b663dead91ca89ca2ee0c3/services/repository/create.go#L251-L267)）。这比“一个业务方法开一个大事务包住所有 I/O”更可靠。

## HTTP 框架怎么选

框架只替代 transport 层，不替代业务分层。不要把 `*gin.Context`、`*echo.Context` 或 Hertz 的 request context 一路传进 service 和 repository；在 handler 中转换成标准 `context.Context` 和 command 后向下调用。

| 选择 | 适合情况 | 注意点 |
|---|---|---|
| `net/http` | 学习、较小服务、希望理解 Go 原生抽象 | Go 1.22 起 `ServeMux` 支持 method + path wildcard 路由（[net/http: ServeMux](https://pkg.go.dev/net/http#ServeMux)），但没有框架式 binder/group middleware 语法 |
| Chi | 想保留 `http.Handler` 兼容性，同时需要 route group、sub-router、middleware | 轻量，适合 REST API，不等于业务框架（[Chi README](https://github.com/go-chi/chi/blob/9f8adb1aabaa8a91180a821111d3f8e668d1c0bf/README.md#L6-L38)） |
| Gin | 团队喜欢快速绑定、validation、group、middleware，接受 `gin.Context` | built-in JSON binding 和 middleware 很强，但 handler 要做框架到 application 的适配（[Gin README](https://github.com/gin-gonic/gin/blob/master/README.md#L20-L41)） |
| Echo | 需要 net/http 互操作、binding、集中错误处理和完整 middleware 生态 | Echo 也建立在标准 `net/http` 上；仍只解决 transport 层（[Echo README](https://github.com/labstack/echo/blob/master/README.md#L35-L55)） |

**FixFlow 建议**：先用 `net/http`。当路由分组、角色/tenant middleware、子路由组合开始重复，再引入 Chi；这比一开始被框架 Context 和生成结构绑住更适合学习。若团队已经统一使用 Gin/Echo，也可以直接用，但业务边界不变。

## 数据访问怎么选

| 选择 | 定位 | 什么时候合适 | 什么时候不合适 |
|---|---|---|---|
| `database/sql` | 标准库数据库抽象 | 学习事务和 scan；SQL 需要完全掌控；服务规模不大 | 手写 `Scan` 大量重复且没有代码生成 |
| `sqlx` | `database/sql` 的扩展 | 想保留显式 SQL，减少 struct scan / named parameter 样板；仍需要标准库事务语义（[sqlx README](https://github.com/jmoiron/sqlx/blob/41dac167fdad5e3fd81d66cafba0951dc6823a30/README.md#L5-L19)） | 查询很少、扫描代码尚未成为痛点 |
| `sqlc` | 从 SQL 生成 Go 代码 | SQL 稳定，希望在 CI 中做 schema/query 类型检查，保留 SQL 可读性（[sqlc README](https://github.com/sqlc-dev/sqlc/blob/3ad8b20fb02b5bea81591b673da0758b8685d951/README.md#L6-L10)） | 需求还在频繁变化；团队不熟悉 schema/query 生成流程 |
| GORM | full-featured ORM | 大量相似 CRUD、关联加载、团队愿意接受 ORM 生命周期和 hooks；事务 API 可覆盖大部分场景（[GORM README](https://github.com/go-gorm/gorm/blob/master/README.md#L10-L26)） | 复杂 tenant 条件、锁、报表 SQL、性能诊断很多；团队没有约定时容易隐藏查询 |

**FixFlow 建议**：

- 第一版用 `database/sql`，手写 SQL，明确事务、tenant 条件和 `RowsAffected`。
- scan 重复开始妨碍改动时，先评估 `sqlx`。
- SQL 和 schema 稳定后，把 repository 内部改为 `sqlc`，不要让 generated code 变成 domain。
- 不建议第一版直接上 GORM。FixFlow 有 tenant、状态机、乐观锁、审计事件和关联约束，显式 SQL 更利于学习。若团队已有 GORM 经验，也可以使用，但必须固定约定：显式 `tenant_id`、显式 transaction、禁止 handler 调 ORM。

## 依赖注入：手工构造、Wire、Fx

### 手工构造

默认推荐，尤其对小型服务和 FixFlow：

```go
db := openDB()
store := workorder.NewSQLStore(db)
auth := identity.NewAccessChecker(db)
service := workorder.NewService(store, auth, uuid.NewString)
handler := workorder.NewHandler(service)
```

优点是依赖图完全可读；测试直接替换边界；没有反射和启动期魔法。缺点是组件很多时 `main` 会变长，解决方式是按 subsystem 提供 `NewWorkOrderModule` 之类的小型组合函数，而不是先引入容器。

### Wire

Google Wire 的原说法是：依赖作为 function parameter 表示，鼓励显式初始化而非全局变量；它通过代码生成连接组件，运行时不使用 reflection（[Wire README](https://github.com/google/wire/blob/9c25c9016f6825302537c4efdd5e897976f9c826/README.md#L11-L16)）。

但当前 Wire README 同时标注项目已不再维护（[Wire README](https://github.com/google/wire/blob/9c25c9016f6825302537c4efdd5e897976f9c826/README.md#L6-L9)）。因此：

- 新项目不要因为“依赖一多”就默认引入 Wire。
- 如果组织已有 fork 或既有 wire 代码，可以继续理解 provider set。
- 小服务使用显式构造函数更简单。

### Fx

Uber Fx 是运行时 dependency injection 系统，强调移除 globals、模块化组件和应用生命周期；其 README 说它是 Uber 绝大多数 Go 服务的 backbone（[Fx README](https://github.com/uber-go/fx/blob/d5da5b04ac906bfbad8b400baeee9b970c1be6f3/README.md#L3-L14)）。

适合：

- 多模块 monolith 或微服务组；
- 大量 long-lived components（DB、HTTP server、consumer、worker）；
- 需要统一启动/停止顺序和 lifecycle；
- 团队愿意理解容器启动期错误和 reflection graph。

不适合：

- 一个 API server、几个 handler、一个 MySQL store 的学习项目；
- 把 `main` 的显式依赖藏在标签或全局 provider 中却认为这更“Enterprise”。

**FixFlow 建议**：手工 wiring。先让依赖图暴露出来，等到模块数量、lifecycle 和共享组件真的造成维护成本，再评估 Fx。

## 文件混在一起时，如何诊断和拆分

典型坏味道不是“代码在一个文件里”，而是同一个函数同时承担以下职责：

- decode HTTP body；
- 取 tenant 和 role；
- 做状态机或权限判断；
- 拼接 SQL；
- 决定 `Begin/Commit/Rollback`；
- 把 MySQL error 直接映射成 HTTP status；
- 组装 response DTO。

这种函数难以做单元测试，导致业务规则只能靠数据库集成测试，最后所有逻辑都变成“必须连 MySQL 才能验证”。

诊断时先不要重写架构，按下面顺序做：

1. **写行为测试**：为现有 handler 写 `httptest`，为 repository 写真实 MySQL integration test，先锁定当前行为。
2. **找不变量**：例如 title 长度、priority 枚举、OPEN 初始状态、当前用户是否有权创建、事件版本必须为 1。
3. **提取纯逻辑**：把状态转换、权限判断和输入规范化放到 domain/application 函数；纯函数容易表驱动测试。
4. **提取 HTTP DTO**：request/response struct 放到 handler 附近，避免 domain 被 JSON tag 和 HTTP 语义污染。
5. **提取 store**：把 SQL、scan、driver error 翻译和局部事务移到 `store.go`；接口只暴露 service 需要的原子操作。
6. **错误映射上移**：`sql.ErrNoRows` 在 repository 转成 `ErrNotFound`，handler 用 `errors.Is/As` 转 HTTP。
7. **最后改 wiring**：在 `main` 或 module constructor 中把 concrete implementation 接起来。

可以先用 `rg` 找混合点：

```bash
rg -n 'BeginTx|Commit|Rollback|QueryContext|ExecContext' internal/workorder
rg -n 'json.NewDecoder|http.Status|WriteHeader' internal/workorder
rg -n 'tenant_id|TenantID' internal/workorder
rg -n 'ErrNoRows|errors.Is|errors.As' internal/workorder
```

拆分判断标准：

- 如果一条路径只是“读一行、返回一个字段”，不要为了形式硬造 domain service；一个简单 handler + query method 可能更好。
- 当业务不变量、权限和事务开始出现时，就应明确 service 与 repository 的边界。
- store interface 只包含 service 真正调用的方法，不要提前写完整 CRUD 接口。
- repository 不应该返回 HTTP status；handler 不应该知道 SQL error。
- domain 不应该 import `net/http`、`database/sql`、gin/echo 或 MySQL driver。

## FixFlow 推荐目录和代码形状

先采用 feature-oriented 的精简结构：

```text
backend/
  cmd/
    api/
      main.go
  internal/
    identity/
      actor.go
      middleware.go
      access_mysql.go
    workorder/
      handler.go
      service.go
      store_mysql.go
      model.go
      errors.go
      handler_test.go
      service_test.go
      store_mysql_test.go
    platform/
      mysql.go
      httpserver.go
  go.mod
```

在这个阶段：

- `handler.go`：HTTP DTO、decode/encode、路由对应的方法。
- `service.go`：use case、tenant/authorization、业务校验、事务语义。
- `store_mysql.go`：SQL、行扫描、事务、数据库错误翻译。
- `model.go`：domain entity 和状态转换。
- `errors.go`：feature-level sentinel/custom errors。
- `main.go`：composition root。

不要一开始创建全局的 `controllers/`、`services/`、`repositories/`、`dtos/`、`mappers/`。对一个小型服务，这种按技术层拆 package 会让一次功能变更跨很多目录，也容易产生 `service` 这种没有业务含义的包名。

当某个部分确实变大，再做局部拆分：

```text
internal/workorder/
  handler/
  service/
  domain/
  mysql/
```

拆分触发条件：

- domain 状态机已经复杂到需要大量纯单元测试，拆 `domain/`；
- SQL 和 query builder 多到一个文件难以阅读，拆 `mysql/`；
- API 有多个版本、多种协议，拆 `httpapi/` 或 `transport/`；
- 不是“看到 Java 有这四个目录，所以 Go 也要有”。

## 针对 FixFlow 的具体设计约束

### Tenant

- 认证成功后，从 verified principal 得到 tenant 和 membership，放进 typed context value。
- 不信任 body 中的 `tenantId`。
- 每个读写 query 都带 `tenant_id`，包括 update、delete、count、exists。
- store method 参数显式带 `tenantID`，不要依赖不可见的全局 tenant。
- 对 public UUID 只做外部标识，不把 UUID 当成授权凭证。
- 对关联对象校验 tenant 范围，例如工单的 customer/equipment 必须属于同一 tenant。

### Work order

- 创建工单直接进入 `OPEN`，由 domain/service 设置。
- `CREATE`、`ASSIGN`、`RETURN_ASSIGNMENT`、`START`、`RESOLVE`、`REOPEN`、`CLOSE`、`CANCEL` 是显式 command。
- 状态迁移由 domain 状态机决定，HTTP handler 不判断“OPEN 能不能 START”。
- 状态变化和 `work_order_event` 在同一数据库事务中。
- `aggregate_version` 用乐观锁；更新 0 行时区分 not found 与 concurrent modification。
- `work_order_event` 是审计记录，不是 outbox。不要在事务内直接发送邮件或 HTTP。

### Queries

- 列表和看板查询可以走独立 read query，直接返回 view DTO，不需要把每个列表页都先完整加载 aggregate。
- 但 read query 仍必须有 tenant predicate、稳定排序和 cursor/limit。
- 复杂报表 SQL 可以留在 store/query package，不要把 SQL 拼进 service。
- 当查询数量显著增长时，再考虑 sqlc 或独立的 read model，不必先做 CQRS。

### Authorization

- route middleware 适合做认证和粗粒度权限，例如“必须登录”“必须有 tenant membership”。
- 角色、当前 assignee、当前 status 相关的业务授权放在 service/domain。
- 这与 FixFlow 已有决策一致：授权策略放 domain/application，而不是散落在 SQL 或 controller 中（[ADR 0008](../../../projects/fixflow/docs/adr/0008-authorization-policies-live-in-domain-code.md)）。

### IDs

结合 FixFlow 已有决策，数据库内部关系用 `BIGINT UNSIGNED` 主键，对外 URL 和 JSON 使用 `CHAR(36)` UUID。不要把自增 ID 暴露给 React 前端，也不要用 public UUID 替代 tenant ownership 检查（[ADR 0003](../../../projects/fixflow/docs/adr/0003-separate-internal-and-public-identifiers.md)）。

## 推荐的落地顺序

1. 选一个垂直切片：创建工单。
2. 用 `net/http`、`database/sql` 和手工 wiring 完成 handler -> service -> store -> MySQL -> JSON。
3. 为 service 的不变量写 fake store 测试。
4. 为 store 写真实 MySQL integration test，覆盖 tenant 隔离、关联对象校验、事务回滚和重复事件版本。
5. 为 handler 写 `httptest`，覆盖 400、403、422、201 和错误 JSON。
6. 再加工作流 command、乐观锁和审计事件。
7. 只有当路由、scan、DI 或 query 数量确实造成痛点时，才引入 Chi、sqlx/sqlc、Fx 等工具。

这个顺序比先搭“企业级目录”更能获得可迁移的判断力，因为每一步都有明确的失败场景和测试证据。

## 常见误解

### 误解 1：Go 也有官方 Controller-Service-DAO 标准

没有。官方只给 package/module 的通用指导；分层是工程选择。`golang-standards/project-layout` 也明确否认自己是官方标准。

### 误解 2：没有 Spring，就没有 dependency injection

Dependency injection 不依赖 Spring。构造函数参数、`main` 中的显式装配就是 DI；Wire/Fx 只是自动化或容器化依赖图。

### 误解 3：每个 service 都要有 interface

Go 接口是消费者需要的行为约束。service 没有多个实现、也没有测试替换点时，先返回 concrete type。等真正需要 mock、替换或隔离边界时再定义小接口。

### 误解 4：Repository 一定不能碰事务

不成立。如果 store method 对应一个内聚的多表原子操作，事务放在 repository/store 内更自然。关键是不要让多个嵌套 repository 调用各自偷偷提交，导致上层无法控制原子性。

### 误解 5：事务应该由 HTTP handler 管

不成立。handler 只负责 transport；事务属于 application/use case 或明确的 persistence boundary。handler 不应该知道 MySQL transaction 生命周期。

### 误解 6：Go 项目越大，就越应该复制 Java 的层目录

大型 Go 项目常常有很强的分层，但具体形状受历史、团队和部署方式影响。Grafana、Gitea、Mattermost 的实现并不完全相同；复制他们的目录而不复制他们的约束和测试，只会增加样板。

### 误解 7：ORM 自动解决事务和安全

不成立。ORM 可以管理 `Begin/Commit`，但 tenant predicate、authorization、lock、query plan 和业务不变量仍要显式设计。隐藏 SQL 可能让跨 tenant 查询更难审查。

### 误解 8：抽象越多越容易维护

Go 更偏好小而清晰的 concrete boundary。过早引入 `Service` interface、generic repository、mapper interface、DI container，往往让调用链比业务本身更难读。

## 相关问题

### Go 是否等价于 Java 的 Controller -> Service -> DAO -> MySQL？

职责相似，但不是目录和类型系统的等价。常见 Go 形状是 HTTP handler -> application service -> store/repository；domain 可以独立，也可以暂放在 feature package。关键是把职责和依赖方向分开，而不是复制 Java 的命名。

### 为什么成熟 Go 项目看起来也分了很多层？

因为项目规模、团队边界、历史迁移和基础设施建设会增加边界。大项目需要 DI graph、权限、缓存、审计、可观测性和多存储；FixFlow 应该学习这些边界为什么存在，而不是先复制目录规模。

### FixFlow 是否应该采用完整 Clean Architecture 或 DDD？

不建议第一版完整铺开。先用 feature package 和明确的不变量/事务边界；当状态机、授权和审计明显增长时，再拆 domain 与 persistence adapter。DDD 的价值在模型和边界，不在于目录数量。

## 证据边界与不确定性

- 本调研是源码和官方文档的定向阅读，不是对 Go 生态的大规模统计；“大型项目常见”不能直接推导“小项目也应如此”。
- Grafana、Gitea、Mattermost 都包含 legacy 或迁移期代码；本文引用的是能说明边界的具体源码路径，不表示我认可项目整体架构的所有细节。
- 企业项目对 service/repository 的划分不同，说明没有一个放之四海皆准的 Go 目录标准。本文的推荐是面向 FixFlow 的小型多租户生产服务，不是语言规范。
- Wire 的维护状态以其当前 README 为准；工具维护状态变化较快，采用前应重新检查 release 和 issue 活跃度。
- 示例代码是教学用的形态说明，不是对 FixFlow 当前 Java schema 的逐列实现；实际落地前应按现有 ADR、schema 和测试约束调整。

## 来源附录

### 官方 Go 文档与规范

- [Organizing a Go module](https://go.dev/doc/modules/layout)
- [Organizing Go code](https://go.dev/blog/organizing-go-code)
- [Go Code Review Comments](https://go.dev/wiki/CodeReviewComments)
- [Effective Go](https://go.dev/doc/effective_go)
- [Package names](https://go.dev/blog/package-names)
- [Go Concurrency Patterns: Context](https://go.dev/blog/context)
- [database/sql](https://pkg.go.dev/database/sql)
- [net/http](https://pkg.go.dev/net/http)
- [errors package](https://pkg.go.dev/errors)

### 官方风格指南

- [Google Go Style Guide: Decisions](https://google.github.io/styleguide/go/decisions)
- [Uber Go Style Guide](https://github.com/uber-go/guide/blob/1d60a91aa5e87d443002e23c21903c49489dbde5/style.md)

### 开源项目源码证据

以下源码链接固定到调研时的 commit，避免默认分支变化导致路径漂移：

- Grafana: [`teamapi/api.go`](https://github.com/grafana/grafana/blob/4c66b8bc919aa7fc7e2b5e8c4c9a94dac5f3a148/pkg/services/team/teamapi/api.go)、[`teamapi/team.go`](https://github.com/grafana/grafana/blob/4c66b8bc919aa7fc7e2b5e8c4c9a94dac5f3a148/pkg/services/team/teamapi/team.go)、[`teamimpl/legacy_team.go`](https://github.com/grafana/grafana/blob/4c66b8bc919aa7fc7e2b5e8c4c9a94dac5f3a148/pkg/services/team/teamimpl/legacy_team.go)、[`teamimpl/store.go`](https://github.com/grafana/grafana/blob/4c66b8bc919aa7fc7e2b5e8c4c9a94dac5f3a148/pkg/services/team/teamimpl/store.go)
- Gitea: [`routers/api/v1/repo/repo.go`](https://github.com/go-gitea/gitea/blob/eb3bc196ec00efd184b663dead91ca89ca2ee0c3/routers/api/v1/repo/repo.go)、[`services/repository/create.go`](https://github.com/go-gitea/gitea/blob/eb3bc196ec00efd184b663dead91ca89ca2ee0c3/services/repository/create.go)、[`services/issue/issue.go`](https://github.com/go-gitea/gitea/blob/eb3bc196ec00efd184b663dead91ca89ca2ee0c3/services/issue/issue.go)、[`models/db/context.go`](https://github.com/go-gitea/gitea/blob/eb3bc196ec00efd184b663dead91ca89ca2ee0c3/models/db/context.go)
- Mattermost: [`api4/post.go`](https://github.com/mattermost/mattermost/blob/4df6bbc764dc5b4e199a6ef0caaa86c9d44c8218/server/channels/api4/post.go)、[`app/post.go`](https://github.com/mattermost/mattermost/blob/4df6bbc764dc5b4e199a6ef0caaa86c9d44c8218/server/channels/app/post.go)、[`store/store.go`](https://github.com/mattermost/mattermost/blob/4df6bbc764dc5b4e199a6ef0caaa86c9d44c8218/server/channels/store/store.go)、[`store/sqlstore/post_store.go`](https://github.com/mattermost/mattermost/blob/4df6bbc764dc5b4e199a6ef0caaa86c9d44c8218/server/channels/store/sqlstore/post_store.go)

### 工具与框架项目文档

- [project-layout README](https://github.com/golang-standards/project-layout/blob/a9d6fae7015527b10550ebb6d6b71a71b1ef5ea7/README.md)
- [Chi README](https://github.com/go-chi/chi/blob/9f8adb1aabaa8a91180a821111d3f8e668d1c0bf/README.md)
- [Gin README](https://github.com/gin-gonic/gin/blob/master/README.md)
- [Echo README](https://github.com/labstack/echo/blob/master/README.md)
- [sqlx README](https://github.com/jmoiron/sqlx/blob/41dac167fdad5e3fd81d66cafba0951dc6823a30/README.md)
- [sqlc README](https://github.com/sqlc-dev/sqlc/blob/3ad8b20fb02b5bea81591b673da0758b8685d951/README.md)
- [GORM README](https://github.com/go-gorm/gorm/blob/master/README.md)
- [GORM Transactions](https://gorm.io/docs/transactions.html)
- [Google Wire README](https://github.com/google/wire/blob/9c25c9016f6825302537c4efdd5e897976f9c826/README.md)
- [Uber Fx README](https://github.com/uber-go/fx/blob/d5da5b04ac906bfbad8b400baeee9b970c1be6f3/README.md)

### FixFlow 本地约束

- [ADR 0002: Work Order lifecycle and command ownership](../../../projects/fixflow/docs/adr/0002-work-order-lifecycle-and-command-ownership.md)
- [ADR 0003: Separate internal and public identifiers](../../../projects/fixflow/docs/adr/0003-separate-internal-and-public-identifiers.md)
- [ADR 0008: Authorization policies live in domain code](../../../projects/fixflow/docs/adr/0008-authorization-policies-live-in-domain-code.md)
- [ADR 0009: Work Order events are audit records](../../../projects/fixflow/docs/adr/0009-work-order-events-are-audit-records.md)
