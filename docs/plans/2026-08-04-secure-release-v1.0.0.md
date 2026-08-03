# Secure Release v1.0.0 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 通过安全、兼容、供应链和真实项目发布门，将 test-assistant Python CLI 发布为可公开安装的 v1.0.0。

**Architecture:** CI 将测试、wheel 消费、静态安全、依赖/密钥扫描和产物证明分离；发布只接受已经在矩阵中验证的不可变 wheel，并使用 PyPI Trusted Publishing。真实项目仅保存脱敏验收摘要，不进入公开仓库或默认 CI。

**Tech Stack:** GitHub Actions、PyPI Trusted Publishing、pip-audit、Bandit/Semgrep（二选一后锁定）、gitleaks、CycloneDX/SPDX、Python packaging。

---

### Task 1: 明确支持与威胁模型

**Files:** Create `SECURITY.md`, `docs/security-model.md`; modify README。

记录受信任/不受信任输入、子进程与文件系统边界、Git/网络权限、Prompt 注入边界、支持平台、漏洞报告方式和不支持范围。

### Task 2: 自动安全门

**Files:** Modify `.github/workflows/ci.yml`; create security configuration and regression fixtures。

增加依赖漏洞、密钥和 Python SAST 扫描；规则必须锁定版本、记录例外理由并用安全 fixture 验证。扫描不得上传目标项目源码到第三方服务。

### Task 3: 发布产物消费矩阵

**Files:** Create `.github/workflows/release.yml`; modify packaging metadata。

构建一次 wheel/sdist，后续 job 只消费该产物；在受支持平台安装并运行 `--version`、`doctor`、fixture triage/audit。校验 wheel 内容不含测试秘密、绝对路径、临时文件和开发配置。

### Task 4: SBOM、hash 与 provenance

为发布产物生成 SHA-256、SBOM 和 GitHub artifact attestation；文档说明用户如何校验。任何重建 tag 不得静默替换已发布 PyPI 文件。

### Task 5: PyPI Trusted Publishing

**Files:** Modify release workflow and `pyproject.toml`; create `docs/releasing.md`。

使用受保护 GitHub Environment 和 OIDC 发布，不保存长期 PyPI token。先 TestPyPI smoke，再由版本 tag 触发正式发布；同版本已存在时硬失败。

### Task 6: 项目治理与包元数据

**Files:** Create `LICENSE`, `CHANGELOG.md`, `CONTRIBUTING.md`; modify `pyproject.toml`, README。

补齐 readme、license、classifiers、主页、源码、issue tracker、支持 Python 和发布说明。许可证必须由维护者显式选择，不代替维护者做法律决定。

### Task 7: 真实项目回归矩阵

维护若干脱敏 fixture 加至少两个经授权的真实项目只读验收。验证绿色套件、失败套件、无 Git、工具缺失和中断恢复；只提交命令、版本、计数和脱敏摘要。

### Task 8: v1.0 发布演练

从候选 tag 完成构建、矩阵、安全门、TestPyPI 安装、回滚演练和正式 PyPI 安装。所有命令与人工审批点记录在发布清单中。

## 完成标准

- 支持矩阵、威胁模型、安全例外和漏洞报告渠道公开；
- wheel 是唯一被测试和发布的产物，具备 hash、SBOM 和 provenance；
- PyPI 发布无长期 token、不可覆盖同版本且可从干净环境安装；
- 全部安全门、真实项目回归和恢复演练通过；
- Web、watch、Vitest 或 Agent 扩展不阻塞 v1.0。

