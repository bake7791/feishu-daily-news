#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
燃料电池汽车产业情报追踪
全球范围搜索政策/事件 → AI 摘要 → 推送飞书群

搜索引擎: Bing Web Search API (Azure 免费层 1000次/月)
          或 SerpAPI (Google, 100次/月免费)
"""

import json, os, urllib.request, urllib.parse
import hmac, hashlib, base64, time as time_module
from datetime import datetime, timedelta

# ── 配置 ──────────────────────────────────────────
WEBHOOK_URL    = os.environ["FEISHU_WEBHOOK_URL"]
FEISHU_SECRET  = os.environ["FEISHU_SECRET"]
SEARCH_ENGINE  = os.environ.get("SEARCH_ENGINE", "bing")  # bing | serpapi
BING_API_KEY   = os.environ.get("BING_API_KEY", "")
SERPAPI_KEY    = os.environ.get("SERPAPI_KEY", "")

# 搜索查询 — 燃料电池汽车相关政策 & 重大事件
QUERIES = [
    "fuel cell vehicle policy regulation 2025 2026",
    "hydrogen fuel cell car government incentive subsidy",
    "燃料电池汽车 政策 补贴 2025 2026",
    "fuel cell electric vehicle FCEV industry news",
    "hydrogen economy national strategy fuel cell",
]

MAX_RESULTS = 15  # 总结果数上限
# ──────────────────────────────────────────────────


def search_bing(query, count=10):
    """Bing Web Search API v7"""
    url = "https://api.bing.microsoft.com/v7.0/search"
    params = urllib.parse.urlencode({"q": query, "count": count, "mkt": "en-US", "freshness": "Month"})
    req = urllib.request.Request(
        f"{url}?{params}",
        headers={"Ocp-Apim-Subscription-Key": BING_API_KEY},
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read().decode())
    results = []
    for item in data.get("webPages", {}).get("value", []):
        results.append({
            "title": item["name"],
            "url": item["url"],
            "snippet": item.get("snippet", ""),
            "source": "Bing",
        })
    return results


def search_serpapi(query, count=10):
    """SerpAPI — Google Search"""
    url = "https://serpapi.com/search"
    params = urllib.parse.urlencode({
        "q": query, "num": count, "api_key": SERPAPI_KEY,
        "engine": "google", "hl": "en", "gl": "us",
        "tbs": "qdr:m",  # past month
    })
    with urllib.request.urlopen(f"{url}?{params}", timeout=15) as resp:
        data = json.loads(resp.read().decode())
    results = []
    for item in data.get("organic_results", []):
        results.append({
            "title": item.get("title", ""),
            "url": item.get("link", ""),
            "snippet": item.get("snippet", ""),
            "source": "Google",
        })
    return results


def search_all():
    """执行全部查询，去重，返回汇总结果"""
    search_func = search_bing if SEARCH_ENGINE == "bing" else search_serpapi
    seen_urls = set()
    all_results = []

    for q in QUERIES:
        try:
            results = search_func(q, count=8)
            for r in results:
                if r["url"] not in seen_urls:
                    seen_urls.add(r["url"])
                    all_results.append(r)
        except Exception as e:
            print(f"[WARN] Search failed for '{q[:40]}...': {e}")

    # 按相关性排序（snippet 长度作为简易相关度指标）
    all_results.sort(key=lambda x: len(x["snippet"]), reverse=True)
    return all_results[:MAX_RESULTS]


def generate_summary(results):
    """生成 AI 可读的结构化摘要文档"""
    today = datetime.now().strftime("%Y-%m-%d")
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

    doc_lines = [
        f"# 🔋 燃料电池汽车产业情报日报",
        f"**日期**: {today}  |  **信源数**: {len(results)}  |  **搜索范围**: 全球",
        "",
        "---",
        "",
    ]

    # 按主题分类
    categories = {
        "政策法规": [],
        "产业动态": [],
        "技术创新": [],
        "市场投资": [],
        "国际合作": [],
    }

    policy_kw = ["policy", "regulation", " subsidy", "incentive", "government", "ban", "mandate",
                 "政策", "补贴", "法规", "标准", "政府"]
    tech_kw = ["technology", "breakthrough", "efficiency", "stack", "membrane", "catalyst",
               "技术", "突破", "效率"]
    market_kw = ["investment", "funding", "market", "stock", "IPO", "acquisition", "partnership",
                 "投资", "市场", "融资", "合作"]
    international_kw = ["EU", "Europe", "China", "Japan", "Korea", "Germany", "US", "California",
                        "欧盟", "中国", "日本", "韩国", "德国", "美国"]

    for r in results:
        text = (r["title"] + " " + r["snippet"]).lower()
        if any(kw.lower() in text for kw in policy_kw):
            categories["政策法规"].append(r)
        elif any(kw.lower() in text for kw in international_kw):
            categories["国际合作"].append(r)
        elif any(kw.lower() in text for kw in tech_kw):
            categories["技术创新"].append(r)
        elif any(kw.lower() in text for kw in market_kw):
            categories["市场投资"].append(r)
        else:
            categories["产业动态"].append(r)

    for cat, items in categories.items():
        if not items:
            continue
        doc_lines.append(f"## 📌 {cat}（{len(items)}条）")
        doc_lines.append("")
        for i, item in enumerate(items, 1):
            doc_lines.append(f"### {i}. {item['title']}")
            doc_lines.append(f"")
            doc_lines.append(f"**摘要**: {item['snippet']}")
            doc_lines.append(f"**信源**: [{item['url']}]({item['url']})")
            doc_lines.append("")
        doc_lines.append("---")
        doc_lines.append("")

    doc_lines += [
        "> ℹ️ 本报告由 AI 自动生成，基于全球公开信源搜索。",
        "> 建议结合专业分析判断，不构成投资建议。",
        f"> 生成时间: {today}",
    ]

    return "\n".join(doc_lines)


def send_to_feishu(markdown_content, title):
    """发送飞书卡片消息"""
    ts = str(int(time_module.time()))
    sign_key = (ts + "\n" + FEISHU_SECRET).encode("utf-8")
    sig = base64.b64encode(hmac.new(sign_key, b"", hashlib.sha256).digest()).decode()
    url = f"{WEBHOOK_URL}?timestamp={ts}&sign={sig}"

    # 飞书卡片最大 5000 字符，超长则截断
    content = markdown_content[:4800]
    if len(markdown_content) > 4800:
        content += "\n\n> ⚠️ 内容过长已截断，完整报告请查看飞书文档"

    payload = {
        "msg_type": "interactive",
        "card": {
            "header": {
                "title": {"tag": "plain_text", "content": title},
                "template": "blue",
            },
            "elements": [
                {"tag": "markdown", "content": content},
            ],
        },
    }

    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json; charset=utf-8"}, method="POST")
    with urllib.request.urlopen(req, timeout=15) as resp:
        result = json.loads(resp.read().decode())
    if result.get("code") != 0:
        raise Exception(f"Feishu error: {result}")
    print("[OK] Pushed to Feishu")


def main():
    print("[INFO] Searching global sources for fuel cell vehicle intelligence...")
    results = search_all()

    if not results:
        print("[ERROR] No results found")
        send_to_feishu("⚠️ 今日未搜索到燃料电池汽车相关新情报，请检查搜索引擎配置。", "🔋 燃料电池情报日报")
        return

    print(f"[INFO] Found {len(results)} results, generating summary...")
    summary = generate_summary(results)

    title = f'🔋 燃料电池汽车情报日报 — {datetime.now().strftime("%m.%d")}'
    send_to_feishu(summary, title)
    print("[OK] Done!")


if __name__ == "__main__":
    main()