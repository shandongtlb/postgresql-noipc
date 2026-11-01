# PostgreSQL NoIPC：AI 接手说明

本文件适用于整个仓库。先读本文件，再按任务查阅
[完整维护手册](noipc/packaging/MAINTENANCE.zh-CN.md)。当前版本、构建类型和测试结果以
`noipc/packaging/manifest.json`、`noipc/packaging/published.json` 和
`noipc/verification/` 为准，不要把本文或旧会话中的版本号当成最新状态。

## 项目目标与实现

- 在缺少 `CONFIG_SYSVIPC` 的 Android 内核上，为运行 systemd 的 Kali NetHunter
  **arm64 chroot** 提供 PostgreSQL 18 的完整运行功能包。
- 根目录是有官方 Git 历史的 PostgreSQL 源码；`noipc/` 是本项目的脚本、打包和验证记录。
  `origin` 为 `git@github.com:shandongtlb/postgresql-noipc.git`，
  `upstream` 为 `https://git.postgresql.org/git/postgresql.git`。
- 核心实现是匿名 mmap 主共享内存、默认文件 mmap 动态共享内存，以及随 fork 继承的
  目录 inode flock。修复时保留孤儿后端仍存活时对数据目录的保护。
- 六个功能文件：`src/backend/port/sysv_shmem.c`、
  `src/backend/utils/init/miscinit.c`、`src/backend/utils/misc/guc_tables.c`、
  `src/bin/initdb/initdb.c`、`src/include/storage/dsm_impl.h`、
  `src/include/storage/pg_shmem.h`。超出这六个文件的源码变更需要同步审查打包配方；
  `prepare-debian-source.py` 会拒绝未纳入配方的上游差异。
- 保留发行版包名、路径、维护脚本、`postgresql-common` 和官方 systemd 单元，
  以及 TLS、ICU、JIT、Python/Perl/Tcl 等运行功能。

## 本机构建与发布目录

以下绝对路径描述当前构建机；迁移机器时按完整手册恢复环境，先核实实际路径。

| 路径 | 用途 |
| --- | --- |
| `/opt/postgresql-noipc` | 主源码 checkout，定时服务从这里执行更新程序 |
| `noipc/packaging/` | 正式 APT 打包、更新、签名和测试入口 |
| `noipc/repository/` | 手动生成/检出的 APT 仓库；本机另有独立 Git 仓库，分支为 `apt` |
| `noipc/build/packaging/kali-arm64-rootfs/` | 隔离的 Kali arm64 构建根，不是手机数据库 |
| `noipc/artifacts/debian-arm64/` | 手动构建的默认产物目录 |
| `noipc/keys-private/apt/` | 本机 APT 签名私钥目录，已被 Git 忽略 |
| `/var/lib/postgresql-noipc-update/` | 定时任务状态目录，含 `last-run.json` 和 `run.lock` |
| `/var/lib/postgresql-noipc-update/worktree/` | 临时源码 worktree，下次任务可能强制重建 |
| `/var/lib/postgresql-noipc-update/artifacts/` | 自动任务的候选包 |
| `/var/lib/postgresql-noipc-update/repository/` | 自动任务生成的候选 APT 仓库 |

自动发布不自动刷新 `noipc/repository/` 的独立 checkout；判断线上版本以远端 `apt`
及 `origin/main` 中的 `published.json` 为准。主 checkout 也可能落后于自动发布后的
`origin/main`，先检查工作区，再按需 `git pull --ff-only`。

旧的 `/opt/postgresql-no-sysvipc` 已清理，其提交历史已保存在当前仓库中，无需恢复。
不要因为目录看起来重复就删除签名密钥、活动构建根、测试集群或 worktree；
先查服务、进程、挂载和 `git worktree list`。

## 接手时先查看

```bash
cd /opt/postgresql-noipc
git status --short --branch
git remote -v
git worktree list
systemctl list-timers postgresql-noipc-update.timer --no-pager
systemctl status postgresql-noipc-update.service --no-pager
cat /var/lib/postgresql-noipc-update/last-run.json
journalctl -u postgresql-noipc-update.service -n 100 --no-pager
```

服务是 oneshot，执行完显示 `inactive` 可以正常；结合最近运行结果、日志和 timer
判断。`last-run.json` 是运行状态，仓库里的验证记录是某次发布的证明，两者时间可以不同。
新克隆不自带 systemd 服务、构建根或私钥。

## 更新与发布规则

现有自动化在**本机构建机**运行，每日 03:30 UTC 起随机延迟最多 15 分钟。
目前没有 GitHub Actions 发布流程；用户此前决定暂不迁移，不要顺手新建 workflow
或停用现有 timer。构建机不远程给手机安装更新。

统一入口是 `noipc/packaging/update.py`：

```bash
# 检查更新；会更新构建根的 APT 索引，不编译、不发布
python3 noipc/packaging/update.py --check
# 立即运行现有完整更新服务；无变化则结束
systemctl start postgresql-noipc-update.service
# 需要重编译并发布时才使用；会递增包修订号
python3 noipc/packaging/update.py --rebuild
```

更新程序从 **GitHub 的 `origin/main`** 建立临时 worktree，不会采用主 checkout
里尚未提交/推送的修改。修改后先执行相应验证并提交推送；修改更新程序时还要确保
本机主 checkout 已更新，因为 systemd 从这里启动脚本。检查/构建使用状态锁，
不要并行手工编辑任务的临时 worktree。

发布必须保持：

1. 依据经 Kali 签名验证的源码、二进制和元包索引，合并与 Kali 源码对应的 PostgreSQL
   **正式发布标签**。`REL_18_STABLE` 用来跟踪和验证标签；不要把未正式发布的分支
   HEAD 或 `master` 直接纳入发布配方。跨大版本须另行适配和迁移，不能自动升级数据库。
2. PostgreSQL 上游版本不变，Debian 包增加 `+noipcN`；`noipc_revision` 全局递增，
   新上游版本也不重置。二进制包及元包都必须比上次版本大；细节由 `versions.py` 管理。
   不要复用同版本覆盖新包，也不要依赖清理 APT 缓存来实现升级。
3. 保留 NoIPC 源优先级、官方核心包屏蔽及安装前 `Postgresql-Noipc: yes` 校验。
   公共服务包和独立扩展仍从 Kali 更新。手机正常使用 `apt update && apt dist-upgrade`。
4. 使用现有 APT 签名密钥，公钥指纹为
   `8404657F5B03D8A975D4572BD95D2C6AD8196DBD`；不要自动换钥，
   不输出或提交私钥、SSH 凭据。密钥续期、备份和迁移见完整手册。
5. 编译、ELF 审计、APT、数据保留、崩溃恢复和 systemd/禁用 IPC 测试全部通过才发布。
   冲突、测试失败或并发推送失败时保留原线上仓库，先处理原因，不绕过检查。
6. `main` 保留官方源码及项目提交历史，正常向前提交；`apt` 只保留最新包、源码包
   和索引，生成一个根提交替换旧快照。使用 `update.py` 的原子推送和明确的旧引用
   lease，同时更新两条分支。不要用无条件强推或 `git push --mirror` 代替。

## APT 元数据与验证

APT 仓库根目录包含：

- `dists/stable/Release`、`InRelease`、`Release.gpg`：仓库说明、校验值和签名。
- `dists/stable/main/binary-arm64/Packages{,.gz,.xz}`：二进制包索引。
- `dists/stable/main/source/Sources{,.gz,.xz}`：源码包索引。
- `pool/`：按内容哈希目录保存当前安装包和源码包。
- 根目录 `postgresql-noipc-archive-keyring_all.deb`：手机首次添加源的引导包。

线上仓库根地址为 `https://raw.githubusercontent.com/shandongtlb/postgresql-noipc/apt/`。
这些文件由 `create-apt-repository.py` 生成和签名，不手工改索引或签名。

构建与测试的完整命令见维护手册。按改动运行相关现有测试，发布时执行完整流程。
原生或 QEMU 测试不能写成手机实机验证。当前发布的构建类型查
`noipc/verification/package-revision-provenance.json`；只改包修订不能声称重新编译了 C 源码。

`noipc/build.sh`、`build-arm64.sh` 和旧便携版说明记录另一套精简构建，不能代替正式
APT 完整功能包的验证。维护流程、路径或约束变化时，同步更新本文及完整维护手册。
