"""Build one private bundle from explicit personal configuration and platform assets."""
import argparse
import json
import os
import re
import ssl
import zipfile
from pathlib import Path, PurePosixPath
from urllib.parse import urlsplit

ROOT=Path(__file__).resolve().parents[1]


def build_bundle(config_path: Path, platform_assets: dict[str,Path], output_path: Path) -> Path:
    config_path=Path(config_path).expanduser().resolve()
    config=json.loads(config_path.read_text())
    url=urlsplit(config['base_url'])
    if url.scheme!='https' or not url.hostname or url.path.rstrip('/')!='/v1' or url.username or url.password or url.query or url.fragment:
        raise ValueError('Use the HTTPS service URL ending in /v1 without credentials or query')
    def personal(name):
        path=Path(config[name]).expanduser()
        return path if path.is_absolute() else config_path.parent/path
    key=personal('api_key_file').read_bytes()
    token=key.decode().strip()
    if len(token)<16 or any(ord(c)<33 or ord(c)>126 for c in token):raise ValueError('Invalid personal credential file')
    ca=personal('ca_file')
    ssl.create_default_context(cafile=str(ca))
    bundled={'base_url':config['base_url'].rstrip('/'),'api_key_file':'api_key','ca_file':'agent-root-ca.crt',
             'output_dir':config.get('output_dir','~/Pictures/Spark Agent'),'journal_path':'requests.sqlite3'}
    files={
        'spark_image_tools.py':b'from client.spark_image_tools import main\n\nif __name__ == "__main__":\n    main()\n',
        'client/__init__.py':b'',
        'client/spark_image_tools.py':(ROOT/'client/spark_image_tools.py').read_bytes(),
        'client/request_journal.py':(ROOT/'client/request_journal.py').read_bytes(),
        'api_key':key,'agent-root-ca.crt':ca.read_bytes(),
        'spark-image.json':json.dumps(bundled,ensure_ascii=False,indent=2).encode(),
        'requirements.txt':(ROOT/'client/image-tools-requirements.txt').read_bytes(),
    }
    for name,source in platform_assets.items():
        path=PurePosixPath(name)
        source=Path(source)
        # Only explicitly selected platform code/docs. Never sweep a runtime directory.
        if (str(path)!=name or path.is_absolute() or '..' in path.parts or '\\' in name or ':' in name or not path.parts
                or any(p.startswith('.') for p in path.parts) or path.parts[0].casefold()=='client'
                or any(p.endswith(('.', ' ')) or re.search(r'[<>:"|?*\x00-\x1f\x7f]',p)
                       or re.fullmatch(r'(?i:con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\..*)?',p) for p in path.parts)
                or any(name.casefold()==p.casefold() or name.casefold().startswith(p.casefold()+'/')
                       or p.casefold().startswith(name.casefold()+'/') for p in files)
                or path.suffix.lower() not in {'.md','.command','.ps1','.py'}
                or source.suffix.lower()!=path.suffix.lower()
                or source.is_symlink() or not source.is_file()):
            raise ValueError('Invalid platform asset: '+name)
        files[name]=source.read_bytes()
    output_path=Path(output_path).expanduser()
    output_path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    fd=os.open(output_path,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
    try:
        with os.fdopen(fd,'wb') as out:
            with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as archive:
                for name,data in files.items():
                    entry=zipfile.ZipInfo('SparkImageTools/'+name)
                    entry.external_attr=0o100600<<16
                    entry.compress_type=zipfile.ZIP_DEFLATED
                    archive.writestr(entry,data)
            out.flush();os.fsync(out.fileno())
    except BaseException:
        output_path.unlink(missing_ok=True)
        raise
    return output_path


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',required=True,type=Path)
    parser.add_argument('--output',required=True,type=Path)
    parser.add_argument('--asset',action='append',default=[],metavar='NAME=PATH')
    args=parser.parse_args()
    assets={}
    for item in args.asset:
        name,sep,path=item.partition('=')
        if not sep or name in assets:parser.error('Use distinct --asset NAME=PATH inputs')
        assets[name]=Path(path)
    build_bundle(args.config,assets,args.output)
    print('Private bundle created:',args.output)


if __name__=='__main__':main()
