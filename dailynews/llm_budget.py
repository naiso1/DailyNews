"""Conservative request budgeting without a tokenizer service or model calls."""

from copy import deepcopy


OUTPUT_TOKEN_LIMIT = 1024
CHAT_TOKEN_RESERVE = 512
IMAGE_TOKEN_RESERVE = 2048
OMISSION = "\n[Source excerpt shortened; middle omitted. Do not infer missing facts.]\n"
SOURCE_MARKERS = (
    "\n本文:\n", "\nArticle: ", "\nArticle/snippet: ",
    "\nSource content: ", "\nContent: ", "\n記事内容: ",
    "\n既存内容: ", "\nSource: ",
)


def _bytes(text):
    return len(text.encode("utf-8"))


def _shorten_user_text(text, budget):
    if _bytes(text) <= budget:
        return text
    # Keep the complete instruction/title prefix for the collector's source
    # prompts. Preserve the end as well: qualifications and JSON requirements
    # often follow the source body. Never join the two excerpts without a marker.
    ends = [text.index(marker) + len(marker) for marker in SOURCE_MARKERS if marker in text]
    split = min(ends) if ends else 0
    prefix, source = text[:split], text[split:]
    available = budget - _bytes(prefix) - _bytes(OMISSION)
    if available < 256:
        raise ValueError("Exterior LLM instructions leave insufficient source budget")
    encoded = source.encode("utf-8")
    head_budget = available * 2 // 3
    tail_budget = available - head_budget
    head = encoded[:head_budget].decode("utf-8", errors="ignore")
    tail = encoded[-tail_budget:].decode("utf-8", errors="ignore")
    return prefix + head + OMISSION + tail


def budget_exterior_payload(payload, context_length=8192):
    """Copy and bound text plus response/image reserves for exterior collection.

    UTF-8 byte length is intentionally more conservative than a characters/4
    estimate for Chinese/Japanese. It is not an exact multimodal token count.
    The caller must pass the actual loaded context size. No source/cache data
    are changed, and oversized fixed instructions fail before HTTP is sent.
    """
    context = int(context_length)
    output_tokens = min(OUTPUT_TOKEN_LIMIT, int(payload.get("max_tokens", OUTPUT_TOKEN_LIMIT)))
    if context <= 0 or output_tokens <= 0:
        raise ValueError("Invalid exterior LLM context/output budget")
    result = deepcopy(payload)
    texts, editable = [], []
    image_count = 0
    for message in result.get("messages", []):
        content = message.get("content")
        if isinstance(content, str):
            parts = [(message, "content")]
        elif isinstance(content, list):
            parts = [(part, "text") for part in content if part.get("type") == "text"]
            image_count += sum(part.get("type") == "image_url" for part in content)
        else:
            parts = []
        texts.extend(parts)
        if message.get("role") == "user":
            editable.extend(parts)
    budget = context - output_tokens - CHAT_TOKEN_RESERVE - image_count * IMAGE_TOKEN_RESERVE
    total = sum(_bytes(container[key]) for container, key in texts)
    for container, key in sorted(editable, key=lambda item: _bytes(item[0][item[1]]), reverse=True):
        if total <= budget:
            break
        before = _bytes(container[key])
        container[key] = _shorten_user_text(container[key], before - (total - budget))
        total += _bytes(container[key]) - before
    if total > budget:
        raise ValueError("Exterior LLM fixed messages exceed available context")
    result["max_tokens"] = output_tokens
    return result
