# 新电脑 Codex：从这里接手抖音作品提取

本文件是接手入口，不是发布许可。先读 [README](README.md) 了解用户如何安装和使用，再读
[HANDOFF](HANDOFF.md) 了解模块、数据和已知问题，最后按[新电脑与发布指南](docs/RELEASE-GUIDE.md)
配置开发环境或准备发布。三份文档与实时平台状态可能不同；动手前重新核对远端。

## 先分清三个对象

| 对象 | 2026-11-01 核对状态 | 用途 |
| --- | --- | --- |
| [`main`](https://github.com/nmrsz645-bit/douyin-works-extractor-desktop/tree/main) | 可维护源码；包含三页暂停/继续、作者目录下载、README/HANDOFF/发布指南。根目录 `version.json` 仍为 1.1.22。 | 继续开发；文档提交不等于新安装包。 |
| [正式 v1.1.22 Release](https://github.com/nmrsz645-bit/douyin-works-extractor-desktop/releases/tag/v1.1.22) | GitHub 的 Latest 正式版；标签源码为 `f56424a9434bb3ee305d4e05fac36c46c81b453b`。 | 新用户下载完整包；已安装用户从 `Start-App.cmd` 检查更新。 |
| [同版本备份预发布](https://github.com/nmrsz645-bit/douyin-works-extractor-desktop/releases/tag/backup-handoff-1.1.22-20261031) | 非 Latest、非客户端更新；候选包与正式 v1.1.22 字节不同。 | 仅供恢复/审阅，**不要安装给用户、覆盖正式附件或上传 OSS**。 |

另有 [`backup/existing-safe-20261031`](https://github.com/nmrsz645-bit/douyin-works-extractor-desktop/tree/backup/existing-safe-20261031)
保存旧 opt-in 更新器的未提交实验，基准提交 `4107c2845bdd5e0b6bc009908c06b2facf7626db`；
分支内的 `version.json` 写 1.1.22，**不代表正式版采用该实验**。恢复前读该分支的
[`BACKUP-SNAPSHOT-20261031.md`](https://github.com/nmrsz645-bit/douyin-works-extractor-desktop/blob/backup/existing-safe-20261031/BACKUP-SNAPSHOT-20261031.md)。

## 新电脑首次只读核对

在 Windows PowerShell 中克隆用户仓库；不要向第三方 `eric1981/douyin-monitor` 推送：

```powershell
git clone https://github.com/nmrsz645-bit/douyin-works-extractor-desktop.git
Set-Location .\douyin-works-extractor-desktop
git status --short
git log -1 --format="%H %s"
Get-Content .\version.json
gh release view --repo nmrsz645-bit/douyin-works-extractor-desktop --json tagName,isPrerelease,url
Invoke-RestMethod https://luotuoqiluotuozhaoma-download.oss-cn-beijing.aliyuncs.com/updates/latest.json
```

`gh` 需由有权使用此仓库的账号自行登录。核对 Latest Release、`version.json` 和 OSS 清单是否一致，
记录完整包与更新包的 SHA-256；**不要以备份预发布、`dist/` 或网页上的版本文字代替公网验包**。
2026-11-01 公网 `latest.json` 仍为 1.1.22，正式完整包 SHA-256 为
`f478f4087b94eedd8bf2f2f28c01b4718aff03be500da63c842bd7535a6ed190`，更新包为
`aa1b80c3ea0db23b5ebbc0e8f18912070473224f7fc0d4c5b9e7935a7bf7382f`；以后须重新读回。

## 程序与数据边界

桌面入口是 `desktop_app.py`，它启动本地 FastAPI 服务和 pywebview 窗口；页面/API 在 `web/app.py`，
作者/话题/单作品提取分别在 `spider.py`、`topic_spider.py`、`single_video_spider.py`，SQLite 在 `db.py`。
正式完整包根目录有 `Start-App.cmd`、`Update-App.ps1` 和 `app/`。源码目录没有可直接运行的 `app/`；
新用户只应解压**正式完整包**后双击包根目录的 `Start-App.cmd`。

用户数据库、配置、登录会话与日志位于 Windows 用户的 `%LOCALAPPDATA%\抖音作品提取\`，
不在 GitHub 或正式 `app/` 中。新电脑继续开发无需旧电脑的登录态；需要迁移实际用户资料时，
先正常退出程序，经用户授权和私密通道保存原件，核对后再迁移。不得把数据库、Cookie、配置、
日志、导出文件或下载视频提交仓库、放入 Release 或发在聊天中。

## 开发、构建与上传更新

开发使用 Windows x64、Python 3.10、Playwright Chromium；重现 v1.1.22 构建的依赖版本见
[`docs/ci-v1.1.22-build-constraints.txt`](docs/ci-v1.1.22-build-constraints.txt)。
从全新隔离检出目录按[发布指南第 2 节](docs/RELEASE-GUIDE.md#2-新电脑环境启动与数据边界)安装依赖、
运行离线测试，再从相应模块修改业务源码。`build_desktop_release.bat` 会删当前检出目录的 `build/`、`dist/`，
只能在隔离检出目录使用。旧版测试记录 `16 passed, 4 skipped` 不能代替新电脑的测试结果。

**发布新版本需另行确认版本、代码、验收和生产权限。**步骤在[发布指南第 3–6 节](docs/RELEASE-GUIDE.md#3-版本完整包与更新包)：
完成源码和数据兼容性检查 → 递增 `version.json` → 隔离构建完整/更新 ZIP → 检查包布局与敏感文件、计算 SHA-256 →
准备 OSS 清单并先做 `--dry-run` → 核对工作流和云端凭证状态，确认可以生产发布后才推送新 `v*` 标签 →
监控工作流及公网 ZIP/清单并回下载验哈希 → 人工创建同标签 GitHub Release、上传同哈希附件 →
单独验收下载站和旧版启动器升级。
当前 CI 不自动创建 GitHub Release；曾有 OIDC 指纹失败。网站是另一仓库，客户端读 `latest.json`，
网页读 `latest.js`。**当前工作流在成功时自行按“ZIP 先、清单后”写入 OSS**，推送标签后不能再人工决定
是否切清单；它可能先切清单再等人工 GitHub Release，不能假定发布全程原子。若需在切清单前做公网
回下载哈希验收，应先改进并验证发布工作流，或按单独获授权的手工分阶段流程执行。
不要重推旧标签、覆盖同版本 ZIP、把 `workflow_dispatch` 当成无害试运行，或用备份预发布向用户更新。

## 直接交给另一个 Codex 的提示词

> 请接手 `nmrsz645-bit/douyin-works-extractor-desktop`。先读仓库 `00-READ-FIRST.md`、`README.md`、
> `HANDOFF.md`、`docs/RELEASE-GUIDE.md`，再只读核对 `main`、正式 Latest Release、OSS `latest.json/latest.js`
> 与工作树。区分正式 v1.1.22 和 `backup-handoff-1.1.22-20261031` 备份预发布；
> `backup/existing-safe-20261031` 是未合入的旧实验。先说明你核实的版本、源码、用户数据边界和下一步，
> 再按我的新需求行动。未经新的发布授权，不推 `v*` 标签、不写 OSS/网站、不替换正式 Release；
> 保留现有数据库、登录态和原工作树改动。
