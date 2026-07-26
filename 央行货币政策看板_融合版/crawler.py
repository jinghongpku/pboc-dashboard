#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
crawler.py — 金融新闻网（financialnews.com.cn）爬虫模块
职责：文章检索/抓取、正文抓取、本地 JSON 缓存（支持增量更新）

数据来源（2026-07 适配网站改版后）：
1. 站内搜索接口 /xy/Search.do —— 按作者检索，覆盖全部历史文章
   （旧 getDataList.action 列表接口已 404 下线；author 字段有效，journalist 字段数据不全）
2. 栏目 HTML 页面 node_3002_{n}.html —— 仅暴露最近 20 页（约两周），
   用于补充搜索索引延迟（搜索索引比网站晚数天）
"""

import requests
import json
import re
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from bs4 import BeautifulSoup

SEARCH_URL = "https://www.financialnews.com.cn/xy/Search.do"
COLUMN_URL = "https://www.financialnews.com.cn/node_3002.html"
COLUMN_PAGE_URL = "https://www.financialnews.com.cn/node_3002_{page}.html"
COLUMN_MAX_PAGES = 20  # 栏目页只暴露最近 20 页

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

# 列表页/正文页中不代表具体作者的占位署名
_PLACEHOLDER_AUTHORS = {'本报记者', '本报', '记者', '新华社'}


# ============================================================
# 途径一：站内搜索接口（按作者，覆盖全部历史）
# ============================================================

def search_author_articles(author, start_date, known_links=None,
                           page_size=100, max_pages=50, sleep=0.3):
    """
    通过 /xy/Search.do 检索指定作者的全部文章
    结果大致按日期倒序；增量模式下整页无新链接时提前停止
    返回：[{date, title, link, author}]（date 为 YYYYMMDD）
    """
    articles = []
    for page in range(max_pages):
        params = {
            "q": "", "pageNo": page, "pageSize": page_size,
            "channel": 1, "siteID": "1", "sort": "",
            "author": author,
        }
        try:
            resp = requests.get(SEARCH_URL, params=params, headers=HEADERS,
                                timeout=30)
            resp.encoding = 'utf-8'
            data = resp.json()
        except Exception as e:
            print(f"搜索接口错误（{author} 第{page}页）: {e}")
            break
        arts = data.get('article') or []
        if not arts:
            break
        fresh = 0
        for a in arts:
            date = a.get('date', '').replace('-', '')
            link = a.get('url', '').replace('http://', 'https://')
            if not link or date < start_date:
                continue
            articles.append({
                'date': date,
                'title': a.get('title', ''),
                'link': link,
                'author': a.get('author', '') or author,
            })
            if known_links is not None and link not in known_links:
                fresh += 1
        total = data.get('foundNum', 0)
        if (page + 1) * page_size >= total:
            break
        if known_links and fresh == 0:
            break  # 增量：整页均为已缓存文章
        time.sleep(sleep)
    return articles


# ============================================================
# 途径二：栏目 HTML 页面（仅最近约两周，补充搜索索引延迟）
# ============================================================

def fetch_article_list(page_num):
    """抓取栏目单页文章列表，每页约 10 篇"""
    url = COLUMN_URL if page_num == 1 else COLUMN_PAGE_URL.format(page=page_num)
    try:
        resp = requests.get(url, headers=HEADERS, timeout=30)
        resp.encoding = "utf-8"
        if resp.status_code != 200:
            return []
        soup = BeautifulSoup(resp.text, "html.parser")
        news_list = soup.find(
            'div', class_=lambda c: c and 'news-list' in str(c))
        if not news_list:
            return []
        articles = []
        for h4 in news_list.find_all('h4'):
            a = h4.find('a', href=re.compile(r'content_\d+\.html'))
            if not a:
                continue
            container_text = h4.parent.get_text(' ', strip=True)
            m_date = re.search(r'(20\d{2})-(\d{2})-(\d{2})', container_text)
            m_author = re.search(r'作者[：:](?:记者\s*)?([^\s]{2,4})',
                                 container_text)
            author = m_author.group(1) if m_author else ''
            if author in _PLACEHOLDER_AUTHORS:
                author = ''
            articles.append({
                "date": ''.join(m_date.groups()) if m_date else '',
                "title": a.get_text(strip=True),
                "link": a['href'].replace('http://', 'https://'),
                "author": author,
            })
        return articles
    except Exception as e:
        print(f"栏目第 {page_num} 页错误: {e}")
        return []


# ============================================================
# 正文抓取
# ============================================================

def extract_page_title(html):
    """
    从文章详情页提取权威标题（页面上黑色大标题本身）。
    优先 <h1>，其次 <title>（剥离 '-中国金融新闻网' 等站点后缀）。
    用于替代基于模式匹配粘连截断的 clean_title（后者降级为兜底）。
    """
    soup = BeautifulSoup(html, "html.parser")
    h1 = soup.find("h1")
    if h1 and h1.get_text(strip=True):
        return re.sub(r'\s+', ' ', h1.get_text(strip=True))
    if soup.title and soup.title.string:
        t = soup.title.string
        t = re.sub(r'[-_—|]*\s*中国金融新闻网\s*$', '', t).strip()
        t = re.sub(r'[-_—|]*\s*金融时报\s*$', '', t).strip()
        t = re.sub(r'\s+', ' ', t).strip()
        if t:
            return t
    return ""


def fetch_page_title(url):
    """单独抓取文章页权威标题（用于存量缓存一次性回填）"""
    try:
        resp = requests.get(url, headers=HEADERS, timeout=20)
        resp.encoding = "utf-8"
        return extract_page_title(resp.text)
    except Exception as e:
        print(f"Fetch page title error for {url}: {e}")
        return ""


def backfill_page_titles(articles, max_workers=5):
    """批量回填页面权威标题，写回 title_page 字段（仅处理缺失该字段的）"""
    targets = [a for a in articles if a.get("link") and not a.get("title_page")]
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_article = {executor.submit(fetch_page_title, a["link"]): a
                             for a in targets}
        done = 0
        for future in as_completed(future_to_article):
            article = future_to_article[future]
            try:
                article["title_page"] = future.result()
            except Exception:
                article["title_page"] = ""
            done += 1
            if done % 100 == 0:
                print(f"  页面标题回填进度 {done}/{len(targets)}")
    return articles


def fetch_article_content(url):
    """
    爬取单篇文章正文，返回 (正文, 署名作者, 页面权威标题)
    署名作者取自正文页头部"作者：记者 XXX"，用于列表页作者缺失时二次确认
    页面权威标题取自文章页 <h1>/<title>，即页面上黑色大标题本身
    """
    try:
        resp = requests.get(url, headers=HEADERS, timeout=20)
        resp.encoding = "utf-8"
        html = resp.text
        soup = BeautifulSoup(html, "html.parser")

        page_title = extract_page_title(html)

        m = re.search(r'作者[：:](?:记者\s*)?([^\s<]{2,4})', html)
        byline = m.group(1) if m else ''
        if byline in _PLACEHOLDER_AUTHORS:
            byline = ''

        content_div = (soup.find("div", class_="detail-cont") or
                       soup.find("div", id="content") or
                       soup.find("div", class_="content") or
                       soup.find("div", class_="article-content") or
                       soup.find("article"))
        text = ""
        if content_div:
            paragraphs = content_div.find_all(["p", "div"])
            text = "\n".join(p.get_text(strip=True)
                             for p in paragraphs
                             if p.get_text(strip=True))
            # 仅当正文容器几乎为空时才回退到 body，且只保留成句的段落，
            # 避免短公告类文章（会见/暂停国债买入等）被导航栏垃圾文本污染
            if len(text) < 30:
                body = soup.find("body")
                if body:
                    lines = [ln for ln in body.get_text(separator="\n", strip=True).split("\n")
                             if len(ln) >= 30 and "。" in ln]
                    text = "\n".join(lines)
        return text, byline, page_title
    except Exception as e:
        print(f"Fetch content error for {url}: {e}")
        return "", "", ""


def fetch_all_contents(articles, max_workers=5):
    """批量爬取文章正文，结果写回 content / byline_author 字段"""
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_article = {}
        for article in articles:
            if article.get("link"):
                future = executor.submit(fetch_article_content,
                                         article["link"])
                future_to_article[future] = article
        for future in as_completed(future_to_article):
            article = future_to_article[future]
            try:
                content, byline, page_title = future.result()
                article["content"] = content
                article["byline_author"] = byline
                if page_title:
                    article["title_page"] = page_title
            except Exception:
                article["content"] = ""
                article["byline_author"] = ""
    return articles


# ============================================================
# 本地缓存与增量更新
# ============================================================

def load_cache(cache_path):
    """读取本地缓存，不存在或损坏时返回空列表"""
    if not os.path.exists(cache_path):
        return []
    try:
        with open(cache_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"缓存读取失败（{e}），将全量重爬")
        return []


def save_cache(cache_path, articles):
    with open(cache_path, 'w', encoding='utf-8') as f:
        json.dump(articles, f, ensure_ascii=False, indent=2)


def _slim(a):
    """非目标文章的瘦身缓存记录（不占正文空间，仅用于增量去重）"""
    return {'date': a.get('date', ''), 'title': a.get('title', ''),
            'link': a.get('link', ''), 'author': a.get('author', ''),
            'content': ''}


def crawl(cache_path='articles_cache.json',
          authors=('马梅若', '马玲'),
          start_date='20240801',
          refresh=False,
          max_pages=1000,
          page_sleep=0.3):
    """
    爬虫主入口：搜索接口全量检索 + 栏目页补充最新 → 正文抓取 → 合并缓存

    - 搜索接口提供全部历史文章（作者已确认）
    - 栏目页补充搜索索引尚未收录的最近文章（约两周窗口）
    - 缓存中作者命中但正文缺失的会自动补抓
    返回：目标作者、日期范围内且含正文的文章列表
    """
    def author_match(name):
        return any(n in (name or '') for n in authors)

    cached = [] if refresh else load_cache(cache_path)
    known_links = {a.get('link') for a in cached if a.get('link')}
    if cached:
        print(f"加载缓存: {len(cached)} 篇，增量更新中...")

    # 1. 搜索接口：按作者全量检索
    # 注意：CMS 作者字段存在"马梅若"和"记者马梅若"两种写法，
    # author 参数为精确匹配，必须用两种变体分别检索再合并（2026-07-21 修复）
    search_articles = []
    for name in authors:
        for variant in (name, f'记者{name}'):
            got = search_author_articles(variant, start_date, known_links)
            print(f"搜索接口 [{variant}]: {len(got)} 篇在范围内")
            search_articles.extend(got)
    seen = set()
    uniq_search = []
    for a in search_articles:  # 合著/重复文章按链接去重
        if a['link'] in seen:
            continue
        seen.add(a['link'])
        # 作者字段规范化："记者马梅若" -> "马梅若"
        a['author'] = re.sub(r'^记者', '', a.get('author', ''))
        uniq_search.append(a)
    new_from_search = [a for a in uniq_search if a['link'] not in known_links]
    print(f"搜索接口去重后 {len(uniq_search)} 篇，其中新文章 {len(new_from_search)} 篇")

    # 2. 栏目页：补充最近文章（覆盖搜索索引延迟）
    new_list = []
    for page in range(1, COLUMN_MAX_PAGES + 1):
        items = fetch_article_list(page)
        if not items:
            break
        fresh = [a for a in items
                 if a.get('link') not in known_links and a.get('link') not in seen]
        new_list.extend(fresh)
        dates = [a['date'] for a in items if a.get('date')]
        if dates and max(dates) < start_date:
            break
        if cached and not fresh:
            break
        time.sleep(page_sleep)
    in_range = [a for a in new_list if a.get('date', '') >= start_date]
    direct = [a for a in in_range if author_match(a.get('author'))]
    unknown = [a for a in in_range if not a.get('author', '').strip()]
    listed_reject = [_slim(a) for a in in_range
                     if a.get('author', '').strip()
                     and not author_match(a.get('author'))]
    print(f"栏目页补充: 新文章 {len(in_range)} 篇（直接命中 {len(direct)}，"
          f"作者待确认 {len(unknown)}）")

    # 3. 缓存中目标作者但正文缺失的，补抓
    retry = [a for a in cached
             if author_match(a.get('author')) and not a.get('content')]

    # 4. 抓正文
    targets = new_from_search + direct + unknown + retry
    if targets:
        print(f"爬取正文中（{len(targets)} 篇）...")
        fetch_all_contents(targets)

    # 5. 作者二次确认：列表作者缺失时采用正文署名
    for a in targets:
        if not a.get('author', '').strip():
            a['author'] = a.get('byline_author', '')

    confirmed = [a for a in new_from_search + direct + unknown
                 if author_match(a.get('author'))]
    rejected = [_slim(a) for a in unknown
                if not author_match(a.get('author'))]
    print(f"本轮确认目标文章 {len(confirmed)} 篇"
          f"（正文有效 {sum(1 for a in confirmed if a.get('content'))} 篇）")

    # 6. 合并缓存（新记录覆盖同链接旧记录）
    updated_links = {a['link'] for a in confirmed + rejected
                     + listed_reject + retry if a.get('link')}
    merged = (confirmed + rejected + listed_reject + retry
              + [a for a in cached if a.get('link') not in updated_links])
    save_cache(cache_path, merged)

    result = [a for a in merged
              if author_match(a.get('author'))
              and a.get('date', '') >= start_date
              and a.get('content')]
    print(f"可用文章: {len(result)} 篇（缓存总量 {len(merged)} 篇）")
    return result
