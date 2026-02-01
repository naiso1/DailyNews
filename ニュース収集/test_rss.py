import sys
import requests
import feedparser
import time

sys.stdout.reconfigure(encoding='utf-8')

# テスト対象のRSSフィード
RSS_FEEDS_TO_TEST = [
    # Yahoo!ニュース（日本）
    {"name": "Yahoo!ニュース 経済", "url": "https://news.yahoo.co.jp/rss/topics/business.xml"},
    {"name": "Yahoo!ニュース IT", "url": "https://news.yahoo.co.jp/rss/topics/it.xml"},
    
    # 自動車専門サイト（日本）
    {"name": "Response.jp", "url": "https://response.jp/rss/rss2.xml"},
    {"name": "くるまのニュース", "url": "https://kuruma-news.jp/feed"},
    {"name": "AUTOCAR JAPAN", "url": "https://www.autocar.jp/feed"},
    {"name": "Motor-Fan", "url": "https://motor-fan.jp/mf/feed/"},
    {"name": "Car-Me", "url": "https://car-me.jp/feed"},
    {"name": "MOBY", "url": "https://car-moby.jp/feed"},
    {"name": "CarView", "url": "https://carview.yahoo.co.jp/rss/news.xml"},
    {"name": "ベストカー", "url": "https://bestcarweb.jp/feed"},
    {"name": "ドライバーWeb", "url": "https://driver-web.jp/feed"},
    {"name": "GAZOO", "url": "https://gazoo.com/rss/news.xml"},
    {"name": "Webモーターマガジン", "url": "https://web.motormagazine.co.jp/feed"},
    
    # 日本のテック
    {"name": "日経クロステック", "url": "https://xtech.nikkei.com/rss/xtech-all.rdf"},
    {"name": "ITmedia", "url": "https://rss.itmedia.co.jp/rss/2.0/itmedia_all.xml"},
    {"name": "MONOist", "url": "https://monoist.itmedia.co.jp/rss/2.0/monoist_all.xml"},
    
    # 米国自動車
    {"name": "Automotive News", "url": "https://www.autonews.com/rss.xml"},
    {"name": "Autoblog", "url": "https://www.autoblog.com/rss.xml"},
    {"name": "The Drive", "url": "https://www.thedrive.com/rss/all"},
    {"name": "Motor1", "url": "https://www.motor1.com/rss/news/all/"},
    {"name": "CarScoops", "url": "https://www.carscoops.com/feed/"},
    {"name": "Jalopnik", "url": "https://jalopnik.com/rss"},
    {"name": "Car and Driver", "url": "https://www.caranddriver.com/rss/all.xml/"},
    {"name": "MotorTrend", "url": "https://www.motortrend.com/feed/"},
    
    # 欧州自動車
    {"name": "AUTOCAR UK", "url": "https://www.autocar.co.uk/rss"},
    {"name": "Top Gear", "url": "https://www.topgear.com/feed/all"},
    {"name": "Auto Express", "url": "https://www.autoexpress.co.uk/feed/all"},
    
    # 中国自動車
    {"name": "汽车之家", "url": "https://www.autohome.com.cn/rss/news.xml"},
    {"name": "太平洋汽车网", "url": "https://www.pcauto.com.cn/rss/news.xml"},
    
    # インド自動車
    {"name": "Autocar India", "url": "https://www.autocarindia.com/rss/news.xml"},
    {"name": "CarDekho", "url": "https://www.cardekho.com/rss/news.xml"},
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}

print("=== RSSフィード有効性検証 ===\n")

valid_feeds = []
invalid_feeds = []

for feed_info in RSS_FEEDS_TO_TEST:
    name = feed_info["name"]
    url = feed_info["url"]
    
    try:
        response = requests.get(url, headers=HEADERS, timeout=10)
        
        if response.status_code == 200:
            feed = feedparser.parse(response.content)
            entry_count = len(feed.entries)
            
            if entry_count > 0:
                print(f"✓ [{name}] OK - {entry_count}件")
                valid_feeds.append(feed_info)
            else:
                print(f"✗ [{name}] 記事0件")
                invalid_feeds.append((name, "記事0件"))
        else:
            print(f"✗ [{name}] HTTPエラー: {response.status_code}")
            invalid_feeds.append((name, f"HTTP {response.status_code}"))
            
    except Exception as e:
        print(f"✗ [{name}] 接続エラー: {str(e)[:30]}")
        invalid_feeds.append((name, str(e)[:30]))
    
    time.sleep(0.3)

print("\n" + "=" * 50)
print(f"\n有効なフィード: {len(valid_feeds)}件")
print(f"無効なフィード: {len(invalid_feeds)}件")

if invalid_feeds:
    print("\n--- 無効なフィード一覧 ---")
    for name, reason in invalid_feeds:
        print(f"  - {name}: {reason}")

print("\n--- 有効なフィードのPythonコード ---")
print("RSS_FEEDS = [")
for f in valid_feeds:
    print(f'    {{"name": "{f["name"]}", "url": "{f["url"]}"}},')
print("]")
