#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
dashboard.py — HTML 看板生成
移植自 run_dashboard_v4（多条摘句换行显示、加宽维度列版本）
"""

import os

DIMS = ['经济形势判断', '工作重点', '货币政策取向', '资金态度', '债券市场态度']

# 标签配色，审阅页（review.py）也复用
TAG_COLORS = {
    '流动性投放': ('#e3f2fd', '#1565c0'),
    '利率政策': ('#f3e5f5', '#7b1fa2'),
    '金融统计数据': ('#e8f5e9', '#2e7d32'),
    '货币政策例会': ('#fff3e0', '#ef6c00'),
    '国债买卖': ('#fce4ec', '#c62828'),
    '货币政策/宏观调控': ('#f5f5f5', '#555555'),
    '宏观点评': ('#e0f7fa', '#00838f'),
}


def generate_dashboard(data, output_path):
    data.sort(key=lambda x: x['date'], reverse=True)
    rows_html = ""
    for item in data:
        tag_class = f"tag-{item['tag'].replace('/', '-')}"
        dims = ['经济形势判断', '工作重点', '货币政策取向',
                '资金态度', '债券市场态度']
        dim_cells = ""
        for d in dims:
            v = item[d]
            css = 'dim-cell slash' if v == '/' else 'dim-cell'
            display = v.replace(' / ', '<br>')
            dim_cells += f'<td class="{css}">{display}</td>'
        clean_title_text = item.get('clean_title', item['title'])
        title_display = clean_title_text[:50]
        if len(clean_title_text) > 50:
            title_display += "..."
        rows_html += (
            f'                    <tr data-tag="{item["tag"]}">\n'
            f'                        <td class="date">{item["date"]}</td>\n'
            f'                        <td class="title">'
            f'<a href="{item["link"]}" target="_blank">{title_display}</a></td>\n'
            f'                        <td>{item["author"][:3]}</td>\n'
            f'                        <td><span class="tag {tag_class}">'
            f'{item["tag"]}</span></td>\n'
            f'                        {dim_cells}\n'
            f'                    </tr>\n'
        )
    total = len(data)
    html = '''<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>央行货币政策跟踪看板</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI",
                "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", sans-serif;
            background: #f5f6fa; color: #333;
        }
        .header {
            background: linear-gradient(135deg, #1a237e 0%, #283593 100%);
            color: white; padding: 20px 30px;
            position: sticky; top: 0; z-index: 100;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }
        .header h1 { font-size: 20px; font-weight: 600; margin-bottom: 5px; }
        .header .subtitle { font-size: 13px; opacity: 0.85; }
        .controls {
            background: white; padding: 15px 30px;
            border-bottom: 1px solid #e8e8e8;
            display: flex; gap: 12px; flex-wrap: wrap;
            align-items: center;
            position: sticky; top: 68px; z-index: 99;
        }
        .controls input {
            padding: 8px 14px; border: 1px solid #d9d9d9;
            border-radius: 6px; font-size: 14px; outline: none;
            width: 260px;
        }
        .controls input:focus { border-color: #283593; }
        .stats {
            display: flex; gap: 20px;
            font-size: 13px; color: #666; margin-left: auto;
        }
        .stats span { color: #283593; font-weight: 600; }
        .tag-filter { display: flex; gap: 6px; flex-wrap: wrap; }
        .tag-btn {
            padding: 4px 12px; border-radius: 4px; font-size: 12px;
            cursor: pointer; border: 1px solid #d9d9d9;
            background: white; color: #555; transition: all 0.2s;
        }
        .tag-btn:hover { border-color: #283593; color: #283593; }
        .tag-btn.active { background: #283593; color: white; border-color: #283593; }
        .container { padding: 20px 30px; }
        .table-wrapper {
            background: white; border-radius: 8px;
            box-shadow: 0 1px 4px rgba(0,0,0,0.05);
            overflow-x: auto;
        }
        table { width: 100%; border-collapse: collapse; font-size: 13px; }
        th {
            background: #f8f9fa; padding: 12px 14px;
            text-align: left; font-weight: 600; color: #555;
            border-bottom: 2px solid #e8e8e8;
            white-space: nowrap; position: sticky; top: 0; z-index: 10;
        }
        td {
            padding: 12px 14px; border-bottom: 1px solid #f0f0f0;
            vertical-align: top; line-height: 1.6;
        }
        tr:hover { background: #fafbfc; }
        .date { color: #888; font-size: 12px; white-space: nowrap; }
        .title a {
            color: #1a237e; text-decoration: none; font-weight: 500;
        }
        .title a:hover { text-decoration: underline; }
        .tag {
            display: inline-block; padding: 2px 8px;
            border-radius: 4px; font-size: 11px;
            font-weight: 500; white-space: nowrap;
        }
        .tag-流动性投放 { background: #e3f2fd; color: #1565c0; }
        .tag-利率政策 { background: #f3e5f5; color: #7b1fa2; }
        .tag-金融统计数据 { background: #e8f5e9; color: #2e7d32; }
        .tag-货币政策例会 { background: #fff3e0; color: #ef6c00; }
        .tag-国债买卖 { background: #fce4ec; color: #c62828; }
        .tag-货币政策-宏观调控 { background: #f5f5f5; color: #555; }
        .tag-宏观点评 { background: #e0f7fa; color: #00838f; }
        .dim-cell { max-width: 250px; color: #444; font-size: 12.5px; }
        .dim-cell.slash { color: #ccc; }
        .no-result {
            text-align: center; padding: 40px;
            color: #999; font-size: 14px; display: none;
        }
    </style>
</head>
<body>
    <div class="header">
        <h1>央行货币政策跟踪看板</h1>
        <div class="subtitle">马梅若/马玲署名文章 · 2024年8月至今 · 五维度核心观点提取</div>
    </div>
    <div class="controls">
        <div class="tag-filter" id="tagFilter">
            <button class="tag-btn active" data-tag="">全部</button>
            <button class="tag-btn" data-tag="流动性投放">流动性投放</button>
            <button class="tag-btn" data-tag="利率政策">利率政策</button>
            <button class="tag-btn" data-tag="金融统计数据">金融统计数据</button>
            <button class="tag-btn" data-tag="货币政策例会">货币政策例会</button>
            <button class="tag-btn" data-tag="国债买卖">国债买卖</button>
            <button class="tag-btn" data-tag="货币政策/宏观调控">宏观调控</button>
            <button class="tag-btn" data-tag="宏观点评">宏观点评</button>
        </div>
        <input type="text" id="searchInput" placeholder="搜索标题、内容关键词...">
        <div class="stats">显示 <span id="showCount">''' + str(total) + '''</span> / ''' + str(total) + ''' 篇</div>
    </div>
    <div class="container">
        <div class="table-wrapper">
            <table>
                <thead>
                    <tr>
                        <th style="width:90px">日期</th>
                        <th style="min-width:200px">标题</th>
                        <th style="width:60px">作者</th>
                        <th style="width:100px">标签</th>
                        <th style="width:200px">经济形势判断</th>
                        <th style="width:200px">工作重点</th>
                        <th style="width:200px">货币政策取向</th>
                        <th style="width:200px">资金态度</th>
                        <th style="width:200px">债券市场态度</th>
                    </tr>
                </thead>
                <tbody id="tableBody">
''' + rows_html + '''                </tbody>
            </table>
            <div class="no-result" id="noResult">没有找到匹配的文章</div>
        </div>
    </div>
    <script>
        const tagBtns = document.querySelectorAll('.tag-btn');
        const searchInput = document.getElementById('searchInput');
        const tableBody = document.getElementById('tableBody');
        const showCount = document.getElementById('showCount');
        const noResult = document.getElementById('noResult');
        const rows = tableBody.querySelectorAll('tr');
        let currentTag = '';

        tagBtns.forEach(btn => {
            btn.addEventListener('click', () => {
                tagBtns.forEach(b => b.classList.remove('active'));
                btn.classList.add('active');
                currentTag = btn.dataset.tag;
                filterRows();
            });
        });

        searchInput.addEventListener('input', filterRows);

        function filterRows() {
            const keyword = searchInput.value.toLowerCase();
            let visible = 0;
            rows.forEach(row => {
                const tagMatch = !currentTag || row.dataset.tag === currentTag;
                const textMatch = !keyword || row.textContent.toLowerCase().includes(keyword);
                if (tagMatch && textMatch) {
                    row.style.display = '';
                    visible++;
                } else {
                    row.style.display = 'none';
                }
            });
            showCount.textContent = visible;
            noResult.style.display = visible === 0 ? 'block' : 'none';
        }
    </script>
</body>
</html>'''
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f"看板已保存: {output_path}")
