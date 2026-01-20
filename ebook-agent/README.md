# ebook-agent

个人电子书知识库检索与问答（RAG）。

## 目录结构

- `ebooks/`：电子书目录（放 PDF/EPUB）
- `src/`：代码与配置
- `doc/`：设计文档

## 运行前准备

### 1) Python 环境

建议 Python 3.10+。

```bash
python3 -m venv venv
source venv/bin/activate
```

### 2) 安装依赖

```bash
pip install -r src/requirements.txt
```

### 3) 启动 Qdrant（本地向量库）

如果本地没有 Qdrant，可用 Docker 启动：

```bash
docker run -d --name qdrant -p 6333:6333 qdrant/qdrant
```

### 4) 配置环境变量

本项目使用 Gemini，需要设置 API Key：

```bash
export GOOGLE_API_KEY=你的key
```

### 5) 配置书籍目录

把电子书放到：

```
ebook-agent/ebooks
```

配置文件在 [src/config/settings.yaml](src/config/settings.yaml)：

- `books_dir`：书籍目录（已默认 `../ebooks`）
- `qdrant_url`：Qdrant 地址（默认 `http://localhost:6333`）
- `embedding_model` / `llm_model`：Gemini 模型名称

## 运行

进入 `src` 目录执行：

```bash
cd src
```

### 1) 导入电子书并建立索引

```bash
python main.py ingest
```

### 2) 提问

```bash
python main.py query "你的问题"
```

## 常见问题

- 依赖安装失败：请确认网络可访问 PyPI，或更换镜像。
- 无法连接 Qdrant：确认 Qdrant 已启动且端口 `6333` 可访问。
- 无法调用 Gemini：确认 `GOOGLE_API_KEY` 已设置。
