#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pipeline.py — 公共数据处理流水线
统一 run_full.py / gen_audit.py / daily_update.py 的数据逻辑

职责：
1. 加载缓存 + 报告
2. 对保留文章重新提取五维度摘句
3. 后处理：资金态度门槛、跨维度去重、工作重点并轨（可选）
4. 输出结构化的维度数据
"""

import json
import re
import os
import sys

# 确保本目录在 sys.path 中（兼容直接运行和模块导入）
_CODE_DIR = os.path.dirname(os.path.abspath(__file__))
if _CODE_DIR not in sys.path:
    sys.path.insert(0, _CODE_DIR)

import config
import extractor


# ============================================================
# 用户五维度 → 系统维度名映射
# ============================================================
DIM_MAP = [
    ('经济形势', '经济形势判断'),
    ('货币政策取向', '货币政策取向'),
    ('国债买卖', '国债买卖'),
    ('资金利率态度', '资金态度'),
    ('债券市场态度', '债券市场态度'),
]

# 维度配色 (背景色, 前景色)
DIM_COLORS = {
    '经济形势': ('#e8f5e9', '#2e7d32'),
    '货币政策取向': ('#e3f2fd', '#1565c0'),
    '国债买卖': ('#fff3e0', '#e65100'),
    '资金利率态度': ('#f3e5f5', '#6a1b9a'),
    '债券市场态度': ('#fce4ec', '#ad1457'),
}


# ============================================================
# 资金态度门槛：只保留"有明确含义"的资金面信息
# （移植自交接文档 §5 + §6 第四轮规则）
# ============================================================
def is_fund_meaningful(text):
    """
    判断一条资金态度摘句是否"有明确含义"：
    - DR001/DR007 具体数值与变动
    - 与政策利率的位置关系（围绕/偏离/上破/下破）
    - 明确的松紧判断
    排除：
    - 纯加量缩量续作、净投放净回笼xx亿、到期量
    - MLF中标利率、操作量为零
    - 纯市场状态罗列
    - 操作归因尾巴
    - 适度宽松类取向表述
    """
    tl = text.lower()

    # === 强信号（直接通过）===
    strong_signals = [
        r'dr00[17]\s*[为至在报升破降达]',
        r'dr00[17]\s*(?:同比|环比|较|比)',
        r'隔夜利率\s*[为至在报升破降达]',
        r'(围绕|偏离|上破|下破|突破|跌破).*?(政策利率|利率走廊)',
        r'(政策利率|利率走廊).*?(围绕|偏离|上破|下破|突破|跌破)',
        r'(资金面|流动性)\s*(?:显著|明显|大幅|持续)\s*(?:收紧|放松|宽松|紧张|收紧)',
        r'(资金面|流动性)\s*(?:偏紧|偏松|收紧|转紧|转松)',
        r'(利率|资金利率)\s*(?:回升|上行|下行|走低|走高)',
        r'资金利率\s*(?:高于|低于|接近|偏离)',
    ]
    if any(re.search(p, tl) for p in strong_signals):
        return True

    # === 排除信号（直接拒绝）===
    exclude_patterns = [
        # 纯操作量叙述
        r'(开展|进行|完成)\s*\d+\s*亿元',
        r'净(投放|回笼)\s*\d+',
        r'到期\s*\d+\s*亿',
        r'(等量|超额|缩量)\s*(续作|续做)',
        r'操作量\s*(?:为|约|达)\s*\d',
        r'中标利率\s*(?:为|保持|不变)',
        # 纯市场状态罗列
        r'(保持|维持|总体|整体)\s*(平稳|充裕|合理|充裕)',
        r'银行体系流动性\s*(合理|充裕|平稳)',
        # 适度宽松等取向表述
        r'(适度宽松|支持性货币政策|稳健的货币政策)',
        # 操作归因尾巴
        r'(适度调减|公开市场操作|流动性安排).*?(影响下|作用下|背景下).*(?:回升|上行|下行)',
        # 企业案例
        r'(企业|公司).*(?:融资|贷款|利率)',
    ]
    if any(re.search(p, tl) for p in exclude_patterns):
        return False

    # === 中等信号（满足任一即通过）===
    medium_signals = [
        r'dr00[17]',
        r'隔夜(?:利率|逆回购)',
        r'(资金面|资金利率|市场利率|短端利率)',
        r'(流动性)\s*(?:紧张|收紧|宽松|充裕)',
        r'同业存单.*?(利率|收益率)',
        r'利率走廊',
        r'(呵护|维护|保持).*(流动性|资金)',
    ]
    if any(re.search(p, tl) for p in medium_signals):
        return True

    # 无明确信号，默认拒绝
    return False


# ============================================================
# 核心流水线
# ============================================================
def load_data(cache_path=None, report_path=None):
    """加载缓存和报告，返回 (cache, report)"""
    cache_path = cache_path or config.CACHE_PATH
    report_path = report_path or config.REPORT_PATH
    with open(cache_path, encoding='utf-8') as f:
        cache = json.load(f)
    with open(report_path, encoding='utf-8') as f:
        report = json.load(f)
    return cache, report


def run_pipeline(cache, report, apply_fund_filter=True, apply_cross_dedup=True):
    """
    对全部保留文章重新提取五维度摘句

    参数:
        cache: 文章缓存列表
        report: 流水线报告
        apply_fund_filter: 是否应用资金态度门槛过滤
        apply_cross_dedup: 是否应用跨维度去重（资金态度让位）

    返回:
        dim_data: {用户维度名: [(摘句, 文章信息), ...]}
        stats: {'总条数': int, '各维度': {维度名: 条数}}
    """
    kept_keys = {(k['title'], k['date']) for k in report['kept']}

    # 初始化维度数据
    dim_data = {u: [] for u, _ in DIM_MAP}
    work_only_articles = []

    for a in cache:
        if (a.get('title'), a.get('date')) not in kept_keys:
            continue

        res = extractor.extract_core_view(
            a.get('content', ''), a.get('title', ''),
            a.get('tag', ''), a.get('title_page'))

        info = {
            'date': _fmt_date(a.get('date', '')),
            'title': a.get('title_page') or extractor.clean_title(a.get('title', '')),
            'link': a.get('link', ''),
            'tag': a.get('tag', ''),
        }

        has_any = False
        seen = set()
        for udim, sdim in DIM_MAP:
            for q in res.get(sdim, []):
                if q == '/' or (udim, q) in seen:
                    continue
                seen.add((udim, q))
                dim_data[udim].append((q, info))
                has_any = True
        if not has_any:
            work_only_articles.append(info)

    # === 后处理1：资金态度门槛 ===
    if apply_fund_filter:
        before = len(dim_data['资金利率态度'])
        dim_data['资金利率态度'] = [
            (q, info) for q, info in dim_data['资金利率态度']
            if is_fund_meaningful(q)
        ]
        filtered = before - len(dim_data['资金利率态度'])
        if filtered:
            print(f"  资金态度门槛过滤: {before} → {len(dim_data['资金利率态度'])}（过滤 {filtered} 条）")

    # === 后处理2：跨维度去重（资金态度优先级最低）===
    if apply_cross_dedup:
        other_quotes = set()
        for udim, _ in DIM_MAP:
            if udim != '资金利率态度':
                for q, _ in dim_data[udim]:
                    other_quotes.add(_norm(q))

        before = len(dim_data['资金利率态度'])
        dim_data['资金利率态度'] = [
            (q, info) for q, info in dim_data['资金利率态度']
            if _norm(q) not in other_quotes
        ]
        deduped = before - len(dim_data['资金利率态度'])
        if deduped:
            print(f"  跨维度去重: 资金态度去除 {deduped} 条")

    # 按日期倒序排列
    for u in dim_data:
        dim_data[u].sort(key=lambda x: x[1]['date'], reverse=True)

    total = sum(len(v) for v in dim_data.values())
    stats = {
        '总条数': total,
        '保留文章': len(kept_keys),
        '无摘句文章': len(work_only_articles),
        '各维度': {u: len(dim_data[u]) for u, _ in DIM_MAP},
    }

    return dim_data, stats, work_only_articles


def run_classification(cache, report):
    """
    对保留文章做标题分类 + 排除规则 + 近似去重
    （与 run_full.py 阶段1-4 对齐，用于每日更新判断新文章）

    返回: (final_articles, removed_articles)
    """
    import difflib
    from datetime import datetime

    kept_keys = {(k['title'], k['date']) for k in report['kept']}
    articles = [a for a in cache if (a.get('title'), a.get('date')) in kept_keys]

    VALID_TAGS = {'流动性投放', '利率政策', '国债买卖', '金融统计数据',
                  '货币政策例会', '货币政策/宏观调控', '宏观点评'}

    # 阶段1：标题分类
    for a in articles:
        tag, include = extractor.classify_article(a.get('title', ''), a.get('title_page'))
        if (not tag or not include) and a.get('tag_csv') in VALID_TAGS:
            tag, include = a['tag_csv'], True
        a['tag'] = tag or ''
        a['include'] = include
        a['clean_title'] = extractor.display_title(a)

    candidates = [a for a in articles if a['include'] and a['tag']]
    removed_classify = [a for a in articles if not (a['include'] and a['tag'])]

    # 阶段2：排除规则
    passed = []
    removed_exclude = []
    for a in candidates:
        reason = _include_reason(a)
        if reason:
            removed_exclude.append({**a, 'reason': reason, 'stage': '②排除规则'})
        else:
            passed.append(a)

    # 阶段3：五维度提取
    for a in passed:
        a.update(extractor.extract_core_view(
            a.get('content', ''), a.get('title', ''),
            a.get('tag', ''), a.get('title_page')))

    from dashboard import DIMS
    final = []
    removed_extract = []
    for a in passed:
        dims = {d: a.get(d, ['/']) for d in DIMS}
        has_content = any(v != ['/'] for v in dims.values())
        # 国债买卖重大公告保底
        if not has_content and a.get('tag') == '国债买卖' \
                and re.search(r'暂停|恢复|决定|启动|首次', a.get('title', '')):
            for s in re.split(r'(?<=[。！？])', a.get('content', '')):
                s = s.strip()
                if 20 <= len(s) <= 200 and re.search(r'人民银行|央行', s) \
                        and re.search(r'国债|债券', s):
                    a['债券市场态度'] = [s]
                    a['国债买卖'] = [s]
                    has_content = True
                    break
        if has_content:
            final.append(a)
        else:
            skipped = extractor.is_skip_article(a.get('content', ''), a.get('title', ''), a.get('tag', ''))
            reason = ('叙事/调研/法律/分行类文章' if skipped else '未提取到有效观点句')
            removed_extract.append({**a, 'reason': reason, 'stage': '③观点提取'})

    # 阶段4：近似去重
    deduped, removed_dedup = _dedup_articles(final)

    removed = (
        [{'date': a.get('date', ''), 'title': a.get('title', ''), 'author': a.get('author', ''),
          'stage': '①标题分类', 'reason': '标题不命中六大类别或命中排除关键词'}
         for a in removed_classify]
        + removed_exclude
        + removed_extract
        + removed_dedup
    )

    return deduped, removed


# ============================================================
# 内部工具函数
# ============================================================
def _fmt_date(d):
    """YYYYMMDD → YYYY-MM-DD"""
    if len(d) == 8:
        return f"{d[:4]}-{d[4:6]}-{d[6:8]}"
    return d


def _norm(text):
    """文本规范化（用于去重比较）"""
    return re.sub(r'\s+', '', text or '')


def _include_reason(article):
    """排除规则判定（与 run_full.py / extractor.should_include 对齐）"""
    title = article.get('title', '')
    tag = article.get('tag', '')
    if tag == '金融统计数据':
        if '托管余额' in title:
            return '纯数据公告：债券市场托管余额'
        if re.search(r'^(\d+月末|[\d\uff10-\uff19]+月[末底])[^。]{0,30}?(存量|余额)', title):
            return '纯数据公告：存量/余额统计'
    if '一图看懂' in title or '一图读懂' in title:
        return '纯图表文章'
    if any(k in title for k in ['法律修订', '金融稳定法', '中央银行法', '制度建设']):
        return '法律修订/制度建设类'
    leader_stmt = extractor.is_leader_statement(title, article.get('title_page'))
    if '双支柱' in title and not leader_stmt:
        return '双支柱主题文章'
    if '宏观审慎管理' in title and '利率风险' not in title \
            and '杠杆' not in title and not leader_stmt:
        return '宏观审慎管理类'
    if any(k in title for k in ['团拜会', '致辞', '新年', '新春']):
        return '团拜会/致辞/节日类'
    return None


def _dedup_articles(final):
    """近似文章去重（与 run_full.py 阶段4 对齐）"""
    import difflib
    from datetime import datetime

    def _norm_t(t):
        return re.sub(r'[！!？?：:，,。、""\'\'（）()《》\s—\-··]', '', t or '')

    def _sim(a, b):
        ta, tb = _norm_t(a), _norm_t(b)
        if not ta or not tb:
            return 0.0
        if ta in tb or tb in ta:
            return min(len(ta), len(tb)) / max(len(ta), len(tb)) if max(len(ta), len(tb)) > 12 else 1.0
        return difflib.SequenceMatcher(None, ta, tb).ratio()

    def _is_dup(ta_raw, tb_raw, dd):
        ta, tb = _norm_t(ta_raw), _norm_t(tb_raw)
        if not ta or not tb:
            return False
        ama = set(re.findall(r'(\d+(?:\.\d+)?)\s*(?:万)?亿', ta))
        amb = set(re.findall(r'(\d+(?:\.\d+)?)\s*(?:万)?亿', tb))
        if ama and amb and ama != amb:
            return False
        if '每月财经观察' in ta and '每月财经观察' in tb:
            ma = re.search(r'(\d{1,2})月财经金融热点', ta)
            mb = re.search(r'(\d{1,2})月财经金融热点', tb)
            if ma and mb and ma.group(1) != mb.group(1):
                return False
        tha = re.search(r'召开(.{2,12}?)(工作会议|例会)', ta)
        thb = re.search(r'召开(.{2,12}?)(工作会议|例会)', tb)
        if tha and thb and tha.group(1) != thb.group(1):
            return False
        la = bool(extractor.LEADER_RE.match(ta_raw))
        lb = bool(extractor.LEADER_RE.match(tb_raw))
        if la != lb:
            return False
        th = 0.55 if dd > 0 else 0.7
        if _sim(ta_raw, tb_raw) < th:
            return False
        if dd >= 1:
            pre = os.path.commonprefix([ta, tb])
            if len(pre) >= 8:
                sa, sb = ta[len(pre):], tb[len(pre):]
                if len(sa) >= 4 and len(sb) >= 4 and _sim(sa, sb) < 0.5:
                    return False
        return True

    final_sorted = sorted(final, key=lambda a: a.get('date', ''))
    deduped = []
    removed = []
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
            removed.append({
                'date': a.get('date', ''), 'title': a.get('title', ''),
                'author': a.get('author', ''), 'stage': '④近似去重',
                'reason': f"与 {dup_of['date']}《{(dup_of.get('title_page') or dup_of.get('title', ''))[:30]}》高度相近",
            })
        else:
            deduped.append(a)

    return deduped, removed


if __name__ == '__main__':
    print("加载数据...")
    cache, report = load_data()
    print(f"缓存 {len(cache)} 篇，保留 {len(report['kept'])} 篇")

    print("\n运行五维度提取流水线...")
    dim_data, stats, _ = run_pipeline(cache, report)

    print(f"\n结果: 共 {stats['总条数']} 条摘句")
    for dim, count in stats['各维度'].items():
        print(f"  {dim}: {count}")
