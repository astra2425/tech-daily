import feedparser
import requests
import os
import json

# ===================== 配置区域 =====================
# 科技新闻 RSS（选一个稳定的）
RSS_NEWS = "https://36kr.com/feed"          # 36氪（推荐）
# RSS_NEWS = "https://www.jiqizhixin.com/rss"  # 机器之心（备选）

# GitHub Trending RSS（只保留一个有效的）
RSS_GITHUB = "https://rsshub.app/github/trending/daily"  # 常用路径
# RSS_GITHUB = "https://rsshub.app/github/trending/all/daily"  # 备选

# DeepSeek API 配置
DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEEPSEEK_MODEL = "deepseek-chat"   # 可选 deepseek-reasoner / deepseek-v4-pro

# 推送渠道选择（二选一）
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
    """推送到企业微信群机器人（Markdown 格式）"""
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
        "contentType": 3,   # 3=Markdown
        "uids": [uid]
    }
    try:
        resp = requests.post(url, json=payload, timeout=10)
        print(f"WxPusher 推送状态: {resp.status_code}")
    except Exception as e:
        print(f"WxPusher 推送失败: {e}")

def llm_summary(api_key, raw_news, raw_github):
    """调用 DeepSeek API 进行智能整理"""
    if not api_key:
        print("警告：DeepSeek API Key 未配置，将使用备用方案")
        return None

    # 构建 Prompt（已修改 Star 条件为 >50）
    prompt = f"""你是技术资讯整理助手，严格按照要求处理信息：
1. 筛选今日高价值科技、AI、开源相关资讯，剔除广告、消费数码无关资讯，每条附带原文链接；
2. GitHub项目只保留Star>50的仓库；格式：项目名称 ⭐Star数量｜简介；
3. 使用Markdown排版，两大板块：〖今日科技热点〗〖⭐GitHub热门开源项目〗；
4. 全文控制在1800字以内，新闻最多8条，开源项目最多10个；
5. 不要多余开场白，资讯不足如实说明。

新闻原始数据：{str(raw_news.entries[:10]) if raw_news and raw_news.entries else "暂无数据"}
GitHub原始数据：{str(raw_github.entries[:12]) if raw_github and raw_github.entries else "暂无数据"}"""

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

def build_fallback_report(news_feed, github_feed):
    """当 AI 不可用时，生成简单的原始内容报告"""
    lines = ["# 每日科技资讯 & GitHub开源日报\n"]
    lines.append("## 📰 今日科技热点")
    if news_feed and news_feed.entries:
        for i, entry in enumerate(news_feed.entries[:8], 1):
            title = entry.get("title", "无标题")
            link = entry.get("link", "")
            lines.append(f"{i}. [{title}]({link})")
    else:
        lines.append("暂无科技资讯")

    lines.append("\n## ⭐ GitHub 热门开源项目")
    if github_feed and github_feed.entries:
        for i, entry in enumerate(github_feed.entries[:10], 1):
            title = entry.get("title", "无项目名")
            lines.append(f"{i}. {title}")
    else:
        lines.append("暂无 GitHub 热门项目")

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
    print("正在抓取 GitHub Trending RSS...")
    github_data = fetch_rss(RSS_GITHUB)

    # AI 整理（如果配置了 Key）
    report = None
    if api_key:
        print("正在调用 DeepSeek AI 整理内容...")
        report = llm_summary(api_key, news, github_data)

    # 降级方案
    if not report:
        print("使用备用方案生成报告...")
        report = build_fallback_report(news, github_data)

    # 推送
    if USE_WEBHOOK:
        print("正在推送到企业微信...")
        send_wecom(webhook_url, report)
    else:
        print("正在推送到 WxPusher...")
        send_wxpush(app_token, user_uid, report)

    print("✅ 推送完成！")
