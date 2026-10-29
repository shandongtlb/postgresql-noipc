# PostgreSQL noipc

这是 PostgreSQL 18 的 Linux/fork 修改分支，目标是在未启用 `CONFIG_SYSVIPC` 的 arm64 手机 Kali chroot 中运行。

源码位于仓库根目录的标准 PostgreSQL 路径，保留官方 `REL_18_6` 及其全部祖先提交，便于继续合并 `REL_18_STABLE`。构建脚本、补丁和历史验证记录放在 `noipc/`。
先前两个发布源码快照提交仍通过合并保存在历史中。

## 原生构建

```bash
sudo apt-get install build-essential bison flex perl python3 bzip2 patch curl
bash noipc/build.sh
```

默认安装到 `noipc/install/`，日志位于 `noipc/logs/`。也可直接按 PostgreSQL 的标准源码构建流程编译。

## arm64 交叉构建

```bash
sudo apt-get install gcc-aarch64-linux-gnu binutils-aarch64-linux-gnu
python3 noipc/setup-sysroot.py
bash noipc/build-arm64.sh
```

结果位于 `noipc/stage-arm64/opt/pgsql-18-no-sysvipc/`。sysroot 采用已校验的 Debian 12 arm64 glibc 2.36 包。

## 同步 PostgreSQL 上游

第一次在自己的克隆中添加官方远端：

```bash
git remote add upstream https://git.postgresql.org/git/postgresql.git
git config remote.upstream.fetch '+refs/heads/REL_18_STABLE:refs/remotes/upstream/REL_18_STABLE'
```

以后同步 PostgreSQL 18 稳定分支：

```bash
git switch main
git fetch upstream
git merge upstream/REL_18_STABLE
git push origin main
```

合并若出现冲突，需要保留本项目的 mmap 与目录锁实现，解决后重新构建和测试。
`REL_18_STABLE` 用于 18 系列维护更新；跨大版本迁移需要单独适配，不能直接以 `master` 替代它。
可用 `git log -- src/backend/port/sysv_shmem.c` 查看包含上游的文件历史。

## 修改与验证

主共享内存采用匿名 mmap，动态共享内存默认采用文件 mmap，信号量使用 POSIX/futex。
目录 inode flock 随 fork 继承，孤儿后端仍存活时继续保护数据目录。

已有验证：231 项原生上游回归测试、原生与 arm64 QEMU 各 13 项集成检查全部通过；70 个 arm64 ELF 文件无 SysV IPC 函数导入。
迁移历史时未改变这 6 个已验证的功能源码文件内容。迁移后已从 Git 标准布局重新原生构建，并再次通过禁用 SysV IPC 的 13 项集成检查。真实手机尚未验证。
精简构建不包含 TLS、ICU、readline、zlib、LLVM JIT 和 liburing 等可选功能。

[历史验证记录](verification/) · [手机安装说明](README.zh-CN.md) · [18.6 补丁](postgresql-18.6-no-sysvipc.patch) · [上游许可证](../COPYRIGHT)
