# Contributing

Keep the wire contract in the [root README](README.md#supported-subset). When changing it, cite the A2UI schema or Discord component reference and update both implementations. Add an input and an independently specified expected result to `conformance/cases.json`. Only the generated UTC timestamp may differ between button actions. Never use customer data or credentials in fixtures.

## Run from a checkout

- Python: in a virtual environment, run `python -m pip install -e ./python` at the repository root. Run `python -m unittest discover -s python` and `python conformance/test_contract.py`.
- TypeScript: run `npm ci --prefix typescript` and `npm test --prefix typescript`. The test builds the library before running the shared cases.

## Check a release candidate

1. Check versions in `python/pyproject.toml` and `typescript/package.json`, the lockfile, and the changelog. Keep the MIT license notice in both packages.
2. Use a clean checkout. Install `build` and `twine` in the Python build environment. Run `python -m build python` to build the wheel from the sdist. Run `python -m twine check --strict python/dist/*`.
3. Run `npm ci` and `npm pack` in `typescript/`. Inspect the npm tarball, Python wheel, and sdist for unexpected files. Check that the npm tarball contains runnable JavaScript and declarations.
4. Install the wheel and npm tarball in separate empty environments outside the checkout. Run the shared cases against each install. Run the Python tests and fictional example. Exercise both ESM and CommonJS imports. The [CI workflow](.github/workflows/ci.yml) has the commands.
5. Test wire changes in a dedicated Discord thread with synthetic data before release. CI uses no Discord credentials and never publishes packages or creates releases.
