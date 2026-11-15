"""Ephemeral loopback HTTPS harness shared by stdio integration tests."""
import asyncio
from contextlib import contextmanager
import datetime
import ipaddress
import socket
import threading
import time
import uvicorn
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID


@contextmanager
def https_server(app, tmp_path):
    key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
    name=x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,'Image ephemeral test')])
    now=datetime.datetime.now(datetime.timezone.utc)
    cert=(x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
          .serial_number(x509.random_serial_number()).not_valid_before(now-datetime.timedelta(minutes=1))
          .not_valid_after(now+datetime.timedelta(hours=1))
          .add_extension(x509.BasicConstraints(ca=True,path_length=None),critical=True)
          .add_extension(x509.SubjectAlternativeName([x509.IPAddress(ipaddress.ip_address('127.0.0.1'))]),critical=False)
          .sign(key,hashes.SHA256()))
    cert_path=tmp_path/'test-ca.crt';cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    key_path=tmp_path/'test-tls.key'
    key_path.write_bytes(key.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption()))
    key_path.chmod(0o600)
    sock=socket.socket();sock.bind(('127.0.0.1',0))
    port=sock.getsockname()[1]
    server=uvicorn.Server(uvicorn.Config(app,host='127.0.0.1',port=port,ssl_certfile=str(cert_path),
        ssl_keyfile=str(key_path),log_level='error',access_log=False,ws='none'))
    thread=threading.Thread(target=lambda:asyncio.run(server.serve(sockets=[sock])),daemon=True)
    thread.start()
    try:
        deadline=time.monotonic()+5
        while not server.started and time.monotonic()<deadline:threading.Event().wait(.01)
        assert server.started
        yield port, cert_path
    finally:
        server.should_exit=True;thread.join(timeout=5);sock.close()
        assert not thread.is_alive(),'TLS test server failed to stop'


def synthetic_resources(*, available=60*1024**3, wait_timeout=2., fault=None):
    import time
    import dataclasses
    from services.image_telemetry import ResourceSample
    from services.image_resources import MemoryBudget
    def sample(tid):
        row = ResourceSample(60*1024**3,50*1024**3,time.monotonic(),frozenset(),(),2,
            release_proven=True,release_task_id=tid,host_id='host',runtime_hash='runtime',session_id='session')
        return dataclasses.replace(row, available_bytes=available, release_task_id=tid,
                                   release_epoch=time.monotonic_ns(), **(fault or {}))
    envelope = {'sizes': ['1024x1024','1152x896','896x1152','1280x768','768x1280'],
                'max_references': 3, 'max_reference_pixels': 16_000_000, 'foreground': True,
                'max_prompt_chars': 4000, 'max_title_chars': 60}
    return {'resource_sampler': sample,
            'memory_budgets': {p: MemoryBudget(10*1024**3, 2*1024**3, 20*1024**3,
                time.monotonic()+3600, 'runtime') for p in ('generate','fast','standard','high')},
            'resource_settings': {'max_age': 1., 'stable_window': .02, 'wait_timeout': wait_timeout,
                                  'input_envelopes': {p: dict(envelope) for p in ('generate','fast','standard','high')}},
            'image_runtime_hash': 'runtime'}



def image_app(*args, **kwargs):
    """Existing integration fixtures explicitly inject synthetic external resources."""
    from services.gateway import create_app
    return create_app(*args, **{**synthetic_resources(), **kwargs})
