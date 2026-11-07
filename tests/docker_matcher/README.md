# Docker ignore matcher (test helper only)

The Python deployment tests call this helper to test the root and nested
`.dockerignore` behavior. It uses exactly upstream **Moby/patternmatcher v0.6.0**
and `ignorefile.ReadAll`, not a similar-but-different Git-ignore or shell-glob
implementation. It is not an image builder, runtime component, Docker Engine,
or guarantee that Docker BuildKit or Render support has been tested.

To avoid shipping compiled code, the Python fixture builds this **vendored Apache-2.0
source** offline in pytest's temporary directory with `GOPROXY=off` and
`GOTOOLCHAIN=local`. A missing Go compiler causes its test to skip; whether
Go is installed does not affect installation of the Python application. No
compiled cache, Go module cache, or downloaded binary is included.

Source files are unmodified except for changing the declared vendor-module
path in `vendor/modules.txt`. Their provenance is
`https://github.com/moby/patternmatcher/tree/v0.6.0`; license is retained in
`LICENSE`. Dependency checksums are retained in `go.sum` from the earlier
recorded upstream download, which had tag commit hash
`347bb8d8d557f90d1b75cd8bca3c0177f380a979`. No credentials are accessed.
