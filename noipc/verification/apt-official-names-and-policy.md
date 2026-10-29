# 官方包名、官方版本与默认保护

实际包名及版本采用 Kali 对应官方值；当前值见 `../packaging/manifest.json`。源配置辅助包独立编号，标准 `postgresql` / `postgresql-client` 元包依赖同一份 `postgresql-18` / `postgresql-client-18`，兼容别名不会额外安装服务端。

同版本的两份包可能在 APT 中合并为一个版本，因此优先级之外还必须保证首选下载来源及安装前校验：

- 受管理 NoIPC 源在 `/etc/apt/sources.list` 首位；公钥使用 Signed-By 限定。
- 其他版本的官方核心包优先级为 -1；NoIPC 版本优先级 1001。按源码包精确匹配核心，不误伤公共服务包和独立扩展。
- 安装前钩子拒绝缺少 `Postgresql-Noipc: yes` 的核心 `.deb`，不依赖版本号猜测。
- 包 URL 含内容哈希；同版本重新发布不复用旧 URL。普通 APT 升级用于官方版本变化，同版本重建使用 `postgresql-noipc-upgrade` 显式重装。

`apt-policy.log` 记录策略测试；`apt-install-guard.log` 记录标记校验；`apt-policy-upgrade.log` 记录从旧自定义版本迁移的实际结果。完整验收及平台限制见 `apt-verification.md` / `latest-update.json`。

默认保护不删除已有其他大版本或数据，不替代数据库跨大版本迁移。APT 分支只保留最新快照，源码分支保留官方历史。
