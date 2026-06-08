# HainTag macOS 移植 — 平台粘合层逐文件分析

> 范围：本文只覆盖 7 个直接含平台粘合代码的文件。UI 控件层、业务逻辑层（api_client / logic / models / theme / i18n / tag_dictionary 等）默认跨平台，不在本表里。
>
> 行号基线：commit `428dd74`（v0.9.9）。

---

## 1. `native_app/updater.py`

### (1) 现在 Windows 上是怎么做的

打包后（`sys.frozen=True`）走"程序内更新"全自动流程：
1. 后台线程查 GitHub Releases API（`UpdateChecker`）
2. 选 Windows 资产 ZIP，三级 HTTP fallback（httpx → requests → urllib）下载到 `%TEMP%/haintag_update_xxx/update.zip`
3. `zipfile.testzip()` + 必须包含 `haintag.exe`
4. 解压到同 temp 目录
5. 写一个 `haintag_update.bat` 到 `%TEMP%`，里面用 `tasklist /FI "PID eq …"` 等待主进程退出，然后 `robocopy /MIR` 镜像覆盖安装目录，再 `start ""` 拉新 exe，最后 `rd /s /q` + `del "%~f0"` 自删除
6. 主进程启动这个 `.bat` 并退出

源码模式或资产不是 ZIP 时，回退到 `QDesktopServices.openUrl` 打开 Releases 页。

### (2) 平台特定调用精确行号

| 行号 | 内容 | 性质 |
|------|------|------|
| [updater.py:60-81](native_app/updater.py#L60) | `_release_download_url` 用 `windows_markers=("windows","win64","win32","win-x64","x64","amd64")` 选包，且明确把 `("macos","darwin","linux","arm64")` 列为 *排除* 标记 | 选错平台资产 |
| [updater.py:185](native_app/updater.py#L185) | ZIP 校验：`n.endswith("/haintag.exe") or n == "haintag.exe"` | macOS 包没有 .exe |
| [updater.py:276-300](native_app/updater.py#L276) | `_generate_update_script` — 整段 Windows batch | 完全无法在 macOS 跑 |
| L283 | `chcp 65001` | Windows 代码页 |
| L286 | `tasklist /FI "PID eq {pid}"` | 不存在 |
| L289-290 | `robocopy "{source_dir}" "{target_dir}" /MIR /R:3 /W:2 …` | 不存在 |
| L292 | `start "" "{exe_path}"` | 不存在 |
| L294 | `rd /s /q "{clean_target}"` | shell 不一样 |
| L295 | `del "%~f0"` | shell 不一样 |
| L297 | 写 `haintag_update.bat` 到 `tempfile.gettempdir()` | 文件名 |
| [updater.py:441](native_app/updater.py#L441) | `_is_zip_download_url` 严格 `.zip` — macOS 通常发 `.dmg` | 资产格式假设 |

### (3) macOS 怎么写

策略：保留整体的"下载 → 校验 → 写脚本 → 启动脚本退出主进程"流水线，把三个 Windows-only 段（资产挑选、ZIP/DMG 校验、替换脚本）按 `sys.platform` 分支。

```python
# updater.py — 顶部
import sys
import shutil
_IS_MAC = sys.platform == "darwin"

# 资产挑选：macOS 优先 .dmg，Windows 优先 .zip
def _release_download_url(assets: list[Any]) -> str:
    win_zips: list[str] = []
    mac_assets: list[str] = []          # .dmg or .zip
    generic: list[str] = []
    for asset in assets:
        if not isinstance(asset, dict):
            continue
        url = str(asset.get("browser_download_url", "") or "")
        name = str(asset.get("name", "") or url).lower()
        if not url:
            continue
        if not (name.endswith(".zip") or name.endswith(".dmg")):
            continue
        if any(m in name for m in ("macos", "darwin", "mac-arm64", "mac-x64", "osx")):
            mac_assets.append(url)
        elif any(m in name for m in ("windows", "win64", "win32", "win-x64", "x64", "amd64")):
            if name.endswith(".zip"):
                win_zips.append(url)
        elif "haintag" in name and not any(
            m in name for m in ("linux", "arm64-linux")
        ):
            generic.append(url)
    bucket = mac_assets if _IS_MAC else win_zips
    return bucket[0] if bucket else (generic[0] if generic else _GITHUB_RELEASES_PAGE)

# 校验：macOS DMG 走 hdiutil verify；macOS ZIP 检查 .app 路径
def _validate_archive(archive_path: str, t) -> None:
    if _IS_MAC and archive_path.lower().endswith(".dmg"):
        result = subprocess.run(
            ["hdiutil", "verify", archive_path],
            capture_output=True, text=True
        )
        if result.returncode != 0:
            raise RuntimeError(t.t("update_zip_corrupt").format(file="dmg"))
        return
    with zipfile.ZipFile(archive_path, "r") as zf:
        bad = zf.testzip()
        if bad:
            raise RuntimeError(t.t("update_zip_corrupt").format(file=bad))
        names = [n.lower().replace("\\", "/") for n in zf.namelist()]
        if _IS_MAC:
            ok = any("haintag.app/contents/macos/haintag" in n for n in names)
            label = "HainTag.app"
        else:
            ok = any(n.endswith("/haintag.exe") or n == "haintag.exe" for n in names)
            label = "HainTag.exe"
        if not ok:
            raise RuntimeError(t.t("update_zip_missing_exe").format(file=label))

# DMG 提取（先挂载到只读 mountpoint，rsync 出来，detach）
def _extract_dmg(dmg_path: str, dest_dir: str) -> str:
    mount_root = tempfile.mkdtemp(prefix="haintag_dmg_")
    # `hdiutil attach -nobrowse -mountpoint /tmp/xxx -readonly file.dmg`
    subprocess.run(
        ["hdiutil", "attach", "-nobrowse", "-readonly",
         "-mountpoint", mount_root, dmg_path],
        check=True, capture_output=True,
    )
    try:
        # 找出挂载点里的 .app
        candidates = [p for p in os.listdir(mount_root) if p.endswith(".app")]
        if not candidates:
            raise RuntimeError("No .app found inside DMG")
        src_app = os.path.join(mount_root, candidates[0])
        dst_app = os.path.join(dest_dir, candidates[0])
        # cp -R 比 shutil.copytree 更尊重 macOS 的 resource forks/扩展属性
        subprocess.run(["cp", "-R", src_app, dst_app], check=True)
    finally:
        subprocess.run(["hdiutil", "detach", mount_root, "-quiet"],
                       capture_output=True)
        shutil.rmtree(mount_root, ignore_errors=True)
    return dst_app

# 替换脚本
def _generate_update_script_mac(
    pid: int, source_app: str, target_app: str,
    cleanup_dir: str | None = None,
) -> str:
    """Bash script that waits for old PID, swaps the .app, relaunches."""
    cleanup = cleanup_dir or os.path.dirname(source_app)
    # 注意 .app 路径里可能有空格 — 全部用双引号
    script = f"""#!/bin/bash
set -u
# wait for the old process to exit
while kill -0 {pid} 2>/dev/null; do sleep 0.3; done
sleep 0.5
# swap the .app
rm -rf "{target_app}"
cp -R "{source_app}" "{target_app}" || {{
  osascript -e 'display alert "HainTag 更新失败" message "无法替换应用程序，请手动从下载目录拖入"'
  exit 1
}}
# strip Gatekeeper quarantine on the freshly copied bundle
xattr -dr com.apple.quarantine "{target_app}" 2>/dev/null || true
# relaunch
open "{target_app}"
# self-cleanup
rm -rf "{cleanup}" 2>/dev/null || true
rm -- "$0"
"""
    path = os.path.join(tempfile.gettempdir(), "haintag_update.sh")
    with open(path, "w", encoding="utf-8") as f:
        f.write(script)
    os.chmod(path, 0o755)
    return path

# 启动脚本（替换 window.py 里调 .bat 的地方）
def _spawn_update_script(script_path: str) -> None:
    if _IS_MAC:
        subprocess.Popen(
            ["/bin/bash", script_path],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,   # 脱离父进程会话
        )
    else:
        subprocess.Popen(
            ["cmd.exe", "/c", "start", "", script_path],
            creationflags=subprocess.DETACHED_PROCESS
                          | subprocess.CREATE_NEW_PROCESS_GROUP,
        )
```

**注意点：**
- `cp -R`（不是 `shutil.copytree`）才能正确保留 `.app` 包内的扩展属性、符号链接和签名结构
- `xattr -dr com.apple.quarantine` 必须在 `cp -R` 之后跑一次，否则用户双击会被 Gatekeeper 拦截（"已损坏"）
- `start_new_session=True` 等价于 batch 里的 `(goto) 2>nul & del`，确保 bash 脚本能在主进程退出后存活
- **不要** 用 `os.execv` 替换主进程后再 cp — Python runtime 还在 .app 里，会自损

---

## 2. `native_app/python_env.py`

### (1) 现在 Windows 上是怎么做的

ONNX 子进程模式需要一个能 import onnxruntime 的 Python；当宿主 Python 不行（PyInstaller 装的 Python 3.14 与 onnxruntime 不兼容）时，下载独立环境：

1. 从 `python.org/ftp/python/3.12.8/python-3.12.8-embed-amd64.zip` 下载 Windows embeddable
2. 解压到 `%APPDATA%/HainTag/python_env/`（产生 `python.exe`）
3. 修补 `._pth` 文件（取消 `#import site` 注释，让 site-packages 生效）
4. 下载 `get-pip.py`，跑 `python.exe get-pip.py`（产出 `Scripts/pip.exe`）
5. `pip install onnxruntime numpy Pillow`，中文 locale 自动加 `-i 清华镜像`
6. 验证：跑 `python.exe -c "import onnxruntime"`

### (2) 平台特定调用精确行号

| 行号 | 内容 | 性质 |
|------|------|------|
| [python_env.py:20-22](native_app/python_env.py#L20) | `python-{ver}-embed-amd64.zip` URL | macOS 上没有"embeddable" Python 分发 |
| [python_env.py:29](native_app/python_env.py#L29) | `_CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)` | 已 getattr 守卫，macOS 上为 0 — 不影响 |
| [python_env.py:34-37](native_app/python_env.py#L34) | `_env_dir()` 用 `os.environ.get("APPDATA")`，fallback `~/AppData/Roaming` | macOS 应该用 `~/Library/Application Support` |
| [python_env.py:42](native_app/python_env.py#L42) | `python.exe` | macOS 是 `bin/python3` |
| [python_env.py:120, 124, 149-150, 163-164](native_app/python_env.py#L120) | 写入路径全部假设 `python.exe` 和 `Scripts/pip.exe` | 子进程脚本布局不同 |
| [python_env.py:222-234](native_app/python_env.py#L222) | `_patch_pth` 修补 `._pth` 文件 | macOS venv 没有 `._pth` 概念 |
| [python_env.py:125, 139, 154, 166, 175, 195, 214, 219](native_app/python_env.py#L125) | 进度文案是中文硬编码 | 不算平台问题，但顺手处理 |
| [python_env.py:150](native_app/python_env.py#L150) | `"解压后未找到 python.exe"` 中文硬编码 + .exe 字眼 | 同上 |

### (3) macOS 怎么写

macOS 上没有"embeddable Python"。最自然的方案是：**用宿主系统的 python3 做 venv**。系统 macOS 12+ 自带 `/usr/bin/python3`，绝大多数 ComfyUI / Pinokio 用户也已经有 Homebrew 的 `python@3.12`。

```python
# python_env.py
import platform
import shutil

_IS_MAC = sys.platform == "darwin"

def _env_dir() -> str:
    if _IS_MAC:
        base = os.environ.get("XDG_DATA_HOME") or str(
            Path.home() / "Library" / "Application Support"
        )
        return os.path.join(base, "HainTag", "python_env")
    appdata = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
    return os.path.join(appdata, "HainTag", "python_env")


def _python_exe_in(env_dir: str) -> str:
    if _IS_MAC:
        return os.path.join(env_dir, "bin", "python3")
    return os.path.join(env_dir, "python.exe")


def get_embedded_python_path() -> str | None:
    candidate = _python_exe_in(_env_dir())
    return candidate if os.path.isfile(candidate) else None


def _find_host_python() -> str | None:
    """Pick a system python3 for venv creation."""
    for candidate in ("python3.12", "python3.11", "python3"):
        path = shutil.which(candidate)
        if path:
            return path
    # Fallbacks for macOS bare metal
    for path in ("/opt/homebrew/bin/python3", "/usr/local/bin/python3", "/usr/bin/python3"):
        if os.path.isfile(path):
            return path
    return None


# 在 PythonEnvSetupWorker 里
class PythonEnvSetupWorker(QThread):
    progress = pyqtSignal(str, int)
    finished = pyqtSignal(str)
    error = pyqtSignal(str)

    def run(self):
        try:
            if _IS_MAC:
                self._setup_mac()
            else:
                self._setup()                # 现有 Windows 流程
        except Exception as exc:
            self.error.emit(str(exc))

    def _setup_mac(self):
        env_dir = _env_dir()
        os.makedirs(env_dir, exist_ok=True)
        python_exe = _python_exe_in(env_dir)

        if not os.path.isfile(python_exe):
            host = _find_host_python()
            if host is None:
                self.error.emit(
                    "未找到系统 python3，请先安装：brew install python@3.12"
                )
                return
            self.progress.emit("正在创建 venv...", 10)
            result = subprocess.run(
                [host, "-m", "venv", env_dir],
                capture_output=True, text=True, timeout=180,
            )
            if result.returncode != 0:
                self.error.emit(f"venv 创建失败: {result.stderr.strip()}")
                return

        if self.isInterruptionRequested():
            return

        self.progress.emit("正在升级 pip...", 30)
        subprocess.run(
            [python_exe, "-m", "pip", "install", "-U", "pip"],
            capture_output=True, text=True, timeout=180,
        )

        if self.isInterruptionRequested():
            return

        self.progress.emit("正在安装 onnxruntime, numpy, Pillow...", 55)
        cmd = [
            python_exe, "-m", "pip", "install",
            "--no-warn-script-location",
            *REQUIRED_PACKAGES,
            *_pip_index_args(),
        ]
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=600,
        )
        if result.returncode != 0:
            self.error.emit(f"依赖安装失败: {result.stderr.strip()}")
            return

        if self.isInterruptionRequested():
            return

        self.progress.emit("正在验证环境...", 95)
        if not is_env_usable(python_exe):
            self.error.emit("环境验证失败：onnxruntime 无法加载")
            return

        self.progress.emit("✓ 环境配置完成", 100)
        self.finished.emit(python_exe)
```

**注意点：**
- onnxruntime 在 macOS arm64 / x86_64 都有官方 wheel，`pip install onnxruntime` 直接成功
- `_patch_pth` 整个分支在 macOS 不需要（venv 自动正确）
- 中文 locale 检测的清华镜像同样适用 macOS（`pip` 命令不分平台）
- 如果 `_find_host_python()` 为 None，建议提示用户用 Homebrew 装 Python，而不是去下载 python.org installer（installer 需要管理员密码）

---

## 3. `native_app/tagger.py`

### (1) 现在 Windows 上是怎么做的

两种推理模式：进程内 import onnxruntime（直接模式），或调外部 Python 的 `tagger_subprocess.py`（子进程模式，兼容性强）。子进程启动前清理 PyInstaller 注入的环境变量（`PYTHONHOME`、`PYTHONPATH`、`_MEIPASS`），并把 `_internal/` 从 `PATH` 里剔除，防止打包内 DLL 与外部 Python 的版本冲突。

### (2) 平台特定调用精确行号

| 行号 | 内容 | 性质 |
|------|------|------|
| [tagger.py:322](native_app/tagger.py#L322) | `"需要指定外部 Python 路径（如 ComfyUI 的 Python）"` | UI 文案，提到 ComfyUI；macOS 用户可能更熟悉 Pinokio / DiffusionBee — 不算 bug 但可以补一句 |
| [tagger.py:344-356](native_app/tagger.py#L344) | 清理 PyInstaller 环境变量 + 从 PATH 剔除 `_internal` | macOS 上 `_MEIPASS` 也存在（PyInstaller bundle 一样），逻辑可保留 |
| [tagger.py:361](native_app/tagger.py#L361) | `creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0)` | 已 getattr 守卫，macOS 为 0 — 无害 |

**结论：tagger.py 几乎不需要改。** 唯一的一处考虑：

### (3) macOS 怎么写

```python
# tagger.py:322 — 错误信息更通用
if not python:
    raise RuntimeError(
        "需要指定外部 Python 路径（macOS：可指向 Homebrew 的 python3 或 ComfyUI 的 venv）"
    )
```

PyInstaller `_MEIPASS` 在 macOS .app bundle 里指向 `Contents/Frameworks/` 之类的位置，剔除该路径仍然是正确的隔离策略，不需要改。

---

## 4. `native_app/tagger_subprocess.py`

### (1) 现在 Windows 上是怎么做的

被 `tagger.py:_predict_subprocess` 调起的独立脚本：清掉 `PYTHONHOME/PYTHONPATH/_MEIPASS` → import onnxruntime/numpy/PIL → 跑推理 → JSON 输出到 stdout。命令行解析、路径处理全部用 `os.path.*`，没有 shell。

### (2) 平台特定调用精确行号

**无。** 全文是纯 Python，使用 numpy / PIL / onnxruntime / json / sys / os，全部跨平台。

[tagger_subprocess.py:13-14](native_app/tagger_subprocess.py#L13) 的环境清理在 macOS PyInstaller bundle 里同样需要（`_MEIPASS` 会污染子进程），保留即可。

### (3) macOS 怎么写

**无需修改。** 验证步骤：在 macOS 装好 venv 后跑一次：

```bash
~/Library/Application\ Support/HainTag/python_env/bin/python3 \
  /path/to/HainTag.app/Contents/Resources/native_app/tagger_subprocess.py \
  /path/to/test.png /path/to/model.onnx /path/to/mapping.json
```

预期输出 `{"results": {...}}`。如果失败会落到 `ort_debug.txt` —— 注意这个 debug 文件写在 `os.path.dirname(__file__)`，在 .app bundle 里这是只读 `Resources/` 目录，写入会失败。**这是 Mac 上需要小修的点：**

```python
# tagger_subprocess.py:74 — 把 debug 文件写到可写目录
def _writable_dir() -> str:
    if sys.platform == "darwin":
        return os.path.expanduser("~/Library/Logs/HainTag")
    if sys.platform == "win32":
        return os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "HainTag", "logs")
    return os.path.expanduser("~/.cache/HainTag")

_log_dir = _writable_dir()
os.makedirs(_log_dir, exist_ok=True)
_debug_path = os.path.join(_log_dir, "ort_debug.txt")
```

---

## 5. `native_app/window.py` — Win32 调用

### (1) 现在 Windows 上是怎么做的

无边框窗口（`FramelessWindowHint`）+ ctypes 直接撩 user32 实现"看似 frameless 但保留 Windows 原生 resize / Aero Snap"：

- `_apply_native_window_style`（[L1606-1630](native_app/window.py#L1606)）通过 `GetWindowLongW / SetWindowLongW` 给 hwnd 加上 `WS_THICKFRAME | WS_MAXIMIZEBOX | WS_MINIMIZEBOX | WS_SYSMENU`，剥掉 `WS_CAPTION`，再 `SetWindowPos(SWP_FRAMECHANGED)` 让样式立即生效
- `nativeEvent`（[L3543-3560](native_app/window.py#L3543)）拦截 `WM_NCCALCSIZE`（声明整个窗口都是 client area，即去掉非客户区边框）和 `WM_NCHITTEST`（自定义边缘命中测试，返回 HT* 常量让系统接管 resize 拖拽与光标）
- `paintEvent`（[L3508-3520](native_app/window.py#L3508)）在窗口 4 边各画一条 `alpha=12` 的几乎透明矩形 — 因为 DWM 不会对完全透明的像素发 `WM_NCHITTEST`，必须有低 alpha 像素让 DWM 注册到这个 zone

### (2) 平台特定调用精确行号

| 行号 | 内容 | 性质 |
|------|------|------|
| [window.py:9-11](native_app/window.py#L9) | `if sys.platform == "win32": import ctypes; from ctypes import wintypes` | 已守卫，macOS 不会 import |
| [window.py:113-134](native_app/window.py#L113) | Windows 常量（`GWL_STYLE`, `WS_THICKFRAME`, `WM_NCHITTEST`, `HTLEFT…HTBOTTOMRIGHT` 等） | 已守卫；但 `HT*` 常量在 macOS 边缘命中测试里仍可复用作为内部枚举值 |
| [window.py:240](native_app/window.py#L240) | `setWindowFlags(FramelessWindowHint | Window)` | 跨平台 Qt API，但 macOS 上 frameless 不会自动出现"红黄绿"交通灯，靠应用内自绘按钮支撑 — 这里需要决策 |
| [window.py:244](native_app/window.py#L244) | `icon_path = … / 'icon.png'` 但 resources 里只有 `icon.ico` | **潜在 bug** — Windows 上估计也没生效，可能靠 PyInstaller spec 注入；macOS 应当用 `.icns` |
| [window.py:1606-1630](native_app/window.py#L1606) | `_apply_native_window_style` — 整段 `ctypes.windll.user32` 调用 | 已 `if sys.platform != 'win32': return` 守卫；macOS 上 NOOP 即可 |
| [window.py:3508-3520](native_app/window.py#L3508) | `paintEvent` 4 边低 alpha 矩形以触发 `WM_NCHITTEST` | macOS 不需要；多余的绘制开销 |
| [window.py:3543-3560](native_app/window.py#L3543) | `nativeEvent` 拦截 `WM_NCCALCSIZE` / `WM_NCHITTEST` | 已 `if sys.platform != 'win32': return False, 0` 守卫 |
| [window.py:3562-3594](native_app/window.py#L3562) | `_window_resize_hit_test` — **本身平台无关**，目前只被 Windows nativeEvent 调用 | macOS 需要复用它来做手动鼠标事件 resize |

### (3) macOS 怎么写

macOS 没有 `WM_NCHITTEST` —— frameless + 自定义 resize 必须用 Qt 鼠标事件实现。`_window_resize_hit_test` 是平台无关的，可以直接复用。

**三条路线，需要让用户拍板：**

**A. 保留 frameless 全自定义** — 视觉一致，符合现状，但牺牲 macOS 原生交通灯和"全屏化"按钮：

```python
# window.py
class MainWindow(QWidget):
    def __init__(self, ...):
        ...
        if sys.platform == "darwin":
            # 主窗口 + 4 边边距处接受鼠标事件
            self.setMouseTracking(True)
            self._resize_edge: int | None = None
            self._resize_origin: tuple[QPoint, QRect] | None = None
            self._mac_min_size = QSize(_dp(720), _dp(480))

    def paintEvent(self, event) -> None:
        if sys.platform != "win32":
            return  # macOS 无需绘制 alpha=12 边缘
        # 现有 Windows 绘制逻辑
        painter = QPainter(self)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(0, 0, 0, 12))
        m = WINDOW_SURFACE_MARGIN
        w, h = self.width(), self.height()
        painter.drawRect(0, 0, w, m)
        painter.drawRect(0, h - m, w, m)
        painter.drawRect(0, m, m, h - 2 * m)
        painter.drawRect(w - m, m, m, h - 2 * m)
        painter.end()

    def mouseMoveEvent(self, event) -> None:
        if sys.platform == "darwin":
            global_pos = event.globalPosition().toPoint()
            if self._resize_edge is None:
                edge = self._window_resize_hit_test(global_pos)
                self._update_resize_cursor(edge)
            else:
                self._continue_resize(global_pos)
        super().mouseMoveEvent(event)

    def mousePressEvent(self, event) -> None:
        if sys.platform == "darwin" and event.button() == Qt.MouseButton.LeftButton:
            global_pos = event.globalPosition().toPoint()
            edge = self._window_resize_hit_test(global_pos)
            if edge is not None and not self.isMaximized():
                self._resize_edge = edge
                self._resize_origin = (global_pos, QRect(self.geometry()))
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if sys.platform == "darwin" and self._resize_edge is not None:
            self._resize_edge = None
            self._resize_origin = None
            self.unsetCursor()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def _continue_resize(self, global_pos: QPoint) -> None:
        if self._resize_origin is None or self._resize_edge is None:
            return
        anchor, origin_rect = self._resize_origin
        dx = global_pos.x() - anchor.x()
        dy = global_pos.y() - anchor.y()
        new_rect = QRect(origin_rect)
        edge = self._resize_edge
        min_w = self._mac_min_size.width()
        min_h = self._mac_min_size.height()
        if edge in (HTLEFT, HTTOPLEFT, HTBOTTOMLEFT):
            new_left = min(origin_rect.left() + dx, origin_rect.right() - min_w)
            new_rect.setLeft(new_left)
        if edge in (HTRIGHT, HTTOPRIGHT, HTBOTTOMRIGHT):
            new_right = max(origin_rect.right() + dx, origin_rect.left() + min_w)
            new_rect.setRight(new_right)
        if edge in (HTTOP, HTTOPLEFT, HTTOPRIGHT):
            new_top = min(origin_rect.top() + dy, origin_rect.bottom() - min_h)
            new_rect.setTop(new_top)
        if edge in (HTBOTTOM, HTBOTTOMLEFT, HTBOTTOMRIGHT):
            new_bottom = max(origin_rect.bottom() + dy, origin_rect.top() + min_h)
            new_rect.setBottom(new_bottom)
        self.setGeometry(new_rect)

    def _update_resize_cursor(self, edge: int | None) -> None:
        cursors = {
            HTLEFT: Qt.CursorShape.SizeHorCursor,
            HTRIGHT: Qt.CursorShape.SizeHorCursor,
            HTTOP: Qt.CursorShape.SizeVerCursor,
            HTBOTTOM: Qt.CursorShape.SizeVerCursor,
            HTTOPLEFT: Qt.CursorShape.SizeFDiagCursor,
            HTBOTTOMRIGHT: Qt.CursorShape.SizeFDiagCursor,
            HTTOPRIGHT: Qt.CursorShape.SizeBDiagCursor,
            HTBOTTOMLEFT: Qt.CursorShape.SizeBDiagCursor,
        }
        if edge is None:
            self.unsetCursor()
        else:
            self.setCursor(QCursor(cursors[edge]))
```

`_apply_native_window_style` 已经守卫好了，不需要改。需要把 `WS_THICKFRAME` 等常量挪到模块顶层无条件定义（当作内部枚举），因为现在 `if sys.platform == "win32"` 守卫里 macOS 拿不到 `HTLEFT` 等：

```python
# window.py:113 — 改为无条件定义这些 HT* 常量（Windows 系统常量也定义，但只在 win32 用到）
GWL_STYLE = -16
WS_THICKFRAME = 0x00040000
# … 其它 WS_/SWP_/WM_ 常量
HTLEFT = 10
HTRIGHT = 11
HTTOP = 12
HTTOPLEFT = 13
HTTOPRIGHT = 14
HTBOTTOM = 15
HTBOTTOMLEFT = 16
HTBOTTOMRIGHT = 17
```

**C.（推荐）保留 macOS 原生窗口外壳，标题栏透明并把内容延伸到顶部** — 视觉接近 frameless（无标题文字、内容贴顶、磨砂玻璃可保留），但保留原生交通灯、原生 resize（系统级，自动处理 retina / 多显示器）、tile-to-left/right、Mission Control 与 macOS 用户预期：

技术要点：
- macOS 上不加 `Qt.WindowType.FramelessWindowHint`，让 Qt 创建标准 NSWindow
- 通过 `pyobjc-framework-Cocoa` 拿到底层 NSWindow，设：
  - `titlebarAppearsTransparent = YES` —— 标题栏背景透明，让应用色板透出
  - `titleVisibility = NSWindowTitleHidden` —— 隐藏标题文字（Dock tooltip / Window 菜单仍能拿到 `setWindowTitle()` 的值）
  - `styleMask |= NSFullSizeContentView` —— content view 延伸到标题栏下方，视觉上"贴顶"
  - `movableByWindowBackground = YES` —— 整个窗口背景都可拖拽（不只是标题栏）
- 应用内自绘的 `─ □ ×` 按钮（[window.py:267-269](native_app/window.py#L267)）在 macOS 上隐藏，标题栏左上 80×28 px 让给系统三色按钮
- 应用内的"中/EN" / 设置 ⚙ / 置顶 📌 / 帮助 ? 按钮维持现状，但确保都在右侧（远离交通灯）
- `_apply_native_window_style` / `paintEvent` 边框 / `nativeEvent` / 手动 mouse resize **全部跳过** —— macOS 帮你做完了

```python
# native_app/macos_window.py（新文件）— 把所有 PyObjC 调用集中在一处
"""macOS-specific NSWindow tweaks. No-op on other platforms.

Requires `pyobjc-framework-Cocoa` (added to requirements.txt under
the macOS marker; bundle gains ~3-5 MB after PyInstaller dead-stripping).
"""
from __future__ import annotations

import sys
from PyQt6.QtWidgets import QWidget

# AppKit constants (avoid importing AppKit at module load time on non-mac)
_NS_WINDOW_TITLE_HIDDEN = 1
_NS_FULLSIZE_CONTENT_VIEW_MASK = 1 << 15  # 0x8000


def apply_macos_titlebar(window: QWidget) -> bool:
    """Make the window use a transparent, hidden-title titlebar with the
    content view extending into it. Returns True on success.

    MUST be called after `window.show()` — the underlying NSWindow
    doesn't exist until Qt has realized the platform window.
    """
    if sys.platform != "darwin":
        return False
    try:
        import objc                          # noqa: F401
        from ctypes import c_void_p          # noqa: F401
    except ImportError:
        return False

    view_ptr = int(window.winId())
    if view_ptr == 0:
        return False

    import objc
    nsview = objc.objc_object(c_void_p=view_ptr)
    nswindow = nsview.window()
    if nswindow is None:
        return False

    nswindow.setTitlebarAppearsTransparent_(True)
    nswindow.setTitleVisibility_(_NS_WINDOW_TITLE_HIDDEN)
    mask = int(nswindow.styleMask())
    nswindow.setStyleMask_(mask | _NS_FULLSIZE_CONTENT_VIEW_MASK)
    nswindow.setMovableByWindowBackground_(True)
    return True
```

```python
# window.py — 集成点

# (a) 顶部 import — 懒加载，避免非 mac 平台 import pyobjc
if sys.platform == "darwin":
    from .macos_window import apply_macos_titlebar
else:
    def apply_macos_titlebar(_w):  # noqa: ARG001
        return False

# (b) L240 windowFlags — macOS 上不加 FramelessWindowHint
flags = Qt.WindowType.Window
if sys.platform != "darwin":
    flags |= Qt.WindowType.FramelessWindowHint
self.setWindowFlags(flags)

# (c) L267-269 标题栏按钮 — macOS 上隐藏 ─ □ ×，并给标题栏左侧让出 80px
if sys.platform == "darwin":
    self.btn_min.hide()
    self.btn_max.hide()
    self.btn_close.hide()
    title_layout.insertSpacing(0, _dp(80))   # leave room for traffic lights
    self.title_bar.setCursor(Qt.CursorShape.ArrowCursor)  # 不再需要 OpenHand 提示

# (d) showEvent — 真正应用 NSWindow 设置
def showEvent(self, event) -> None:
    super().showEvent(event)
    if sys.platform == "win32":
        self._apply_native_window_style()
    elif sys.platform == "darwin":
        apply_macos_titlebar(self)
        # Qt 会在某些 setWindowFlags() 调用后 recreate NSWindow，
        # 重新进入 showEvent 时再 apply 一次即可（幂等）

# (e) paintEvent / nativeEvent — macOS 上完全跳过（已用 sys.platform 守卫）
```

`requirements.txt` 增加 macOS 标记的依赖：

```
pyobjc-framework-Cocoa>=10.0; sys_platform == "darwin"
```

**风险点：**

1. **PyObjC 体积**：`pyobjc-framework-Cocoa` 单独 wheel ~10 MB，PyInstaller 死代码消除后实际包体积增量约 3–5 MB，可接受
2. **NSWindow 时机**：`winId()` 在 `__init__` 阶段拿到的 NSView 还没绑定 NSWindow（值为 0 或 view.window() 返回 None）。必须在 `showEvent` 里调用；首次成功后 Qt 通常不会重建 NSWindow，但触发 `setWindowFlags()` / 切置顶 / 最大化恢复时偶发重建，所以 `showEvent` 里 idempotent 重 apply 即可
3. **`movableByWindowBackground=YES` 与 Qt 鼠标事件冲突**：用户在文本输入框、按钮、滑块等控件上点击空白区域时也可能误触整窗拖动。两种缓解：
   - 在重要控件上 `setAttribute(Qt.WidgetAttribute.WA_NoMousePropagation)` 或装事件过滤器吃掉鼠标事件
   - 或者保守做法：放弃 `movableByWindowBackground=YES`，让 macOS 默认行为（只能从标题栏区域拖拽）。即便如此，FullSizeContentView 仍然有效，标题栏区域是窗口顶部 28 px
4. **绿按钮（zoom button）行为差异**：macOS 默认点击绿按钮 = 进入全屏 fullscreen mode（创建独立 Space），与 Windows `□`（最大化填可用屏幕）不一致。若希望保持 Windows 习惯，可设 `nswindow.setCollectionBehavior_(NSWindowCollectionBehaviorFullScreenAuxiliary)` 让绿按钮做 zoom 而不是 fullscreen；如不处理，macOS 用户会按本地预期使用，问题不大
5. **交通灯位置硬编码**：默认 (8, 8) 起，三个按钮各 14×16 px、间距 8 px，总占 ~70 px。我们留 80 px 是 8 px 富余；如果未来 macOS 改设计（Tahoe / Sequoia 各版本细节有微调），需要重新测量
6. **暗黑模式联动**：macOS 系统切 light/dark 时，透明标题栏会让应用主题色直接显露。如果用户在 macOS 暗色模式但用 HainTag 亮色主题，标题栏可能与窗口边缘出现色差。可监听 Qt 的 `QGuiApplication.styleHints().colorScheme()` 或在标题栏背景显式设应用主题色
7. **`paintEvent` 4 边低 alpha 边框**：macOS 路线 C 下完全跳过 —— 不需要触发 `WM_NCHITTEST`，原生 resize 自动处理。这块代码用 `if sys.platform == "win32"` 守卫即可
8. **WindowStaysOnTopHint 切换会重建 NSWindow**：Qt 在切置顶时会调 `setWindowFlags()` 触发 NSWindow recreate，导致透明标题栏设置丢失。需要在 `_apply_pinned_state` 调用后重新 `apply_macos_titlebar(self)`，否则置顶后标题栏会突然变回不透明白条
9. **多屏不同 DPI / Retina**：原生窗口在多显示器拖动时由系统自动处理 backing scale，不像 Windows 路线 A 还要手算 DPI。**这反而是路线 C 的优点。**

---

**B. macOS 上放弃 frameless，使用原生标题栏** — 改动最小，但视觉风格与 Windows 不一致：

```python
# window.py:240
flags = Qt.WindowType.Window
if sys.platform != "darwin":
    flags |= Qt.WindowType.FramelessWindowHint
self.setWindowFlags(flags)
# macOS 上自绘的标题栏按钮（设置/语言/置顶/最大化/关闭）需要隐藏，让出 traffic light
if sys.platform == "darwin":
    for btn in (self.btn_min, self.btn_max, self.btn_close):
        btn.hide()
```

并且需要用 `QMainWindow` + `setUnifiedTitleAndToolBarOnMac(True)` 才能拿到 macOS 风格的紧凑标题栏 — 但这要重构整个 `MainWindow` 继承体系。

**Icon（[L244](native_app/window.py#L244)）：**

```python
icon_dir = Path(__file__).parent / 'resources'
for name in ('icon.icns', 'icon.png', 'icon.ico'):
    candidate = icon_dir / name
    if candidate.exists():
        self.setWindowIcon(QIcon(str(candidate)))
        break
```

但更应该的是修源：在 `resources/` 里同时放 `icon.png`（512×512）和 `icon.icns`（macOS bundle 用），打包 spec 按平台分发。

---

## 6. `native_app/storage/_state.py` — `os.replace` 退避

### (1) 现在 Windows 上是怎么做的

`save_state` 走 "tmp 写 → `os.replace(tmp, target)`" 原子重命名。Windows 上偶发 AV / OneDrive / 杀软扫描临时锁文件导致 `PermissionError`，所以加了 4 次重试（间隔 0 / 50 / 150 / 400 ms），全失败时回退直接 `target.write_text`（牺牲原子性保数据）。

### (2) 平台特定调用精确行号

| 行号 | 内容 | 性质 |
|------|------|------|
| [_state.py:30-31](native_app/storage/_state.py#L30) | 注释明确说 "Windows: settings.json may be transiently locked by AV / sync tools." | 文档；macOS 上不存在该问题 |
| [_state.py:33](native_app/storage/_state.py#L33) | `for delay in (0, 0.05, 0.15, 0.4)` 四次重试 | 在 macOS 上一次就成功，循环立即退出，**无副作用** |
| [_state.py:39](native_app/storage/_state.py#L39) | `except PermissionError as exc` | macOS 上 rename 不会抛 PermissionError（除非真的没权限），这种情况下重试也救不了，落到 fallback 直写 |

### (3) macOS 怎么写

**不需要改代码逻辑。** 现在的实现在 macOS 上行为正确：第一次 `os.replace` 就成功，循环退出。仅建议把注释更通用化：

```python
# _state.py:30-31
# Atomic rename can transiently fail under file-locking edge cases
# (e.g. Windows AV / OneDrive scans). Retry briefly before falling
# back to a non-atomic direct write that at least preserves the data.
```

POSIX `rename(2)` 是原子的，macOS 上 iCloud Drive 也不会锁文件 — 重试机制是 dead code 但保留无害。

---

## 7. `native_app/error_reporting.py` — `runtime_mode()` 与文件夹打开

### (1) 现在 Windows 上是怎么做的

`runtime_mode()` 单纯返回 `'dist'` if `sys.frozen` else `'source'` — 跨平台 PyInstaller 都这样。错误报告对话框里"打开报告目录"按钮调 `_open_report_directory`，先 `QDesktopServices.openUrl(QUrl.fromLocalFile(...))`，失败则 `os.startfile(...)`（仅 Windows 有此函数）。

### (2) 平台特定调用精确行号

| 行号 | 内容 | 性质 |
|------|------|------|
| [error_reporting.py:62](native_app/error_reporting.py#L62) | `runtime_mode()` 用 `getattr(sys, 'frozen', False)` | 跨平台，PyInstaller 在 macOS 也设此属性 — **无需改** |
| [error_reporting.py:255-265](native_app/error_reporting.py#L255) | `_open_report_directory`：先 `QDesktopServices.openUrl`，失败 fallback `os.startfile` | `os.startfile` 仅 Windows，已用 `hasattr` 守卫；macOS 上 `QDesktopServices` 工作正常，但补一条 `open` fallback 更稳 |

### (3) macOS 怎么写

**`runtime_mode()` 不动。**

```python
# error_reporting.py:255 — 给 _open_report_directory 加 macOS fallback
import subprocess

def _open_report_directory(path: Path) -> None:
    try:
        if QDesktopServices.openUrl(QUrl.fromLocalFile(str(path))):
            return
    except Exception:
        pass
    if sys.platform == "darwin":
        try:
            subprocess.run(["open", str(path)], check=False)
            return
        except OSError:
            return
    if hasattr(os, 'startfile'):
        try:
            os.startfile(str(path))
        except OSError:
            return
```

实际上 `QDesktopServices.openUrl` 在 macOS 上调 Launch Services 几乎不会失败，`subprocess.run(["open", ...])` 是 belt-and-braces。**这个改动可有可无。**

---

## 总结：每个文件的工作量

| 文件 | 改动量 | 风险 | 说明 |
|------|--------|------|------|
| `updater.py` | **大** | 高 | 资产挑选 + DMG 解压 + 替换脚本三段都要重写；建议先做 macOS 端 .zip 替换走通，再加 .dmg 支持 |
| `python_env.py` | **中** | 中 | 整段 `_setup_mac()` 用 venv 重写，逻辑比 Windows 简单（无需修补 `._pth`） |
| `tagger.py` | 极小 | 极低 | 只有一句错误信息文案需要更通用化 |
| `tagger_subprocess.py` | 极小 | 极低 | 只需把 `ort_debug.txt` 写入路径改到可写目录 |
| `window.py` | **大** | 高 | 需要决策路线 A vs B；A 需要新写一套鼠标事件 resize（约 80 行）；图标加载多格式探测 |
| `storage/_state.py` | 0 | 0 | 仅注释微调 |
| `error_reporting.py` | 极小 | 极低 | 加一条 `subprocess.run(["open", ...])` fallback（可选） |

### 决策点（需要用户确认）

1. **`updater.py`：macOS 走 .dmg 还是 .zip？** .dmg 更地道但要 `hdiutil`；.zip 最简单（直接 cp .app）
2. **`window.py`：路线 A（frameless 全自定义，~80 行 mouse event resize）/ 路线 C（推荐：NSFullSizeContentView + 透明标题栏，保留交通灯，~30 行 PyObjC + 增加 pyobjc 依赖）/ 路线 B（macOS 上完全用原生标题栏）？** 影响视觉一致性与 macOS 用户预期
3. **`python_env.py`：找不到系统 python3 时降级方案？** 提示用户 brew install？还是 fallback 下载 python-build-standalone（额外 ~30 MB）？
