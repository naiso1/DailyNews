"""Component hints shared by idea evidence extraction and final scope checks.

These hints do not replace the independent source and product-scope review.
Article admission uses its own automotive-context rules.
"""

COMPONENT_PATTERNS = {
    "interior": (
        r"\bdisplays?\b|\bscreens?\b|touchscreen|dashboard|console|(?<![a-z])door[ -](?:trim|panel)s?(?![a-z])|steering.wheel|switch|grab.handle|armrest|storage|weatherstrip|cargo|\bboot\b|soundbar|ambient.light|"
        r"インパネ|加飾|画面|ディスプレイ|モニター|サウンドバー|ドアトリム|コンソール|肘|アームレスト|収納|荷室|スイッチ"
    ),
    "exterior": (
        r"bumper|grille|door.handle|roof|tailgate|spoiler|fender|body.panel|rear.wing|bodywork|pillar|paint|coating|joining|bonding|radar|lidar|sensor|laser|in.mold|hot.stamp|recycl|"
        r"tail.?light|head.?light|tail.?lamp|head.?lamp|daytime.running|\bDRL\b|light.signature|bonnet|\bhood\b|mirror|canop(?:y|ies)|splitter|diffuser|wheel.arch|air.intake|cooling|aerodynamic|glazing|windshield|window|weather.?strip|"
        r"バンパー|グリル|ドアハンドル|ルーフ|テールゲート|バックドア|フェンダー|スポイラー|ウ[イィ]ング|ピラー|塗装|接合|ミリ波|センサー|レーザー|再生材|"
        r"ヘッドライト|テールライト|ヘッドランプ|テールランプ|ボンネット|フード|ミラー|キャノピー|スプリッター|ディフューザー|冷却|空力|ガラス|窓|ウェザーストリップ"
    ),
}

# Bilingual topics let a supplemental attempt choose an evidenced component
# that differs from the already written Japanese proposal.
COMPONENT_TOPICS = {
    "interior": {
        "ステアリングホイール周辺": r"steering.wheel|ステアリング|ハンドル",
        "ディスプレイ周辺": r"display|screen|画面|ディスプレイ|モニター|テレビ",
        "ドアトリム": r"\bdoor[ -](?:trim|panel)|ドアトリム",
        "操作スイッチ": r"\bswitch|physical.button|スイッチ|物理ボタン",
        "コンソール": r"console|コンソール",
        "荷室・収納": r"storage|cargo|\bboot\b|収納|荷室",
        "アームレスト": r"armrest|アームレスト|肘掛",
        "照明": r"ambient.light|アンビエント|照明",
    },
    "exterior": {
        "ボンネット": r"bonnet|\bhood\b|ボンネット|フード",
        "ディフューザー": r"diffuser|ディフューザー",
        "スポイラー・ウイング": r"spoiler|rear.wing|スポイラー|ウ[イィ]ング",
        "ランプ周辺": r"\blights?\b|head.?lamp|tail.?lamp|head.?light|tail.?light|ライト|ランプ",
        "グリル": r"grille|グリル",
        "バンパー": r"bumper|バンパー",
        "フェンダー": r"fender|wheel.arch|フェンダー|ホイールアーチ",
        "ドアハンドル": r"door.handle|ドアハンドル",
        "ルーフ": r"roof|ルーフ",
        "バックドア": r"tailgate|テールゲート|バックドア",
        "センサー周辺": r"lidar|radar|sensor|センサー|ミリ波",
        "窓・ガラス周辺": r"glazing|windshield|window|ガラス|窓",
    },
}
