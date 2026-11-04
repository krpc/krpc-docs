# Publish wheels for krpc and krpctools

PyPI has only an sdist for each release of `krpc` and `krpctools`. So every `pip install` builds a
wheel on the user's machine. pip first downloads the build backend, hatchling, into an isolated
environment, then runs it.

- **Slower installs.** Each install, and each new virtual environment, repeats the build.
- **More can go wrong.** An install fails without network access to fetch hatchling. It also fails
  where an index mirror or `--only-binary :all:` blocks sdists.
- **Build code runs at install time.** A wheel is unpacked, with no build step.

Both packages are pure Python, so a `py3-none-any` wheel covers every platform.
- `krpctools` carries the bundled .NET tools as data, and they run on the dotnet host, whatever
  the Python platform.
- The native `libSystem.IO.Ports.Native.so` in the TestServer bundle is data too. It is loaded only
  by the TestServer on Linux.

## Change

- Build a wheel beside each sdist: `//client/python:python-pypi` and `//tools/krpctools`. Build it
  from the sdist, so the two have the same contents. `tools/build/python/build_sdist.py` already
  runs hatchling in a staged tree, and `hatchling build -t wheel` there gives the wheel.
- Upload both in `tools/release/60-release-python.py` and `61-release-krpctools.py`. Each calls
  `lib.twine_upload` with the sdist alone today.
- Attach the wheels to the GitHub release in `tools/release/40-build-assets.py`, next to the
  sdists.
- Install the wheel in the package tests that install today's sdist, such as
  `//tools/krpctools:conformance-test` and the CI `test-tool-packages` job. That checks the wheel's
  contents, the bundled tools and the entry points among them.

## Notes

- `[tool.hatch.build.targets.wheel]` is already set in both `pyproject.toml` files, so no
  packaging config is missing.
- hatchling builds a wheel reproducibly by default, with a fixed timestamp unless
  `SOURCE_DATE_EPOCH` is set, as it does the sdist.
- `krpc-base`, the client without its generated services, is a test artifact and needs no wheel.
