import numpy as np


def normalize_audio(audio, rate):
    audio = np.asarray(audio, dtype=np.float32)
    if audio.ndim==2:
        audio=audio.mean(axis=1)
    if audio.ndim!=1 or len(audio)==0 or rate<8000 or rate>192000 or not np.isfinite(audio).all():
        raise ValueError('Invalid audio samples/rate')
    if len(audio)/rate>30.05:
        raise ValueError('Audio exceeds 30 seconds; use media tasks for longer recordings')
    if rate!=16000:
        count=round(len(audio)*16000/rate)
        audio=np.interp(np.arange(count)*rate/16000,np.arange(len(audio)),audio).astype(np.float32)
    return audio


def whisper_segments(decoded, duration):
    segments=[]
    for item in decoded.get('offsets',[]):
        start,end=item['timestamp']
        start=max(0,min(duration,float(start)))
        end=max(start,min(duration,float(end)))
        segments.append({'id':len(segments),'start':start,'end':end,'text':item['text']})
    return segments


_inflight = set()


async def run_inference(slot, function, request, timeout=180):
    """Retain GPU admission until the worker thread actually finishes after disconnect."""
    import asyncio
    import threading
    import time
    from fastapi import HTTPException
    try:
        await asyncio.wait_for(slot.acquire(), timeout=5)
    except TimeoutError:
        raise HTTPException(429, 'Audio model busy')
    event=threading.Event()
    task=asyncio.create_task(asyncio.to_thread(function,event))
    _inflight.add(task)
    def finished(completed):
        _inflight.discard(completed)
        slot.release()
        if not completed.cancelled():
            completed.exception()  # Consume detached failures after the requesting client has gone.
    task.add_done_callback(finished)
    try:
        deadline=time.monotonic()+timeout
        while not task.done():
            if await request.is_disconnected() or time.monotonic()>deadline:
                event.set()
                raise HTTPException(408,'Audio request cancelled or timed out')
            await asyncio.sleep(.1)
        return task.result()
    finally:
        event.set()


async def admit_decode(slot, function):
    """Bound file reads and ffmpeg work before reaching GPU inference admission."""
    import asyncio
    from fastapi import HTTPException
    try:
        await asyncio.wait_for(slot.acquire(), timeout=5)
    except TimeoutError:
        raise HTTPException(429,'Audio preprocessing busy')
    try:
        return await function()
    finally:
        slot.release()
