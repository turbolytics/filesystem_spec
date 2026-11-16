"""The fs.contract lattice: what every filesystem promises, per filesystem.

Each test states what it proves with @pytest.mark.covers (temper-python).
Without `temper run`, the marks do nothing.
"""

import io
import os
import tarfile
import zipfile

import pytest

import fsspec
import fsspec.tests.abstract as abstract
from fsspec.implementations.asyn_wrapper import AsyncFileSystemWrapper
from fsspec.implementations.dirfs import DirFileSystem
from fsspec.implementations.local import LocalFileSystem, make_path_posix
from fsspec.implementations.memory import MemoryFileSystem
from fsspec.implementations.tests.local.local_fixtures import LocalFixtures
from fsspec.implementations.tests.memory.memory_fixtures import MemoryFixtures
from fsspec.tests.abstract import AbstractFixtures

pa_fs = pytest.importorskip("pyarrow.fs")
from fsspec.implementations.arrow import ArrowFSWrapper  # noqa: E402


def _clear_memory():
    MemoryFileSystem.store.clear()
    MemoryFileSystem.pseudo_dirs.clear()
    MemoryFileSystem.pseudo_dirs.append("")


def _slash_join(*args):
    return "/".join(args)


# Fixtures for the shared abstract tests


class DirfsMemoryFixtures(AbstractFixtures):
    @pytest.fixture
    def fs(self):
        _clear_memory()
        yield DirFileSystem(path="/root", fs=fsspec.filesystem("memory"))
        _clear_memory()

    @pytest.fixture
    def fs_join(self):
        return _slash_join

    @pytest.fixture
    def fs_path(self):
        return "base"


class DirfsLocalFixtures(AbstractFixtures):
    @pytest.fixture
    def fs(self, tmp_path):
        return DirFileSystem(path=str(tmp_path), fs=LocalFileSystem(auto_mkdir=True))

    @pytest.fixture
    def fs_join(self):
        return _slash_join

    @pytest.fixture
    def fs_path(self):
        return "base"


class AsyncWrapperFixtures(AbstractFixtures):
    @pytest.fixture(scope="class")
    def fs(self):
        return AsyncFileSystemWrapper(
            LocalFileSystem(auto_mkdir=True), asynchronous=False
        )

    @pytest.fixture
    def fs_path(self, tmpdir):
        return make_path_posix(str(tmpdir))

    @pytest.fixture
    def fs_join(self):
        return _slash_join

    @pytest.fixture
    def fs_sanitize_path(self):
        return make_path_posix


class SimplecacheFixtures(AbstractFixtures):
    @pytest.fixture
    def fs(self, tmp_path):
        _clear_memory()
        yield fsspec.filesystem(
            "simplecache",
            target_protocol="memory",
            cache_storage=str(tmp_path / "cache"),
        )
        _clear_memory()

    @pytest.fixture
    def fs_join(self):
        return _slash_join

    @pytest.fixture
    def fs_path(self):
        return ""


class ArrowFixtures(AbstractFixtures):
    @pytest.fixture(scope="class")
    def fs(self):
        return ArrowFSWrapper(pa_fs.LocalFileSystem())

    @pytest.fixture
    def fs_path(self, tmpdir):
        return make_path_posix(str(tmpdir))

    @pytest.fixture
    def fs_join(self):
        return _slash_join

    @pytest.fixture
    def fs_sanitize_path(self):
        return make_path_posix


class ReferenceFixtures(AbstractFixtures):
    @pytest.fixture
    def fs(self):
        return fsspec.filesystem("reference", fo={"version": 1, "refs": {}})

    @pytest.fixture
    def fs_join(self):
        return _slash_join

    @pytest.fixture
    def fs_path(self):
        return "base"


SUITES = {
    "copy": abstract.AbstractCopyTests,
    "get": abstract.AbstractGetTests,
    "put": abstract.AbstractPutTests,
    "pipe": abstract.AbstractPipeTests,
    "open": abstract.AbstractOpenTests,
}
ALL = list(SUITES)

# (class name, subject, fixtures, the members its subject answers supported)
SHARED = [
    ("Local", "local", LocalFixtures, ALL),
    ("Memory", "memory", MemoryFixtures, ALL),
    ("DirfsMemory", "dirfs", DirfsMemoryFixtures, ALL),
    ("DirfsLocal", "dirfs", DirfsLocalFixtures, ALL),
    ("AsyncWrapper", "async_wrapper", AsyncWrapperFixtures, ALL),
    ("Simplecache", "simplecache", SimplecacheFixtures, ALL),
    ("Arrow", "arrow", ArrowFixtures, ["put", "pipe"]),
    ("Reference", "reference", ReferenceFixtures, ["pipe"]),
]
for _cls, _subject, _fixtures, _members in SHARED:
    for _member in _members:
        _name = f"Test{_cls}{_member.capitalize()}"
        globals()[_name] = type(
            _name,
            (SUITES[_member], _fixtures),
            {
                "pytestmark": [
                    pytest.mark.covers(f"fs.contract/{_member}", subject=f"fs.{_subject}")
                ]
            },
        )


# One small tree in every filesystem, for find and the feature checks

TREE = {"x/0": b"zero", "x/sub/1": b"one", "x_bnds/0": b"bnds"}


def _write_local(root):
    for k, v in TREE.items():
        p = os.path.join(root, k)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "wb") as f:
            f.write(v)


def _with_tree(subject, tmp_path):
    """Return (fs, base) for a filesystem that holds TREE under base."""
    root = str(tmp_path / "tree")
    if subject in ("local", "async_wrapper", "arrow"):
        _write_local(root)
        base = make_path_posix(root)
        if subject == "local":
            return LocalFileSystem(), base
        if subject == "async_wrapper":
            return AsyncFileSystemWrapper(LocalFileSystem(), asynchronous=False), base
        return ArrowFSWrapper(pa_fs.LocalFileSystem()), base
    if subject in ("memory", "dirfs", "simplecache"):
        _clear_memory()
        mem = fsspec.filesystem("memory")
        for k, v in TREE.items():
            mem.pipe_file(f"/tree/{k}", v)
        if subject == "memory":
            return mem, "/tree"
        if subject == "dirfs":
            return DirFileSystem(path="/tree", fs=mem), ""
        cache = str(tmp_path / "cache")
        return (
            fsspec.filesystem("simplecache", target_protocol="memory", cache_storage=cache),
            "/tree",
        )
    if subject == "reference":
        refs = {k: v.decode() for k, v in TREE.items()}
        return fsspec.filesystem("reference", fo={"version": 1, "refs": refs}), ""
    if subject == "zip":
        path = str(tmp_path / "t.zip")
        with zipfile.ZipFile(path, "w") as z:
            for k, v in TREE.items():
                z.writestr(k, v)
        return fsspec.filesystem("zip", fo=path), ""
    if subject == "tar":
        path = str(tmp_path / "t.tar")
        with tarfile.open(path, "w") as t:
            for k, v in TREE.items():
                info = tarfile.TarInfo(k)
                info.size = len(v)
                t.addfile(info, io.BytesIO(v))
        return fsspec.filesystem("tar", fo=path), ""
    raise ValueError(subject)


def _rel(base, paths):
    b = base.strip("/")
    out = []
    for p in paths:
        p = p.strip("/")
        if b and p.startswith(b + "/"):
            p = p[len(b) + 1 :]
        out.append(p)
    return sorted(out)


def _join(base, rel):
    return f"{base}/{rel}" if base else rel


SUBJECTS = [
    "local",
    "memory",
    "dirfs",
    "async_wrapper",
    "simplecache",
    "arrow",
    "reference",
    "zip",
    "tar",
]


@pytest.mark.parametrize(
    "subject",
    [pytest.param(s, marks=pytest.mark.covers(f"fs.{s}")) for s in SUBJECTS],
)
def test_reads_a_file(subject, tmp_path):
    fs, base = _with_tree(subject, tmp_path)
    assert fs.cat_file(_join(base, "x/sub/1")) == b"one"


@pytest.mark.parametrize(
    "subject",
    [
        pytest.param(s, marks=pytest.mark.covers("fs.contract/find", subject=f"fs.{s}"))
        for s in SUBJECTS
    ],
)
def test_find_stays_under_path_and_maxdepth(subject, tmp_path):
    fs, base = _with_tree(subject, tmp_path)
    assert _rel(base, fs.find(_join(base, "x"))) == ["x/0", "x/sub/1"]
    assert _rel(base, fs.find(_join(base, "x"), maxdepth=1)) == ["x/0"]


RM_LIST = ["local", "memory", "dirfs", "async_wrapper", "simplecache", "arrow", "reference"]


@pytest.mark.parametrize(
    "subject",
    [
        pytest.param(
            s, marks=pytest.mark.covers("fs.contract/rm_list", subject=f"fs.{s}")
        )
        for s in RM_LIST
    ],
)
def test_rm_takes_a_list(subject, tmp_path):
    fs, base = _with_tree(subject, tmp_path)
    paths = [_join(base, "x/0"), _join(base, "x_bnds/0")]
    fs.rm(paths)
    assert not any(fs.exists(p) for p in paths)


# Proofs for the exemptions: each filesystem refuses the operation loudly.


def _refusals(tmp_path):
    local = tmp_path / "local.bin"
    local.write_bytes(b"new")
    return {
        ("arrow", "open"): (ValueError, lambda fs, b: fs.open(_join(b, "new"), "xb")),
        ("reference", "copy"): (
            NotImplementedError,
            lambda fs, b: fs.cp_file("x/0", "x/copy"),
        ),
        ("reference", "open"): (
            FileNotFoundError,
            lambda fs, b: fs.open("x/new", "wb"),
        ),
        **{
            (ro, "copy"): (NotImplementedError, lambda fs, b: fs.cp_file("x/0", "x/c"))
            for ro in ("zip", "tar")
        },
        **{
            (ro, "put"): (Exception, lambda fs, b: fs.put(str(local), "x/new"))
            for ro in ("zip", "tar")
        },
        **{
            (ro, "pipe"): (ValueError, lambda fs, b: fs.pipe_file("x/new", b"y"))
            for ro in ("zip", "tar")
        },
        ("zip", "open"): (OSError, lambda fs, b: fs.open("x/new", "wb")),
        ("tar", "open"): (ValueError, lambda fs, b: fs.open("x/new", "wb")),
        **{
            (ro, "rm_list"): (NotImplementedError, lambda fs, b: fs.rm(["x/0"]))
            for ro in ("zip", "tar")
        },
    }


REFUSALS = [
    ("arrow", "open"),
    ("reference", "copy"),
    ("reference", "open"),
    ("zip", "copy"),
    ("zip", "put"),
    ("zip", "pipe"),
    ("zip", "open"),
    ("zip", "rm_list"),
    ("tar", "copy"),
    ("tar", "put"),
    ("tar", "pipe"),
    ("tar", "open"),
    ("tar", "rm_list"),
]


@pytest.mark.parametrize(
    "subject,member",
    [
        pytest.param(
            s,
            m,
            id=f"{s}-{m}",
            marks=pytest.mark.exempts(f"fs.contract/{m}", subject=f"fs.{s}"),
        )
        for s, m in REFUSALS
    ],
)
def test_refuses(subject, member, tmp_path):
    fs, base = _with_tree(subject, tmp_path)
    exc, call = _refusals(tmp_path)[(subject, member)]
    with pytest.raises(exc):
        call(fs, base)
