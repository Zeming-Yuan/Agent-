"""Bounded local preprocessing; all sources are private uploaded file IDs."""
import asyncio
import base64
import json
import os
import signal
import tempfile
from pathlib import Path
from .gateway import acquire


async def command(*args, timeout=120):
    proc = await asyncio.create_subprocess_exec(*map(str,args), stdout=asyncio.subprocess.PIPE,
                                                stderr=asyncio.subprocess.PIPE, start_new_session=True)
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout)
        if proc.returncode:
            raise RuntimeError(f'{Path(str(args[0])).name} failed')
        return stdout
    except BaseException:
        if proc.returncode is None:
            os.killpg(proc.pid, signal.SIGKILL)
            await proc.wait()
        raise


async def process_task(item, store, client, main, whisper, omni, headers, slots, *, audio_enabled=True):
    source = store.path(item['file_id'])
    options = item['options']
    tid = item['id']
    def progress(value):
        store.update(tid, progress=value)

    async def vision(path, prompt):
        encoded = base64.b64encode(path.read_bytes()).decode()
        await acquire(slots)
        try:
            r = await client.post(main+'/v1/chat/completions', headers={**headers,'X-Request-ID':tid},json={
                'model':'spark-main', 'messages':[{'role':'user','content':[
                    {'type':'text','text':prompt}, {'type':'image_url','image_url':{'url':'data:image/png;base64,'+encoded}}]}],
                'max_tokens':512,'chat_template_kwargs':{'enable_thinking':False}})
            r.raise_for_status()
            return r.json()['choices'][0]['message']['content']
        finally:
            slots.release()

    async def audio_segments(folder, duration, kind='transcribe'):
        results=[]
        for i,start in enumerate(range(0, max(1,int(duration+.999)), 30)):
            wav = folder / f'audio-{start}.wav'
            await command('ffmpeg','-nostdin','-v','error','-protocol_whitelist','file,pipe','-format_whitelist','wav,mp3,flac,ogg,mov,matroska,webm,aac,aiff,asf,avi,mpeg,mpegts','-ss',start,'-i',source,
                          '-t',30,'-vn','-ac','1','-ar',16000,'-y',wav)
            endpoint = whisper+'/transcribe' if kind=='transcribe' else omni+'/understand'
            with wav.open('rb') as file:
                r = await client.post(endpoint, files={'file':('segment.wav',file,'audio/wav')},
                                      data={'language':options['language'],'prompt':options['prompt']},headers={'X-Request-ID':tid})
            r.raise_for_status()
            result = r.json()
            result.update(start=start, end=min(duration,start+30))
            for seg in result.get('segments',[]):
                seg['start']+=start
                seg['end']+=start
            results.append(result)
            progress(.05+.9*min(duration,start+30)/max(duration,.001))
        return results

    with tempfile.TemporaryDirectory(prefix='job-',dir=store.root) as temp:
        folder = Path(temp)
        if item['kind']=='pdf':
            # Refuse unbounded documents before rendering any page.
            info = (await command('pdfinfo',source)).decode(errors='replace')
            count = next(int(line.split(':',1)[1].strip()) for line in info.splitlines() if line.startswith('Pages:'))
            if not 1<=count<=20:
                raise ValueError('PDF must contain 1 to 20 pages')
            pages=[]
            for n in range(1,count+1):
                text=(await command('pdftotext','-f',n,'-l',n,'-layout',source,'-')).decode(errors='replace').strip()
                page={'page':n,'text':text[:8000],'truncated':len(text)>8000}
                if len(text)<50:
                    prefix=folder/f'page-{n}'
                    await command('pdftoppm','-f',n,'-l',n,'-scale-to',1280,'-singlefile','-png',source,prefix)
                    page['vision']=await vision(prefix.with_suffix('.png'),f'这是文档第 {n} 页。请提取可见信息，模糊处明确说明。')
                pages.append(page)
                progress(n/count)
            return {'source_file_id':item['file_id'],'pages':pages}
        metadata=json.loads(await command('ffprobe','-v','error','-protocol_whitelist','file,pipe','-format_whitelist','wav,mp3,flac,ogg,mov,matroska,webm,aac,aiff,asf,avi,mpeg,mpegts','-show_format','-show_streams','-of','json',source))
        duration=float(metadata['format']['duration'])
        if not 0<duration<=300:
            raise ValueError('Media duration must be between 0 and 300 seconds')
        if item['kind'] in ('transcribe','audio_understand'):
            segments=await audio_segments(folder,duration,item['kind'])
            return {'source_file_id':item['file_id'],'duration':duration,'segments':segments,'text':'\n'.join(s.get('text','') for s in segments)}
        frames=[]
        for start in range(0,max(1,int(duration)),15):
            path=folder/f'frame-{start}.png'
            await command('ffmpeg','-nostdin','-v','error','-protocol_whitelist','file,pipe','-format_whitelist','wav,mp3,flac,ogg,mov,matroska,webm,aac,aiff,asf,avi,mpeg,mpegts','-ss',start,'-i',source,
                          '-frames:v',1,'-vf','scale=1024:1024:force_original_aspect_ratio=decrease','-y',path)
            frames.append({'timestamp':start,'description':await vision(path,f'视频 {start} 秒处的画面。请描述可见内容。')})
            progress(.5*min(duration,start+15)/duration)
        transcript=await audio_segments(folder,duration) if audio_enabled and any(s['codec_type']=='audio' for s in metadata['streams']) else []
        return {'source_file_id':item['file_id'],'duration':duration,'frames':frames,'transcript':transcript,
                'sampling_interval_seconds':15,'audio_enabled':audio_enabled, 'note':'画面按15秒采样，未采到的事件可能遗漏。'+('音频功能已停用，本任务仅分析画面。' if not audio_enabled else '声音理解请另建 audio_understand 任务。')}
