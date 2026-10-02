---
date: 2026-09-27
tags: [Orca, ADE, AI-Agent, Git-Worktree, 微服务, 多仓库, 工具评估]
---

# Orca 微服务多仓库开发评估

## 问题

公司开发以微服务为主，一个需求经常横跨多个仓库。想引入 Orca（"ADE"，agent development environment，用来跑并行 coding agent 的桌面应用），需要确认：

1. Orca 是否真的能支撑多仓库/微服务开发？
2. Orca 的 "project groups"、"folder workspaces"、`--parent-worktree` 血缘到底是什么机制？
3. 如果推到公司，会遇到哪些问题？

前提认知：`git worktree` 是**按仓库**的，"一个 worktree 装多个仓库" 不是 Git 概念。Orca 本身也明确说 "Every Orca worktree is a real git worktree"（[Worktrees](https://www.onorca.dev/docs/model/worktrees)）。

本笔记基于**一手来源**：官方文档 + 本机安装的 Orca 1.4.212（Homebrew cask `stablyai/orca`，`/Applications/Orca.app`，`/opt/homebrew/bin/orca`，版本经 `orca status --json` 确认为 `appVersion: 1.4.212`）的 CLI `--help`/只读命令输出，以及应用包内实现的核对。

---

## 回答

### 结论先行

| 问题 | 结论 |
|------|------|
| Orca 的多仓库机制是什么？ | 是**编排层面的分组**（project group / folder workspace）+ **一个跑在父目录里的共享工作区**，**不是** Git 层的多仓库 worktree |
| 单个 agent session 能看到多个仓库的文件吗？ | ✅ 能，但**只有**在 folder workspace 里（终端 cwd = 多仓库的父目录） |
| 并行 agent 的多仓库隔离靠什么？ | ❌ 文档未说明。folder workspace 本身**不是** worktree，没有 per-feature 的 git 隔离，需实测 |
| 一个需求跨 N 个仓库怎么落地？ | 目前只能 N 个独立仓库 worktree 各自成篇，靠 `--parent-worktree` 在侧边栏做血缘关联 |
| 公司推行的主要阻力 | agent 默认"全权限"启动、插件信任模型、企业能力（SSO/策略/托管）官方页面未给出具体能力；License 是 MIT（法务上友好） |

### 1. 核心概念：四个层次要分清

| 概念 | 是什么 | Git 含义 | 来源 |
|------|--------|----------|------|
| Project（项目） | 一个"持久项目"，`--kind git\|folder` | 通常一个仓库 | `orca project list --json`；`orca project setups --json` 返回 `kind: "git"` |
| Repo（仓库） | 一个磁盘上的 checkout 路径 | 一个 Git 仓库 | `orca repo list --json` |
| Project group（项目组） | 导入一个**内含多个 Git 仓库的父目录**时，把若干仓库归到一个组 | 纯侧边栏分组，**无 Git 语义** | 官方 Worktrees 文档 |
| Folder workspace（文件夹工作区） | 组级别、位于**父目录**的"类 worktree"条目 | ❌ 不是 worktree，无 branch/commit | 官方 Worktrees 文档 + 应用实现 |
| Worktree | 一个任务一个 `git worktree`，独立分支、独立文件、独立 agent 终端 | 真正的 `git worktree` | 官方 Worktrees 文档 |

#### 1.1 Project group 精确语义

> "When you add a parent folder that contains multiple Git repos, Orca can import the selected repos separately or **group them under one project group**."
> — [Worktrees · Sidebar layout](https://www.onorca.dev/docs/model/worktrees)

> "When you import a parent folder that contains several Git repos, Orca can group those repos under a single project group in the sidebar."
> — [Worktrees · Multi-repo project groups & folder workspaces](https://www.onorca.dev/docs/model/worktrees)

也就是说：**project group 只是"若干仓库的集合容器"**，对应磁盘上的一个父目录（实现里叫 `parentPath`）。它不产生任何 Git 对象。

#### 1.2 Folder workspace 精确语义（这是多仓库的关键）

官方定义：

> "Each project group exposes a **folder workspace** flow — a worktree-like entry that **lives at the parent-folder level** and binds its task source to one of the repos underneath, so one feature's GitHub/GitLab/Linear/Jira task surface stays attached to the right repo even though the workspace itself is grouped with its siblings in the sidebar."
> — [Worktrees · Multi-repo project groups & folder workspaces](https://www.onorca.dev/docs/model/worktrees)

创建路径（**仅 UI**）：

> "hover the project group's header row in the sidebar and click the + action (tooltip: "Create workspace for group"). The composer dialog ("Create Folder Workspace") asks you to pick the source project for the workspace's task source, name the workspace, and optionally attach a linked issue or PR."
> — 同上

⚠️ **文档没说清的地方，我在应用实现里核实了**（Orca 1.4.212 `app.asar` → `/out/main/index.js`）：

- folder workspace 的数据结构是 `{ id, projectGroupId, name, folderPath, connectionId, linkedTask, workspaceStatus, ... }` — **完全没有** `branch` / `head` / `isMainWorktree` 等 Git 字段，与 worktree 的 schema 是两套东西。
- `folderPath` 默认取 **project group 的 `parentPath`**（即多仓库的父目录）。代码：`folderPath = e.folderPath ?? t?.parentPath`，缺失时抛错 `Folder-backed project group not found.`
- 终端运行时明确支持两种 workspace 类型：`workspaceKind === 'git-worktree' || workspaceKind === 'folder'`。
- 终端 cwd 解析：`resolveFolderWorkspacePath: id => getFolderWorkspace(id)?.folderPath`，即 **folder workspace 里的终端工作目录就是那个父目录**。

➡️ **结论**：`folder workspace` = "把多仓库父目录当成一个共享工作区"，于是**一个 agent session 确实能同时读写多个仓库的文件**（因为它就在父目录里跑，各仓库是子目录）。这就是 Orca 对多仓库的官方答案。

但必须同时说清三件事（见 §3）：

1. 它**不是** worktree → 没有 per-feature 的 Git 隔离；
2. 它依赖"父目录里平铺多个 repo"这种磁盘布局；
3. 官方文档**没有**任何一处说 folder workspace 适合跑并行 agent。

#### 1.3 什么被绑定到单个 worktree

| 对象 | 作用域 | 来源 |
|------|--------|------|
| Agent terminal（含 session） | 一个 worktree = 一个终端 = 一个 agent | "An agent session is one CLI agent running in one terminal **in one worktree**" — [Agents & sessions](https://www.onorca.dev/docs/model/agents-sessions) |
| 编辑器 tab / 浏览器 tab / 终端 pane 布局 | **每个 worktree 独占一套** | "Each worktree owns its own tab layout. Switching worktrees swaps the entire pane tree" — [Tabs, panes & splits](https://www.onorca.dev/docs/model/tabs-panes-splits) |
| 文件(每 worktree 干净的 checkout) | 每 worktree 独立，gitignored 依赖需重建 | [Worktrees · Shared directories](https://www.onorca.dev/docs/model/worktrees) |
| Quick Commands | 全局或按 project 作用域（**跨 worktree 共享**） | [Terminal · Quick Commands](https://www.onorca.dev/docs/terminal)；[Settings](https://www.onorca.dev/docs/settings) |
| Settings / Integrations 凭据 | 每台机器/每 host（"Saved credentials stay on this machine"） | [Settings · Integrations](https://www.onorca.dev/docs/settings) |

#### 1.4 `--parent-worktree folder:<id>` 到底做什么

CLI 原文（`orca worktree create --help`，本机 1.4.212 输出）：

```
--parent-worktree <selector> Parent selector such as identity:<identity>, active/current,
  id:<repo-id>::<path>, branch:<branch>, issue:<number>, path:<path>, folder:<id>,
  or worktree:<worktreeId>
```

我实测 `orca worktree show --worktree folder:test --json`（只读）确认：`folder:<id>` **只被 `--parent-worktree` 接受**，普通 worktree selector 不接受它，返回：

```json
{"ok": false, "error": {"code": "selector_not_found",
  "data": {"validSelectorForms": ["id:<repo-id>::<absolute-path>","path:<absolute-path>",
    "name:<display-name>","branch:<branch>","identity:<identity-key>","issue:<number>",
    "current","active"]}}}
```

官方也直说了它的作用是**只做嵌套**：

> "The same drawer lets you choose an active worktree from the same repository as the new workspace's Parent workspace. **This only nests the workspaces in Orca's sidebar; it does not change Git history or branches.**"
> — [Worktrees · Naming the branch](https://www.onorca.dev/docs/model/worktrees)

应用实现同样确认：`resolveParent()` 对 folder 父级只返回 `{type:'folder', folderWorkspace, instanceId:null}` — 一个**没有 instance 的容器**。

➡️ **一句话**：`--parent-worktree folder:<id>` = 在侧边栏把这个新 worktree 挂到某个 folder workspace 下面，便于归类；**不会**让这个 worktree 变成"多仓库 worktree"。

### 2. 公司推行的关键因素

#### 2.1 许可证

| 项 | 值 | 来源 |
|----|----|------|
| License | **MIT**（SPDX: `MIT`） | GitHub API `GET /repos/stablyai/orca/license` |
| 版权方 | `Copyright (c) 2026 Lovecast Inc.` | LICENSE 原文（GitHub API 返回内容 + 应用包内 `/LICENSE` 一致） |
| 语言 / 仓库 | TypeScript；`stablyai/orca`，default branch `main` | GitHub API `GET /repos/stablyai/orca` |

➡️ MIT 意味着公司可自由内部使用、可自建、可修改；但**注意** MIT 只覆盖代码，桌面分发版是否含额外条款，文档未说明。

#### 2.2 遥测（Privacy & Telemetry）

| 项 | 内容 | 来源 |
|----|------|------|
| 匿名标识 | 本地随机 ID，**不收集**账号/邮箱/IP/用户名 | [Telemetry](https://www.onorca.dev/docs/telemetry) |
| 收集内容 | 生命周期启动、加 repo/建 workspace 的方式、启动的 agent 种类、粗粒度 agent 错误类别、少量白名单设置项、遥测开关本身 | 同上 |
| 明确不发送 | 文件内容、prompt、agent 输出、终端内容、**repo 名/分支名/URL/路径/commit message**、原始错误栈、账号信息、IP | 同上 |
| 接收方 | **PostHog Cloud，美国区域**；保留期按 PostHog 套餐默认 | 同上 |
| 关闭方式 | ①设置 → Privacy 关闭"Share anonymous usage data"；②`DO_NOT_TRACK=1`；③`ORCA_TELEMETRY_DISABLED=1`（三者任一即可） | 同上 |

⚠️ **文档内部有矛盾**：Telemetry 页写 "Orca has no account system"，但 Settings 页写 Artifacts 需要 "Orca account — sign in（same account family as Orca Relay）"（[Settings · Artifacts](https://www.onorca.dev/docs/settings)）。结论：**遥测不带账号**，但 Orca 存在一个用于 Artifacts 的可选账号；两者不是一回事。公司合规评审时建议按"数据出网到美国 PostHog，但仅匿名事件"来评估，并默认用环境变量关闭。

#### 2.3 账号与凭据：Orca 是否代理/存储模型凭据？

- 官方定位：**"Orca never sits in the middle"** — "Agents talk to the model providers and CLIs your team already approves."；"**No model in the middle** — Prompts and code go straight to the providers you configure. Orca does not inspect or store them."（[Enterprise](https://www.onorca.dev/enterprise)）
- 但 Orca **确实**有一个"托管账号"能力：`orca account add --agent claude|codex`；CLI 参考原文：

  > "`account add` runs `claude login` / `codex login` in this terminal on the host, then **registers the captured credentials with the local runtime**. Codex uses device authorization so the browser can finish on another machine. Run these on the machine that owns the accounts."
  > — [CLI reference · Account](https://www.onorca.dev/docs/cli/reference)

- 支持**多账号热切换**（Claude/Codex）："Orca supports multiple Claude accounts and can swap between them in one click"（[Claude Code in Orca](https://www.onorca.dev/docs/agents/claude-code)）。
- Claude Code 集成方式是**读本地状态**：Orca "picks up `~/.claude` automatically"、读本地 usage 状态做限额展示（同上）。

本机存在的相关文件（**只看存在性与权限，未读取任何内容**）：

| 路径 | 类型 | 大小 | 权限 |
|------|------|------|------|
| `~/Library/Application Support/orca/agent-session-authority.key` | 文件 | 32 B | `-rw-------` |
| `~/Library/Application Support/orca/orca-e2ee-keypair.json` | 文件 | 144 B | `-rw-------` |
| `~/Library/Application Support/orca/codex-runtime-home/` | 目录 | — | `drwxr-xr-x`（内含 `home/`、`system-default-auth.json`、`shared-runtime-auth-provenance.json`、`migration-v1.json`） |
| `~/Library/Application Support/orca/codex-pane-accounts.json` | 文件 | 359 B | `-rw-------` |
| `~/.orca/` | 目录 | — | 仅含 `agent-hooks/` |

✅ **已核实**：Orca 在本地保存了会话授权密钥、E2EE 密钥对，以及 Codex 账号迁移/认证来源文件 → **Orca 进程本身能接触到 agent 凭据材料**，这与"完全不经手"的营销表述有张力。`codex-runtime-home/` 是 `755`，比同类敏感文件宽松，**值得让安全同学确认里面是否有可复制凭据**（我按约束未读取内容）。

⚠️ **文档未说明**：凭据是否落 Keychain、是否加密、E2EE 密钥对用于什么通道（推测是 Remote Server / 移动端配对加密，文档未明说）。

#### 2.4 企业能力（Enterprise 页原文）

官方页面（[onorca.dev/enterprise](https://www.onorca.dev/enterprise)）的**全部**实质性声明：

- "**AICPA SOC 2** — **Readiness**"（注意是 *readiness*，**不是** "certified"）
- "No silent changes — Every agent change lands in a worktree and a pull request"
- "Audit trail by default — Git history, pull requests, and workspace activity record who ran what, where, and when."
- "**Your providers, your keys** — Agents talk to the model providers and CLIs your team already approves. Orca never sits in the middle."
- "**Self-hostable** — Orca is open source. Run the desktop app, an always-on Orca server, or both inside your own network."
- FAQ："Does Orca store my code or chat history?" → "No. Orca is local-first… Orca does not need to store your source code or chat history on Orca servers for local workspaces."
- FAQ："Can I self-host Orca?" → "**Yes. Orca is open source and self-hostable**, so your team can run it in the environment that fits your security and deployment requirements."
- FAQ："Can I restrict which agents and integrations my organization uses?" → "**Enterprise teams work with us on** deployment requirements, security constraints, and organization-level defaults for how Orca is used with approved agents and integrations."
- FAQ："Is Orca SOC 2 compliant?" → "Orca is built for SOC 2 **readiness**… Email us for the current compliance documentation."

❌ **明确没有的**（页面与文档全文均未见）：

| 项目 | 状态 |
|------|------|
| 定价 / 企业版收费 | ❌ 页面无任何价格信息 |
| SSO / SAML / OIDC | ❌ 全文未出现 |
| 组织级策略下发（把"组织默认值"真正做成产品能力） | ⚠️ 只有"我们和企业一起定"的说法，无功能描述 |
| 审计日志导出 / 合规报告 | ⚠️ 只有 "git history/PR 即审计面" 的说法 |
| 支持 SLA / 商业支持条款 | ❌ 未说明 |
| 是否有企业专属构建/私有 registry | ❌ 未说明 |

➡️ 企业能力目前是**"邮件联系"式销售**，不是自助产品。这直接影响公司推行的可行性评估。

#### 2.5 代码留在公司基础设施上：四种运行模式

（[Ways to run Orca](https://www.onorca.dev/docs/ways-to-run)）

| 模式 | 文件与 agent 在哪 | 机器归属 | 备注 |
|------|-------------------|----------|------|
| Local | 你的桌面 | 你 | 默认路径 |
| SSH target | 远程主机 | 你/团队 | worktree 与 agent 在远端，编辑器/diff/UI 在本地 |
| Remote Orca Server（beta） | 跑 Orca 的机器 | 你/团队 | server 拥有 project/worktree/terminal/session；客户端只是 UI |
| Cloud VM（实验性） | 每 workspace 一个一次性 VM/沙箱 | **你的云账号（BYO）** | 从仓库内 `orca.yaml` + 生命周期脚本的 recipe 拉起 |

官方明确：**"Orca does not sell managed VPS hosting."**、"Orca is a thin wrapper: your provider account, images, and billing stay yours."

SSH 细节（[SSH worktrees](https://www.onorca.dev/docs/ssh)）：支持 system OpenSSH、known_hosts 校验、proxy/jump host、Kerberos/GSSAPI、FIDO2 安全钥匙、端口转发；远端终端需要 node-pty 原生模块，Linux 无 C/C++ 工具链时**远程终端不可用**（文件/git/编辑器可用）。远程 terminal session 经 relay 租约存活，关掉本地 Orca 不杀进程。

Remote Server 细节（[Remote Orca Servers](https://www.onorca.dev/docs/remote-servers)）：beta；建议 Tailscale；每个客户端一个**可吊销 token**；明确警告 **"Do not forward the Orca port directly to the public internet."**；文档也提示要单独在 server 上安装并登录 agent CLI（"A login on your laptop does not automatically carry over to the server."）。

✅ 对公司的意义：**代码可以完全不出公司网络**（SSH 到内网 dev box / 自建 Orca server / 自建 Docker recipe），这条是成立的，且是官方一等公民能力。

#### 2.6 插件信任模型（原文引用）

> "**Plugins (Experimental)** — Plugin system… Turn the system on, then review and enable each plugin individually. **Nothing runs until you consent.**"
> "Marketplaces — add a git marketplace source, browse plugins, preview capabilities (panels, commands, language packs, VM recipes), install, update, or roll back."
> "**Plugin workers always run on this computer; SSH workspace actions still route through Orca.**"
> "Capability and API shapes may change; **treat third-party plugins as untrusted software.**"
> — [Settings · Plugins](https://www.onorca.dev/docs/settings)（原文加粗）

➡️ 官方自己把第三方插件定性为**不可信软件**，且插件 worker **只在本机跑**（不会因为用了 SSH 就隔离到远端）。公司推行时应默认**禁用插件系统**，或建立内部 marketplace + 白名单。

#### 2.7 agent 默认权限：这是公司推行最大的"意外"

> "Orca launches every supported agent with its **full-autonomy permission flag pre-applied** — Claude with `--dangerously-skip-permissions`, Codex with `--dangerously-bypass-approvals-and-sandbox`, Gemini with `--yolo`, and the equivalent for each other agent in the picker. **The intent is that the worktree itself is the sandbox.**"
> — [Agents & sessions · Launch defaults](https://www.onorca.dev/docs/model/agents-sessions)

> "Orca pre-fills each supported CLI's permission-bypass flag for new launches… The reasoning is that worktrees are disposable."
> — [Supported agents · Permissions default](https://www.onorca.dev/docs/agents/supported)

可改：Settings → Agents → **Agent Permissions** 全局切 `Yolo` / `Manual`，或逐个 agent 改 launch arguments（改过的 agent 不会被全局开关覆盖）。

❌ **关键缺陷**：这套"worktree 就是沙箱"的安全论证**在 folder workspace 下不成立** —— folder workspace 里**没有**独立 worktree，agent 就在你的主 checkout 父目录里跑，且默认带 `--dangerously-skip-permissions`。这是我这次评估里最需要公司红队关注的一点。

### 3. 微服务场景的实际落地推演

假设需求横跨 `svc-a` / `svc-b` / `lib-contract` 三个仓库。

#### 方案 A：per-repo worktree（官方一等公民路径）

```
svc-a     → worktree a-feature（分支 feature/x）   child of folder:<groupId>
svc-b     → worktree b-feature（分支 feature/x）   child of folder:<groupId>
lib-contract → worktree c-feature（分支 feature/x） child of folder:<groupId>
```

- ✅ 每个仓库有真正的 Git 隔离，互不干扰
- ✅ 侧边栏靠 `--parent-worktree folder:<id>` 聚成一簇，`orca worktree ps --json` 可见 `parentWorktreeId` / `childWorktreeIds`
- ❌ **一个 agent 只能看到一个仓库**：跨仓库改动需要跨 worktree/跨终端协作，Orca 不提供"跨仓库原子提交/原子 PR"
- ❌ 磁盘与依赖成本 ×N（见 §4.1）
- ⚠️ 本地联调（同时起 3 个服务）需要靠端口转发 / 各 worktree 终端手动协调，**文档未提供"多仓库一起跑"的功能**

#### 方案 B：文件夹工作区（folder workspace）

- ✅ agent 在父目录，能同时读写多个仓库 → 跨仓库搜索/改代码/跑脚本是自然的
- ✅ 一个终端就能 `cd ../svc-b`，符合微服务开发者直觉
- ❌ 不是 worktree：**没有 feature 分支隔离**，agent 直接改你正在用的工作副本
- ❌ 文档**完全没提**如何在 folder workspace 里做并行 agent 隔离；也没有 `orca worktree create --kind folder` 之类的 CLI
- ⚠️ **创建只能走 UI**：本机 CLI 无 `orca folder` 命令（`orca folder --help` → `Unknown command: folder`），`orca worktree create` 也没有创建 folder workspace 的参数。要规模化/自动化建多仓库工作区，**CLI 不支持**

#### 方案 C：monorepo

❌ **文档未说明**。我在全部 14 个已抓取的官方文档页 + sitemap（61 个 URL）中检索 `monorepo` / `mono-repo`，**零命中**。Orca 没有 monorepo 专属概念，只能用普通 per-repo worktree（worktree 里就是一整棵 monorepo 树）。

#### 共享库 / 契约仓库 / 跨仓库依赖接线

❌ **文档未说明**。检索 `shared librar` / `contract` / `cross-repo` 在官方文档中**零命中**。相关的只有仓库内部的依赖共享机制，且是**单仓库内**的：

| 机制 | 用途 | 范围 |
|------|------|------|
| Worktree Shared Paths（Settings → Repository） | gitignored 路径从主 checkout 物化到每个新 worktree（macOS 用 APFS clone-copy，否则 symlink） | **per repo** |
| `orca.yaml` → `worktree.sharedDirectories` | 仓库内声明的 gitignored 目录，symlink/share 复用（如 `node_modules`、`.cache`） | **per repo** |
| `.worktreeinclude` | gitignored 文件/目录**复制**进新 worktree（如 `.env`）；只支持字面路径，glob 和取反会被跳过并告警 | **per repo** |

来源：[Worktrees · Shared directories & gitignored files](https://www.onorca.dev/docs/model/worktrees)、[Settings · Repository](https://www.onorca.dev/docs/settings)

➡️ 也就是说：**"把 `lib-contract` 以本地 link 方式接到 `svc-a`/`svc-b`" 这类跨仓库接线，Orca 没有任何官方机制**，得靠你自己的脚本（setup hooks）或 `gis`/`npm workspaces`/`go.work`/Maven reactor 等语言侧方案。

---

## 相关问题

- **Orca 是不是 Electron 套壳 IDE？** → 是 Electron 应用（内容有 Ghostty 风格终端、xterm.js、Monaco、内建浏览器），`/Applications/Orca.app` 532 MB；主进程 bundle 8 MB，`app.asar` 135 MB。`CFBundleIdentifier = com.stablyai.orca`。它本质是"worktree 管理 + 终端 + diff/PR 审阅 + agent 编排"。
- **`orca worktree list --json` 能拿到什么？** → 每条含 `id`（`<repo-id>::<path>`）、`repoId`、`projectId`、`hostId`、`path`、`head`、`branch`、`isMainWorktree`、`displayName`、`linkedIssue/PR/LinearIssue/GitLabMR`、`isArchived`、`workspaceStatus`、`parentWorktreeId`、`childWorktreeIds`。本机实测 21 条 worktree。**注意没有任何字段表达"这个 workspace 跨了 N 个仓库"** —— 多仓库只体现在 `projectId`/`projectGroupId` 的归属上。
- **`orca worktree ps --json` 里的 `workspaceKind` 是什么？** → 取值为 `git`（worktree）；folder workspace 在内部类型里是 `folder`。这是区分"真 worktree"和"文件夹工作区"的字段。
- **Orca 会不会把我的代码/聊天历史传到它的服务器？** → 官方声明本地优先、不需要把源码或聊天记录存到 Orca 服务器；遥测明确不传内容。但 Remote Orca Server / Artifacts 是例外通道：Artifacts 需要**登录 Orca 账号**并把 HTML/Markdown 传到公开链接（默认关闭，需人工在 Settings → Artifacts 打开，见 [CLI reference · Artifacts](https://www.onorca.dev/docs/cli/reference)）。
- **一台机器跑很多 worktree，Orca 怎么管资源？** → status bar 的 **Resource Manager** 提供 CPU/内存/session 统计、daemon 控制与 **workspace 磁盘扫描**；`Resource Manager → Clean up workspaces` 会列出本地 worktree、主 worktree、folder workspace 以及失联 SSH host 上的 workspace，并显示每项的**状态、最近活动、大小、Git 状态、关联 review**，再选择删除（[Worktrees · Resource Manager cleanup](https://www.onorca.dev/docs/model/worktrees)、[Settings · Appearance](https://www.onorca.dev/docs/settings)）。另有 worktree **archive / sleep / delete** 右键菜单、"Sleep with Descendants"、"Delete with Descendants"，以及实验性的 **Agent hibernation**（默认 idle 30 分钟后休眠，reopen 自动 resume）。
- **删 worktree 会不会连分支一起删？未合并的提交会丢吗？** → 会同时删目录和分支（带确认）。若 git 因未合并提交拒绝删分支，Orca 保留这些分支并弹出 "Review N Branches" 让你逐个处理；**但 workspace 目录不会恢复**（[Worktrees · Preserved branches](https://www.onorca.dev/docs/model/worktrees)）。
- **能不能只在远端跑、本地不留代码？** → 可以。SSH 模式下 worktree 与 agent 在远端；Remote Orca Server 模式下 server 拥有全部状态。但远端需要单独装 git/agent CLI/凭据，且远端终端需要 node-pty 原生模块可编译（否则**终端不可用**）。

---

## 技术拓展

### T1. 为什么"多仓库 worktree"在 Git 层根本不存在

Git 的工作区模型是"一个 worktree ↔ 一个仓库的某个分支"，`git worktree add` 的 `--separate-git-dir`、`core.worktree` 都只在**单个仓库**内描述。跨仓库的原子性只能由上层工具模拟，主流做法有三类：

| 做法 | 代表 | 代价 |
|------|------|------|
| 元仓库 + 子目录（superproject） | `git submodule` / `git subtree` | 子模块指针难用，CI/分支管理复杂 |
| 多仓库工作区清单 | `repo`(Google)、`meta`、`gita`、`mu-repo` | 各仓库 worktree 独立，无统一分支原子性 |
| 多仓库构建/依赖视图 | `go.work`、Maven reactor、`npm/pnpm workspaces`、Nx/Turborepo | 只解决"一起构建"，不解决"一起隔离" |

Orca 的 folder workspace 属于第二类的**轻量版本**：只在父目录级别"给一个共享视图"，连清单文件都没有（没有官方的 `orca-multi.yaml` 之类）。所以它的能力上限就是"一个终端能看到多仓库"，**不提供**"一个需求一套跨仓库隔离副本"。

### T2. 微服务下"一个需求跨 N 仓"的隔离成本模型

per-repo worktree 的成本大致是：

```
总磁盘 ≈ Σ(仓库工作副本大小) + Σ(依赖/构建产物, 每 worktree 一份)
        - 可被 Shared Paths / sharedDirectories 复用掉的部分(仅 gitignored 目录)
```

本机实测参考（`du -sh <repo>/.git`，同一台 M 系列 Mac）：

| 仓库 | `.git` 大小 |
|------|-------------|
| `deepseek-harness` | 274 MB |
| `EduGenius` | 161 MB |
| `claude-code-sourcemap` | 73 MB |
| 小型仓库 | 0.8–2 MB |

注意 `.git` 只是仓库元数据，**工作副本 + 依赖（node_modules / ~/.m2 / Go build cache）通常更大**，而 Orca 的共享机制**只对 gitignored 目录生效**（`node_modules`、`.cache` 这类可以，`target/`、`build/` 也可以，但需要显式声明）。一个需求跨 3 个微服务、每个服务 3 个并行 agent，就是 9 份工作副本 → 建议上线前先按团队真实仓库做一次容量测算。

### T3. 评估结论的置信度分级

本笔记严格区分三类结论，供决策时按置信度取用：

- ✅ **已核实（一手来源：官方文档原文 / 本机 CLI 实际输出 / GitHub API / 应用包实现）**
- ⚠️ **文档未说明 / 需实测**（我不猜）
- ❌ **明确不支持**（官方文档明确说没有，或 CLI/sitemap 证实不存在）

---

## 结论 / 建议

1. **可以把 Orca 当"并行 agent 工作台"引入，但不要把它当"多仓库开发方案"引入。** Orca 的多仓库能力止步于"侧边栏分组 + 一个跑在父目录的共享文件夹工作区"，它没有也不能提供跨仓库的 Git 隔离。微服务的"一个需求跨多仓"问题，Orca 不解决，只是让你在同一个窗口里管 N 个仓库的 N 个 worktree。

2. **小范围试点，选"仓库边界清晰、联调少"的服务。** 单仓库为主、偶尔跨仓库的任务，Orca 的价值（并行 worktree + diff 审阅 + 远程执行）最明显；重联调、契约频繁变动的核心链路，先用方案 A（per-repo worktree + `--parent-worktree folder:<id>` 血缘）小步试。

3. **安全评审要先于功能推广。** 三件事必须在公司环境先决：
   - agent 默认带 `--dangerously-skip-permissions` / `--dangerously-bypass-approvals-and-sandbox`，**必须**在 Settings → Agents → Agent Permissions 切 `Manual`，或在托管配置里逐个改 launch arguments；
   - folder workspace 里的 agent **没有 worktree 隔离**，默认全权限下风险等同"让 agent 直接改你的主 checkout"；
   - 插件系统默认**禁用**（官方自己写 "treat third-party plugins as untrusted software"）。

4. **代码不出内网是可行的，走 SSH target 或自建 `orca serve`**，但企业能力（SSO/策略/审计/支持）目前只有"发邮件谈"，不是产品功能。如果公司硬性要求 SSO/组织级策略，**当前版本大概率不满足**，需要先和厂商确认再立项。

5. **许可友好**：MIT + 可自建，法务与采购层面阻力小；但注意版权方是 `Lovecast Inc.`（非 `stablyai`）。

---

## 上公司前必须实测的清单

按优先级排序，每条都写清"怎么测"和"看什么"：

**P0 — 安全与合规**

1. [ ] **全权限默认值是否可集中管控**：在 Settings → Agents → Agent Permissions 切 `Manual`，确认新起 agent 命令行里**不再出现** `--dangerously-skip-permissions`（用 `orca terminal read` 或 `ps aux | grep claude` 验证）；确认该设置为**机器级还是账号级**、能否由 IT 统一下发（文档未说明，需实测 + 问厂商）。
2. [ ] **托管账号凭据的落地位置**：执行 `orca account add --agent claude`（**需用户在场，涉及真实登录**）后，检查凭据落到 Keychain 还是明文文件；重点确认 `~/Library/Application Support/orca/codex-runtime-home/`（权限 `755`）内是否含可复制凭据。
3. [ ] **遥测在真实运行时确实关闭**：设置 `ORCA_TELEMETRY_DISABLED=1` + 在 UI 关闭开关，然后用网络侧（Little Snitch / 代理日志 / `tcpdump`）确认**没有**到 PostHog 的出站连接（文档声明需实证）。
4. [ ] **私有 marketplace / 插件禁用策略**：确认能否在托管环境中彻底关闭 Plugin system；若公司要自建 marketplace，验证 git 源 + 能力预览是否满足内部审计要求。
5. [ ] **E2EE 密钥对与 Remote Server 配对通道**：`orca-e2ee-keypair.json` 的用途、配对 token 的有效期与吊销路径，在自建 server 上实测一遍（Remote Server 仍为 **beta**）。

**P1 — 多仓库机制是否真的可用**

6. [ ] **拿 2–3 个真实微服务仓库，建一个 project group + folder workspace**（必须在 UI 操作，CLI 不支持创建），然后：
   - 在 folder workspace 里起一个 agent，确认它**能读到所有子仓库**；
   - 同时起**两个** agent，确认它们是否互相踩文件、有无任何隔离（这决定 folder workspace 能不能用于并行）。
7. [ ] **方案 A 血缘验证**：`orca worktree create --repo id:<svc-a-repoId> --name x --parent-worktree folder:<folderId> --json`，然后 `orca worktree list --json` 检查 `parentWorktreeId` / `childWorktreeIds`；再用 `orca worktree ps --json` 看 `workspaceKind` 是否符合预期。
8. [ ] **跨仓库联调**：在 3 个 worktree 里分别起服务，用 SSH/端口转发或本地端口协调跑通一次真实联调，记录手工步骤（预期：**Orca 不提供任何帮助**，全部手工）。
9. [ ] **`--parent-worktree` 的边界**：验证文档说的"excludes archived workspaces and choices that would create a cycle"，以及跨 repo/跨 host 的子级是否被拒绝（官方写 "children across host or repo boundaries are excluded"）。

**P2 — 工程成本**

10. [ ] **磁盘容量测算**：在真实仓库上跑 `Resource Manager → workspace 磁盘扫描`，记录"单任务三仓库"的实际占用；再用 `reclaimableBytes` 判断"archive/sleep 到底能省多少"。按团队并行任务数 × 仓库数做容量规划。
11. [ ] **依赖缓存复用**：为每个仓库配置 `worktree.sharedDirectories`（`node_modules` / `target` / `.cache`）和 `.worktreeinclude`（`.env`），实测新建一个 worktree 的耗时与磁盘占用改善。注意：**glob 不支持**，大仓要枚举路径。
12. [ ] **清理与归档流程**：验证 `Clean up workspaces`、`Sleep with Descendants`、`Delete with Descendants` 在真实多级嵌套下的行为；确认删除后**未合并分支的保留与恢复路径**（目录不恢复，这点要和团队说清）。
13. [ ] **远程执行可行性**：在公司的内网 dev box / K8s VM 上试 SSH target（重点验证 Linux 无 C++ 工具链时"远程终端不可用"的影响范围），或试 `orca serve` + Tailscale；确认 agent CLI 与凭据在远端如何运维。
14. [ ] **CLI 自动化边界**：确认哪些操作**必须走 UI**（已知：创建 folder workspace、创建 project group、SSH target 添加），这决定能否把 Orca 接进内部开发者平台/流水线。

**P3 — 协作与流程**

15. [ ] **PR/评审链路的适配**：验证 GitHub/GitLab/Linear/Jira 连接在公司的自建/私有部署下是否可用（文档提到 GitHub OAuth、Jira Server/DC PAT、Bitbucket；**私有化 GitLab/Gitea/Azure DevOps 的字段在 worktree 结构里存在，但文档覆盖很少**，需实测）。
16. [ ] **团队约定**：一个需求跨 N 仓时，是否统一"同名分支 + folder lineage 聚合"；契约仓库变更如何通知下游（Orca 不提供）。
17. [ ] **版本策略**：cask 注明 `auto_updates true`，即**应用会自更新**（`brew upgrade` 是 no-op，除非 `--greedy`）。公司在受控环境下需确认能否关闭自动更新 / 钉版本（[Homebrew cask 定义](https://github.com/stablyai/homebrew-orca)，cask 内注释解释了 electron-updater 的原地更新行为）。

---

### 附：本笔记的来源清单

| 类型 | 来源 |
|------|------|
| 官方文档 | [Worktrees](https://www.onorca.dev/docs/model/worktrees)、[Settings](https://www.onorca.dev/docs/settings)、[Tabs/panes/splits](https://www.onorca.dev/docs/model/tabs-panes-splits)、[Agents & sessions](https://www.onorca.dev/docs/model/agents-sessions)、[Telemetry](https://www.onorca.dev/docs/telemetry)、[Ways to run](https://www.onorca.dev/docs/ways-to-run)、[SSH](https://www.onorca.dev/docs/ssh)、[Remote Orca Servers](https://www.onorca.dev/docs/remote-servers)、[CLI overview](https://www.onorca.dev/docs/cli/overview)、[CLI reference](https://www.onorca.dev/docs/cli/reference)、[Supported agents](https://www.onorca.dev/docs/agents/supported)、[Claude Code](https://www.onorca.dev/docs/agents/claude-code)、[Native chat](https://www.onorca.dev/docs/agents/native-chat)、[Hibernation](https://www.onorca.dev/docs/agents/hibernation)、[Terminal](https://www.onorca.dev/docs/terminal)、[What is Orca](https://www.onorca.dev/docs) |
| 官网 | [Enterprise](https://www.onorca.dev/enterprise)（含折叠 FAQ 原文） |
| GitHub API | `GET /repos/stablyai/orca`、`GET /repos/stablyai/orca/license` |
| Homebrew | [stablyai/homebrew-orca · Casks/orca.rb](https://github.com/stablyai/homebrew-orca)（`version 1.4.212`，本机 `brew list --cask` 含 `orca`） |
| 本机 CLI（只读） | `orca --help`、`orca repo --help`、`orca repo add --help`、`orca project --help`、`orca project setup-existing-folder --help`、`orca project setups --help`、`orca worktree --help`、`orca worktree create --help`、`orca worktree list --help`、`orca worktree list --json`、`orca worktree ps --json`、`orca worktree show --worktree folder:test --json`、`orca tab --help`、`orca tab create --help`、`orca terminal --help`、`orca terminal create --help`、`orca account --help`、`orca account list --help`、`orca host list --help`、`orca environment list --help`、`orca status --json`、`orca project list --json`、`orca repo list --json`、`orca agent-context --json` |
| 应用包（只读） | `app.asar` → `/LICENSE`、`/package.json`、`/out/main/index.js`（folder workspace 数据结构、终端 cwd 解析、workspaceKind 校验）、`/out/renderer/assets/{store,App,useSettingsNavigationMetadata}-*.js`（Resource Manager 字段、folder workspace 错误文案）；`/Applications/Orca.app/Contents/Info.plist` |

**只读约束说明**：本次评估未执行任何会改变 Orca 状态的命令（未运行 `repo add` / `project setup-*` / `worktree create` / `worktree rm`），未读取任何密钥文件内容，未修改 `~/.claude`，未提交 git，未安装任何软件。
