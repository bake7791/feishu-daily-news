#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
燃料电池汽车产业情报日报
Google News RSS 全球搜索 → GPT-4o-mini AI 分析总结 → 飞书推送
完全免费：GitHub Models (GPT-4o-mini) + Google News RSS
"""

import json, os, urllib.request, urllib.parse
import xml.etree.ElementTree as ET
import hmac, hashlib, base64, time as time_module
from datetime import datetime, timedelta

# ── 配置 ────────────────────────────────────────────
WEBHOOK_URL    = os.environ["FEISHU_WEBHOOK_URL"]
FEISHU_SECRET  = os.environ["FEISHU_SECRET"]
GITHUB_TOKEN   = os.environ.get("GITHUB_TOKEN", "")
AI_MODEL       = "gpt-4o-mini"
AI_ENDPOINT    = "https://models.inference.ai.azure.com/chat/completions"

QUERIES = [
    ("fuel cell vehicle policy hydrogen regulation subsidy 2026", "en-US", "US"),
    ("hydrogen fuel cell FCEV industry government strategy",        "en-GB", "GB"),
    ("Brennstoffzelle Wasserstoff Fahrzeug Politik Deutschland EU", "de-DE", "DE"),
    ("pile combustible hydrogène véhicule politique France",        "fr-FR", "FR"),
    ("燃料電気自動車 水素 政策 トヨタ ホンダ 日本",                  "ja-JP", "JP"),
]
CN_QUERIES = [
    ("燃料电池汽车 政策 氢能 产业 补贴 2026",     "zh-CN", "CN"),
    ("氢能 燃料电池 示范城市群 政策 国家规划",     "zh-CN", "CN"),
]

MAX_SEARCH = 30  # 原始搜索结果上限
# ────────────────────────────────────────────────────


def search_google_news(query, hl, gl, max_results=50):
    ceid_map = {"CN":"CN:zh-Hans","US":"US:en","GB":"GB:en","JP":"JP:ja","DE":"DE:de","FR":"FR:fr","ES":"ES:es"}
    ceid = ceid_map.get(gl, f"{gl}:{hl.split('-')[0]}")
    rss_url = f"https://news.google.com/rss/search?q={urllib.parse.quote(query)}&hl={hl}&gl={gl}&ceid={ceid}"
    req = urllib.request.Request(rss_url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        xml_data = resp.read().decode("utf-8")
    root = ET.fromstring(xml_data)
    results = []
    for item in root.findall(".//item"):
        title_el, link_el, source_el, pubdate_el = item.find("title"), item.find("link"), item.find("source"), item.find("pubDate")
        title = title_el.text.strip() if title_el is not None and title_el.text else ""
        link  = link_el.text if link_el is not None else ""
        source = source_el.text.strip() if source_el is not None and source_el.text else "Unknown"
        pubdate = pubdate_el.text if pubdate_el is not None else ""
        skip = ["stock", "share price", "股", "advertisement", "sponsored", "click here"]
        if not title or any(w in title.lower() for w in skip):
            continue
        results.append({"title":title,"url":link,"source":source,"date":pubdate,"region":gl})
        if len(results)>=max_results: break
    return results


def search_all():
    seen = set(); all_results = []
    for query, hl, gl in QUERIES + CN_QUERIES:
        try:
            results = search_google_news(query, hl, gl)
            print(f"  [{gl}] {query[:35]}... -> {len(results)} results")
            for r in results:
                key = r["title"][:80]
                if key not in seen:
                    seen.add(key); all_results.append(r)
        except Exception as e:
            print(f"  [WARN] {gl}: {e}")
    def pd(r):
        try: return datetime.strptime(r["date"], "%a, %d %b %Y %H:%M:%S %Z")
        except: return datetime.min
    all_results.sort(key=pd, reverse=True)
    return all_results[:MAX_SEARCH]


def ai_analyze(articles):
    """用 GPT-4o-mini 对新闻进行综合分析总结"""
    # 构建新闻摘要
    articles_text = ""
    for i, a in enumerate(articles):
        flag = {"CN":"[中]","US":"[美]","GB":"[英]","JP":"[日]","DE":"[德]","FR":"[法]","ES":"[西]"}.get(a["region"],"[?]")
        articles_text += f"\n{i+1}. {flag} {a['title']} (来源: {a['source']})"

    prompt = f"""你是燃料电池汽车产业分析师。以下是今日全球最新相关新闻（{len(articles)}条）。请做综合分析：

{articles_text}

请生成一份结构化的产业情报分析报告，用中文输出，包括：

## 一、📊 今日核心要闻
（选3-5条最重要的，每条约50字概括要点）

## 二、🔍 政策与监管动态
（各国最新政策变化、法规更新、补贴调整等，归纳分析）

## 三、🏭 产业与技术趋势
（技术突破、量产进展、产业链变化等）

## 四、💡 综合研判
（100字以内，对行业趋势的简要判断）

格式要求：Markdown，简洁专业，每条分析不超过80字。"""

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {GITHUB_TOKEN}"
    }
    payload = {
        "model": AI_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 1500,
        "temperature": 0.3,
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(AI_ENDPOINT, data=data, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=90) as resp:
        result = json.loads(resp.read().decode())
    return result["choices"][0]["message"]["content"]


def build_card(ai_report, articles, total_chars):
    """构建飞书卡片：AI 分析 + 信源列表"""
    today = datetime.now().strftime("%Y-%m-%d")

    # AI 分析部分（控制在 3500 字符）
    ai_text = ai_report[:3500]
    if len(ai_report) > 3500:
        ai_text += "\n\n> ⚠️ 分析过长已截断"

    # 信源部分（控制在 1200 字符）
    sources = [f"\n**📎 今日信源（{len(articles)}条）**\n"]
    region_flags = {"CN":"🇨🇳","US":"🇺🇸","GB":"🇬🇧","JP":"🇯🇵","DE":"🇩🇪","FR":"🇫🇷","ES":"🇪🇸"}
    for i, a in enumerate(articles[:15], 1):
        flag = region_flags.get(a["region"], "")
        title = a["title"][:50] + "..." if len(a["title"])>50 else a["title"]
        sources.append(f"{i}. {flag} [{title}]({a['url']}) — {a['source']}")

    source_text = "\n".join(sources)[:1200]

    content = ai_text + source_text + f"\n\n---\n🤖 AI 分析 | Google News 全球检索 | {today}"

    return content


def send_to_feishu(markdown, title):
    """飞书卡片推送"""
    content_md = markdown[:4900]
    if len(markdown) > 4900:
        content_md += "\n\n> ⚠️ 内容过长已截断"

    payload = {
        "msg_type": "interactive",
        "card": {
            "header": {"title": {"tag": "plain_text", "content": title}, "template": "blue"},
            "elements": [{"tag": "markdown", "content": content_md}],
        },
    }
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")

    for attempt in range(3):
        ts = str(int(time_module.time()))
        sign_key = (ts + "\n" + FEISHU_SECRET).encode("utf-8")
        sig = base64.b64encode(hmac.new(sign_key, b"", hashlib.sha256).digest()).decode()
        url = f"{WEBHOOK_URL}?timestamp={ts}&sign={sig}"

        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json; charset=utf-8"}, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                result = json.loads(resp.read().decode())
            if result.get("code") == 0:
                print(f"[OK] Pushed (attempt {attempt+1})")
                return
            print(f"[RETRY {attempt+1}] {result}")
            time_module.sleep(2)
        except Exception as e:
            print(f"[RETRY {attempt+1}] {e}")
            time_module.sleep(2)
    raise Exception("Push failed after 3 retries")

def main():
    print("=" * 60)
    print("🔋 Fuel Cell Intelligence Daily — AI Powered")
    print("=" * 60)

    # Step 1: 搜索
    print("\n[1/3] Searching global sources...")
    articles = search_all()
    print(f"  Collected: {len(articles)} unique articles")

    if not articles:
        send_to_feishu("⚠️ 今日未检索到新情报", "🔋 燃料电池情报日报")
        return

    # Step 2: AI 分析
    print("\n[2/3] AI analyzing (GPT-4o-mini)...")
    try:
        ai_report = ai_analyze(articles)
        print(f"  AI report: {len(ai_report)} chars")
    except Exception as e:
        print(f"  AI failed: {e}, falling back to list format")
        ai_report = f"## ⚠️ AI 分析暂不可用\n\n今日检索到 {len(articles)} 篇相关新闻，详见信源列表。"

    # Step 3: 推送
    print("\n[3/3] Building card & pushing...")
    content = build_card(ai_report, articles, len(ai_report))
    print(f"  Card: {len(content)} chars")

    title = f'🔋 燃料电池情报日报 — {datetime.now().strftime("%m.%d")}'
    send_to_feishu(content, title)
    print("\n✅ Done!")


if __name__ == "__main__":
    main()