# fsspec contract map

[Temper](https://github.com/turbolytics/temper) map of what every fsspec
filesystem promises, against nine filesystems. `MATRIX.md` at the repository
root is the result.

- `lattices/fs.contract.yml`: the guarantees. copy, get, put, pipe and open are
  the shared abstract tests. find and rm_list come from the AbstractFileSystem
  docstrings.
- `subjects/`: one file per filesystem, answering each guarantee.
- `fsspec/implementations/tests/temper/test_contract.py`: the tests. Each one
  states what it proves with `@pytest.mark.covers`.

Run it:

```sh
pip install -e ".[test]" pyarrow temper-python
brew install turbolytics/tap/temper   # or: go install github.com/turbolytics/temper/cmd/temper@v0.1.2
temper clean
temper run --level ci -- pytest fsspec/implementations/tests/temper
temper matrix
```

`temper matrix` exits 1 while any cell is failing.
