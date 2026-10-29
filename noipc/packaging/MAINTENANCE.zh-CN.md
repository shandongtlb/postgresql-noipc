# 安装、日常更新与自动发布维护手册

适用范围：运行 systemd 的 Kali NetHunter **arm64 chroot**，内核没有 CONFIG_SYSVIPC。当前构建采用 Kali rolling 的完整运行功能，glibc 至少 2.43。PostgreSQL 本身的版本跟随官方（当前 18.6），包名、路径和服务沿用发行版规范；Debian 包修订号使用 `+noipcN`，让标准 APT 能识别每次重编译。包另带 `Postgresql-Noipc: yes` 标记。

## 手机添加软件源与首次安装

在手机 Kali chroot 内，以 root 执行整段：

```bash
apt update
apt install -y curl ca-certificates
curl -fL \
  https://raw.githubusercontent.com/shandongtlb/postgresql-noipc/apt/postgresql-noipc-archive-keyring_all.deb \
  -o /tmp/postgresql-noipc-archive-keyring_all.deb
apt install -y /tmp/postgresql-noipc-archive-keyring_all.deb
apt update
apt dist-upgrade
# 原来没有安装 PostgreSQL 时，再安装一次标准包：
apt install -y postgresql postgresql-client
systemctl enable --now postgresql
systemctl status postgresql@18-main --no-pager
pg_lsclusters
runuser -u postgres -- psql
```

在 psql 中输入 `\q` 退出。

添加源后，已安装的官方包、此前使用官方完整包版本的 NoIPC 构建，以及后续重编译都通过 `apt update && apt dist-upgrade` 切换/更新；不需要专用升级命令。从未安装过 PostgreSQL 的系统仍需执行一次 `apt install postgresql postgresql-client`。

当前服务端包为 **18.6-3+noipc2**，标准元包为 **18+293+noipc2**，PostgreSQL 的上游版本仍为 **18.6**。每次发布递增全局 `noipc_revision`；即使官方源码版本不变，也会产生 `+noipc3`、`+noipc4` 等新包版本。元包同样递增，避免被 APT 视为已更新而漏掉新构建。源配置辅助包使用独立日期修订。

早期试验元包曾使用 `18+noipc1`，迁移时 APT 可能显示元包降级；普通交互式 `apt dist-upgrade` 按本源优先级处理，确认清单即可。若用 `-y` 自动确认这一次旧元包迁移，需要按 APT 规则加 `--allow-downgrades`。旧的 `postgresql-noipc-upgrade` 只作为手动恢复工具保留，日常不使用。

先前便携版 `/opt/pgsql-18-no-sysvipc` 的数据不会自动搬到发行版目录。需要迁移旧库时，先备份并停止便携实例，再导入新集群，避免两个实例争用端口或数据目录。

## 如何确保不会装回官方核心包

APT 偏好规则优先选择签名 NoIPC 源，并阻止官方核心包及未经适配的新大版本。同时启用：

1. `/etc/apt/sources.list` 最前面的受管理 NoIPC 源条目，保证下载优先选本源。
2. `/etc/apt/apt.conf.d/99-postgresql-noipc` 的安装前校验：没有 `Postgresql-Noipc: yes` 的 PostgreSQL 核心包不能交给 dpkg 安装。
3. 核心包依赖源配置辅助包，确保签名源、偏好规则及安装前校验配套安装。PG 包自身的 `+noipcN` 修订号递增，APT 按正常版本比较升级，无需修改 APT 的下载缓存或在更新索引时安装软件。
4. 软件包 URL 使用内容哈希目录，每批发布有独立路径。

公共服务包 `postgresql-common`、`postgresql-client-common` 以及独立源码包构建的扩展（如 pgvector）继续由 Kali 更新。规则不自动删除已有的其他大版本，也不处理这些大版本的数据迁移。

检查版本及标记：

```bash
apt-cache policy postgresql postgresql-18 libpq5
apt-get --print-uris download postgresql-18
dpkg-query -W -f='${Package} ${Version} ${Postgresql-Noipc}\n' \
  postgresql postgresql-client postgresql-18 postgresql-client-18 libpq5
```

`apt-cache policy` 应显示带 `+noipcN` 的候选包，来自本 GitHub APT 源；`--print-uris` 的下载地址应包含本 GitHub APT 源。上面查询的五个包都应显示 `yes`。

刚发布时若遇到 GitHub 缓存导致的 404，稍后重新执行 `apt update`，不要切回官方核心包。

恢复受管理的源顺序：

```bash
/usr/lib/postgresql-noipc/configure-source
apt update
apt dist-upgrade
```

不要删除公钥或安装前校验来绕过报错；先检查软件源是否可访问、源顺序是否正确、发布是否完成。

## 手机日常更新

添加源之后，日常只需：

```bash
apt update && apt dist-upgrade
```

新官方版本、NoIPC 补丁变化，以及只更新构建依赖的重编译均使用这条命令。每次发布都有更大的包修订号，无需显式重装、手动指定来源或额外运行辅助工具。APT 正常展示升级清单并等待确认；更新成功后，再执行 `dist-upgrade` 不会重复安装当前构建。

可用以下命令先看计划及更新后的服务状态：

```bash
apt -s dist-upgrade
pg_lsclusters
systemctl status postgresql@18-main --no-pager
```

安装沿用官方维护脚本，可能重启数据库。构建机定时任务负责发布包，不远程操作手机。手动 hold 的包、未启用的源及已有依赖冲突仍遵循 APT 的正常规则。

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
5. 递增全局 NoIPC 包修订及源配置辅助包版本；从已校验的官方源码和 Debian 打包规则生成补丁及 `.dsc`，在 Kali arm64 构建根中构建完整运行功能包。PG 上游版本不改，Debian 包版本加 `+noipcN`。只有确认包版本高于上次发布才继续。
6. 审计真实 ARM64 ELF；用真实 APT 验证官方包切换、旧 NoIPC 修订更新、辅助包已更新的情况与更新后不重复安装；验证候选策略、安装前拒绝官方核心包、安装/重装、TLS、PL、JIT、并行查询、多集群、数据保留、systemd 自启及包维护脚本重启；保留上次测试安装时，还会先在其既有数据库上实际执行升级并检查数据、配置和重复升级；另执行 13 项已安装程序的崩溃恢复、孤儿后端锁保护和备份恢复检查。
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

上游版本未变时强制重建，通过测试后递增包修订发布：

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
python3 noipc/packaging/test-dist-upgrade.py noipc/repository \
  --rootfs noipc/build/packaging/integration/testroot
bash noipc/packaging/install-update-timer.sh
python3 noipc/packaging/update.py --check
```

新机器上的 `build-debs.sh` 会引导 Kali 根目录。`nocheck nodoc` 仅跳过包构建时的测试和独立文档包；运行功能保留，集成测试由独立步骤执行。不要把这些命令放到手机数据库运行根目录里。

`manifest.json` 分开记录官方和本地版本：`debian_version` 是官方源码包版本，`binary_version` 是官方 ARM64 二进制版本，`metapackage_version` 是官方元包版本。`noipc_revision` 为全局递增整数，`noipc_version` 为源码包版本（如 `18.6-3+noipc2`）。`versions.py` 生成实际二进制和元包版本；官方已有 `+bN` 时，二进制版本采用 `18.6-3+noipc2+bN`，Source 仍指向 `18.6-3+noipc2`。

`noipc_revision` 每次重编译都递增，跟进新官方版本时也不重置，确保未变的元包版本仍能持续升级。`archive_keyring_version` 是辅助包的独立日期修订；自动任务在构建前处理这些字段。`published.json` 同时记录官方版本和实际发布的 `noipc_*_version`。

## 上游合并冲突或打包变化时

先停用 timer，再查看隔离 worktree 和日志：

```bash
systemctl disable --now postgresql-noipc-update.timer
git -C /var/lib/postgresql-noipc-update/worktree status
journalctl -u postgresql-noipc-update.service -n 200 --no-pager
```

下一次任务会重建这个临时 worktree，需参考的冲突改动先复制出来。在主源码 checkout 中正常拉取 `main`、合并对应 `REL_18_*` 标签并解决冲突，验证后推送，再运行 `update.py --rebuild`。每次发布会从当前 Git 相对该正式标签的差异生成 NoIPC 补丁，准备后的六个功能文件必须与 Git 一致。

如果 Kali 默认元包已经切到 19，自动任务会停止，让维护者明确选择后续策略；不会自动跨大版本迁移数据库。源码仍可跟踪 PostgreSQL 18 的维护分支。

修改构建流程/源配置辅助包后，记得在构建机上 `git pull --ff-only` 更新定时任务使用的程序。任务的配方指纹会检测代码变化；每次构建前递增 `noipc_revision` 和辅助包修订。手动发布另一批包时，同样更新 manifest 的版本字段并重新准备源码及包；不能只替换文件而复用旧包版本。建议统一使用 `update.py --rebuild`。

## 发布保留策略与验证边界

APT 分支只有最新快照；旧 `.deb`、旧源码压缩包及旧索引从当前快照删除。不覆盖源码 `main` 的官方 Git 历史。上游版本未变的重编译通过更大的 `+noipcN` 修订号发布，手机仍用普通 `apt dist-upgrade`。

最新发布状态和审计见 `noipc/packaging/published.json`、`noipc/verification/latest-update.json` 及 `apt-deb-audit.json`。仿真测试不等于手机实机测试；手机安装后请用 `pg_lsclusters` 和实例服务状态确认。

规则参考：[PostgreSQL 正式版本与维护策略](https://www.postgresql.org/support/versioning/)、[APT 同版本选源与偏好规则](https://manpages.debian.org/unstable/apt/apt_preferences.5.en.html)、[systemd.timer](https://www.freedesktop.org/software/systemd/man/latest/systemd.timer.html)。
