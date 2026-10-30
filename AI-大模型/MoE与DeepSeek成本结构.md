---
date: 2026-10-07
tags: [MoE, 大模型, 推理优化, AI-Infra]
---

# MoE 与 DeepSeek 成本结构

Dense 模型为什么贵，MoE 怎么把“模型容量”和“每 token 计算量”拆开。

## 问题

Dense 模型是什么？MoE 是什么？Router 和专家 FFN 怎么工作？为什么 DeepSeek-V3 能又便宜又强？

## 回答

### 核心结论

1. Dense 模型里，总参数 ≈ 每 token 激活参数；MoE 把两者拆开。
2. MoE 把 FFN 换成 N 个专家 + 一个 router。Router 只做一次矩阵乘法，每个 token 只跑 top-k 个专家。
3. MoE 省 FFN 计算，不省显存；DeepSeek-V3 用 671B 总量 / 37B 激活做到又强又便宜。

### 1. Dense 模型是什么

**Dense model（稠密模型）**：每个 token 都过全部参数。

标准 Transformer 的 FFN 就是 Dense。

```text
FFN(x) = W₂ × activation(W₁ × x + b₁) + b₂
```

- Attention 负责跨 token 混合信息。
- FFN 负责逐 token 做非线性加工。
- 模型的大部分知识存在 FFN 参数里。

Dense 的代价：

```text
能力越大 → 模型越大 → 每 token 计算量越大
```

能力和成本绑在一起。

### 2. MoE 是什么

**MoE = Mixture of Experts，混合专家。**

它把一层 FFN 换成：

- N 个专家 FFN。
- 1 个 router。
- 可能还有 1 个共享专家。

每个专家是一个独立的 FFN。Router 决定每个 token 用哪些专家。

### 3. 路由公式

来源：Shazeer et al., *Outrageously Large Neural Networks: The Sparsely-Gated Mixture-of-Experts Layer*（2017）；DeepSeek-AI, *DeepSeekMoE*（2024）；DeepSeek-AI, *DeepSeek-V3 Technical Report*（2024）。

```text
g = h × W_g
p = softmax(g)
I = TopK(p, k)
p′_i = p_i / Σ_{j ∈ I} p_j        # 只对选中的专家重新归一化
y = Σ_{i ∈ I} p′_i × E_i(h)
```

| 符号 | 含义 | 形状 |
|---|---|---|
| `h` | 当前 token 的 hidden state | `[d_model]` |
| `W_g` | Router 的偏好矩阵 | `[d_model, N]` |
| `g` | 每个专家的原始分数 logits | `[N]` |
| `p` | Softmax 后的专家权重 | `[N]` |
| `I` | 选中的 top-k 专家集合 | `k` 个索引 |
| `E_i` | 专家 i 的 FFN | 独立参数 |
| `y` | MoE 层输出 | `[d_model]` |

假设：

- 每个 token 独立选择 top-k 专家。
- Router 与专家联合训练。
- 只对选中的专家权重重新归一化。

作用：每个 token 只运行 k 个专家 FFN，不运行全部 N 个专家。

### 4. Router 到底在做什么

Router 是一个小线性层。

```text
W_g 的每一列 w_i = 专家 i 的偏好向量
g_i = h · w_i         # 点积
```

要点：

- Router **不运行专家的完整 FFN**。
- 它只做一次矩阵乘法 `h × W_g`。
- `g_i` 越高，表示当前 hidden state 与专家 i 的偏好方向越接近。
- 这个偏好是**训练出来的**，不是人工定义的。
- Router 和专家联合训练：Router 学分配，专家学专长。
- 负载均衡防止所有 token 挤到少数专家。DeepSeek-V3 用 bias 做无辅助损失的负载均衡。

一句话：

> Router 是学习出来的“分诊台”。它用偏好向量做点积，不运行专家网络。

### 5. 专家 FFN 是什么

每个专家就是一个 FFN / MLP。

- 不同专家可以形成分工：代码、中文、数学、长文本等。
- 分工不是人工指定的，是训练出来的。
- **共享专家**永远激活，负责通用知识。
- **路由专家**按 top-k 激活，负责专门知识。
- DeepSeek 使用**细粒度专家**：很多个小专家，而不是少数大专家。

### 6. 为什么省计算，不省显存

```text
所有专家权重：仍然要存在显存里
每个 token：只运行 top-k 个专家
```

所以 MoE 省的是**每 token 的 FFN 计算量**，不是权重存储。

例子：4 个专家，top-2。

```text
Dense：4 个专家的计算量
MoE：  2 个专家的计算量 + Router
显存： 仍然存 4 个专家
```

工程含义：

- API 厂商有大量 GPU 显存，MoE 很划算。
- 16GB 笔记本跑不动大 MoE。Llama 4 Scout 这类 MoE 仍要几十 GB 显存。
- MoE 是“大显存、小计算”，不是“小模型”。

### 7. DeepSeek-V3 的配置与成本

| 项 | 数值 |
|---|---|
| 总参数 | 671B |
| 每 token 激活参数 | 约 37B |
| 路由专家 | 256 个 |
| 共享专家 | 1 个 |
| 每 token 激活 | top-8 路由专家 + 1 个共享专家 |
| 训练精度 | FP8 混合精度 |
| 负载均衡 | 无辅助损失的 bias 方案 |
| 训练目标 | 多 token 预测（MTP） |
| 最终训练运行 | 2.788M H800 GPU 小时，约 $5.576M |

注意：

- $5.576M 是**最终一次训练运行**的 GPU 成本。
- 它不包含前期研究、消融实验、数据成本、人力和失败运行。
- 不要读成“从零训练一个前沿模型只要 560 万美元”。

### 8. 著名模型例子

| 模型 | 类型 | 关键数字 |
|---|---|---|
| GPT-3 175B | Dense | 每个 token 过全部参数 |
| Llama 3 8B / 70B / 405B | Dense | 标准 Dense Transformer |
| Mistral 7B | Dense | Dense FFN；滑动窗口注意力 |
| Qwen2.5 7B / 14B / 32B / 72B | Dense | 这些尺寸是 Dense 版本 |
| Mixtral 8x7B | MoE | 8 专家，top-2；46.7B 总量，约 12.9B 激活 |
| Mixtral 8x22B | MoE | 8 专家，top-2；141B 总量，约 39B 激活 |
| DeepSeek-V2 | MoE + MLA | 236B 总量，21B 激活 |
| **DeepSeek-V3** | **MoE + MLA** | **671B 总量，37B 激活** |
| DeepSeek-V3.2-Exp | MoE + MLA + DSA | 在 V3 基础上加稀疏注意力 |
| Qwen3-30B-A3B | MoE | 30B 总量，3B 激活 |
| Qwen3-235B-A22B | MoE | 235B 总量，22B 激活 |
| Llama 4 Scout | MoE | 109B 总量，17B 激活 |
| Llama 4 Maverick | MoE | 400B 总量，17B 激活 |
| Grok-1 | MoE | 314B 总量，8 专家，2 个激活 |
| DBRX | MoE | 132B 总量，36B 激活 |
| Snowflake Arctic | MoE | 480B 总量，17B 激活 |
| GPT-4 | 疑似 MoE | OpenAI 未正式确认 |
| Gemini 1.5 | 疑似 MoE | Google 未正式确认 |

规律：

- 小模型多用 Dense。
- 大模型越来越多用 MoE。
- 原因是 MoE 把“容量”和“每 token 计算量”拆开。

### 9. 训练与工程难点

- **负载均衡**：防止所有 token 挤到少数专家。专家坍缩后，其余专家得不到训练。
- **通信**：专家分散在多张 GPU 上，token 要发到对应 GPU。这需要 all-to-all 通信。
- **显存**：所有专家都要常驻显存。MoE 适合大显存集群，不适合小显存设备。
- **训练目标**：Router 的 top-k 是离散选择，训练需要特殊处理。DeepSeek-V3 用无辅助损失的 bias 方案做负载均衡。

## 常见误解

| 误解 | 纠正 |
|---|---|
| “Dense 就是小模型” | Dense 指参数使用方式，不是规模。Llama 3 405B 也是 Dense |
| “MoE 是小模型” | MoE 是大模型，小的是每 token 计算量 |
| “MoE 省显存” | 不省。所有专家权重都要存 |
| “Router 要运行每个专家才能打分” | 不。Router 只做一次矩阵乘法 |
| “专家分工是人工指定的” | 不是。Router 和专家联合训练出来的 |
| “Dense 和 MoE 是二选一” | 不是。MoE 只替换 FFN；Attention 仍然可以是 Dense。DeepSeek = MoE FFN + MLA/DSA attention |
| “671B 模型每 token 要算 671B” | 只激活约 37B |

## 相关问题

- **Dense 和 MoE 是二选一吗？** → 不是。MoE 替换 FFN；Attention 可以保持 Dense。DeepSeek 同时用 MoE FFN 和 MLA/DSA attention。
- **Router 需要运行专家吗？** → 不需要。Router 只做 `h × W_g`，然后用 top-k 选择。
- **MoE 为什么适合 API 厂商？** → 因为它是“大显存、小计算”。API 厂商有大量 GPU 显存，可以摊薄权重存储成本。
- **共享专家是什么？** → 永远激活的专家，负责通用知识，减轻路由专家的负担。
- **DeepSeek 为什么又便宜又强？** → MoE 给容量，激活参数控成本；MLA 压 KV 存储；DSA 降长上下文注意力成本；FP8 和基础设施再降训练与服务成本。

## 延伸阅读

- KV 存储侧的压缩 → [[MLA原理与RoPE解耦]]
- 注意力侧的稀疏化 → [[DSA稀疏注意力]]
- Attention 与 FFN 的分工 → [[大模型推理基础]]
- 在线模型成本与价格 → [[2026年10月-在线大模型性价比调研]]
