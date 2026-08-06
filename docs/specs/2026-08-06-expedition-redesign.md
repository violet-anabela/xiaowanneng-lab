# 前端改版设计：猫咪考察队手账（方向 B）

日期：2026-08-06 · 状态：已由 mockup 确认（`frontend/public/_mockups/b-expedition.html`，实施后删除）

## 目标

让站点有"探索欲望"：把整站叙事改为「两只猫的考察队手账」，视觉从浅克莱因蓝改为暖纸张手账风。保留品牌元素：两只猫吉祥物、实验室/lab 概念。

## 设计 Token（global.css）

- 色板：米纸底 `#f5efe2`、卡片纸 `#fffdf7`、墨蓝 `#23324d`（主文字/边框）、砖红 `#d94f30`（强调）、墨绿 `#1e7f74`（辅助）、芥末金 `#d9a13b`（点缀）
- 字体：标题 Georgia/Songti SC/Noto Serif SC（衬线）；正文 Inter/PingFang SC；标签编号 ui-monospace；便签 Kaiti SC（楷体）。全部系统字体，不引 webfont（部署环境无外网出站）。
- 质感：稿纸横线底纹、等高线装饰、邮戳、胶带、拍立得、虚线路线、硬偏移阴影 `4px 4px 0`、元素微旋转 ±2°
- 卡片：`2px solid 墨蓝` 边框 + 偏移阴影，hover 位移 `translate(-3px,-3px)` 加深阴影

## 页面叙事映射

| 页面 | 叙事 | 要点 |
|---|---|---|
| 首页 | 大本营 | hero 用 mockup 新文案「两只猫的探索手账」，拍立得+邮戳+便签，路线图 01 记录→02 造物→03 分享，三条 TRAIL 卡片 |
| /docs/ | 考察记录 | 列表 = 带日期邮戳的日志条目 |
| /docs/[slug] | 手账纸正文 | prose 放在纸张卡上 |
| /tools/ | 远征装备 | 可用盖 READY 戳，未上线盖 PACKING 戳 |
| /tools/remove-background | 装备操作台 | 上传区 = 虚线标本框；交互逻辑不动 |
| /skills/ | 补给站 | 下载卡 = 补给包 + 编号签条 |
| /development/ | 队内档案 | 同语言更朴素，导航保持区分 |

## 约束

- 只改样式与页面结构（Base.astro、global.css、各 .astro 的模板/样式），不动功能逻辑（抠图 API 调用、skills manifest、content collections）
- 移动端全部适配；`prefers-reduced-motion` 保留
- 页脚：手账风"队伍签名"，两只猫职务署名
