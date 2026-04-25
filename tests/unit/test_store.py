from __future__ import annotations


from speclink.core.paths import SPECLINK_DIR
from speclink.core.store import Store


def test_store_init_sets_root(tmp_path):
    store = Store(tmp_path)
    assert store.root == tmp_path / SPECLINK_DIR


def test_save_eval_does_nothing_when_not_eval_mode(tmp_path):
    store = Store(tmp_path)
    store.save_eval("test", "model", [{"a": 1}], eval_mode=False)
    assert not (store.root / "runs").exists()
