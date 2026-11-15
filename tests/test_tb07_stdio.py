"""T07: actual stdio MCP and TLS, with only external inference held at barriers."""
import asyncio
import json
import os
from pathlib import Path
import sys
import threading

import httpx
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from services.gateway import create_app
from image_test_harness import https_server


def test_tb07_lifecycle_stdio_loading_saving_and_cancel_cleanup(owner_env, tmp_path):
    backend = owner_env.new_backend(hold=True, hold_stop=True)
    view_entered = threading.Event(); release_view = threading.Event()
    async def external(request):
        if request.url.path == '/view':
            view_entered.set()
            assert await asyncio.to_thread(release_view.wait, 5)
        return await backend(request)
    app = create_app(owner_env.root, owner_env.keys['legacy'], key_registry=owner_env.registry,
        identity_mode='staging', transport=httpx.MockTransport(external), run_worker=True,
        audio_enabled=False, images_enabled=True, event_stream_factory=backend.event_stream)
    with https_server(app, tmp_path) as (port, cert):
        personal = tmp_path/'personal.key'; personal.write_text(owner_env.keys['A']); personal.chmod(0o600)
        config = tmp_path/'client.json'
        config.write_text(json.dumps({'base_url': f'https://127.0.0.1:{port}/v1', 'api_key_file': str(personal),
            'ca_file': str(cert), 'output_dir': str(tmp_path/'图片 output'), 'journal_path': str(tmp_path/'journal.sqlite3')}))
        script = Path(__file__).resolve().parents[1]/'client/spark_image_tools.py'
        async def run():
            params = StdioServerParameters(command=sys.executable, args=[str(script), '--config', str(config)],
                env={k:v for k,v in os.environ.items() if k != 'PYTHONPATH'}, cwd=tmp_path)
            with open(os.devnull, 'w') as errors:
                async with stdio_client(params, errlog=errors) as (read, write):
                    async with ClientSession(read, write) as session:
                        await session.initialize()
                        async def call(name, arguments):
                            response = await session.call_tool(name, arguments)
                            assert not response.isError, response
                            return response
                        def state(response):
                            return json.loads(next(c.text for c in response.content if c.type == 'text'))
                        submitted = state(await call('generate_image', {'prompt': 'fixture', 'request_id': 't07-stdio'}))
                        tid = submitted['id']
                        assert await asyncio.to_thread(backend.started.wait, 2)
                        loading = state(await call('get_image_task', {'task_id': tid, 'wait_seconds': 0}))
                        assert loading['stage_text'] == '加载模型' and loading['steps'] is None
                        assert 'progress' not in loading
                        backend.finish.set()
                        assert await asyncio.to_thread(view_entered.wait, 2)
                        saving = state(await call('get_image_task', {'task_id': tid, 'wait_seconds': 0}))
                        assert saving['stage_text'] == '保存图片'
                        release_view.set()
                        result = await call('get_image_task', {'task_id': tid, 'wait_seconds': 20})
                        assert any(c.type == 'image' for c in result.content)
                        assert next((tmp_path/'图片 output').glob('*.png')).read_bytes() == backend.png
                        backend.started.clear(); backend.finish.clear()
                        cancelled = state(await call('generate_image', {'prompt': 'fixture', 'request_id': 't07-cancel'}))['id']
                        assert await asyncio.to_thread(backend.started.wait, 2)
                        cancelling = state(await call('cancel_image_task', {'task_id': cancelled}))
                        assert cancelling['status'] == 'running' and cancelling['stage'] == 'cancelling'
                        assert '后台停止' in cancelling['stage_text']
                        listing = state(await call('list_image_tasks', {}))
                        assert next(t for t in listing['data'] if t['id'] == cancelled)['stage'] == 'cancelling'
                        backend.release_stop.set()
                        for _ in range(100):
                            listing = state(await call('list_image_tasks', {}))
                            task = next(t for t in listing['data'] if t['id'] == cancelled)
                            if task['status'] == 'cancelled': break
                            await asyncio.sleep(.01)
                        assert task['status'] == 'cancelled' and not backend.running
                        assert len(backend.jobs) == 2
        try:
            asyncio.run(run())
        finally:
            release_view.set(); backend.finish.set(); backend.release_stop.set()
