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
            for separator in ("\n\n", "\n", " ", "\t"):
                boundary = text.rfind(separator, start + max_chars // 2, end)
                if boundary > start:
                    end = boundary
                    break
        content = text[start:end].strip()
        if content:
            chunks.append(content)
        if end == len(text):
            break
        next_start = max(start + 1, end - overlap)
        if not text[next_start - 1].isspace() and not text[next_start].isspace():
            left = next_start
            while left > start and not text[left - 1].isspace():
                left -= 1
            right = next_start
            while right < end and not text[right].isspace():
                right += 1
            boundaries = [left] if left > start else []
            if text[right].isspace():
                boundaries.append(right)
            if boundaries:
                next_start = min(boundaries, key=lambda position: abs(position - next_start))
            # Слово длиннее окна всё же приходится делить, иначе нет продвижения.
        start = next_start
    return chunks
