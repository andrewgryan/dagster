import tempfile

import pytest

from dagster._core.test_utils import instance_for_test

from .setup import define_test_out_of_process_context


@pytest.yield_fixture(scope="function")
def graphql_context():
    with tempfile.TemporaryDirectory() as temp_dir:
        with instance_for_test(
            temp_dir=temp_dir,
            overrides={
                "scheduler": {
                    "module": "dagster.utils.test",
                    "class": "FilesystemTestScheduler",
                    "config": {"base_dir": temp_dir},
                }
            },
        ) as instance:
            with define_test_out_of_process_context(instance) as context:
                yield context
