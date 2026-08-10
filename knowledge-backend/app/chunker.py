"""
Chunking Engine
- Target: ~1000 tokens / chunk, ~150 token overlap
- Token estimate: ~4 characters ≈ 1 token (MVP)
"""

from __future__ import annotations
from typing import List, Dict
import re

TARGET_CHUNK_TOKENS = 1000
OVERLAP_TOKENS = 150
CHARS_PER_TOKEN = 4


def estimate_tokens(text: str) -> int:
    if not text:
        return 0
    return max(1, len(text) // CHARS_PER_TOKEN)


def _split_into_sentences(text: str) -> List[str]:
    parts = re.split(r"(?<=[.!?])\s+", text.strip())
    return [p.strip() for p in parts if p.strip()]


def chunk_text(
    text: str,
    chunk_size_tokens: int = TARGET_CHUNK_TOKENS,
    overlap_tokens: int = OVERLAP_TOKENS,
) -> List[Dict]:
    if not text or not text.strip():
        return []

    text = text.strip()
    total_tokens = estimate_tokens(text)

    if total_tokens <= chunk_size_tokens:
        return [{
            "chunk_index": 0,
            "text": text,
            "token_count": total_tokens,
        }]

    sentences = _split_into_sentences(text)
    if not sentences:
        return _hard_chunk(text, chunk_size_tokens, overlap_tokens)

    chunks = []
    current_sentences = []
    current_tokens = 0
    chunk_index = 0
    overlap_chars = overlap_tokens * CHARS_PER_TOKEN

    i = 0
    while i < len(sentences):
        sentence = sentences[i]
        sentence_tokens = estimate_tokens(sentence)

        if sentence_tokens > chunk_size_tokens:
            if current_sentences:
                chunk_text_str = " ".join(current_sentences).strip()
                chunks.append({
                    "chunk_index": chunk_index,
                    "text": chunk_text_str,
                    "token_count": estimate_tokens(chunk_text_str),
                })
                chunk_index += 1
                current_sentences = []
                current_tokens = 0

            hard_parts = _hard_chunk(sentence, chunk_size_tokens, overlap_tokens)
            for part in hard_parts:
                part["chunk_index"] = chunk_index
                chunks.append(part)
                chunk_index += 1
            i += 1
            continue

        if current_tokens + sentence_tokens <= chunk_size_tokens:
            current_sentences.append(sentence)
            current_tokens += sentence_tokens
            i += 1
        else:
            if current_sentences:
                chunk_text_str = " ".join(current_sentences).strip()
                chunks.append({
                    "chunk_index": chunk_index,
                    "text": chunk_text_str,
                    "token_count": estimate_tokens(chunk_text_str),
                })
                chunk_index += 1

                overlap_text = chunk_text_str[-overlap_chars:] if overlap_chars > 0 else ""
                if overlap_text.strip():
                    current_sentences = [overlap_text.strip(), sentence]
                    current_tokens = estimate_tokens(" ".join(current_sentences))
                else:
                    current_sentences = [sentence]
                    current_tokens = sentence_tokens
                i += 1
            else:
                current_sentences = [sentence]
                current_tokens = sentence_tokens
                i += 1

    if current_sentences:
        chunk_text_str = " ".join(current_sentences).strip()
        if chunk_text_str:
            chunks.append({
                "chunk_index": chunk_index,
                "text": chunk_text_str,
                "token_count": estimate_tokens(chunk_text_str),
            })

    return chunks


def _hard_chunk(
    text: str,
    chunk_size_tokens: int,
    overlap_tokens: int,
) -> List[Dict]:
    chunk_chars = chunk_size_tokens * CHARS_PER_TOKEN
    overlap_chars = overlap_tokens * CHARS_PER_TOKEN
    step = max(1, chunk_chars - overlap_chars)

    chunks = []
    start = 0
    index = 0
    while start < len(text):
        end = min(len(text), start + chunk_chars)
        piece = text[start:end].strip()
        if piece:
            chunks.append({
                "chunk_index": index,
                "text": piece,
                "token_count": estimate_tokens(piece),
            })
            index += 1
        if end >= len(text):
            break
        start += step
    return chunks


def build_chunk_id(document_id: str, chunk_index: int) -> str:
    return f"{document_id}_chunk_{chunk_index:04d}"