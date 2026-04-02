# native_app/widgets/ 文件说明

> UI 组件目录。每个文件是一个独立的 Qt 组件，负责特定的界面功能。

## dock.py
- **DockItemButton**：dock 栏中的单个项目按钮
  - 左键点击 → activated 信号（恢复卡片到工作区）
  - 左键拖出 → dragged_out 信号（拖拽恢复到指定位置）
  - 右键菜单 → close_requested 信号（删除该例图）
  - `refresh_text(expanded, floating)`：收缩时只显示图标，展开时显示图标+标签
  - `set_close_label(label)`：设置右键菜单"关闭"的翻译文本
- **DockPanel**：收缩栏框架
  - 支持四个停靠位置（LEFT/RIGHT/TOP/BOTTOM）+ 浮动
  - 展开/收缩切换（toggle_expanded）
  - edge handle 拖拽调整宽度/高度
  - 浮动模式下四边+四角 resize
  - `set_items()`：设置 dock 项列表
  - `set_close_label()`：设置所有项的右键关闭文本
  - resizeEvent 中调用 `_refresh_layout_direction()` 防止窗口缩放后布局错乱
  - 信号：state_changed、widget_activated、widget_drag_restored、widget_close_requested

## workspace.py
- **Workspace**：卡片工作区容器
  - `add_card()` / `remove_card()`：管理卡片注册
  - `all_cards()` / `visible_cards()`：查询卡片
  - `find_free_position()`：找空闲位置放新卡片
  - `resolve_overlap()`：解决卡片重叠
  - `clamp_card()`：确保卡片不超出工作区
  - `hide_card()` / `restore_card()`：隐藏/恢复卡片
  - `widget_states()`：收集所有卡片的位置/可见状态
  - `is_card_resize_hotspot_at()`：检测全局坐标是否在卡片 resize 热区

## widget_card.py
- **WidgetCard**：可拖拽/缩放的卡片容器壳
  - widget_id 唯一标识
  - grip 拖拽（标题区域拖动移动卡片）
  - grip 右键菜单 → 收回工作区（浮动时）/ 收纳到 dock
  - 四角 + 四边 resize handle
  - `set_content(widget)`：嵌入内容 widget
  - `retranslate_ui()`：更新 grip/resize 的 tooltip
  - min_size 约束最小尺寸
  - **标题 label**：`set_title(text)` 设置卡片名称，显示在 grip 和按钮之间，`WA_TransparentForMouseEvents` 不阻拦拖拽
  - **× 收纳按钮**：`_close_action()` 直接收纳到 dock，浮动时先收回再收纳
  - **📌 置顶按钮**：`_toggle_pin()` → `_update_pin_style()` 统一管理样式，颜色从 `current_palette()` 取 `accent_text`/`text_dim`
  - **apply_theme()**：切主题时刷新标题颜色和 pin/close 按钮样式
  - **浮动窗口**：`float_out(global_pos)` 脱离工作区变独立 Tool 窗口，`float_back(parent)` 收回
  - 拖拽超出工作区边界自动 float_out
  - 信号：geometry_edited、interaction_finished、close_requested、floated、unfloated

## settings_panel.py
- **SettingsPanel**：设置面板（从 content_host 右侧滑出的覆盖层，不再是独立侧车）
  - 语言选择（QComboBox）
  - API 配置：base URL、API Key（带显隐切换）、模型（可编辑 QComboBox + ↻ 获取模型按钮）
  - 模型参数滑块：Temperature、Top P（所有滑块禁用鼠标滚轮防误触）
  - 数值输入：Top K（QSpinBox，-1=不启用显示'--'）、频率惩罚、存在惩罚、最大 Tokens
  - 开关：流式输出、记忆模式
  - 总结提示词（QTextEdit）
  - 导出/导入按钮（点击弹出 QDialog 勾选页面：当前设置页/整套 Profile/提示词）
  - `settings()`：收集当前设置为 AppSettings 对象
  - `apply_settings()`：从 AppSettings 恢复 UI 状态
  - 信号：settings_changed、language_changed、fetch_models_requested、config_export/import_requested、export/import_prompts_requested

## prompt_manager.py
- **PromptEntryWidget**：单条提示词的 UI
  - header 区域：顺序 spin(58px)、拖拽手柄≡、启用开关、名称（点击编辑/预览切换）、角色 combo（系统/用户/助手）、深度标签、深度 spin(58px)、展开指示器、删除按钮×
  - body 区域：内容 QTextEdit（可展开/折叠，带动画）
  - `entry()` → PromptEntry、`set_entry()` ← PromptEntry
- **PromptManagerWidget**：提示词列表管理器
  - QListWidget 显示所有提示词条目
  - 拖拽排序（DragDrop）
  - 添加/删除提示词
  - `prompt_entries()` → list[PromptEntry]
  - `set_prompt_entries()` ← list[PromptEntry]

## input_widget.py
- **InputWidget**：用户输入区（纯输入，发送后清空）
  - QTextEdit 编辑器（用户在这里写画面描述）
  - action bar：token 计数标签、Σ 总结按钮、➤ 发送按钮（发送中变 ■ 停止）
  - `text()` / `set_text()` / `clear_text()`：文本操作
  - `set_sending(bool)`：切换发送/停止状态
  - `set_token_estimate()`：更新 token 计数显示（正常状态回退 QSS text_muted，warning/critical 通过 `is_theme_light()` 适配暗/亮主题色）
  - 发送后由 window.py 清空输入框，AI 响应路由到 OutputWidget

## output_widget.py
- **TagTextEdit**：TAG 专用文本编辑器（继承 QTextEdit）
  - 按逗号解析 TAG 文本，记录每个 tag 的字符起止位置
  - hover：鼠标移到 tag 上 → 高亮背景（通过 `is_theme_light()` 适配暗/亮主题色） + 发出 tag_hovered 信号 + tooltip
  - 右键拖拽权重编辑（scrub 模式）：右键按住 tag → 左右拖动 → 实时更新权重值 → 纯 tag 自动包裹 `(tag:1.05)`，权重回到 1.0 自动去括号
  - 屏蔽 tag 上的右键菜单（右键用于 scrub）
- **OutputWidget**：TAG 工作台
  - QTabWidget 两个 tab：「完整 TAG」+「无角色 TAG」
  - 每个 tab 包含 TagTextEdit（可编辑）+ 复制按钮
  - `set_full_tags()` / `set_nochar_tags()`：设置 TAG 文本
  - `append_full_text()`：流式追加文本（ChatWorker delta 用）
  - `clear_output()`：清空两个 tab

## example_widget.py
- **ExampleWidget**：例图卡片内容
  - 图片选择按钮（点击选文件，支持 jpg/png/webp）
  - 标签输入 QTextEdit（`1girl, blue_hair, ...`）
  - 描述输入 QTextEdit
  - 顺序 QSpinBox（0-9999）
  - 深度 QSpinBox（0-999）
  - 删除按钮 ×（触发 delete_requested 信号）
  - `entry()` → ExampleEntry
  - 信号：changed、delete_requested、error_occurred

## collapsible_section.py
- **CollapsibleSection**：通用折叠/展开区域组件
  - 可点击标题栏（▼/▶ 箭头 + 标题文字）+ 内容 widget
  - `collapsed` 参数控制初始状态
  - `right_widget` 可选右侧附加组件（如复制按钮）
  - 标题颜色使用 palette `accent_text`，跟随主题
  - 信号：`toggled(bool)`

## metadata_viewer.py
- **MetadataViewerWidget**：Metadata 查看器卡片（单实例）
  - 两种状态：空白（全区域拖放/点击判定区，虚线框 + 居中提示）→ 内容（缩略图 + 解析后的 metadata 分区显示）
  - 支持拖入图片和文件选择器
  - 使用 `CollapsibleSection` 展示各区域：正面提示词、负面提示词、参数、LoRA（展开）、Workflow、Raw Chunks（折叠）
  - QTextEdit 用 QSS class `MetadataText`（跟随主题）
  - ✕ 按钮回到空白状态
  - 纯只读，编辑功能在销毁器

## metadata_destroyer.py
- **MetadataDestroyerWidget**：Metadata 销毁/编辑器卡片（单实例）
  - 三种状态：空白（全区域拖放/点击判定区）→ 单图（`_DraggableImageLabel` 显示销毁后图片，可拖出，右键另存为/复制/切换编辑模式）→ 批量（结果列表，每行有复制/另存为按钮）
  - `_DraggableImageLabel`：支持像浏览器一样拖出图片到其他应用
  - 编辑模式：右键切换 → 显示可编辑的 prompt 字段 + 另存为副本按钮
  - 销毁使用 `MetadataWriter.destroy()`，编辑使用 `MetadataWriter.edit()`

## common.py
- **ToggleSwitch**：自定义开关控件（圆形滑块样式），通过 `is_theme_light()` 自动适配暗/亮主题颜色
- **DragHandleLabel**：≡ 拖拽手柄（用于提示词排序）
- **compute_resized_rect()**：通用的矩形 resize 计算函数（处理各个方向的拖拽缩放）

## tag_completer.py
- **TagCompleterPopup**：TAG 自动补全弹窗（ToolTip 类型，不抢焦点）
  - 从 `TagDictionary` 查询匹配项，显示 tag 名 + 中文翻译 + 使用次数
  - 150ms 防抖输入，接受后 0.3s 抑制重触发
  - `sip.isdeleted()` 检查避免定时器访问已销毁 QTextEdit
- **install_completer(text_edit, dictionary)**：一行安装补全到任意 QTextEdit

## image_manager.py（~1450 行）
- **独立无边框窗口**（`FramelessWindowHint + WA_TranslucentBackground`），从主窗口菜单/dock 打开
- 设计语言：极简、呼吸感、线条驱动、克制

### ThumbnailModel（QAbstractListModel）
- 持有文件路径列表（目录 + 图片分开存储），不存像素数据
- `set_folder_contents(dirs, images, buffer_size)` → 设置当前文件夹内容（目录在前、图片在后）
- `set_source(paths, buffer_size)` → 直接设路径列表（过滤模式用）
- `canFetchMore()` / `fetchMore()` → 批量加载，每批 `buffer_size`（默认 50）
- `set_sort(key)` → 排序（newest/oldest/largest/smallest），对 `_all` 和已加载数据同时排序
- `path_at(index)` / `is_dir(index)` → 查询单项
- `mimeData()` → 返回 `QUrl.fromLocalFile`，支持拖出到外部应用
- 自定义 role：`_ROLE_IS_DIR = Qt.ItemDataRole.UserRole + 1`

### ThumbnailDelegate（QStyledItemDelegate）
- 自定义绘制：文件夹图标（手绘几何）、图片缩略图、文件名、❤ 喜欢角标
- `set_thumb_size(s, sizing)` → 更新尺寸，sizing=True 时 paint 不排队新请求（防止滑块拖动时 CPU 飙升）
- `set_likes(likes)` → 传入喜欢集合
- `set_cut(cut)` → 传入剪切集合，剪切的文件缩略图 opacity=0.35 变暗
- 缓存 miss 时用 `get_any()` 快速缩放已有缓存作为过渡

### LightboxOverlay（QWidget）
- 全屏遮罩层，`background: rgba(0,0,0,200)`
- 居中大图 + 底部文件名/尺寸
- ← → 导航（键盘 + 鼠标点击左右区域）、Esc 关闭
- 信号：`closed`

### DetailPanel（QWidget）
- **浮动 Tool 窗口**（`Qt.WindowType.Tool | WA_ShowWithoutActivating`），不抢焦点
- 可拖拽标题栏 + 置顶按钮（pin）
- `show_at(pos)` → 在指定位置显示，`_clamp_to_screen()` 确保不超出屏幕
- `show_image(path)` → 异步读取 metadata 并填充内容
- `show_metadata(meta, file_info)` → 直接传入已解析的 metadata
- `hide()` → 带 150ms 淡出动画（`QPropertyAnimation windowOpacity`）
- `set_pinned(v)` / `is_pinned` → 置顶控制
- 内容：预览图 + 文件信息 + CollapsibleSection × N（Prompt/Negative/Parameters/LoRA/Workflow）
- 底部按钮：复制提示词、发送到输入框、用作例图、复制 LoRA
- 信号：`send_to_input(str)`、`use_as_example(str)`

### ImageManagerWindow（QWidget）
- 无边框窗口，自定义标题栏（拖拽移动、四边+四角 resize、10px 边缘检测）
- `_toggle_pin()` → 置顶切换（`setWindowFlag` + 保存/恢复 geometry + 重新启用 mouseTracking）
- **文件夹导航**：前进/后退/上级历史栈（`_nav_history` / `_nav_future`），鼠标侧键（通过 `viewport().installEventFilter()`），Alt+←/→/↑ 键盘快捷键
- **路径显示**：日期文件夹名 + 完整路径标签（可点击弹出文件选择器）
- **工具栏**：缓冲区大小 SpinBox、缩略图大小 Slider（拖动时 sizing 模式不加载新缩略图）、排序下拉、子文件夹递归开关、只看喜欢开关
- **自动加载**：滚动到 70% 时自动 `fetchMore()`
- `apply_theme()` → 重新应用 QSS，使用 `current_palette()` 与主窗口同步
- `load_initial_folder()` → 启动时加载上次文件夹
- **喜欢持久化**：启动时从 `storage.load_likes()` 加载，toggle 时自动 `storage.save_likes()`
- **文件操作**：
  - 右键"移动到..."子菜单 → 列当前子文件夹 + "新建文件夹"，点击即移动
  - 新建文件夹（右键空白处 / 移动子菜单底部）
  - F2 重命名（QInputDialog）
  - Delete 删除到回收站（ctypes `SHFileOperationW` + `FOF_ALLOWUNDO`）
  - Ctrl+X 剪切 + Ctrl+V 粘贴（内部剪贴板，缩略图变暗提示）
  - Ctrl+C 复制文件到系统剪贴板（`QMimeData` + `QUrl`）
  - 移动/重命名时自动更新 likes 路径
- **右键菜单**：有选中 → 查看大图/复制/剪切/复制提示词/移动到.../重命名/删除/发送输入框/用作例图/喜欢/打开位置/销毁metadata；无选中 → 新建文件夹/粘贴
- 信号：`action_requested(str, list)`、`send_to_input(str)`、`use_as_example(str)`、`folder_changed(str)`

### 通用接口设计
```python
# 缩略图模型 — 可换数据源
ThumbnailModel.set_source(paths, buffer_size)
ThumbnailModel.set_folder_contents(dirs, images, buffer_size)

# 缩略图缓存 — 可独立复用
ThumbCache.get(path, size) → QPixmap | None
ThumbCache.request(path, size, callback)
ThumbCache.cancel_pending()

# 详情面板 — 可独立使用
DetailPanel.show_metadata(meta: ImageMetadata, file_info: dict)
DetailPanel.show_image(path: str)
DetailPanel.show_at(pos: QPoint)

# Lightbox — 可独立使用
LightboxOverlay.show_image(path, paths_list, current_index)

# 信号驱动 — 不在组件内执行实际操作
ImageManagerWindow.send_to_input = pyqtSignal(str)
ImageManagerWindow.use_as_example = pyqtSignal(str)
ImageManagerWindow.folder_changed = pyqtSignal(str)
```

## 信号链路

### 发送流程
```
用户点击 ➤ → window._handle_send_action()
  → 校验 → build_messages() → output_widget.clear_output()
  → input_widget.clear_text() → _start_worker()
  → ChatWorker.delta_received → window._on_worker_delta()
  → output_widget.append_full_text()
```

### Dock 项操作
```
DockItemButton.activated → DockPanel.widget_activated → window._restore_card()
DockItemButton.close_requested → DockPanel.widget_close_requested → window._close_dock_item()
DockItemButton.dragged_out → DockPanel.widget_drag_restored → window._restore_card(pos)
```

### 卡片生命周期
```
window._add_example_card() → _create_example_card() → workspace.add_card()
ExampleWidget.delete_requested → window._delete_example_card() → workspace.remove_card()
WidgetCard dock 按钮 → window._dock_card() → workspace.hide_card() → _refresh_dock_items()
```

### 图像管理器
```
主窗口菜单/dock → window._open_image_manager() → ImageManagerWindow.show()
缩略图点击 → _on_click() → DetailPanel.show_at(cursor_pos) + show_image(path)
缩略图双击 → LightboxOverlay.show_image(path, paths, idx)
右键复制提示词 → MetadataReader.read_metadata() → clipboard
右键发送到输入框 → ImageManagerWindow.send_to_input → window._on_im_send_to_input()
右键用作例图 → ImageManagerWindow.use_as_example → window._on_im_use_as_example()
文件夹切换 → ImageManagerWindow.folder_changed → window 保存到 settings
ThumbCache.request() → ThumbLoaderThread → thumbnail_ready → delegate repaint
```

## library_panel.py
- **LibraryPanel**：画师库 + OC 库两步抽屉面板
  - 两步交互：半圆按钮 → 窄条（选择画师/OC 库）→ 展开内容，带宽度动画 + 淡入
  - 常量：`SECTION_ARTIST`、`SECTION_OC` — 区块标识
  - 样式公共函数（DRY）：`_input_style()`、`_del_btn_style()`、`_arrow_style()`、`_header_style()`、`_dim_label_style()`
- **ArtistBanner**：画师条目卡片（展开/收起）
  - 参考图网格（`_RefImageGrid` 纵向）+ 名称 + LoRA/触发词 + Copy 按钮
- **OCBanner**：OC 角色条目卡片（展开/收起）
  - Order/Depth spin、角色名、Tags、参考图网格、服装列表
  - ToggleSwitch 启用/禁用
- **_OutfitRow**：服装条目行（toggle + 名称 + tags + 删除）
- **_RefImageGrid**：参考图网格（支持纵向/横向布局，添加/删除图片）

## hint_manager.py
- **HintBubble**：浮动提示气泡（ToolTip 窗口类型，不抢焦点）
  - 淡入动画 200ms，8 秒自动消失或点击关闭
  - `show_near(widget, position)` — 在目标 widget 附近定位，屏幕边界 clamp
- **HintManager**：首次使用提示管理器
  - `register(widget, hint_id, text_key, position, delay_ms)` — 注册提示，首次自动显示
  - `show_hint(widget, hint_id, text_key)` — 强制显示（不管已看过）
  - `reset_hints()` — 清空记录，所有提示重新显示
  - 持久化到 `hints.json`（已显示 hint_id 集合）
  - `sip.isdeleted()` 防止访问已销毁 widget

## shortcuts_panel.py
- **ShortcutsPanel**：快捷键速查弹窗（Popup 窗口，点击外部关闭）
  - 6 个区块：全局 / 图像管理器 / Lightbox / TAG 补全 / 输出编辑器 / 卡片操作
  - 每行：monospace 风格快捷键 badge + 描述文本
  - 触发：F1 / Ctrl+/ / 标题栏 ? 按钮 / 工作区右键菜单
  - `show_at(global_pos)` — 屏幕中心定位

## history_panel.py
- **HistoryPanel**：生成历史浏览卡片
  - QScrollArea 滚动列表，newest first
  - 每条 _HistoryItem：时间戳 + 模型标签 + 输入预览 + 输出预览（截断 80 字符）
  - 左键点击 → `entry_selected(output_text)` 填充到输出卡片
  - 右键菜单：复制输出 / 复制输入 / 填充输出
  - hover 高亮（`hover_bg`）
  - 清空按钮 → 确认弹窗 → `storage.clear_history()`
  - `add_entry(entry)` — 添加新条目并持久化
  - `set_entries(entries)` — 批量加载（启动时）
  - 信号：`entry_selected(str)`、`changed()`
- **历史捕获流程**：
  - `_handle_send_action()` 保存 `_pending_history_input` + `_pending_history_model`
  - `_on_worker_finished()` 读取输出文本 → 创建 HistoryEntry → `add_entry()`

## prompt_preview.py
- **PromptPreviewPopup**：最终 Prompt 预览弹窗（Popup 窗口）
  - 每条消息一个区块：角色标签（SYSTEM/USER/ASSISTANT 带颜色）+ token 数 + 内容
  - 顶部总 token 计数
  - `set_messages(messages, title)` — 填充消息列表
  - `show_at(global_pos)` — 屏幕 clamp 定位
