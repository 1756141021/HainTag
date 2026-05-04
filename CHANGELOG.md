# Changelog

All notable changes to HainTag will be documented in this file.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
versioning follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.9.9] - 2026-05-04

### Fixed
- **历史记录 token 数为零** — 新一次生成开始时 `clear_output()` 触发 `textChanged`→`_persist_current_history_output`，此时 editor 刚清空，`_worker` 尚未启动（guard 失效），导致上一条历史记录的 `output_text` 被空字符串覆盖，时间轴显示 0 tokens。现在加一条守卫：若新文本为空而旧条目已有内容，直接跳过，不覆盖

## [0.9.8] - 2026-05-04

### Fixed
- **例图无限增殖** — `file_dialogs.py` 的全局"上次目录"被污染成 `examples_dir` 后，例图选择器打开就落在 examples 里，用户选已有 UUID 文件会触发 `copy_example_image` 制造副本。现在 `_select_image` 检测文件是否已在 `examples_dir`，若是则直接复用路径，不再复制
- **自动更新报"没有 exe 文件"** — ZIP 校验仅接受 `HainTag/HainTag.exe` 子目录结构，flat 打包直接失败。放宽为任意路径下存在 `haintag.exe` 即通过；`_apply_update` 自动探测 ZIP 解压后是否有 `HainTag/` 子目录，据此设定 robocopy 源路径；清理目录也升级为清理整个 temp 目录
- **例图 tags 照搬到输出** — 例图作为 assistant message 发给 AI，AI 把整个 tag 列表（含 `<lora:...>`）原封不动复读到输出。现在 `_format_example` 一并处理：过滤 lora token 避免触发权重引用；在格式里加明确约束"禁止照搬，须根据当前描述重新生成"，让 AI 只作风格参考

## [0.9.7] - 2026-05-03

### Added
- **TAG 补全支持中文查询** — `search_prefix` 检测 CJK 字符后走 substring 匹配 `translation` 字段，输入"女孩"能弹出 `1girl` / `multiple_girls` 等候选；ASCII 输入仍走原 prefix 匹配 `name` + `aliases`
- **补全 token 切分识别中文逗号** — `_do_complete` 现在同时按 `,` 和 `，` 切 token，CJK 输入法用户写 "女孩，猫耳" 不会让整段当一个 token

### Fixed
- **图片选择对话框默认目录共享** — 例图卡 / OC 库参考图 / metadata 销毁器 / metadata 查看器以前都用 `""` 当起点，每次都掉到进程 cwd。新增 `file_dialogs.pick_image_file/pick_image_files` 帮手共享一个"上次图片目录"缓存，启动时从 `image_manager_folder` 注入，picking 后自动更新

## [0.9.6] - 2026-05-02

### Fixed
- **TAG 补全弹窗多开重叠** — 主工作台 editor 和其它卡片输入框各自挂了独立 `TagCompleterPopup`，A 焦点离开时 200ms 延迟 hide 还没触发，B 已经 show 出来，两个弹窗同时可见。改为类级 `_active_popup` 单例：新 popup 调 `show_suggestions` 前先 hide 上一个，`hideEvent` 里清引用，全局只有一个补全窗可见

## [0.9.5] - 2026-05-02

### Added
- **TAG 补全全局覆盖** — 所有可编辑文本控件（QTextEdit / QPlainTextEdit / QLineEdit）默认挂上 Danbooru TAG 补全。覆盖到主输入、完整 / 无角色 TAG editor、例图 tags / 描述、Artist 名 / 触发词、OC 名 / tags / 服装、LLM 反推预设、设置面板各字段、prompt manager、销毁模板、metadata 销毁器（含动态 LoRA 行）、图像管理器搜索 / 重命名等
- **工作台 chip 视图新增「✏ 编辑」按钮** — copy bar 左端显式切换 chip / editor 视图，编辑态下 TAG 补全直接可用；流式生成期间强制 editor，结束后回到用户选择的视图
- **TagCompletionHost 协议接口** — 各 panel 实现 `set_tag_dictionary(d)`，window 启动时统一通过 `_dispatch_tag_dictionary()` 注入；新加的 panel 只要实现协议即可即插即用，window.py 无需逐个挂

### Changed
- **`tag_completer` 通用化** — `install_completer` 同时支持 QTextEdit、QPlainTextEdit、QLineEdit，新增 `install_completer_recursive(root, dict)` 一次性走树挂载。过滤只读 / 密码 / 显式 `noTagCompleter=True` 的控件；幂等，重复调用安全
- **动态生成的子节点也参与覆盖** — `LibraryPanel._add_artist/_add_oc`、`OCBanner._add_outfit`、`MetadataDestroyer._add_lora_row`、`PromptManagerWidget._on_rows_inserted`、`ExampleWidget` 卡片新增时都会再调一次 recursive 把新控件接入

### Fixed
- **completer 延迟回调访问已销毁对象崩溃** — `_focus_out` 200ms 延迟、`_check_active` 500ms 轮询、textChanged 150ms 防抖三条 timer 路径都可能在 dialog/卡片销毁后触发，原代码裸调 `popup.hide()` / `edit.hasFocus()` 抛 `RuntimeError`。统一改走 `_safe_hide_popup` + `_popup_alive` 守卫（先 `sip.isdeleted` 再 `RuntimeError` 兜底），`_pick_info` / `_insert_tag` 也加 `_target_edit` 删除检查

## [0.9.4] - 2026-05-02

### Fixed
- **流式生成卡死 / 输出区缩成一团** — 流式模式下，模型 reasoning 和正文 token 每次追加都会触发 `_TagStreamView.refresh()`，整批 chip 反复 deleteLater + 重建 + setStyleSheet，长输出（DeepSeek V4 Pro 等）下主线程被打满，最后 `apply_post_processing` 一刀又把 chip 全砸进 FlowLayout，inner 塌成一个 chip 大小。现在流式期间 chip 流暂停渲染、直接显示 editor 文本，完成后一次性建 chip
- **`_FlowLayout.sizeHint` 返回单 chip 尺寸** — 改为按内容宽度跑一次 `_do_layout` 拿真实累加高度，`adjustSize()` 不再把 inner 缩塌
- **生成完成后状态栏卡在「生成中」** — `_on_worker_finished` 漏掉了 `set_generation_status("done")`，现在补上，错误 / 取消路径也一起清流式标记

## [0.9.3] - 2026-05-02

### Fixed
- **存放台只在工作区外触发** — 卡片在工作区（应用窗口）内拖拽永不触发存放台；只有 `_floating=True`（已浮出为独立顶层窗口）的卡片才能形成 / 加入存放台
- **`settings.json` 保存抗锁** — `os.replace` 原子保存遇 Windows AV / OneDrive / 杀软扫描临时锁文件不再直接崩溃，新增三档退避重试（50ms / 150ms / 400ms），失败时回退直写保数据

### Changed
- **浮出卡片默认非顶置** — `WidgetCard.float_out` 不再默认置顶，去掉 `Qt.WindowStaysOnTopHint`，`_pinned` 默认 `False`；要顶置手动点针。这样从存放台拖出的卡片、新浮出的卡片都不会强行覆盖其它窗口
- **WidgetCard 新增 `set_pinned(bool)` 公开接口** — 给外部按需置位 / 复位顶置状态用



### Fixed
- **Prompt 顺序与深度语义** — 还原 SillyTavern 风格：`depth=0` 落在用户输入之后（最末端，约束力最强），`depth>0` 从末尾倒数 N 条插入；超出聊天范围的大 depth 自动溢出到历史之上作为 system 块，历史本身永不被切开
- **存放台主工作区限定** — 存放台只对已 floated-out 的卡片生效，主工作区内拖拽不再触发存放台；主工作台 `widget-main` 加入受保护集合，永不进入存放台
- **存放台位置** — `_tray_anchor_point` 改写，存放台必落在主工作台之外（优先右侧、再左侧、兜底屏幕右沿）
- **侧栏开启崩溃** — `card.is_floating()` 三处误把 `@property` 当方法调用导致 `TypeError: 'bool' object is not callable`，统一改为属性访问
- **i18n 文案** — `tip_depth` 恢复 v0.7.1 措辞（消息条数语义），`default_example_order` / `default_oc_order` 中文从「权重」改回「顺序」

### Changed
- **TagDictionary 懒加载** — 5.9 MB CSV 改为首次 `lookup` / `search_prefix` 时触发解析，启动期省 ~500 ms；`queue_csv()` 排队、`_ensure_loaded()` 自动加载
- **例图默认 order** — `default_example_order` 由 100 调整为 50，新建例图自动落在「例图参考开始/结束」标记区间内
- **打包瘦身** — spec 排除未用 PyQt6 子模块（QtQml / QtWebEngine / QtMultimedia / QtCharts 等）、关闭 UPX 压缩、过滤 50+ 个 Win10+ 系统自带的 `api-ms-win-*` 转发 DLL，dist 体积更干净，冷启动 DLL 解压开销降低

## [0.9.1] - 2026-05-01

### Added
- **主工作台 v3** — 输出区改为可编辑 TAG 流工作台，保留完整 TAG / 无角色 TAG 双页，支持 hover 说明、左键拖拽排序、右键横向拖拽权重和分类色 chip
- **OC 标题栏快捷入口** — 工作台标题区新增 OC chip 与就地 `+` 菜单，左键快速切换服装 / Order / Depth，右键可从工作台移除、编辑或打开 OC 库
- **历史时间线** — 工作台底部新增最近生成 Timeline，可查看全部历史，也可回填输入、完整 TAG 和无角色 TAG
- **本地化右键菜单** — 新增统一文本编辑菜单与应用菜单样式，输入框、输出区、资料库、历史、存放台、Dock 等自定义菜单统一走 i18n 和主题接口
- **TAG 自动补全复刻** — 自动补全弹层支持最佳匹配 / 相关分组、query 高亮、分类圆点、翻译 / alias / posts 展示和键盘 `↑/↓`、`Enter`、`Tab`、`Esc`
- **浮窗存放台** — 多个拖出的浮动卡片重叠或靠近时会自动折叠进常驻小收缩栏，可按标题恢复，并持久化位置与成员关系
- **标题栏语言快切** — 新增 `中 / EN` 快速切换按钮，不必每次都进入设置页

### Changed
- **LLM 反推工作台** — 按设计稿重建为顶部工具条、状态条、大图预览、实体色 tag chip、底部缩略图条和复制/发送动作区，保留批量图片、预设、独立 API、流式请求和 tag 字典校验
- **图像反推一体化** — Local / LLM 改为卡片内容分段按钮切换，LLM 工作台按当前图片比例自动切换横版/竖版布局，并保留预览区与 tag 区边界拖动
- **本地反推 UI** — 本地 ONNX 反推页重建为设置 / 推理两态工作台，保留模型目录、Python 环境、自动配置、类别过滤、双阈值、置信度、复制和发送功能
- **Dock 默认列表化** — 左侧 Dock 默认展开为图标字母 + 完整标题，避免窄条状态下只显示字母导致难以辨认
- **右侧工作台轨道** — 生成历史和 Artist / OC 资料库改为共享同一条右侧侧栏轨道，减少重复开关和空间冲突
- **记忆模式深度语义** — `build_messages()` 改为按“对话回合距离”插入 depth>0 条目，保留完整 user/assistant 回合，不再按裸 message 数打散上下文
- **资料库布局** — Artist / OC 改为单入口标签切换侧栏，记住上次停留分区，减少操作冗余
- **顶置反馈** — 主窗口和浮动卡片的置顶按钮改成统一的双态视觉、tooltip 和高亮反馈，恢复状态时与真实 window flag 同步
- **更新器** — 程序内更新继续走 ZIP 下载 / 校验 / 解压 / 自动替换流程，补齐失败提示、损坏包校验和缺失 exe 检查文案

### Fixed
- **发送确认失效** — 输入区发送快捷键从全局 shortcut 下沉到编辑器级别，修复“设置可切换但实际无效”的问题
- **生成历史可读性** — 历史记录现在按时间倒序、按天分组，支持复制输入/完整 TAG/无角色 TAG，并按设置自动清理旧记录
- **历史接口兼容** — `HistorySidebar.entry_selected(QString)` 保留旧输出回填接口，同时增加完整恢复入口，避免旧调用方断层
- **资料库与历史开关** — 资料库 / 历史互斥打开，重复触发当前入口可关闭，关闭按钮和 `Esc` 都能收起右侧轨道
- **OC 数据显示** — 过滤空 OC，修正短中文 OC 名在标题栏 chip 中被压成竖块的问题；从工作台移除只取消启用，不删除库数据
- **存放台恢复规则** — 存放台只在 2 个及以上成员时显示，成员回到 1 个时自动恢复剩余卡片并隐藏，避免空壳或无用靶子常驻
- **浮窗合并范围** — 主工作台与图像反推卡片也可进入存放台，存放 / 恢复时不再留下空白顶层窗口
- **主题与字号通用化** — 工作台、菜单、资料库、本地 / LLM 反推和 tag 区统一接入 `current_palette()`、`_fs()`、`_dp()`，跟随背景、亮暗主题、字体和 UI 缩放
- **语言切换漏改** — 引导、快捷键文案、历史侧栏、资料库、右键菜单、浮窗存放台和标题栏快速入口都能随语言切换即时刷新

## [0.9.0] - 2026-04-26

### Changed
- **程序内更新** — "立即更新"按钮改为直接下载 ZIP + 自动替换 + 重启，不再打开浏览器手动操作
  - 三级 HTTP fallback 下载（httpx→requests→urllib），进度条显示，支持取消
  - ZIP 校验（testzip + 入口文件检查）+ 解压
  - 批量替换脚本：robocopy /MIR 镜像同步，PID 等待循环，杀毒锁文件自动重试
  - 源码模式（非 frozen）保持原有行为（打开浏览器）

## [0.8.1] - 2026-04-26

### Changed
- **LLM 预设管理化** — 删除 5 个硬编码提示词预设（通用/详细/NSFW/简洁/自定义），替换为用户自管理的预设系统：combo 选择 + 新建/删除 + 名称/内容编辑，预设数量无限制
- `AppSettings` 字段 `tagger_llm_prompt_preset` / `tagger_llm_custom_prompt` 替换为 `tagger_llm_presets`（list）/ `tagger_llm_active_preset`（int）
- 旧配置自动迁移：`tagger_llm_custom_prompt` 非空时转为 `[{"name": "Custom", "text": 旧值}]`

### Fixed
- 独立 API 字段（URL/密钥/模型）编辑后未触发保存，重启丢失配置
- `apply_llm_settings()` 初始化加载时误触 `settings_changed` 信号

## [0.8.0] - 2026-04-26

### Added
- **LLM 反推批量推理** — 支持多图拖入/选择，逐张队列处理，进度显示，中途可停止
- **提示词预设** — 通用/详细/NSFW/简洁/自定义 5 种预设切换，自定义预设可编辑并持久化
- **结果结构化** — LLM 输出自动解析为独立 tag，有效 tag 按 Danbooru 分类着色，无效 tag 灰显，hover 显示中文翻译
- **独立 API 配置** — LLM 反推可使用独立的 API 地址/密钥/模型，或共享主工作台配置
- **FlowLayout** — tag 标签流式布局，自动换行排列

### Changed
- `_LLMTaggerTab` 完全重写：批量队列、预设选择、API 切换、折叠结果区域
- `_DropZone` 支持 `multi=True` 多图模式，向后兼容单图模式
- `InterrogatorWidget` 新增 `set_tag_dictionary()` / `apply_llm_settings()` / `collect_llm_settings()` 接口
- `AppSettings` 新增 6 个 `tagger_llm_*` 字段，自动持久化
- 配置导出安全约束扩展：`tagger_llm_api_key` 和 `tagger_llm_base_url` 也被屏蔽

## [0.7.4] - 2026-04-26

### Changed
- **DPI 全量转换** — 全部 25 个 Python 文件中约 200 处硬编码像素值转换为 `_dp()` 调用，覆盖 window、所有 widget、dialog、panel、sidebar，1-2px 微小值和 0 值按规则跳过
- **Interrogator i18n** — 图像反推模块约 37 处硬编码中文替换为 `translator.t()` 调用，新增 `interr_` 前缀翻译键（zh-CN + en）
- **样式规范化** — example_widget 硬编码颜色 `#c08040` 和 `font-size: 10px` 改走 `current_palette()` 和 `_fs()`

## [0.7.3] - 2026-04-26

### Added
- **导出/导入细目** — 设置面板配置导出/导入改为细分勾选项，支持外观与字体、模型参数、提示词、例图、OC 库、画师库、条目默认值、TAG 标记、窗口布局和生成历史
- **配置包 scope 列表** — 新配置包写入 `scope: [...]`，导入时只合并用户勾选且配置包内存在的部分

### Fixed
- **敏感配置保护** — 配置导出继续强制排除 API Key 和 API Base URL，导入也不会覆盖当前机器的 API Key / Base URL
- **旧配置兼容** — 旧 `settings_page` / `full_profile` 配置包可按新的细分勾选项导入，未勾选内容保持当前状态

## [0.7.2] - 2026-04-26

### Added
- **DPI 尺寸接口** — 新增 `_dp()`，设置面板、Metadata、图像反推等高风险固定尺寸开始按屏幕 DPI 缩放
- **Metadata 批量全部保存** — 批量销毁结果支持一键保存到目录，重名文件自动追加后缀
- **Metadata 完整编辑入口** — 单图底栏新增显式编辑按钮，编辑界面支持 prompts、Steps、Sampler、CFG、Seed、Size、Model 和 LoRA 列表
- **记忆清空入口** — 输入框右键菜单新增“清空记忆”

### Fixed
- **记忆模式实际带历史** — `build_messages()` 现在可接收最近对话历史；AI 回复成功后才写入记忆，失败和取消不会污染上下文
- **主题刷新接口补齐** — Dock、折叠区、引导层、TAG 补全、Prompt 预览等组件补齐主题刷新入口

## [0.7.1] - 2026-04-08

### Added
- **自动配置 Python 环境** — 当 onnxruntime 无法在当前 Python 加载时，自动下载 Python 3.12 嵌入式包 + onnxruntime/numpy/Pillow 到 AppData，无需用户手动安装依赖或拥有 ComfyUI
  - 下载进度条实时显示，中文环境自动使用清华 pip 镜像加速
  - 安装完成后自动切换到推理模式，重启后自动检测已安装环境
- **置信度显示开关** — 推理结果支持一键切换显示/隐藏置信度百分比
- **手动选择 Python 路径** — 设置页新增手动选择按钮，可指定任意已安装 onnxruntime 的 Python（如 ComfyUI 的 python.exe）

### Fixed
- **tag 映射格式兼容** — 修复 dict 格式 tag_mapping.json 读取 key 而非 tag 字段的问题，修复类别名大小写不匹配（General vs general）
- **Python 路径持久化** — 外部 Python 路径 (`tagger_python_path`) 现在正确保存到 settings.json，重启后自动恢复
- **模型目录扫描** — 支持任意 .onnx 文件名（不再要求 model_optimized.onnx），兼容 ComfyUI 等第三方目录结构
- **启动字体** — 修复启动时 `generate_qss()` 缺少 `body_font_pt` 和 `font_family` 参数，导致首次加载使用系统默认字体而非用户设置
- **主题/字号响应** — 图像反推组件所有 inline style 改用 `_fs()` 接口，`apply_theme()` 实现完整重建，字体大小切换全局生效
- **重启应用** — 修复源码模式下重启应用闪退（正确使用 `python -m native_app`）
- **DLL 冲突** — 从打包中移除 onnxruntime（`excludes=['onnxruntime']`），避免 dist 内的 Python 3.14 版 DLL 与外部 Python 3.12 的 onnxruntime 冲突导致初始化失败
- **子进程环境隔离** — 清理 PyInstaller 注入的 PYTHONHOME/PYTHONPATH 环境变量和 PATH 中的 _internal 路径，防止污染外部 Python 子进程

---

## [0.7.0] - 2026-04-07

### Added
- **图像反推** — 新增图像反推卡片，支持两种模式：
  - **本地推理**：使用 cl_tagger ONNX 模型离线识别 Danbooru 标签（需安装 onnxruntime），支持选择 ComfyUI 等已有模型目录，首次使用有引导页面
  - **LLM 反推**：使用已配的多模态 API 发送图片让 LLM 生成标签，流式输出
  - 灵敏度滑块（一般/角色阈值）、类别过滤开关、反推词黑名单
  - 推理结果可复制或发送到工作台输入框
  - 模型路径持久化，重启后自动加载

---

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
