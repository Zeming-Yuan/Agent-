"""T08 public measurement boundaries; inference is never contacted on import."""
import asyncio
import runpy
from pathlib import Path


def test_tb08_memory_evidence_import_does_not_start_image_work(monkeypatch):
    def reject_run(coro):
        coro.close()
        raise AssertionError('import invoked benchmark main')
    def reject_write(*args, **kwargs):
        raise AssertionError('import attempted filesystem write')
    monkeypatch.setattr(Path, 'mkdir', reject_write)
    monkeypatch.setattr(asyncio, 'run', reject_run)
    runpy.run_module('scripts.benchmark_images', run_name='benchmark_import_probe')
