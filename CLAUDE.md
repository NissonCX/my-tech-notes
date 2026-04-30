# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 仓库用途

技术问答笔记仓库，用于记录用户日常提出的问题和解答。

## 目录结构

- `Java/` - Java 基础、设计模式、JVM、并发等
- `AI/` - LangChain4j、RAG、向量数据库等（按需创建）
- `Others/` - Git、正则表达式、工具使用等杂项

## 笔记记录规则

### 合并同类问题
- 同一主题的多个相关问题记录在同一文档
- 在"相关问题"部分追加拓展提问，避免创建重复文档
- 示例：`Git数据模型基础概念.md` 中追加 Git Flow、MR 相关问题

### 文档格式
```markdown
# 标题

日期：YYYY-MM-DD
标签：标签1, 标签2

## 问题
原问题内容

## 回答
核心回答内容

## 相关问题
- 拓展问题 1 → 回答

## 技术拓展
延伸知识点（可选）
```

### 分类管理
- 按技术领域分类（Java、AI、Others 等）
- 分类文件夹按需创建
- 图片跟随笔记文件同目录

## 提交规范

使用 Conventional Commits 格式，描述用中文：
- `docs(Git): 添加 Git 数据模型笔记`
- `docs(Java): 补充单例模式相关问题`

**注意**：commit message 不要包含 Co-Authored-By Claude 相关信息。

## 回答风格

- 优先使用代码示例和表格对比
- 从简单方案逐步深入到复杂方案
- 相关问题部分用 `→` 简洁回答，技术拓展详述
