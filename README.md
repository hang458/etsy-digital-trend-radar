# Etsy Digital Trend Radar

一个面向 Etsy 数字下载商品的轻量趋势雷达，参考 [Averixa Market Radar Lite](https://github.com/hang458/averixa-market-radar-lite) 的关键词发现、候选池、定时快照与静态看板架构。

## 功能

- 按 `config/research.json` 中的数字商品关键词轮询 Etsy 官方 API。
- 优先筛选数字下载商品，并保留关键词、价格、收藏数、搜索排名、商店和商品链接。
- 结合 Etsy 搜索排名、收藏数、收藏变化与多关键词重复出现情况计算趋势分；该分数是公开信号，不代表销量。
- 保存有限历史快照，支持比较最近 24 小时收藏变化。
- 输出适合 GitHub Pages 发布的静态中文研究看板和 CSV 数据。
- 看板包含商品研究、关键词样本分析和竞品收藏三个视图；支持价格/趋势排序、关键词比较历史图表。
- 关键词指标仅从已采集商品样本汇总，不代表全站搜索量或实际销量；竞品收藏保存在当前浏览器。
- API 密钥只从环境变量读取，不写入代码、状态文件或网页。

## 本地启动

需要 Python 3.10+ 和 Etsy Open API v3 应用密钥。在 Etsy 开发者应用中获取 `ETSY_KEYSTRING` 和 `ETSY_SHARED_SECRET` 后：

```powershell
$env:ETSY_KEYSTRING="你的 keystring"
$env:ETSY_SHARED_SECRET="你的 shared secret"
python radar.py
python -m http.server 8000 --directory site
```

打开 `http://localhost:8000` 查看采集结果。也可以用 `python radar.py --render-only` 在没有密钥时仅渲染已有数据。

关键词研究页会按采集关键词汇总候选商品数量、平均价格、平均收藏、平均趋势分和最佳搜索位置。勾选最多 5 个关键词可比较历史收藏信号；历史样本会随公开看板数据发布。

## GitHub Actions 定时运行

把项目推送到自己的 GitHub 仓库后，在仓库设置中添加 Actions secrets `ETSY_KEYSTRING`、`ETSY_SHARED_SECRET`，并启用 GitHub Pages（GitHub Actions 发布源）。工作流每小时运行一次；GitHub 可能延迟定时任务。

## 调整研究范围

编辑 `config/research.json` 修改关键词和每轮采集上限。默认研究 2027 规划品、圣诞 SVG/PNG、Canva 社媒模板、婚礼模板、可打印预算表、学习资料、数字贴纸、Notion 模板和墙面艺术等数字下载方向。词条会轮换采集，不会声称覆盖 Etsy 全站。

## 数据限制

Etsy API 返回的数据与权限会随接口和应用额度变化。趋势分只用于排序公开热度信号；收藏变化不等同于订单或销量。完整的时间趋势需成功运行多轮后才能形成基线。请遵守 Etsy API 使用条款及速率限制。
