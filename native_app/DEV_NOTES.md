# native_app/ 文件说明

> 每个文件是干什么的、负责什么功能、包含什么内容。修改功能前先查这里定位文件。

## _version.py
- 单一版本来源：`__version__ = "0.9.2"`
- 被 `__init__.py` 导出，被 `window.py` 读取显示在工作区右下角
- 版本号遵循 SemVer（语义化版本）

## __main__.py
- 入口点，一行代码调用 `main()`

## main.py
- 应用启动流程：创建 QApplication → 加载字体 → 设置 QFont → 生成 QSS（含 body_font_pt + font_family） → 创建 MainWindow → exec 事件循环
- 全局异常处理钩子（sys.excepthook）
- 确保 stdio 存在（打包后 stderr/stdout 可能为 None）

## window.py（~1650 行，最大最核心的文件）
- **MainWindow 类**：整个应用的主窗口
- **窗口行为**：无边框窗口、WS_THICKFRAME、WM_NCHITTEST（用 QCursor.pos() 取逻辑坐标解决 150% DPI）、标题栏拖拽、最大化/最小化/置顶
- **标题栏按钮**：设置⚙、语言切换 `中/EN`、添加例图+、置顶📌/📍、最小化、最大化、关闭
- **卡片管理**：创建/删除/dock/restore 提示词卡片、输入卡片、输出卡片、例图卡片。卡片可自由叠加（PPT 图层式），点击置顶
- **右侧轨道**：历史与资料库改为共用一条 right rail，通过 `_open_right_sidebar()` / `_close_right_sidebar()` / `_reparent_sidebar_for_mode()` 统一管理，主卡片浮动时会整体跟随重挂载
- **浮窗存放台**：`FloatingTrayWidget` + `_store_card_in_tray()` / `_restore_from_floating_tray()` / `_restore_floating_tray_state()` 负责把重叠浮窗折叠成可恢复堆栈，并把状态写入 `AppState.floating_tray`
- **Dock 管理**：右键菜单（添加例图）、dock 项关闭信号、dock 预览
- **工作区右键菜单**：注册表驱动（_DEFAULT_MENU_ORDER + _workspace_menu_items 映射），支持用户拖拽自定义顺序（_show_menu_order_dialog 覆盖面板），菜单项包含收拾工作区、清空布局等
- **设置面板**：内嵌覆盖层模式（从 content_host 右侧滑出），settingsReveal 属性驱动动画（320ms OutCubic），_settings_backdrop 半透明遮罩点击关闭
- **API 调用**：_handle_send_action 构建 payload → _start_worker 启动 ChatWorker → delta 路由到 OutputWidget，发送后清空输入框
- **后台记忆**：_conversation_history 列表维护最近对话上下文，不在 UI 显示；成功回复后写入 user/assistant，右键输入框可清空记忆
- **发送确认**：全局发送快捷键已下沉到 `InputWidget.install_send_key_handler()`；窗口层只消费 `send_requested`，发送模式由 `AppSettings.send_mode` 决定
- **获取模型**：_fetch_models 从 API 拉取模型列表填充 QComboBox
- **导出导入**：config bundle 和 prompts 的文件导出导入
- **配置细分导入导出**：按 scope 列表导出/导入外观、模型参数、提示词、例图、库、布局和历史；导入时只合并勾选项
- **外观菜单**：主题切换（暗/亮）、卡片透明度、UI 缩放、字体大小、字体 profile
- **状态保存**：窗口位置/大小、所有卡片位置、设置、提示词、例图 → settings.json

## models.py
- **纯数据类**（@dataclass），无逻辑：
  - `AppState`：整个应用状态（设置+窗口+dock+提示词+例图+widgets+输入历史）
  - `AppSettings`：API 配置、模型参数、UI 偏好、workspace_menu_order、发送模式、历史保留天数、资料库上次分区、条目默认值（default_example_order/depth、default_oc_order/depth）
  - `PromptEntry`：单条提示词（name/role/depth/order/enabled/content）
  - `ExampleEntry`：单个例图（image_path/tags/description/order/depth）
  - `OutfitEntry`：服装方案（name/tags/active），OC 子项
  - `ArtistEntry`：画师条目（name/artist_string/reference_images），纯存储/复制用，不参与消息发送
  - `OCEntry`：OC 角色（character_name/tags/reference_images/outfits/order/depth/enabled），`merged_tags()` 合并角色 tag + 所有启用服装 tag
  - `HistoryEntry`：生成历史条目（input_text/output_text/timestamp/model）
  - `DockState`：dock 位置/展开状态/尺寸
  - `WidgetState`：卡片位置/可见性/docked
  - `WindowState`：窗口几何信息
  - `FloatingTrayMemberState` / `FloatingTrayState`：浮窗存放台位置与成员快照，用于重启恢复
  - `ConfigBundle`：导出配置包，`scope` 兼容旧字符串和新细分 scope 列表
  - `ErrorReport`：错误报告
- **metadata/models.py**：`ImageMetadata` 提供 metadata 编辑辅助方法：读取/设置参数、解析/写入 Size、把 LoRA 列表同步回 positive prompt

## storage/ 包（原 storage.py，SRP 拆分后）
- **Facade 模式**：`AppStorage`（`_facade.py`）是门面类，委托给 12 个域子管理器
- **外部接口零破坏**：`from .storage import AppStorage` 不变，所有方法签名不变
- 子管理器：
  - `_paths.py` — `StoragePaths` dataclass，共享路径根目录
  - `_state.py` — `StateStorage`：load_state / save_state → `settings.json`
  - `_likes.py` — `LikesStorage`：load_likes / save_likes → `likes.json`
  - `_hints.py` — `HintsStorage`：load_shown_hints / save_shown_hints → `hints.json`
  - `_library.py` — `LibraryStorage`：load/save_library + copy/remove_library_image → `library.json` + `library_images/`
  - `_history.py` — `HistoryStorage`：load/save/append/clear_history → `history.json`；统一做 newest-first 排序、按保留天数清理、内部上限 500 条
  - `_fonts.py` — `FontStorage`：import_font / list_imported_fonts / font_file_path / load_imported_fonts → `fonts/index.json`
  - `_examples.py` — `ExampleStorage`：copy/save/remove_example_image + serialize/deserialize → `examples/`
  - `_prompts.py` — `PromptStorage`：export/import_prompts（无状态，纯 JSON IO）
  - `_config_bundle.py` — `ConfigBundleStorage`：export/import_config_bundle + scoped merge/state/library/history restore（跨域协调器，注入 FontStorage + ExampleStorage）
  - `_error_reports.py` — `ErrorReportStorage`：write_error_report → `reports/`

## api_client.py
- `ChatWorker`（QThread）：后台执行 API 请求
- 支持两种 HTTP 后端：httpx（优先）和 requests（fallback）
- 流式 SSE 解析：逐行读取 `data:` 前缀，解析 JSON，提取 `choices[0].delta.content`
- 非流式：完整请求后提取 `choices[0].message.content`
- 信号：delta_received、summary_received、error_received、cancelled、finished_cleanly
- 空 choices 防护（避免 IndexError）
- 取消时 drain response（避免 ResponseNotRead）

## logic.py
- `build_messages()`：把提示词 + 例图 + 用户输入组装成 API messages 数组，**SillyTavern 风格深度**
  - `depth=0` 条目落在 active_input 之后（末端，约束力最强）
  - `depth>0` 按 `len(messages) - depth` 从末尾倒数 N 条插入
  - 大 depth 落点会跌入历史区间时自动溢出到历史之上（above-history zone），形成顶部 system 块
  - `history_floor` 标记历史末端，所有 depth>0 插入都受这个 floor 保护，历史块永不被切开
  - 同 depth 内按 `order` 升序作为整块 splice
- 记忆模式接收 `history`：原序逐条 append，过滤空内容/非法 role
- `_entry_block()`：把 PromptEntry / OCEntry / ExampleEntry 转成 `[{role, content}, ...]` 块；OC = `user(Character: 名)` + `assistant(merged_tags)` 双消息
- `normalize_api_base_url()`：清理 API URL，剥掉尾部 `/chat/completions`
- `extract_active_input()`：记忆模式整段保留；非记忆模式按 `---` 切，只取最后一段
- `validate_examples()`：例图必须同时有描述和标签
- `estimate_text_tokens()` / `estimate_messages_tokens()`：token 估算

## theme.py
- **主题模板系统**：DARK_PALETTE / LIGHT_PALETTE 两套色板（Charcoal/Oatmeal），`generate_qss(theme, custom_palette, card_opacity)` 生成 QSS
- `_QSS_TEMPLATE`：QSS 模板字符串，用 `{bg}` `{text}` `{line}` 等占位符，支持暗/亮主题和自定义色板
- `scale_qss()`：根据 UI 缩放百分比调整 QSS 中的像素值
- `extract_palette_from_image()`：从图片提取主色调自动生成配套色板（HSL 降饱和 + WCAG 对比度保障）
- 卡片透明度由 `card_opacity` 参数控制（30-100%）
- `is_theme_light()`：公开接口，返回当前主题是否为浅色。供自定义绘制组件（ToggleSwitch、TagTextEdit）和 inline style（token 计数）读取
- `current_palette()`：返回 `generate_qss()` 最后一次解析出的完整色板。所有自定义绘制组件统一调用此接口获取颜色，确保与主窗口主题/背景/亮度完全同步
- `_fs(key)`：全局字号快捷函数，返回当前 body_font_pt 对应的缩放字号。key 为 `'fs_9'`~`'fs_14'`，所有 inline stylesheet 统一调用 `_fs('fs_12')` 替代硬编码 px，字体大小设置全局生效
- `font_sizes()`：返回完整字号 token 字典 `{fs_9: '9px', ...}`
- `generate_qss()` 新增 `body_font_pt` 参数，QSS 模板中 21 处 font-size 改为 `{fs_N}` token，9 个 widget 文件 70 处 inline font-size 改为 `_fs()` 调用
- 所有 rgba alpha 值统一使用 0-1 标度，避免插值时 0-1 与 0-255 混用导致错误
- `is_light` 判断基于 `_relative_luminance(palette['bg']) > 0.18`，与 `_auto_text_colors` 使用同一阈值，保证卡片颜色与文字颜色始终协调

## ui_tokens.py
- UI 数字常量集合：
  - 窗口：WINDOW_RADIUS(12)、WINDOW_SURFACE_MARGIN(8)、WINDOW_EDGE_GAP(10)、TITLEBAR_HEIGHT(38)
  - Dock：DOCK_COLLAPSED_THICKNESS(40)、DOCK_EXPANDED_SIDE(132)、各种 MIN/MAX
  - Widget 卡片：WIDGET_RESIZE_EDGE(8)、WIDGET_RESIZE_CORNER(14)
  - 设置面板：SETTINGS_WIDTH(280)
  - CSS class 常量：CLS_FIELD_INPUT、CLS_FIELD_SPIN 等
- `_dp(px)`：按主屏幕逻辑 DPI 缩放像素尺寸。全部 25 个 widget/window 文件的 `setFixed*`、`setMinimum*`、`setMaximum*`、`setContentsMargins`、`setSpacing`、`addSpacing`、`resize` 等布局调用均已通过 `_dp()` 转换。值为 0 或 1-2 的跳过，`setFixedHeight(1)` 分隔线保持原样

## file_filters.py
- 文件选择过滤器统一入口，避免在各组件里散落 `Images (*.png...)` 等硬编码字符串
- `image_filter()` / `png_filter()` / `json_filter()` / `config_filter()` / `ttf_filter()` / `python_filter()` 均接收 `Translator`，返回当前语言对应文案
- 图像管理器、Metadata、图像反推、配置导入导出和字体导入应优先使用这里的接口，保证 i18n 和后续格式扩展集中维护

## i18n.py
- `Translator` 类：加载 resources/lang/*.json 翻译文件
- `t(key)` 方法返回翻译后的字符串，找不到则返回 key 本身
- 支持运行时切换语言
- available_languages() 列出可用语言

## font_loader.py
- `load_app_fonts()`：从 resources/fonts/ 加载内嵌字体
- `build_body_font()`：根据 font_profile 和 point_size 构建 QFont
- `create_app_font()`：创建应用级字体

## llm_tagger_logic.py
- LLM 反推处理逻辑，纯函数模块，无 UI 依赖
- `parse_llm_tags(raw_text) → list[str]`：解析 LLM 输出为独立 tag。逗号分割优先，fallback 换行分割，去重去格式
- `validate_tags(tags, dictionary) → list[ParsedTag]`：用 TagDictionary 校验 tag 有效性，填充 category_id + 中文翻译
- `build_vision_messages(image_path, prompt_text) → list[dict]`：构建 OpenAI 多模态 vision messages（base64 图片）

## widgets/text_context_menu.py
- 本地化文本编辑菜单公共模块，用于替换 Qt 默认英文右键菜单
- `apply_app_menu_style(menu)`：给 `QMenu` 套用当前 `current_palette()`、`_fs()`、`_dp()`，菜单背景、hover、禁用态跟随全局主题
- `show_text_edit_context_menu()` / `show_line_edit_context_menu()`：提供撤销、重做、剪切、复制、粘贴、删除、全选，全部通过 `Translator.t()` 获取文案
- `install_localized_context_menus(root, translator)`：批量为默认右键策略的 `QTextEdit` / `QLineEdit` 安装本地化菜单，不覆盖已有自定义菜单

## widgets/workbench_oc.py
- 主工作台标题栏 OC 快捷条与就地气泡菜单
- `WorkbenchOCStrip` 只展示启用且有可见内容的 OC，提供：
  - 标题栏 `+` 就地添加 OC，不直接打开远处资料库
  - OC chip 左键打开 `OCBubble`，可快速调整 Order / Depth 与服装
  - OC chip 右键菜单提供“从工作台移除 / 编辑 OC / 打开 OC 库”
- `remove_requested` 只表示取消当前工作台启用状态，不永久删除 OC 库资料；真实数据更新由 `MainWindow` / `LibraryPanel` 接口承接
- 样式统一走 `current_palette()`、`_fs()`、`_dp()`，中文短名通过 `fontMetrics().elidedText()` 防止压成竖块

## widgets/workbench_timeline.py
- 主工作台底部最近生成时间线，显示最近 18 条历史摘要
- `view_all_requested` 打开真实历史侧栏；`entry_selected` 发出对应 `HistoryEntry` 或当前 item，供窗口回填输出 / 完整恢复
- 支持折叠行和横向展开卡片，时间、prompt 摘要、token 数和状态点均走主题 token
- 只负责可见前端和信号，不直接读取磁盘；历史来源由 `AppStorage.load_history()` / `HistorySidebar` / `MainWindow` 统一注入

## tag_dictionary.py
- **TagDictionary 类**：通用 Danbooru TAG 词典加载器
- `queue_csv(path)`：**懒加载入口** —— 把 CSV 路径排进 `_lazy_paths`，不立即解析；首次 `lookup` / `search_prefix` 触发 `_ensure_loaded()` 才读盘解析。5.9 MB CSV 解析耗时 ~500 ms，靠这个把启动成本推迟到用户真正需要 tag 翻译的瞬间
- `load_csv(path)`：传统同步加载（直接解析），与 `queue_csv` 互斥地置 `_loaded = True`
- `translate(tag) → str | None`：查中文翻译（O(1) dict 查询，会触发懒加载）
- `lookup(tag) → TagInfo | None`：查完整信息（翻译、分类号、使用次数、别名、大类、子类）
- `search_prefix(prefix, limit)`：前缀模糊查询，按 count 倒序，给自动补全弹层用
- 自动建立别名索引：查 `blueeyes` 也能命中 `blue_eyes` 的翻译
- tag 名标准化：strip、lower、空格→下划线
- TagInfo dataclass：name、translation、category_id、count、aliases、group、subgroup

## metadata/ 包 — AI 图像元数据解析与写入引擎
- **metadata/models.py**：`ImageMetadata` dataclass（positive/negative/parameters/loras/model/workflow_json）+ `GeneratorType` enum（A1111/ComfyUI/NovelAI/Fooocus/Unknown）
- **metadata/reader.py**：`MetadataReader` — 自定义 PNG chunk 解析（绕过 PIL iTXt bug），tEXt 先试 UTF-8 再 fallback latin-1。支持 PNG tEXt/iTXt/zTXt + JPEG/WebP EXIF UserComment。Plugin-based parser 分发
- **metadata/writer.py**：`MetadataWriter` — 二进制 chunk 级操作，IDAT 逐字节不变。`write_chunks(src, dst, chunks)` 底层接口，`destroy(src, dst)` 用垃圾文本覆盖，`edit(src, dst, metadata)` 用有意义内容覆盖。销毁文本：「哈基米哦南北绿豆~阿西嘎哈椰果奶龙~」，A1111 格式
- **metadata/parsers/base.py**：`BaseMetadataParser` ABC — `can_parse(chunks)` + `parse(chunks, image_path)`
- **metadata/parsers/a1111.py**：A1111/Forge parser — 按 `Steps:` 和 `Negative prompt:` 分割，提取 LoRA `<lora:name:weight>`，处理引号内 Lora hashes
- **metadata/parsers/comfyui.py**：ComfyUI parser — 遍历 JSON 节点找 KSampler/CLIPTextEncode/CheckpointLoader
- **metadata/parsers/novelai.py**：NovelAI parser — `Comment` JSON（`uc`=负面），fallback alpha 通道 LSB 隐写（`stealth_pngcomp` magic）
- **metadata/parsers/fooocus.py**：Fooocus parser — JSON 格式
- **metadata/thumb_cache.py**：缩略图缓存与后台加载引擎
  - `ThumbCache`：线程安全 LRU 内存缓存（`OrderedDict`，默认上限 500 个 QPixmap）
  - `get(path, size)` → 精确命中；`get_any(path)` → 模糊命中任意尺寸（缩放过渡用）
  - `request(path, size, callback)` → 缓存 miss 时排队后台加载，完成后回调
  - `cancel_pending()` → 清空队列（排序/缩放切换时用）
  - `ThumbLoaderThread`（QThread × 2，round-robin 分发）：PIL `draft()` + `thumbnail()` 快速降采样，`QImage` 带显式 `bytesPerLine` 避免 stride 对齐问题
  - 信号：`thumbnail_ready(path, size, QPixmap)`

## tagger.py
- **TaggerEngine 类**：cl_tagger ONNX 推理引擎，支持两种模式
  - **直接模式**：进程内 import onnxruntime 推理（快，需兼容 Python）
  - **子进程模式**：调用外部 Python 执行 tagger_subprocess.py（慢，兼容性强）
  - `find_model()`：搜索模型文件（自定义目录 → AppData → HuggingFace 缓存）
  - `load()`：加载模型，直接 import 失败时切换到子进程模式
  - `predict()`：推理并返回按类别分组的标签 `{category: [(tag, prob), ...]}`
  - `_predict_subprocess()`：子进程推理，清理 PyInstaller 环境变量（PYTHONHOME/PYTHONPATH）和 PATH 中的 `_internal` 路径防止 DLL 冲突，使用 `-E` 参数隔离
  - 8 个标签类别：general/character/copyright/meta/model/rating/quality/artist
- **TaggerDownloadWorker**（QThread）：后台从 HuggingFace 下载模型
- **TaggerWorker**（QThread）：后台执行推理
- **TagMapping**：解析 tag_mapping.json，支持 list 和 dict 两种格式，类别名自动 `.lower()`
- **打包注意**：spec 必须 `excludes=['onnxruntime']`，否则 dist 内的 Python 3.14 版 onnxruntime DLL 会与外部 Python 的版本冲突

## tagger_subprocess.py
- 独立 Python 脚本，被子进程模式调用
- 命令行参数：image_path model_path mapping_path [gen_threshold] [char_threshold] [categories] [blacklist]
- 输出 JSON 到 stdout：`{"results": {...}}` 或 `{"error": "...", debug_info...}`
- 依赖：onnxruntime、numpy、Pillow（必须在外部 Python 中可用）
- 错误时输出详细 debug 信息（sys.path、sys.prefix、环境变量、traceback）

## python_env.py
- **嵌入式 Python 环境管理器**：当 onnxruntime 在宿主 Python 不可用时，自动下载独立 Python 环境
- `get_embedded_python_path()`：检查 `%APPDATA%/HainTag/python_env/python.exe` 是否存在
- `is_env_usable(path)`：subprocess 测试 onnxruntime 是否可导入
- **PythonEnvSetupWorker**（QThread）：后台下载安装流水线
  - 下载 Python 3.12 嵌入式包 → 解压 → 修补 ._pth → 安装 pip → pip install onnxruntime/numpy/Pillow
  - 信号：`progress(str, int)`、`finished(str)`、`error(str)`
  - 自动判断 locale 决定是否用清华 pip 镜像

## error_reporting.py
- `report_error()`：生成错误报告文件 + 弹窗显示
- `format_exception_details()`：格式化异常堆栈
- `runtime_mode()`：检测是 dist 还是 source 运行模式

## updater.py
- **UpdateChecker**（QThread）：后台查询 GitHub Releases API (`/repos/1756141021/HainTag/releases/latest`)
  - 信号：`update_available(version, changelog, download_url)` / `no_update` / `check_error`
  - 版本比较：`_parse_version()` 解析 `v0.5.21` → `(0, 5, 21)` tuple 比较
  - HTTP 后端：httpx → requests → urllib（三级 fallback）
- **UpdateDownloadWorker**（QThread）：下载 + 验证 + 解压更新 ZIP
  - 信号：`progress(str, int)` / `download_done(str)` / `error(str)`
  - 三级 HTTP fallback 分块下载（8KB chunks），每 chunk 检查取消标志
  - 验证：`zipfile.testzip()` + 确认 `HainTag/HainTag.exe` 存在
  - 解压到临时目录，删除 ZIP，emit `download_done(extracted_dir)`
- **`_generate_update_script()`**：生成 batch 替换脚本写入 %TEMP%
  - 等待旧 PID 退出 → `robocopy /MIR` 镜像替换 → 启动新 exe → 自删除
- **UpdateDialog**（QDialog）：更新提示弹窗
  - 显示新版本号 + changelog
  - 三个按钮：立即更新 / 跳过此版本（存 skipped_version）/ 下次提醒
  - 点击更新后：隐藏按钮，显示进度条 + 取消按钮，下载完成后 accept
  - 源码模式（`sys.frozen` 不存在）fallback 打开浏览器
- **NoUpdateDialog**：已是最新版提示
- window.py 中：`_check_update_auto()`（启动 3s 后自动，尊重 skipped_version）/ `check_update_manual()`（设置面板按钮，忽略 skip）/ `_apply_update()`（写脚本 → 保存状态 → 启动脚本 → 退出）

## resources/
- `resources/lang/zh-CN.json`：中文翻译（所有 UI 字符串）
- `resources/lang/en.json`：英文翻译
- `resources/fonts/`：内嵌字体文件
