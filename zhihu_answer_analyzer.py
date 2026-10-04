#!/usr/bin/env python3
"""
知乎问题回答爬取分析工具
输入知乎问题链接，自动爬取所有回答+评论，智能筛选精华，生成HTML报告

使用方法:
    python zhihu_answer_analyzer.py https://www.zhihu.com/question/123456
    python zhihu_answer_analyzer.py 123456 --cookie "你的z_c0值"

依赖:
    pip install requests jieba beautifulsoup4
"""

import argparse
import json
import os
import re
import sys
import time
from collections import Counter
from datetime import datetime

import requests

# ============================================================
# 配置
# ============================================================

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://www.zhihu.com",
    "Accept": "application/json, text/plain, */*",
    "x-requested-with": "fetch",
    "x-zse-93": "101_3_3.0",
}

# 全局Cookie和d_c0
ZHIHU_COOKIE = ""
ZHIHU_DC0 = ""

# DeepSeek API配置
DEEPSEEK_API_URL = "https://api.deepseek.com/chat/completions"
DEEPSEEK_MODEL = "deepseek-chat"


def deepseek_summary(api_key, question_info, answers, max_answers=50, max_chars_per_answer=800):
    """调用DeepSeek API生成深度总结"""
    if not api_key:
        return None

    print("\n🤖 调用DeepSeek生成深度总结...")
    print(f"   输入：TOP{max_answers}精华回答，每个截取{max_chars_per_answer}字")

    # 准备回答内容（取精华评分最高的N个回答）
    sorted_answers = sorted(answers, key=lambda x: x.get("quality_score", {}).get("total", 0), reverse=True)
    top_answers = sorted_answers[:max_answers]

    answers_text = ""
    for i, ans in enumerate(top_answers, 1):
        content = ans.get("content", "")[:max_chars_per_answer]
        author = ans.get("author", "匿名")
        votes = ans.get("voteup_count", 0)
        comments = ans.get("comment_count", 0)
        answers_text += f"\n【回答{i}】作者：{author} | 赞同：{votes} | 评论：{comments}\n{content}\n"

    prompt = f"""你是一个专业的知乎内容分析专家，也是一个高效的知识筛选助手。你的任务是分析以下知乎问题下的所有回答，帮用户筛选干货、提炼精华，让用户不用逐条阅读就能高效吸收最有价值的内容。

【问题标题】{question_info.get('title', '')}

【问题描述】{question_info.get('detail', '')[:500]}

【精华回答（共{len(top_answers)}条，按质量评分排序）】{answers_text}

请按以下格式生成一份全面、详细的深度总结（用中文，分点清晰，重点突出）：

## 一、问题背景与核心议题
（这个问题在讨论什么？为什么会有这个问题？核心议题是什么？用2-3段话说明）

## 二、主流观点全景图
（把所有回答的观点分成3-5个主要流派/立场，每个流派说明：核心主张、代表回答、支持人数、主要论据。让用户一眼看清整体格局）

## 三、高赞回答精华摘要
（对点赞最高的5-8个回答，每个用3-5句话详细总结核心内容、关键论据、独特观点。注明作者和赞同数）

## 四、实用干货提取
（从所有回答中提取最有价值的实用信息，分类整理：
- 📌 具体方法/步骤/技巧
- 💡 经验教训/避坑指南
- 📚 推荐资源/工具/书籍/链接
- ⚠️ 注意事项/风险提示
每条干货注明来自哪个回答）

## 五、金句与亮点摘录
（摘录5-10条最精彩、最有启发性的原文句子，注明作者和赞同数）

## 六、争议焦点与多方辩论
（列出2-3个争议最大的话题，分别说明正方观点、反方观点、中立观点，以及各自的核心论据）

## 七、反方/小众观点
（那些赞同数不高但很有启发性的反常识观点、小众视角，不要遗漏）

## 八、阅读优先级推荐
（如果用户时间有限，推荐优先看哪3-5个回答？为什么？哪些回答可以跳过？）

## 九、知识体系梳理
（把这个问题涉及的核心概念、逻辑关系、因果链条梳理清楚，帮用户建立系统认知）

## 十、最终结论与行动建议
（这个问题的共识是什么？还有哪些没有定论？给读者的具体建议是什么？如果要实践，第一步该做什么？）

要求：
1. 客观中立，不偏不倚，基于提供的回答内容，不要编造
2. 重点突出干货和实用信息，避免空泛的套话
3. 语言精炼但信息密度高，让用户花最少时间获取最多价值
4. 总字数控制在2000-3000字
5. 重要信息用加粗标注
6. 每个观点尽量注明来源（回答编号或作者）"""

    try:
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        data = {
            "model": DEEPSEEK_MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.7,
            "max_tokens": 4000
        }

        resp = requests.post(DEEPSEEK_API_URL, headers=headers, json=data, timeout=180)
        resp.raise_for_status()
        result = resp.json()

        summary = result["choices"][0]["message"]["content"]
        print(f"✅ 深度总结生成完成（约{len(summary)}字）")
        return summary

    except Exception as e:
        print(f"⚠️  DeepSeek API调用失败: {e}")
        return None


def load_knowledge(books=None, perspective=None):
    """加载知识库文件（书籍核心观点+名人视角）"""
    knowledge_text = ""

    # 加载书籍
    if books:
        book_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "knowledge", "books")
        for book_name in books:
            book_file = os.path.join(book_dir, f"{book_name}_核心观点.md")
            if os.path.exists(book_file):
                with open(book_file, "r", encoding="utf-8") as f:
                    knowledge_text += f"\n\n========== 书籍：{book_name} ==========\n"
                    knowledge_text += f.read()
                print(f"📚 已加载书籍：{book_name}")
            else:
                print(f"⚠️  未找到书籍：{book_name}")

    # 加载名人视角
    if perspective:
        persp_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "knowledge", "perspectives")
        persp_file = os.path.join(persp_dir, f"{perspective}_思维框架.md")
        if os.path.exists(persp_file):
            with open(persp_file, "r", encoding="utf-8") as f:
                knowledge_text += f"\n\n========== 视角：{perspective} ==========\n"
                knowledge_text += f.read()
            print(f"🎯 已加载视角：{perspective}")
        else:
            print(f"⚠️  未找到视角：{perspective}")

    return knowledge_text


def multi_source_analysis(api_key, question_info, answers, knowledge_text, perspective=None):
    """多源知识融合分析：知乎回答 + 书籍 + 名人视角"""
    if not api_key or not knowledge_text:
        return None

    print(f"\n🧠 多源融合分析中（视角：{perspective or '无'}）...")

    # 准备回答内容
    sorted_answers = sorted(answers, key=lambda x: x.get("quality_score", {}).get("total", 0), reverse=True)
    top_answers = sorted_answers[:30]

    answers_text = ""
    for i, ans in enumerate(top_answers, 1):
        content = ans.get("content", "")[:600]
        author = ans.get("author", "匿名")
        votes = ans.get("voteup_count", 0)
        answers_text += f"\n【回答{i}】作者：{author} | 赞同：{votes}\n{content}\n"

    persp_text = f"用{perspective}的思维框架和表达方式来点评" if perspective else "客观中立地"

    prompt = f"""你是一个顶级的内容分析专家，擅长从多个信息源中提炼精华、辨析真伪、给出高维洞察。

请分析以下知乎问题下的回答，并结合提供的书籍知识和名人视角，生成一份多源融合的深度分析报告。

【问题标题】{question_info.get('title', '')}

【知乎精华回答】{answers_text}

【参考知识库】{knowledge_text}

请按以下格式生成分析报告（用中文，分点清晰，重点突出）：

## 一、三方对照分析
将知乎回答、书籍观点、{perspective or '通用'}视角三者进行对照：
- 共识点：哪些观点是三方都认同的？
- 矛盾点：哪些观点之间存在冲突？谁更有道理？
- 互补点：书籍和视角补充了哪些知乎回答没有提到的内容？

## 二、{perspective or '专家'}视角深度点评
{persp_text}这些回答：
- 哪些回答说到了点子上？为什么？
- 哪些回答是正确的废话？看似有道理实则没用？
- 哪些回答有误导性？可能会害了读者？
- 从更高维的视角看，这个问题的本质是什么？

## 三、精华回答分级
将回答分为三个等级：
- ⭐⭐⭐ 真干货：有具体方法、数据、可操作建议的回答（列出3-5个，说明为什么好）
- ⭐⭐ 有启发：有一定观点但不够深入的回答（列出3-5个）
- ⭐ 鸡汤/误导：看似正能量实则没用，甚至有误导性的回答（列出2-3个，说明为什么不好）

## 四、书籍知识印证
- 书中的哪些观点被知乎回答印证了？
- 书中的哪些建议在知乎回答中被反复验证？
- 有没有知乎回答提到了书里没有的新视角？

## 五、认知升级总结
综合所有信息源，给出比任何单一来源都更高维的结论：
- 这个问题的底层逻辑是什么？
- 普通人最应该记住的3-5条核心建议是什么？
- 有哪些常见的误区需要避免？
- 如果只能做一件事，应该做什么？

要求：
1. 基于提供的所有信息，不要编造
2. 敢于直言，不怕得罪人，明确指出哪些回答是垃圾
3. 重点突出可操作的建议，不要空泛的道理
4. 每个判断尽量说明理由和依据
5. 总字数控制在2000-3000字
6. 重要信息用加粗标注"""

    try:
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        data = {
            "model": DEEPSEEK_MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.7,
            "max_tokens": 4000
        }

        resp = requests.post(DEEPSEEK_API_URL, headers=headers, json=data, timeout=180)
        resp.raise_for_status()
        result = resp.json()

        analysis = result["choices"][0]["message"]["content"]
        print(f"✅ 多源融合分析完成（约{len(analysis)}字）")
        return analysis

    except Exception as e:
        print(f"⚠️  多源融合分析失败: {e}")
        return None


def set_zhihu_cookie(cookie):
    """设置知乎Cookie并提取d_c0"""
    global ZHIHU_COOKIE, ZHIHU_DC0
    ZHIHU_COOKIE = cookie
    HEADERS["Cookie"] = cookie
    # 提取d_c0
    import re
    match = re.search(r'd_c0=([^;]+)', cookie)
    if match:
        ZHIHU_DC0 = match.group(1)


def sign_zhihu_request(url_path, body=""):
    """生成知乎x-zse-96签名"""
    import hashlib
    x_zse_93 = "101_3_3.0"
    # 签名公式: MD5(x-zse-93 + 路径 + body + d_c0)
    raw = f"{x_zse_93}{url_path}{body}{ZHIHU_DC0}"
    md5 = hashlib.md5(raw.encode()).hexdigest()
    return f"{x_zse_93}+{md5}"

# 停用词
STOP_WORDS = {
    "的", "了", "是", "在", "和", "有", "就", "都", "而", "及", "与", "之", "也",
    "不", "很", "还", "这", "那", "我", "你", "他", "她", "它", "什么", "怎么",
    "一个", "一点", "全部", "看看", "我们", "你们", "他们", "这个", "那个",
    "可以", "已经", "还是", "就是", "不是", "没有", "自己", "一下", "一些",
    "一种", "一样", "真的", "太", "最", "更", "非常", "特别", "比较", "其实",
    "然后", "因为", "所以", "如果", "但是", "而且", "或者", "虽然", "不过",
    "以及", "等等", "之类", "这么", "那么", "怎样", "咋样", "啥", "呗", "呀",
    "啊", "吧", "呢", "嘛", "哦", "哈", "嘿", "哎", "嗯", "说", "做", "要",
    "会", "能", "对", "去", "来", "给", "从", "到", "被", "把", "让", "用",
    "想", "看", "听", "知道", "觉得", "感觉", "应该", "可能", "大概", "也许",
    "似乎", "好像", "比如", "例如", "关于", "对于", "通过", "根据", "为了",
    "由于", "随着", "按照", "经过", "除了", "只有", "只要", "不仅", "不但",
    "既", "又", "与其", "不如", "宁可", "即使", "无论", "不管", "总是", "从来",
    "一直", "曾经", "刚刚", "正在", "将要", "马上", "立刻", "顿时", "忽然",
    "渐渐", "逐渐", "慢慢", "悄悄", "明明", "偏偏", "简直", "几乎", "差不多",
    "或许", "恐怕", "难道", "究竟", "到底", "毕竟", "居然", "竟然", "果然",
    "幸亏", "难怪", "原来", "事实上", "实际上", "当然", "自然", "显然", "明显",
    "确实", "的确", "实在", "根本", "完全", "所有", "一切", "整个", "每", "各",
    "某", "另", "其他", "另外", "其余", "剩下", "以上", "以下", "以内", "以外",
    "之前", "之后", "以前", "以后", "上面", "下面", "里面", "外面", "前面", "后面",
    "左边", "右边", "中间", "旁边", "附近", "周围", "到处", "处处", "哪里", "这儿",
    "那儿", "这里", "那里", "此时", "此刻", "当时", "那时", "今天", "明天", "昨天",
    "现在", "过去", "将来", "未来", "刚才", "终于", "最终", "最后", "结果", "总之",
    "因此", "因而", "从而", "以致", "以至", "于是", "接着", "随后", "首先", "其次",
    "再次", "第一", "第二", "第三", "一方面", "另一方面", "知乎", "zhihu", "问题",
    "回答", "答案", "评论", "用户", "作者", "编辑", "发布", "更新", "赞同", "喜欢",
    "收藏", "分享", "举报", "折叠", "删除", "修改", "建议", "感谢", "关注", "粉丝",
    "文章", "想法", "专栏", "话题", "圈子", "直播", "视频", "图片", "文字", "链接",
    "引用", "回复", "点赞", "点踩", "反对", "没有帮助", "作者", "本人", "个人",
    "认为", "觉得", "表示", "指出", "说明", "提到", "讲", "问", "答", "写", "读",
    "学", "教", "买", "卖", "吃", "喝", "玩", "睡", "走", "跑", "飞", "开", "关",
    "上", "下", "左", "右", "前", "后", "里", "外", "中", "内", "旁", "间", "底",
    "顶", "边", "面", "头", "尾", "始", "终", "初", "末", "早", "晚", "先", "后",
    "新", "旧", "好", "坏", "大", "小", "多", "少", "高", "低", "长", "短", "远",
    "近", "快", "慢", "强", "弱", "厚", "薄", "重", "轻", "难", "易", "真", "假",
    "对", "错", "是", "非", "正", "反", "男", "女", "老", "少", "胖", "瘦", "美",
    "丑", "善", "恶", "穷", "富", "贵", "贱", "忙", "闲", "累", "闲", "饿", "饱",
    "渴", "困", "醒", "病", "健", "死", "活", "生", "灭", "成", "败", "胜", "负",
    "赢", "输", "得", "失", "增", "减", "升", "降", "涨", "跌", "进", "出", "入",
    "存", "取", "借", "贷", "买", "卖", "租", "售", "赚", "赔", "花", "省", "费",
    "用", "废", "弃", "留", "扔", "丢", "找", "寻", "追", "赶", "等", "待", "停",
    "走", "行", "坐", "站", "躺", "趴", "蹲", "跪", "爬", "跳", "跑", "飞", "游",
    "骑", "驾", "乘", "坐", "搬", "运", "送", "拿", "提", "扛", "背", "抱", "推",
    "拉", "拽", "拖", "抬", "举", "放", "摆", "挂", "贴", "装", "拆", "拼", "凑",
    "组", "建", "造", "做", "制", "作", "写", "画", "涂", "抹", "剪", "切", "割",
    "砍", "劈", "砸", "敲", "打", "击", "拍", "摸", "抓", "握", "捏", "掐", "揉",
    "搓", "洗", "擦", "扫", "拖", "抹", "刷", "冲", "泡", "煮", "炒", "烤", "炸",
    "蒸", "炖", "焖", "煲", "拌", "腌", "酱", "醋", "盐", "糖", "油", "酒", "茶",
    "水", "饭", "菜", "肉", "鱼", "鸡", "鸭", "鹅", "猪", "牛", "羊", "狗", "猫",
    "鸟", "虫", "花", "草", "树", "林", "山", "水", "河", "湖", "海", "江", "洋",
    "云", "雨", "雪", "风", "雷", "电", "日", "月", "星", "天", "地", "人", "口",
    "手", "脚", "头", "眼", "耳", "鼻", "舌", "牙", "心", "肝", "脾", "肺", "肾",
    "胃", "肠", "脑", "骨", "肉", "皮", "毛", "血", "汗", "泪", "尿", "便", "精",
    "气", "神", "魂", "魄", "梦", "想", "思", "念", "意", "志", "情", "感", "爱",
    "恨", "喜", "怒", "哀", "乐", "忧", "愁", "烦", "闷", "慌", "忙", "急", "躁",
    "平静", "安静", "热闹", "吵", "乱", "整齐", "干净", "脏", "臭", "香", "甜",
    "酸", "苦", "辣", "咸", "淡", "浓", "稀", "干", "湿", "软", "硬", "滑", "涩",
    "亮", "暗", "明", "黑", "白", "红", "黄", "蓝", "绿", "紫", "灰", "粉", "橙",
    "色", "彩", "光", "影", "声", "音", "响", "味", "觉", "感", "知", "识", "理",
    "法", "道", "术", "器", "具", "物", "事", "情", "景", "象", "现", "状", "态",
    "势", "形", "式", "样", "种", "类", "别", "级", "等", "层", "次", "批", "群",
    "堆", "束", "串", "排", "列", "行", "列", "队", "伍", "组", "班", "队", "团",
    "社", "会", "国", "家", "市", "区", "县", "镇", "乡", "村", "街", "路", "巷",
    "楼", "房", "屋", "室", "厅", "厨", "卫", "门", "窗", "墙", "顶", "地", "板",
    "桌", "椅", "床", "柜", "架", "箱", "包", "袋", "瓶", "罐", "盒", "盘", "碗",
    "筷", "勺", "刀", "叉", "杯", "壶", "锅", "盆", "桶", "篮", "网", "绳", "线",
    "带", "链", "环", "圈", "钉", "螺丝", "胶", "漆", "油", "墨", "笔", "纸", "书",
    "本", "册", "页", "张", "片", "块", "条", "根", "支", "枝", "棵", "株", "朵",
    "片", "颗", "粒", "滴", "杯", "碗", "盆", "桶", "箱", "包", "袋", "群", "批",
    "堆", "束", "串", "排", "列", "行", "队", "组", "班", "队", "团", "社", "会",
}

# 精华关键词（高质量回答常出现的词）
QUALITY_KEYWORDS = {
    "首先", "其次", "最后", "总结", "综上", "因此", "所以", "因为", "原因",
    "分析", "研究", "数据", "实验", "证明", "证据", "例子", "案例", "经验",
    "建议", "方法", "步骤", "流程", "技巧", "攻略", "指南", "教程", "原理",
    "本质", "核心", "关键", "重点", "注意", "提醒", "警告", "对比", "比较",
    "区别", "相同", "不同", "优势", "劣势", "优点", "缺点", "好处", "坏处",
    "影响", "作用", "功能", "效果", "结果", "结论", "观点", "看法", "态度",
    "立场", "角度", "层面", "维度", "层次", "深度", "广度", "高度", "程度",
    "专业", "深入", "详细", "全面", "系统", "完整", "清晰", "明确", "具体",
    "实际", "实用", "有效", "靠谱", "真实", "客观", "理性", "逻辑", "严谨",
}


# ============================================================
# 工具函数
# ============================================================

def print_progress(current, total, prefix=""):
    """打印进度条"""
    percent = current / total * 100 if total > 0 else 0
    bar_len = 30
    filled = int(bar_len * current / total) if total > 0 else 0
    bar = "█" * filled + "░" * (bar_len - filled)
    print(f"\r{prefix} [{bar}] {current}/{total} ({percent:.1f}%)", end="", flush=True)
    if current >= total:
        print()


def safe_get(url, params=None, cookies=None, retries=3, delay=2):
    """带重试的GET请求，自动加x-zse-96签名"""
    from urllib.parse import urlparse
    # 提取URL路径用于签名
    parsed = urlparse(url)
    url_path = parsed.path
    if params:
        from urllib.parse import urlencode
        url_path = f"{url_path}?{urlencode(params)}"
    
    # 生成签名
    headers = dict(HEADERS)
    if ZHIHU_DC0:
        headers["x-zse-96"] = sign_zhihu_request(url_path)
    
    for i in range(retries):
        try:
            resp = requests.get(url, params=params, headers=headers,
                                cookies=cookies, timeout=15)
            if resp.status_code == 401:
                print("\n❌ 401未授权，请检查Cookie是否正确")
                return None
            if resp.status_code == 429:
                print(f"\n⚠️  请求过于频繁，等待{delay*2}秒后重试...")
                time.sleep(delay * 2)
                continue
            resp.raise_for_status()
            return resp
        except Exception as e:
            if i < retries - 1:
                time.sleep(delay)
            else:
                print(f"\n⚠️  请求失败: {e}")
                return None


def extract_question_id(input_str):
    """从输入中提取问题ID"""
    match = re.search(r"question/(\d+)", input_str)
    if match:
        return match.group(1)
    match = re.search(r"(\d{6,})", input_str)
    if match:
        return match.group(1)
    return input_str.strip()


def clean_html(html_text):
    """清洗HTML标签，提取纯文本"""
    if not html_text:
        return ""
    # 去除图片、链接等标签但保留文本
    text = re.sub(r"<[^>]+>", "", html_text)
    # 去除HTML实体
    text = re.sub(r"&[a-zA-Z]+;", " ", text)
    text = re.sub(r"&#\d+;", " ", text)
    # 去除多余空白
    text = re.sub(r"\s+", " ", text).strip()
    return text


def load_cookie(cookie_str=None, cookie_file=None):
    """加载Cookie"""
    cookies = {}
    if cookie_file and os.path.exists(cookie_file):
        with open(cookie_file, "r", encoding="utf-8") as f:
            cookie_str = f.read().strip()

    if cookie_str:
        # 支持多种格式：z_c0=xxx 或 完整Cookie字符串
        if "=" in cookie_str:
            for pair in cookie_str.split(";"):
                pair = pair.strip()
                if "=" in pair:
                    k, v = pair.split("=", 1)
                    cookies[k.strip()] = v.strip()
        else:
            # 只有z_c0的值
            cookies["z_c0"] = cookie_str.strip()

    return cookies


# ============================================================
# 知乎API
# ============================================================

def get_question_info(qid, cookies=None):
    """获取问题基本信息"""
    url = f"https://www.zhihu.com/api/v4/questions/{qid}"
    resp = safe_get(url, cookies=cookies)
    if not resp:
        return None
    data = resp.json()
    return {
        "id": qid,
        "title": data.get("title", ""),
        "detail": clean_html(data.get("detail", "")),
        "answer_count": data.get("answer_count", 0),
        "follower_count": data.get("follower_count", 0),
        "comment_count": data.get("comment_count", 0),
        "created": datetime.fromtimestamp(data.get("created", 0)).strftime("%Y-%m-%d"),
        "updated_time": datetime.fromtimestamp(data.get("updated_time", 0)).strftime("%Y-%m-%d %H:%M"),
    }


def get_answers(qid, cookies=None, max_pages=100, sort_by="default"):
    """爬取问题下的所有回答"""
    all_answers = []
    url = f"https://www.zhihu.com/api/v4/questions/{qid}/answers"

    offset = 0
    limit = 20
    page = 0
    total = None

    while page < max_pages:
        params = {
            "include": "data[*].content,excerpt,voteup_count,comment_count,"
                       "created_time,updated_time,author[*].name,follower_count,"
                       "gender,headline,is_org",
            "limit": limit,
            "offset": offset,
            "sort_by": sort_by,  # default=默认, created=按时间
        }
        resp = safe_get(url, params=params, cookies=cookies)
        if not resp:
            break

        data = resp.json()
        answers = data.get("data", [])
        if not answers:
            break

        if total is None:
            total = data.get("paging", {}).get("totals", len(answers))

        for ans in answers:
            author = ans.get("author", {})
            content_html = ans.get("content", "")
            content_text = clean_html(content_html)

            answer = {
                "id": ans["id"],
                "author": author.get("name", "匿名用户"),
                "author_followers": author.get("follower_count", 0),
                "author_headline": author.get("headline", ""),
                "content": content_text,
                "content_html": content_html,
                "excerpt": ans.get("excerpt", ""),
                "voteup_count": ans.get("voteup_count", 0),
                "comment_count": ans.get("comment_count", 0),
                "created_time": datetime.fromtimestamp(ans.get("created_time", 0)).strftime("%Y-%m-%d %H:%M"),
                "updated_time": datetime.fromtimestamp(ans.get("updated_time", 0)).strftime("%Y-%m-%d %H:%M"),
                "content_length": len(content_text),
                "comments": [],
            }
            all_answers.append(answer)

        # 检查是否还有下一页
        paging = data.get("paging", {})
        if paging.get("is_end", True):
            break

        offset += limit
        page += 1
        print_progress(page, max_pages, f"爬取回答中 (共约{total}条)")
        time.sleep(1)  # 知乎反爬，加延时

    return all_answers


def get_answer_comments(answer_id, cookies=None, max_comments=50):
    """爬取单个回答的评论"""
    comments = []
    url = f"https://www.zhihu.com/api/v4/answers/{answer_id}/comments"

    offset = 0
    limit = 20
    fetched = 0

    while fetched < max_comments:
        params = {
            "include": "data[*].author[*].name,content,vote_count,created_time",
            "limit": limit,
            "offset": offset,
        }
        resp = safe_get(url, params=params, cookies=cookies)
        if not resp:
            break

        data = resp.json()
        batch = data.get("data", [])
        if not batch:
            break

        for c in batch:
            author = c.get("author", {})
            comments.append({
                "id": c["id"],
                "author": author.get("name", "匿名用户"),
                "content": clean_html(c.get("content", "")),
                "vote_count": c.get("vote_count", 0),
                "created_time": datetime.fromtimestamp(c.get("created_time", 0)).strftime("%Y-%m-%d %H:%M"),
            })
            fetched += 1
            if fetched >= max_comments:
                break

        if data.get("paging", {}).get("is_end", True):
            break

        offset += limit
        time.sleep(0.5)

    return comments


# ============================================================
# 智能精华评分系统
# ============================================================

def calculate_quality_score(answer, all_answers):
    """
    多维度智能评分，筛选精华回答
    评分维度：
    1. 赞同数（40%）- 社区认可
    2. 评论数（15%）- 讨论热度
    3. 内容长度（15%）- 信息量（适中最佳）
    4. 关键词密度（15%）- 专业度信号
    5. 作者影响力（10%）- 作者粉丝数
    6. 时效性（5%）- 更新时间
    """
    import math

    # 1. 赞同数评分（对数归一化）
    max_votes = max(a["voteup_count"] for a in all_answers) if all_answers else 1
    vote_score = min(math.log1p(answer["voteup_count"]) / math.log1p(max_votes) * 100, 100) if max_votes > 0 else 0

    # 2. 评论数评分
    max_comments = max(a["comment_count"] for a in all_answers) if all_answers else 1
    comment_score = min(math.log1p(answer["comment_count"]) / math.log1p(max_comments) * 100, 100) if max_comments > 0 else 0

    # 3. 内容长度评分（500-3000字最佳，太短或太长扣分）
    length = answer["content_length"]
    if length < 100:
        length_score = length / 100 * 40  # 太短低分
    elif length < 500:
        length_score = 40 + (length - 100) / 400 * 30
    elif length <= 3000:
        length_score = 70 + (length - 500) / 2500 * 30  # 最佳区间
    elif length <= 8000:
        length_score = 100 - (length - 3000) / 5000 * 20
    else:
        length_score = max(80 - (length - 8000) / 1000 * 5, 30)

    # 4. 关键词密度（专业词汇占比）
    content = answer["content"]
    keyword_hits = sum(1 for kw in QUALITY_KEYWORDS if kw in content)
    keyword_density = keyword_hits / max(length / 100, 1)  # 每100字的关键词数
    keyword_score = min(keyword_density * 20, 100)

    # 5. 作者影响力
    max_followers = max(a["author_followers"] for a in all_answers) if all_answers else 1
    author_score = min(math.log1p(answer["author_followers"]) / math.log1p(max_followers) * 100, 100) if max_followers > 0 else 0

    # 6. 时效性（最近更新有加成）
    try:
        update_date = datetime.strptime(answer["updated_time"], "%Y-%m-%d %H:%M")
        days_ago = (datetime.now() - update_date).days
        if days_ago < 30:
            time_score = 100
        elif days_ago < 180:
            time_score = 100 - (days_ago - 30) / 150 * 30
        else:
            time_score = max(70 - (days_ago - 180) / 365 * 20, 30)
    except Exception:
        time_score = 60

    # 加权总分
    total_score = (
        vote_score * 0.40 +
        comment_score * 0.15 +
        length_score * 0.15 +
        keyword_score * 0.15 +
        author_score * 0.10 +
        time_score * 0.05
    )

    return {
        "total": round(total_score, 1),
        "vote_score": round(vote_score, 1),
        "comment_score": round(comment_score, 1),
        "length_score": round(length_score, 1),
        "keyword_score": round(keyword_score, 1),
        "author_score": round(author_score, 1),
        "time_score": round(time_score, 1),
    }


# ============================================================
# 数据分析
# ============================================================

def get_word_frequency(texts, top_n=30):
    """词频统计"""
    try:
        import jieba
        all_words = []
        for text in texts:
            if not text:
                continue
            text = re.sub(r"[^\u4e00-\u9fa5a-zA-Z0-9]", " ", text)
            words = jieba.lcut(text)
            for w in words:
                w = w.strip()
                if len(w) > 1 and w not in STOP_WORDS and not w.isdigit():
                    all_words.append(w)
        counter = Counter(all_words)
        return counter.most_common(top_n)
    except ImportError:
        print("⚠️  未安装jieba，词频分析已跳过。执行: pip install jieba")
        return []


def analyze_answers(answers):
    """分析回答数据"""
    if not answers:
        return {}

    # 所有回答文本
    all_texts = [a["content"] for a in answers]

    # 词频
    word_freq = get_word_frequency(all_texts)

    # 长度分布
    length_bins = {"<100字": 0, "100-500字": 0, "500-2000字": 0, "2000-5000字": 0, ">5000字": 0}
    for a in answers:
        l = a["content_length"]
        if l < 100:
            length_bins["<100字"] += 1
        elif l < 500:
            length_bins["100-500字"] += 1
        elif l < 2000:
            length_bins["500-2000字"] += 1
        elif l < 5000:
            length_bins["2000-5000字"] += 1
        else:
            length_bins[">5000字"] += 1

    # 赞同数分布
    vote_bins = {"0-10": 0, "10-100": 0, "100-1000": 0, "1000-10000": 0, ">10000": 0}
    for a in answers:
        v = a["voteup_count"]
        if v < 10:
            vote_bins["0-10"] += 1
        elif v < 100:
            vote_bins["10-100"] += 1
        elif v < 1000:
            vote_bins["100-1000"] += 1
        elif v < 10000:
            vote_bins["1000-10000"] += 1
        else:
            vote_bins[">10000"] += 1

    # 评论词频
    all_comments = []
    for a in answers:
        for c in a["comments"]:
            all_comments.append(c["content"])
    comment_word_freq = get_word_frequency(all_comments, top_n=20)

    # 热门评论
    hot_comments = []
    for a in answers:
        for c in a["comments"]:
            hot_comments.append({**c, "answer_author": a["author"], "answer_excerpt": a["excerpt"][:50]})
    hot_comments = sorted(hot_comments, key=lambda x: x["vote_count"], reverse=True)[:15]

    return {
        "total": len(answers),
        "word_freq": word_freq,
        "length_bins": length_bins,
        "vote_bins": vote_bins,
        "comment_word_freq": comment_word_freq,
        "hot_comments": hot_comments,
        "total_comments": len(all_comments),
    }


# ============================================================
# HTML报告生成
# ============================================================

def markdown_to_html(text):
    """简单的Markdown转HTML，处理标题、加粗、列表、段落"""
    if not text:
        return ""

    lines = text.split("\n")
    html_lines = []
    in_list = False
    in_ol = False

    for line in lines:
        stripped = line.strip()

        # 空行：结束列表
        if not stripped:
            if in_list:
                html_lines.append("</ul>")
                in_list = False
            if in_ol:
                html_lines.append("</ol>")
                in_ol = False
            continue

        # 标题
        if stripped.startswith("#### "):
            if in_list: html_lines.append("</ul>"); in_list = False
            if in_ol: html_lines.append("</ol>"); in_ol = False
            html_lines.append(f"<h5>{stripped[5:]}</h5>")
            continue
        if stripped.startswith("### "):
            if in_list: html_lines.append("</ul>"); in_list = False
            if in_ol: html_lines.append("</ol>"); in_ol = False
            html_lines.append(f"<h4>{stripped[4:]}</h4>")
            continue
        if stripped.startswith("## "):
            if in_list: html_lines.append("</ul>"); in_list = False
            if in_ol: html_lines.append("</ol>"); in_ol = False
            html_lines.append(f"<h4>{stripped[3:]}</h4>")
            continue
        if stripped.startswith("# "):
            if in_list: html_lines.append("</ul>"); in_list = False
            if in_ol: html_lines.append("</ol>"); in_ol = False
            html_lines.append(f"<h3>{stripped[2:]}</h3>")
            continue

        # 无序列表
        if stripped.startswith("- ") or stripped.startswith("* "):
            if not in_list:
                if in_ol: html_lines.append("</ol>"); in_ol = False
                html_lines.append("<ul>")
                in_list = True
            content = stripped[2:]
            # 处理加粗
            import re
            content = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', content)
            html_lines.append(f"<li>{content}</li>")
            continue

        # 有序列表
        import re
        ol_match = re.match(r'^(\d+)\.\s+(.+)$', stripped)
        if ol_match:
            if not in_ol:
                if in_list: html_lines.append("</ul>"); in_list = False
                html_lines.append("<ol>")
                in_ol = True
            content = ol_match.group(2)
            content = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', content)
            html_lines.append(f"<li>{content}</li>")
            continue

        # 普通段落：处理加粗
        if in_list: html_lines.append("</ul>"); in_list = False
        if in_ol: html_lines.append("</ol>"); in_ol = False
        content = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', stripped)
        html_lines.append(f"<p>{content}</p>")

    # 结束未闭合的列表
    if in_list: html_lines.append("</ul>")
    if in_ol: html_lines.append("</ol>")

    return "\n".join(html_lines)


def generate_html_report(question_info, answers, analysis, output_path, ai_summary=None, multi_analysis=None):
    """生成HTML分析报告"""

    # 精华回答（按评分排序，取前10）
    top_answers = sorted(answers, key=lambda x: x["quality_score"]["total"], reverse=True)[:10]
    # 高赞回答
    top_voted = sorted(answers, key=lambda x: x["voteup_count"], reverse=True)[:10]

    # 生成精华回答HTML
    top_answers_html = ""
    for i, a in enumerate(top_answers, 1):
        score = a["quality_score"]
        # 截取前500字作为摘要
        excerpt = a["content"][:500] + "..." if len(a["content"]) > 500 else a["content"]
        top_answers_html += f"""
        <div class="answer-card">
            <div class="answer-rank">#{i}</div>
            <div class="answer-body">
                <div class="answer-header">
                    <span class="answer-author">{a['author']}</span>
                    <span class="answer-headline">{a['author_headline']}</span>
                    <span class="answer-score">精华评分: {score['total']}</span>
                </div>
                <div class="answer-meta">
                    <span>👍 {a['voteup_count']:,} 赞同</span>
                    <span>💬 {a['comment_count']} 评论</span>
                    <span>📝 {a['content_length']} 字</span>
                    <span>🕐 {a['updated_time']}</span>
                </div>
                <div class="answer-score-bar">
                    <span title="赞同数">👍{score['vote_score']}</span>
                    <span title="评论数">💬{score['comment_score']}</span>
                    <span title="内容长度">📏{score['length_score']}</span>
                    <span title="关键词密度">🔑{score['keyword_score']}</span>
                    <span title="作者影响力">👤{score['author_score']}</span>
                    <span title="时效性">⏰{score['time_score']}</span>
                </div>
                <div class="answer-content">{excerpt}</div>
                <div class="answer-tags">
                    <span class="tag tag-vote">赞同 {a['voteup_count']:,}</span>
                    <span class="tag tag-comment">评论 {a['comment_count']}</span>
                    <span class="tag tag-length">{a['content_length']}字</span>
                </div>
            </div>
        </div>
        """

    # 生成热门评论HTML
    hot_comments_html = ""
    for i, c in enumerate(analysis.get("hot_comments", []), 1):
        hot_comments_html += f"""
        <div class="comment-item">
            <div class="comment-rank">#{i}</div>
            <div class="comment-body">
                <div class="comment-header">
                    <span class="comment-user">{c['author']}</span>
                    <span class="comment-like">👍 {c['vote_count']}</span>
                    <span class="comment-time">{c['created_time']}</span>
                </div>
                <div class="comment-content">{c['content']}</div>
                <div class="comment-source">回复: {c['answer_author']} 的回答</div>
            </div>
        </div>
        """

    word_freq = analysis.get("word_freq", [])
    comment_word_freq = analysis.get("comment_word_freq", [])
    length_bins = analysis.get("length_bins", {})
    vote_bins = analysis.get("vote_bins", {})

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>知乎问题分析 - {question_info['title']}</title>
    <script src="https://cdn.jsdelivr.net/npm/echarts@5.4.3/dist/echarts.min.js"></script>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif;
            background: #f0f2f5;
            color: #333;
            font-size: 15px;
            line-height: 1.7;
        }}
        .header {{
            background: linear-gradient(135deg, #0066ff 0%, #0084ff 50%, #00a6ff 100%);
            color: white;
            padding: 36px 48px;
        }}
        .header h1 {{ font-size: 28px; margin-bottom: 16px; line-height: 1.4; }}
        .question-meta {{ display: flex; gap: 24px; flex-wrap: wrap; font-size: 15px; opacity: 0.95; }}
        .container {{ max-width: 100%; margin: 0 auto; padding: 20px 32px; }}
        .stats-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
            gap: 16px;
            margin-bottom: 24px;
        }}
        .stat-card {{
            background: white;
            border-radius: 12px;
            padding: 24px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.08);
            text-align: center;
        }}
        .stat-card .label {{ font-size: 15px; color: #999; margin-bottom: 10px; }}
        .stat-card .value {{ font-size: 34px; font-weight: 700; color: #0066ff; }}
        .stat-card .sub {{ font-size: 14px; color: #bbb; margin-top: 8px; }}
        .tabs {{
            display: flex;
            gap: 6px;
            background: white;
            padding: 10px;
            border-radius: 12px;
            margin-bottom: 20px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.08);
            flex-wrap: wrap;
        }}
        .tab {{
            padding: 12px 24px;
            border-radius: 8px;
            cursor: pointer;
            font-size: 15px;
            transition: all 0.2s;
            color: #666;
        }}
        .tab:hover {{ background: #f5f5f5; }}
        .tab.active {{ background: #0066ff; color: white; font-weight: 500; }}
        .chart-container {{
            background: white;
            border-radius: 12px;
            padding: 24px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.08);
            margin-bottom: 28px;
        }}
        .chart-container h3 {{
            font-size: 19px;
            margin-bottom: 20px;
            padding-left: 12px;
            border-left: 4px solid #0066ff;
        }}
        .chart {{ width: 100%; height: 700px; font-size: 14px; line-height: 1.5; }}
        .chart canvas, .chart svg {{ display: block; }}
        .hidden {{ display: none; }}
        .answer-card {{
            display: flex;
            gap: 16px;
            padding: 20px;
            border-bottom: 1px solid #f0f0f0;
        }}
        .answer-rank {{
            width: 40px;
            height: 40px;
            background: linear-gradient(135deg, #0066ff, #00a6ff);
            color: white;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            font-weight: 600;
            font-size: 14px;
            flex-shrink: 0;
        }}
        .answer-body {{ flex: 1; min-width: 0; }}
        .answer-header {{
            display: flex;
            align-items: center;
            gap: 10px;
            margin-bottom: 8px;
            flex-wrap: wrap;
        }}
        .answer-author {{ color: #0066ff; font-weight: 600; font-size: 16px; }}
        .answer-headline {{ color: #999; font-size: 14px; }}
        .answer-score {{
            margin-left: auto;
            background: linear-gradient(135deg, #ff6b6b, #ffa502);
            color: white;
            padding: 5px 14px;
            border-radius: 12px;
            font-size: 14px;
            font-weight: 600;
        }}
        .answer-meta {{
            display: flex;
            gap: 16px;
            font-size: 14px;
            color: #888;
            margin-bottom: 10px;
            flex-wrap: wrap;
        }}
        .answer-score-bar {{
            display: flex;
            gap: 8px;
            margin-bottom: 10px;
            flex-wrap: wrap;
        }}
        .answer-score-bar span {{
            background: #f0f7ff;
            color: #0066ff;
            padding: 2px 8px;
            border-radius: 4px;
            font-size: 11px;
        }}
        .answer-content {{
            font-size: 15px;
            line-height: 1.9;
            color: #444;
            margin-bottom: 12px;
            display: -webkit-box;
            -webkit-line-clamp: 8;
            -webkit-box-orient: vertical;
            overflow: hidden;
        }}
        .answer-tags {{ display: flex; gap: 8px; }}
        .tag {{
            padding: 3px 10px;
            border-radius: 4px;
            font-size: 12px;
        }}
        .tag-vote {{ background: #fff1f0; color: #ff4d4f; }}
        .tag-comment {{ background: #e6f7ff; color: #1890ff; }}
        .tag-length {{ background: #f6ffed; color: #52c41a; }}
        .comment-item {{
            display: flex;
            gap: 12px;
            padding: 14px;
            border-bottom: 1px solid #f0f0f0;
        }}
        .comment-rank {{
            width: 32px;
            height: 32px;
            background: #0084ff;
            color: white;
            border-radius: 6px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 12px;
            font-weight: 600;
            flex-shrink: 0;
        }}
        .comment-body {{ flex: 1; }}
        .comment-header {{
            display: flex;
            gap: 12px;
            margin-bottom: 6px;
            font-size: 13px;
        }}
        .comment-user {{ color: #0066ff; font-weight: 500; }}
        .comment-like {{ color: #999; }}
        .comment-time {{ color: #bbb; margin-left: auto; }}
        .comment-content {{ font-size: 14px; line-height: 1.6; color: #333; }}
        .comment-source {{ font-size: 12px; color: #aaa; margin-top: 6px; }}
        .insight-box {{
            background: linear-gradient(135deg, #e6f4ff 0%, #f0f5ff 100%);
            border-radius: 10px;
            padding: 20px;
            margin-bottom: 24px;
            border-left: 4px solid #0066ff;
        }}
        .insight-box h4 {{ font-size: 15px; margin-bottom: 12px; color: #0066ff; }}
        .insight-box ul {{ padding-left: 20px; }}
        .insight-box li {{ margin-bottom: 8px; font-size: 14px; line-height: 1.6; }}
        .ai-summary {{
            background: linear-gradient(135deg, #f0f9ff 0%, #faf5ff 100%);
            border-radius: 12px;
            padding: 28px;
            margin-bottom: 24px;
            border-left: 4px solid #8b5cf6;
        }}
        .ai-summary h3 {{ font-size: 18px; margin-bottom: 16px; color: #7c3aed; display: flex; align-items: center; gap: 8px; }}
        .ai-summary h4 {{ font-size: 15px; margin: 18px 0 10px 0; color: #6d28d9; border-bottom: 1px solid #e9d5ff; padding-bottom: 6px; }}
        .ai-summary p {{ font-size: 16px; line-height: 2.0; color: #333; margin-bottom: 12px; }}
        .ai-summary ul {{ padding-left: 24px; margin-bottom: 12px; }}
        .ai-summary li {{ font-size: 16px; line-height: 2.0; color: #333; margin-bottom: 8px; }}
        .ai-summary h3 {{ font-size: 20px; margin: 24px 0 14px 0; color: #6d28d9; border-bottom: 2px solid #ddd6fe; padding-bottom: 8px; }}
        .ai-summary h4 {{ font-size: 18px; margin: 20px 0 12px 0; color: #7c3aed; }}
        .ai-summary ul {{ padding-left: 20px; margin-bottom: 10px; }}
        .ai-summary li {{ font-size: 14px; line-height: 1.8; color: #444; margin-bottom: 6px; }}
        .ai-summary strong {{ color: #7c3aed; }}
        .ai-badge {{ display: inline-block; background: linear-gradient(135deg, #8b5cf6, #ec4899); color: white; padding: 2px 10px; border-radius: 12px; font-size: 11px; font-weight: 500; }}
        .multi-analysis {{
            background: linear-gradient(135deg, #fff7ed 0%, #fef3c7 100%);
            border-radius: 12px;
            padding: 28px;
            margin-bottom: 24px;
            border-left: 4px solid #f59e0b;
        }}
        .multi-analysis h3 {{ font-size: 20px; margin-bottom: 16px; color: #d97706; display: flex; align-items: center; gap: 8px; }}
        .multi-analysis h4 {{ font-size: 18px; margin: 20px 0 12px 0; color: #b45309; border-bottom: 2px solid #fde68a; padding-bottom: 8px; }}
        .multi-analysis p {{ font-size: 16px; line-height: 2.0; color: #333; margin-bottom: 12px; }}
        .multi-analysis ul {{ padding-left: 24px; margin-bottom: 12px; }}
        .multi-analysis li {{ font-size: 16px; line-height: 2.0; color: #333; margin-bottom: 8px; }}
        .multi-analysis strong {{ color: #d97706; }}
        .multi-badge {{ display: inline-block; background: linear-gradient(135deg, #f59e0b, #ef4444); color: white; padding: 2px 10px; border-radius: 12px; font-size: 11px; font-weight: 500; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>💡 {question_info['title']}</h1>
        <div class="question-meta">
            <span>📝 回答数: {question_info['answer_count']:,}</span>
            <span>👥 关注者: {question_info['follower_count']:,}</span>
            <span>💬 评论数: {question_info['comment_count']:,}</span>
            <span>📅 创建于: {question_info['created']}</span>
            <span>🕐 最后更新: {question_info['updated_time']}</span>
        </div>
    </div>

    <div class="container">
        <!-- 统计卡片 -->
        <div class="stats-grid">
            <div class="stat-card"><div class="label">爬取回答</div><div class="value">{analysis.get('total', 0)}</div><div class="sub">条回答</div></div>
            <div class="stat-card"><div class="label">爬取评论</div><div class="value">{analysis.get('total_comments', 0)}</div><div class="sub">条评论</div></div>
            <div class="stat-card"><div class="label">精华回答</div><div class="value">{len(top_answers)}</div><div class="sub">智能筛选TOP10</div></div>
            <div class="stat-card"><div class="label">最高赞同</div><div class="value">{top_voted[0]['voteup_count']:,}</div><div class="sub">{top_voted[0]['author']}</div></div>
            <div class="stat-card"><div class="label">最热关键词</div><div class="value" style="font-size:18px;">{word_freq[0][0] if word_freq else '无'}</div><div class="sub">{word_freq[0][1] if word_freq else 0}次</div></div>
        </div>

        <!-- 洞察 -->
        <div class="insight-box">
            <h4>🎯 智能分析洞察</h4>
            <ul>
                <li>📌 讨论最热关键词：「<strong>{word_freq[0][0] if word_freq else '无'}</strong>」（{word_freq[0][1] if word_freq else 0}次）</li>
                <li>🏆 精华回答第一名：<strong>{top_answers[0]['author']}</strong>（评分 {top_answers[0]['quality_score']['total']}，{top_answers[0]['voteup_count']:,}赞同）</li>
                <li>👍 最高赞回答：<strong>{top_voted[0]['author']}</strong>（{top_voted[0]['voteup_count']:,}赞同，{top_voted[0]['content_length']}字）</li>
                <li>💬 评论区最热词：「<strong>{comment_word_freq[0][0] if comment_word_freq else '无'}</strong>」（{comment_word_freq[0][1] if comment_word_freq else 0}次）</li>
                <li>📊 回答长度分布：{length_bins.get('500-2000字', 0)}篇中等长度（500-2000字），占比 {length_bins.get('500-2000字', 0)/max(analysis.get('total',1),1)*100:.1f}%</li>
            </ul>
        </div>

        <!-- AI深度总结 -->
        {f'''
        <div class="ai-summary">
            <h3>🤖 AI深度总结 <span class="ai-badge">DeepSeek生成</span></h3>
            {markdown_to_html(ai_summary)}
        </div>
        ''' if ai_summary else ''}

        <!-- 多源融合分析 -->
        {f'''
        <div class="multi-analysis">
            <h3>🧠 多源融合深度分析 <span class="multi-badge">书籍+视角+回答</span></h3>
            {markdown_to_html(multi_analysis)}
        </div>
        ''' if multi_analysis else ''}

        <!-- 标签页 -->
        <div class="tabs">
            <div class="tab active" data-tab="essence">🏆 精华回答</div>
            <div class="tab" data-tab="wordfreq">🔤 回答词频</div>
            <div class="tab" data-tab="commentword">💬 评论词频</div>
            <div class="tab" data-tab="length">📏 长度分布</div>
            <div class="tab" data-tab="vote">👍 赞同分布</div>
            <div class="tab" data-tab="hotcomment">🔥 热门评论</div>
            <div class="tab" data-tab="topvoted">📈 高赞回答</div>
        </div>

        <!-- 精华回答 -->
        <div class="chart-container" id="panel-essence">
            <h3>🏆 智能筛选精华回答TOP10（多维度评分）</h3>
            {top_answers_html}
        </div>

        <!-- 回答词频 -->
        <div class="chart-container hidden" id="panel-wordfreq">
            <h3>回答内容关键词TOP30</h3>
            <div class="chart" id="chart-wordfreq"></div>
        </div>

        <!-- 评论词频 -->
        <div class="chart-container hidden" id="panel-commentword">
            <h3>评论区关键词TOP20</h3>
            <div class="chart" id="chart-commentword"></div>
        </div>

        <!-- 长度分布 -->
        <div class="chart-container hidden" id="panel-length">
            <h3>回答长度分布</h3>
            <div class="chart" id="chart-length"></div>
        </div>

        <!-- 赞同分布 -->
        <div class="chart-container hidden" id="panel-vote">
            <h3>回答赞同数分布</h3>
            <div class="chart" id="chart-vote"></div>
        </div>

        <!-- 热门评论 -->
        <div class="chart-container hidden" id="panel-hotcomment">
            <h3>热门评论TOP15</h3>
            {hot_comments_html}
        </div>

        <!-- 高赞回答 -->
        <div class="chart-container hidden" id="panel-topvoted">
            <h3>高赞回答TOP10</h3>
            <div class="chart" id="chart-topvoted"></div>
        </div>
    </div>

    <script>
        // 标签页切换
        document.querySelectorAll('.tab').forEach(tab => {{
            tab.addEventListener('click', () => {{
                document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
                tab.classList.add('active');
                const name = tab.dataset.tab;
                ['essence','wordfreq','commentword','length','vote','hotcomment','topvoted'].forEach(n => {{
                    document.getElementById('panel-' + n).classList.toggle('hidden', n !== name);
                }});
                setTimeout(() => window.dispatchEvent(new Event('resize')), 100);
            }});
        }});

        // 回答词频图
        const wordFreqData = {json.dumps([[w,c] for w,c in word_freq], ensure_ascii=False)};
        if (wordFreqData.length > 0) {{
            const chart1 = echarts.init(document.getElementById('chart-wordfreq'));
            chart1.setOption({{
                tooltip: {{ trigger: 'axis', axisPointer: {{ type: 'shadow' }}, formatter: '{{b}}: {{c}}次' }},
                grid: {{ left: 120, right: 80, top: 30, bottom: 50 }},
                xAxis: {{ type: 'value', name: '出现次数', nameLocation: 'middle', nameGap: 30, minInterval: 1 }},
                yAxis: {{ type: 'category', data: wordFreqData.map(w=>w[0]).reverse(), axisLabel: {{fontSize:14, interval:0, width: 110, overflow: 'truncate'}} }},
                series: [{{
                    data: wordFreqData.map(w=>w[1]).reverse(),
                    type: 'bar',
                    barWidth: '60%',
                    label: {{ show: true, position: 'right', fontSize: 13 }},
                    itemStyle: {{
                        color: new echarts.graphic.LinearGradient(0,0,1,0,[
                            {{offset:0,color:'#0066ff'}},{{offset:1,color:'#00a6ff'}}
                        ]),
                        borderRadius: [0,4,4,0]
                    }}
                }}]
            }});
        }}

        // 评论词频图
        const commentWordData = {json.dumps([[w,c] for w,c in comment_word_freq], ensure_ascii=False)};
        if (commentWordData.length > 0) {{
            const chart2 = echarts.init(document.getElementById('chart-commentword'));
            chart2.setOption({{
                tooltip: {{ trigger: 'axis', axisPointer: {{ type: 'shadow' }}, formatter: '{{b}}: {{c}}次' }},
                grid: {{ left: 120, right: 80, top: 30, bottom: 50 }},
                xAxis: {{ type: 'value', name: '出现次数', nameLocation: 'middle', nameGap: 30, minInterval: 1 }},
                yAxis: {{ type: 'category', data: commentWordData.map(w=>w[0]).reverse(), axisLabel: {{fontSize:14, interval:0, width: 110, overflow: 'truncate'}} }},
                series: [{{
                    data: commentWordData.map(w=>w[1]).reverse(),
                    type: 'bar',
                    barWidth: '60%',
                    label: {{ show: true, position: 'right', fontSize: 13 }},
                    itemStyle: {{
                        color: new echarts.graphic.LinearGradient(0,0,1,0,[
                            {{offset:0,color:'#ff6b6b'}},{{offset:1,color:'#ffa502'}}
                        ]),
                        borderRadius: [0,4,4,0]
                    }}
                }}]
            }});
        }}

        // 长度分布图
        const lengthData = {json.dumps(length_bins, ensure_ascii=False)};
        const chart3 = echarts.init(document.getElementById('chart-length'));
        chart3.setOption({{
            tooltip: {{ trigger: 'axis', axisPointer: {{ type: 'shadow' }}, formatter: '{{b}}: {{c}}篇' }},
            grid: {{ left: 80, right: 40, top: 40, bottom: 80 }},
            xAxis: {{ type: 'category', data: Object.keys(lengthData), axisLabel: {{fontSize:13, interval:0, rotate: 35}} }},
            yAxis: {{ type: 'value', name: '回答数', nameLocation: 'middle', nameGap: 45, minInterval: 1 }},
            series: [{{
                data: Object.values(lengthData),
                type: 'bar',
                barWidth: '55%',
                label: {{ show: true, position: 'top', fontSize: 13 }},
                itemStyle: {{
                    color: new echarts.graphic.LinearGradient(0,0,0,1,[
                        {{offset:0,color:'#0084ff'}},{{offset:1,color:'#00a6ff'}}
                    ]),
                    borderRadius: [4,4,0,0]
                }}
            }}]
        }});

        // 赞同分布图
        const voteData = {json.dumps(vote_bins, ensure_ascii=False)};
        const chart4 = echarts.init(document.getElementById('chart-vote'));
        chart4.setOption({{
            tooltip: {{ trigger: 'axis', axisPointer: {{ type: 'shadow' }}, formatter: '{{b}}赞同: {{c}}篇' }},
            grid: {{ left: 80, right: 40, top: 40, bottom: 80 }},
            xAxis: {{ type: 'category', data: Object.keys(voteData), axisLabel: {{fontSize:13, interval:0, rotate: 35}} }},
            yAxis: {{ type: 'value', name: '回答数', nameLocation: 'middle', nameGap: 45, minInterval: 1 }},
            series: [{{
                data: Object.values(voteData),
                type: 'bar',
                barWidth: '55%',
                label: {{ show: true, position: 'top', fontSize: 13 }},
                itemStyle: {{
                    color: new echarts.graphic.LinearGradient(0,0,0,1,[
                        {{offset:0,color:'#ffa502'}},{{offset:1,color:'#ff6b6b'}}
                    ]),
                    borderRadius: [4,4,0,0]
                }}
            }}]
        }});

        // 高赞回答图
        const topVotedData = {json.dumps([[a['author'], a['voteup_count']] for a in top_voted], ensure_ascii=False)};
        const chart5 = echarts.init(document.getElementById('chart-topvoted'));
        chart5.setOption({{
            tooltip: {{ trigger: 'axis', axisPointer: {{ type: 'shadow' }}, formatter: '{{b}}: {{c}}赞同' }},
            grid: {{ left: 150, right: 100, top: 30, bottom: 50 }},
            xAxis: {{ type: 'value', name: '赞同数', nameLocation: 'middle', nameGap: 30, axisLabel: {{formatter: function(v){{return v >= 10000 ? (v/10000).toFixed(1)+'万' : v;}}}} }},
            yAxis: {{ type: 'category', data: topVotedData.map(d=>d[0]).reverse(), axisLabel: {{fontSize:14, interval:0, width: 140, overflow: 'truncate'}} }},
            series: [{{
                data: topVotedData.map(d=>d[1]).reverse(),
                type: 'bar',
                barWidth: '60%',
                label: {{ show: true, position: 'right', fontSize: 13, formatter: function(p){{return p.value >= 10000 ? (p.value/10000).toFixed(1)+'万' : p.value;}} }},
                itemStyle: {{
                    color: new echarts.graphic.LinearGradient(0,0,1,0,[
                        {{offset:0,color:'#52c41a'}},{{offset:1,color:'#95de64'}}
                    ]),
                    borderRadius: [0,4,4,0]
                }}
            }}]
        }});

        window.addEventListener('resize', () => {{
            [chart1, chart2, chart3, chart4, chart5].forEach(c => c && c.resize());
        }});
    </script>
</body>
</html>"""

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)
    return output_path


# ============================================================
# 主函数
# ============================================================

def main():
    parser = argparse.ArgumentParser(description="知乎问题回答爬取分析工具")
    parser.add_argument("question", help="知乎问题链接或问题ID")
    parser.add_argument("--cookie", help="知乎Cookie（z_c0的值或完整Cookie字符串）")
    parser.add_argument("--cookie-file", help="Cookie文件路径")
    parser.add_argument("--max-pages", type=int, default=100, help="最大爬取回答页数（默认100，每页20条）")
    parser.add_argument("--max-comments", type=int, default=30, help="每个回答最多爬取评论数（默认30）")
    parser.add_argument("--output", "-o", default="", help="输出HTML文件路径")
    parser.add_argument("--sort", choices=["default", "created"], default="default",
                        help="回答排序方式：default=默认（综合），created=按时间")
    parser.add_argument("--deepseek-api-key", help="DeepSeek API Key（用于AI深度总结）")
    parser.add_argument("--no-ai-summary", action="store_true", help="禁用AI深度总结")
    parser.add_argument("--books", nargs="*", default=[],
                        help="参考书籍（可选：大学突围、大学进化论、决胜大学），可指定多个")
    parser.add_argument("--perspective", default="",
                        help="名人视角分析（可选：张雪峰），用指定名人的思维框架点评回答")
    args = parser.parse_args()

    qid = extract_question_id(args.question)
    print(f"🔍 问题ID: {qid}")

    # 加载Cookie
    cookies = load_cookie(args.cookie, args.cookie_file)
    if not cookies.get("z_c0"):
        print("\n⚠️  未检测到有效的 z_c0 Cookie，可能无法获取完整数据")
        print("   获取方法：浏览器登录知乎 → F12 → Application → Cookies → 复制 z_c0 的值")
        print("   使用方式：python zhihu_answer_analyzer.py 问题ID --cookie \"你的z_c0值\"")
        print()
    
    # 设置完整Cookie用于x-zse-96签名
    full_cookie = args.cookie or ""
    if not full_cookie and args.cookie_file and os.path.exists(args.cookie_file):
        with open(args.cookie_file, "r", encoding="utf-8") as f:
            full_cookie = f.read().strip()
    if full_cookie:
        set_zhihu_cookie(full_cookie)
        print("✅ Cookie已设置（含x-zse-96签名）")

    # 1. 获取问题信息
    print("\n📋 获取问题信息...")
    question_info = get_question_info(qid, cookies)
    if not question_info:
        print("❌ 无法获取问题信息，请检查问题ID和Cookie")
        sys.exit(1)
    print(f"✅ 标题: {question_info['title']}")
    print(f"✅ 回答数: {question_info['answer_count']:,} | 关注者: {question_info['follower_count']:,}")

    # 2. 爬取回答
    print(f"\n📝 开始爬取回答（最多{args.max_pages}页）...")
    answers = get_answers(qid, cookies, max_pages=args.max_pages, sort_by=args.sort)
    print(f"\n✅ 爬取到 {len(answers)} 条回答")

    if not answers:
        print("❌ 未爬取到任何回答，请检查Cookie是否有效")
        sys.exit(1)

    # 3. 爬取评论
    print(f"\n💬 开始爬取评论（每个回答最多{args.max_comments}条）...")
    for i, ans in enumerate(answers):
        print_progress(i + 1, len(answers), "爬取评论中")
        ans["comments"] = get_answer_comments(ans["id"], cookies, max_comments=args.max_comments)
        time.sleep(0.3)
    print()

    # 4. 智能评分
    print("\n🧠 智能评分中...")
    for ans in answers:
        ans["quality_score"] = calculate_quality_score(ans, answers)

    # 5. 数据分析
    print("📊 分析数据...")
    analysis = analyze_answers(answers)

    # 5.5 AI深度总结
    ai_summary = None
    if not args.no_ai_summary:
        api_key = args.deepseek_api_key or os.environ.get("DEEPSEEK_API_KEY", "")
        if api_key:
            ai_summary = deepseek_summary(api_key, question_info, answers)
        else:
            print("\n💡 提示：设置DeepSeek API Key可生成AI深度总结")
            print("   方式1：--deepseek-api-key 你的key")
            print("   方式2：设置环境变量 DEEPSEEK_API_KEY")
            print("   方式3：--no-ai-summary 禁用此提示")

    # 5.6 多源知识融合分析（书籍+名人视角）
    multi_analysis = None
    if (args.books or args.perspective) and args.deepseek_api_key:
        api_key = args.deepseek_api_key or os.environ.get("DEEPSEEK_API_KEY", "")
        knowledge_text = load_knowledge(books=args.books, perspective=args.perspective)
        if knowledge_text:
            multi_analysis = multi_source_analysis(
                api_key, question_info, answers, knowledge_text, perspective=args.perspective
            )

    # 6. 生成报告
    date_str = datetime.now().strftime("%Y-%m-%d")
    task_dir = f"output/{date_str}_question_{qid}"
    os.makedirs(task_dir, exist_ok=True)
    output_path = args.output or f"{task_dir}/report.html"
    print(f"\n📝 生成HTML报告...")
    generate_html_report(question_info, answers, analysis, output_path,
                         ai_summary=ai_summary, multi_analysis=multi_analysis)

    print(f"\n🎉 分析完成！报告已保存至: {output_path}")
    print(f"   爬取回答: {len(answers)} 条")
    print(f"   爬取评论: {analysis.get('total_comments', 0)} 条")
    print(f"   用浏览器打开即可查看交互式分析报告")

    # 7. 导出原始数据
    try:
        import csv
        csv_path = output_path.replace(".html", "_answers.csv")
        with open(csv_path, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["作者", "赞同数", "评论数", "字数", "精华评分", "更新时间", "回答内容"])
            for a in sorted(answers, key=lambda x: x["quality_score"]["total"], reverse=True):
                writer.writerow([
                    a["author"], a["voteup_count"], a["comment_count"],
                    a["content_length"], a["quality_score"]["total"],
                    a["updated_time"], a["content"][:500]
                ])
        print(f"   回答数据已导出: {csv_path}")
    except Exception as e:
        print(f"   ⚠️  CSV导出失败: {e}")


if __name__ == "__main__":
    main()
