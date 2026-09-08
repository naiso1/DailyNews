"""Small checks for turning an equipment criticism into a positive claim."""

import re


SUMMARY_GROUNDING_RULES = (
    "原文にある事実・評価だけを使い、原文にない装備を補ってはいけません。\n"
    "筆者の要望・批評・否定・仮定を維持してください。『こだわりが欲しかった』は"
    "『こだわりが備わる』ではありません。『欲しい』『期待したい』を採用済みの装備としないこと。\n"
    "競合車の装備を対象車の装備へ置き換えず、どの車・グレードへの記述かを維持してください。\n"
    "筆者の感想は『筆者は〜と評価／指摘』として事実と区別し、根拠が曖昧な装備は省いてください。\n"
)
CRITICISM = re.compile(r"欲しかった|欲しい|ほしかった|ほしい|物足り|もの足り|惜しい|改善の余地|改善を求め|期待したい")
QUALIFIED = re.compile(r"指摘|批評|求め|評価|課題|不足|改善|要望|不満|欲し|ほし|期待|望ま|物足り|もの足り|惜しい")
POSITIVE = re.compile(r"備わ|備え|採用|搭載|装備|充実|こだわり|高級|上質|優れ")
EQUIPMENT = re.compile(r"(?:センター)?テーブル|スイッチ(?:類)?|室内灯|アームレスト|ドアトリム|ディスプレイ|センターコンソール")


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
