# Kali NetHunter arm64 APT 安装与维护

完整说明见 **[安装、更新、构建与定时发布维护手册](MAINTENANCE.zh-CN.md)**。
PG18 包名和版本号均与 Kali 对应官方包一致，精确版本见 [当前构建清单](manifest.json) 和 [发布状态](published.json)。源配置辅助包独立编号。

## 手机完整安装命令

在运行 systemd 的 Kali NetHunter arm64 chroot 内以 root 执行：

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

`postgresql-noipc-upgrade` 使用 APT，确保同版本官方包被重装为本源构建，并兼容此前 `+noipc` 版本的迁移；不会创建第二份服务端或删除已有数据。
之后新官方版本用 `apt update && apt upgrade` 更新；官方版本未变、仅本构建变化时用 `postgresql-noipc-upgrade` 显式重装。

包沿用发行版目录、维护脚本、`postgresql-common` 和 systemd 单元。包含 TLS、ICU、压缩库、LLVM/JIT、Python/Perl/Tcl 等完整运行功能。当前构建依赖 glibc >= 2.43。

## 官方包的默认屏蔽

- NoIPC 签名源被放在 `/etc/apt/sources.list` 首位。
- 偏好规则优先本源并拒绝其他版本的 PostgreSQL 核心包。
- 安装前校验拒绝没有 `Postgresql-Noipc: yes` 标记的核心包，补足同版本 APT 选源的限制。
- `postgresql-common`、客户端公共脚本及独立扩展正常从 Kali 更新。

恢复源顺序：`/usr/lib/postgresql-noipc/configure-source`。详细原理及检查命令见完整手册。

## 定时发布与保留策略

构建机的 `postgresql-noipc-update.timer` 每天 03:30 UTC 起检查正式 PG18 / Kali 打包更新，随机延迟最多 15 分钟。构建、包审计、APT 和 systemd 检查通过后，才会签名并原子推送。

`main` 保留官方 PostgreSQL 源码历史。`apt` 是仅一个 Git 提交的最新软件源快照，旧包、旧源码包和旧索引直接清除。同版本包通过内容哈希目录区分下载地址，不另加版本后缀。

```bash
systemctl list-timers postgresql-noipc-update.timer --no-pager
journalctl -u postgresql-noipc-update.service -n 100 --no-pager
cat /var/lib/postgresql-noipc-update/last-run.json
```

手动检查：`python3 noipc/packaging/update.py --check`。
同版本强制重建、测试并发布：`python3 noipc/packaging/update.py --rebuild`。
定时任务运行在构建机，手机是否安装更新及何时重启数据库仍由手机使用者决定。

签名公钥指纹：`8404657F5B03D8A975D4572BD95D2C6AD8196DBD`。
私钥留在本机 `noipc/keys-private/apt/`，不进入仓库或包。完整手册包含新构建机迁移、密钥备份、异常处理和验证边界。
