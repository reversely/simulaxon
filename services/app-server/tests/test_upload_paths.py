"""A dataset ID names one folder inside the datasets; nothing a request sends can reach outside it."""
import pytest
from app_server.lab import datasets


@pytest.mark.parametrize('did', ['../escaped', '../../etc', '/etc', 'a/b', '..', '', 'x' * 121])
def test_ids_that_leave_the_datasets_are_refused(did):
    with pytest.raises(ValueError):
        datasets.dataset_dir(did)


@pytest.mark.parametrize('did', ['upload_1a2b3c4d', 'openneuro_ds004488', 'generated-examples'])
def test_dataset_ids_resolve_inside_the_datasets(did):
    assert datasets.dataset_dir(did).parent == datasets.HERE
