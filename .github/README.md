# PostgreSQL noipc

基于 PostgreSQL 18 官方 Git 历史的修改分支，用于未启用 `CONFIG_SYSVIPC` 的 arm64 手机 Kali chroot。

源码保持上游标准目录结构，已保留 `REL_18_6` 的完整历史；辅助脚本及验证记录位于 [`noipc/`](../noipc/)。

```bash
bash noipc/build.sh
```

以后可从官方 `upstream/REL_18_STABLE` 合并维护更新。

请阅读 [构建与同步上游说明](../noipc/README.md)。

手机使用签名 APT 源安装，并通过官方 systemd 服务管理：[NetHunter arm64 APT 安装说明](../noipc/packaging/README.md)。
