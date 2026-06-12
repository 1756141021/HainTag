# Roadmap

后续工作清单，按优先级分级。来源：2026-06-12 双视角评审（新人用户 + 资深工程师），评分摘要见文末。

工作量标记：S（≤半天）/ M（1-3 天）/ L（一周+）。

---

## P0 — 新手引导

新用户视角评分 5/10，三大流失点都在前 10 分钟。

| # | 事项 | 量 | 说明 |
|---|------|----|------|
| 1 | API 配置引导 | S | 缺 API 报错自动打开的设置面板里加帮助文本：支持哪些 OpenAI 兼容服务、去哪申请、README 对应章节链接。引导第 2 步从"在这里配置 API"升级为"怎么获得 API" |
| 2 | 本地反推降门槛 | S-M | 模型步骤加 HuggingFace 直达链接按钮；"自动配置 Python 环境"补充体积/耗时预期；术语口语化（非程序员不懂 onnxruntime） |
| 3 | 首启空白感 | S | 提示词卡片首启默认可见（models.py WidgetState 默认值），或输入框空状态加提示"输入画面描述，Enter 生成" |
| 4 | 气泡提示时机 | S | 现在延迟 2-6s 出现容易错过，改为关键控件首次 hover/focus 触发 |

## P1 — 工程基建

资深视角"贡献者就绪 4/10"的解药。

| # | 事项 | 量 | 说明 |
|---|------|----|------|
| 5 | pytest 核心逻辑测试 | M | logic.py（depth/消息组装）、llm_tagger_logic.py（1girl 归一化做回归）、metadata/parsers、storage 往返。先纯逻辑层，目标 40-50% |
| 6 | GitHub Actions CI | S | ruff + import 冒烟，PR/push 触发 |
| 7 | Release workflow | M | tag 推送 → win+mac 双平台打包 → 自动建 release。PR #4 作者（Miint-Sunny）也提过，mac 侧可邀其协作 |
| 8 | CONTRIBUTING + 模板 | S | 开发环境、架构入口指向 DEV_NOTES、CHANGELOG 约定、issue/PR 模板 |
| 9 | pyproject.toml + 依赖锁定 | S | 现在 requirements.txt 只有直接依赖无锁定 |

## P2 — 安全 / 信任

| # | 事项 | 量 | 说明 |
|---|------|----|------|
| 10 | API key 入 OS keyring | M | 现为 settings.json 明文。Windows 凭据管理器，首启迁移，keyring 不可用回退明文+提示 |
| 11 | 更新包 SHA256 校验 | S | release body 嵌 hash，updater 下载后校验（现仅 zip 完整性检查） |
| 12 | 代码签名 | 待定 | Windows 证书有年费，成本决策项 |

## P3 — 远期架构

| # | 事项 | 量 | 说明 |
|---|------|----|------|
| 13 | window.py 拆分 | L | ~3900 行。抽 DockManager / FloatingTrayManager / ChatHandler，MainWindow 留编排。评审判断为 6-12 个月内最大维护风险 |
| 14 | interrogator.py 类别映射抽离 | M | ~3100 行，语义分类映射抽成可测试模块 |

---

## 评审摘要（2026-06-12）

**资深工程师视角评分**：架构 8 · 代码质量 7 · 文档 7 · 发布工程 5 · 安全 6 · 贡献者就绪 4。

被点名的优点（重构时别丢）：DEV_NOTES 内部文档、错误报告脱敏、storage Facade、原子写+退避重试、双语 README、spec 打包瘦身、子进程环境隔离、metadata parser 插件化。

**新人用户视角**：6 步引导和"缺 API 自动开设置"是好底子；卡点全在"API 去哪搞"和"Python 环境是什么"两个问题上。
