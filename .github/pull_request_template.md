## 变更说明

<!-- 做了什么、为什么 -->

## 类型

- [ ] 修复（patch）
- [ ] 新功能（minor）
- [ ] 文档 / 杂项

## 自检

- [ ] `ruff check native_app` 通过
- [ ] `pytest -q` 通过（改动逻辑层时补用例）
- [ ] `python -m native_app` 启动正常
- [ ] CHANGELOG.md 已加条目（修复/功能必填）
- [ ] UI 字符串已同步 zh-CN.json 与 en.json（涉及 UI 时）
- [ ] Windows 行为无意外改动（跨平台改动时说明验证方式）
