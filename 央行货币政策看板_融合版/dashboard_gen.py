#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
dashboard_gen.py — 五维度看板 HTML 生成器
生成 app/dashboard.html（卡片式看板）和 app/index.html（着陆页）
"""

import os
import sys
from html import escape
from datetime import date

_CODE_DIR = os.path.dirname(os.path.abspath(__file__))
if _CODE_DIR not in sys.path:
    sys.path.insert(0, _CODE_DIR)

import config
import pipeline


def generate_dashboard(dim_data, stats, output_path):
    """
    生成五维度看板 HTML

    参数:
        dim_data: {用户维度名: [(摘句, 文章信息), ...]}
        stats: pipeline 返回的统计信息
        output_path: 输出 HTML 路径
    """
    today = date.today().isoformat()
    total_quotes = stats['总条数']
    total_articles = stats['保留文章']

    P = []

    # === HTML 头部 + CSS ===
    P.append(_html_head())

    # === Hero ===
    P.append(f'''<div class="hero"><div class="hero-inner">
<h1>央行货币政策跟踪看板 <span class="thin">PBOC POLICY TRACKER</span></h1>
<div class="sub">数据源：金融时报 / 中国金融新闻网 · 记者马梅若、马玲<br>
保留文章 <b>{total_articles}</b> 篇 · 五维度摘句 <b>{total_quotes}</b> 条 · 更新至 {today}</div>
</div></div>''')

    # === Stat Row ===
    P.append('<div class="statrow">')
    for i, (udim, _) in enumerate(pipeline.DIM_MAP):
        _, fg = pipeline.DIM_COLORS[udim]
        count = stats['各维度'].get(udim, 0)
        en = _dim_en(udim)
        P.append(f'<a class="stat" href="#dim-{i}" style="--dc:{fg}">'
                 f'<div class="n">{count}</div><div class="l">{udim}</div>'
                 f'<div class="e">{en}</div></a>')
    P.append('</div>')

    # === Toolbar ===
    P.append('<div class="toolbar"><div class="toolbar-inner">')
    for i, (udim, _) in enumerate(pipeline.DIM_MAP):
        _, fg = pipeline.DIM_COLORS[udim]
        P.append(f'<a class="chip" href="#dim-{i}" style="--dc:{fg}">{udim}</a>')
    P.append('<input class="search" id="kw" placeholder="搜索摘句 / 文章标题…" oninput="filt()">')
    P.append('</div></div><main>')

    # === 各维度 ===
    for di, (udim, _) in enumerate(pipeline.DIM_MAP):
        _, fg = pipeline.DIM_COLORS[udim]
        bg = _dim_bg(udim)
        items = dim_data[udim]
        icon = _dim_icon(udim)

        P.append(f'<section class="dimsec" id="dim-{di}" style="--dc:{fg};--dbg:{bg}">')
        P.append(f'<div class="dimhead">{icon}<span class="name">{udim}</span>'
                 f'<span class="en">{_dim_en(udim)}</span>'
                 f'<span class="cnt">{len(items)} 条</span></div>')

        # 按文章分组
        cur_key = None
        for q, info in items:
            key = (info['title'], info['date'])
            if key != cur_key:
                if cur_key is not None:
                    P.append('</div>')  # 关闭上一个 art
                cur_key = key
                P.append(f'<div class="art" data-t="{escape(info["title"].lower())}">')
                P.append(f'<div class="art-head">'
                         f'<a href="{escape(info["link"])}" target="_blank">'
                         f'{escape(info["title"])}</a>'
                         f'<span class="badge date">{info["date"]}</span>'
                         f'<span class="badge">{escape(info["tag"])}</span></div>')
            P.append(f'<div class="q">{escape(q)}</div>')

        if cur_key is not None:
            P.append('</div>')
        P.append('</section>')

    # === Footer + JS ===
    P.append(f'''</main>
<footer>央行货币政策跟踪看板 · 五维度版<br>
共 {total_articles} 篇保留文章 · {total_quotes} 条摘句 · 生成于 {today}</footer>
<script>
function filt() {{
  const kw = document.getElementById('kw').value.trim().toLowerCase();
  document.querySelectorAll('.art').forEach(el => {{
    if (!kw) {{ el.classList.remove('hidden'); return; }}
    el.classList.toggle('hidden', !el.textContent.toLowerCase().includes(kw));
  }});
  document.querySelectorAll('.dimsec').forEach(sec => {{
    const any = sec.querySelector('.art:not(.hidden)');
    sec.classList.toggle('hidden', !any);
  }});
}}
document.querySelectorAll('a[href^="#dim-"]').forEach(a => {{
  a.addEventListener('click', e => {{
    e.preventDefault();
    const t = document.querySelector(a.getAttribute('href'));
    if (t) window.scrollTo({{ top: t.getBoundingClientRect().top + window.scrollY - 64, behavior: 'smooth' }});
  }});
}});
</script></body></html>''')

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(P))
    print(f"看板已生成: {output_path}（{total_quotes} 条摘句）")


def generate_index(dim_data, stats, output_path):
    """生成着陆页 index.html"""
    today = date.today().isoformat()
    total_quotes = stats['总条数']
    total_articles = stats['保留文章']

    dim_counts = ' · '.join(
        f'{udim} {stats["各维度"].get(udim, 0)}' for udim, _ in pipeline.DIM_MAP)

    html = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>央行货币政策跟踪看板</title>
<style>
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{ font-family: "PingFang SC","Microsoft YaHei","Noto Sans CJK SC",sans-serif;
       background: #f4f7fb; color: #1b2a41; }}
.hero {{
  background: linear-gradient(135deg, #0b2149 0%, #123a7a 55%, #1a5fb4 100%);
  color: #fff; padding: 52px 24px 92px; position: relative; overflow: hidden;
}}
.hero::after {{
  content: ""; position: absolute; right: -120px; top: -120px; width: 420px; height: 420px;
  background: radial-gradient(circle, rgba(255,255,255,.14), transparent 65%); border-radius: 50%;
}}
.hero-inner {{ max-width: 860px; margin: 0 auto; position: relative; z-index: 1; }}
.hero h1 {{ font-size: 30px; letter-spacing: 2px; font-weight: 700; }}
.hero h1 .thin {{ font-weight: 300; opacity: .85; }}
.hero .sub {{ margin-top: 12px; font-size: 13.5px; color: #b9cff0; letter-spacing: .5px; line-height: 1.9; }}
.hero .sub b {{ color: #ffd98a; font-weight: 600; }}
.wrap {{ max-width: 860px; margin: -52px auto 0; padding: 0 24px 60px; position: relative; z-index: 2; }}
.card {{
  display: block; background: #fff; border-radius: 16px; padding: 24px 28px; margin-bottom: 16px;
  text-decoration: none; color: #1b2a41; box-shadow: 0 8px 24px rgba(15,40,90,.10);
  border: 1px solid #eef2f8; transition: transform .15s ease, box-shadow .15s ease;
  position: relative; overflow: hidden;
}}
.card::before {{ content: ""; position: absolute; left: 0; top: 0; bottom: 0; width: 4px; background: var(--cc, #1a5fb4); }}
.card:hover {{ transform: translateY(-3px); box-shadow: 0 14px 32px rgba(15,40,90,.16); }}
.card .t {{ font-size: 17px; font-weight: 700; margin-bottom: 6px; }}
.card .t .tag {{ font-size: 11px; font-weight: 600; color: var(--cc, #1a5fb4); background: #f0f5fd;
  padding: 3px 10px; border-radius: 999px; margin-left: 8px; vertical-align: 2px; }}
.card .d {{ font-size: 13px; color: #5b6b82; line-height: 1.8; }}
.card.hot {{ box-shadow: 0 10px 28px rgba(15,40,90,.14); }}
footer {{ text-align: center; color: #9aa8bc; font-size: 12px; padding: 24px 0 10px; }}
</style>
</head>
<body>
<div class="hero"><div class="hero-inner">
  <h1>央行货币政策跟踪看板 <span class="thin">PBOC POLICY TRACKER</span></h1>
  <div class="sub">数据源：金融时报 / 中国金融新闻网 · 记者马梅若、马玲<br>
  保留文章 <b>{total_articles}</b> 篇 · 五维度摘句 <b>{total_quotes}</b> 条 · 更新至 {today}</div>
</div></div>

<div class="wrap">
<a class="card hot" href="dashboard.html" style="--cc:#1a5fb4">
  <div class="t">五维度看板<span class="tag">最新版</span></div>
  <div class="d">{dim_counts}<br>
  按维度分区展示，支持关键词搜索</div>
</a>

<a class="card" href="dim_audit.html" style="--cc:#9334e6">
  <div class="t">摘句审核看板<span class="tag">审核工具</span></div>
  <div class="d">五维度摘句逐条校对（对 / 不对标记，可导出清单）</div>
</a>

<footer>央行货币政策跟踪看板 · 生成于 {today}</footer>
</div>
</body>
</html>'''

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f"着陆页已生成: {output_path}")


# ============================================================
# HTML / CSS 模板片段
# ============================================================
def _html_head():
    return '''<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>央行货币政策跟踪看板</title>
<style>
:root {
  --ink: #1b2a41; --sub: #5b6b82; --line: #e8edf4; --bg: #f4f7fb;
}
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: "PingFang SC","Microsoft YaHei","Noto Sans CJK SC",sans-serif;
       background: var(--bg); color: var(--ink); }
.hero {
  background: linear-gradient(135deg, #0b2149 0%, #123a7a 55%, #1a5fb4 100%);
  color: #fff; padding: 44px 24px 88px; position: relative; overflow: hidden;
}
.hero::after {
  content: ""; position: absolute; right: -120px; top: -120px; width: 420px; height: 420px;
  background: radial-gradient(circle, rgba(255,255,255,.14), transparent 65%); border-radius: 50%;
}
.hero::before {
  content: ""; position: absolute; left: -80px; bottom: -160px; width: 340px; height: 340px;
  background: radial-gradient(circle, rgba(120,180,255,.18), transparent 65%); border-radius: 50%;
}
.hero-inner { max-width: 1080px; margin: 0 auto; position: relative; z-index: 1; }
.hero h1 { font-size: 30px; letter-spacing: 2px; font-weight: 700; }
.hero h1 .thin { font-weight: 300; opacity: .85; }
.hero .sub { margin-top: 10px; font-size: 13.5px; color: #b9cff0; letter-spacing: .5px; }
.hero .sub b { color: #ffd98a; font-weight: 600; }
.statrow { max-width: 1080px; margin: -56px auto 0; padding: 0 24px;
  display: grid; grid-template-columns: repeat(5, 1fr); gap: 14px; position: relative; z-index: 2; }
.stat {
  background: rgba(255,255,255,.96); border-radius: 14px; padding: 16px 16px 14px;
  box-shadow: 0 8px 24px rgba(15,40,90,.12); cursor: pointer;
  border-top: 3px solid var(--dc); transition: transform .15s ease, box-shadow .15s ease;
  text-decoration: none; display: block;
}
.stat:hover { transform: translateY(-3px); box-shadow: 0 14px 30px rgba(15,40,90,.18); }
.stat .n { font-size: 28px; font-weight: 700; color: var(--dc); line-height: 1.1; }
.stat .l { font-size: 13px; font-weight: 600; margin-top: 5px; }
.stat .e { font-size: 10px; color: #9aa8bc; letter-spacing: 1px; margin-top: 2px; }
.toolbar {
  position: sticky; top: 0; z-index: 20; background: rgba(244,247,251,.92);
  backdrop-filter: blur(8px); padding: 12px 24px; border-bottom: 1px solid var(--line);
}
.toolbar-inner { max-width: 1080px; margin: 0 auto; display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.chip {
  font-size: 12.5px; padding: 5px 13px; border-radius: 999px; text-decoration: none;
  background: #fff; color: var(--sub); border: 1px solid var(--line); font-weight: 600;
  transition: all .15s ease;
}
.chip:hover { border-color: var(--dc); color: var(--dc); }
.search {
  margin-left: auto; border: 1px solid var(--line); border-radius: 999px; padding: 7px 16px;
  font-size: 13px; width: 220px; outline: none; background: #fff; color: var(--ink);
}
.search:focus { border-color: #1a5fb4; box-shadow: 0 0 0 3px rgba(26,95,180,.12); }
main { max-width: 1080px; margin: 0 auto; padding: 10px 24px 60px; }
.dimsec { margin-top: 34px; }
.dimhead {
  display: flex; align-items: center; gap: 12px; padding: 13px 18px; border-radius: 14px;
  background: var(--dbg); margin-bottom: 14px;
}
.dimhead svg { width: 22px; height: 22px; stroke: var(--dc); fill: none; stroke-width: 2; stroke-linecap: round; stroke-linejoin: round; }
.dimhead .name { font-size: 17px; font-weight: 700; color: var(--dc); }
.dimhead .en { font-size: 10.5px; color: #9aa8bc; letter-spacing: 1.5px; }
.dimhead .cnt { margin-left: auto; font-size: 13px; font-weight: 700; color: var(--dc);
  background: #fff; padding: 3px 12px; border-radius: 999px; }
.art {
  background: #fff; border-radius: 14px; margin-bottom: 12px; overflow: hidden;
  box-shadow: 0 2px 10px rgba(15,40,90,.06); border: 1px solid #eef2f8;
  transition: box-shadow .15s ease;
}
.art:hover { box-shadow: 0 6px 20px rgba(15,40,90,.11); }
.art-head { padding: 13px 18px 10px; display: flex; align-items: baseline; gap: 10px; flex-wrap: wrap; }
.art-head a { color: var(--ink); font-weight: 700; font-size: 14.5px; text-decoration: none; }
.art-head a:hover { color: #1a5fb4; }
.badge { font-size: 11px; color: var(--sub); background: var(--bg); padding: 2px 10px; border-radius: 999px; }
.badge.date { font-variant-numeric: tabular-nums; }
.art-head .src { margin-left: auto; font-size: 11px; color: #a5b2c5; }
.q { padding: 9px 18px 9px 20px; font-size: 13.5px; line-height: 1.85; color: #2c3e57;
  border-top: 1px dashed #edf1f7; position: relative; }
.q::before { content: ""; position: absolute; left: 0; top: 0; bottom: 0; width: 3px; background: var(--dc); opacity: .55; }
.q:first-of-type { border-top: none; }
footer { text-align: center; color: #9aa8bc; font-size: 12px; padding: 30px 0 40px; line-height: 2; }
.hidden { display: none !important; }
@media (max-width: 760px) {
  .statrow { grid-template-columns: repeat(2, 1fr); }
  .search { width: 100%; margin-left: 0; }
}
</style></head><body>'''


def _dim_en(udim):
    return {
        '经济形势': 'ECONOMY',
        '货币政策取向': 'POLICY STANCE',
        '国债买卖': 'BOND TRADING',
        '资金利率态度': 'LIQUIDITY & RATES',
        '债券市场态度': 'BOND MARKET',
    }.get(udim, '')


def _dim_bg(udim):
    return {
        '经济形势': '#e6f4ea',
        '货币政策取向': '#e3eefd',
        '国债买卖': '#fef3e6',
        '资金利率态度': '#f3e5f5',
        '债券市场态度': '#fce4ec',
    }.get(udim, '#f5f5f5')


def _dim_icon(udim):
    icons = {
        '经济形势': '<svg viewBox="0 0 24 24"><path d="M3 17l6-6 4 4 8-8"/></svg>',
        '货币政策取向': '<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 3"/></svg>',
        '国债买卖': '<svg viewBox="0 0 24 24"><path d="M12 2v20M2 12h20"/></svg>',
        '资金利率态度': '<svg viewBox="0 0 24 24"><path d="M4 14h4v7H4zM10 9h4v12h-4zM16 4h4v17h-4z"/></svg>',
        '债券市场态度': '<svg viewBox="0 0 24 24"><path d="M3 20l4-8 4 4 4-6 6 10"/></svg>',
    }
    return icons.get(udim, '<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="9"/></svg>')


if __name__ == '__main__':
    print("加载数据并运行流水线...")
    cache, report = pipeline.load_data()
    dim_data, stats, _ = pipeline.run_pipeline(cache, report)

    print(f"\n生成看板...")
    generate_dashboard(dim_data, stats,
                       os.path.join(config.OUTPUT_DIR, 'dashboard.html'))
    generate_index(dim_data, stats,
                   os.path.join(config.OUTPUT_DIR, 'index.html'))
