<div align="center">

<img src="native_app/resources/icon.ico" width="96" />

# HainTag

**Turn the picture in your head into tags a model can read.**

[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](https://www.gnu.org/licenses/gpl-3.0)
[![Platform: Windows](https://img.shields.io/badge/Platform-Windows_10%2F11-0078d4.svg)]()
[![Release](https://img.shields.io/github/v/release/1756141021/HainTag?color=green)](https://github.com/1756141021/HainTag/releases)
[![Downloads](https://img.shields.io/github/downloads/1756141021/HainTag/total?color=orange)](https://github.com/1756141021/HainTag/releases)

A Windows desktop tool for AI art tag generation, editing, and workflow management.

[简体中文](README.md) · [About Hein ☽](README.hein.md)

</div>

---

### What is HainTag?

HainTag is a Windows desktop app for AI art workflows. It connects to **any OpenAI-compatible LLM API** and turns your natural language descriptions into Danbooru-style tags for Stable Diffusion, NovelAI, and similar models.

Everything stays local. No cloud, no telemetry, no data leaves your machine.

---

### Download

Head to **[Releases](https://github.com/1756141021/HainTag/releases)** and grab the latest `.zip`.

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
- **Generation history** — Every generation logged; one-click restore
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
