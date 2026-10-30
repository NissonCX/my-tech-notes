---
date: 2026-10-07
tags: [DSA, 稀疏注意力, 大模型, 推理优化]
---

# DSA 稀疏注意力

DSA 怎么把长上下文注意力的昂贵部分从 `O(L²)` 降到 `O(L·k)`。

## 问题

DSA 是什么？它和 MoE、MLA、滑动窗口、FlashAttention 有什么区别？为什么它能降低长上下文成本？

## 回答

### 核心结论

1. **DSA = DeepSeek Sparse Attention。** 标准 attention 让每个 query 和全部历史 key 算分数；DSA 只让主注意力算 top-k 个 key。
2. DSA 用轻量 lightning indexer 给所有历史 token 打便宜分数，再选 top-k。主注意力从 `O(L²)` 降到 `O(L·k)`。
3. MLA 让 KV 存得小；DSA 让注意力算得少。两者互补。

### 1. 标准注意力为什么贵

设上下文长度是 `L`。

Prefill：

```text
L 个 query × L 个 key = L² 个注意力分数
```

Decode：

```text
每生成 1 个 token：和 L 个历史 key 算分数
每生成 1 个 token：读 L 份 KV
```

`L = 100,000` 时，`L² = 10^10`。这就是长上下文最贵的地方。

### 2. DSA 的三步

1. 当前 query 进入 **lightning indexer**。
2. Indexer 给每个历史 token 打一个便宜的相关性分数。
3. 选出 top-k 个 token。
4. 主 MLA 注意力只对这 k 个 token 计算。
5. 输出是这 k 个 token 的加权和。

```text
索引阶段：所有历史 token 都打分     ← 便宜
选择阶段：取 top-k                  ← 便宜
主注意力：只算 k 个 token           ← 贵，但数量少
```

### 3. 为什么省钱

```text
标准主注意力：O(L²) 个昂贵分数
DSA：          O(L²) 个便宜索引分数 + O(L × k) 个昂贵分数
```

最贵的部分从 `O(L²)` 降到 `O(L × k)`。

Decode 时，最贵的 KV 读取也从 `O(L)` 降到 `O(k)`。

注意：

- Indexer 仍然要给所有 token 打分。它不是免费。
- Indexer 很轻：头数少，常用 FP8。
- 主注意力很贵：头数多，精度高。它只算 top-k。

### 4. 示意算例

```text
L = 100,000
k = 2,048

标准主注意力分数：100,000 × 100,000 = 10^10
DSA 主注意力分数：100,000 × 2,048 = 2.048 × 10^8
```

昂贵部分约减少 50 倍。

具体 `k` 值和实现细节，以 DeepSeek-V3.2-Exp 技术报告为准。

### 5. Indexer 怎么训练

- 主模型从 V3.1-Terminus 继续训练。
- Indexer 学习模仿原来的密集注意力分布。
- 主模型继续训练，适应稀疏选择。
- 具体训练 token 数、损失函数和 `k` 值，待核 DeepSeek-V3.2-Exp 技术报告。

来源：DeepSeek-AI, *DeepSeek-V3.2-Exp Technical Report*（2025-09）；DeepSeek API 文档。

### 6. DSA 不是什么

| 容易混淆 | 纠正 |
|---|---|
| DSA = MoE | 不是。MoE 稀疏 FFN 专家；DSA 稀疏注意力连接 |
| DSA = 滑动窗口 | 不是。滑动窗口只看最近 token；DSA 动态选择最相关 token，可以选到很远的 token |
| DSA = MLA | 不是。MLA 压缩 KV 存储；DSA 减少注意力计算和 KV 读取 |
| DSA = FlashAttention | 不是。FlashAttention 仍算全部 `L²` 分数，只是 IO 更高效；DSA 只算一部分分数 |
| DSA 让模型更聪明 | 不是。DSA 是成本优化，让长上下文更便宜 |
| DSA 不给低相关 key 打分 | 不是。Indexer 仍要给所有历史 key 打便宜分数，再选 top-k |
| DSA 减少 KV Cache 存储 | 不是。MLA 才减少存储。DSA 减少主注意力计算和 KV 读取 |

### 7. 两类稀疏，不要混

| 机制 | 稀疏的连接 | 省什么 |
|---|---|---|
| **MoE** | token ↔ 专家 FFN | FFN 计算量 |
| **DSA** | token ↔ token 注意力 | 主注意力计算量和 KV 读取 |

一个是“少算专家”。一个是“少看 token”。

### 8. MLA 和 DSA 的关系

| | MLA | DSA |
|---|---|---|
| 压缩什么 | KV 存储 | 注意力连接 |
| 缓存存什么 | `c + k_rope` | 主 KV 仍要存；另加 indexer 的小 key |
| 省什么 | 显存容量和带宽 | 主注意力计算量和 KV 读取 |
| 解决什么 | 长上下文显存 | 长上下文注意力成本 |

两者互补。DeepSeek-V3.2 同时使用两者。

## 常见误解

| 误解 | 纠正 |
|---|---|
| “DSA 是 MoE 的别名” | 不是。MoE 稀疏 FFN 参数；DSA 稀疏注意力连接 |
| “DSA 只关注最近 token” | 不是。那是滑动窗口。DSA 动态选 top-k，可以选到很远的 token |
| “DSA 减少 KV Cache 存储” | 不是。MLA 才减少存储；DSA 减少主注意力计算和 KV 读取 |
| “DSA 和 FlashAttention 一样” | 不是。FlashAttention 算全部 `L²` 分数；DSA 只算一部分 |
| “DSA 完全不用给低相关 key 打分” | 不是。Indexer 仍要给所有 key 打便宜分数 |
| “DSA 让模型更聪明” | 不是。DSA 是成本优化 |

## 相关问题

- **DSA 的 top-k 是多少？** → 以 DeepSeek-V3.2-Exp 技术报告为准。本文不凭记忆报数。
- **DSA 会降低质量吗？** → DeepSeek 报告称长上下文效果基本保持。具体评测以报告为准。
- **DSA 和滑动窗口的区别？** → 滑动窗口是固定模式，只看最近 N 个；DSA 是学习出来的动态选择，可以选到很远的 token。
- **DSA 和 FlashAttention 的区别？** → FlashAttention 是精确算法，仍算全部 `L²`；DSA 是稀疏算法，只算 top-k。
- **DSA 和 MLA 的关系？** → MLA 压 KV 存储，DSA 稀疏注意力。两者互补。
- **为什么 DSA 还要 indexer？** → 没有真值相关性。先用便宜分数近似筛选，再让昂贵的主注意力只算 top-k。

## 延伸阅读

- KV 存储侧的压缩 → [[MLA原理与RoPE解耦]]
- FFN 侧的稀疏化 → [[MoE与DeepSeek成本结构]]
- KV Cache 的基础 → [[KV-Cache原理]]
- prefill / decode 的瓶颈 → [[推理性能与显存]]
- Attention 的基础 → [[大模型推理基础]]
