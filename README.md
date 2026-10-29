# PostgreSQL noipc

基于 PostgreSQL **18.6** 的 Linux/fork 修改版，用于没有 `CONFIG_SYSVIPC` 的 arm64 手机 Kali chroot。
完整修改版源码在 [`src/postgresql-18.6/`](src/postgresql-18.6/)，可直接克隆后编译。

主共享内存使用匿名 mmap，动态共享内存默认使用文件 mmap，信号量采用 POSIX/futex；通过随 fork 继承的数据目录 inode flock，保护数据目录并阻止孤儿后端仍存活时启动第二个实例。

## 原生编译

在 Kali、Debian 或 Ubuntu 上安装构建依赖后执行：

```bash
sudo apt-get install build-essential bison flex bzip2 patch curl
git clone git@github.com:shandongtlb/postgresql-noipc.git
cd postgresql-noipc
bash build.sh
```

结果默认安装到仓库内的 `install/`。也可在 `src/postgresql-18.6/` 内按 PostgreSQL 的标准源码流程编译。

## arm64 交叉编译

在 x86_64 Linux 上安装上述构建依赖及 arm64 工具链后：

```bash
sudo apt-get install gcc-aarch64-linux-gnu binutils-aarch64-linux-gnu
python3 setup-sysroot.py
bash build-arm64.sh
```

产物位于 `stage-arm64/opt/pgsql-18-no-sysvipc/`。sysroot 使用经 SHA-256 校验的 Debian 12 arm64 包，运行兼容基线为已验证的 glibc 2.36。

## 已完成的验证

- 禁用 SysV 共享内存和信号量后，x86_64 原生版通过上游全部 **231 项回归测试**。
- 原生版与 arm64 QEMU 版各通过 **13 项集成检查**，覆盖并行查询、并发事务、导出导入、目录互斥、孤儿进程持锁及崩溃恢复。
- 全部 **70 个 arm64 ELF 文件** 均无 SysV IPC 函数导入。

测试源码见 [`tests/`](tests/)，本次验证记录见 [`verification/`](verification/)。尚未在真实手机上验证。
精简构建关闭 TLS、ICU、readline、zlib、LLVM JIT 与 liburing 等可选功能。修改仅支持 Linux/fork 模式。

[完整中文说明](README.zh-CN.md) · [源码补丁](postgresql-18.6-no-sysvipc.patch) · [构建参数](BUILD-INFO.txt) · [上游许可证](COPYRIGHT)

仓库保留官方发布源码快照与本项目改动两个独立提交；下载缓存、编译产物及数据库测试数据不纳入 Git。
