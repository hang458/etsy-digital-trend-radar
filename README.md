# Etsy Digital Trend Radar

一个覆盖 Etsy 主要商品大类的轻量趋势雷达，采集实体商品与数字下载，参考 [Averixa Market Radar Lite](https://github.com/hang458/averixa-market-radar-lite) 的关键词发现、候选池、定时快照与静态看板架构。

## 功能

- 按 `config/research.json` 中的 16 个主要品类和跨品类搜索词轮询 Etsy 官方 API。
- 同时采集实体商品和数字下载，并保留品类、商品类型、关键词、价格、收藏数、搜索排名、商店和商品链接。
- 结合 Etsy 搜索排名、收藏数、收藏变化与多关键词重复出现情况计算趋势分；该分数是公开信号，不代表销量。
- 保存有限历史快照，支持比较最近 24 小时收藏变化。
- 输出适合 GitHub Pages 发布的静态中文研究看板和 CSV 数据。
- 看板包含商品研究、关键词样本分析和竞品收藏三个视图；支持品类筛选、价格/趋势排序、关键词比较历史图表。
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

编辑 `config/research.json` 修改品类、搜索词和每轮采集上限。当前配置覆盖艺术收藏、家居、珠宝、服装、配饰、箱包、美妆、手工材料、纸品派对、玩具、宠物、鞋履、电子配件、书影音、婚礼和数字下载。每轮按额度轮换少量搜索词；这是各大类的代表性采样，不是对 Etsy 全站商品的穷举抓取。

## 数据限制

Etsy API 返回的数据与权限会随接口和应用额度变化。趋势分只用于排序公开热度信号；收藏变化不等同于订单或销量。完整的时间趋势需成功运行多轮后才能形成基线。请遵守 Etsy API 使用条款及速率限制。
