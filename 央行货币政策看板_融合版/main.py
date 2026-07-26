#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
main.py — 央行货币政策跟踪看板主流程（融合版）

流程：爬取（增量缓存）→ 标题分类 → 标题清洗 → 五维度提取 → 排除规则 → HTML看板
可选：--review 同时生成"货币政策基调与方向"审阅页

用法：
    python main.py                    # 增量更新并生成看板
    python main.py --refresh          # 忽略缓存全量重爬
    python main.py --review           # 同时生成基调与方向审阅页
    python main.py --start-date 20250101 --output ./out
"""

import argparse
import os
from collections import Counter

_CODE_DIR = os.path.dirname(os.path.abspath(__file__))
import sys
if _CODE_DIR not in sys.path:
    sys.path.insert(0, _CODE_DIR)

import config
import crawler
import extractor
import dashboard
import review


def main():
    parser = argparse.ArgumentParser(description='央行货币政策跟踪看板')
    parser.add_argument('--cache', default=config.CACHE_PATH,
                        help='文章缓存 JSON 路径')
    parser.add_argument('--output', default=config.OUTPUT_DIR,
                        help='看板输出目录（默认 output/）')
    parser.add_argument('--refresh', action='store_true',
                        help='忽略缓存，全量重爬')
    parser.add_argument('--review', action='store_true',
                        help='同时生成"基调与方向"审阅页')
    parser.add_argument('--start-date', default='20240801',
                        help='起始日期 YYYYMMDD（默认 20240801）')
    parser.add_argument('--max-pages', type=int, default=1000,
                        help='列表最多翻页数（每页约10篇，默认1000为安全上限，'
                             '实际由日期/缓存条件提前停止）')
    args = parser.parse_args()

    # 1. 爬取（带增量缓存）
    articles = crawler.crawl(
        cache_path=args.cache,
        start_date=args.start_date,
        refresh=args.refresh,
        max_pages=args.max_pages,
    )

    # 2. 标题分类 + 标题清洗
    for a in articles:
        tag, include = extractor.classify_article(a['title'])
        a['tag'] = tag or ''
        a['include'] = include
        a['clean_title'] = extractor.clean_title(a['title'])

    # 3. 五维度核心观点提取
    for a in articles:
        if a.get('tag') and a.get('content'):
            a.update(extractor.extract_core_view(
                a['content'], a['title'], a['tag']))

    # 4. 排除规则
    filtered = [a for a in articles
                if a.get('include') and extractor.should_include(a)]
    print(f"排除规则后: {len(filtered)} 篇")

    # 5. 组装看板数据
    dashboard_data = []
    for a in filtered:
        has_content = any(a.get(f, ['/']) != ['/'] for f in dashboard.DIMS)
        if not has_content:
            continue
        d = a['date']
        a['date_fmt'] = f"{d[:4]}-{d[4:6]}-{d[6:8]}" if len(d) == 8 else d
        dashboard_data.append({
            'date': a['date_fmt'],
            'title': a['title'],
            'clean_title': a.get('clean_title', a['title']),
            'link': a.get('link', ''),
            'author': a.get('author', ''),
            'tag': a.get('tag', ''),
            **{dim: ' / '.join(a.get(dim, ['/'])) for dim in dashboard.DIMS},
        })

    # 6. 生成看板
    dashboard_path = os.path.join(args.output, 'index.html')
    dashboard.generate_dashboard(dashboard_data, dashboard_path)
    print(f"看板数据: {len(dashboard_data)} 篇")
    print(f"按标签: {dict(Counter(d['tag'] for d in dashboard_data))}")

    # 7. 可选：基调与方向审阅页
    if args.review:
        review_data = review.build_review_data(filtered)
        review.generate_review_page(
            review_data, os.path.join(args.output, 'policy_review.html'))


if __name__ == '__main__':
    main()
