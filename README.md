<div align="center">

# HainTag · 海茵的标签工坊

**AI 绘画 TAG 生成器 · AI Drawing Tag Generator**

[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](https://www.gnu.org/licenses/gpl-3.0)
[![Platform: Windows](https://img.shields.io/badge/Platform-Windows-lightgrey.svg)]()
[![Version](https://img.shields.io/badge/Version-0.5.2-green.svg)]()

[简体中文](#简体中文) · [English](#english)

</div>

---

## 简体中文

### 简介

HainTag 是一款 Windows 桌面应用，专为 AI 绘画工作流设计。它连接你自己的 LLM API（兼容 OpenAI 格式），帮助你生成、编辑和管理 Stable Diffusion / NovelAI 等模型所需的 Danbooru 标签体系 TAG。

所有数据存储在本地，不依赖任何云服务。

---

### 功能一览

#### TAG 生成与编辑
- **LLM 驱动生成** — 连接任意 OpenAI 兼容 API（本地模型、Claude、GPT 等），流式输出
- **分类高亮** — 输出 TAG 自动按类别着色（人物/场景/服饰/姿势/表情/风格/质量）
- **Danbooru 自动补全** — 15 万词典实时匹配，hover 显示中文翻译 + 使用频率
- **权重拖拽编辑** — 右键拖动 TAG 实时调整权重，自动添加/移除括号语法
- **TAG 拖拽排序** — 左键拖动重新排列 TAG 顺序
- **TAG 提取标记** — 自定义 `[TAGS]...[/TAGS]` 标记，自动从 LLM 输出中提取 TAG 字段

#### 提示词与上下文管理
- **提示词管理器** — 多条提示词卡片，支持 Order（顺序）和 Depth（插入深度）精细控制消息位置
- **例图系统** — 拖入参考图自动解析 metadata，作为 few-shot 例图发送给 LLM
- **记忆模式** — 维护完整对话上下文，支持多轮追加生成
- **Prompt 预览** — 查看最终发送给 API 的完整消息和 token 计数

#### 画师库 & OC 库
- **画师库** — 管理画师名、LoRA/触发词、参考图，一键复制
- **OC 角色库** — 原创角色管理，支持服装子系统（多套服装独立开关）
- **插入控制** — 每个角色/服装的 Order/Depth 控制消息插入位置

#### 图像管理器
- **缩略图网格浏览** — 多线程加载 + LRU 缓存，流畅滚动
- **Lightbox 大图查看** — 键盘/鼠标翻页
- **浮动详情面板** — hover 即时显示 metadata，可置顶
- **文件操作** — 移动、重命名（F2）、删除（回收站）、剪切/粘贴
- **喜欢标记** — 持久化收藏，支持"只看喜欢"过滤
- **子文件夹导航** — 前进/后退历史栈 + 鼠标侧键

#### Metadata 工具
- **Metadata 查看器** — 支持 A1111/Forge、ComfyUI、NovelAI（含 LSB 隐写）、Fooocus 四种格式
- **Metadata 销毁器** — 二进制 chunk 级操作，IDAT 零损耗，支持批量处理
- **Metadata 编辑器** — 直接修改图片内嵌的提示词和参数

#### 外观 & 体验
- **暗色/亮色主题** — 磨砂玻璃质感，卡片透明度可调
- **自定义背景** — 从图片提取主色调自动生成配套色板
- **多语言** — 中文 / 英文
- **新手引导** — 首次启动步骤式高亮引导
- **生成历史** — 自动记录所有生成记录，可回溯填充
- **快捷键面板** — F1 查看所有快捷键
- **内嵌字体** — 预装霞鹜文楷 Screen（SIL OFL 授权）

---

### 下载安装

前往 [Releases](https://github.com/1756141021/HainTag/releases) 页面下载最新版本。

1. 下载 `HainTag-vX.X.X-windows.zip`
2. 解压到任意目录
3. 运行 `HainTag.exe`，无需安装

> **系统要求**：Windows 10/11，64 位

---

### 从源码运行

```bash
git clone https://github.com/1756141021/HainTag.git
cd HainTag
pip install -r requirements.txt
python -m native_app
```

**打包**

```bash
pip install pyinstaller
python -m PyInstaller AITagGenerator.spec -y
```

---

### 配置 API

首次启动后，在设置面板填入：

| 字段 | 说明 |
|------|------|
| API Base URL | 兼容 OpenAI 格式的接口地址，例如 `https://api.openai.com/v1` |
| API Key | 你的 API 密钥 |
| 模型 | 点击 ↻ 按钮从 API 拉取可用模型列表 |

---

### 开源协议

本项目基于 [GNU General Public License v3.0](LICENSE) 开源。

---

## English

### Overview

HainTag is a Windows desktop application designed for AI art workflows. It connects to your own LLM API (OpenAI-compatible) and helps you generate, edit, and manage Danbooru-style tags for Stable Diffusion, NovelAI, and similar image generation models.

All data is stored locally — no cloud dependencies.

---

### Features

#### TAG Generation & Editing
- **LLM-powered generation** — Connect to any OpenAI-compatible API (local models, Claude, GPT, etc.) with streaming output
- **Category highlighting** — Output TAGs are automatically color-coded by category (character, scene, outfit, pose, expression, style, quality)
- **Danbooru autocomplete** — 150K+ dictionary with real-time matching, hover shows Chinese translation and usage count
- **Weight scrubbing** — Right-click and drag a TAG to adjust its weight in real time, with automatic bracket syntax
- **Drag-to-reorder** — Left-click drag to rearrange TAG order
- **TAG extraction markers** — Customizable `[TAGS]...[/TAGS]` markers to automatically extract TAG fields from LLM output

#### Prompt & Context Management
- **Prompt manager** — Multiple prompt cards with Order and Depth controls for precise message positioning
- **Example image system** — Drag in reference images to auto-parse their metadata as few-shot examples for the LLM
- **Memory mode** — Maintain full conversation context for multi-turn generation
- **Prompt preview** — View the complete message array sent to the API with token count

#### Artist & OC Library
- **Artist library** — Manage artist names, LoRA/trigger words, and reference images with one-click copy
- **OC character library** — Original character management with an outfit subsystem (multiple outfits, individually toggled)
- **Insertion control** — Per-character Order/Depth settings for message position control

#### Image Manager
- **Thumbnail grid** — Multi-threaded loading with LRU cache for smooth scrolling
- **Lightbox viewer** — Full-screen image viewer with keyboard/mouse navigation
- **Floating detail panel** — Hover to instantly view metadata, pinnable
- **File operations** — Move, rename (F2), delete (Recycle Bin), cut/paste
- **Favorites** — Persistent likes with "favorites only" filter
- **Folder navigation** — Forward/back history stack with mouse side buttons

#### Metadata Tools
- **Metadata viewer** — Supports A1111/Forge, ComfyUI, NovelAI (including LSB steganography), and Fooocus formats
- **Metadata destroyer** — Binary chunk-level operation, IDAT zero-loss, supports batch processing
- **Metadata editor** — Directly modify embedded prompts and parameters

#### Appearance & UX
- **Dark/light themes** — Frosted glass aesthetics with adjustable card transparency
- **Custom background** — Extracts dominant color from an image to generate a matching palette
- **Multilingual** — Chinese / English
- **Onboarding guide** — Step-by-step highlight tour on first launch
- **Generation history** — Automatic log of all generations, with one-click restore
- **Shortcuts panel** — Press F1 to view all keyboard shortcuts
- **Bundled font** — LXGW WenKai Screen included (SIL OFL licensed)

---

### Download

Go to the [Releases](https://github.com/1756141021/HainTag/releases) page to download the latest version.

1. Download `HainTag-vX.X.X-windows.zip`
2. Extract to any directory
3. Run `HainTag.exe` — no installation required

> **Requirements**: Windows 10/11, 64-bit

---

### Run from Source

```bash
git clone https://github.com/1756141021/HainTag.git
cd HainTag
pip install -r requirements.txt
python -m native_app
```

**Build**

```bash
pip install pyinstaller
python -m PyInstaller AITagGenerator.spec -y
```

---

### API Configuration

On first launch, fill in the Settings panel:

| Field | Description |
|-------|-------------|
| API Base URL | An OpenAI-compatible endpoint, e.g. `https://api.openai.com/v1` |
| API Key | Your API key |
| Model | Click ↻ to fetch available models from the API |

---

### License

This project is open source under the [GNU General Public License v3.0](LICENSE).
