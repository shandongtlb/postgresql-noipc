Format: 3.0 (quilt)
Source: postgresql-18
Binary: libpq-dev, libpq5, libpq-oauth, libecpg6, libecpg-dev, libecpg-compat3, libpgtypes3, postgresql-18, postgresql-client-18, postgresql-server-dev-18, postgresql-doc-18, postgresql-plperl-18, postgresql-plpython3-18, postgresql-pltcl-18, postgresql-18-jit
Architecture: any all
Version: 18.6-3+noipc2
Maintainer: SDTLB <40312509+shandongtlb@users.noreply.github.com>
Uploaders: Martin Pitt <mpitt@debian.org>, Peter Eisentraut <petere@debian.org>, Christoph Berg <myon@debian.org>
Homepage: http://www.postgresql.org/
Standards-Version: 4.7.4
Vcs-Browser: https://salsa.debian.org/postgresql/postgresql
Vcs-Git: https://salsa.debian.org/postgresql/postgresql.git -b 18
Testsuite: autopkgtest
Testsuite-Triggers: build-essential, debhelper, fakeroot, hunspell-en-us, iproute2, locales-all, logrotate, netcat-openbsd, perl, postgresql-common-dev, procps, tzdata, tzdata-legacy
Build-Depends: autoconf, bison, clang [amd64 arm64 mips64el ppc64 ppc64el s390x] <!pkg.postgresql.nollvm>, debhelper-compat (= 13), dh-exec (>= 0.13~), docbook-xml, docbook-xsl (>= 1.77), dpkg-dev (>= 1.16.1~), flex, gdb <!nocheck>, gettext, libcurl4-openssl-dev [linux-any], libicu-dev, libio-pty-perl <!nocheck>, libipc-run-perl <!nocheck>, libkrb5-dev, libldap2-dev, liblz4-dev, libnuma-dev [linux-any], libpam0g-dev | libpam-dev, libperl-dev, libreadline-dev, libselinux1-dev [linux-any], libssl-dev, libsystemd-dev [linux-any], liburing-dev [linux-any], libxml2-dev, libxml2-utils, libxslt1-dev, libzstd-dev (>= 1.4.0) <!pkg.postgresql.nozstd>, llvm-dev [amd64 arm64 mips64el ppc64 ppc64el s390x] <!pkg.postgresql.nollvm>, lz4 | liblz4-tool, mawk, openssl, perl (>= 5.8), pkgconf, postgresql-common-dev, python3-dev, systemtap-sdt-dev [linux-any], tcl-dev, tzdata <!nocheck>, tzdata-legacy <!nocheck> | tzdata (<< 2023c-8) <!nocheck>, uuid-dev, xsltproc, zlib1g-dev | libz-dev, zstd (>= 1.4.0) <!pkg.postgresql.nozstd>
Package-List:
 libecpg-compat3 deb libs optional arch=any profile=!pkg.postgresql.nolibpkgs profile:v1=!pkg.postgresql.nolibpkgs
 libecpg-dev deb libdevel optional arch=any profile=!pkg.postgresql.nolibpkgs profile:v1=!pkg.postgresql.nolibpkgs
 libecpg6 deb libs optional arch=any profile=!pkg.postgresql.nolibpkgs profile:v1=!pkg.postgresql.nolibpkgs
 libpgtypes3 deb libs optional arch=any profile=!pkg.postgresql.nolibpkgs profile:v1=!pkg.postgresql.nolibpkgs
 libpq-dev deb libdevel optional arch=any profile=!pkg.postgresql.nolibpkgs profile:v1=!pkg.postgresql.nolibpkgs
 libpq-oauth deb libs optional arch=linux-any profile=!pkg.postgresql.nolibpkgs profile:v1=!pkg.postgresql.nolibpkgs
 libpq5 deb libs optional arch=any profile=!pkg.postgresql.nolibpkgs profile:v1=!pkg.postgresql.nolibpkgs
 postgresql-18 deb database optional arch=any
 postgresql-18-jit deb database optional arch=amd64,arm64,mips64el,ppc64,ppc64el,s390x profile=!pkg.postgresql.nollvm profile:v1=!pkg.postgresql.nollvm
 postgresql-client-18 deb database optional arch=any
 postgresql-doc-18 deb doc optional arch=all profile=!nodoc profile:v1=!nodoc
 postgresql-plperl-18 deb database optional arch=any
 postgresql-plpython3-18 deb database optional arch=any
 postgresql-pltcl-18 deb database optional arch=any
 postgresql-server-dev-18 deb libdevel optional arch=any
Checksums-Sha1:
 a0b624ab95fd6fae676bc929d0e6fbcbc777c327 22632314 postgresql-18_18.6.orig.tar.bz2
 abde9a852b5b33a9d29b1b281bf50cd3b505e964 44472 postgresql-18_18.6-3+noipc2.debian.tar.xz
Checksums-Sha256:
 555610c24d53e4316da5b7d3fc25c279d96856d5e0e23ee308c328c5fa881d9f 22632314 postgresql-18_18.6.orig.tar.bz2
 872ef5ee04b823e0e85fd68d3f6e7fed70d3b73b1669e1694680b1ef38502fcd 44472 postgresql-18_18.6-3+noipc2.debian.tar.xz
Files:
 6143c18ab91bdfcaa056a61861814cde 22632314 postgresql-18_18.6.orig.tar.bz2
 b951b8d5283edbc7b7225ee280b85954 44472 postgresql-18_18.6-3+noipc2.debian.tar.xz
Original-Maintainer: Debian PostgreSQL Maintainers <team+postgresql@tracker.debian.org>
