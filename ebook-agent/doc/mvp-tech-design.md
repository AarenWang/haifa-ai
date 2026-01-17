

# 📄 文档二：MVP 技术设计文档

> 文件名建议：`MVP-Tech-Design.md`

---

## 1. 技术选型

### 1.1 技术栈

| 层级        | 技术           |
| --------- | ------------ |
| 语言        | Python 3.10+ |
| RAG 框架    | LlamaIndex   |
| 向量数据库     | Qdrant       |
| Embedding | OpenAI / 可替换 |
| LLM       | OpenAI / 可替换 |
| 存储        | 本地文件系统       |

---

## 2. 系统整体架构

```
+----------------------+
|   User Interface     |  (CLI / 简易 Web)
+----------+-----------+
           |
           v
+----------------------+
|   Query Service      |
|  - 检索              |
|  - Prompt 构造        |
|  - 引用约束           |
+----------+-----------+
           |
           v
+----------------------+
|   LlamaIndex Engine  |
|  - Retriever         |
|  - Response Synth.   |
+----------+-----------+
           |
           v
+----------------------+
|   Qdrant Vector DB   |
+----------------------+

+----------------------+
|   Book Ingestor      |
|  - PDF / EPUB 解析    |
|  - Chunk 切分         |
|  - Embedding          |
+----------------------+
```

---

## 3. 数据模型设计

### 3.1 Chunk Metadata 设计（核心）

```json
{
  "book_id": "uuid",
  "book_title": "书名",
  "author": "作者",
  "chapter": "第3章 / 3.2 小节",
  "page": "45-46",
  "chunk_index": 12,
  "text": "原文内容..."
}
```

### 3.2 Qdrant Collection

* collection_name: `book_chunks`
* vector_size: embedding 模型维度
* payload: metadata（用于过滤 & 展示）

---

## 4. 文档处理流程设计

### 4.1 电子书解析

#### PDF

* 使用 `pdfplumber` / `PyMuPDF`
* 优先读取文本层
* 按页面 → 段落 → 章节切分

#### EPUB

* 使用 `ebooklib`
* 直接利用章节结构

---

### 4.2 Chunk 切分策略（强约束）

* Chunk size：600–1200 字符
* Overlap：80–150 字符
* 优先在：

  * 标题边界
  * 段落边界
* 禁止跨章节混合

---

## 5. 向量检索设计

### 5.1 检索参数（初始）

* Top-K：5–8
* 相似度阈值：可配置
* 检索结果必须附带 metadata

---

## 6. 回答生成策略（非常关键）

### 6.1 Prompt 核心原则

* **只能基于提供的上下文回答**
* 每个结论都要引用
* 不确定即说明“不确定”

示意 Prompt：

```
你是一个基于书籍的知识助理。
只能基于以下引用内容作答。
如果引用内容中没有答案，请明确说明未找到。

回答时：
1. 先给出简明结论
2. 列出引用来源（书名 / 章节）
3. 附上原文片段
```

---

## 7. MVP 目录结构建议

```
src/
├── ingest/
│   ├── scan_books.py
│   ├── parse_pdf.py
│   ├── parse_epub.py
│   ├── chunker.py
│   └── embed_store.py
├── query/
│   ├── retriever.py
│   ├── prompt.py
│   └── answer.py
│   └── cli.py
├── config/
│   └── settings.yaml
├── data/
│   └── books/
├── main.py
└── requirements.txt
```

---

## 8. 安全与约束（MVP 级）

* 不缓存完整书籍到云端
* 仅发送必要 chunk 给 LLM
* 所有原文保留在本地

---

## 9. 后续可扩展点（非 MVP）

* BM25 + 向量混合检索
* Rerank 模型
* 书籍增量更新
* 用户笔记融合
* 主题索引 / 概念卡片

---

## ✅ 下一步我可以直接继续帮你做的事

你可以直接选一个，我就**往下写代码级内容**：

1️⃣ **把这套 PRD/设计转成第一版可运行代码（Python）**
2️⃣ 给你 **Chunk / Metadata 的最佳实践示例**
3️⃣ 帮你设计 **“强制引用不胡说”的 Prompt 模板**
4️⃣ 帮你加一个 **CLI 查询界面**

你选哪个，我们就继续往下“真做”。
