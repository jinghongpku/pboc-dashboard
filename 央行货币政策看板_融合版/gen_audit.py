#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
gen_audit.py — 五维度摘句审核看板（2026-07-22）
对全部保留文章重新提取摘句，按用户五维度组织：
  经济形势(=经济形势判断) / 货币政策取向 / 国债买卖 / 资金利率态度(=资金态度) / 债券市场态度
每条摘句可标记 对/不对，标记存 localStorage，可导出"不对"清单回贴给助手。
（"工作重点"维度的摘句不参与本轮审核，仅统计数量）
"""

import json
import re
import sys
import os
from html import escape

_CODE_DIR = os.path.dirname(os.path.abspath(__file__))
if _CODE_DIR not in sys.path:
    sys.path.insert(0, _CODE_DIR)

import config
import extractor
import pipeline

CACHE = config.CACHE_PATH
REPORT = config.REPORT_PATH
OUT = os.path.join(config.OUTPUT_DIR, 'dim_audit.html')

# 用户五维度 → 系统维度名
DIM_MAP = [
    ('经济形势', '经济形势判断'),
    ('货币政策取向', '货币政策取向'),
    ('国债买卖', '国债买卖'),
    ('资金利率态度', '资金态度'),
    ('债券市场态度', '债券市场态度'),
]
DIM_COLORS = {
    '经济形势': ('#e8f5e9', '#2e7d32'),
    '货币政策取向': ('#e3f2fd', '#1565c0'),
    '国债买卖': ('#fff3e0', '#e65100'),
    '资金利率态度': ('#f3e5f5', '#6a1b9a'),
    '债券市场态度': ('#fce4ec', '#ad1457'),
}

cache = json.load(open(CACHE, encoding='utf-8'))
report = json.load(open(REPORT, encoding='utf-8'))
kept_keys = {(k['title'], k['date']) for k in report['kept']}

# 逐篇重新提取，收集五维度摘句
dim_data = {u: [] for u, _ in DIM_MAP}   # 用户维度 -> [(句子, 文章信息)]
work_only_articles = []                  # 五维度无句、仅工作重点有句的文章
for a in cache:
    if (a.get('title'), a.get('date')) not in kept_keys:
        continue
    res = extractor.extract_core_view(
        a.get('content', ''), a.get('title', ''), a.get('tag', ''),
        a.get('title_page'))
    info = {
        'date': f"{a['date'][:4]}-{a['date'][4:6]}-{a['date'][6:8]}",
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

for u in dim_data:
    dim_data[u].sort(key=lambda x: x[1]['date'], reverse=True)
total = sum(len(v) for v in dim_data.values())

# ============ 生成 HTML ============
P = []
P.append('''<!DOCTYPE html><html><head><meta charset="UTF-8">
<title>五维度摘句审核</title>
<style>
body { font-family: "Microsoft YaHei","PingFang SC",sans-serif; margin:16px; background:#f5f5f5; }
h1 { font-size:20px; color:#333; margin:8px 0; }
.stats { background:#fff; padding:12px 18px; border-radius:8px; margin-bottom:12px; font-size:13px; line-height:1.9; }
.dimnav { position:sticky; top:0; background:#f5f5f5; padding:8px 0; z-index:10; }
.dimnav a { display:inline-block; padding:5px 14px; margin-right:6px; border-radius:16px; text-decoration:none; font-size:13px; font-weight:bold; }
.dimsec { margin-bottom:26px; }
.dimhead { font-size:16px; font-weight:bold; padding:8px 14px; border-radius:8px 8px 0 0; }
.art { background:#fff; border:1px solid #e3e3e3; border-top:none; }
.art-head { padding:8px 14px; background:#fafbfc; border-bottom:1px solid #eee; font-size:13px; }
.art-head a { color:#1a3a5c; font-weight:bold; text-decoration:none; }
.art-head a:hover { text-decoration:underline; }
.art-meta { color:#999; font-size:11px; margin-left:8px; }
.item { padding:8px 14px; border-bottom:1px solid #f2f2f2; font-size:13px; line-height:1.7; }
.item:last-child { border-bottom:none; }
.item .q { color:#222; }
.item .btns { margin-top:4px; }
.b { display:inline-block; padding:2px 12px; border-radius:3px; cursor:pointer; font-size:12px; margin-right:6px; border:1px solid #ccc; user-select:none; }
.b-ok { background:#e8f5e9; border-color:#4caf50; color:#2e7d32; }
.b-no { background:#ffebee; border-color:#f44336; color:#c62828; }
.item.ok { background:#f1f8f1; }
.item.no { background:#fff5f5; }
.item.ok .b-ok { background:#4caf50; color:#fff; }
.item.no .b-no { background:#f44336; color:#fff; }
.toolbar { margin:10px 0; }
.toolbar .b { font-size:13px; padding:5px 14px; background:#fff; }
#export { width:100%; height:130px; font-size:12px; margin-top:8px; display:none; }
.counter { color:#888; font-weight:normal; font-size:12px; margin-left:10px; }
details { background:#fff; border-radius:8px; padding:8px 14px; margin-bottom:14px; font-size:13px; }
summary { cursor:pointer; font-weight:bold; }
</style></head><body>''')

P.append('<h1>五维度摘句审核看板</h1>')
stat_cells = ''.join(
    f'<span style="background:{DIM_COLORS[u][0]};color:{DIM_COLORS[u][1]};'
    f'padding:2px 10px;border-radius:10px;margin-right:8px;font-weight:bold">'
    f'{u} {len(dim_data[u])}条</span>' for u, _ in DIM_MAP)
P.append(f'<div class="stats">{stat_cells}<br>'
         f'共 {len(kept_keys)} 篇保留文章，五维度摘句合计 {total} 条；'
         f'其中 {len(work_only_articles)} 篇五维度无摘句（仅"工作重点"有句或为空，见文末）。'
         f'<br>操作：逐条点「对」或「不对」，标记自动保存在浏览器；'
         f'审完点「导出不对清单」把文本贴回给我即可。</div>')

P.append('<div class="dimnav">' + ''.join(
    f'<a href="#dim-{i}" style="background:{DIM_COLORS[u][0]};color:{DIM_COLORS[u][1]}">'
    f'{u} ({len(dim_data[u])})</a>' for i, (u, _) in enumerate(DIM_MAP)) + '</div>')

P.append('''<div class="toolbar">
<span class="b" onclick="markVisible('ok')">本页全标对</span>
<span class="b" onclick="markVisible('no')">本页全标不对</span>
<span class="b" onclick="exportNo()">导出不对清单</span>
<span class="b" onclick="resetAll()">清空标记</span>
<span class="counter" id="cnt"></span>
</div>
<textarea id="export" readonly></textarea>''')

for di, (udim, _) in enumerate(DIM_MAP):
    bg, fg = DIM_COLORS[udim]
    items = dim_data[udim]
    P.append(f'<div class="dimsec" id="dim-{di}">')
    P.append(f'<div class="dimhead" style="background:{bg};color:{fg}">{udim}（{len(items)}条）</div>')
    # 按文章分组
    cur = None
    for qi, (q, info) in enumerate(items):
        key = (info['title'], info['date'])
        if key != cur:
            if cur is not None:
                P.append('</div>')
            cur = key
            P.append('<div class="art">')
            P.append(f'<div class="art-head"><a href="{escape(info["link"])}" target="_blank">'
                     f'{escape(info["title"])}</a>'
                     f'<span class="art-meta">{info["date"]} | {escape(info["tag"])}</span></div>')
        iid = f'd{di}-{qi}'
        P.append(f'<div class="item" id="{iid}"><div class="q">{escape(q)}</div>'
                 f'<div class="btns"><span class="b b-ok" onclick="mark(\'{iid}\',\'ok\',event)">对</span>'
                 f'<span class="b b-no" onclick="mark(\'{iid}\',\'no\',event)">不对</span></div></div>')
    if cur is not None:
        P.append('</div>')
    P.append('</div>')

# 五维度无摘句文章清单
P.append(f'<details><summary>五维度无摘句的文章（{len(work_only_articles)}篇，仅"工作重点"有句或为空，不纳入本轮审核）</summary>')
for info in work_only_articles:
    P.append(f'<div style="padding:3px 0"><a href="{escape(info["link"])}" target="_blank">{escape(info["title"])}</a>'
             f'<span class="art-meta">{info["date"]} | {escape(info["tag"])}</span></div>')
P.append('</details>')

P.append('''<script>
const KEY = 'dim_audit_marks_v1';
let marks = JSON.parse(localStorage.getItem(KEY) || '{}');
function apply() {
  for (const [id, st] of Object.entries(marks)) {
    const el = document.getElementById(id);
    if (el) { el.classList.remove('ok','no'); el.classList.add(st); }
  }
  updateCnt();
}
function mark(id, st, ev) {
  ev.stopPropagation();
  const el = document.getElementById(id);
  if (marks[id] === st) { delete marks[id]; el.classList.remove('ok','no'); }
  else { marks[id] = st; el.classList.remove('ok','no'); el.classList.add(st); }
  localStorage.setItem(KEY, JSON.stringify(marks));
  updateCnt();
}
function markVisible(st) {
  document.querySelectorAll('.item').forEach(el => {
    marks[el.id] = st; el.classList.remove('ok','no'); el.classList.add(st);
  });
  localStorage.setItem(KEY, JSON.stringify(marks));
  updateCnt();
}
function resetAll() {
  if (!confirm('清空全部标记？')) return;
  marks = {}; localStorage.removeItem(KEY);
  document.querySelectorAll('.item').forEach(el => el.classList.remove('ok','no'));
  updateCnt();
}
function updateCnt() {
  const ok = Object.values(marks).filter(v=>v==='ok').length;
  const no = Object.values(marks).filter(v=>v==='no').length;
  document.getElementById('cnt').textContent = `已标 对${ok} / 不对${no} / 共${document.querySelectorAll('.item').length}`;
}
function exportNo() {
  const lines = [];
  document.querySelectorAll('.dimsec').forEach(sec => {
    const dim = sec.querySelector('.dimhead').textContent.replace(/（.*$/,'');
    sec.querySelectorAll('.art').forEach(art => {
      const title = art.querySelector('.art-head a').textContent;
      const meta = art.querySelector('.art-meta').textContent;
      art.querySelectorAll('.item.no').forEach(it => {
        lines.push(`【${dim}】${title} | ${meta}\\n  ✗ ${it.querySelector('.q').textContent}`);
      });
    });
  });
  const ta = document.getElementById('export');
  ta.style.display = 'block';
  ta.value = lines.length ? lines.join('\\n') : '（没有标记"不对"的摘句）';
  ta.scrollIntoView();
}
apply();
</script></body></html>''')

with open(OUT, 'w', encoding='utf-8') as f:
    f.write('\n'.join(P))
print(f'审核看板已生成: {OUT}')
print(f'五维度摘句: {total} 条')
for u, _ in DIM_MAP:
    print(f'  {u}: {len(dim_data[u])} 条')
print(f'五维度无摘句文章: {len(work_only_articles)} 篇')
