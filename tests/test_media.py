import asyncio
import sys
import pytest
from services.media import command
from services.store import Store


def test_subprocess_timeout_and_failure():
    async def check():
        with pytest.raises(TimeoutError):
            await command(sys.executable,'-c','import time; time.sleep(10)',timeout=.1)
        with pytest.raises(RuntimeError):
            await command(sys.executable,'-c','raise SystemExit(7)')
        assert await command(sys.executable,'-c','print("ok")')==b'ok\n'
    asyncio.run(check())


def test_restart_marks_running_failed_but_preserves_queued(tmp_path):
    store=Store(tmp_path)
    fid='file-'+'0'*32
    store.add_file(fid,'name',5)
    running=store.submit('transcribe',fid,{},'r')['id']
    queued=store.submit('transcribe',fid,{},'q')['id']
    store.update(running,status='running')
    store.recover()
    assert store.task(running)['status']=='failed'
    assert store.task(queued)['status']=='queued'
