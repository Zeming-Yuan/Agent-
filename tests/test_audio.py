import numpy as np
from services.audio_utils import normalize_audio, whisper_segments
import pytest


def test_audio_bound_and_resample():
    assert normalize_audio(np.ones((8000,2)),8000).shape==(16000,)
    with pytest.raises(ValueError):
        normalize_audio(np.zeros(31*16000),16000)
    with pytest.raises(ValueError):
        normalize_audio(np.array([float('nan')]),16000)


def test_timestamp_offsets_clamped_to_actual_audio():
    result=whisper_segments({'text':'测试','offsets':[{'text':'测试','timestamp':(0,4)}]},2.5)
    assert result==[{'id':0,'start':0.0,'end':2.5,'text':'测试'}]


def test_cancelled_inference_releases_slot_only_after_thread_finishes():
    import asyncio
    import time
    from services.audio_utils import run_inference
    class Request:
        async def is_disconnected(self):
            return False
    async def check():
        slot=asyncio.Semaphore(1)
        finished=[]
        def infer(cancelled):
            while not cancelled.is_set():
                time.sleep(.005)
            time.sleep(.05)
            finished.append(True)
            raise RuntimeError('cancelled backend')
        task=asyncio.create_task(run_inference(slot,infer,Request()))
        await asyncio.sleep(.05)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        assert slot.locked() and not finished
        await asyncio.sleep(.15)
        assert finished and not slot.locked()
    asyncio.run(check())
