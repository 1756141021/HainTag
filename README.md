<div align="center">

<img src="native_app/resources/icon.ico" width="96" />

# HainTag · 海茵的标签工坊

**「把你脑海里的画面，变成机器能读懂的语言。」**

[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](https://www.gnu.org/licenses/gpl-3.0)
[![Platform: Windows](https://img.shields.io/badge/Platform-Windows_10%2F11-0078d4.svg)]()
[![Release](https://img.shields.io/github/v/release/1756141021/HainTag?color=green)](https://github.com/1756141021/HainTag/releases)
[![Downloads](https://img.shields.io/github/downloads/1756141021/HainTag/total?color=orange)](https://github.com/1756141021/HainTag/releases)

AI 绘画 TAG 生成 · 管理 · 工作流——一站式 Windows 桌面工具

[海茵的介绍 ☽](README.hein.md) · [English](README.en.md)

</div>

---

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
