"""One resident GPU model per process. Endpoints bind only to loopback."""
import asyncio
import os
import tempfile
import time
from contextlib import asynccontextmanager
from pathlib import Path
import numpy as np
import torch
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from transformers import (WhisperForConditionalGeneration, WhisperProcessor,
    Qwen2_5OmniForConditionalGeneration, Qwen2_5OmniProcessor, StoppingCriteria, StoppingCriteriaList)
from .audio_utils import normalize_audio, whisper_segments, run_inference, admit_decode
from .media import command

MODE = os.environ.get('AUDIO_MODEL','whisper')
MODEL_PATH = os.environ['AUDIO_MODEL_PATH']
model = processor = None
slot = asyncio.Semaphore(1)
decode_slot = asyncio.Semaphore(1)


class CancelGeneration(StoppingCriteria):
    def __init__(self, event):
        self.event = event
    def __call__(self, input_ids, scores, **kwargs):
        return self.event.is_set()


@asynccontextmanager
async def lifespan(app):
    global model, processor
    torch.set_num_threads(4)
    if MODE=='whisper':
        processor=WhisperProcessor.from_pretrained(MODEL_PATH,local_files_only=True)
        model=WhisperForConditionalGeneration.from_pretrained(MODEL_PATH,local_files_only=True,dtype=torch.float16).to('cuda').eval()
    else:
        if not Path(MODEL_PATH,'.verified.json').is_file():
            raise RuntimeError('Omni weights must be checksum verified before startup')
        processor=Qwen2_5OmniProcessor.from_pretrained(MODEL_PATH,local_files_only=True)
        model=Qwen2_5OmniForConditionalGeneration.from_pretrained(MODEL_PATH,local_files_only=True,
                    dtype=torch.bfloat16,enable_audio_output=False,attn_implementation='sdpa').to('cuda').eval()
        if model.has_talker:
            model.disable_talker()
    print(f'READY {MODE}; allocated={torch.cuda.memory_allocated()/2**30:.2f} GiB',flush=True)
    yield


app=FastAPI(lifespan=lifespan,docs_url=None,redoc_url=None,openapi_url=None)


@app.get('/health')
async def health():
    return {'status':'ready','model':MODE,'allocated_gib':round(torch.cuda.memory_allocated()/2**30,2)}


def infer(audio, language, prompt, cancelled):
    started=time.monotonic()
    stop=StoppingCriteriaList([CancelGeneration(cancelled)])
    torch.cuda.reset_peak_memory_stats()
    with torch.inference_mode():
        if MODE=='whisper':
            inputs=processor(audio,sampling_rate=16000,return_tensors='pt',return_attention_mask=True)
            features=inputs.input_features.to('cuda',dtype=torch.float16)
            ids=model.generate(features,attention_mask=inputs.attention_mask.to('cuda'),language=language,
                               task='transcribe',return_timestamps=True,max_length=448,do_sample=False,stopping_criteria=stop)
            decoded=processor.tokenizer.decode(ids[0],skip_special_tokens=True,output_offsets=True)
            result={'text':decoded['text'],'segments':whisper_segments(decoded,len(audio)/16000)}
        else:
            messages=[{'role':'system','content':[{'type':'text','text':'请仅描述可听到的语词、声音事件和语气线索。不要猜测说话者的年龄、身份或个人背景。无法确认时明确说明。'}]}, {'role':'user','content':[{'type':'audio','audio':'local.wav'}, {'type':'text','text':prompt}]}]
            text=processor.apply_chat_template(messages,add_generation_prompt=True,tokenize=False)
            inputs=processor(text=text,audio=[audio],sampling_rate=16000,return_tensors='pt',padding=True)
            inputs=inputs.to('cuda').to(torch.bfloat16)
            ids=model.generate(**inputs,return_audio=False,thinker_max_new_tokens=512,thinker_do_sample=False,thinker_stopping_criteria=stop)
            ids=ids[:,inputs['input_ids'].shape[1]:]
            result={'text':processor.batch_decode(ids,skip_special_tokens=True)[0]}
    result.update(duration=len(audio)/16000,elapsed_seconds=round(time.monotonic()-started,3),
                  peak_allocated_gib=round(torch.cuda.max_memory_allocated()/2**30,3),model=MODE)
    return result


async def handle(request, file, language, prompt):
    if len(language)>8 or len(prompt)>2000:
        raise HTTPException(422,'Invalid language or prompt')
    data=await file.read(64*1024*1024+1)
    await file.close()
    if not data or len(data)>64*1024*1024:
        raise HTTPException(413,'Empty or oversized audio')
    try:
        # Decode through ffmpeg with external protocols disabled and a fixed output bound.
        with tempfile.TemporaryDirectory(prefix='audio-') as temp:
            source=Path(temp)/'input'
            source.write_bytes(data)
            decoded=await command('ffmpeg','-nostdin','-v','error','-protocol_whitelist','file,pipe','-format_whitelist','wav,mp3,flac,ogg,mov,matroska,webm,aac,aiff,asf,avi,mpeg,mpegts','-i',source,
                                  '-t','31','-vn','-ac','1','-ar','16000','-f','f32le','pipe:1',timeout=30)
            audio=normalize_audio(np.frombuffer(decoded,dtype='<f4'),16000)
    except (ValueError,RuntimeError,TimeoutError):
        raise HTTPException(422,'Invalid audio or duration over 30 seconds; use /v1/tasks for longer media')
    return await run_inference(slot,lambda cancelled: infer(audio,language,prompt,cancelled),request)


async def admitted_handle(request,file,language,prompt):
    try:
        return await admit_decode(decode_slot,lambda: handle(request,file,language,prompt))
    finally:
        await file.close()


@app.post('/transcribe')
async def transcribe(request:Request,file:UploadFile=File(...),language:str=Form('zh'),prompt:str=Form('')):
    if MODE!='whisper':
        raise HTTPException(404,'Not a transcription backend')
    return await admitted_handle(request,file,language,prompt)


@app.post('/understand')
async def understand(request:Request,file:UploadFile=File(...),language:str=Form('zh'),prompt:str=Form('请描述听到的声音。')):
    if MODE!='omni':
        raise HTTPException(404,'Not an Omni backend')
    return await admitted_handle(request,file,language,prompt)
