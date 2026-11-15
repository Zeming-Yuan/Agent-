# Reproduce T09 offline checks

Run in the controlled source checkout. The original product supplies the supported virtualenv; no invented npm/build/type command is substituted. In the original directory `.venv/bin/python` resolves to the same interpreter. Commands originate from README/T09 plan; selections narrow to modified interfaces and fixtures per user instruction.

```bash
/home/clusteradmin/Desktop/Agent多模态服务/.venv/bin/python -m pytest --collect-only -q -k tb09_safe_admission
/home/clusteradmin/Desktop/Agent多模态服务/.venv/bin/python -m pytest -q -k tb09_safe_admission
/home/clusteradmin/Desktop/Agent多模态服务/.venv/bin/python -m pytest -q -k 'tb09 or tb07 or unknown_submit_outcome or unavailable_backend_rejects'
/home/clusteradmin/Desktop/Agent多模态服务/.venv/bin/python -m pytest -q tests/test_tb09_safe_admission.py tests/test_tb07_lifecycle.py tests/test_tb07_stdio.py tests/test_tb08_memory_evidence.py tests/test_images.py tests/test_image_cancel.py tests/test_image_gateway.py tests/test_image_uncertain.py tests/test_image_admission.py tests/test_tb01_legacy_expand.py tests/test_tb02_owner_files.py tests/test_tb03_owner_tasks.py tests/test_tb04_owner_contract.py tests/test_tb05_server_resume.py tests/test_tb06_mcp_resume.py tests/test_tb06_mcp_stdio.py
bash -n deploy/run-image.sh deploy/run-gateway-runtime.sh
```

CLI is automatically exercised via a child process in test_tb09_config_cli_uses_approval_pin_and_reports_nonzero_without_it with temporary private synthetic files only. Do not copy those values into production. No configured type/lint/build/CI/Compose/seed/security/mutation command exists (N/A). Affected tests do not constitute a full gate or physical/platform acceptance.
