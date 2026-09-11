# 💡 知乎问题回答爬取分析工具

> 输入知乎问题链接，自动爬取所有回答+评论，**智能评分筛选精华**，生成交互式HTML报告，帮你高效吸收信息，节省阅读时间。

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python](https://img.shields.io/badge/Python-3.8+-blue.svg)](https://www.python.org/)

## ✨ 核心功能

### 🧠 智能精华筛选（多维度评分）
不再只按点赞数排序！综合6个维度给每个回答打分：

| 维度 | 权重 | 说明 |
|------|------|------|
| 👍 赞同数 | 40% | 社区认可度 |
| 💬 评论数 | 15% | 讨论热度 |
| 📏 内容长度 | 15% | 信息量（500-3000字最佳） |
| 🔑 关键词密度 | 15% | 专业度信号（首先、其次、分析、数据等） |
| 👤 作者影响力 | 10% | 作者粉丝数 |
| ⏰ 时效性 | 5% | 最近更新有加成 |

### 📥 数据爬取
- 📝 **全部回答** — 按默认/时间排序爬取，支持分页
- 💬 **回答评论** — 每个回答下的热门评论
- 📋 **问题信息** — 标题、回答数、关注者、创建时间

### 📊 分析维度
- 🏆 **精华回答TOP10** — 智能评分排序，附多维度得分
- 🔤 **回答词频** — 关键词TOP30，快速了解讨论焦点
- 💬 **评论词频** — 评论区热点词TOP20
- 📏 **长度分布** — 回答字数分布统计
- 👍 **赞同分布** — 赞同数区间分布
- 🔥 **热门评论** — 高赞评论TOP15
- 📈 **高赞回答** — 按赞同数排序TOP10

### 📝 内容摘要
- 自动总结最热关键词
- 精华回答第一名推荐
- 最高赞回答摘要
- 评论区热点词
- 回答长度分布分析

## 🚀 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
# 或手动安装
pip install requests jieba beautifulsoup4
```

### 2. 获取知乎Cookie（重要！）

知乎需要登录才能获取完整数据，需要获取 `z_c0` 这个Cookie：

**方法一：浏览器开发者工具（推荐）**
1. 用Chrome/Edge打开知乎并登录
2. 按 `F12` 打开开发者工具
3. 切换到 `Application`（应用）标签
4. 左侧找到 `Cookies` → `https://www.zhihu.com`
5. 找到 `z_c0` 这一行，复制它的 Value

**方法二：Network面板**
1. F12 → Network（网络）标签
2. 刷新知乎页面
3. 点击任意一个请求
4. 在 Request Headers 里找到 `Cookie:`
5. 复制 `z_c0=xxx` 这一段

### 3. 运行工具

```bash
# 基本用法（输入问题链接或ID）
python zhihu_answer_analyzer.py https://www.zhihu.com/question/123456 --cookie "你的z_c0值"

# 只输入问题ID
python zhihu_answer_analyzer.py 123456 --cookie "你的z_c0值"

# 把Cookie保存到文件，避免每次输入
echo "你的z_c0值" > cookie.txt
python zhihu_answer_analyzer.py 123456 --cookie-file cookie.txt

# 限制爬取数量（回答多的问题用）
python zhihu_answer_analyzer.py 123456 --cookie "xxx" --max-pages 20

# 每个回答爬取更多评论
python zhihu_answer_analyzer.py 123456 --cookie "xxx" --max-comments 50

# 按时间排序回答
python zhihu_answer_analyzer.py 123456 --cookie "xxx" --sort created

# 指定输出文件名
python zhihu_answer_analyzer.py 123456 --cookie "xxx" -o my_report.html
```

### 4. 查看报告

运行完成后，会生成 `zhihu_report_{问题ID}.html`，用浏览器打开即可。

## 📊 报告预览

报告包含7个分析标签页：

| 标签页 | 内容 |
|--------|------|
| 🏆 精华回答 | 智能评分TOP10，附6维度得分条 |
| 🔤 回答词频 | 回答内容关键词TOP30横向条形图 |
| 💬 评论词频 | 评论区关键词TOP20 |
| 📏 长度分布 | 回答字数分布柱状图 |
| 👍 赞同分布 | 赞同数区间分布 |
| 🔥 热门评论 | 高赞评论TOP15列表 |
| 📈 高赞回答 | 按赞同数排序TOP10 |

## 🛠️ 技术栈

| 技术 | 用途 |
|------|------|
| Python 3 | 核心爬取与分析逻辑 |
| requests | HTTP请求，调用知乎API |
| jieba | 中文分词，词频统计 |
| BeautifulSoup | HTML内容清洗 |
| ECharts 5 | 交互式图表渲染 |

## ⚙️ 参数说明

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `question` | 问题链接或ID（必填） | - |
| `--cookie` | 知乎Cookie（z_c0值） | - |
| `--cookie-file` | Cookie文件路径 | - |
| `--max-pages` | 最大爬取回答页数（每页20条） | 100 |
| `--max-comments` | 每个回答最多爬取评论数 | 30 |
| `--output, -o` | 输出HTML文件路径 | 自动生成 |
| `--sort` | 回答排序：default/created | default |

## 📂 项目结构

```
zhihu-answer-analyzer/
├── zhihu_answer_analyzer.py   # 主程序
├── requirements.txt           # 依赖列表
├── README.md                  # 项目说明
├── LICENSE                    # MIT协议
└── .gitignore
```

## 🎯 使用场景

- 📚 **学习研究** — 快速了解一个问题的核心观点和精华回答
- 💼 **职场决策** — 收集行业问题的多方观点
- 🏫 **备考复习** — 提取考试相关问题的高分回答
- 🔬 **内容创作** — 分析热门问题的讨论角度
- ⏱️ **节省时间** — 不用逐条翻回答，直接看精华

## ⚠️ 注意事项

1. **Cookie有效期** — 知乎Cookie会过期，失效后重新获取即可
2. **爬取频率** — 脚本已内置延时（回答1秒、评论0.5秒），请勿过于频繁
3. **数据量** — 回答多的问题可能需要较长时间，建议先用 `--max-pages` 限制
4. **内容版权** — 爬取的数据仅供个人学习使用，请勿商用或二次传播

## 🔧 常见问题

**Q: 提示401未授权？**
A: Cookie无效或已过期，请重新获取 z_c0。

**Q: 爬取速度很慢？**
A: 为了避免被封IP，脚本内置了延时。回答多的问题可以用 `--max-pages` 限制。

**Q: 回答内容不完整？**
A: 知乎API返回的是完整HTML内容，脚本已清洗为纯文本。报告中只显示前500字摘要，完整内容在导出的CSV里。

**Q: 可以爬取专栏文章吗？**
A: 当前版本专注于问题回答。如需文章爬取，可以提Issue或PR。

## 🤝 贡献指南

欢迎提交 Issue 和 Pull Request！

1. Fork 本仓库
2. 创建特性分支 (`git checkout -b feature/AmazingFeature`)
3. 提交修改 (`git commit -m 'Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 开启 Pull Request

## 📄 许可证

本项目基于 [MIT License](LICENSE) 开源协议。

## ⚠️ 免责声明

- 本工具仅供学习和研究使用
- 请遵守知乎的用户协议和相关法律法规
- 请勿用于商业用途或大规模爬取
- 使用本工具产生的任何后果由使用者自行承担

---

**如果这个工具对你有帮助，欢迎给个 ⭐ Star 支持一下！**
