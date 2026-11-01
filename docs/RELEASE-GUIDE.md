# 抖音作品提取：新 Windows 电脑接手与发布指南

本指南针对仓库 [`nmrsz645-bit/douyin-works-extractor-desktop`](https://github.com/nmrsz645-bit/douyin-works-extractor-desktop)。
截至 2026-11-01，正式版为 **v1.1.22**；`main` 是后续维护源码，`v1.1.22` 标签指向
`f56424a9434bb3ee305d4e05fac36c46c81b453b`。标签后的文档提交不会改变既有安装包。
新电脑 Codex 先从 [00-READ-FIRST](../00-READ-FIRST.md) 进入，再读 [README](../README.md) 的用户操作和
[HANDOFF](../HANDOFF.md) 的模块/已知问题，然后执行本指南。
跨项目下载站的公共边界见[网站](https://github.com/nmrsz645-bit/software-download-center/blob/docs-cross-pc-handoff/docs/PUBLISHING.md#website)、
[卡片与 catalog](https://github.com/nmrsz645-bit/software-download-center/blob/docs-cross-pc-handoff/docs/PUBLISHING.md#catalog)、
[客户端更新](https://github.com/nmrsz645-bit/software-download-center/blob/docs-cross-pc-handoff/docs/PUBLISHING.md#client-update)、
[验收与回滚](https://github.com/nmrsz645-bit/software-download-center/blob/docs-cross-pc-handoff/docs/PUBLISHING.md#verify-rollback)和
[凭证](https://github.com/nmrsz645-bit/software-download-center/blob/docs-cross-pc-handoff/docs/PUBLISHING.md#credentials)。本项目的对象、命令和限制以下文为准。

> 本文件是**未来发布操作手册**。隔离候选的安全副本已存入非 `v*` 的备份预发布；没有构建新的正式版本、替换正式 Release、上传 OSS、改下载站或执行生产上传命令。`git push` 文档提交和备份预发布都不等于客户端已更新。

## 1. 仓库、正式版和测试版

只向上述用户仓库的 `origin` 推送；仓库内另有第三方 `upstream`，不得向它推送。新电脑用 PowerShell：

```powershell
git clone https://github.com/nmrsz645-bit/douyin-works-extractor-desktop.git
Set-Location .\douyin-works-extractor-desktop
git switch main
git pull --ff-only origin main
git status --short
git log -1 --format="%H %s"
Get-Content .\version.json
```

`main` 是维护分支；有意发布的 `v*` 标签和 GitHub Release 才是正式版。测试改动用独立分支与隔离安装目录，
本仓库没有独立的测试版自动更新清单，也没有已验证的“测试版推送给所有用户”流程。
要检查 **v1.1.22 原始发布源码**可 `git switch --detach v1.1.22`，但该旧标签不含后来补充的文档；
继续开发应回到 `main`，不要移动旧标签。当前 GitHub Release 有完整包和更新包；源码根目录的 `dist/` 不是发布证明。

## 2. 新电脑环境、启动与数据边界

开发/构建使用 Windows x64、Python **3.10**（本轮本机为 3.10.11；CI 为 `actions/setup-python` 的 3.10）、Git、PowerShell 7
（下文完整组包命令按 CI 的 `pwsh` 写法）。打包界面还依赖目标电脑安装 **Microsoft .NET Framework 4.8.1 或更高版本**；
它不是 ZIP 中的可分发 CoreCLR。新用户只需完整 ZIP 和该系统运行时，按 README 运行包根目录 `Start-App.cmd`，无需 Python。

源码 `requirements.txt` 只给最低版本，**没有带 wheel SHA-256 的依赖锁文件，不能保证在新电脑按范围安装后生成与旧 ZIP 位一致的包**。
本轮可核对的本机直接依赖版本为：Playwright 1.63.0、PyYAML 6.0.3、FastAPI 0.141.1、Uvicorn 0.53.0、
Jinja2 3.1.6、requests 2.34.2、zhconv 1.4.3、openpyxl 3.1.5、python-multipart 0.0.32、
pywebview 6.2.1、PyInstaller 6.22.3、pytest 9.1.1。旧本机 `.venv` 未装 `faster-whisper`；
v1.1.22 的 [CI 构建日志](https://github.com/nmrsz645-bit/douyin-works-extractor-desktop/actions/runs/35972034374)
安装了 `faster-whisper 1.2.1`。该次 CI 解析出的 63 个包及预装的 `setuptools 65.5.0` 记在
[构建版本约束](ci-v1.1.22-build-constraints.txt)；它是版本记录，**不是 wheel 哈希锁或新版本通用约束**。
交接时保存新环境的 `pip freeze` 和浏览器目录清单，再判断是否可发布。

在**新建的源码检出目录**安装并做离线检查：

```powershell
py -3.10 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --index-url https://pypi.org/simple --upgrade pip
.\.venv\Scripts\python.exe -m pip install --index-url https://pypi.org/simple -r requirements.txt pyinstaller -c docs\ci-v1.1.22-build-constraints.txt
.\.venv\Scripts\python.exe -m pip install --index-url https://pypi.org/simple pytest==9.1.1
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m playwright install chromium
.\.venv\Scripts\python.exe -m pytest -q
```

2026-10-31 在另建的隔离 Windows/Python 3.10.11 环境中，按上述构建版本约束安装后，
`pip check` 通过，`WhisperModel`、CTranslate2 4.8.2、PyAV 17.1.0、ONNX Runtime 1.23.2 和 tokenizers 0.23.2 可导入；
离线测试为 `16 passed, 4 skipped`。PyInstaller 最小 onedir 构建完成，归档含 `faster_whisper`，
输出含 `ctranslate2.dll` 和 ONNX Runtime 扩展。安装命令指定官方 PyPI 索引，但 pip 使用了本机缓存中的多个 wheel，
没有逐个验证 wheel 的来源/哈希。最小 onedir 构建没有捆绑 Chromium；后续用本机已匹配的浏览器组件
组装了完整候选并直启 EXE 做隔离的本地页面检查，见下文。**没有下载语音模型或执行真实转录**。
`test_web.py` 的 4 个服务冒烟项本身被标记跳过。
开发启动用独立资料目录，避免碰当前用户的正式数据：

```powershell
$env:PLAYWRIGHT_BROWSERS_PATH = Join-Path $env:LOCALAPPDATA 'ms-playwright'
$env:LOCALAPPDATA = Join-Path $env:TEMP 'dwe-dev-profile'
.\.venv\Scripts\python.exe desktop_app.py
```

上面两个环境变量只对当前 PowerShell 会话及其子进程生效。源码的 `Start-App.cmd` 因没有发布包 `app/` 而不能用作开发入口。
`build_desktop_release.bat` 只生成 `dist/抖音作品提取/`，并且会删除当前检出目录的 `build/`、`dist/`；
脚本按固定浏览器修订号 `chromium-1243`、`chromium_headless_shell-1243`、`ffmpeg-1011` 复制，升级 Playwright 后必须重新核对。

| 路径/对象 | 新电脑处理 |
| --- | --- |
| Git 源码、`config.example.yaml`、README/HANDOFF/本指南 | 从用户仓库重新克隆；示例无真实凭证。 |
| `%LOCALAPPDATA%\抖音作品提取\data\douyin_monitor.db` 与 `config.yaml` | 属于用户业务资料；仅在数据所有者明确同意时，退出旧程序后经私密通道备份/迁移，并先保留原件。不要提交、打包或作为交接附件。 |
| `%LOCALAPPDATA%\抖音作品提取\douyin_session\` | 浏览器登录态可能受 Windows DPAPI/用户身份绑定；不作为可分发或可跨机复用资料。新电脑由使用者重新扫码登录。 |
| `desktop.log`、安装目录 `Update-App.log`、导出文件和下载视频 | 可能含个人或业务信息；按需由所有者私下提供脱敏片段，不进入 GitHub/安装包。下载目录由用户另选。 |
| 已发布完整 ZIP/更新 ZIP | 从 GitHub Release 或已核验的公开 OSS 地址下载并验 SHA-256，不从旧电脑的运行目录直接拷贝。 |

## 3. 版本、完整包与更新包

新版本须由源码功能/修复和验收决定，不能只为改文档而改号。实际源版本在根目录 `version.json`；
`vX.Y.Z` 标签、`app/version.json`、两个 ZIP 文件名和 OSS 清单版本必须一致。
`.github/workflows/release.yml` 从 **标签名**生成 `app/version.json` 与文件名，不会自动验证根目录 `version.json` 是否相同；发布前人工比对。

下面是从现有 CI 工作流提炼的**候选包本地组包示例**，只在干净隔离检出目录、PowerShell 7 中运行，
`$version` 必须先替换为本次真实新版本。它会写本地 `dist/`、`release/`，不会上传；不要在用户安装目录运行。

```powershell
$version = (Get-Content .\version.json -Raw | ConvertFrom-Json).version
$root = "release/douyin-works-extractor-$version-windows-x64"
if (Test-Path $root) { throw "输出目录已存在，请先使用全新隔离检出目录" }
.\.venv\Scripts\pyinstaller.exe --noconfirm --clean --windowed --onedir --name "抖音作品提取" --paths . --add-data "web;web" --collect-all webview --collect-all openpyxl --collect-all multipart desktop_app.py
New-Item -ItemType Directory -Path "$root/app/ms-playwright" -Force | Out-Null
Copy-Item -Path "dist/抖音作品提取/*" -Destination "$root/app" -Recurse -Force
$browserSource = Join-Path $env:LOCALAPPDATA 'ms-playwright'
Get-ChildItem -LiteralPath $browserSource -Directory |
  Where-Object { $_.Name -match '^(chromium|chromium_headless_shell|ffmpeg)-' } |
  Copy-Item -Destination "$root/app/ms-playwright" -Recurse -Force
Copy-Item .\version.json "$root/app/version.json"
Copy-Item .\Start-App.cmd "$root/Start-App.cmd"
Copy-Item .\Update-App.ps1 "$root/Update-App.ps1"
Compress-Archive -LiteralPath "$root/app" -DestinationPath 'release/app.zip'
Compress-Archive -LiteralPath $root -DestinationPath "$root.zip"
```

检查 `app/抖音作品提取.exe`、`app/version.json`、Chromium/无头 Chromium/ffmpeg 目录、根目录两个脚本确实在 ZIP 内；
不能只看到压缩成功就称“完整包可运行”。`release/app.zip` 是含顶层 `app/` 的更新包；`$root.zip` 是新用户完整包。
正式 CI 同样组包，并把待上传文件保存为 Actions artifact `douyin-works-extractor-oss-vX.Y.Z`。

现有本地整理脚本的参数**已核对源码**，示例只做本地复制、哈希与清单生成：

```powershell
$stage = ".\oss-upload-$version"
if (Test-Path $stage) { throw "待上传目录已存在" }
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\Prepare-DomesticRelease.ps1 `
  -Version $version -UpdatePackage .\release\app.zip `
  -UpdatePackageName "douyin-works-extractor-update-$version.zip" `
  -FullPackage "$root.zip" -OutputDirectory $stage
.\.venv\Scripts\python.exe .\scripts\publish_oss_release.py --directory "$stage\updates" --dry-run
Get-FileHash "$stage\updates\douyin-works-extractor-$version-windows-x64.zip" -Algorithm SHA256
Get-FileHash "$stage\updates\douyin-works-extractor-update-$version.zip" -Algorithm SHA256
```

`--dry-run` 只校验待上传文件与清单，不触网写 OSS。必须另外检查 ZIP 内是否有 `.env`、Cookie、
浏览器资料、数据库、日志、个人资料或真实配置，并在独立用户数据目录做启动检查。

### 2026-10-31 本机隔离完整候选（原件未发布）

Playwright 1.63.0 的 `browsers.json` 要求 Chromium `1243`、headless shell `1243`、ffmpeg `1011`。
本机标准 `%LOCALAPPDATA%\ms-playwright` 缓存有这三个目录及安装完成标记；三个核心 EXE 的 SHA-256
分别与已解压的 v1.1.22 正式完整包相同。只复制这三个浏览器组件目录，不复制 `.links`、浏览器用户资料、
登录态、业务数据或旧安装目录。候选程序沿用上文隔离 PyInstaller 产物，另拷贝启动/更新脚本与
`app/version.json`，输出在本机 `C:\软件\作品提取-handoff-build\full-candidate-v1.1.22`。

| 本机候选 ZIP | 大小 | SHA-256 |
| --- | ---: | --- |
| `candidate-app-update.zip` | 478942737 字节 | `a6d8f033bd5ec7f7f812c5c380cbf60bf9e9a5c5d38e5d24c01fd7d6ae6df8a4` |
| `candidate-full-package.zip` | 479138485 字节 | `e4e8cf71abd4c0b97cbaf7dd67a5350469cb67ece1e75506236829dd063232cc` |

两份 ZIP 的 `app/version.json` 均为 1.1.22；完整包含 `Start-App.cmd`、`Update-App.ps1`，
更新包以 `app/` 为顶层。静态校验核对了浏览器 EXE、CTranslate2、PyAV、tokenizers 和 ONNX Runtime 文件、
ZIP CRC、排除用户资料路径。运行真实 `Prepare-DomesticRelease.ps1` 时输出到独立 `prepare-output-do-not-upload`，
把 `OssBaseUrl` 设为 `https://example.invalid/handoff-only`；其本地清单哈希与两份 ZIP 一致。
候选 EXE 直接在**空隔离** `%LOCALAPPDATA%` 中启动，本地首页返回 HTTP 200，随后停止测试进程；
没有运行 `Start-App.cmd` 或检查公网更新。

**这些候选与 v1.1.22 已发布 ZIP 的字节和 SHA-256 均不同，绝不能作为同版本资产上传或覆盖 OSS。**
这次检查没有真实抖音提取、语音模型/转录、旧版升级、另一台电脑或正式用户数据验收。

原候选 ZIP 各含一个浏览器 `debug.log`，不得原样公开。仅剔除该日志、其余条目大小及 CRC 保持一致的
安全副本已上传到[备份预发布](https://github.com/nmrsz645-bit/douyin-works-extractor-desktop/releases/tag/backup-handoff-1.1.22-20261031)，
作为另一台电脑的恢复资料：完整备份 ZIP SHA-256 为
`882b07792e3a3da70dbab875863134c49444f6860b7e6b1f048d4a705980c16c`，更新备份 ZIP 为
`e5f75dea1d6ed32cd28b3c9995903eb7690c275531fcb864997e3fe9188b1272`。
GitHub 附件 digest 与这两个哈希一致；详细文件名、大小、原候选哈希见该预发布的 `BACKUP-MANIFEST.json`。
**这些附件不是正式 v1.1.22，也不得拿来替换客户端更新 ZIP 或补发给用户。**

## 4. GitHub Release、OSS 和客户端更新

现有 v1.1.22 对象（用于核对路径模式，**不能覆盖这些旧对象**）：

[备份预发布](https://github.com/nmrsz645-bit/douyin-works-extractor-desktop/releases/tag/backup-handoff-1.1.22-20261031)
是 `prerelease=true`、`latest=false` 的审阅资料；
[`backup/existing-safe-20261031`](https://github.com/nmrsz645-bit/douyin-works-extractor-desktop/tree/backup/existing-safe-20261031)
是未合入的旧 opt-in 更新器实验。它们与正式发布流程分开，不能当作新电脑给用户安装的最新版。

| 对象 | 实际位置/字段 |
| --- | --- |
| 完整版 | GitHub Release 附件 `douyin-works-extractor-1.1.22-windows-x64.zip`；OSS bucket `luotuoqiluotuozhaoma-download`、key `updates/douyin-works-extractor-1.1.22-windows-x64.zip`；SHA-256 `f478f4087b94eedd8bf2f2f28c01b4718aff03be500da63c842bd7535a6ed190`。 |
| 更新包 | GitHub Release 附件 `douyin-works-extractor-update-1.1.22.zip`；OSS key `updates/douyin-works-extractor-update-1.1.22.zip`；SHA-256 `aa1b80c3ea0db23b5ebbc0e8f18912070473224f7fc0d4c5b9e7935a7bf7382f`。 |
| 客户端清单 | `https://luotuoqiluotuozhaoma-download.oss-cn-beijing.aliyuncs.com/updates/latest.json`；字段 `version`、`url`、`sha256`、`fullPackageUrl`、`fullPackageSha256`、`fullPackageName`。 |
| 网站运行时元数据 | 同 bucket 的 `updates/latest.js`，定义 `window.DOUYIN_WORKS_EXTRACTOR_LATEST = {version, fullPackageUrl}`。 |

`Update-App.ps1` 的默认 `ManifestUrl` 是上表 JSON。`Start-App.cmd` 每次启动先同步运行它：
比较 `app/version.json` 与清单 `version`；有新版会提示用户；同意后按 JSON 的 `url` 下载更新 ZIP，
以 `sha256` 校验，并要求解压后有顶层 `app/`，再替换安装目录的 `app/`；失败写 `Update-App.log`，
启动器仍会尝试运行 `app/` 中**现存**的 EXE。替换失败后必须核对旧 `app/` 是否真的恢复，不能保证它仍可启动。
它**不从 GitHub Release 自动检查更新，也不读取网站 `latest.js`**。替换失败时脚本尝试恢复旧 `app/`，
但替换成功后才发现新程序启动失败时**没有自动回滚**；不能据此宣称旧版用户已成功升级。

`.github/workflows/release.yml` 只在推送 `v*` 标签或手动触发时运行；**推送 `main` 文档不会触发它**。
标签工作流会构建、生成两个 ZIP/清单、保存 Actions artifact，并尝试用 OIDC 临时凭证上传 OSS；
它**不会创建 GitHub Release 或上传 Release 附件**。推送正式标签会有生产 OSS 写入风险，不能当成测试按钮。
`workflow_dispatch` 也不是安全的试运行：在 `main` 上运行时脚本会把分支名当版本而失败，
在旧标签上重跑则可能重写同名 OSS 对象；不要用它测试发布权限。
v1.1.22 的 [Actions 记录](https://github.com/nmrsz645-bit/douyin-works-extractor-desktop/actions/runs/35972034374)
在配置阿里云临时凭证时因 `AuthenticationFail.OIDCToken.PublicKeyFingerprintMismatch` 失败；
公开 v1.1.22 OSS 对象后来可访问，但本轮未验证云端 OIDC 设置是否修复。下一次须先核对此故障和可回退入口。

未来**经单独生产授权**的顺序：确认构建提交与版本 → 离线测试/包布局/敏感信息扫描 →
先上传并从公网回下载核验不可变完整包和更新包 → 最后切换 `latest.json`、`latest.js` →
在 GitHub 创建同标签 Release 并上传同哈希两个 ZIP → 检查网站卡片与隔离旧版升级。
现有标签工作流会自行完成 OSS ZIP 与清单发布，可能早于手工 GitHub Release；在未调整流程前，
不能声称此顺序跨平台完全原子。若 OIDC 仍失败，保留旧清单；仅由获授权操作者用受限短时 STS 凭证和已验证候选包执行手工发布。
CI 实际调用 `python scripts/publish_oss_release.py --directory oss-upload/updates`；
新电脑手工运行对应命令应使用 `.\.venv\Scripts\python.exe .\scripts\publish_oss_release.py --directory <待上传目录>\updates`
（事先安装 `oss2` 并取得短时 STS 凭证）。从前面的核验命令移除 `--dry-run` **就会写生产 OSS**；
该脚本先传两个 ZIP、做远端大小 HEAD 校验，再传 `latest.json`、`latest.js`。它不替代公网回下载哈希核验。
创建 GitHub Release 可用 `gh release create vX.Y.Z <完整ZIP> <更新ZIP> --repo nmrsz645-bit/douyin-works-extractor-desktop --verify-tag --notes-file <已审核说明文件>`；
这是未来人工步骤，本轮未执行。已有同版 Release 不应重建或覆盖附件。

## 5. 下载站卡片与 catalog 实情

网站仓库是 [`nmrsz645-bit/software-download-center`](https://github.com/nmrsz645-bit/software-download-center)，
Pages 当前从其 `main` 根目录发布 `index.html`；本项目仓库不托管网站。网站生产修改只由网站维护会话执行。
新电脑如需只读核对网站，可 `git clone https://github.com/nmrsz645-bit/software-download-center.git` 后
`git switch main` 查看 `index.html`；不要从本项目会话推送该仓库。
在其 `index.html` 中，本产品卡片的版本节点 ID 是 **`douyin-version`**，下载按钮 ID 是 **`douyin-download`**。
2026-10-31 核对时，静态兜底仍写 v1.1.10 和旧完整包 URL；页面运行时加载本产品 OSS `updates/latest.js`，
读取 `window.DOUYIN_WORKS_EXTRACTOR_LATEST.version`、`.fullPackageUrl`，只接受 2 至 4 段数字的版本和 HTTPS URL，
再改写这两个节点。因此网页显示 v1.1.22 依赖运行时脚本成功；脚本失败会退回旧静态内容。

该网站仓库当前没有供本产品读取的 `catalog.json`，`index.html` 不调用统一 catalog；
不要编造“更新仓库 catalog 脚本”。未来更新网站，应由网站维护者在其仓库 `index.html` 调整
`douyin-version`、`douyin-download` 的静态兜底及文案，并核对本产品 OSS `latest.js` 的运行时覆盖；
是否把网站分支合入 Pages `main` 是网站的独立发布动作。客户端只读 `latest.json`，网站卡片和客户端清单须分别验收。

## 6. 发布后验证与可行回滚

逐项记录**公网**而非本地结果：

1. `gh release view vX.Y.Z --repo nmrsz645-bit/douyin-works-extractor-desktop --json assets,tagName,url`，确认标签、两个附件和 GitHub 返回的 SHA-256 digest；从 GitHub/OSS 实际下载包再 `Get-FileHash`，只查 HTTP 200 不够。
2. `Invoke-RestMethod https://luotuoqiluotuozhaoma-download.oss-cn-beijing.aliyuncs.com/updates/latest.json`，核对 `version`、两条 URL、两个哈希和完整包名；再读 `latest.js`，确认它定义本项目对象且与完整包一致。
3. 在新浏览器打开 `https://download.luotuoqiluotuozhaoma.com/?verify=<随机值>`，检查卡片显示版本、下载按钮目标；再单独检查静态兜底。网站看起来新不代表客户端会更新。
4. 在**隔离的旧版完整包目录**、独立的 `LOCALAPPDATA` 测试资料下，通过旧版 `Start-App.cmd` 验证提示、选择、下载、哈希、升级后启动和测试数据未丢失；不要直接运行内部 EXE，也不要操作客户真实安装目录。
5. 若只验证了启动和本地页面，应写“未做真实抖音提取”；若没在另一台干净 Windows 机器测试，不应写“所有用户可更新”。

回滚优先在切清单前停止：旧 `latest.json`/`latest.js` 和旧 ZIP 原样保留。若清单已切换，
由获授权发布者恢复**本产品**先前核验过的清单与网站元数据，再从公网核对；不删除历史包。
对已经成功替换 `app/` 却启动失败的客户，更新器不会自动回滚：先保全安装目录、`desktop.log`、
`Update-App.log` 和用户数据，评估 SQLite 迁移兼容性后，才用已核验的旧完整包作隔离恢复。
不要清理登录资料、覆盖数据库或把其他产品的更新器当作回滚工具。

## 7. 权限、凭证与尚未验证项

GitHub 使用获授权账号的浏览器交互登录（例如 `gh auth login`），只需本仓库源码/Release 所需权限；
不改仓库可见性、不向第三方 `upstream` 推送、不强推。网站仓库权限单独由网站维护者管理。
Actions OIDC 所需仓库变量名为 `ALIYUN_OIDC_PROVIDER_ARN`、`ALIYUN_OSS_RELEASE_ROLE_ARN`；
实际值和受限角色由阿里云/GitHub 管理员在控制台核对。手工脚本只读取进程内临时 STS 环境变量
`ALIBABA_CLOUD_ACCESS_KEY_ID`、`ALIBABA_CLOUD_ACCESS_KEY_SECRET`、`ALIBABA_CLOUD_SECURITY_TOKEN`；
不要在仓库、命令行参数、聊天或日志中写它们的真实值。目标 bucket 只应授予 `updates/` 所需最小写入/校验权限。

本轮核对 `desktop_app.py`、`web/`、三个 spider、`db.py`、启动/更新/打包/上传脚本均在 `main`，
未发现这些必需源码缺失；仓库不跟踪 PyInstaller 自动生成的 `.spec`，CI 直接传打包参数。
当前明确的缺项/限制：没有全依赖锁和跨机位一致构建证据；本地构建脚本浏览器修订号硬编码；
没有自动创建 GitHub Release 的工作流；历史 OIDC 指纹失败是否修复未核；网站静态兜底仍是 v1.1.10；
本轮未实测另一台 Windows、真实抖音提取、未来版本构建或升级。它们都不能从文档提交推断为完成。
