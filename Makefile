.PHONY: test build check publish-test publish bump-patch clean

test:
	PYTHONPATH=src pytest -q

build:
	python -m build

check:
	python -m twine check dist/*

publish-test: build check
	python -m twine upload --repository testpypi dist/*

bump-patch:
	python -c "from pathlib import Path; import re; p=Path('pyproject.toml'); s=p.read_text(); m=re.search(r'^version\\s*=\\s*\"(\\d+)\\.(\\d+)\\.(\\d+)\"\\s*$$', s, re.M); \
assert m, 'Could not find project version in pyproject.toml'; major, minor, patch = map(int, m.groups()); new=f'{major}.{minor}.{patch+1}'; \
s2=s[:m.start()] + f'version = \"{new}\"' + s[m.end():]; p.write_text(s2); print(f'Bumped version: {major}.{minor}.{patch} -> {new}')"

publish: bump-patch build check
	python -m twine upload dist/*

clean:
	rm -rf build dist *.egg-info
