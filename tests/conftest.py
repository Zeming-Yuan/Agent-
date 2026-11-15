import asyncio
import io
import json
import threading
import queue
import time
import uuid
from types import SimpleNamespace
import httpx
import pytest
from fastapi.testclient import TestClient
from PIL import Image
from image_test_harness import image_app as create_app
from services.identity import KeyRegistry

class BackendEvents:
    """Controlled external WebSocket boundary; never replaces gateway state."""
    def __init__(self, backend):
        self.backend = backend
    async def __aenter__(self):
        self.backend.events_connected.set()
        return self
    async def __aexit__(self, *exc):
        return False
    async def events(self):
        while True:
            try:
                event = self.backend.events_to_emit.get_nowait()
            except queue.Empty:
                await asyncio.sleep(.01)
            else:
                yield event


@pytest.fixture(autouse=True)
def isolate_comfy_websocket(request, monkeypatch):
    # Only the local protocol test may open a socket. Other tests inject the
    # external event boundary, including legacy fixtures with HTTP-only backends.
    if request.node.name == 'test_tb07_real_websocket_subscribes_before_prompt_and_filters_reconnect':
        return
    class QuietEvents:
        def __init__(self, url, client_id):
            pass
        async def __aenter__(self):
            return self
        async def __aexit__(self, *exc):
            return False
        async def events(self):
            await asyncio.Event().wait()
            yield  # async generator, deliberately no invented backend events
    monkeypatch.setattr('services.comfy_events.ComfyEventStream', QuietEvents)


class ImageBackend:
    def __init__(self,hold=False,hold_stop=False):
        self.jobs=[]; self.running=set(); self.known=set()
        self.events_to_emit=queue.Queue(); self.events_connected=threading.Event()
        self.started=threading.Event(); self.finish=threading.Event()
        self.release_stop=threading.Event(); self.offline=threading.Event()
        if not hold: self.finish.set()
        if not hold_stop: self.release_stop.set()
        buf=io.BytesIO(); Image.new("RGB",(8,8),"green").save(buf,format="PNG")
        self.png=buf.getvalue()
    def event_stream(self, url, client_id):
        return BackendEvents(self)
    async def __call__(self,req):
        p=req.url.path
        if p=="/system_stats":
            return httpx.Response(503 if self.offline.is_set() else 200,json={"system":{}})
        if p=="/health": return httpx.Response(200,json={"status":"ready"})
        if p=="/queue" and req.method=="GET":
            return httpx.Response(200,json={"queue_running":[[0,x,{}, {}, []] for x in self.running],"queue_pending":[]})
        if p=="/queue": return httpx.Response(200,json={})
        if p=="/interrupt":
            pid=json.loads(req.content).get("prompt_id")
            if pid in self.running:
                stopped=await asyncio.to_thread(self.release_stop.wait,2.0)
                if not stopped: return httpx.Response(503,json={"error":"stop held"})
                self.running.discard(pid)
                self.known.discard(pid)
            elif pid is None:
                self.running.clear()
            return httpx.Response(200,json={})
        if p=="/prompt":
            body=json.loads(req.content); pid=body.get("prompt_id", "")
            try:
                if str(uuid.UUID(pid)) != pid: raise ValueError("noncanonical UUID")
            except (ValueError, AttributeError):
                return httpx.Response(400,json={"error":"prompt_id must be a canonical UUID"})
            self.jobs.append(body); self.running.add(pid); self.known.add(pid); self.started.set()
            return httpx.Response(200,json={"prompt_id":pid})
        if p.startswith("/history/"):
            pid=p.rsplit("/",1)[-1]
            if pid not in self.known or not self.finish.is_set(): return httpx.Response(200,json={})
            self.running.discard(pid)
            return httpx.Response(200,json={pid:{"status":{"completed":True,"status_str":"success"},
                "outputs":{"9":{"images":[{"filename":"fixture.png","subfolder":"","type":"output"}]}}}})
        if p=="/history":
            body=json.loads(req.content)
            if body.get("clear"): self.known.clear()
            for pid in body.get("delete", []): self.known.discard(pid)
            return httpx.Response(200,json={})
        if p=="/free": return httpx.Response(200,json={})
        if p=="/upload/image": return httpx.Response(200,json={"name":"fixture.png","subfolder":""})
        if p=="/view": return httpx.Response(200,content=self.png)
        return httpx.Response(404,json={"error":"unexpected backend path"})

@pytest.fixture
def owner_env(tmp_path):
    registry=KeyRegistry(tmp_path/"keys.sqlite3")
    keys={o:registry.issue(o) for o in ("legacy","A","B")}
    env=SimpleNamespace(root=tmp_path/"runtime",registry=registry,keys=keys,new_backend=ImageBackend)
    env.auth=lambda owner:{"Authorization":"Bearer "+keys[owner]}
    def client(*,backend=None,run_worker=False,identity_mode="staging",event_stream_factory=None):
        backend=backend or ImageBackend()
        event_args = {} if event_stream_factory is None else {'event_stream_factory': event_stream_factory}
        app=create_app(env.root,keys["legacy"],key_registry=registry,
            identity_mode=identity_mode,transport=httpx.MockTransport(backend),
            run_worker=run_worker,audio_enabled=False,images_enabled=True,**event_args)
        return TestClient(app)
    env.client=client
    def upload(c,owner="A"):
        png=ImageBackend().png
        r=c.post("/v1/files",headers=env.auth(owner),files={"file":("fixture.png",png,"image/png")})
        assert r.status_code==200,r.text
        return r.json()["id"]
    env.upload=upload
    def submit(c,owner="A",*,kind="image_generate",request_key=None,**options):
        headers=env.auth(owner)
        if request_key is not None: headers["Idempotency-Key"]=request_key
        return c.post("/v1/tasks",headers=headers,json={"kind":kind,"options":{"prompt":"fixture",**options}})
    env.submit=submit
    def wait_task(c,tid,owner,predicate,timeout=3.0):
        deadline=time.monotonic()+timeout; last=None
        while time.monotonic()<deadline:
            r=c.get("/v1/tasks/"+tid,headers=env.auth(owner)); assert r.status_code==200,r.text
            last=r.json()
            if predicate(last): return last
            threading.Event().wait(.01)
        raise AssertionError(f"task did not converge: {last}")
    env.wait_task=wait_task
    return env


@pytest.fixture
def legacy_services():
    """Import the immutable pre-T01 services independently of the live package."""
    import hashlib
    import importlib
    from pathlib import Path
    import sys
    from types import ModuleType
    import uuid
    import zipfile

    folder = Path(__file__).parent / 'fixtures'
    archive_path = folder / 't01-legacy-services.zip'
    manifest = json.loads((folder / 't01-legacy-manifest.json').read_text())
    with zipfile.ZipFile(archive_path) as archive:
        assert set(archive.namelist()) == set(manifest['files'])
        for name, digest in manifest['files'].items():
            assert hashlib.sha256(archive.read(name)).hexdigest() == digest, name
    name = 't01_legacy_' + uuid.uuid4().hex
    package = ModuleType(name)
    package.__path__ = [str(archive_path) + '/services']
    sys.modules[name] = package
    try:
        yield SimpleNamespace(
            create_app=importlib.import_module(name + '.gateway').create_app,
            Store=importlib.import_module(name + '.store').Store,
        )
    finally:
        for module in list(sys.modules):
            if module == name or module.startswith(name + '.'):
                del sys.modules[module]
