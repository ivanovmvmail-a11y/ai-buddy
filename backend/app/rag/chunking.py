"""Ограниченные по длине фрагменты markdown с небольшим перекрытием."""


def chunk_markdown(text: str, max_chars: int = 1200, overlap: int = 150) -> list[str]:
    if max_chars <= 0 or not 0 <= overlap < max_chars:
        raise ValueError("Require max_chars > 0 and 0 <= overlap < max_chars")
    text = text.strip()
    chunks = []
    start = 0
    while start < len(text):
        end = min(start + max_chars, len(text))
        if end < len(text):
            # Предпочитаем границу абзаца/строки/слова во второй половине окна.
            for separator in ("\n\n", "\n", " "):
                boundary = text.rfind(separator, start + max_chars // 2, end)
                if boundary > start:
                    end = boundary
                    break
        content = text[start:end].strip()
        if content:
            chunks.append(content)
        if end == len(text):
            break
        start = max(start + 1, end - overlap)
    return chunks
