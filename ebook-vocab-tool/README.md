# ebook-vocab-tool (spaCy)

一个本地/离线的电子书词汇分析工具：

- 读取 `.txt`、`.md`、`.epub`、`.pdf`
- 规范化并清理文本
- 分词 + 词性标注 + 词形还原（词元频次）
- 对专有名词进行 NER（PERSON/GPE/LOC/ORG 等）
- 将频次列表导出为 CSV

## 快速开始（macOS zsh）

```bash
cd ebook-vocab-tool
./scripts/setup_venv.sh
./scripts/run.sh /path/to/book.epub --out ./out --top-lemmas 5000
```

可选参数：

```text
--out <dir>  输出目录（默认 ./out）
--top-lemmas <int>  导出 Top N 词元（默认 5000）
--top-entities <int>  每类实体导出 Top N（默认 2000）
--keep-stopwords  保留停用词（默认过滤）
--include-entity-labels <labels>  逗号分隔的实体标签（默认常见标签）
--max-chars <int>  仅分析前 N 字符（0 表示不限制）
--disable-epub-structured-filter  关闭 EPUB TOC/spine 结构化过滤（仅使用关键词过滤）
--disable-pdf-outline-filter  关闭 PDF 书签/大纲过滤（默认开启）
--min-body-ratio <float>  章节正文比例阈值（0 关闭；建议 0.7~0.85）
--min-chapter-words <int>  章节最小正文词数（0 关闭；建议 200~500）
--log-level {debug,info,warning,error}  日志级别（默认 info）
```

输出（会根据输入文件名创建子目录）：
- `out/<book>/lemmas.csv`
- `out/<book>/lemmas_anki.csv`
- `out/<book>/entities/entities_PERSON.csv` 等

## Anki CSV（lemmas_anki.csv）

每行包含：

```text
lemma,count,Example,Source,Tags
```

示意：

```text
astonish,42,"She was astonished by the news.",Harry Potter 1,ebook::hp1
```

**Anki 导入时的关键设置：**

- 分隔符：Comma（,）
- 字段映射：按你 CSV 顺序手动对应
- 不要勾选「第一行是字段名」
- 允许 HTML（如果你例句里有斜体）

## 备注
- PDF 提取质量取决于 PDF 是否包含嵌入文本（扫描版 PDF 可能需要 OCR）。
- spaCy 模型会在安装时下载一次（`en_core_web_sm`）。


# spaCy 命名实体类型说明（NER Entities Guide）

 `out/entities/` 目录下生成的各类 `entities_XXX.csv` 文件含义，帮助你理解 **spaCy 命名实体识别（Named Entity Recognition, NER）** 的分类体系，以及它们在电子书分析、语言学习和知识抽取中的实际用途。

---

## 目录结构总览

```text
out/
└── entities/
    ├── entities_EVENT.csv
    ├── entities_FAC.csv
    ├── entities_GPE.csv
    ├── entities_LOC.csv
    ├── entities_NORP.csv
    ├── entities_ORG.csv
    ├── entities_PERSON.csv
    ├── entities_PRODUCT.csv
    └── entities_WORK_OF_ART.csv
```

含义说明：

* spaCy 会在全文中识别 **专用名词（Proper Nouns）**
* 按“语义类别”进行分组
* 每个 CSV 文件内容结构通常为：

```text
实体原文, 在全文中出现的次数
```

---

## 各实体类型详细说明

### PERSON（人名）

**文件：** `entities_PERSON.csv`

**定义**
指真实或虚构人物的名字。

**典型示例**

* Harry Potter
* Dumbledore
* Napoleon
* Elizabeth Bennet
* Sherlock Holmes

**使用建议**

* 小说：可直接生成“人物表”
* 历史/传记：人物索引
* ⚠️ 通常不纳入词汇背诵体系（否则学习噪声极大）

---

### GPE（地缘政治实体）

**文件：** `entities_GPE.csv`

**全称**
Geo-Political Entity

**定义**
国家、城市、行政区等具有政治或行政属性的地名。

**典型示例**

* China
* England
* London
* Paris
* New York

**使用建议**

* 历史 / 国际关系 / 新闻类文本核心信息
* 可独立做“地理词表”或背景索引

---

### LOC（地理位置）

**文件：** `entities_LOC.csv`

**定义**
不具备政治或行政属性的自然或抽象地点。

**典型示例**

* the Pacific Ocean
* Mount Everest
* Sahara Desert
* outer space

**与 GPE 的区别**

* GPE：人类政治划分的区域
* LOC：自然存在或抽象空间

---

### ORG（组织机构）

**文件：** `entities_ORG.csv`

**定义**
公司、机构、学校、政府、军队、宗教组织等。

**典型示例**

* Google
* United Nations
* Hogwarts
* Apple Inc.
* CIA

**使用建议**

* 商业 / 科技 / 政治类书籍极其重要
* 可用于组织关系、时代背景分析

---

### NORP（民族 / 宗教 / 政治群体）

**文件：** `entities_NORP.csv`

**全称**
Nationalities, Religious or Political groups

**定义**
民族、国籍、宗教或政治群体名称。

**典型示例**

* Americans
* British
* Christians
* Buddhists
* Democrats

**使用建议**

* 社会学、历史、政治文本关键理解点
* 在英语学习中常被忽略，但对理解语境非常重要

---

### FAC（设施 / 建筑）

**文件：** `entities_FAC.csv`

**全称**
Facilities

**定义**
人造的大型设施或建筑结构。

**典型示例**

* the White House
* airports
* bridges
* highways
* the Great Wall

**使用建议**

* 城市、战争、旅行类文本
* 作为背景信息使用即可

---

### PRODUCT（产品 / 商品）

**文件：** `entities_PRODUCT.csv`

**定义**
商业产品、工具、软件、设备名称。

**典型示例**

* iPhone
* Windows
* Tesla Model S
* PlayStation

**使用建议**

* 科技 / 商业 / 当代文本分析价值高
* 可用于分析时代特征或技术背景

---

### WORK_OF_ART（作品名称）

**文件：** `entities_WORK_OF_ART.csv`

**定义**
文学、艺术、影视、音乐等作品名称。

**典型示例**

* *Harry Potter and the Philosopher’s Stone*
* *The Lord of the Rings*
* *Mona Lisa*
* *Star Wars*

**使用建议**

* 文学研究、文化分析
* 可构建作品引用或文化索引

---

### EVENT（事件）

**文件：** `entities_EVENT.csv`

**定义**
历史、社会、政治、体育等重大事件。

**典型示例**

* World War II
* the French Revolution
* the Olympics
* the Renaissance

**使用建议**

* 历史与社科书籍的关键信息骨架
* 可直接用于时间线或事件索引

---

## 总体使用策略建议

### 1️⃣ 语言学习

* **只从 `lemmas.csv` 学习词汇**
* 所有 entities 默认视为“世界知识”，不纳入背诵

### 2️⃣ 小说分析

* PERSON + GPE → 人物与世界观
* lemmas → 作者真实用词水平

### 3️⃣ 非虚构 / 专业书籍

* ORG / EVENT / NORP → 核心理解点
* lemmas → 专业术语密度分析

