# AGENTS.md

This file provides guidance to Codex (Codex.ai/code) when working with code in this repository.

## 仓库用途

技术问答笔记仓库，用于记录用户日常提出的问题和解答。

## 笔记记录规则

### 合并同类问题
- 同一主题的多个相关问题记录在同一文档
- 在"相关问题"部分追加拓展提问

### 文档格式

元信息写在 frontmatter 里（Obsidian 属性能识别；正文里的"标签：xxx"识别不了）：

```markdown
---
date: YYYY-MM-DD
tags: [标签1, 标签2]
---

# 标题

## 问题
原问题内容

## 回答
核心回答内容

## 相关问题
- 拓展问题 1 → 回答

## 技术拓展
延伸知识点（可选）
```

**标签规则**：Obsidian 的 tag 不能含空格，多个词的标签用连字符（`KV-Cache`、`AI-Infra`）。

### 长对话学习笔记（AI 整理）

从长对话整理出的学习笔记（区别于逐条问答的老笔记），额外遵守：

- **不搬对话过程**：只留结论、对比表、图示、术语和纠错点。
- **开头必须有「核心结论」**（3 句以内），复习时先看这里。
- **必须有「常见误解」一节**：你忘掉的，往往正是当初搞错的。
- **一篇一主题**；明显长于其他笔记就按主题拆开，用 `[[双链]]` 互连。

### 分类管理
- **所有笔记平铺在仓库根目录**，不建技术分类文件夹（理由见 README）
- 分类用 frontmatter 的 `tags`，导航用根目录 `README.md` 索引
- 新笔记三步：平铺 → 打标签 → 在 README 索引加一行链接
- 图片跟随笔记文件同目录

## 提交规范

使用 Conventional Commits 格式，描述用中文：
- `docs(Git): 添加 Git 数据模型笔记`
- `docs: 更新 README`

**注意**：commit message 不要包含 Co-Authored-By Codex 相关信息。
