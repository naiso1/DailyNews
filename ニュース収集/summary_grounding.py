"""Checks for reversed equipment criticism and lost interior details."""

import re


BRAND_ALIASES = {
    "mazda": ("マツダ",), "toyota": ("トヨタ",), "honda": ("ホンダ",),
    "nissan": ("日産",), "lexus": ("レクサス",), "subaru": ("スバル",),
    "suzuki": ("スズキ",), "mitsubishi": ("三菱",), "audi": ("アウディ",),
    "volkswagen": ("フォルクスワーゲン",), "renault": ("ルノー",),
    "volvo": ("ボルボ",), "ford": ("フォード",), "tesla": ("テスラ",),
    "hyundai": ("ヒョンデ",), "kia": ("起亜", "キア"),
    "mercedes-benz": ("メルセデス・ベンツ", "メルセデスベンツ"),
}


def source_identifiers_match(summary, identifiers):
    """Accept verified brand spellings, without translating arbitrary identifiers."""
    folded = str(summary or "").casefold()
    for identifier in identifiers:
        key = identifier.casefold()
        if re.search(r"(?<![a-z0-9])" + re.escape(key) + r"(?![a-z0-9])", folded):
            return True
        if any(alias in folded for alias in BRAND_ALIASES.get(key, ())):
            return True
    return False


SUMMARY_GROUNDING_RULES = (
    "原文にある事実・評価だけを使い、原文にない装備を補ってはいけません。\n"
    "筆者の要望・批評・否定・仮定を維持してください。『こだわりが欲しかった』は"
    "『こだわりが備わる』ではありません。『欲しい』『期待したい』を採用済みの装備としないこと。\n"
    "競合車の装備を対象車の装備へ置き換えず、どの車・グレードへの記述かを維持してください。\n"
    "筆者の感想は『筆者は〜と評価／指摘』として事実と区別し、根拠が曖昧な装備は省いてください。\n"
    "内装の具体情報が複数ある記事の要約では、そのうち2〜3点を残してください。"
    "発売日と価格だけの要約にせず、原文に内装情報がない場合は補ってはいけません。\n"
)
CRITICISM = re.compile(r"欲しかった|欲しい|ほしかった|ほしい|物足り|もの足り|惜しい|改善の余地|改善を求め|期待したい")
QUALIFIED = re.compile(r"指摘|批評|求め|評価|課題|不足|改善|要望|不満|欲し|ほし|期待|望ま|物足り|もの足り|惜しい")
POSITIVE = re.compile(r"備わ|備え|採用|搭載|装備|充実|こだわり|高級|上質|優れ")
EQUIPMENT = re.compile(r"(?:センター)?テーブル|スイッチ(?:類)?|室内灯|アームレスト|ドアトリム|ディスプレイ|センターコンソール")

INTERIOR_TOPICS = tuple(re.compile(pattern, re.I) for pattern in (
    r"センターコンソール|中央コンソール|可動式コンソール|センターアイランド|\b(?:central|cent(?:er|re))[ -](?:console|island)\b",
    r"ディスプレイ|画面|スクリーン|インフォテインメント|\b(?:display|screen|infotainment)\b",
    r"シート|座席|[23]列目|[23]列シート|\b(?:seats?|seating|zero.gravity)\b",
    r"冷蔵庫|冷温庫|収納|荷室|\b(?:refrigerator|fridge|storage)\b",
    r"ドアトリム|加飾|表皮|内張|\b(?:door[ -]trim|upholstery)\b",
    r"室内灯|間接照明|アンビエント|\bambient[ -]light(?:ing|s)?\b",
))


def summary_omits_interior_details(summary, source):
    """Only require detail when the source itself covers multiple interior topics."""
    source_topics = [pattern for pattern in INTERIOR_TOPICS if pattern.search(str(source or ""))]
    if len(source_topics) < 2:
        return False
    return sum(bool(pattern.search(str(summary or ""))) for pattern in source_topics) < 2


def reverses_equipment_criticism(summary, source):
    source_sentences = re.split(r"[。！？!?\n]+", str(source or ""))
    criticized = {term for sentence in source_sentences if CRITICISM.search(sentence)
                  for term in EQUIPMENT.findall(sentence)}
    if not criticized:
        return False
    for sentence in re.split(r"[。！？!?\n]+", str(summary or "")):
        if any(term in sentence for term in criticized) and POSITIVE.search(sentence) and not QUALIFIED.search(sentence):
            return True
    return False
