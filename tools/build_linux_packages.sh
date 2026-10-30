#!/usr/bin/env bash
set -euo pipefail
version="0.2.8"
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$root"
mkdir -p dist-linux
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
app="$work/pkg"
install -d "$app/opt/meridian" "$app/usr/bin" "$app/usr/share/applications" "$app/usr/share/icons/hicolor/256x256/apps" "$app/DEBIAN"
install -m 0644 meridian.py "$app/opt/meridian/meridian.py"
install -m 0644 auth.py "$app/opt/meridian/auth.py"
cp -r static "$app/opt/meridian/static"
install -m 0644 assets/meridian.png "$app/usr/share/icons/hicolor/256x256/apps/meridian.png"
cat > "$app/usr/bin/meridian" <<'LAUNCHER'
#!/bin/sh
exec /usr/bin/python3 /opt/meridian/meridian.py "$@"
LAUNCHER
chmod 755 "$app/usr/bin/meridian"
cat > "$app/usr/share/applications/meridian.desktop" <<'DESKTOP'
[Desktop Entry]
Name=Meridian
GenericName=Development Control Center
Comment=Track project releases, uptime, analytics, and next steps
Exec=meridian
Icon=meridian
Terminal=false
Type=Application
Categories=Development;Utility;
StartupNotify=true
DESKTOP
cat > "$app/DEBIAN/control" <<'CONTROL'
Package: meridian
Version: 0.2.8
Section: utils
Priority: optional
Architecture: all
Depends: python3 (>= 3.9)
Maintainer: Meridian Project
Description: Personal development control center for Latitude, Longitude and Sundial
 A local-first project monitor, release and website status dashboard.
CONTROL
dpkg-deb --root-owner-group --build "$app" "dist-linux/Meridian-${version}-all.deb"
rpmroot="$work/rpmbuild"
mkdir -p "$rpmroot"/{BUILD,BUILDROOT,RPMS,SOURCES,SPECS,SRPMS}
mkdir -p "$work/rpmroot"
cp -a "$app/opt" "$app/usr" "$work/rpmroot/"
tar -C "$work/rpmroot" -czf "$rpmroot/SOURCES/meridian-root.tar.gz" .
cat > "$rpmroot/SPECS/meridian.spec" <<'SPEC'
Name: meridian
Version: 0.2.8
Release: 1
Summary: Local-first development control center
License: Proprietary
BuildArch: noarch
Requires: python3
Source0: meridian-root.tar.gz

%description
Personal project monitoring and notes dashboard for Latitude, Longitude, and Sundial.

%prep
%setup -q -c -T
tar xzf %{_sourcedir}/meridian-root.tar.gz

%build

%install
mkdir -p %{buildroot}
cp -a opt usr %{buildroot}/

%files
/opt/meridian
/usr/bin/meridian
/usr/share/applications/meridian.desktop
/usr/share/icons/hicolor/256x256/apps/meridian.png

%changelog
* Thu Oct 29 2026 Meridian Project - 0.2.8-1
- First Linux desktop package of the unified dashboard
SPEC
rpmbuild -bb --define "_topdir $rpmroot" "$rpmroot/SPECS/meridian.spec"
cp "$rpmroot/RPMS/noarch/meridian-${version}-1.noarch.rpm" "dist-linux/Meridian-${version}-1.noarch.rpm"
echo "Linux installers built in dist-linux/"
