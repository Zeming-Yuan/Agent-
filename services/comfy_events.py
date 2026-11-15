"""ComfyUI fixed-graph event normalization; unowned messages are ignored."""
import json
import asyncio
from urllib.parse import urlencode, urlsplit, urlunsplit


class ComfyEventStream:
    def __init__(self, url: str, client_id: str):
        self.client_id = client_id
        parts = urlsplit(url)
        self.url = urlunsplit(('wss' if parts.scheme == 'https' else 'ws', parts.netloc,
                               parts.path.rstrip('/') + '/ws', urlencode({'clientId': client_id}), ''))
        self.socket = None

    async def __aenter__(self):
        from websockets.asyncio.client import connect
        self.socket = await connect(self.url, proxy=None, open_timeout=3, close_timeout=2,
                                    max_size=1024*1024)
        try:
            first = json.loads(await asyncio.wait_for(self.socket.recv(), 3))
            if first.get('type') != 'status' or first.get('data', {}).get('sid') != self.client_id:
                raise ValueError('Unconfirmed event subscription')
        except BaseException:
            await self.socket.close()
            raise
        return self

    async def __aexit__(self, *exc):
        await self.socket.close()

    async def events(self):
        async for message in self.socket:
            if not isinstance(message, str):
                continue  # binary previews are not evidence of step progress
            try:
                event = json.loads(message)
            except ValueError:
                continue
            if isinstance(event, dict):
                yield event


def normalize_event(event: dict, prompt_id: str, active_node: str | None) -> dict | None:
    if not isinstance(event, dict) or not isinstance(event.get('data'), dict):
        return None
    data = event['data']
    if data.get('prompt_id') != prompt_id:
        return None
    kind = event.get('type')
    node = data.get('node')
    if kind == 'executing':
        stage = {'1': 'loading', '2': 'loading', '3': 'loading', '4': 'loading',
                 '5': 'loading', '6': 'loading', '10': 'loading', '11': 'loading',
                 '12': 'loading', '20': 'loading', '21': 'loading', '22': 'loading',
                 '7': 'generating', '8': 'saving', '9': 'saving'}.get(node)
        if stage:
            return {'type': 'stage', 'stage': stage, 'node': node}
    if kind == 'execution_error':
        return {'type': 'backend_error'}
    if kind == 'progress' and active_node == '7' and node in (None, '7'):
        value, maximum = data.get('value'), data.get('max')
        if type(value) is int and type(maximum) is int and 0 <= value <= maximum and maximum > 0:
            return {'type': 'progress', 'step': value, 'steps': maximum}
    return None
