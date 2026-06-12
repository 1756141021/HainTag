# Roadmap

后续工作清单，按优先级分级。来源：2026-06-12 双视角评审（新人用户 + 资深工程师），评分摘要见文末。

工作量标记：S（≤半天）/ M（1-3 天）/ L（一周+）。

---

## P0 — 新手引导

新用户视角评分 5/10，三大流失点都在前 10 分钟。

| # | 事项 | 量 | 说明 |
|---|------|----|------|
| ~~1~~ | ~~API 配置引导~~ | S | ✅ 2026-06-12 设置面板 API 标签悬停说明 + 「查看配置说明」README 链接；缺 API 报错与教程第 2 步文案同步 |
| 2 | 本地反推降门槛 | S-M | 部分完成（体积/耗时预期已补）。剩：HuggingFace 直达链接按钮、术语口语化（非程序员不懂 onnxruntime） |
| 3 | 首启空白感 | S | 部分完成（输入框空状态提示已改）。剩：提示词卡片首启默认可见（models.py WidgetState 默认值）可选项待定 |
| ~~4~~ | ~~气泡提示时机~~ | S | ✅ 2026-06-12 hint_send/hint_scrub 改里程碑触发（首次输入 / 首次生成完成） |

## P1 — 工程基建

资深视角"贡献者就绪 4/10"的解药。批次顺序（已定）：①工程三件套 → ②pytest 测试集 → ③Release 自动发版 → ④安全双修（P2 #10+#11）。

| # | 事项 | 量 | 说明 |
|---|------|----|------|
| ~~5~~ | ~~pytest 核心逻辑测试~~ | M | ✅ 2026-06-12 `tests/` 118 条：logic/llm_tagger_logic/models/updater/metadata 读写/i18n/词典；后续可向 metadata parsers、storage 往返扩展 |
| ~~6~~ | ~~GitHub Actions CI~~ | S | ✅ 2026-06-12 `.github/workflows/ci.yml`：ruff + import 冒烟，push/PR 触发 |
| ~~7~~ | ~~Release workflow~~ | M | ✅ 2026-06-12 `.github/workflows/release.yml`：tag 推送 → win zip + mac dmg（arm64）→ draft release + SHA256；词典 CSV 走 `dict-data` 数据 release；mac 构建失败不挡 Windows 发版 |
| ~~8~~ | ~~CONTRIBUTING + 模板~~ | S | ✅ 2026-06-12 `CONTRIBUTING.md` + issue/PR 模板 |
| ~~9~~ | ~~pyproject.toml + 依赖锁定~~ | S | ✅ 2026-06-12 `pyproject.toml`（含 ruff 配置）+ `requirements.lock`（uv pip compile 生成） |

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
