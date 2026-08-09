import math
import re
from collections import Counter
from dataclasses import dataclass
from typing import Any


TOKEN_RE = re.compile(r"[a-z0-9]+")
STOP_WORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "can", "do", "for",
    "from", "how", "i", "in", "is", "it", "of", "on", "or", "our", "the",
    "their", "this", "to", "we", "what", "with", "you", "your",
}

SOURCE_LABELS = {
    "company": "Sentientia company profile",
    "learning_services": "Sentientia learning-services materials",
    "products.bluetree_lms": "BlueTree LMS product materials",
    "products.nudge_ai": "Nudge AI product materials",
    "products.satyaa_ai": "Satyaa.ai product materials",
    "products.rxready_ai": "RxReady AI pitch deck",
    "publisher_and_content_services": "Sentientia content-services materials",
    "recommended_discovery_questions": "Sentientia discovery framework",
    "suggested_faqs": "Sentientia approved FAQs",
}


def tokenize(text: str) -> list[str]:
    tokens = [token for token in TOKEN_RE.findall(text.lower()) if token not in STOP_WORDS]
    expanded = list(tokens)
    synonyms = {
        "lms": ["learning", "platform"],
        "bluetree": ["lms", "platform"],
        "nudge": ["whatsapp", "coaching", "reinforcement"],
        "localisation": ["localization", "language", "translation"],
        "localization": ["language", "translation", "multilingual"],
        "voice": ["audio", "speaking"],
        "courses": ["content", "learning"],
    }
    for token in tokens:
        expanded.extend(synonyms.get(token, []))
    return expanded


def source_label(path: str) -> str:
    for prefix, label in SOURCE_LABELS.items():
        if path == prefix or path.startswith(f"{prefix}."):
            return label
    return "Sentientia verified knowledge base"


@dataclass(frozen=True)
class KnowledgeChunk:
    path: str
    label: str
    text: str
    tokens: tuple[str, ...]


def _text_value(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list) and all(isinstance(item, str) for item in value):
        return "; ".join(value)
    return ""


def build_chunks(data: dict[str, Any]) -> list[KnowledgeChunk]:
    chunks: list[KnowledgeChunk] = []

    def visit(value: Any, path: str) -> None:
        if isinstance(value, dict) and "question" in value and "answer" in value:
            chunk_text = f"FAQ question: {value['question']} FAQ answer: {value['answer']}"
            chunks.append(
                KnowledgeChunk(path, source_label(path), chunk_text, tuple(tokenize(chunk_text)))
            )
            return
        text = _text_value(value)
        if text:
            readable_path = path.replace("_", " ").replace(".", " > ")
            chunk_text = f"{readable_path}: {text}"
            chunks.append(
                KnowledgeChunk(path, source_label(path), chunk_text, tuple(tokenize(chunk_text)))
            )
            return
        if isinstance(value, dict):
            for key, child in value.items():
                child_path = f"{path}.{key}" if path else key
                visit(child, child_path)
        elif isinstance(value, list):
            for index, child in enumerate(value):
                visit(child, f"{path}.{index}")

    for root_key, root_value in data.items():
        if root_key not in {"knowledge_base", "source_register"}:
            visit(root_value, root_key)
    return chunks


class LightweightRetriever:
    def __init__(self, data: dict[str, Any]):
        self.chunks = build_chunks(data)
        self.average_length = (
            sum(len(chunk.tokens) for chunk in self.chunks) / max(len(self.chunks), 1)
        )
        document_frequency: Counter[str] = Counter()
        for chunk in self.chunks:
            document_frequency.update(set(chunk.tokens))
        total = len(self.chunks)
        self.idf = {
            token: math.log(1 + (total - count + 0.5) / (count + 0.5))
            for token, count in document_frequency.items()
        }

    def search(self, query: str, limit: int = 7) -> list[KnowledgeChunk]:
        query_tokens = tokenize(query)
        if not query_tokens:
            return self._fallback(limit)
        query_counts = Counter(query_tokens)
        scored: list[tuple[float, KnowledgeChunk]] = []
        k1, b = 1.5, 0.75
        for chunk in self.chunks:
            frequencies = Counter(chunk.tokens)
            length_norm = 1 - b + b * len(chunk.tokens) / max(self.average_length, 1)
            score = 0.0
            for token, query_weight in query_counts.items():
                frequency = frequencies[token]
                if not frequency:
                    continue
                score += (
                    self.idf.get(token, 0.0)
                    * (frequency * (k1 + 1))
                    / (frequency + k1 * length_norm)
                    * min(query_weight, 2)
                )
            lowered = query.lower()
            if "blue" in lowered and chunk.path.startswith("products.bluetree_lms"):
                score += 2.5
            if "nudge" in lowered and chunk.path.startswith("products.nudge_ai"):
                score += 2.5
            if "satyaa" in lowered and chunk.path.startswith("products.satyaa_ai"):
                score += 2.5
            if "rxready" in lowered and chunk.path.startswith("products.rxready_ai"):
                score += 2.5
            if any(term in lowered for term in ("what does sentientia", "about sentientia", "company")):
                if chunk.path in {
                    "company.positioning",
                    "company.public_website_highlights",
                    "company.connected_model",
                    "company.business_outcomes",
                }:
                    score += 4.0
            if any(term in lowered for term in ("language", "localize", "localise", "translation", "arabic")):
                if chunk.path.startswith("learning_services.localization"):
                    score += 4.0
            if score > 0:
                scored.append((score, chunk))
        scored.sort(key=lambda item: item[0], reverse=True)
        results = [chunk for _, chunk in scored[:limit]]
        return results or self._fallback(limit)

    def _fallback(self, limit: int) -> list[KnowledgeChunk]:
        preferred = (
            "company.positioning",
            "company.public_website_highlights",
            "company.connected_model",
            "recommended_discovery_questions",
        )
        results = [
            chunk for chunk in self.chunks if any(chunk.path.startswith(path) for path in preferred)
        ]
        return results[:limit]
