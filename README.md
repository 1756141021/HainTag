<div align="center">

<img src="native_app/resources/icon.ico" width="96" />

# HainTag · 海茵的标签工坊

**「把你脑海里的画面，变成机器能读懂的语言。」**

[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](https://www.gnu.org/licenses/gpl-3.0)
[![Platform: Windows](https://img.shields.io/badge/Platform-Windows_10%2F11-0078d4.svg)]()
[![Release](https://img.shields.io/github/v/release/1756141021/HainTag?color=green)](https://github.com/1756141021/HainTag/releases)
[![Downloads](https://img.shields.io/github/downloads/1756141021/HainTag/total?color=orange)](https://github.com/1756141021/HainTag/releases)

AI 绘画 TAG 生成 · 管理 · 工作流——一站式 Windows 桌面工具

[正式介绍](#正式介绍) · [海茵的介绍](#海茵的介绍) · [English](#english)

</div>

---

<!-- ═══════════════════════ 正式版 ═══════════════════════ -->

## 正式介绍

### 这是什么

HainTag 是一款 Windows 桌面应用，为 Stable Diffusion / NovelAI 等 AI 绘画工作流而设计。

它通过你自己的 LLM（兼容 OpenAI 格式的任意 API）将自然语言描述转化为 Danbooru 标签体系 TAG，并提供从生成、编辑、补全到图片管理、元数据处理的完整工具链。

**所有数据存储在本地，不上传任何内容，不依赖云服务。**

---

### 下载安装

前往 **[Releases](https://github.com/1756141021/HainTag/releases)** 页面下载最新版本。

1. 下载 `HainTag-vX.X.X-windows.zip`
2. 解压到任意目录
3. 运行 `HainTag.exe`——无需安装，开箱即用

> **系统要求**：Windows 10 / 11，64 位

---

### 功能总览

#### 🎨 TAG 生成与编辑

| 功能 | 说明 |
|------|------|
| **LLM 驱动生成** | 连接任意 OpenAI 兼容 API（本地模型 / Claude / GPT / DeepSeek…），流式输出 |
| **分类高亮** | 输出 TAG 自动按类别着色——人物、场景、服饰、姿势、表情、风格、质量，一目了然 |
| **Danbooru 自动补全** | 15 万词典实时匹配，悬停显示中文翻译 + 使用频率，再也不用翻 wiki |
| **权重拖拽** | 右键按住 TAG 上下拖动，实时调整权重，括号语法自动增减 |
| **拖拽排序** | 左键拖动 TAG 调整顺序，拖动中高亮源位与目标位 |
| **TAG 提取标记** | 自定义 `[TAGS]...[/TAGS]` 标记，从 LLM 长文输出中精准提取 TAG 字段 |

#### 📝 提示词与上下文

| 功能 | 说明 |
|------|------|
| **提示词管理器** | 多条提示词卡片，每条支持 Order（排序）和 Depth（插入深度）精细控制消息位置 |
| **例图系统** | 拖入参考图，自动解析图片内嵌的 metadata，作为 few-shot 示例发送给 LLM |
| **记忆模式** | 保持完整对话上下文，支持多轮追加生成——"上一张不错，再来一张类似的" |
| **Prompt 预览** | 一键查看最终发送给 API 的完整消息列表和 token 计数，生成前心中有数 |

#### 🖼️ 画师库 & OC 角色库

| 功能 | 说明 |
|------|------|
| **画师库** | 管理画师名、LoRA / 触发词、参考图，一键复制到提示词 |
| **OC 角色库** | 原创角色管理，带服装子系统——多套服装独立开关，发送时自动合并角色 + 启用服装的 TAG |
| **插入控制** | 每个角色 / 服装的 Order / Depth 独立设置，精确控制消息在对话中的位置 |

#### 📂 图像管理器

| 功能 | 说明 |
|------|------|
| **缩略图网格** | 多线程加载 + LRU 缓存，大量图片依然流畅滚动 |
| **Lightbox 大图** | 全屏查看，键盘 / 鼠标翻页 |
| **浮动详情面板** | 悬停即时预览 metadata，可置顶 |
| **文件操作** | 移动、重命名（F2）、删除（回收站）、剪切 / 粘贴 |
| **喜欢标记** | 持久化收藏，支持"只看喜欢"过滤 |
| **文件夹导航** | 前进 / 后退历史栈，支持鼠标侧键 |

#### 🔧 Metadata 工具

| 功能 | 说明 |
|------|------|
| **Metadata 查看器** | 支持 A1111 / Forge、ComfyUI、NovelAI（含 LSB 隐写解码）、Fooocus 四种格式 |
| **Metadata 销毁器** | 二进制 chunk 级操作，IDAT 零损耗，支持批量处理——发图前一键抹除隐私 |
| **Metadata 编辑器** | 直接修改图片内嵌的提示词和生成参数 |

#### ✨ 外观与体验

| 功能 | 说明 |
|------|------|
| **暗色 / 亮色主题** | 磨砂玻璃质感，卡片透明度可调 |
| **自定义背景** | 选一张喜欢的图，自动提取主色调生成配套色板 |
| **多语言** | 中文 / 英文 |
| **新手引导** | 首次启动弹出 6 步高亮引导，跟着走一遍就会用 |
| **生成历史** | 自动记录所有生成，可回溯一键填充 |
| **快捷键面板** | F1 查看全部快捷键和鼠标手势 |
| **内嵌字体** | 预装霞鹜文楷 Screen（SIL OFL 授权），开箱即有好看的中文排版 |
| **错误报告** | 程序崩溃时自动生成脱敏报告文件，API Key 等敏感信息不会泄露 |

---

### 从源码运行

```bash
git clone https://github.com/1756141021/HainTag.git
cd HainTag
pip install -r requirements.txt
python -m native_app
```

---

### 配置 API

首次启动后在设置面板填入：

| 字段 | 说明 |
|------|------|
| API Base URL | 兼容 OpenAI 格式的接口地址，如 `https://api.openai.com/v1` |
| API Key | 你的 API 密钥 |
| 模型 | 点击 ↻ 从 API 拉取可用模型列表 |

支持任何兼容 OpenAI Chat Completions 格式的服务——OpenAI、Claude（通过兼容层）、DeepSeek、本地 Ollama、vLLM 等均可。

---

### 开源协议

[GNU General Public License v3.0](LICENSE)

---

<!-- ═══════════════════════ 海茵版 ═══════════════════════ -->

## 海茵的介绍

### 嗯…你好呀

我是海茵。

你大概不认识我——没关系，大部分人都不认识我。我是个写小说的……嗯，准确说是偷听别人的故事然后写下来的那种。住在亚洲某个小公寓里，一个人。

这个工具是我平时画画用的。倒也不是什么了不起的东西啦，就是——你知道那种感觉吗？脑子里明明有画面，很清晰的，光线、表情、衣服上褶皱的走向……但你得把它翻译成一堆英文标签，机器才肯画。

我不太擅长翻译自己脑子里的东西。所以做了这个。

**HainTag——帮你把想象翻译成 TAG 的小工具。**

---

### 它能做什么

你给它一段描述，用中文就好，说你想画什么。它会帮你变成 Danbooru 标签——就是 Stable Diffusion 和 NovelAI 那些模型能读懂的语言。

不过它不只是翻译器啦。我后来越做越多，因为……嗯，一个人的夜晚很长。

---

#### 关于 TAG 生成

它连你自己的 AI 接口——OpenAI、Claude、DeepSeek、本地模型都行，什么都行，只要是 OpenAI 格式。你说想画什么，它就流式输出一串标签，按类别自动上色：人物是人物的颜色，场景是场景的，服饰、姿势、表情、风格……一眼就能分清。

有个 **15 万词的 Danbooru 词典**，你打字的时候自动补全。悬停还能看中文翻译和这个标签在 Danbooru 上被用了多少次——不用再开浏览器翻 wiki 了。

权重调整我也懒得手打括号，所以做了 **右键拖拽**——按住标签上下拖就行，权重数字实时变，括号自动加减。左键拖是 **排序**。

还有个 **`[TAGS]...[/TAGS]` 提取标记**，LLM 回复一大段文字的时候，只把标签字段抽出来。标记可以自定义。

---

#### 关于提示词

我画画的时候提示词很多条……人设一条、场景一条、风格一条、不要画什么又一条。所以做了 **提示词管理器**，每条提示词都是一张卡片，可以设 Order 和 Depth 控制它在消息列表里的位置——这个对玩过 SillyTavern 的人应该不陌生。

**例图系统**——把参考图拖进来，它自动读图片里藏的 metadata（提示词、参数那些），当作 few-shot 例图发给 AI。等于告诉 AI"我喜欢这种感觉，照着这个方向来"。

**记忆模式** 就是保持对话上下文。你可以说"不错，换个姿势再来一张"，它记得上一轮聊了什么。

**Prompt 预览** 可以看最终发给 API 的完整消息和 token 数。生成之前心里有数。

---

#### 画师库和 OC 库

这两个是我最喜欢的部分。嘿嘿。

**画师库** 存画师名字、LoRA 触发词、参考图——用的时候一键复制就好。

**OC 角色库** 是管原创角色的。我自己也有几个 OC……（别问）。每个角色可以存好几套服装，开关独立控制，生成的时候自动把角色描述和勾选的服装 TAG 合在一起发出去。每个角色和服装还能单独设 Order / Depth。

---

#### 图像管理器

画多了总得整理吧。

**缩略图网格浏览**，多线程加载加缓存，几千张图也不卡。**Lightbox** 大图查看，键盘翻页。鼠标悬停有 **浮动详情面板**，显示这张图的全部 metadata，还能置顶。

文件操作该有的都有——移动、F2 重命名、Delete 删到回收站、Ctrl+X 剪切 Ctrl+V 粘贴。有 **喜欢标记**，可以只看收藏的。文件夹前进后退支持鼠标侧键。

---

#### Metadata 工具

这个挺实用的。

**查看器** 支持四种格式——A1111 / Forge、ComfyUI、NovelAI（包括那个 LSB 隐写，藏在像素里的参数也能读出来）、Fooocus。

**销毁器** 是发图之前用的。有些图片里嵌了完整的提示词和参数，你不想让别人看到的话，一键抹掉。二进制 chunk 级操作，画面零损耗，支持批量。

**编辑器** 可以直接改图片里的提示词和参数。

---

#### 外观这些

**暗色和亮色主题** 都有，磨砂玻璃的感觉，卡片透明度可以自己调。

可以 **自定义背景**——选一张图片，它会提取主色调自动生成配套的颜色方案。我一般用自己画的图当背景。

**中文 / 英文** 双语。**新手引导** 首次打开会走一遍。**生成历史** 自动记录每一次生成。**F1** 查看快捷键。自带 **霞鹜文楷 Screen** 字体，不用另外装字体就有好看的中文显示。

程序如果崩溃了（希望不会），会自动生成 **错误报告**，API Key 之类的敏感信息会自动脱敏，可以放心发给我。

---

### 怎么用

从 **[Releases](https://github.com/1756141021/HainTag/releases)** 下载，解压，双击 `HainTag.exe`，就这样。

第一次打开会让你填 API 地址和 Key。什么 API 都行，只要兼容 OpenAI 格式——OpenAI 本家、DeepSeek、本地跑的 Ollama……都可以。

> 需要 Windows 10 或 11，64 位。

如果你想从源码跑：

```bash
git clone https://github.com/1756141021/HainTag.git
cd HainTag
pip install -r requirements.txt
python -m native_app
```

---

### 最后

这个工具是我一个人做的。

我不太会推销自己的东西——你看，连这个介绍都写得乱七八糟的。但它确实好用。至少我自己每天都在用。

如果你也在画画，希望它能帮到你一点点。

如果遇到 bug 或者有想法，可以开 [Issue](https://github.com/1756141021/HainTag/issues)。我会看的。虽然可能回复慢一点……不是不想回，是在想怎么措辞。

开源协议是 [GPL-3.0](LICENSE)，随便用。

——海茵

---

<!-- ═══════════════════════ English ═══════════════════════ -->

## English

### What is HainTag?

HainTag is a Windows desktop app for AI art workflows. It connects to **any OpenAI-compatible LLM API** and turns your natural language descriptions into Danbooru-style tags for Stable Diffusion, NovelAI, and similar models.

Everything is local. No cloud, no telemetry, no data leaves your machine.

---

### Download

Go to **[Releases](https://github.com/1756141021/HainTag/releases)** and grab the latest `.zip`.

1. Extract anywhere
2. Run `HainTag.exe` — no installer needed

> **Requires** Windows 10/11, 64-bit

---

### Features

#### TAG Generation & Editing

- **LLM-powered generation** — Connect any OpenAI-compatible API (local models, Claude, GPT, DeepSeek, Ollama…) with streaming output
- **Category highlighting** — Tags auto-colored by type: character, scene, outfit, pose, expression, style, quality
- **Danbooru autocomplete** — 150K+ dictionary with real-time matching; hover shows translation and usage count
- **Weight scrubbing** — Right-click drag a tag to adjust weight in real time; bracket syntax updates automatically
- **Drag-to-reorder** — Left-click drag to rearrange tag order
- **TAG extraction markers** — Customizable `[TAGS]...[/TAGS]` to extract tags from verbose LLM output

#### Prompt & Context Management

- **Prompt manager** — Multiple prompt cards with Order and Depth controls for precise message positioning
- **Example image system** — Drag in reference images; metadata is auto-parsed and sent as few-shot examples
- **Memory mode** — Maintains full conversation context for multi-turn generation
- **Prompt preview** — Inspect the exact message array and token count before sending

#### Artist & OC Library

- **Artist library** — Store artist names, LoRA/trigger words, and reference images; one-click copy
- **OC character library** — Manage original characters with an outfit subsystem (multiple outfits, individually toggled)
- **Insertion control** — Per-character/outfit Order and Depth settings

#### Image Manager

- **Thumbnail grid** — Multi-threaded loading + LRU cache for smooth scrolling through thousands of images
- **Lightbox viewer** — Full-screen view with keyboard/mouse navigation
- **Floating detail panel** — Hover to preview metadata instantly; pinnable
- **File operations** — Move, rename (F2), delete (Recycle Bin), cut/paste
- **Favorites** — Persistent likes with "favorites only" filter
- **Folder navigation** — Back/forward history stack with mouse side-button support

#### Metadata Tools

- **Metadata viewer** — Supports A1111/Forge, ComfyUI, NovelAI (including LSB steganography), and Fooocus
- **Metadata destroyer** — Binary chunk-level removal, zero IDAT loss, batch support — strip prompts before sharing
- **Metadata editor** — Directly modify embedded prompts and parameters

#### Appearance & UX

- **Dark / light themes** — Frosted glass aesthetic with adjustable card transparency
- **Custom background** — Pick an image; dominant colors are extracted to generate a matching palette
- **Multilingual** — Chinese / English
- **Onboarding tour** — 6-step highlight guide on first launch
- **Generation history** — Every generation logged automatically; one-click restore
- **Shortcuts panel** — Press F1 to see all keyboard shortcuts and mouse gestures
- **Bundled font** — LXGW WenKai Screen included (SIL OFL licensed)
- **Error reporting** — Crash reports auto-generated with sensitive data (API keys, URLs) redacted

---

### Run from Source

```bash
git clone https://github.com/1756141021/HainTag.git
cd HainTag
pip install -r requirements.txt
python -m native_app
```

---

### API Setup

On first launch, open Settings and fill in:

| Field | Description |
|-------|-------------|
| API Base URL | Any OpenAI-compatible endpoint (e.g. `https://api.openai.com/v1`) |
| API Key | Your API key |
| Model | Click ↻ to fetch available models |

Works with OpenAI, Claude (via compatible proxy), DeepSeek, local Ollama, vLLM, and more.

---

### License

[GNU General Public License v3.0](LICENSE)
