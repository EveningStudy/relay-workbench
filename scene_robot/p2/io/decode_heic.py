"""Decode human HEIC inputs locally without modifying the originals."""
import argparse
import hashlib
import json
from pathlib import Path
from PIL import Image, ImageOps
from pi_heif import register_heif_opener


def decode(source, output):
    register_heif_opener()
    out=Path(output);out.mkdir(parents=True,exist_ok=True);rows=[]
    manifest=out/'decode_manifest.json';previous={r['source']:r['sha256'] for r in json.loads(manifest.read_text())} if manifest.exists() else {}
    for path in sorted(Path(source).glob('*')):
        if path.suffix.lower() not in ('.heic','.heif'):continue
        dst=out/(path.stem+'.png')
        digest=hashlib.sha256(path.read_bytes()).hexdigest()
        with Image.open(path) as original:
            exif=original.getexif()
            camera_exif=exif.get_ifd(34665)
            image=ImageOps.exif_transpose(original).convert('RGB')
            if not dst.exists() or previous.get(str(path))!=digest:image.save(dst,compress_level=3)
            thumb=image.copy();thumb.thumbnail((640,640));thumb.save(out/(path.stem+'_preview.jpg'),quality=90)
            rows.append({'source':str(path),'decoded':str(dst),'size':list(image.size),
                         'sha256':digest,
                         'focal_length':str(camera_exif.get(37386,'')),'lens_model':str(camera_exif.get(42036,'')),
                         'digital_zoom':str(camera_exif.get(41988,'')),
                         'orientation':exif.get(274),'source_kind':'real'})
        print(path.name,rows[-1]['size'],flush=True)
    (out/'decode_manifest.json').write_text(json.dumps(rows,indent=2))
    return rows


def main():
    p=argparse.ArgumentParser();p.add_argument('source');p.add_argument('output');a=p.parse_args()
    print(json.dumps({'decoded':len(decode(a.source,a.output))}))


if __name__=='__main__':main()
