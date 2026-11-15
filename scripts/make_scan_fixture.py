from pathlib import Path
import subprocess,zlib
from PIL import Image
root=Path('/samples')
subprocess.run(['pdftoppm','-f','1','-l','1','-scale-to','1280','-singlefile','-png',str(root/'invoice.pdf'),str(root/'invoice-render')],check=True)
image=Image.open(root/'invoice-render.png').convert('RGB');w,h=image.size
pixels=zlib.compress(image.tobytes())
objs=[b'<< /Type /Catalog /Pages 2 0 R >>',b'<< /Type /Pages /Kids [3 0 R] /Count 1 >>',b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /XObject << /Im0 5 0 R >> >> /Contents 4 0 R >>']
stream=b'q 612 0 0 792 0 0 cm /Im0 Do Q'
objs.append(b'<< /Length '+str(len(stream)).encode()+b' >>\nstream\n'+stream+b'\nendstream')
objs.append(f'<< /Type /XObject /Subtype /Image /Width {w} /Height {h} /ColorSpace /DeviceRGB /BitsPerComponent 8 /Filter /FlateDecode /Length {len(pixels)} >>\nstream\n'.encode()+pixels+b'\nendstream')
out=bytearray(b'%PDF-1.4\n');pos=[0]
for i,obj in enumerate(objs,1):pos.append(len(out));out.extend(str(i).encode()+b' 0 obj\n'+obj+b'\nendobj\n')
xref=len(out);out.extend(b'xref\n0 6\n0000000000 65535 f \n')
for n in pos[1:]:out.extend(f'{n:010d} 00000 n \n'.encode())
out.extend(f'trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n'.encode());(root/'scanned-invoice.pdf').write_bytes(out)
