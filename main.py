import feedparser
import requests
import os
import json

# ===================== 配置区域 =====================
# 科技新闻 RSS（可自由更换）
RSS_NEWS = "https://36kr.com/feed"          # 36氪（推荐）
# RSS_NEWS = "https://www.jiqizhixin.com/rss"  # 机器之心（备选）
# RSS_NEWS = "https://www.infoq.cn/feed"      # InfoQ

# DeepSeek API 配置（若不需要 AI 整理，可将 USE_AI 设为 False）
USE_AI = True   # True=使用 DeepSeek AI 整理, False=直接推送 RSS 原文
DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEEPSEEK_MODEL = "deepseek-chat"

# 推送渠道
USE_WEBHOOK = True   # True=企业微信机器人, False=WxPusher
# ==================================================

def fetch_rss(url):
    """抓取 RSS 并解析"""
    try:
        resp = requests.get(url, timeout=25)
        resp.raise_for_status()
        return feedparser.parse(resp.text)
    except Exception as e:
        print(f"RSS 抓取失败 [{url}]: {e}")
        return None

def send_wecom(webhook_url, content):
    """推送到企业微信群机器人（Markdown 格式），自动截断过长内容"""
    # 企业微信 Markdown 消息限制 4096 字节
    max_bytes = 4000
    if len(content.encode('utf-8')) > max_bytes:
        # 按字符截断，保留尾部提示
        content = content[:max_bytes//4] + "\n\n... (内容过长已截断)"
    body = {
        "msgtype": "markdown",
        "markdown": {"content": content}
    }
    try:
        resp = requests.post(webhook_url, json=body, timeout=10)
        print(f"企微推送状态: {resp.status_code}")
    except Exception as e:
        print(f"企微推送失败: {e}")

def send_wxpush(app_token, uid, content):
    """推送到 WxPusher（微信服务号）"""
    url = "https://wxpusher.zjiecode.com/api/send/message"
    payload = {
        "appToken": app_token,
        "content": content,
        "contentType": 3,
        "uids": [uid]
    }
    try:
        resp = requests.post(url, json=payload, timeout=10)
        print(f"WxPusher 推送状态: {resp.status_code}")
    except Exception as e:
        print(f"WxPusher 推送失败: {e}")

def llm_summary(api_key, raw_news):
    """调用 DeepSeek API 进行新闻智能整理"""
    if not api_key:
        print("警告：DeepSeek API Key 未配置，将使用备用方案")
        return None

    prompt = f"""你是科技资讯编辑，请将以下新闻列表整理成一份简洁的日报，要求：
1. 筛选出与科技、AI、开源、商业科技动态相关的高价值新闻，剔除无关内容。
2. 每条新闻用一句话概括（不超过60字），并附上原文链接。
3. 格式为：“数字. 标题：一句话摘要 [原文链接]”
4. 按重要性排序，最多保留 10 条。
5. 整体排版清晰，不要多余的开场白或结束语。

新闻列表：
{str(raw_news.entries[:15]) if raw_news and raw_news.entries else "暂无数据"}"""

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": DEEPSEEK_MODEL,
        "messages": [{"role": "user", "content": prompt}]
    }
    try:
        resp = requests.post(
            f"{DEEPSEEK_BASE_URL}/chat/completions",
            headers=headers,
            json=payload,
            timeout=30
        )
        resp.raise_for_status()
        result = resp.json()
        return result["choices"][0]["message"]["content"]
    except Exception as e:
        print(f"DeepSeek AI 整理失败: {e}")
        return None

def build_fallback_report(news_feed):
    """当 AI 不可用时，直接推送 RSS 原始标题和链接（无摘要）"""
    lines = ["# 📰 今日科技快讯\n"]
    if news_feed and news_feed.entries:
        for i, entry in enumerate(news_feed.entries[:10], 1):
            title = entry.get("title", "无标题")
            link = entry.get("link", "")
            lines.append(f"{i}. {title}\n[原文链接]({link})")
    else:
        lines.append("暂无科技资讯")
    return "\n".join(lines)

if __name__ == "__main__":
    # 读取环境变量
    webhook_url = os.getenv("WEBHOOK_URL")
    app_token = os.getenv("APP_TOKEN")
    user_uid = os.getenv("USER_UID")
    api_key = os.getenv("DEEPSEEK_API_KEY")

    # 检查推送配置
    if USE_WEBHOOK and not webhook_url:
        print("错误：未设置 WEBHOOK_URL 环境变量")
        exit(1)
    if not USE_WEBHOOK and (not app_token or not user_uid):
        print("错误：未设置 APP_TOKEN 或 USER_UID")
        exit(1)

    # 抓取 RSS
    print("正在抓取科技新闻 RSS...")
    news = fetch_rss(RSS_NEWS)

    # 生成报告
    report = None
    if USE_AI and api_key:
        print("正在调用 DeepSeek AI 整理新闻...")
        report = llm_summary(api_key, news)
    if not report:
        print("使用备用方案生成报告...")
        report = build_fallback_report(news)

    # 推送
    if USE_WEBHOOK:
        print("正在推送到企业微信...")
        send_wecom(webhook_url, report)
    else:
        print("正在推送到 WxPusher...")
        send_wxpush(app_token, user_uid, report)

    print("✅ 推送完成！")
