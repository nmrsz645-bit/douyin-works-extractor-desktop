# 抖音作品提取：开发与发布交接

本文件对应 **v1.1.22**。该版 Release 标签 `v1.1.22` 指向源码提交
`f56424a9434bb3ee305d4e05fac36c46c81b453b`；后续文档提交不会移动旧标签或替换旧安装包。
接手时先检查 `version.json`、远端 `main`、最新 Release 和公开更新清单，不能仅凭本文件判断未来的最新版。
新 Windows 电脑克隆、测试、组包、GitHub/OSS/下载站步骤以 [发布指南](docs/RELEASE-GUIDE.md) 为准；本文件负责架构与修改入口。

## 用途与运行架构

Windows x64 桌面程序提供作者、话题、单作品三种提取方式，并导出结果、下载可访问的视频。
`desktop_app.py` 启动 Uvicorn/FastAPI 本地服务，在随机的 `127.0.0.1` 端口用 pywebview 承载界面；
Playwright 使用持久化 Chromium 会话读取抖音页面及接口。SQLite 保存作者和结果，下载文件由用户选择位置。
抖音登录态、平台接口、频率限制和风控都会影响提取成功率；不保证每个作品均能取得播放地址或统计数据。

发布包结构为 `Start-App.cmd`、`Update-App.ps1`、`app/`。启动器同步检查 OSS `updates/latest.json`，
有新版本时提示用户，验证下载 ZIP 的 SHA-256 后只替换 `app/`，最后启动 EXE。更新检查失败时仍尝试启动现有 EXE。
**源码根目录没有 `app/`，不可把源码的 `Start-App.cmd` 当成已安装程序启动。**

运行数据在 `%LOCALAPPDATA%\抖音作品提取\`：`data\douyin_monitor.db`（SQLite/WAL）、
`douyin_session\`（登录态）、`config.yaml`、`desktop.log`。安装目录有 `Update-App.log`。
处理备份和迁移时先正常关闭程序，再复制整个用户数据目录；不要把它或导出文件提交到 GitHub。

## 目录和修改入口

| 文件 | 作用与修改入口 |
| --- | --- |
| `desktop_app.py` | 桌面入口、本地端口、数据目录、.NET Framework 检查和 pywebview 窗口。 |
| `web/app.py` | 页面/API、提取状态、导出、下载队列、作者目录和文件名。 |
| `web/templates/extract.html`、`topic.html`、`single.html` | 三个主要页面及前端提取/导出/下载流程。 |
| `web/static/extraction_pause.js`、`extraction_pause.py` | 暂停/继续按钮状态与异步检查点。 |
| `spider.py`、`topic_spider.py`、`single_video_spider.py` | Playwright 作者、话题、单作品抓取。 |
| `db.py` | SQLite 表、迁移、结果存取和顺序。修改字段必须兼容旧库。 |
| `config_manager.py`、`config.example.yaml` | 默认配置、保存和无凭证示例。 |
| `Start-App.cmd`、`Update-App.ps1` | 启动和客户端更新；仅完整版包根目录的启动器可直接运行。 |
| `build_desktop_release.bat`、`.github/workflows/release.yml` | 本地 PyInstaller 构建和标签触发的完整打包/OSS 发布。 |
| `Prepare-DomesticRelease.ps1`、`scripts/publish_oss_release.py` | 生成更新清单、核对哈希、按顺序上传 OSS。 |
| `test_extraction_pause.py`、`test_download_folders.py`、`test_web.py` | 现有离线测试与跳过的服务冒烟测试。 |

`monitor.py`/`commands.py` 等旧监控 CLI 仍在仓库，但桌面版用户入口是 `desktop_app.py`；
不要再以旧“博主监控系统”README 描述桌面版。`SKILL_CODE_AUDIT.md` 是代码审计说明，不是本交接文档。

## 开发环境、配置和命令

CI 使用 Windows、Python **3.10**；本轮本机验证环境为 Python **3.10.11**、
Playwright **1.63.0**、FastAPI **0.141.1**、Uvicorn **0.53.0**、
pywebview **6.2.1**、PyInstaller **6.22.3**、openpyxl **3.1.5**。
源码的 `requirements.txt` 采用最低版本范围，不是锁定文件；复现旧包要核对实际依赖和 Chromium 版本。
本机旧 `.venv` 未装 `faster-whisper`。v1.1.22 的 [CI 安装日志](https://github.com/nmrsz645-bit/douyin-works-extractor-desktop/actions/runs/35972034374)
记录 `faster-whisper 1.2.1`；对应构建包的 PyInstaller 归档也含该模块。2026-10-31 在另建的隔离虚拟环境中，
按 [CI 版本约束](docs/ci-v1.1.22-build-constraints.txt) 安装后，`pip check`、`WhisperModel`/二进制依赖导入、
离线测试及最小 PyInstaller 打包通过；尚未下载模型、验证真实转录或把候选包作为正式发布包运行。
打包界面需要 Windows .NET Framework **4.8.1 或更高版本**。

在干净、隔离的源码检出目录中执行（PowerShell）：

```powershell
py -3.10 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --index-url https://pypi.org/simple -r requirements.txt pyinstaller -c docs\ci-v1.1.22-build-constraints.txt
.\.venv\Scripts\python.exe -m pip install --index-url https://pypi.org/simple pytest==9.1.1
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m playwright install chromium
.\.venv\Scripts\python.exe -m pytest -q
```

以上约束用于复现 v1.1.22 的 CI 版本；开发新版本时应重新审查依赖兼容性，不要直接把旧约束当成新版本锁文件。

开发启动建议使用独立用户资料，避免读写正在使用的正式数据：

```powershell
$env:PLAYWRIGHT_BROWSERS_PATH = Join-Path $env:LOCALAPPDATA 'ms-playwright'
$env:LOCALAPPDATA = Join-Path $env:TEMP 'dwe-dev-profile'
.\.venv\Scripts\python.exe desktop_app.py
```

这只在当前 PowerShell 会话覆盖 `LOCALAPPDATA`。若开发浏览器安装在其他位置，请把
`PLAYWRIGHT_BROWSERS_PATH` 指向实际的 `ms-playwright` 目录。单独运行旧 Web/CLI 时的配置和数据路径与桌面入口不同，
不要以 CLI 测试结果推断桌面用户数据。

本地构建命令为 `./build_desktop_release.bat`（在 `cmd.exe` 中运行）。该脚本**先删除当前检出目录的
`build/` 和 `dist/`**，然后生成 `dist/抖音作品提取/抖音作品提取.exe`；请只在隔离检出目录执行。
脚本复制硬编码的 Playwright 浏览器修订号；若浏览器版本变了，先检查该脚本和完整包内容。
单独的 `dist/` 不等于可升级完整包。完整打包步骤以 `.github/workflows/release.yml` 为准：
把 `dist/` 放进 `app/`，附带浏览器、`app/version.json`、启动器与更新器，再生成完整和更新 ZIP。

## 安全配置模板与获取方式

仓库只保留 [`config.example.yaml`](config.example.yaml)；它不含真实账号、Cookie 或密钥。
桌面版无需 API Key；首次启动后通过界面“扫码登录抖音”，会话存在本机 `douyin_session/`。
作者通过界面粘贴公开主页链接，程序从链接解析 `sec_uid` 并将作者记录写入 SQLite；
可从抖音网页的作者主页复制链接。话题名/链接和作品链接也从抖音公开页面复制，不写进仓库配置。

`config.example.yaml` 的 `creators` 是旧 CLI 的可选示例，桌面版作者列表不从这里导入。
`transcriber.cookie_import_path` 默认为空；如在旧 CLI 转录流程中使用，路径必须指向使用者有权使用的本机 Cookie 文件，
且文件本身不得提交或打包。`spider`、`comments`、`transcriber`、`schedule`、`web` 等项的默认值来自
`config_manager.py`；`/settings` 路由会写入用户本机 `config.yaml`，但当前 `web/templates/base.html`
主导航没有设置页链接，普通桌面用户不会直接看到它。桌面入口固定随机本地端口，`web.host/port`
主要供旧 CLI/Web 入口使用。当前桌面作者提取把滚动次数/等待/闲置阈值固定为 `80/0/20`，
话题提取把滚动次数/闲置阈值固定为 `80/10`；修改示例配置中的这些项不会改变对应页面的行为。

发布工作流使用 GitHub OIDC 换取阿里云临时凭证；仓库变量为
`ALIYUN_OIDC_PROVIDER_ARN` 和 `ALIYUN_OSS_RELEASE_ROLE_ARN`。这些值和角色权限由仓库/云账号管理员在各自控制台维护；
本仓库不应存放访问密钥、临时 token、真实 `.env` 或业务数据。不要扩大凭证权限来处理发布失败。

## 发布和升级边界

可操作命令、对象路径、网站卡片和回滚细节统一维护在 [docs/RELEASE-GUIDE.md](docs/RELEASE-GUIDE.md)。

1. 在新功能完成并验证后，更新 `version.json`，检查源码、提交历史与发布 ZIP 中没有密钥、Cookie、会话、数据库、日志或个人资料。
2. 在隔离环境运行测试并构建完整 Windows 包；核对 `app/version.json`、EXE、浏览器、启动器和 SHA-256。
3. 正常推送源码到本仓库 `main`；**推送 `v*` 标签会触发 `.github/workflows/release.yml`，并尝试向生产 OSS 上传**。仅在获得对应发布授权、确认归属和凭证后推送标签。
4. 此工作流**不会创建 GitHub Release 或上传其附件**；需另行创建 Release、上传完整包和更新包，并核对 GitHub 附件的大小及 SHA-256。保留已有版本资产不覆盖。OSS 必须先上传不可变 ZIP，再更新 `latest.json`、`latest.js`；公开校验值要与文件一致。
5. 在独立旧版安装目录验证“启动器提示 → 下载 → 校验 → 替换 `app/` → 启动”，并确认 `%LOCALAPPDATA%` 数据未变化。

**本轮只是为 v1.1.22 补文档：不移动 `v1.1.22` 标签、不重打包、不修改 OSS 或下载站。**
v1.1.22 GitHub 完整包 SHA-256：
`f478f4087b94eedd8bf2f2f28c01b4718aff03be500da63c842bd7535a6ed190`；
更新包 SHA-256：`aa1b80c3ea0db23b5ebbc0e8f18912070473224f7fc0d4c5b9e7935a7bf7382f`。

历史发布故障：[`v1.1.22` 标签的 Actions 运行](https://github.com/nmrsz645-bit/douyin-works-extractor-desktop/actions/runs/35972034374)
在“Configure temporary Alibaba Cloud credentials”步骤失败，错误码为
`AuthenticationFail.OIDCToken.PublicKeyFingerprintMismatch`。公开的 v1.1.22 OSS 清单和包后来可访问，
但不能据此推断当前 OIDC 配置已修复；下次发布前应核对云端指纹配置，并实际检查工作流与公开对象。

## 已完成、未完成与已知问题

- 已完成：作者/话题/单作品提取；结果即时显示；XLSX 导出；按作者目录下载可访问的最高码率地址；三页提取暂停/继续。
- 暂停只在当前请求结束后的检查点生效，状态只在当前进程内；关闭程序不提供断点续跑。下载队列没有暂停按钮。
- 每次新作者提取会清空旧作者作品、快照、评论和转录结果，但保留作者资料；新话题或单作品提取各自清空同类旧结果。完整历史须在退出程序后备份整个用户数据目录；XLSX/CSV 只覆盖导出字段，不能恢复全部快照、评论和转录。
- 单作品页面按首次输入顺序显示**去重后的**链接/作品；当前 `web/app.py` 会对重复 URL 去重，数据库也按作品 ID 合并。同一链接需保留多行是尚未实现的需求。
- 抖音登录状态、验证页、接口变动或频率限制可能导致作者资料、作品详情、统计或视频地址缺失。复现时记录输入类型、时间、界面错误与 `desktop.log`，避免分享 Cookie。
- `test_web.py` 的 4 个服务冒烟测试在文件中显式跳过；本轮离线测试为 `16 passed, 4 skipped`，未做真实抖音提取。
- 本地 `build_desktop_release.bat` 的浏览器修订号硬编码；未来升级 Playwright 后需同步检查。旧 `.venv` 缺 `faster-whisper`；隔离环境只验证导入和打包，真实语音转录仍未验证。
- 缺少 `faster-whisper` 时，作者提取会跳过自动转录；手动转录路径可能把“Whisper 模型未加载”占位文字存入数据库。使用转录功能前应检查模型和依赖，不能把占位文字当识别结果。
- `/settings` 与清理浏览器缓存 API 仍存在，但主导航只链接作者、话题、单作品页，普通用户没有设置页入口；若要开放入口，先明确配置与会话清理的产品行为。

可直接复现的边界：

1. 在单作品页粘贴同一个作品链接两行并开始提取：`web/app.py` 先对 URL 去重，结果只有一行；若两个不同链接指向同一作品，`db.py` 仍按作品 ID 合并。
2. 在纯源码目录运行 `Start-App.cmd`：因缺少发布包的 `app/` 会提示文件不完整。应从完整 ZIP 解压后运行其根目录启动器；开发时运行 `desktop_app.py`。
3. 运行 `python -m pytest -q`：`test_web.py` 中 4 个用例显示 skipped，因为文件级 `pytestmark` 要求先启动旧 Web 服务且当前未解除跳过；这不代表服务端到端已验证。
4. 混合勾选有/无视频地址的作品并下载：`web/app.py` 会静默过滤无地址项，只把有地址项加入队列；全部无地址时 `/api/downloads/start` 才返回“暂无可访问的视频地址”。已取得地址在下载中失效时，该条失败并继续下一条。失败时可能留下同目录 `.part`，先检查文件是否仍被写入，再人工处理。

后续修改优先从对应模块与测试入手；数据结构变更在 `db.py` 加迁移，保留用户现有库与输入顺序；
发布前重新核对 README、此交接文档和实际版本。若线上提取异常，先取日志和最小复现，再决定是否改源码。
