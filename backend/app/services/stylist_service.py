"""A chat with the AI about the user's own wardrobe. The model sees the wardrobe as a numbered
list and cites pieces as [#n]; those become [[item:<id>]] in the reply, so the page can show
the photo and the model cannot point at something the user does not own."""

import re
from dataclasses import dataclass

from app.models.item import ClothingItem
from app.services.ai_service import AIService

MAX_ITEMS = 150
MAX_TURNS = 20

STYLIST_PROMPT = """You are a friendly personal stylist. You only know the clothes in the user's
wardrobe listed below, plus general fashion knowledge.
- Answer in the same language the user writes in.
- Keep answers short and practical: a few sentences or a short list.
- When you suggest one of the user's own pieces, cite it as [#number] using the list's numbers,
  for example "the navy jacket [#12] with white sneakers [#4]".
- Never cite a number that is not in the list. If the wardrobe lacks something, say what kind
  of piece would help instead of inventing one.
{context}
Wardrobe:
{listing}"""

CITATION = re.compile(r"\[#(\d+)\]")
ITEM_TOKEN = re.compile(r"\[\[item:([0-9a-fA-F-]{36})\]\]")


@dataclass
class StylistReply:
    text: str
    items: list[ClothingItem]


def wardrobe_listing(items: list[ClothingItem]) -> str:
    lines = []
    for number, item in enumerate(items, start=1):
        # The subtype tells jeans from chinos, which the type alone ("pants") does not.
        subtype = item.subtype if item.subtype and item.subtype != item.type else None
        parts = [item.name, item.primary_color, item.pattern, item.material, subtype, item.type]
        text = " ".join(p for p in parts if p)
        extras = []
        if item.season:
            extras.append("/".join(item.season))
        if item.formality:
            extras.append(item.formality)
        if extras:
            text += f" ({', '.join(extras)})"
        lines.append(f"{number}. {text}")
    return "\n".join(lines)


def resolve_citations(text: str, items: list[ClothingItem]) -> StylistReply:
    cited: list[ClothingItem] = []

    def replace(match: re.Match) -> str:
        index = int(match.group(1)) - 1
        if 0 <= index < len(items):
            item = items[index]
            if item not in cited:
                cited.append(item)
            return f"[[item:{item.id}]]"
        return ""

    return StylistReply(CITATION.sub(replace, text).strip(), cited)


def renumber_history(content: str, wardrobe: list[ClothingItem]) -> str:
    """An earlier reply comes back with [[item:<id>]] tokens; the model only knows the list's
    numbers, so each token turns back into [#n] for this request's listing. A piece that is no
    longer in the listing becomes a plain mention the model cannot cite."""
    numbers = {str(item.id): n for n, item in enumerate(wardrobe, start=1)}

    def replace(match: re.Match) -> str:
        number = numbers.get(match.group(1).lower())
        return f"[#{number}]" if number else "(a piece no longer in the wardrobe)"

    return ITEM_TOKEN.sub(replace, content)


async def ask_stylist(
    ai: AIService,
    items: list[ClothingItem],
    conversation: list[dict[str, str]],
    context: str = "",
) -> StylistReply:
    wardrobe = items[:MAX_ITEMS]
    system = STYLIST_PROMPT.format(
        context=f"\nContext: {context}\n" if context else "",
        listing=wardrobe_listing(wardrobe) or "(empty)",
    )
    messages = [{"role": "system", "content": system}]
    messages += [
        {
            "role": turn["role"],
            "content": renumber_history(turn["content"], wardrobe)
            if turn["role"] == "assistant"
            else turn["content"],
        }
        for turn in conversation[-MAX_TURNS:]
    ]
    content, error, _ = await ai._call_with_fallback(messages, "stylist", use_vision_model=False)
    if content is None:
        raise error or RuntimeError("The AI did not answer")
    return resolve_citations(content, wardrobe)
