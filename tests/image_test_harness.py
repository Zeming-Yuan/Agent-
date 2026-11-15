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
