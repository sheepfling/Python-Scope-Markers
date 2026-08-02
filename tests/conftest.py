from collections.abc import Iterator
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest


@pytest.fixture
def tmp_path() -> Iterator[Path]:
    """Provide test directories inside the repository instead of global temp."""
    repository_root = Path(__file__).resolve().parents[1]
    with TemporaryDirectory(prefix=".pytest-tmp-", dir=repository_root) as directory:
        yield Path(directory)
    ####
####
