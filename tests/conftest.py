from collections.abc import Iterator
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest


@pytest.fixture
def tmp_dir() -> Iterator[Path]:
    """Provide test directories inside the repository instead of global temp."""
    repo_tmp = Path(__file__).resolve().parents[1] / '.tmp'
    repo_tmp.mkdir(exist_ok=True, parents=True)
    with TemporaryDirectory(prefix="pytest-", dir=repo_tmp) as directory:
        yield Path(directory)
    ####
####


@pytest.fixture
def tmp_path(tmp_dir: Path) -> Path:
    """Compatibility alias for tests that still use pytest's fixture name."""
    return tmp_dir
####
