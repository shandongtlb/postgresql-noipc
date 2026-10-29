# 安装、日常更新与自动发布维护手册

适用范围：运行 systemd 的 Kali NetHunter **arm64 chroot**，内核没有 CONFIG_SYSVIPC。当前构建采用 Kali rolling 的完整运行功能，glibc 至少 2.43。数据库源码、包名及包版本保持上游/发行版规范，NoIPC 的区别记录在包的 `Postgresql-Noipc: yes` 字段和签名软件源中。

## 手机首次安装，或从此前的自定义版本迁移

在手机 Kali chroot 内，以 root 执行整段：

```bash
apt update
apt install -y curl ca-certificates
curl -fL \
  https://raw.githubusercontent.com/shandongtlb/postgresql-noipc/apt/postgresql-noipc-archive-keyring_all.deb \
  -o /tmp/postgresql-noipc-archive-keyring_all.deb
apt install -y /tmp/postgresql-noipc-archive-keyring_all.deb
postgresql-noipc-upgrade -y
systemctl enable --now postgresql
systemctl status postgresql@18-main --no-pager
pg_lsclusters
runuser -u postgres -- psql
```

在 psql 中输入 `\q` 退出。

`postgresql-noipc-upgrade` 内部使用 APT，安装标准的 `postgresql` / `postgresql-client` / `postgresql-18` 等包，并重新安装本源提供的已安装 PG18 核心组件。它同时处理从旧的 `+noipc` 自定义版本降到**相同官方版本号**的迁移，不删除集群和数据。首次迁移必须运行它：Kali 可能已经装了同版本官方包，仅执行普通 `apt install` 不保证将它替换成修改版。

本方案首次沿用的官方服务端版本为 **18.6-3**，两个标准元包为 **18+293**。后续版本同样直接采用 Kali 对应官方版本，当前值以 `manifest.json`、`published.json` 和 `apt-cache policy` 为准。源配置辅助包有独立版本，因为官方没有这个辅助包。此前的 `postgresql-noipc` 只作为兼容元包保留，依赖同一份服务端。

先前便携版 `/opt/pgsql-18-no-sysvipc` 的数据不会自动搬到发行版目录。需要迁移旧库时，先备份并停止便携实例，再导入新集群，避免两个实例争用端口或数据目录。

## 同版本下如何确保不会装回官方核心包

APT 偏好规则会优先选择签名 NoIPC 源，并阻止其他版本的官方核心包，包括未经适配的新大版本。**相同版本号在 APT 中可能合并为一个候选版本，不能只靠优先级判断下载来自哪里**，因此同时启用：

1. `/etc/apt/sources.list` 最前面的受管理 NoIPC 源条目，保证同版本下载优先选本源。
2. `/etc/apt/apt.conf.d/99-postgresql-noipc` 的安装前校验：没有 `Postgresql-Noipc: yes` 的 PostgreSQL 核心包不能交给 dpkg 安装。
3. 使用内容哈希作为 pool 子目录。同版本重建后的下载 URL 会变化，避免复用旧包缓存。

公共服务包 `postgresql-common`、`postgresql-client-common` 以及独立源码包构建的扩展（如 pgvector）继续由 Kali 更新。规则不自动删除已有的其他大版本，也不处理这些大版本的数据迁移。

检查版本及标记：

```bash
apt-cache policy postgresql postgresql-18 libpq5
apt-get --print-uris download postgresql-18
dpkg-query -W -f='${Package} ${Version} ${Postgresql-Noipc}\n' \
  postgresql postgresql-client postgresql-18 postgresql-client-18 libpq5
```

同版本时，`apt-cache policy` 可能同时列出两个来源；`--print-uris` 的下载地址应包含本 GitHub APT 源。上面查询的五个包都应显示 `yes`。

刚发布时若遇到 GitHub 缓存导致的 404，稍后重新执行 `apt update`，不要切回官方核心包。

恢复受管理的源顺序：

```bash
/usr/lib/postgresql-noipc/configure-source
apt update
postgresql-noipc-upgrade -y
```

不要删除公钥或安装前校验来绕过报错；先检查软件源是否可访问、源顺序是否正确、发布是否完成。

## 手机日常更新

当维护者发布了新的**官方版本号**：

```bash
apt update
apt upgrade
pg_lsclusters
systemctl status postgresql@18-main --no-pager
```

当官方版本未变，但 NoIPC 补丁、打包或构建依赖变化导致同版本重新发布：

```bash
postgresql-noipc-upgrade -y
```

这是精确沿用官方版本号的代价：同版本重建不会可靠地触发普通升级。安装过程沿用官方维护脚本，可能重启数据库，执行时间由手机使用者决定。构建机定时任务负责发布包，**不会远程操作手机或自动重启手机数据库**。

可选功能按官方包名安装，例如：

```bash
apt install postgresql-18-jit postgresql-plpython3-18 postgresql-plperl-18 postgresql-pltcl-18
```

## 官方服务与数据路径

| 内容 | 路径/命令 |
| --- | --- |
| 服务端程序 | `/usr/lib/postgresql/18/bin/` |
| 配置 | `/etc/postgresql/18/main/` |
| 数据 | `/var/lib/postgresql/18/main/` |
| 日志 | `/var/log/postgresql/postgresql-18-main.log` |
| socket | `/run/postgresql/` |
| 集群列表 | `pg_lsclusters` |
| 单实例 | `systemctl start/stop/restart/reload postgresql@18-main` |
| 汇总服务 | `systemctl enable --now postgresql` |
| 集群工具 | `pg_createcluster`、`pg_ctlcluster`、`pg_dropcluster` |

`postgresql.service` 显示 `active (exited)` 正常；运行状态看 `postgresql@18-main.service`。自启发生在 chroot 的 systemd 启动时，Android 启动 chroot 的时间由 NetHunter 决定。

## 构建机已安装的定时任务

任务名：`postgresql-noipc-update.timer` / `postgresql-noipc-update.service`。
每天 **03:30 UTC 起，随机延迟最多 15 分钟**检查一次；错过的检查在构建机恢复运行后补做。定时任务依赖本机构建环境、GitHub SSH 凭据以及本机 APT 签名私钥，构建机关机期间不能发布。

自动流程：

1. 拉取 GitHub `main` 与官方 `REL_18_STABLE`；读取经 Kali 签名验证的 Sources 索引。
2. 跟进 Kali 提供的 PostgreSQL 18 正式维护版及 Debian/Kali 打包修订（含官方的 `+bN` 二进制重建修订）。确认对应官方 Git 发布标签位于 18 稳定分支中。
3. 比较发行版版本、源码哈希和构建配方指纹。无变化就结束，不重复构建/发布。
4. 在独立 Git worktree 中合并正式发布标签。保留 NoIPC 的 mmap 和继承式目录锁实现。合并冲突会中止，等待维护者处理。
5. 从已校验的官方源码和 Debian 打包规则生成新的补丁及 `.dsc`，在 Kali arm64 构建根中构建完整运行功能包，版本号保持发行版版本。
6. 审计真实 ARM64 ELF；验证 APT 候选策略、安装前拒绝官方核心包、安装/重装、TLS、PL、JIT、并行查询、多集群、数据保留、systemd 自启及包维护脚本重启；另执行 13 项已安装程序的崩溃恢复、孤儿后端锁保护和备份恢复检查。
7. 签名 APT 仓库。仅保留当前一批包和源码、当前索引及哈希寻址数据。
8. 用 Git 原子推送同时更新 `main` 和 `apt`。`main` 正常向前提交，保留官方源码历史；`apt` 替换为**仅一个提交的当前快照**。远端发生并发变化时拒绝覆盖。

构建或测试失败、签名密钥缺失、网络异常、上游改大版本或并发发布时不会发布候选包，原有软件源保持可用。任务最新状态覆盖写入 `/var/lib/postgresql-noipc-update/last-run.json`，不按日期积累构建结果。系统 journal 保留常规任务日志。

检查、手动触发、查看日志：

```bash
systemctl list-timers postgresql-noipc-update.timer --no-pager
systemctl status postgresql-noipc-update.timer --no-pager
systemctl start postgresql-noipc-update.service
journalctl -u postgresql-noipc-update.service -n 100 --no-pager
cat /var/lib/postgresql-noipc-update/last-run.json
```

只检查、不构建、不发布：

```bash
cd /opt/postgresql-noipc
python3 noipc/packaging/update.py --check
```

同版本强制重建并通过测试后发布：

```bash
cd /opt/postgresql-noipc
python3 noipc/packaging/update.py --rebuild
```

暂停自动检查：

```bash
systemctl disable --now postgresql-noipc-update.timer
```

该命令不终止已经运行的构建。需要同时停止正在运行的任务时，另行执行 `systemctl stop postgresql-noipc-update.service`；未完成的构建不会发布，下次任务会重建隔离 worktree。

## 迁移或重建构建机

需要可运行 systemd/systemd-nspawn 的 root Linux 构建机。x86_64 通过 QEMU/binfmt 运行 arm64 构建和 PostgreSQL；测试控制器使用宿主原生 systemd，PostgreSQL 单元保持发行版原样。原生 arm64 主机不需要该 QEMU 控制器兼容措施。

```bash
apt install -y git openssh-client python3 build-essential binutils dpkg-dev \
  mmdebstrap qemu-user binfmt-support devscripts debhelper dh-exec \
  apt-utils gpg curl bzip2 xz-utils rsync systemd-container util-linux

git clone git@github.com:shandongtlb/postgresql-noipc.git /opt/postgresql-noipc
cd /opt/postgresql-noipc
git config user.name SDTLB
git config user.email 40312509+shandongtlb@users.noreply.github.com
git remote add upstream https://git.postgresql.org/git/postgresql.git
git config remote.upstream.fetch '+refs/heads/REL_18_STABLE:refs/remotes/upstream/REL_18_STABLE'
git fetch upstream
```

配置能够推送同一仓库的 SSH 凭据，并恢复**原有**签名私钥目录到 `noipc/keys-private/apt/`，权限 700。不要让迁移机器自动生成不同的密钥；手机信任的公钥指纹为：

`8404657F5B03D8A975D4572BD95D2C6AD8196DBD`

私钥只保留在构建机，不进入 Git、公开软件源或手机包。应在构建机之外安全备份私钥和 SSH 凭据；当前签名密钥有效期到 2028-10-28，届时应先完成续期/公钥更新再发布。

首次建立构建根和包：

```bash
PG_NOIPC_FRESH_SOURCE=1 bash noipc/packaging/build-debs.sh
python3 noipc/packaging/audit-debs.py noipc/artifacts/debian-arm64
python3 noipc/packaging/create-apt-repository.py --packages noipc/artifacts/debian-arm64
python3 noipc/packaging/test-apt-policy.py noipc/repository
python3 noipc/packaging/test-install-guard.py
python3 noipc/packaging/test-update-publish.py
python3 noipc/packaging/test-packages.py \
  --rootfs noipc/build/packaging/kali-arm64-rootfs \
  --repository noipc/repository --state noipc/build/packaging/integration
bash noipc/packaging/install-update-timer.sh
python3 noipc/packaging/update.py --check
```

新机器上的 `build-debs.sh` 会引导 Kali 根目录。`nocheck nodoc` 仅跳过包构建时的测试和独立文档包；运行功能保留，集成测试由独立步骤执行。不要把这些命令放到手机数据库运行根目录里。

`manifest.json` 的 `noipc_version` 是遗留字段名，值必须与 `debian_version` 完全相同，不能加 NoIPC 或日期后缀；`binary_version` 另行记录官方二进制版本，允许官方已有的 `+bN` 后缀；`metapackage_version` 采用 Kali 对应的标准元包版本。

## 上游合并冲突或打包变化时

先停用 timer，再查看隔离 worktree 和日志：

```bash
systemctl disable --now postgresql-noipc-update.timer
git -C /var/lib/postgresql-noipc-update/worktree status
journalctl -u postgresql-noipc-update.service -n 200 --no-pager
```

下一次任务会重建这个临时 worktree，需参考的冲突改动先复制出来。在主源码 checkout 中正常拉取 `main`、合并对应 `REL_18_*` 标签并解决冲突，验证后推送，再运行 `update.py --rebuild`。每次发布会从当前 Git 相对该正式标签的差异生成 NoIPC 补丁，准备后的六个功能文件必须与 Git 一致。

如果 Kali 默认元包已经切到 19，自动任务会停止，让维护者明确选择后续策略；不会自动跨大版本迁移数据库。源码仍可跟踪 PostgreSQL 18 的维护分支。

修改构建流程/源配置辅助包后，记得在构建机上 `git pull --ff-only` 更新定时任务使用的程序；更改辅助包内容时递增其自身版本；定时任务检测到辅助包字节变化时会自动递增它的独立版本。修改当前源配置辅助包与官方 PG 版本无关。任务的配方指纹会检测代码变化；同版本重建后提醒手机端运行 `postgresql-noipc-upgrade`。

## 发布保留策略与验证边界

APT 分支只有最新快照；旧 `.deb`、旧源码压缩包及旧索引从当前快照删除。不覆盖源码 `main` 的官方 Git 历史。同版本重建保持官方版本号，pool 路径用内容哈希区分新包；手机需要显式重装，不能依靠版本号猜测代码变化。

最新发布状态和审计见 `noipc/packaging/published.json`、`noipc/verification/latest-update.json` 及 `apt-deb-audit.json`。仿真测试不等于手机实机测试；手机安装后请用 `pg_lsclusters` 和实例服务状态确认。

规则参考：[PostgreSQL 正式版本与维护策略](https://www.postgresql.org/support/versioning/)、[APT 同版本选源与偏好规则](https://manpages.debian.org/unstable/apt/apt_preferences.5.en.html)、[systemd.timer](https://www.freedesktop.org/software/systemd/man/latest/systemd.timer.html)。
