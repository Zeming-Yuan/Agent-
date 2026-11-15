"""Build a private Mac MCP integration bundle; never print credentials."""
import json, shutil, zipfile
from pathlib import Path
root=Path(__file__).resolve().parents[1]
out=root/'.private/mac-image-tools';out.mkdir(parents=True,exist_ok=True,mode=0o700)
for p in (root/'client/mac').iterdir():
 if p.is_file():shutil.copy2(p,out/p.name)
shutil.copy2(root/'client/spark_image_tools.py',out/'spark_image_tools.py')
shutil.copy2(root/'certificates/agent-root-ca.crt',out/'agent-root-ca.crt')
shutil.copy2(root/'.private/agent-api.key',out/'api_key');(out/'api_key').chmod(0o600)
(out/'spark-image.json').write_text(json.dumps({'base_url':'https://192.168.10.77:18443/v1','api_key_file':'api_key','ca_file':'agent-root-ca.crt','output_dir':'~/Pictures/Spark Agent'},ensure_ascii=False,indent=2))
bundle=root/'.private/mac-image-tools.zip'
with zipfile.ZipFile(bundle,'w',zipfile.ZIP_DEFLATED) as z:
 for p in out.iterdir():
  if p.is_file():z.write(p,'SparkImageTools/'+p.name)
bundle.chmod(0o600)
print('Private bundle:',bundle,'bytes:',bundle.stat().st_size)
