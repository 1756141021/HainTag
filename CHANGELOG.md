# Changelog

All notable changes to HainTag will be documented in this file.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
versioning follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.6.1] - 2026-04-04

### Added
- **文本区域拖拽调整高度** — Metadata 查看器、编辑器、例图卡片的文本框底部新增 6px 拖拽手柄，可拖动调整高度
- **销毁文本模板系统** — Metadata 销毁器标题栏新增模板下拉框，支持切换/新增/编辑/删除预设销毁文本，右键下拉框或从右键菜单"编辑预设文本"打开编辑器弹窗
- **编辑模式子菜单** — Metadata 销毁器右键"编辑模式"拆为"编辑单个图片"和"编辑预设文本"两个选项

### Fixed
- **浮动窗口边缘保护** — 浮动卡片拖拽时限制在屏幕可用区域内，标题栏不会跑出屏幕外
- **浮动窗口 resize** — 浮动模式下卡片可正常拖拽调整大小（之前 bounds 为空导致无法放大）
- **销毁模板持久化** — destroy_templates 和 skipped_version 在 _build_app_state 中正确保留，不再被设置面板重建覆盖

---

## [0.6.0] - 2026-04-04

### Added
- **历史记录侧边栏** — 工作台右侧可收缩侧边栏，替代原独立历史卡片。◁ 按钮触发，200ms 动画展开/收缩，不影响工作台布局。条目可折叠/展开（懒创建），支持复制输出、复制输入、填充到当前输出。浮动窗口模式下侧边栏跟随
- **自动更新检查** — 启动 3 秒后后台查询 GitHub Releases API，发现新版弹窗显示 changelog，三个按钮：立即更新（打开浏览器下载）/ 跳过此版本 / 下次提醒。设置面板底部新增"检查更新"按钮可手动触发
- **HistoryEntry 增加 nochar_text** — 历史记录同时保存完整 TAG 和无角色 TAG，向后兼容

### Fixed
- **输入保留** — API 报错（HTTP 502 等）或取消生成时，输入框内容自动恢复，不再丢失
- **错误显示** — URL 配置错误（缺少 http://）不再弹出错误报告弹窗，改为在 TAG 输出区显示 `[Error]` 并自动打开设置面板

### Changed
- **WidgetCard 新增 geometry_live 信号** — moveEvent/resizeEvent 中触发，拖拽过程中每帧同步，供侧边栏按钮实时跟随

---

## [0.5.21] - 2026-04-03

### Added
- **NAI / SD 格式预设** — 新增 NAI 和 SD 两条默认提示词预设，控制输出格式（NAI 默认启用，SD 默认关闭），用户可按需切换

### Changed
- **品牌统一** — 错误报告标题、新手引导欢迎语、导出/导入对话框、错误报告文件头、更新日志弹窗全部从 "AI Tag Generator" 更名为 "HainTag"

---

## [0.5.2] - 2026-04-02

### Added
- **工作台合并** — 输入和输出卡片合并为一个"工作台"卡片，QSplitter 可拖动分割线调整比例，⇅ 按钮交换输入/输出位置
- **TAG 拖拽排序** — 左键按住 TAG 拖动可调整顺序，拖动中高亮源和目标
- **TAG 提取标记** — `[TAGS]...[/TAGS]` 和 `[NOTAGS]...[/NOTAGS]` 自动从 LLM 输出中提取 TAG，标记可在设置面板自定义
- **TAG 自动补全** — 完整 TAG 和无角色 TAG 编辑器均支持 Danbooru 词典自动补全
- **TAG 分类中文翻译** — hover 时分类名显示中文（质量/角色/场景等）
- **新手引导** — 首次启动弹出步骤式高亮引导（6 步），介绍主要功能区域，可跳过
- **默认提示词预设** — 内置 7 条 TAG 生成提示词模板，新用户开箱即用
- **默认例图** — 内置一张示例图 + metadata 原始 TAG，新用户立即看到效果
- **霞鹜文楷 Screen** — 内置字体（SIL OFL），默认字体 profile
- **程序图标** — 自定义 Q 版角色图标（EXE + 窗口任务栏）
- **画师库 hint** — 首次使用提示气泡引导打开画师库/OC 库
- **Tooltip 引导** — 深度/顺序字段、× 收纳按钮、画师库入口、TAG 提取标记均有 hover 说明

### Changed
- **品牌重命名** — AITagGenerator → **HainTag**（海茵的标签工坊），EXE/窗口标题/AppData 目录全部更新
- **例图消息格式** — 合并为单条 assistant 消息：`例图N：\n画面描述：xxx\n\`\`\`\ntags\n\`\`\``
- **Depth 排序修复** — 同 depth 条目按 Order 分组后一次性 splice 插入，保持顺序不反转，user+assistant 配对不拆散
- **默认亮度** — 暗色主题 brightness 默认 0（纯暗），亮色默认 100
- **默认 max_tokens** — 2048 → 64000
- **Hint 时机** — 首次启动时 hint 气泡在新手引导结束后才弹出

### Fixed
- **例图不完整警告** — 只填 tags 没填描述（或反过来）时显示橙色提示
- **首次启动例图不显示** — `_load_state_into_ui` 首次路径未创建例图卡片

---

## [0.4.0] - 2026-04-01

### Changed
- **storage.py → storage/ 包**（SRP 拆分）— Facade 模式，AppStorage 拆分为 12 个域子管理器，外部接口零破坏
- **HintManager.dismiss()** — 新增公共方法，window.py 不再直接访问私有属性
- **卡片标题** — drag strip 显示卡片名称（提示词/输入/完整TAG/生成历史/例图N…），切语言自动更新
- **卡片 × 收纳按钮** — drag strip 右侧新增 × 按钮，点击直接收纳到 dock
- **主题级联刷新** — 切换主题时 HistoryPanel / LibraryPanel / WidgetCard 内部组件全部跟随 palette 更新

### Fixed
- **ResponseNotRead 崩溃** — httpx 流式响应 HTTPStatusError 时 `exc.response.text` 加 try-except 防护
- **错误报告对话框** — QMessageBox 加 `current_palette()` 样式，跟随主题
- **历史面板对比度** — input preview 颜色从 `text_muted` 改为 `text`
- **亮度标签** — "明暗" → "亮度"
- **主题切换亮度** — 暗色主题 brightness=0，亮色主题 brightness=100
- **卡片拖拽失效** — title_label 加 `WA_TransparentForMouseEvents`

---

## [0.3.2] - 2026-04-01

### Fixed
- **代码准则全面审计** — 按 KISS/DRY/SRP/防守型编程准则审计并修复
  - **P0 健壮性**：6 处可能导致崩溃的 IndexError/KeyError 加守卫（api_client/theme/window/storage）
  - **P1 死代码**：5 处未使用导入删除（main/metadata_destroyer/metadata_viewer/image_manager）
  - **P2 DRY**：library_panel.py 提取 6 个样式公共函数（`_input_style`/`_del_btn_style`/`_arrow_style`/`_header_style`/`_dim_label_style`），消除 15+ 处重复样式代码
  - **P4 命名**：魔法字符串常量化（`_SSE_DONE`/`_NEW_FOLDER_SENTINEL`/`SECTION_ARTIST`/`SECTION_OC`），storage.py 全部字典访问统一改用 `.get()`

---

## [0.3.1] - 2026-04-01

### Fixed
- **接口对齐修复** — 全项目审计并统一主题/字体接口
  - `widget_card.py`：pin 按钮 4 处 `_fs()` 缺少 f-string 前缀导致 font-size 无效，颜色硬编码改用 `current_palette()` 的 `accent_text`/`text_dim`
  - `window.py`：更新日志弹窗 2 处硬编码 px 改用 `_fs()` 系统
  - `library_panel.py`：面板背景硬编码深色 `rgba(18,18,22)` 改用 `p['bg']`，亮色主题不再显示为黑块
  - `metadata_viewer.py`：缩略图边框硬编码灰色改用 `p['line']`
  - `metadata_destroyer.py`：成功色硬编码 `#5c5` 改为深/浅主题自适应
  - `theme.py`：`#PanelHeader` 的 `font-family` 从硬编码衬线字体改为 `{font_family}` token，用户切换字体 profile 时面板标题同步生效

---

## [0.3.0] - 2026-03-31

### Added
- **生成历史面板** — 自动记录每次生成的输入+输出+时间戳+模型，持久化到 history.json（上限 500 条），点击填充输出，右键复制
- **快捷键速查面板** — F1 / Ctrl+/ / 标题栏 ? 按钮，Popup 弹窗显示 6 个区块 21 个快捷键和鼠标手势
- **HintManager 框架** — 首次使用提示气泡接口，register() 注册 → 自动显示 → 持久化到 hints.json，8 秒自动消失
- 工作区右键菜单新增"生成历史"和"快捷键"入口

---

## [0.2.0] - 2026-03-31

### Added
- **TAG 分类高亮** — LLM 输出 `§category¦tag` 分类映射，自动解析并按类别着色（人物/场景/姿势/服饰/表情/风格/质量 8 种颜色）
- **TAG hover 增强** — 悬停显示中文翻译 + 分类名
- **QSyntaxHighlighter** — 替代 setCharFormat，hover 高亮改用 setExtraSelections 避免冲突
- **Prompt 预览** — 提示词编辑器 ⋯ 按钮，弹出完整 prompt 预览（角色标签 + token 计数）
- **画师库** — 右上角抽屉面板，存储画师名 + LoRA/触发词 + 大尺寸参考图，一键 Copy
- **OC 库** — 角色管理，支持 Order/Depth 控制消息插入位置，ToggleSwitch 启用/禁用
- **服装系统** — OC 子项，每套服装独立 ToggleSwitch 多选，发送时合并角色 tag + 启用服装 tag
- **条目默认值设置** — 设置面板可配置 Example/OC 的默认 Order 和 Depth
- **抽屉两步交互** — 半圆按钮 → 窄条（画师库/OC库选择） → 展开内容，带宽度动画 + 淡入
- **iTXt 编码修复** — PNG 写入自动选择 tEXt（Latin-1）或 iTXt（UTF-8），中文销毁文本不再乱码

### Changed
- **图像管理器主题同步** — 所有组件改用 `current_palette()`，自定义背景色板完全同步
- **缩略图 CPU 优化** — 滑块拖动时跳过新请求，松手后统一加载
- **窗口光标修复** — 拖拽显示 ClosedHandCursor，松开重置 ArrowCursor

### Added (v0.1.0 延续)
- **版本号系统** — `_version.py` 单一来源 + CHANGELOG.md + 工作区右下角标签 + 点击查看更新日志
- **PyInstaller 版本信息** — EXE 属性嵌入版本号
- **喜欢持久化** — likes.json 独立存储
- **子文件夹递归扫描** — 工具栏开关，平铺所有子目录图片
- **文件操作** — 移动到子文件夹菜单、新建文件夹、F2 重命名、Delete 回收站、Ctrl+X/V/C
- **美化对话框** — _StyledDialog 替代 QInputDialog/QMessageBox，跟随主题

---

## [0.1.0] - 2026-03-31

### Added
- **Metadata 解析引擎** — 支持 A1111/Forge、ComfyUI、NovelAI（含 LSB 隐写）、Fooocus 四种格式
- **Metadata 查看器** — 拖入或选择图片，分区显示正面/负面提示词、参数、LoRA、Workflow
- **Metadata 销毁/编辑器** — 二进制 chunk 级操作，IDAT 零损耗；支持单图编辑和批量销毁
- **TAG 自动补全** — 150K Danbooru 词典，150ms 防抖，不抢焦点
- **图像管理器** — 独立无边框窗口
  - 缩略图网格浏览（PIL 快速降采样 + 双线程加载 + LRU 缓存）
  - 子文件夹导航（前进/后退/上级 + 鼠标侧键 + Alt 快捷键）
  - 子文件夹递归扫描开关
  - Lightbox 大图查看（键盘/鼠标翻页）
  - 浮动详情面板（hover 显示 metadata，可置顶）
  - 喜欢标记（持久化到 likes.json）+ 只看喜欢过滤
  - 排序（时间/大小/名称）
  - 文件操作：移动到子文件夹、新建文件夹、F2 重命名、Delete 回收站、Ctrl+X/V 剪切粘贴、Ctrl+C 复制
  - 右键菜单：复制提示词、复制 LoRA、发送到输入框、用作例图、打开位置、销毁 metadata
- **例图自动提取** — 选择图片时自动解析 metadata 填充描述和标签
- **自定义背景** — 从图片提取主色调生成配套色板（WCAG 对比度保障）
- **外观设置** — UI 缩放、字体大小、字体样式、TTF 导入
- **工作区菜单自定义** — 拖拽排序、添加/删除菜单项
- **导出/导入** — 配置和提示词的文件导出导入
- **多语言** — 中文/英文切换
- **全局主题同步** — 所有窗口和组件统一使用 `current_palette()`
