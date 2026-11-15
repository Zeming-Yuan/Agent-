"""T06 public bridge/MCP recovery against the real owner-aware HTTP app."""
import asyncio
import json
from pathlib import Path

import httpx
import pytest

from client.spark_image_tools import ImageBridge, build_server

CA = Path(__file__).resolve().parents[1] / 'certificates/agent-root-ca.crt'


class GatewayTransport(httpx.AsyncBaseTransport):
    """Keep real auth, SQLite, routes and worker; inject only network loss."""
    def __init__(self, gateway, *, journal=None, drop_submit=False):
        self.gateway = gateway
        self.journal = journal
        self.drop_submit = drop_submit
        self.requests = []

    async def handle_async_request(self, request):
        self.requests.append(request)
        if request.method == 'POST' and request.url.path == '/v1/tasks':
            from client.request_journal import RequestJournal
            records = RequestJournal(self.journal, 'https://spark.invalid/v1', 'A').pending()
            assert request.headers['idempotency-key'] in {r['request_id'] for r in records}
        response = await asyncio.to_thread(
            self.gateway.request, request.method, str(request.url),
            headers=dict(request.headers), content=await request.aread())
        if self.drop_submit and request.method == 'POST' and request.url.path == '/v1/tasks':
            self.drop_submit = False
            assert response.status_code == 202, response.text
            raise httpx.ReadError('accepted response lost', request=request)
        return httpx.Response(response.status_code, headers=response.headers, content=response.content)


def bridge_for(env, tmp_path, transport, *, owner='A', service='https://spark.invalid/v1'):
    return ImageBridge(service, env.keys[owner], CA, tmp_path/'out',
                       journal_path=tmp_path/'requests.sqlite3', transport=transport)


def test_tb06_lost_response_replays_after_bridge_restart(owner_env, tmp_path):
    backend = owner_env.new_backend()
    with owner_env.client(backend=backend, run_worker=True) as gateway:
        transport = GatewayTransport(gateway, journal=tmp_path/'requests.sqlite3', drop_submit=True)

        async def run():
            one = bridge_for(owner_env, tmp_path, transport)
            try:
                with pytest.raises(Exception, match='accepted response lost'):
                    await build_server(one).call_tool('generate_image', {'prompt':'fixture', 'request_id':'r1'})
            finally:
                await one.close()
            original = gateway.get('/v1/tasks', headers=owner_env.auth('A')).json()['data'][0]['id']
            two = bridge_for(owner_env, tmp_path, transport)
            try:
                result = await build_server(two).call_tool('generate_image', {'prompt':'fixture', 'request_id':'r1'})
                content = result[0] if isinstance(result, tuple) else result
                state = json.loads(next(x.text for x in content if x.type == 'text'))
                assert state['id'] == original
                owner_env.wait_task(gateway, original, 'A', lambda t: t['status'] == 'completed')
                assert len(backend.jobs) == 1
            finally:
                await two.close()
        asyncio.run(run())


def test_tb06_new_intent_and_conflict(owner_env, tmp_path):
    with owner_env.client() as gateway:
        transport = GatewayTransport(gateway, journal=tmp_path/'requests.sqlite3')

        async def run():
            bridge = bridge_for(owner_env, tmp_path, transport)
            try:
                first = await bridge.generate('fixture','1024x1024',0,'','',request_id='r')
                replay = await bridge.generate('fixture','1024x1024',0,'','',request_id='r')
                assert replay['id'] == first['id']
                count = len(transport.requests)
                with pytest.raises(ValueError, match='different input'):
                    await bridge.generate('changed','1024x1024',0,'','',request_id='r')
                assert not any(r.method == 'POST' for r in transport.requests[count:])
                new = await bridge.generate('fixture','1024x1024',0,'','')
                assert new['id'] != first['id']
                assert new['request_id'] != 'r'
                from client.request_journal import RequestJournal
                records = RequestJournal(tmp_path/'requests.sqlite3','https://spark.invalid/v1','A').pending()
                assert {r['task_id'] for r in records} == {first['id'],new['id']}
                assert owner_env.keys['A'].encode() not in (tmp_path/'requests.sqlite3').read_bytes()
            finally:
                await bridge.close()
        asyncio.run(run())
