# 当前 APT 发布验证

当前版本、代码配方指纹、包哈希和最近的验证结果以 [latest-update.json](latest-update.json) 与 [发布状态](../packaging/published.json) 为准；这些文件在每次成功发布时覆盖更新。

采用发行版的 PostgreSQL 18 包名和精确官方版本，不加 NoIPC/日期后缀。修改过的包带 `Postgresql-Noipc: yes` 字段。沿用官方 `postgresql-common` 路径、集群维护脚本、systemd 单元与运行功能。`nocheck nodoc` 跳过包构建内测试与独立文档包，运行验收由单独的 CI 步骤执行。

验收覆盖：

- 14 个 ARM64 核心包、137 个 AArch64 ELF；全部具有 NoIPC 标记，直接导入中没有 12 类 SysV IPC 函数。详细依赖/GLIBC 需求见 `apt-deb-audit.json`。
- 17 项真实 APT 隔离策略测试：同版本实际下载来源、不同版本及未来大版本拒绝、外架构、独立扩展、公共服务包、NoIPC 源缺失时不回退。
- 7 项真实 `.deb` 安装前检查测试：拒绝未标记核心包，允许标记核心包及正常公共包/独立扩展。
- 真实 dpkg 源码/二进制版本测试：官方源码版本不变，官方 `+bN` 二进制修订保留其原始 Source 版本。
- 12 项 APT 安装验收：完整安装、官方目录与服务、TLS/SCRAM、并行查询、PL/JIT、多集群、重装/移除再安装保留数据与配置、认证源码下载。
- 13 项已安装程序集成验收：SQL、并发、备份恢复、后端崩溃、PID 文件移除、孤儿后端继续持有目录锁、WAL 恢复、单用户访问、重复启停。
- 4 项 systemd/IPC 验收：继承禁用 SysV 的过滤器、开机自动启动已有集群、实例启停/重启/重载、包维护脚本实际触发重启并保留数据。
- 真实 Git 原子发布测试：源码历史保持向前，APT 快照仅一个提交，并发旧 lease 会拒绝两个分支的更新。

另使用原先 `+noipc` 包和旧源配置的隔离安装，验证迁移到官方 `18.6-3` / `18+293` 后仍为单一集群，保留 200,000 行及其求和结果，旧 Deb822 源被正确移除，新源顺序和安装前保护生效。

## 环境与边界

x86_64 构建机通过 QEMU 运行 Kali rolling ARM64 用户空间。整个验收容器继承 seccomp 过滤器，12 类 SysV IPC 系统调用返回 ENOSYS；ARM64 Python 会实际验证共享内存、信号量及消息队列调用失败。

测试控制器采用宿主原生 systemd/执行器及其库的只读绑定，以避开 ARM64 systemd 在 QEMU 用户态仿真的重载问题。PostgreSQL、客户端、包维护脚本、集群工具及数据库模块均为 ARM64。六个基础设施单元清空 ImportCredential，设置 QEMU CPU 模型；PostgreSQL 单元不变。测试根目录移除构建专用 policy-rc.d 后，真实测试包维护脚本与服务。

这些是包、服务与故障恢复的隔离仿真结果；手机实机尚未验证。安装与定时任务操作见 [完整维护手册](../packaging/MAINTENANCE.zh-CN.md)。
