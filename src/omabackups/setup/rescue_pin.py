"""The Rescue USB image a release writes (D58): the release that carries it
and its SHA-256. A release downloads from there only and refuses anything
else, so it writes exactly the image reviewed with it. Empty (or a version
that isn't this one): follow the "rescue-edge" testing image.

The image is built from the commit before this pin (a file can't hold its
own image's checksum); .github/workflows/rescue-release.yml copies it into
the release and checks it against this file."""

RELEASE = "v2.0.3"
SHA256 = "569efb3739e332b56b2a1dddf4d076ee8cca35885b45ca6428b74bf28cf76a34"
