from __future__ import annotations

import csv
import re
from collections import Counter, defaultdict
import logging
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

_WORD_RE = re.compile(r"^[A-Za-z][A-Za-z'\-]*$")

_EPUB_SKIP_KEYWORDS = (
    "title",
    "cover",
    "copyright",
    "toc",
    "contents",
    "preface",
    "foreword",
    "introduction",
    "acknowledg",
    "dedication",
    "about",
    "publisher",
    "imprint",
)

_LOGGER = logging.getLogger(__name__)

_START_PATTERNS = (
    r"^\s*chapter\s+(\d+|[ivxlcdm]+)\b",
    r"^\s*part\s+(\d+|[ivxlcdm]+)\b",
    r"^\s*第\s*[0-9一二三四五六七八九十百千]+\s*章",
    r"^\s*序\s*章\b",
)

_END_PATTERNS = (
    r"^\s*about\s+the\s+author\b",
    r"^\s*acknowledg(e)?ments?\b",
    r"^\s*appendix\b",
    r"^\s*notes\b",
    r"^\s*bibliograph(y|ies)\b",
    r"^\s*index\b",
)

_CHAPTER_TITLE_PATTERNS = (
    r"^\s*chapter\s+(\d+|[ivxlcdm]+)\b",
    r"^\s*part\s+(\d+|[ivxlcdm]+)\b",
    r"^\s*第\s*[0-9一二三四五六七八九十百千]+\s*章",
)


def normalize_output_name(name: str) -> str:
    base = re.sub(r"[^\w]+", "_", name, flags=re.UNICODE).strip("_")
    return base.lower() if base else "ebook"


def should_skip_epub_item(item_name: str) -> bool:
    lowered = item_name.lower()
    return any(keyword in lowered for keyword in _EPUB_SKIP_KEYWORDS)


def _normalize_epub_href(href: str) -> str:
    base = href.split("#", 1)[0]
    return base.strip().lower()


def _iter_toc_items(toc: object) -> List[object]:
    items: List[object] = []
    if isinstance(toc, (list, tuple)):
        for entry in toc:
            items.extend(_iter_toc_items(entry))
        return items
    if toc is None:
        return items
    items.append(toc)
    # Some ebooklib toc nodes are tuples like (section, [children])
    if isinstance(toc, tuple) and len(toc) == 2 and isinstance(toc[1], (list, tuple)):
        items.extend(_iter_toc_items(toc[1]))
    return items


def _extract_allowed_epub_hrefs(book: object) -> Set[str]:
    toc_items = _iter_toc_items(getattr(book, "toc", []))
    allowed: Set[str] = set()
    for item in toc_items:
        href = getattr(item, "href", None)
        title = getattr(item, "title", "") or getattr(item, "label", "") or ""
        if not href:
            continue
        if should_skip_epub_item(title):
            continue
        normalized = _normalize_epub_href(href)
        if normalized:
            allowed.add(normalized)
            allowed.add(Path(normalized).name)
    return allowed


def _find_first_match_line(lines: List[str], patterns: Tuple[str, ...]) -> Optional[int]:
    for i, line in enumerate(lines):
        for pattern in patterns:
            if re.search(pattern, line, flags=re.IGNORECASE):
                return i
    return None


def _find_last_match_line(lines: List[str], patterns: Tuple[str, ...]) -> Optional[int]:
    for i in range(len(lines) - 1, -1, -1):
        line = lines[i]
        for pattern in patterns:
            if re.search(pattern, line, flags=re.IGNORECASE):
                return i
    return None


def trim_front_back_matter(text: str) -> str:
    lines = re.split(r"\r?\n", text)
    start_idx = _find_first_match_line(lines, _START_PATTERNS)
    end_idx = _find_last_match_line(lines, _END_PATTERNS)

    if start_idx is None:
        start_idx = 0

    if end_idx is not None and end_idx > start_idx:
        lines = lines[start_idx:end_idx]
    else:
        lines = lines[start_idx:]

    return "\n".join(lines)


def _is_chapter_title(line: str) -> bool:
    return any(re.search(pattern, line, flags=re.IGNORECASE) for pattern in _CHAPTER_TITLE_PATTERNS)


def _split_chapters(text: str) -> List[str]:
    lines = re.split(r"\r?\n", text)
    indices = [i for i, line in enumerate(lines) if _is_chapter_title(line)]
    if not indices:
        return [text]
    indices.append(len(lines))
    chunks: List[str] = []
    for start, end in zip(indices, indices[1:]):
        chunk = "\n".join(lines[start:end]).strip()
        if chunk:
            chunks.append(chunk)
    return chunks


def _count_words(text: str) -> Tuple[int, int]:
    english_words = re.findall(r"[A-Za-z]+(?:'[A-Za-z]+)?", text)
    chinese_chars = re.findall(r"[\u4e00-\u9fff]", text)
    total_tokens = re.findall(r"\w+", text)
    body_words = len(english_words) + len(chinese_chars)
    total_words = max(len(total_tokens) + len(chinese_chars), 1)
    return body_words, total_words


def filter_chapters_by_density(text: str, *, min_body_ratio: float, min_chapter_words: int) -> str:
    if min_body_ratio <= 0 and min_chapter_words <= 0:
        return text
    chunks = _split_chapters(text)
    kept: List[str] = []
    for chunk in chunks:
        body_words, total_words = _count_words(chunk)
        ratio = body_words / total_words if total_words else 0.0
        if min_chapter_words > 0 and body_words < min_chapter_words:
            continue
        if min_body_ratio > 0 and ratio < min_body_ratio:
            continue
        kept.append(chunk)
    if not kept:
        return text
    return "\n".join(kept)


def project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def load_word_list(csv_path: Path) -> Set[str]:
    if not csv_path.exists():
        return set()
    words: Set[str] = set()
    with csv_path.open("r", encoding="utf-8") as f:
        reader = csv.reader(f)
        word_index: Optional[int] = None
        for row in reader:
            if not row:
                continue
            if word_index is None:
                lowered = [col.strip().lower() for col in row]
                if "word" in lowered:
                    word_index = lowered.index("word")
                    continue
                word_index = 0
            if word_index >= len(row):
                continue
            word = row[word_index].strip().lower()
            if not word or word == "word":
                continue
            words.add(word)
    return words


def read_txt(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def read_epub(path: Path, *, structured_filter: bool = True) -> str:
    from ebooklib import epub, ITEM_DOCUMENT
    from bs4 import BeautifulSoup

    book = epub.read_epub(str(path))
    allowed_hrefs: Set[str] = set()
    if structured_filter:
        allowed_hrefs = _extract_allowed_epub_hrefs(book)
        if allowed_hrefs:
            _LOGGER.info("EPUB TOC filter enabled: %d toc hrefs", len(allowed_hrefs))
        else:
            _LOGGER.info("EPUB TOC filter enabled but no toc hrefs found; fallback to keyword filter")
    parts = []
    total_items = 0
    kept_items = 0
    for item in book.get_items():
        if item.get_type() == ITEM_DOCUMENT:
            total_items += 1
            item_name = item.get_name()
            item_key = _normalize_epub_href(item_name)
            item_basename = Path(item_key).name
            if structured_filter and allowed_hrefs:
                if item_key not in allowed_hrefs and item_basename not in allowed_hrefs:
                    continue
            else:
                if should_skip_epub_item(item_name):
                    continue
            soup = BeautifulSoup(item.get_content(), "html.parser")
            parts.append(soup.get_text(" "))
            kept_items += 1
    if structured_filter:
        _LOGGER.info("EPUB items kept: %d/%d", kept_items, total_items)
    return "\n".join(parts)


def read_pdf(
    path: Path,
    *,
    outline_filter: bool = True,
    outline_start_patterns: Tuple[str, ...] = _START_PATTERNS,
    outline_end_patterns: Tuple[str, ...] = _END_PATTERNS,
) -> str:
    import fitz

    doc = fitz.open(str(path))
    page_start = 0
    page_end = doc.page_count

    if outline_filter:
        toc = doc.get_toc() or []
        start_page: Optional[int] = None
        end_page: Optional[int] = None
        for _, title, page in toc:
            if start_page is None and any(re.search(p, title, flags=re.IGNORECASE) for p in outline_start_patterns):
                start_page = max(page - 1, 0)
            if start_page is not None and any(re.search(p, title, flags=re.IGNORECASE) for p in outline_end_patterns):
                end_page = max(page - 1, 0)
                if end_page > start_page:
                    break
        if start_page is not None:
            page_start = start_page
        if end_page is not None and end_page > page_start:
            page_end = end_page
        _LOGGER.info("PDF outline filter: pages %d-%d of %d", page_start + 1, page_end, doc.page_count)

    parts = [doc.load_page(i).get_text("text") for i in range(page_start, page_end)]
    doc.close()
    return "\n".join(parts)


def read_ebook(
    path: Path,
    *,
    epub_structured_filter: bool = True,
    pdf_outline_filter: bool = True,
) -> str:
    suffix = path.suffix.lower()
    if suffix in {".txt", ".md"}:
        return read_txt(path)
    if suffix == ".epub":
        return read_epub(path, structured_filter=epub_structured_filter)
    if suffix == ".pdf":
        return read_pdf(path, outline_filter=pdf_outline_filter)
    raise ValueError(f"Unsupported file type: {suffix}")


def normalize_text(text: str) -> str:
    # Join hyphenated line breaks: hyphen-\nated -> hyphenated
    text = re.sub(r"(\w)-\n(\w)", r"\1\2", text)
    # Collapse whitespace
    text = re.sub(r"\s+", " ", text)
    # Normalize punctuation variants
    text = text.replace("’", "'").replace("“", '"').replace("”", '"').replace("—", "-")
    return text.strip()


def analyze_with_spacy(
    text: str,
    *,
    keep_stopwords: bool,
    include_entity_labels: Set[str],
    max_examples_per_lemma: int = 2,
) -> Tuple[Counter, Dict[str, Counter], Dict[str, List[str]]]:
    """
        Run spaCy pipeline and return:
            - lemma_freq: Counter({lemma: count})
            - entity_freq_by_label: {label: Counter({entity_text: count})}
            - lemma_examples: {lemma: [sentence1, sentence2]}
    """
    import spacy

    # Disable parser for speed; keep tagger/lemmatizer/ner
    nlp = spacy.load("en_core_web_sm", disable=["parser"])
    if "sentencizer" not in nlp.pipe_names:
        nlp.add_pipe("sentencizer")

    lemma_freq: Counter = Counter()
    entity_freq_by_label: Dict[str, Counter] = defaultdict(Counter)
    lemma_examples: Dict[str, List[str]] = defaultdict(list)

    doc = nlp(text)

    # Entities
    for ent in doc.ents:
        if ent.label_ in include_entity_labels:
            entity_freq_by_label[ent.label_][ent.text] += 1

    # Lemmas + example sentences
    for token in doc:
        if token.is_space or token.is_punct:
            continue
        if token.like_num:
            continue
        if not _WORD_RE.match(token.text):
            continue
        if (not keep_stopwords) and token.is_stop:
            continue

        lemma = token.lemma_.lower().strip()
        if lemma in {"'s", "''", "'"}:
            continue
        lemma_freq[lemma] += 1

        if max_examples_per_lemma > 0 and len(lemma_examples[lemma]) < max_examples_per_lemma:
            sent_text = token.sent.text.strip()
            if sent_text and sent_text not in lemma_examples[lemma]:
                lemma_examples[lemma].append(sent_text)

    return lemma_freq, entity_freq_by_label, lemma_examples


def export_top_lemmas(lemma_freq: Counter, out_csv: Path, top_n: int) -> None:
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    with out_csv.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["lemma", "count"])
        for lemma, cnt in lemma_freq.most_common(top_n):
            w.writerow([lemma, cnt])


def export_entities(entity_freq_by_label: Dict[str, Counter], out_dir: Path, top_n: int) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    for label, counter in entity_freq_by_label.items():
        out_csv = out_dir / f"entities_{label}.csv"
        with out_csv.open("w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["entity", "count"])
            for ent, cnt in counter.most_common(top_n):
                w.writerow([ent, cnt])


def export_anki_csv(
    lemma_freq: Counter,
    lemma_examples: Dict[str, List[str]],
    out_csv: Path,
    *,
    top_n: int,
    source: str,
    deck_tag: str,
    max_example_chars: int = 100,
    exclude_lemmas: Optional[Set[str]] = None,
) -> None:
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    with out_csv.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        for lemma, cnt in lemma_freq.most_common(top_n):
            if exclude_lemmas and lemma in exclude_lemmas:
                continue
            examples = lemma_examples.get(lemma, [])
            example_text = " ".join(examples[:2]).strip()
            if max_example_chars > 0 and len(example_text) > max_example_chars:
                example_text = example_text[:max_example_chars].rstrip() + "…"
            w.writerow([lemma, cnt, example_text, source, deck_tag])


def run_pipeline(
    *,
    book_path: Path,
    out_dir: Path,
    top_lemmas: int,
    top_entities: int,
    keep_stopwords: bool,
    include_entity_labels: Set[str],
    max_chars: Optional[int] = None,
    epub_structured_filter: bool = True,
    pdf_outline_filter: bool = True,
    min_body_ratio: float = 0.0,
    min_chapter_words: int = 0,
) -> None:
    raw = read_ebook(
        book_path,
        epub_structured_filter=epub_structured_filter,
        pdf_outline_filter=pdf_outline_filter,
    )
    raw = trim_front_back_matter(raw)
    raw = filter_chapters_by_density(
        raw,
        min_body_ratio=min_body_ratio,
        min_chapter_words=min_chapter_words,
    )
    if max_chars is not None:
        raw = raw[:max_chars]
    text = normalize_text(raw)

    out_dir = out_dir / normalize_output_name(book_path.stem)

    lemma_freq, entity_freq_by_label, lemma_examples = analyze_with_spacy(
        text,
        keep_stopwords=keep_stopwords,
        include_entity_labels=include_entity_labels,
    )

    export_top_lemmas(lemma_freq, out_dir / "lemmas.csv", top_n=top_lemmas)
    export_entities(entity_freq_by_label, out_dir / "entities", top_n=top_entities)
    export_anki_csv(
        lemma_freq,
        lemma_examples,
        out_dir / "lemmas_anki.csv",
        top_n=top_lemmas,
        source=book_path.stem,
        deck_tag=f"ebook::{normalize_output_name(book_path.stem)}",
    )

    top5000_path = project_root() / "data" / "word-freq-top5000.csv"
    top5000_words = load_word_list(top5000_path)
    if top5000_words:
        export_anki_csv(
            lemma_freq,
            lemma_examples,
            out_dir / "lemmas_anki_5000.csv",
            top_n=top_lemmas,
            source=book_path.stem,
            deck_tag=f"ebook::{normalize_output_name(book_path.stem)}",
            exclude_lemmas=top5000_words,
        )

    print("done.")
    print("lemmas:", (out_dir / "lemmas.csv").resolve())
    print("entities dir:", (out_dir / "entities").resolve())
    print("anki:", (out_dir / "lemmas_anki.csv").resolve())
    if top5000_words:
        print("anki (filtered top5000):", (out_dir / "lemmas_anki_5000.csv").resolve())
