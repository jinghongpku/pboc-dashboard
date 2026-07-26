#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
run_full.py — 全量抓取 + 流水线筛选 + 明细报告
记录每篇文章在三个筛选阶段的去留与原因，输出 pipeline_report.json
"""

import json
import re
import os
import sys
from collections import Counter

_CODE_DIR = os.path.dirname(os.path.abspath(__file__))
if _CODE_DIR not in sys.path:
    sys.path.insert(0, _CODE_DIR)

import config
import crawler
import extractor
import dashboard
import review

START_DATE = config.START_DATE
CACHE = config.CACHE_PATH
OUT_DIR = config.OUTPUT_DIR
REPORT_PATH = config.REPORT_PATH

os.makedirs(OUT_DIR, exist_ok=True)


def include_reason(article):
    """与 extractor.should_include 完全一致的规则，但返回命中的原因"""
    title = article.get('title', '')
    tag = article.get('tag', '')
    if tag == '金融统计数据':
        if '托管余额' in title:
            return '纯数据公告：债券市场托管余额'
        if re.search(r'^(\d+月末|[\d\uff10-\uff19]+月[末底])[^。]{0,30}?(存量|余额)',
                     title):
            return '纯数据公告：存量/余额统计'
    if '一图看懂' in title or '一图读懂' in title:
        return '纯图表文章（一图看懂/一图读懂）'
    if any(k in title for k in ['法律修订', '金融稳定法', '中央银行法', '制度建设']):
        return '法律修订/制度建设类，与货币政策操作无关'
    # 央行领导署名表态例外（2026-07-22 新增，与 extractor.should_include 同步）
    leader_stmt = extractor.is_leader_statement(title, article.get('title_page'))
    if '双支柱' in title and not leader_stmt:
        return '双支柱主题文章'
    if '宏观审慎管理' in title and '利率风险' not in title and '杠杆' not in title \
            and not leader_stmt:
        return '宏观审慎管理类（非债市利率风险相关）'
    if any(k in title for k in ['团拜会', '致辞', '新年', '新春']):
        return '团拜会/致辞/节日类文章'
    return None


def main():
    import argparse
    parser = argparse.ArgumentParser(description='全量抓取+筛选+看板生成')
    parser.add_argument('--refresh', action='store_true',
                        help='忽略缓存全量重爬（默认增量更新）')
    args = parser.parse_args()

    report = {'start_date': START_DATE, 'kept': [], 'removed': []}

    # ========== 阶段0：全量爬取 ==========
    articles = crawler.crawl(
        cache_path=CACHE,
        start_date=START_DATE,
        refresh=args.refresh,
        max_pages=2000,
    )
    report['total_crawled'] = len(articles)
    print(f"\n{'='*60}\n爬取完成: {len(articles)} 篇目标作者文章\n{'='*60}")

    # ========== 阶段1：标题分类 ==========
    VALID_TAGS = {'流动性投放', '利率政策', '国债买卖', '金融统计数据',
                  '货币政策例会', '货币政策/宏观调控', '宏观点评'}
    for a in articles:
        tag, include = extractor.classify_article(a['title'], a.get('title_page'))
        # 兜底：标题分类失败时采用CSV历史标签（旧管线已审核的标签）
        if (not tag or not include) and a.get('tag_csv') in VALID_TAGS:
            tag, include = a['tag_csv'], True
        a['tag'] = tag or ''
        a['include'] = include
        a['clean_title'] = extractor.display_title(a)

    candidates = []
    for a in articles:
        if a['include'] and a['tag']:
            candidates.append(a)
        else:
            report['removed'].append({
                'date': a['date'], 'title': a['title'], 'author': a['author'],
                'stage': '①标题分类',
                'reason': '标题不命中六大类别，或命中排除关键词（非货币政策操作类内容）',
            })
    print(f"阶段1 标题分类: 保留 {len(candidates)} / 剔除 {len(articles)-len(candidates)}")

    # ========== 阶段2：排除规则 ==========
    passed = []
    for a in candidates:
        reason = include_reason(a)
        if reason:
            report['removed'].append({
                'date': a['date'], 'title': a['title'], 'author': a['author'],
                'tag': a['tag'], 'stage': '②排除规则', 'reason': reason,
            })
        else:
            passed.append(a)
    print(f"阶段2 排除规则: 保留 {len(passed)} / 剔除 {len(candidates)-len(passed)}")

    # ========== 阶段3：五维度观点提取 ==========
    for a in passed:
        a.update(extractor.extract_core_view(a['content'], a['title'], a['tag'], a.get('title_page')))

    final = []
    for a in passed:
        dims = {d: a.get(d, ['/']) for d in dashboard.DIMS}
        has_content = any(v != ['/'] for v in dims.values())
        # 重大一次性政策公告例外（2026-07-21 定稿，2026-07-22 改投双维度）：
        # 国债买卖类含"暂停/恢复/决定/启动/首次"的标题，即使无观点句，
        # 也将公告事实句同时放入国债买卖（句子级维度）和债券市场态度（看板兼容）
        # （日常例行操作公告如MLF月报仍按规则剔除）
        if not has_content and a.get('tag') == '国债买卖' \
                and re.search(r'暂停|恢复|决定|启动|首次', a.get('title', '')):
            for s in re.split(r'(?<=[。！？])', a.get('content', '')):
                s = s.strip()
                if 20 <= len(s) <= 200 and re.search(r'人民银行|央行', s) \
                        and re.search(r'国债|债券', s):
                    a['债券市场态度'] = [s]
                    a['国债买卖'] = [s]
                    dims['债券市场态度'] = [s]
                    has_content = True
                    break
        if has_content:
            final.append(a)
            report['kept'].append({
                'date': a['date'], 'title': a['title'], 'author': a['author'],
                'tag': a['tag'],
                'dims': {d: len([x for x in v if x != '/']) for d, v in dims.items()},
            })
        else:
            skipped = extractor.is_skip_article(a['content'], a['title'], a['tag'])
            reason = ('叙事/调研/法律/分行类文章，主动留空'
                      if skipped else '正文未提取到有效观点句')
            report['removed'].append({
                'date': a['date'], 'title': a['title'], 'author': a['author'],
                'tag': a['tag'], 'stage': '③观点提取', 'reason': reason,
            })
    print(f"阶段3 观点提取: 保留 {len(final)} / 剔除 {len(passed)-len(final)}")

    # ========== 阶段4：近似文章去重（2026-07-22 用户规则1）==========
    # 标题高度相似且发布日期接近（≤10天）的文章保留较早一篇
    import difflib
    from datetime import datetime

    def _norm_t(t):
        return re.sub(r'[！!？?：:，,。、"“”‘’（）()《》\s—\-··]', '', t or '')

    def _sim(a, b):
        ta, tb = _norm_t(a), _norm_t(b)
        if not ta or not tb:
            return 0.0
        if ta in tb or tb in ta:
            return min(len(ta), len(tb)) / max(len(ta), len(tb)) if max(len(ta), len(tb)) > 12 else 1.0
        return difflib.SequenceMatcher(None, ta, tb).ratio()

    def _is_dup(ta_raw, tb_raw, dd):
        """近似判定（含防误杀护栏）：
        金额不同的操作公告、不同月份的月度观察、不同主题的会议、
        领导署名与非领导署名、长公共前缀+不同后缀，均不算重复"""
        ta, tb = _norm_t(ta_raw), _norm_t(tb_raw)
        if not ta or not tb:
            return False
        # 护栏1：金额不同 → 两次不同的操作（如9000亿 vs 11000亿买断式逆回购）
        ama = set(re.findall(r'(\d+(?:\.\d+)?)\s*(?:万)?亿', ta))
        amb = set(re.findall(r'(\d+(?:\.\d+)?)\s*(?:万)?亿', tb))
        if ama and amb and ama != amb:
            return False
        # 护栏2：月度观察系列月份不同
        if '每月财经观察' in ta and '每月财经观察' in tb:
            ma = re.search(r'(\d{1,2})月财经金融热点', ta)
            mb = re.search(r'(\d{1,2})月财经金融热点', tb)
            if ma and mb and ma.group(1) != mb.group(1):
                return False
        # 护栏3：会议主题不同（信贷市场工作会议 vs 宏观审慎工作会议）
        tha = re.search(r'召开(.{2,12}?)(工作会议|例会)', ta)
        thb = re.search(r'召开(.{2,12}?)(工作会议|例会)', tb)
        if tha and thb and tha.group(1) != thb.group(1):
            return False
        # 护栏4：领导署名文章与非署名文章不去重
        la = bool(extractor.LEADER_RE.match(ta_raw))
        lb = bool(extractor.LEADER_RE.match(tb_raw))
        if la != lb:
            return False
        th = 0.55 if dd > 0 else 0.7  # 同日文章要求更高相似度
        if _sim(ta_raw, tb_raw) < th:
            return False
        # 护栏5：长公共前缀+各自不同后缀 → 同系列不同主题
        if dd >= 1:
            pre = os.path.commonprefix([ta, tb])
            if len(pre) >= 8:
                sa, sb = ta[len(pre):], tb[len(pre):]
                if len(sa) >= 4 and len(sb) >= 4 and _sim(sa, sb) < 0.5:
                    return False
        return True

    final_sorted = sorted(final, key=lambda a: a.get('date', ''))
    deduped = []
    for a in final_sorted:
        ta = a.get('title_page') or a.get('title', '')
        dup_of = None
        for b in deduped:
            try:
                dd = abs((datetime.strptime(a['date'], '%Y%m%d') -
                          datetime.strptime(b['date'], '%Y%m%d')).days)
            except Exception:
                dd = 999
            if dd > 10:
                continue
            if _is_dup(ta, b.get('title_page') or b.get('title', ''), dd):
                dup_of = b
                break
        if dup_of is not None:
            report['removed'].append({
                'date': a['date'], 'title': a['title'], 'author': a['author'],
                'tag': a['tag'], 'stage': '④近似去重',
                'reason': f"与 {dup_of['date']}《"
                          f"{(dup_of.get('title_page') or dup_of.get('title', ''))[:30]}》"
                          f"标题高度相近、日期接近，保留较早一篇",
            })
        else:
            deduped.append(a)
    print(f"阶段4 近似去重: 保留 {len(deduped)} / 剔除 {len(final)-len(deduped)}")
    final = deduped
    # kept报告与去重后final对齐
    _kept_keys_final = {(a['title'], a['date']) for a in final}
    report['kept'] = [k for k in report['kept']
                      if (k['title'], k['date']) in _kept_keys_final]

    # ========== 生成看板与审阅页 ==========
    dashboard_data = []
    for a in final:
        a['date_fmt'] = f"{a['date'][:4]}-{a['date'][4:6]}-{a['date'][6:8]}"
        dashboard_data.append({
            'date': a['date_fmt'], 'title': a['title'],
            'clean_title': a.get('clean_title', a['title']),
            'link': a['link'], 'author': a['author'], 'tag': a['tag'],
            **{dim: ' / '.join(a.get(dim, ['/'])) for dim in dashboard.DIMS},
        })
    dashboard.generate_dashboard(dashboard_data, os.path.join(OUT_DIR, 'index.html'))

    review_data = review.build_review_data(final)
    review.generate_review_page(review_data, os.path.join(OUT_DIR, 'policy_review.html'))

    # ========== 汇总 ==========
    report['summary'] = {
        'total_crawled': len(articles),
        'after_classify': len(candidates),
        'after_exclude': len(passed),
        'final_kept': len(final),
        'kept_by_tag': dict(Counter(a['tag'] for a in final)),
        'removed_by_stage': dict(Counter(r['stage'] for r in report['removed'])),
        'removed_by_reason': dict(Counter(r['reason'] for r in report['removed'])),
    }
    with open(REPORT_PATH, 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print(f"\n{'='*60}")
    print(f"全部完成: 爬取 {len(articles)} → 看板 {len(final)} 篇")
    print(f"按标签: {report['summary']['kept_by_tag']}")
    print(f"剔除分布: {report['summary']['removed_by_stage']}")
    print(f"报告已保存: {REPORT_PATH}")


if __name__ == '__main__':
    main()
