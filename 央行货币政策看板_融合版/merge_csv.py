#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
merge_csv.py — 将历史全量CSV合并入文章缓存（一次性数据迁移）
CSV：/mnt/agents/upload/马梅若马玲_文章正文全量.csv（旧爬虫产出，541篇，截至2026-07-16）
合并规则：
- 链接已在缓存中的跳过（以缓存为准）
- 规范化标题+日期与缓存一致的跳过（同一文章的栏目版/电子版不同URL）
- 其余作为新文章写入缓存（正文取CSV内容）
"""

import csv
import json
import re
import sys

sys.path.insert(0, '/tmp/pboc_dashboard')
import extractor

CSV_PATH = '/mnt/agents/upload/马梅若马玲_文章正文全量.csv'
CACHE_PATH = '/tmp/pboc_run/articles_cache.json'


def norm_title(t):
    t = extractor.clean_title(t or '')
    return re.sub(r'\s+', '', t)[:25]


def main():
    with open(CACHE_PATH, encoding='utf-8') as f:
        cache = json.load(f)
    known_links = {a['link'].replace('http://', 'https://')
                   for a in cache if a.get('link')}
    known_ids = {(norm_title(a.get('title', '')), a.get('date', ''))
                 for a in cache if a.get('content')}

    with open(CSV_PATH, encoding='utf-8-sig') as f:
        rows = list(csv.DictReader(f))

    added, skip_link, skip_dup = [], 0, 0
    for r in rows:
        link = (r.get('链接') or '').replace('http://', 'https://')
        date = (r.get('日期') or '').replace('-', '')
        title = r.get('标题（原始）') or ''
        content = r.get('正文') or ''
        if not link or not date or not content:
            continue
        if link in known_links:
            skip_link += 1
            continue
        if (norm_title(title), date) in known_ids:
            skip_dup += 1
            continue
        added.append({
            'date': date,
            'title': title,
            'link': link,
            'author': (r.get('作者') or '').strip(),
            'content': content,
            'byline_author': '',
            '_source': 'csv_merge',
        })

    cache.extend(added)
    with open(CACHE_PATH, 'w', encoding='utf-8') as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)
    print(f"CSV {len(rows)} 行：链接重复 {skip_link}，同文不同链 {skip_dup}，新增 {len(added)}")


if __name__ == '__main__':
    main()
