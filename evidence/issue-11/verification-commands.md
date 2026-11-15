# Reproduce T10 affected checks

Run in controlled checkout or reviewed original delivery. Interpreter is the README-supported original .venv; commands from T10 plan/pytest. No full suite or invented checker command.

```bash
/home/clusteradmin/Desktop/Agent多模态服务/.venv/bin/python -m pytest --collect-only -q -k tb10_fair_queue
/home/clusteradmin/Desktop/Agent多模态服务/.venv/bin/python -m pytest -q -k tb10_fair_queue
/home/clusteradmin/Desktop/Agent多模态服务/.venv/bin/python -m pytest -q -k 'tb10 or tb09 or bounded_task_queue or image_task_validation'
/home/clusteradmin/Desktop/Agent多模态服务/.venv/bin/python -m pytest -q tests/test_tb10_fair_queue.py tests/test_tb09_safe_admission.py tests/test_tb07_lifecycle.py tests/test_tb07_stdio.py tests/test_images.py tests/test_image_cancel.py tests/test_image_gateway.py tests/test_image_uncertain.py tests/test_image_admission.py tests/test_image_bridge.py tests/test_tb01_legacy_expand.py tests/test_tb02_owner_files.py tests/test_tb03_owner_tasks.py tests/test_tb04_owner_contract.py tests/test_tb05_server_resume.py tests/test_tb06_mcp_resume.py tests/test_tb06_mcp_stdio.py
```

No type/lint/build/CI/Compose/security/mutation/seed gate configured (N/A). No deploy/guard scripts modified. Actual GPU, production config/service/restore and Windows/macOS desktop Harness not exercised. Loopback TLS/stdio uses temporary generated certificates/test Key and external resource/inference substitutes only.
