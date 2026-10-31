# 2026-10-31 安全源码状态备份

此分支保存旧 `codex/douyin-opt-in-updater` 工作树中尚未提交的 **opt-in 更新器实验**。复制前基准提交为 `4107c2845bdd5e0b6bc009908c06b2facf7626db`；备份时正式 `main` 为 `44caca167b2f8098d4dab91b6a645c25b0493826`。本分支从基准提交建立，未合入 `main`，也不是任何已发布安装包的源码声明。

原工作树有 6 个已跟踪文件改动和 2 个未跟踪脚本，暂存区为空。以下文件在独立克隆中按原始字节复制；SHA-256 是复制时原工作树文件的字节哈希。不同机器的 Git 换行符设置可能改变检出后的工作树字节；恢复时以本分支提交内容及基准差异为准。

| 路径 | 原状态 | 原文件 SHA-256 |
| --- | --- | --- |
| `.github/workflows/release.yml` | 已跟踪文件改动 | `3671fc597a211de0705bac17240a8c14b8615622c76cfb083c3d054b54832d20` |
| `Prepare-DomesticRelease.ps1` | 已跟踪文件改动 | `4af549cc155b93099ebe940bcf2e074ad54374f3587ebedbd4d81319d4dc301d` |
| `README.md` | 已跟踪文件改动 | `64996576fe5648b2e6e7a85546dd0a22f7dd9f9c3fc7ad0a327e6c050e05c6ea` |
| `Update-App.ps1` | 已跟踪文件改动 | `7eb4e5e3c547d0a5252391c31aea5f4fe76b7ea48a0688d6716c3c13adabe3dd` |
| `scripts/publish_oss_release.py` | 已跟踪文件改动 | `90cb671779e85d550b35f88ea3095003ec7eed9169ed2bb567deb894a799bb59` |
| `version.json` | 已跟踪文件改动 | `a240a423ec68b4873c20e25f6bf25a1add03cba280bcd9ac9bfbde0e95b18703` |
| `scripts/Update-Core.psm1` | 未跟踪脚本 | `9a1dfe5a23d53b646e468d085d00908e492947977617a0ab47381ca2f2cccf45` |
| `scripts/test-opt-in-update.ps1` | 未跟踪脚本 | `a4b4417f37a06df556f101f48eb9e84f875a2b1c759cc1022ba56a7ad3e74ace` |

用途与边界：这组文件尚未在本轮测试、构建或部署。`version.json` 的 1.1.22 只属于此实验快照，不表示正式 v1.1.22 使用 opt-in 更新器。需要恢复时，检出本备份分支并比较上述基准提交；审查后再决定是否移植，不要直接覆盖正在运行的安装。

本次没有复制 `.env`、密钥/令牌值、Cookie、浏览器会话、数据库、导出文件、下载视频、运行日志、虚拟环境、模型、旧发布 ZIP 或临时验收数据。同产品版本的验证候选 ZIP 的独立备份见非 `v*` 的 `backup-handoff-1.1.22-20261031` 预发布；它也不是正式更新。

仓库工作流只在推送 `v*` 标签或手动运行时触发；本分支备份不应触发 OSS 发布。
