#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
daily_update.py — 每日增量更新脚本

两种模式：
  --crawl    增量爬取新文章 + 重新提取 + 生成看板
  （默认）   仅从已有缓存重新提取 + 生成看板（不爬取）

用法：
    python daily_update.py           # 仅重新提取（不爬取）
    python daily_update.py --crawl   # 增量爬取 + 重新提取
    python daily_update.py --full    # 全量重爬 + 重新提取
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
import extractor
import pipeline
import dashboard_gen
from dashboard import DIMS


def main():
    parser = argparse.ArgumentParser(description='每日增量更新')
    parser.add_argument('--crawl', action='store_true',
                        help='增量爬取新文章后再提取')
    parser.add_argument('--full', action='store_true',
                        help='全量重爬后提取')
    args = parser.parse_args()

    print(f"{'='*60}")
    print(f"央行货币政策看板 · 每日更新")
    print(f"日期: {date.today().isoformat()}")
    print(f"模式: {'全量重爬' if args.full else '增量爬取' if args.crawl else '仅重新提取（不爬取）'}")
    print(f"{'='*60}\n")

    # ========== 加载缓存 ==========
    if not os.path.exists(config.CACHE_PATH):
        print(f"错误: 缓存文件不存在: {config.CACHE_PATH}")
        sys.exit(1)

    cache = json.load(open(config.CACHE_PATH, encoding='utf-8'))
    print(f"缓存文章: {len(cache)} 篇")

    # ========== 可选：爬取新文章 ==========
    if args.crawl or args.full:
        import crawler
        print("\n【爬取】增量更新新文章...")
        crawled = crawler.crawl(
            cache_path=config.CACHE_PATH,
            start_date=config.START_DATE,
            refresh=args.full,
            max_pages=2000,
        )
        new_count = len(crawled)
        print(f"  爬取结果: {new_count} 篇可用文章")

        # 安全保护：如果爬取返回 0 篇但缓存有数据，不覆盖
        if new_count == 0 and len(cache) > 0:
            print("  ⚠ 爬取返回 0 篇，但缓存有 %d 篇。可能是网络问题。" % len(cache))
            print("  继续使用已有缓存数据生成看板。")
        else:
            # 重新加载更新后的缓存
            cache = json.load(open(config.CACHE_PATH, encoding='utf-8'))

    # ========== 加载或重建报告 ==========
    report = None
    if os.path.exists(config.REPORT_PATH):
        report = json.load(open(config.REPORT_PATH, encoding='utf-8'))
        kept_count = len(report.get('kept', []))
        print(f"报告: {kept_count} 篇保留文章")

        # 安全保护：如果报告为空但缓存有数据，重建报告
        if kept_count == 0 and len(cache) > 0:
            print("  ⚠ 报告为空，从缓存重建...")
            report = None

    if report is None:
        print("\n【重建报告】从缓存重建 pipeline_report...")
        report = _rebuild_report(cache)
        _save_report(report)
        print(f"  重建完成: {len(report['kept'])} 篇保留\n")

    # ========== 五维度提取 + 后处理 ==========
    print("【提取】五维度摘句提取 + 后处理...")
    dim_data, stats, work_only = pipeline.run_pipeline(
        cache, report,
        apply_fund_filter=True,
        apply_cross_dedup=True,
    )
    print(f"  摘句总计: {stats['总条数']}")
    for dim, count in stats['各维度'].items():
        print(f"    {dim}: {count}")
    print(f"  无摘句文章: {stats['无摘句文章']} 篇\n")

    # ========== 生成看板 HTML ==========
    print("【生成】看板 HTML...")
    os.makedirs(config.OUTPUT_DIR, exist_ok=True)
    dashboard_gen.generate_dashboard(
        dim_data, stats,
        os.path.join(config.OUTPUT_DIR, 'dashboard.html'))
    dashboard_gen.generate_index(
        dim_data, stats,
        os.path.join(config.OUTPUT_DIR, 'index.html'))

    # ========== 保存更新后的报告 ==========
    _save_report(report)

    # ========== 汇总 ==========
    print(f"\n{'='*60}")
    print(f"更新完成！")
    print(f"  文章: {stats['保留文章']} 篇保留")
    print(f"  摘句: {stats['总条数']} 条（五维度合计）")
    print(f"  输出: {config.OUTPUT_DIR}/")
    print(f"{'='*60}")


def _rebuild_report(cache):
    """从缓存重建 pipeline_report（分类→排除→提取→去重）"""
    # 构建全量候选列表
    all_keys = [{'title': a['title'], 'date': a['date']} for a in cache if a.get('content')]
    fake_report = {'kept': all_keys, 'removed': []}
    final, removed = pipeline.run_classification(cache, fake_report)

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
    report['total_crawled'] = len(cache)
    report['summary'] = {
        'total_crawled': len(cache),
        'final_kept': len(final),
        'kept_by_tag': dict(Counter(a.get('tag', '') for a in final)),
        'removed_by_stage': dict(Counter(r.get('stage', '') for r in removed)),
    }
    return report


def _save_report(report):
    """保存 pipeline_report.json"""
    with open(config.REPORT_PATH, 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"  报告已保存: {config.REPORT_PATH}")


if __name__ == '__main__':
    main()
