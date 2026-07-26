#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
daily_update.py — 每日增量更新脚本

流程：
1. 增量爬取新文章（crawler.crawl 天然支持增量）
2. 标题分类 + 排除规则 + 五维度提取 + 近似去重
3. 对全部保留文章重新提取五维度摘句（pipeline.run_pipeline）
4. 后处理：资金态度门槛 + 跨维度去重
5. 生成看板 HTML（dashboard_gen）
6. 更新 pipeline_report.json

用法：
    python daily_update.py          # 常规增量更新
    python daily_update.py --full   # 全量重爬后更新
"""

import json
import os
import sys
import argparse
from collections import Counter
from datetime import date

_CODE_DIR = os.path.dirname(os.path.abspath(__file__))
if _CODE_DIR not in sys.path:
    sys.path.insert(0, _CODE_DIR)

import config
import crawler
import extractor
import pipeline
import dashboard_gen
from dashboard import DIMS


def main():
    parser = argparse.ArgumentParser(description='每日增量更新')
    parser.add_argument('--full', action='store_true',
                        help='忽略缓存全量重爬')
    args = parser.parse_args()

    print(f"{'='*60}")
    print(f"央行货币政策看板 · 每日更新")
    print(f"日期: {date.today().isoformat()}")
    print(f"{'='*60}\n")

    # ========== 阶段1：增量爬取 ==========
    print("【1/5】增量爬取新文章...")
    articles = crawler.crawl(
        cache_path=config.CACHE_PATH,
        start_date=config.START_DATE,
        refresh=args.full,
        max_pages=2000,
    )
    print(f"  可用文章: {len(articles)} 篇\n")

    # ========== 阶段2：标题分类 + 排除 + 提取 + 去重 ==========
    print("【2/5】分类 → 排除 → 提取 → 去重...")
    final, removed = pipeline.run_classification(
        json.load(open(config.CACHE_PATH, encoding='utf-8')),
        {'kept': [{'title': a['title'], 'date': a['date']} for a in articles],
         'removed': []}
    )
    print(f"  保留: {len(final)} 篇, 剔除: {len(removed)} 篇\n")

    # ========== 阶段3：更新 pipeline_report.json ==========
    print("【3/5】更新 pipeline_report.json...")
    report = {
        'start_date': config.START_DATE,
        'kept': [],
        'removed': removed,
    }
    for a in final:
        dims = {d: a.get(d, ['/']) for d in DIMS}
        report['kept'].append({
            'date': a['date'],
            'title': a['title'],
            'author': a.get('author', ''),
            'tag': a.get('tag', ''),
            'dims': {d: len([x for x in v if x != '/']) for d, v in dims.items()},
        })
    report['total_crawled'] = len(articles)
    report['summary'] = {
        'total_crawled': len(articles),
        'after_classify': len(final) + sum(1 for r in removed if r.get('stage') == '①标题分类'),
        'after_exclude': len(final) + sum(1 for r in removed if r.get('stage') in ('②排除规则', '③观点提取', '④近似去重')),
        'final_kept': len(final),
        'kept_by_tag': dict(Counter(a.get('tag', '') for a in final)),
        'removed_by_stage': dict(Counter(r.get('stage', '') for r in removed)),
    }
    with open(config.REPORT_PATH, 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"  报告已保存: {config.REPORT_PATH}\n")

    # ========== 阶段4：五维度提取 + 后处理 ==========
    print("【4/5】五维度摘句提取 + 后处理...")
    cache = json.load(open(config.CACHE_PATH, encoding='utf-8'))
    dim_data, stats, work_only = pipeline.run_pipeline(
        cache, report,
        apply_fund_filter=True,
        apply_cross_dedup=True,
    )
    print(f"  摘句总计: {stats['总条数']}")
    for dim, count in stats['各维度'].items():
        print(f"    {dim}: {count}")
    print(f"  无摘句文章: {stats['无摘句文章']} 篇\n")

    # ========== 阶段5：生成看板 HTML ==========
    print("【5/5】生成看板 HTML...")
    os.makedirs(config.OUTPUT_DIR, exist_ok=True)
    dashboard_gen.generate_dashboard(
        dim_data, stats,
        os.path.join(config.OUTPUT_DIR, 'dashboard.html'))
    dashboard_gen.generate_index(
        dim_data, stats,
        os.path.join(config.OUTPUT_DIR, 'index.html'))

    # ========== 汇总 ==========
    print(f"\n{'='*60}")
    print(f"更新完成！")
    print(f"  文章: {stats['保留文章']} 篇保留")
    print(f"  摘句: {stats['总条数']} 条（五维度合计）")
    print(f"  输出: {config.OUTPUT_DIR}/")
    print(f"{'='*60}")


if __name__ == '__main__':
    main()
