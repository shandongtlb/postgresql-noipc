# PostgreSQL 18.6：手机 Kali arm64，无需 SysV IPC

目标：在未启用 `CONFIG_SYSVIPC` 的 Android 手机内核上，通过 arm64/glibc 的 Kali chroot 运行 PostgreSQL。
项目、源码、构建目录和日志均保存在 `/opt/postgresql-no-sysvipc`。

## 手机安装

把 `artifacts/postgresql-18.6-linux-arm64-no-sysvipc.tar.gz` 复制到手机，进入 **Kali chroot**，以 root 运行：

```bash
tar -xzf postgresql-18.6-linux-arm64-no-sysvipc.tar.gz -C /opt
/opt/pgsql-18-no-sysvipc/pg-mobile init
/opt/pgsql-18-no-sysvipc/pg-mobile start
/opt/pgsql-18-no-sysvipc/pg-mobile psql -c 'SELECT version();'
```

停止或查看状态：

```bash
/opt/pgsql-18-no-sysvipc/pg-mobile stop
/opt/pgsql-18-no-sysvipc/pg-mobile status
```

脚本自动使用 Kali 的 `postgres` 系统用户；不存在时会创建该用户。`init` 只初始化空目录，已有 `PG_VERSION` 时直接返回。
数据库默认在 `/opt/pgsql-18-no-sysvipc/var/data`，日志在其中的 `server.log`；Unix socket 在 `var/run`。
默认只开放本机 Unix socket，使用 peer 认证；root 调用脚本时会先切换到 postgres 用户。
直接使用其他程序时可先运行 `source /opt/pgsql-18-no-sysvipc/env.sh`，再以 postgres 用户执行数据库操作。

要求：arm64/aarch64 Linux、glibc 2.36 或更新、支持目录 `flock` 的本地文件系统，以及 Kali 基础命令 `bash`、`runuser`、`useradd`。
这是 glibc Linux 包，不适用于直接在 Android shell 或普通 Termux/Bionic 下执行。数据目录应位于 Kali 的 Linux 文件系统中，不要放在 `/sdcard`。
可通过 `getconf GNU_LIBC_VERSION` 查看手机 Kali 的 glibc 版本。

## 修改内容

- 主共享内存继续使用 PostgreSQL 原有的匿名共享 `mmap`，保留 huge page 实现。
- 移除主共享内存的 SysV shim；在创建、检查或清理 `postmaster.pid` 前，对数据目录 inode 获取排他 `flock`。
- 文件描述符随 `fork` 继承，主进程被强杀后，仍持有共享内存的子进程继续阻止其他实例打开该数据目录。
- 不执行 `LOCK_UN`；内核在最后一个持有者退出时释放锁。描述符设置 `O_CLOEXEC`，不传给外部执行命令。
- 不参与共享内存的子进程（包括日志收集进程）关闭自己的锁副本；主进程发生共享内存重建时保持锁。
- 动态共享内存及 `initdb` 默认使用数据目录内的文件 `mmap`，不依赖 `/dev/shm`；保留可选 POSIX 动态共享内存，移除 SysV 选项。
- 信号量采用 Linux 上 PostgreSQL 自带的匿名 POSIX 实现，通过 futex 同步，无需 SysV 信号量。

此补丁只支持 Linux/fork 模式，不支持 `EXEC_BACKEND`。同一数据目录请统一使用本补丁构建的程序。
默认 `mmap` 动态共享内存可能增加文件回写开销；这是兼容手机 chroot 的取舍。

## 包的内容与功能边界

包内提供 PostgreSQL 服务端、`psql`、`pg_ctl`、`initdb`、`pg_dump`/`pg_restore`、`pgbench`、libpq、头文件及 PGXS；另附补丁和源码许可证。
使用 Debian 12 的 glibc 2.36 sysroot 交叉编译，目标为 ARMv8-A，不要求较新的 ARM 指令集。包内所需的 PostgreSQL 共享库均已提供。
为减少运行时依赖，关闭 ICU、readline、zlib、TLS/OpenSSL、LLVM JIT、liburing，以及其他需额外第三方库的可选功能。
支持 UTF-8 数据库、SQL、内置函数、并行查询、无压缩 dump；不提供 TLS 连接、ICU 排序规则、readline 历史编辑或额外压缩算法。

## 构建、补丁与测试

官方源码及校验文件位于 `downloads/`；上游下载地址：
https://ftp.postgresql.org/pub/source/v18.6/

`postgresql-18.6-no-sysvipc.patch` 可以应用到未经修改的 PostgreSQL 18.6 源码。
`patch-source.py` 可从原版源码生成同样修改。构建脚本 `build.sh` 用于在 Linux 主机原生构建；交叉构建脚本为 `build-arm64.sh`，完整参数见 `BUILD-INFO.txt`。
原生构建需要 `build-essential bison flex bzip2 patch curl`，上述精简配置无需额外开发库。

```bash
bash build.sh
```

如需在 x86_64 Linux 上重建 arm64 包，先安装 `gcc-aarch64-linux-gnu binutils-aarch64-linux-gnu`，再运行 `python3 setup-sysroot.py` 和 `bash build-arm64.sh`。脚本按 `toolchain/sysroot-manifest.json` 下载并校验 Debian sysroot。
安装包中的开发文件保留了交叉编译配置；在手机编译额外 C 扩展时，需调整 PGXS 的编译器设置，或在手机上使用源码原生构建。

`tests/deny-sysvipc.c` 通过 seccomp 将 SysV 共享内存与信号量系统调用设置为 `ENOSYS`，且限制会被 fork/exec 的后代继承。
`tests/integration.py` 验证初始化、并行查询、并发事务、导出导入、目录互斥、主进程与后端崩溃恢复等行为。
原生测试和 arm64 QEMU 测试的真实结果、glibc 需求与验证边界见 `STATUS.zh-CN.md`。
没有在你的真实手机上执行；手机首次运行请用新数据目录验证。

现有其他 PostgreSQL 大版本的数据目录需要按 PostgreSQL 的升级流程迁移，不能直接作为 18 版目录启动。
