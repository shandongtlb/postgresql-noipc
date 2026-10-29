# 构建与验证结果

日期：2026-10-29。以下为首次二进制包构建的历史记录，本机目录为 `/opt/postgresql-no-sysvipc`。当前仓库已迁移到上游 Git 历史和标准源码布局，辅助文件位于 `noipc/`；原有构建产物保留在上述本机目录。

## 已完成

- PostgreSQL **18.6** 原版源码已从官方站点下载，并通过官方 SHA-256 校验。
- 已重建无需 SysV IPC 的 Linux/fork 源码补丁，同时保留数据目录互斥和孤儿进程保护。
- 已完成 x86_64 原生构建、arm64 交叉构建与安装。
- 已生成可直接复制到手机 Kali chroot 的 arm64/glibc 二进制安装包。

## 实际验证

1. x86_64 原生版：在 seccomp 禁用所有 SysV 共享内存和信号量调用的条件下，**上游全部 231 项回归测试通过**。
2. x86_64 原生版：在同样限制下，**13 项项目集成检查全部通过**。
3. arm64 版：通过 QEMU user-mode/binfmt 执行真正的 arm64 可执行文件，使用 Debian 12 glibc 2.36；同样禁用 SysV IPC，**13 项项目集成检查全部通过**。
4. arm64 的手机管理脚本：以 root 调用后切换到 postgres 用户，完成 **init → start → psql → stop**；SQL 确认版本 18.6、动态共享内存为 mmap。
5. 全部 **70 个 ELF 文件** 均为 AArch64；没有 SysV IPC 函数导入；全部 ELF 所需最高 GLIBC 符号版本为 **2.34**。运行兼容基线保守定为已实际验证的 **glibc 2.36+**。
6. 补丁可干净应用于下载的原版源码，修改后的 6 个文件与实际编译源码逐字节一致。

13 项集成检查覆盖：初始化与启动、双实例拒绝、删除 PID 文件仍保持互斥、SQL 数据校验、实际启动两个并行 worker、100 笔并发 pgbench 事务零失败、dump/restore 往返、后端 SIGKILL 后重建共享内存、主进程 SIGKILL 后孤儿后端继续持锁、孤儿结束后 WAL 恢复、单用户模式互斥、三轮正常启停持久性，以及停服后的单用户访问。

`tests/deny-sysvipc` 设置的过滤器会跨 fork/exec 继承，相关调用返回 `ENOSYS`。已单独确认 shmget 和 semget 的返回值。ELF 检查同时确认产物不导入这些函数。

## 产物

- `artifacts/postgresql-18.6-linux-arm64-no-sysvipc.tar.gz`：手机运行包，解压至 `/opt`，得到 `pgsql-18-no-sysvipc/`。
- `artifacts/postgresql-18.6-no-sysvipc-source.tar.gz`：原版源码压缩包、补丁、构建脚本、测试与构建记录。
- `artifacts/SHA256SUMS`：两个压缩包的校验和。
- `BUILD-INFO.txt`：编译器、sysroot 包校验和、源码与补丁校验和、完整交叉编译参数。

## 日志

- `logs/regression-native.log`
- `logs/integration-native.log`
- `logs/integration-arm64.log`
- `logs/mobile-wrapper-arm64.log`
- `logs/arm64-elf-audit.json`
- `logs/patch-verification.log`
- `logs/configure-arm64.log`、`logs/build-arm64-final.log`、`logs/install-arm64.log`

## 验证边界

没有访问你的真实手机，arm64 验证使用 QEMU；需要手机 Kali 自己提供 glibc、Linux 文件系统上的目录 flock、mmap 与 POSIX/futex 同步支持。
不需要 SysV IPC，也不需要 `/dev/shm`。包为依赖精简构建，关闭 TLS、ICU、readline、zlib、LLVM JIT 和 liburing 等可选功能。
初次使用请创建新数据目录；已有数据库的迁移按 PostgreSQL 大版本升级规则进行。
