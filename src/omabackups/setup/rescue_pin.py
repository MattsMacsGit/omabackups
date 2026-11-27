"""The Rescue USB image a release writes (D58): the release that carries it
and its SHA-256. A release downloads from there only and refuses anything
else, so it writes exactly the image reviewed with it. Empty (or a version
that isn't this one): follow the "rescue-edge" testing image.

The image is built from the commit before this pin (a file can't hold its
own image's checksum); .github/workflows/rescue-release.yml copies it into
the release and checks it against this file.

D65: a release whose changes don't reach the stick keeps the last release's
image, byte for byte (copied from that release), so nobody's stick goes
out of date and Refresh downloads nothing new. 2.0.5 to 2.0.7 carry 2.0.4's."""

RELEASE = "v2.0.7"
SHA256 = "94beefeabc851836faad15af96382e228b88bd4a4333b952f8bf7638a36e4c7a"
