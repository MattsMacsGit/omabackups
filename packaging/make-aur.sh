#!/bin/bash
# Make the AUR copy of the omabackups package recipe (D20), from the one in
# this folder: the same steps, but reading a tagged release that it
# downloads and checks, instead of this clone.
#
#   packaging/make-aur.sh AUR-FOLDER            the release on GitHub (tag v<version>)
#   packaging/make-aur.sh AUR-FOLDER TARBALL    a local tarball instead (to test first)
#
# Writes PKGBUILD and .SRCINFO into AUR-FOLDER (a clone of the AUR's
# omabackups repo). The version is the one in src/omabackups/__init__.py.
set -euo pipefail

here="$(cd "$(dirname "$0")" && pwd)"
repo="$(dirname "$here")"
out="${1:?usage: make-aur.sh AUR-FOLDER [TARBALL]}"
version="$(sed -n 's/^__version__ = "\(.*\)"$/\1/p' "$repo/src/omabackups/__init__.py")"
url="$(sed -n 's/^url="\(.*\)"$/\1/p' "$here/PKGBUILD")"
tarball="omabackups-$version.tar.gz"

grep -q "^pkgver=$version$" "$here/PKGBUILD" || { echo "PKGBUILD's pkgver isn't $version" >&2; exit 1; }
mkdir -p "$out"
if [[ -n ${2:-} ]]; then
  cp "$2" "$out/$tarball"
else
  curl -fsSL -o "$out/$tarball" "$url/archive/refs/tags/v$version.tar.gz"
fi
sum="$(sha256sum "$out/$tarball" | cut -d' ' -f1)"

{
  echo "# The omabackups package (D20), from the tagged release v$version."
  echo "# Made by packaging/make-aur.sh in $url"
  echo
  sed -n '/^pkgname=/,$p' "$here/PKGBUILD" |
    sed -e "s|^options=(.*|&\nsource=(\"$tarball::$url/archive/refs/tags/v\$pkgver.tar.gz\")\nsha256sums=('$sum')|" \
        -e 's|local repo="\$startdir/.."|local repo="$srcdir/$pkgname-$pkgver"|'
} > "$out/PKGBUILD"
grep -q 'local repo="$srcdir/$pkgname-$pkgver"' "$out/PKGBUILD" || { echo "couldn't point the recipe at the release" >&2; exit 1; }
(cd "$out" && makepkg --printsrcinfo > .SRCINFO)
[[ -n ${2:-} ]] || rm -f "$out/$tarball"
echo "Wrote $out/PKGBUILD and .SRCINFO for omabackups $version."
