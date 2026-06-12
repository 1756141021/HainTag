# 参与开发

## 环境

```bash
git clone https://github.com/1756141021/HainTag.git
cd HainTag
python -m venv .venv
.venv\Scripts\activate          # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
```

依赖说明：`requirements.txt` 是直接依赖（README 安装路径用它）；`requirements.lock` 是 `uv pip compile pyproject.toml` 生成的完整锁定，需要可复现环境时用 `pip install -r requirements.lock`。

## 运行与调试

```bash
python -m native_app
```

打包（仅发版/用户验证时）：`python -m PyInstaller AITagGenerator.spec -y`（macOS 见 `build-macos.sh`）。

## 架构入口

- `native_app/DEV_NOTES.md` — 核心模块逐文件说明
- `ROADMAP.md` — 待办与优先级

分层约定：处理逻辑放逻辑层（logic / metadata / storage），不进 widget；数据用 dataclass，不用魔法字符串。

## 提交前自检

```bash
ruff check native_app        # 配置在 pyproject.toml
python -c "import native_app.window"
```

CI 会在 PR 上跑同样两步。

## 约定

- 版本遵循 SemVer：功能 minor、修复 patch，改 `native_app/_version.py` + 在 `CHANGELOG.md` 顶部加条目（中文，`**标题** — 描述` 格式）
- UI 字符串一律走 i18n：`resources/lang/zh-CN.json` 与 `en.json` 必须同步添加
- Windows 路径/扩展名比较一律 `.lower()`
- 注释默认不写，命名表达行为；只在代码无法表达约束时写
