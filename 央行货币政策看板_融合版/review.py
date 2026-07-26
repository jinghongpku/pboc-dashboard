#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
review.py — "货币政策基调与方向"专项审阅页
从看板文章中筛出基调/方向类摘句，生成逐条校对页面

融合版修复：
1. 删除 extract_policy_tone_direction 末尾的二次过滤——原正则交替分支中混入
   字面空格（如 '今年以来 | ...'）导致过滤失效，且这些规则已正确包含在
   is_tone_direction 的 veto 列表中，属于重复逻辑
2. 修复审阅页 CSS 中标签配色类名被转义破坏的问题，改为内联样式
3. 数据源从 CSV 切换为爬虫流程，日期/链接直接取文章字段
"""

import re
from html import escape

from extractor import extract_core_view
from dashboard import TAG_COLORS


def is_tone_direction(text):
    """
    判断一个句子是否属于"货币政策基调与方向"
    基调：适度宽松/支持性/稳健/以我为主/定力/观察期
    方向：逆周期跨周期/配合财政/熨平波动/扩大内需/稳增长防风险/内外均衡/力度节奏
    """
    tl = text.lower()

    # === 否决项：不属于基调与方向 ===
    veto = [
        # LPR报价分析
        r'lpr.*?报价', r'报价行.*?加点', r'报价.*?不动',
        r'净息差.*?\d', r'加点.*?动力',
        # LPR事件描述（纯事件，不含基调判断）
        r'lpr.*?按兵不动.*?符合预期',
        r'lpr.*?按兵不动.*?连续.*?月.*?不变',
        r'lpr.*?按兵不动.*?背后的原因',
        r'lpr.*?按兵不动.*?定价基础',
        r'lpr.*?按兵不动.*?可以更好地配合',
        r'报价降幅.*?带动.*?贷款利率.*?下降',
        # 房贷/存量利率
        r'存量.*?房贷.*?利率', r'房贷利率.*?下降', r'房贷.*?平均',
        r'借款人.*?利息', r'惠及.*?户.*?家庭',
        # 存款/利率市场化细节
        r'定期存款.*?利率', r'存款.*?创新', r'靠档计息',
        r'储蓄管理.*?条例', r'贷款.*?定价方式',
        r'存款.*?提前.*?支取', r'期限利差',
        # 市场描述
        r'住房租赁', r'租售比', r'房地产市场.*?定价',
        r'资管产品.*?存款.*?此消彼长',
        r'直接融资.*?非银.*?加快',
        r'm2.*?社融.*?增速.*?保持.*?\d',
        r'企业.*?融资.*?成本.*?利息',
        r'融资主体.*?信用等级',
        # 企业案例
        r'车间|流水线|生产线|订单',
        r'研发周期|投入成本高',
        r'购房.*?自住.*?刚需',
        # 其他非基调
        r'网络.*?信息安全',
        r'统一大市场.*?低价.*?竞争',
        r'外贸.*?经营风险',
        r'大型银行.*?主力军.*?中小银行.*?主责主业',
        r'非银同业.*?存款.*?定价.*?规范',
        r'手工补息.*?高息揽储',
        r'利率自律机制.*?工作.*?成效',
        r'理财.*?资管.*?丰富',
        r'股市.*?情绪.*?修复',
        r'降息并非.*?关键因素',
        r'暂停降息',
        r'贸易战.*?直接冲击',
        r'新科技.*?新产业.*?农产品',
        r'金融改革.*?宝贵经验',
        r'博眼球|骗流量',
        r'江西.*?试点',
        r'银行.*?债券.*?价格发现',
        r'银行.*?金融体系.*?结构.*?货币创造',
        r'存贷款利率.*?全面放开.*?形得成',
        r'居民存款.*?增速.*?回落',
        r'四大行.*?同业负债.*?占比',
        r'金融创新.*?直接融资.*?融资结构.*?深层次',
        r'利率调整.*?流程.*?熟练.*?稳妥',
        r'缓解.*?支出压力.*?消费信心',
        r'贷款利息.*?明文标注',
        # 操作细节
        r'买断式.*?逆回购.*?缩量',
        r'mlf.*?加量.*?续作.*?亿元',
        r'公开市场.*?操作量.*?适度调减',
        # 操作框架细节（非方向判断）
        r'基准利率地位.*?淡化.*?mlf',
        r'买断式逆回购.*?跨期.*?调节.*?能力',
        r'覆盖.*?3个月.*?6个月.*?跨期',
        # 具体产品/工具
        r'创业担保贷款',
        r'互换便利.*?回购增持',
        r'农业现代化.*?乡村',
        # 泛泛经济判断
        r'促进物价.*?回升.*?扩大.*?有效需求',
        r'住房贷款.*?消费贷款.*?利息.*?减轻',
        r'宏观经济景气度.*?上行.*?楼市.*?回暖',
        r'gdp.*?增速.*?落在.*?目标',
        # === 用户新增规则 (2026-07-20) ===
        # 1. 记者提问句
        r'记者[：:].*?\?', r'记者.*?有何考虑', r'记者.*?下一步.*?考虑',
        r'^《.*?》记者[：:]', r'《.*?》记者.*?\?',
        # 2. 过去工作总结（保留展望/下一阶段，过滤"今年以来xxx""已经xxx"）
        r'^今年以来[，,]', r'^今年.*?以来[，,]', r'^上半年[，,]', r'^一季度[，,]',
        r'^过去.*?[，,]', r'^已.*?完成', r'^已.*?实现', r'^已.*?落地',
        # 3. 对财政政策的表述（非货币政策）
        r'^财政政策.*?要', r'^财政.*?将.*?加大', r'^财政.*?发力',
        # 4. 过于务虚的套话
        r'坚持以习近平.*?为指导', r'全面贯彻落实党的.*?精神',
        r'坚持稳中求进工作总基调', r'完整.*?准确.*?全面贯彻新发展理念',
        r'坚定不移走中国特色金融发展之路', r'推动金融高质量发展',
        r'金融强国建设', r'加快完善中央银行制度', r'进一步健全货币政策框架',
        r'深化金融改革.*?高水平对外开放',
    ]

    for v in veto:
        if re.search(v, tl):
            return False, 'veto'

    # === 命中项：基调 ===
    tone_keywords = [
        '适度宽松', '支持性', '支持性立场',
        '稳健的货币政策', '稳健偏宽松',
        '基调', '取向',
        '以我为主', '战略定力', '保持定力',
        '观察期', '按兵不动',
        '立场不变', '基调未变', '基调稳固',
        '释放.*?信号',
        '货币政策.*?立场',
        '延续.*?支持性',
        '支持性.*?货币政策',
    ]

    # === 命中项：方向 ===
    direction_keywords = [
        '逆周期', '跨周期',
        '财政.*?(协同|配合)', '货币财政.*?协同',
        '协同配合', '加强.*?协同',
        '熨平.*?波动', '平稳.*?波动',
        '扩大内需', '优化供给',
        '力度.*?节奏.*?时机',
        '总量.*?结构.*?双重功能',
        '稳增长.*?防风险',
        '内外.*?均衡', '内外部均衡',
        '前瞻性.*?安排',
        '稳增长.*?结构优化',
        '促进.*?经济.*?稳定增长',
        '物价.*?合理回升',
        '营造.*?货币金融环境',
        '创造.*?货币金融环境',
        '为.*?实体经济.*?创造',
        '更加.*?积极有为',
        '加大.*?调节.*?力度',
        '把握好.*?货币政策.*?实施',
        '兼顾.*?稳增长.*?防风险',
        '从短期稳增长.*?转向',
        '提升.*?效能',
        '增强.*?能力',
    ]

    has_tone = any(re.search(k, tl) for k in tone_keywords)
    has_direction = any(re.search(k, tl) for k in direction_keywords)

    if has_tone or has_direction:
        return True, 'tone' if has_tone and not has_direction else ('direction' if has_direction and not has_tone else 'both')

    return False, 'no_match'


def extract_policy_tone_direction(content, title, tag):
    """
    从文章中提取"货币政策基调与方向"相关摘句
    复用 extract_core_view 的引语提取逻辑，再用 is_tone_direction 筛选
    """
    views = extract_core_view(content, title, tag)
    if not views:
        return []

    all_items = []
    for dim, items in views.items():
        if not items or items == ['/']:
            continue
        all_items.extend(items)

    result = []
    seen = set()
    for item in all_items:
        is_td, _ = is_tone_direction(item)
        if is_td and item not in seen:
            seen.add(item)
            result.append(item)
    return result


def build_review_data(articles):
    """
    从文章列表构建审阅数据
    入参：已含 tag / clean_title / content / date_fmt 字段的文章列表
    """
    review_articles = []
    for a in articles:
        content = a.get('content', '')
        if not content or len(content) < 50:
            continue
        items = extract_policy_tone_direction(
            content, a.get('title', ''), a.get('tag', ''))
        if items:
            review_articles.append({
                'date': a.get('date_fmt', a.get('date', '')),
                'title': a.get('clean_title', a.get('title', '')),
                'link': a.get('link', ''),
                'tag': a.get('tag', ''),
                'items': items,
            })
    review_articles.sort(key=lambda x: x['date'], reverse=True)
    return review_articles


def _tag_style(tag):
    bg, fg = TAG_COLORS.get(tag, ('#f5f5f5', '#666666'))
    return (f'display:inline-block;padding:1px 6px;border-radius:3px;'
            f'font-size:11px;margin-left:8px;background:{bg};color:{fg};')


def generate_review_page(review_articles, output_path):
    """生成逐条审阅 HTML 页面"""
    import os
    total = sum(len(a['items']) for a in review_articles)

    parts = ['<!DOCTYPE html><html><head><meta charset="UTF-8">',
             '<title>货币政策基调与方向 - 审阅</title>',
             '''<style>
    body { font-family: "Microsoft YaHei", "PingFang SC", sans-serif; margin: 20px; background: #f5f5f5; }
    h1 { color: #333; }
    .stats { background: #fff; padding: 15px 20px; border-radius: 8px; margin-bottom: 20px; display: inline-block; }
    .article { background: #fff; margin-bottom: 12px; border-radius: 8px; overflow: hidden; border: 1px solid #e0e0e0; }
    .article-header { padding: 10px 15px; background: #f0f4f8; border-bottom: 1px solid #e0e0e0; cursor: pointer; }
    .article-header:hover { background: #e8eef5; }
    .article-title { font-weight: bold; color: #1a3a5c; font-size: 14px; }
    .article-title a { color: #1a3a5c; text-decoration: none; }
    .article-title a:hover { text-decoration: underline; }
    .article-meta { color: #888; font-size: 12px; margin-top: 3px; }
    .article-items { padding: 10px 15px; }
    .item { padding: 8px 12px; margin: 6px 0; background: #f9f9f9; border-left: 3px solid #4a90d9; border-radius: 0 4px 4px 0; font-size: 13px; line-height: 1.6; color: #333; }
    .item:hover { background: #f0f4f8; }
    .actions { margin-top: 6px; }
    .btn { display: inline-block; padding: 3px 10px; border-radius: 3px; cursor: pointer; font-size: 12px; margin-right: 5px; border: 1px solid #ccc; }
    .btn-ok { background: #4caf50; color: white; border-color: #4caf50; }
    .btn-problem { background: #f44336; color: white; border-color: #f44336; }
    .btn:hover { opacity: 0.85; }
    .item.problem { border-left-color: #f44336; background: #fff5f5; }
    .item.ok { border-left-color: #4caf50; background: #f1f8f1; }
    .hidden { display: none; }
    </style></head><body>''',
             '<h1>货币政策基调与方向 - 逐条审阅</h1>',
             f'<div class="stats">共 {len(review_articles)} 篇文章，{total} 条摘句</div>',
             """<div style="margin-bottom:15px"><button class="btn btn-ok" onclick="markAll('ok')">全部标OK</button>
    <button class="btn" onclick="expandAll()">展开全部</button>
    <button class="btn" onclick="collapseAll()">收起全部</button></div>"""]

    for i, a in enumerate(review_articles):
        title_html = (f'<a href="{escape(a["link"])}" target="_blank">{escape(a["title"])}</a>'
                      if a['link'] else escape(a['title']))
        parts.append(f'<div class="article" id="art-{i}">')
        parts.append(f'<div class="article-header" onclick="toggle({i})">')
        parts.append(f'<div class="article-title">{title_html}'
                     f'<span style="{_tag_style(a["tag"])}">{escape(a["tag"])}</span></div>')
        parts.append(f'<div class="article-meta">{a["date"]} | {len(a["items"])} 条摘句</div>')
        parts.append('</div>')
        parts.append(f'<div class="article-items" id="items-{i}">')
        for j, item in enumerate(a['items']):
            item_id = f'item-{i}-{j}'
            parts.append(f'<div class="item" id="{item_id}">')
            parts.append(f'<div>{escape(item)}</div>')
            parts.append('<div class="actions">')
            parts.append(f"""<span class="btn btn-ok" onclick="mark('{item_id}', 'ok')">OK</span>""")
            parts.append(f"""<span class="btn btn-problem" onclick="mark('{item_id}', 'problem')">不算</span>""")
            parts.append('</div></div>')
        parts.append('</div></div>')

    parts.append('''<script>
    function toggle(i) {
        document.getElementById('items-' + i).classList.toggle('hidden');
    }
    function expandAll() {
        document.querySelectorAll('.article-items').forEach(el => el.classList.remove('hidden'));
    }
    function collapseAll() {
        document.querySelectorAll('.article-items').forEach(el => el.classList.add('hidden'));
    }
    function mark(id, status) {
        var el = document.getElementById(id);
        el.classList.remove('ok', 'problem');
        el.classList.add(status);
        event.stopPropagation();
    }
    function markAll(status) {
        document.querySelectorAll('.item').forEach(el => {
            el.classList.remove('ok', 'problem');
            el.classList.add(status);
        });
    }
    document.querySelectorAll('.article-items').forEach(el => el.classList.remove('hidden'));
    </script></body></html>''')

    os.makedirs(os.path.dirname(output_path) or '.', exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(parts))
    print(f"审阅页面已生成: {output_path}（{len(review_articles)} 篇，{total} 条）")
