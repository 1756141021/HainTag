<div align="center">

<img src="native_app/resources/icon.ico" width="96" />

# HainTag

**Turn the picture in your head into tags a model can read.**

[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](https://www.gnu.org/licenses/gpl-3.0)
[![Platform: Windows](https://img.shields.io/badge/Platform-Windows_10%2F11-0078d4.svg)]()
[![Release](https://img.shields.io/github/v/release/1756141021/HainTag?color=green)](https://github.com/1756141021/HainTag/releases)
[![Downloads](https://img.shields.io/badge/Downloads-Release-orange)](https://github.com/1756141021/HainTag/releases)

A Windows desktop tool for AI art tag generation, editing, and workflow management.

If you find it useful, share it with your friends and give it a ⭐ Star — it means a lot!

[简体中文](README.md) · [About Hein ☽](README.hein.md)

</div>

---

### What is HainTag?

HainTag is a Windows desktop app for AI art workflows. It connects to **any OpenAI-compatible LLM API** and turns your natural language descriptions into Danbooru-style tags for Stable Diffusion, NovelAI, and similar models.

Everything stays local. No cloud, no telemetry, no data leaves your machine.

---

### Download

#### Windows

Head to **[Releases](https://github.com/1756141021/HainTag/releases)** and grab the latest `.zip`.

1. Download `HainTag-vX.X.X-windows.zip`
2. Extract anywhere
3. Run `HainTag.exe` — no installer needed

> **Requires** Windows 10/11, 64-bit

#### macOS

macOS currently runs from source. HainTag is a standalone desktop app, not a ComfyUI custom node. Do not put it in `ComfyUI/custom_nodes` or a node directory.

Choose any folder for the app code. This example puts it in `~/Applications/HainTag`:

```bash
cd ~/Applications
git clone https://github.com/1756141021/HainTag.git
cd HainTag
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m native_app
```

If `git clone` fails while `Receiving objects` or `Unpacking objects`, delete the incomplete `~/Applications/HainTag` folder and run the `git clone` step again. You can also clone into another parent folder, such as `~/Downloads`.

The app code folder is only where the program lives. User data is stored in `~/Library/Application Support/HainTag/`.

---

### What's new in 0.9.1

This release focuses on closing real interaction gaps in the workbench instead of only changing visuals. Context menus, OC shortcuts, history, the floating tray, and image interrogation are wired back into the existing data and settings paths.

| Update | Details |
|--------|---------|
| **Workbench v3** | The output area is now an editable TAG stream with hover hints, category colors, left-drag reorder, right-drag weight scrubbing, and Full / No-Character tabs |
| **Shorter OC flow** | The titlebar `+` opens an in-place OC picker; chips support quick outfit / Order / Depth changes and a right-click management menu |
| **History timeline** | Recent generations appear at the bottom of the workbench; the full history panel can restore input, full TAGs, and no-character TAGs |
| **Floating tray** | Nearby floating cards can collapse into a compact tray; when only one card remains, it restores automatically and the tray hides |
| **Unified menus** | Input, output, library, history, Dock, and tray context menus now use the same i18n, theme, font, and scaling interfaces |
| **Image interrogation** | Local and LLM interrogation share one card-level mode switch while keeping batch images, presets, thresholds, category colors, and copy/send actions |

### Worried about bloat?

Every feature in HainTag lives in its own card — if you don't open it, it doesn't exist. No extra memory overhead. The app is lightweight by design; after sitting idle for a while, memory usage drops even further.

---

### Features

#### Floating Cards & Always-on-Top

Drag any card out of the main window into an independent floating panel. Pin the main window on top. Place your TAG output next to WebUI and work side by side — especially useful with multiple monitors. Multiple floating cards can also be grouped into the floating tray and restored on demand.

---

#### TAG Generation & Editing

- **LLM-powered generation** — Connect any OpenAI-compatible API (local models, Claude, GPT, DeepSeek, Ollama…) with streaming output
- **Category highlighting** — Tags auto-colored by type: character, scene, outfit, pose, expression, style, quality
- **Danbooru autocomplete** — 150K+ dictionary with real-time matching; hover shows translation and usage count
- **Weight scrubbing** — Right-click drag a tag to adjust weight in real time; bracket syntax updates automatically
- **Drag-to-reorder** — Left-click drag to rearrange tag order
- **TAG extraction markers** — Customizable `[TAGS]...[/TAGS]` to extract tags from verbose LLM output
- **Generation timeline** — Recent generations are visible in the workbench, with the full history one click away

#### Prompt & Context Management

- **Prompt manager** — Multiple prompt cards with Order and Depth controls for precise message positioning
- **Example image system** — Drag in reference images; metadata is auto-parsed and sent as few-shot examples
- **Memory mode** — Maintains full conversation context for multi-turn generation
- **Prompt preview** — Inspect the exact message array and token count before sending

#### Artist & OC Library

- **Artist library** — Store artist names, LoRA/trigger words, and reference images; one-click copy
- **OC character library** — Manage original characters with an outfit subsystem (multiple outfits, individually toggled)
- **Insertion control** — Per-character/outfit Order and Depth settings
- **Titlebar OC chips** — Active OCs appear directly in the workbench titlebar for quick add, outfit switching, editing, or removal

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

#### Image Interrogation

- **Local inference** — Offline Danbooru tag recognition using cl_tagger ONNX model; supports ComfyUI model directories
- **LLM vision** — Send images to multimodal APIs for tag generation
- **Auto environment setup** — Automatically downloads Python + onnxruntime when needed, no manual setup
- **Threshold controls** — Independent sliders for general and character tag confidence thresholds
- **Confidence toggle** — Show or hide confidence percentages with one click

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

If you are not using the Windows release package, follow the macOS source-run steps above. The important part is to choose a parent folder first, then clone the repo as its `HainTag` subfolder, such as `~/Applications/HainTag`.

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
