"""Exterior genre vocabulary shared by the publisher and generated browser asset.

These tags describe the published title/summary, not collection eligibility.
Run ``python -m dailynews.exterior_tags`` after changing this vocabulary.
"""
import json
from pathlib import Path
import re
import unicodedata


def english(pattern):
    # ASCII boundaries also work next to Japanese text in Python and JavaScript.
    return r"(?<![A-Za-z0-9])(?:" + pattern + r")(?![A-Za-z0-9])"


def rule(tag, japanese, latin="", aliases=()):
    return dict(tag=tag, pattern=japanese + ("|" + english(latin) if latin else ""), aliases=list(aliases))


# Keep all 39 requested labels individually selectable; retain useful old genres.
RULES = [
    rule("冷却", r"冷却|放熱|熱マネジメント|热管理", r"cooling|thermal management|heat dissipation"),
    rule("3Dプリンター", r"3Dプリンタ[ー]?|3D印刷|積層造形|付加製造|增材制造|3D打印", r"3d[ -]print(?:ing|ed|ers?)|additive manufacturing"),
    rule("CN/CE", r"カーボンニュートラル|サーキュラーエコノミー|脱炭素|資源循環|循環経済|再生材|リサイクル|再利用|碳中和|循环经济|回收", r"CN/CE|carbon[ -]neutral(?:ity)?|circular economy|recycl\w*|reuse|decarbon\w*"),
    rule("NV", r"騒音|振動|静粛|遮音|吸音|噪声|振动", r"NVH?|noise|vibration|acoustic\w*"),
    rule("低コスト化", r"低コスト|コスト(?:低減|削減)|原価低減|降本", r"cost[ -](?:reduction|saving|savings|effective)|low[ -]cost|reduc\w* costs?"),
    rule("バックドア", r"バックドア|テールゲート|リフトゲート|尾门", r"tailgates?|liftgates?|rear hatch|back doors?"),
    rule("フェンダー", r"フェンダー|翼子板", r"fenders?"),
    rule("ドア", r"ドア|车门", r"doors?"),
    rule("ルーフ", r"ルーフ|車頂|车顶", r"roofs?"),
    rule("リアスポイラー", r"リアスポイラー|リヤスポイラー|後部スポイラー|尾翼|扰流板", r"rear spoilers?|rear wings?"),
    rule("ピラー", r"ピラー|立柱", r"pillars?"),
    rule("フード", r"フード|ボンネット|发动机罩", r"hoods?|bonnets?"),
    rule("型内塗装", r"型内塗装|金型内塗装|インモールド(?:塗装|コーティング)|模内涂装", r"in[ -]mou?ld coat(?:ing)?|IMC"),
    rule("ホットスタンプ", r"ホットスタンプ|熱間プレス|加飾箔転写|热冲压|烫印", r"hot[ -]stamp(?:ing|ed)?|press harden(?:ing|ed)|foil transfer"),
    rule("インクジェット", r"インクジェット|喷墨", r"ink[ -]?jet"),
    rule("フィルム", r"フィルム|薄膜", r"films?|foils?"),
    rule("印刷", r"印刷|プリント", r"print(?:ing|ed)?"),
    rule("メッキ", r"メッキ|めっき|電鍍|电镀|クロム", r"plating|electroplat\w*|chrom(?:e|ium)"),
    rule("レーザー", r"レーザー?|激光(?!雷达)", r"lasers?"),
    rule("ミリ波", r"ミリ波|毫米波", r"milli(?:meter|metre)[ -]waves?|mmwave"),
    rule("Lidar", r"ライダー|ライダ[ー]?センサ|光検出測距|激光雷达", r"LiDAR", aliases=("LiDAR",)),
    rule("カメラ", r"カメラ|摄像头", r"cameras?"),
    rule("ソナー", r"ソナー|超音波|超声波", r"sonar|ultrasonic\w*"),
    rule("フロントエンドモジュール", r"フロントエンドモジュール|フロントモジュール|前端模块", r"front[ -]end modules?"),
    rule("軽量", r"軽量|轻量", r"light[ -]?weight|weight reduction", aliases=("軽量化",)),
    rule("アブソーバー", r"アブソーバ[ー]?|衝撃吸収|吸能", r"absorbers?|energy absorb\w*"),
    rule("シームレス", r"シームレス|継ぎ目(?:の)?ない|无缝", r"seamless"),
    rule("樹脂化", r"樹脂化|樹脂代替|樹脂置換|塑料替代", r"metal replacement|plastic replacement|replac\w* metal with (?:plastic|polymer)"),
    rule("鉄との接合", r"鉄との接合|異材接合|(?:鉄|鋼)[^。.!?\n]{0,24}(?:樹脂|接合)|樹脂[^。.!?\n]{0,24}(?:鉄|鋼)|钢塑|异种材料连接", r"(?:polymer|plastic)[ -]metal join\w*|steel[ -]polymer|hybrid join\w*|dissimilar material join\w*"),
    rule("塗装", r"塗装|塗料|コーティング|涂装|涂层", r"paint(?:s|ed|ing)?|coat(?:ing|ings|ed)"),
    rule("歩行者保護", r"歩行者保護|歩行者安全|行人保护", r"pedestrian (?:protection|safety)"),
    rule("軽衝突", r"軽衝突|低速衝突|低速碰撞", r"low[ -]speed (?:impact|collision|crash)"),
    rule("法規", r"法規|規制|安全基準|法规", r"regulations?|legislation|regulatory|FMVSS|UNECE"),
    rule("アセス", r"アセス|安全性能評価|安全评价", r"NCAP|crash assessment"),
    rule("自動運転", r"自動運転|自动驾驶", r"autonomous driving|self[ -]driving|automated driving"),
    rule("車両骨格", r"車両骨格|車体骨格|ホワイトボディ|白车身", r"body[ -]in[ -]white|BIW|vehicle structure|body structure"),
    rule("ADAS", r"先進運転支援|先進運転者支援|驾驶辅助", r"ADAS|advanced driver assistance"),
    rule("走行安定", r"走行安定|操縦安定|行驶稳定", r"driving stability|vehicle stability|handling stability"),
    rule("Cd値", r"Cd値|空気抵抗係数|抗力係数|风阻系数", r"Cd(?=\s*[=:]?\s*0?\.\d)|drag coefficient"),
    rule("グリル", r"グリル|格栅|フロントパネル", r"grilles?"),
    rule("バンパー", r"バンパー|保险杠", r"bumpers?|fascia"),
    rule("加飾", r"加飾|塗装|メッキ|めっき|クロム|エンブレム", r"decorat\w*|emblems?|chrome|plating", aliases=("外装加飾",)),
    rule("照明・発光", r"照明|発光|ライト|ランプ|前大灯|尾灯", r"lighting|illumin\w*|LED|headlights?|headlamps?|taillights?|taillamps?"),
    rule("センサー対応", r"センサー|レーダー|レドーム|ライダー|ミリ波|カメラ|ソナー|透過|透波", r"sensors?|radars?|radomes?|LiDAR|ADAS|cameras?|sonar|ultrasonic\w*", aliases=("センサー透過",)),
    rule("空力", r"空力|エアロ|空気抵抗|シャッター|スポイラー|ディフューザ|空气动力", r"aerodynamic\w*|shutters?|spoilers?|drag coefficient"),
    rule("新素材", r"樹脂|材料|成形|新素材|素材|树脂", r"polymers?|resins?|materials?|mou?lding", aliases=("材料",)),
    rule("サステナビリティ", r"リサイクル|再生材|バイオ|脱炭素|資源循環|循環経済", r"recycl\w*|sustainab\w*|bio[ -]based|circular economy"),
    rule("サプライチェーン", r"工場|生産拠点|サプライチェーン", r"factor(?:y|ies)|plants?|supply chain"),
    rule("エンブレム", r"エンブレム|车标", r"emblems?"),
    rule("シール", r"ウェザーストリップ|ウエザーストリップ|シール材|密封条", r"weather[ -]?strips?|weatherstripping|body seal(?:ing|s)?"),
]
PATTERNS = [(r["tag"], re.compile(r["pattern"], re.I)) for r in RULES]


def generate_tags(text):
    normalized = unicodedata.normalize("NFKC", str(text or ""))
    return [tag for tag, pattern in PATTERNS if pattern.search(normalized)]


def browser_script():
    return '''"use strict";
// Generated by python -m dailynews.exterior_tags; edit the Python vocabulary.
(() => {
  const rules = ''' + json.dumps(RULES, ensure_ascii=False, indent=2) + ''';
  const patterns = rules.map(rule => new RegExp(rule.pattern, "i"));
  const canonical = tag => rules.find(rule => rule.tag === tag || rule.aliases.includes(tag))?.tag || tag;
  function derive(item) {
    // Stored tags and application ideas cannot become evidence for new tags.
    const text = [item?.title, item?.desc, item?.summary].filter(Boolean).join(" ").normalize("NFKC");
    return rules.filter((rule, index) => patterns[index].test(text)).map(rule => rule.tag);
  }
  window.DailyNewsExteriorTags = {rules, derive, canonical,
    matches: (item, tag) => (item.tags || []).includes(canonical(tag))};
})();
'''


if __name__ == "__main__":
    destination = Path(__file__).resolve().parents[1] / "dailynews_exterior_tags.js"
    destination.write_text(browser_script(), encoding="utf-8")
    print(f"Generated {len(RULES)} exterior genres: {destination.name}")
