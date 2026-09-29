"""Shared exterior-development vocabulary and semantic review contract.

Terms admit candidates, never establish relevance or adoption by themselves.
Keep the same contract in initial classification, scoring, summaries and ideas.
"""
import re

POLICY_VERSION = "exterior-development-20260930"
THEMES = {
    "body": ("バックドア", "フェンダー", "ドア", "ルーフ", "リアスポイラー", "ピラー", "フード", "フロントエンドモジュール", "車両骨格",
             "tailgate", "liftgate", "fender", "door", "roof", "rear spoiler", "pillar", "hood", "bonnet", "front end module", "body in white", "body-in-white", "尾门", "翼子板", "车门", "车顶", "扰流板", "立柱", "发动机罩", "前端模块", "白车身"),
    "process": ("3Dプリンター", "3Dプリンタ", "型内塗装", "ホットスタンプ", "インクジェット", "フィルム", "印刷", "メッキ", "めっき", "レーザー", "塗装",
                "3D printing", "additive manufacturing", "in-mold coating", "in-mould coating", "hot stamping", "press hardening", "foil transfer", "inkjet", "film", "printing", "plating", "laser", "coating", "paint", "增材制造", "3D打印", "模内涂装", "热冲压", "烫印", "喷墨", "薄膜", "印刷", "电镀", "激光", "涂装"),
    "materials": ("CN/CE", "カーボンニュートラル", "サーキュラーエコノミー", "低コスト化", "軽量", "樹脂化", "鉄との接合", "異材接合", "再生材", "分解", "再利用",
                  "carbon neutral", "circular economy", "cost reduction", "lightweight", "metal replacement", "polymer metal joining", "steel polymer", "hybrid joining", "recycled", "disassembly", "碳中和", "循环经济", "降本", "轻量化", "塑料替代", "异种材料连接", "钢塑", "回收"),
    "performance": ("冷却", "NV", "騒音", "振動", "シームレス", "走行安定", "Cd値", "空気抵抗係数",
                    "cooling", "NVH", "noise vibration", "seamless", "driving stability", "drag coefficient", "aerodynamic", "lift coefficient", "冷却", "噪声", "振动", "无缝", "行驶稳定", "风阻系数", "空气动力"),
    "sensing": ("ミリ波", "Lidar", "カメラ", "ソナー", "自動運転", "ADAS", "millimeter wave", "millimetre wave", "camera", "ultrasonic", "sonar", "autonomous driving", "毫米波", "激光雷达", "摄像头", "超声波", "自动驾驶"),
    "safety": ("アブソーバー", "歩行者保護", "軽衝突", "法規", "アセス", "absorber", "pedestrian protection", "pedestrian safety", "low speed impact", "low-speed impact", "regulation", "NCAP", "crash assessment", "吸能", "行人保护", "低速碰撞", "法规", "安全评价"),
}


def _pattern(terms):
    # English abbreviations/words must not match inside unrelated words.
    return re.compile("|".join((r"\b" + re.escape(term).replace(r"\ ", r"[\s-]+") + r"s?\b") if term.isascii()
                               else re.escape(term) for term in terms), re.I)


PATTERNS = {key: _pattern(terms) for key, terms in THEMES.items()}
BODY = PATTERNS["body"]
TRANSFER = _pattern(tuple(term for group in ("process", "materials") for term in THEMES[group]
                         if term not in {"CN/CE", "分解", "再利用", "disassembly"}))
PROPERTY = re.compile(r"樹脂|鋼|接合|強度|耐候|耐食|成形|曲面|表面|試験|複合材|polymer|steel|joining|strength|weather|corrosion|mold|mould|curved|surface|test|composite|树脂|钢|连接|强度|耐候|成型|曲面|表面|试验", re.I)

SCOPE_TEXT = """外装開発室の収集範囲（ニュース・論文共通）:
既存のグリル、バンパー、加飾、エンブレム、ランプ、レドーム、シールを維持する。
追加重点: バックドア/tailgate/liftgate、フェンダー、ドア、ルーフ、リアスポイラー、ピラー、フード/bonnet、フロントエンドモジュール、車両骨格。
製法・表面: 3Dプリンター/積層造形、型内塗装、ホットスタンプ（加飾箔転写と鋼板熱間成形の両方）、インクジェット、フィルム、印刷、メッキ、レーザー加工・接合、塗装。
材料・環境: CN=カーボンニュートラル、CE=サーキュラーエコノミー、低コスト化、軽量、樹脂化、鉄との接合/異材接合。
性能: 冷却、NV=騒音・振動（NVHも含む）、シームレス、走行安定、Cd値/空気抵抗係数。
センシング: ミリ波、LiDAR、カメラ、ソナー、自動運転、ADASの外装への配置・保護・透過・汚れ・雨雪・洗浄・加熱・意匠との両立。
安全: アブソーバー、歩行者保護、軽衝突、法規、アセス=NCAP等の安全性能評価。規制案/施行/試験結果と対象地域・時期を区別する。
A direct: 外装・車体の形状、構造、材料、製法、性能、評価、設計要求のいずれか1つに具体情報があれば対象。複数テーマや製法の説明を必須にしない。シールによる車内騒音低減は内装記事扱いにしない。
B transfer: 自動車用途が原文にない周辺技術でも、原文の具体的な材料・方法・特性から外装部品の検討用途を説明できるなら対象。厳密な数値や特定書式は必須にしない。原文の技術をsource_evidenceに、外装応用の仮説をapplicationに分けて短く記録する。仮説を採用実績にしない。
trend: 従来の市場・規制・材料・デザイン・競合情報も残すが、上記の技術テーマを優先する。
C exclude: 内装だけ・二輪車が主題の記事、ITのバックドア、建築ドア、家庭用プリンターの商品紹介、スマホカメラ、一般企業のCN宣言、外装との接点のない自動運転AI。二輪主体は転用を想像できても初期運用では対象外。
混在記事は外装の具体情報があれば対象。例えばAI搭載ニュースでもバンパー・テールゲートの設計変更が本文にあれば対象。『内装』『二輪』の単語が出ただけで除外しない。単語の一致数・写真だけで採用せず原文の主題と事実で判断する。
"""


def theme_hits(text):
    return [key for key, pattern in PATTERNS.items() if pattern.search(str(text or ""))]


def transfer_candidate(text):
    return bool(TRANSFER.search(str(text or "")) and PROPERTY.search(str(text or "")))


def review_fields(data, category):
    """New model decisions fail closed when transfer reasoning is missing."""
    lane = str(data.get("development_lane", "")).strip().lower()
    evidence = str(data.get("source_evidence", "") or "").strip()[:300]
    application = str(data.get("application", "") or "").strip()[:300]
    if lane not in {"direct", "transfer", "trend", "exclude"}:
        lane = "trend" if category == "trend" else "direct" if category == "product" else "exclude"
    if lane == "transfer" and (not evidence or not application):
        lane = "exclude"
    return {"development_lane": lane, "source_evidence": evidence, "application": application,
            "policy_version": POLICY_VERSION}
