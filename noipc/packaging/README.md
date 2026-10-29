# Kali arm64 的 APT 分发

目标是最新版 **Kali NetHunter arm64 chroot，且其中运行了 systemd**。此目录沿用 Debian/Kali 的 **postgresql-18 18.6-3** 官方打包规则，追加 NoIPC 补丁，生成版本 **18.6-3+noipc1**。
安装目录、包名、维护脚本和集群服务均沿用发行版规范；服务管理由手机 Kali 自己的 `postgresql-common` 提供。
这套包按当前 Kali rolling arm64 构建，包含 TLS、ICU、readline、压缩库、LLVM/JIT，以及 Python、Perl、Tcl 等官方功能。
本次构建和验证环境为 Kali 2026.3 rolling；服务端声明依赖 `libc6 (>= 2.43)`，其他依赖由 APT 一并解析。

## 手机安装

在 **arm64 手机的 Kali chroot 内**以 root 执行：

```bash
apt update
apt install -y curl ca-certificates
curl -fLO https://raw.githubusercontent.com/shandongtlb/postgresql-noipc/apt/postgresql-noipc-archive-keyring_all.deb
apt install ./postgresql-noipc-archive-keyring_all.deb
apt update
apt install postgresql-noipc
systemctl enable --now postgresql
systemctl status postgresql@18-main --no-pager
pg_lsclusters
runuser -u postgres -- psql
```

`postgresql-noipc` 是指向 18 版服务端和客户端的元包；也可以直接安装 `postgresql-18`。
首次安装由官方维护脚本创建 `18/main` 集群。已有集群时沿用发行版的保留和升级规则。
源配置包会安装公钥、Deb822 APT 源和包优先级，使后续升级继续选择 NoIPC 构建。
不要把此 APT 包与之前解压到 `/opt/pgsql-18-no-sysvipc` 的便携版同时作为同一集群运行。

官方路径和命令：

| 项目 | 路径或命令 |
| --- | --- |
| 服务端程序 | `/usr/lib/postgresql/18/bin/` |
| 配置 | `/etc/postgresql/18/main/` |
| 数据 | `/var/lib/postgresql/18/main/` |
| 日志 | `/var/log/postgresql/postgresql-18-main.log` |
| socket/PID | `/run/postgresql/` |
| 集群状态 | `pg_lsclusters` |
| 启停某个集群 | `pg_ctlcluster 18 main start` / `stop` / `restart` |
| 管理全部集群 | `service postgresql start` / `stop` / `restart` / `status` |
| 创建与删除集群 | `pg_createcluster` / `pg_dropcluster` |

## 守护与自启

你已确认 NetHunter chroot 中运行了 systemd，直接使用官方 `postgresql.service` 和 `postgresql@18-main.service`：

```bash
systemctl enable --now postgresql
systemctl restart postgresql@18-main
systemctl status postgresql@18-main --no-pager
```

`postgresql.service` 是管理全部集群的汇总服务，显示 `active (exited)` 属于正常行为；数据库实例状态看 `postgresql@18-main.service`。
启用后每次该 chroot 的 systemd 启动时自动启动数据库；Android 何时启动 chroot 仍由 NetHunter 管理。

对于其他未运行 systemd 的普通 chroot，官方 SysV 脚本仍可使用：

```bash
service postgresql start
```

只有这种没有 init 的 chroot 才需要在 Android 启动入口挂载并准备好根目录后调用，例如：

```bash
chroot /你的/Kali/根目录 /usr/sbin/service postgresql start
```

服务启动后 PostgreSQL 自己的 postmaster 在后台运行并管理后端进程。安装包不修改 Android 的开机脚本。
如果残留的 systemd 状态导致重定向，可显式运行 `pg_ctlcluster --skip-systemctl-redirect 18 main start`。

## 包与源码的构建

在有 root 权限的 Linux 构建机安装工具（x86_64 主机通过 QEMU 执行 arm64）：

```bash
apt install mmdebstrap qemu-user binfmt-support build-essential dpkg-dev \
  devscripts debhelper dh-exec apt-utils gpg curl bzip2 python3
bash noipc/packaging/build-debs.sh
```

`build-debs.sh` 创建独立的 Kali arm64 根文件系统，校验 Kali 归档公钥，下载并校验官方发布包及 Debian 补丁，追加 NoIPC 补丁，再运行正式 `dpkg-buildpackage`。
使用 `nocheck nodoc` 构建 profile 跳过打包过程中的测试和独立文档包，完整运行功能仍保留。安装包的集成测试单独执行。
输出位于 `noipc/artifacts/debian-arm64/`，包括服务端、客户端、JIT、PL 包、开发包、库包及修改后的 `.dsc` 源码包。
打包规则固定在 18.6-3；同步新上游版本后应先更新 `manifest.json`、对应补丁和构建脚本，避免发布错配的源码。

## 创建与更新签名仓库

```bash
python3 noipc/packaging/audit-debs.py noipc/artifacts/debian-arm64 > noipc/logs/packaging/deb-audit.json
python3 noipc/packaging/create-apt-repository.py --packages noipc/artifacts/debian-arm64
```

公钥指纹：`8404657F5B03D8A975D4572BD95D2C6AD8196DBD`。
公钥见 `postgresql-noipc-archive-keyring.asc`。仓库包含签名的 InRelease/Release、按内容哈希寻址的索引及 deb-src 源码包。
仓库输出位于 `noipc/repository/`，通过同一 GitHub 仓库的独立 `apt` 分支发布；无需启用 GitHub Pages。
私钥留在本机被 Git 忽略的 `noipc/keys-private/apt/`，后续更新需要继续使用并备份该目录。私钥不进入仓库或安装包。
重新发布同一包名与版本时必须保持内容一致；有源码或依赖构建变化时应递增 `+noipc` 修订号。

## 验证

`audit-debs.py` 检查真实 `.deb` 中的架构、依赖、官方集群维护脚本以及 ELF 的 SysV IPC 导入和 glibc 需求。
`test-apt-install.sh` 只在带构建标记的隔离 Kali 环境中运行，验证签名 APT 安装、官方服务、目录、TLS、并行查询、PL 语言、JIT、多集群、配置/数据保留与源码下载。
由宿主的 `deny-sysvipc` 启动整个测试，模拟未启用 CONFIG_SYSVIPC 的手机内核。
`test-systemd.sh` 进一步验证随 systemd 启动、启停/重载以及真正由包维护脚本触发的服务重启。
测试根目录须先移除仅用于构建的 `/usr/sbin/policy-rc.d`；它不进入发布包。
实际验证记录及 QEMU/systemd 测试环境限制见 [APT 验证报告](../verification/apt-verification.md)。手机实机验证仍需要在你的 chroot 内进行。
