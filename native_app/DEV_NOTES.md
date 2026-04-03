# native_app/ 文件说明

> 每个文件是干什么的、负责什么功能、包含什么内容。修改功能前先查这里定位文件。

## _version.py
- 单一版本来源：`__version__ = "0.1.0"`
- 被 `__init__.py` 导出，被 `window.py` 读取显示在工作区右下角
- 版本号遵循 SemVer（语义化版本）

## __main__.py
- 入口点，一行代码调用 `main()`

## main.py
- 应用启动流程：创建 QApplication → 加载字体 → 加载 QSS 主题 → 创建 MainWindow → exec 事件循环
- 全局异常处理钩子（sys.excepthook）
- 确保 stdio 存在（打包后 stderr/stdout 可能为 None）

## window.py（~1650 行，最大最核心的文件）
- **MainWindow 类**：整个应用的主窗口
- **窗口行为**：无边框窗口、WS_THICKFRAME、WM_NCHITTEST（用 QCursor.pos() 取逻辑坐标解决 150% DPI）、标题栏拖拽、最大化/最小化/置顶
- **标题栏按钮**：设置⚙、添加例图+、置顶📌、最小化、最大化、关闭
- **卡片管理**：创建/删除/dock/restore 提示词卡片、输入卡片、输出卡片、例图卡片。卡片可自由叠加（PPT 图层式），点击置顶
- **Dock 管理**：右键菜单（添加例图）、dock 项关闭信号、dock 预览
- **工作区右键菜单**：注册表驱动（_DEFAULT_MENU_ORDER + _workspace_menu_items 映射），支持用户拖拽自定义顺序（_show_menu_order_dialog 覆盖面板），菜单项包含收拾工作区、清空布局等
- **设置面板**：内嵌覆盖层模式（从 content_host 右侧滑出），settingsReveal 属性驱动动画（320ms OutCubic），_settings_backdrop 半透明遮罩点击关闭
- **API 调用**：_handle_send_action 构建 payload → _start_worker 启动 ChatWorker → delta 路由到 OutputWidget，发送后清空输入框
- **后台记忆**：_conversation_history 列表维护对话上下文，不在 UI 显示
- **获取模型**：_fetch_models 从 API 拉取模型列表填充 QComboBox
- **导出导入**：config bundle 和 prompts 的文件导出导入
- **外观菜单**：主题切换（暗/亮）、卡片透明度、UI 缩放、字体大小、字体 profile
- **状态保存**：窗口位置/大小、所有卡片位置、设置、提示词、例图 → settings.json

## models.py
- **纯数据类**（@dataclass），无逻辑：
  - `AppState`：整个应用状态（设置+窗口+dock+提示词+例图+widgets+输入历史）
  - `AppSettings`：API 配置、模型参数、UI 偏好、workspace_menu_order、条目默认值（default_example_order/depth、default_oc_order/depth）
  - `PromptEntry`：单条提示词（name/role/depth/order/enabled/content）
  - `ExampleEntry`：单个例图（image_path/tags/description/order/depth）
  - `OutfitEntry`：服装方案（name/tags/active），OC 子项
  - `ArtistEntry`：画师条目（name/artist_string/reference_images），纯存储/复制用，不参与消息发送
  - `OCEntry`：OC 角色（character_name/tags/reference_images/outfits/order/depth/enabled），`merged_tags()` 合并角色 tag + 所有启用服装 tag
  - `HistoryEntry`：生成历史条目（input_text/output_text/timestamp/model）
  - `DockState`：dock 位置/展开状态/尺寸
  - `WidgetState`：卡片位置/可见性/docked
  - `WindowState`：窗口几何信息
  - `ConfigBundle`：导出配置包
  - `ErrorReport`：错误报告

## storage/ 包（原 storage.py，SRP 拆分后）
- **Facade 模式**：`AppStorage`（`_facade.py`）是门面类，委托给 12 个域子管理器
- **外部接口零破坏**：`from .storage import AppStorage` 不变，所有方法签名不变
- 子管理器：
  - `_paths.py` — `StoragePaths` dataclass，共享路径根目录
  - `_state.py` — `StateStorage`：load_state / save_state → `settings.json`
  - `_likes.py` — `LikesStorage`：load_likes / save_likes → `likes.json`
  - `_hints.py` — `HintsStorage`：load_shown_hints / save_shown_hints → `hints.json`
  - `_library.py` — `LibraryStorage`：load/save_library + copy/remove_library_image → `library.json` + `library_images/`
  - `_history.py` — `HistoryStorage`：load/save/append/clear_history → `history.json`（上限 500 条）
  - `_fonts.py` — `FontStorage`：import_font / list_imported_fonts / font_file_path / load_imported_fonts → `fonts/index.json`
  - `_examples.py` — `ExampleStorage`：copy/save/remove_example_image + serialize/deserialize → `examples/`
  - `_prompts.py` — `PromptStorage`：export/import_prompts（无状态，纯 JSON IO）
  - `_config_bundle.py` — `ConfigBundleStorage`：export/import_config_bundle + merge_settings + state_from_bundle（跨域协调器，注入 FontStorage + ExampleStorage）
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
- `build_messages()`：把提示词 + 例图 + 用户输入组装成 API messages 数组
- depth=0 的条目放前面，depth>0 的条目从末尾往前插入
- `normalize_api_base_url()`：清理 API URL
- `extract_active_input()`：记忆模式取全部，非记忆模式取最后一段
- `validate_examples()`：校验例图必须同时有描述和标签
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

## i18n.py
- `Translator` 类：加载 resources/lang/*.json 翻译文件
- `t(key)` 方法返回翻译后的字符串，找不到则返回 key 本身
- 支持运行时切换语言
- available_languages() 列出可用语言

## font_loader.py
- `load_app_fonts()`：从 resources/fonts/ 加载内嵌字体
- `build_body_font()`：根据 font_profile 和 point_size 构建 QFont
- `create_app_font()`：创建应用级字体

## tag_dictionary.py
- **TagDictionary 类**：通用 Danbooru TAG 词典加载器
- `load_csv(path)`：加载 CSV 词典（UTF-8 BOM），支持多次调用合并来源
- `translate(tag) → str | None`：查中文翻译（O(1) dict 查询）
- `lookup(tag) → TagInfo | None`：查完整信息（翻译、分类号、使用次数、别名、大类、子类）
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

## error_reporting.py
- `report_error()`：生成错误报告文件 + 弹窗显示
- `format_exception_details()`：格式化异常堆栈
- `runtime_mode()`：检测是 dist 还是 source 运行模式

## resources/
- `resources/lang/zh-CN.json`：中文翻译（所有 UI 字符串）
- `resources/lang/en.json`：英文翻译
- `resources/fonts/`：内嵌字体文件
