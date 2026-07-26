#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""config.py — 全局路径配置（告别硬编码 /tmp/ 路径）

目录结构：
  PROJECT_ROOT/          ← 项目根目录
    articles_cache.json  ← 文章缓存
    pipeline_report.json ← 流水线报告
    app/                 ← 看板 HTML 输出
    code/                ← 本目录（Python 代码）
"""
import os

# 代码目录（本文件所在目录）
CODE_DIR = os.path.dirname(os.path.abspath(__file__))

# 项目根目录（代码目录的上一级）
PROJECT_ROOT = os.path.dirname(CODE_DIR)

# 数据文件
CACHE_PATH = os.path.join(PROJECT_ROOT, 'articles_cache.json')
REPORT_PATH = os.path.join(PROJECT_ROOT, 'pipeline_report.json')

# 输出目录
OUTPUT_DIR = os.path.join(PROJECT_ROOT, 'app')

# 爬虫参数
START_DATE = '20240801'
AUTHORS = ('马梅若', '马玲')
