import asyncio
import pytest
from fastapi import HTTPException
from services.audio_utils import admit_decode


def test_audio_decode_admission_is_bounded():
    async def check():
        slot=asyncio.Semaphore(1)
        active=0
        peak=0
        async def decode():
            nonlocal active,peak
            active+=1;peak=max(peak,active)
            await asyncio.sleep(.02)
            active-=1
            return 'decoded'
        result=await asyncio.gather(*(admit_decode(slot,decode) for _ in range(10)))
        assert result==['decoded']*10 and peak==1
    asyncio.run(check())
