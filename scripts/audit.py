"""Audit Git-visible paths/text/media with an externally supplied private term list."""
from pathlib import Path
import argparse,json,re,subprocess,sys
ROOT=Path(__file__).resolve().parents[1]

def decode(data):
    if data.startswith((b'\xff\xfe',b'\xfe\xff')):return data.decode('utf-16')
    if b'\0' in data:return None
    try:return data.decode('utf-8-sig')
    except UnicodeDecodeError:return None

def main():
    p=argparse.ArgumentParser();p.add_argument('--terms-file',type=Path,required=True);p.add_argument('--output',type=Path);a=p.parse_args()
    terms=json.loads(a.terms_file.read_text(encoding='utf-8-sig'))
    # Alphanumeric boundaries also catch snake_case and hyphenated identifiers.
    patterns=[re.compile(r'(?<![A-Za-z0-9])'+re.escape(t)+r'(?![A-Za-z0-9])',re.I) for t in terms]
    ordinary=[re.compile(r'\b'+re.escape(t)+r'\b',re.I) for t in terms]
    raw=subprocess.check_output(['git','ls-files','--cached','--others','--exclude-standard','-z'],cwd=ROOT)
    paths=sorted(set(x for x in raw.decode().split('\0') if x))
    counts={'paths':0,'text':0,'subtitles':0,'metadata':0,'history':0,'cjk':0,'over_100_mb':0,'lfs_pointers':0}
    hits=[];text_count=0;subtitle_count=0;media_count=0;max_size=0
    def check(text,kind,path):
        for i,(token,word) in enumerate(zip(patterns,ordinary)):
            if token.search(text) or word.search(text):counts[kind]+=1;hits.append({'path':path,'kind':kind,'term_index':i})
    for name in paths:
        check(name,'paths',name);path=ROOT/name
        size=path.stat().st_size;max_size=max(max_size,size)
        if size>100_000_000:counts['over_100_mb']+=1
        data=path.read_bytes();t=decode(data)
        if t is not None:
            text_count+=1;check(t,'text',name)
            if re.search(r'[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\U00020000-\U000323af]',t):counts['cjk']+=1;hits.append({'path':name,'kind':'cjk'})
            if data.startswith(b'version https://git-lfs.github.com/spec/v1'):counts['lfs_pointers']+=1
            if path.suffix.lower() in ['.srt','.vtt','.ass','.ssa']:
                subtitle_count+=1;check(t,'subtitles',name)
        if path.suffix.lower() in ['.png','.jpg','.jpeg','.gif']:
            from PIL import Image
            with Image.open(path) as im:
                encoded=json.dumps({**im.info,'exif':dict(im.getexif())},default=str)
                check(encoded,'metadata',name)
                if re.search(r'GPS|latitude|longitude|location',encoded,re.I):raise AssertionError('Location metadata: '+name)
            media_count+=1
        if path.suffix.lower() in ['.mp4','.mov','.wav']:
            import imageio_ffmpeg
            info=subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(),'-hide_banner','-i',str(path)],capture_output=True,text=True).stderr
            check('\n'.join(l for l in info.splitlines() if 'Input #' not in l),'metadata',name)
            if re.search(r'location\s*:|GPS|latitude|longitude',info,re.I):raise AssertionError('Location metadata: '+name)
            if path.suffix.lower() in ['.mp4','.mov'] and 'Subtitle:' in info:
                decoded=subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(),'-loglevel','error','-i',str(path),'-map','0:s','-f','srt','-'],capture_output=True,text=True,check=True).stdout
                subtitle_count+=1;check(decoded,'subtitles',name)
            media_count+=1
    history=subprocess.run(['git','log','--all','--format=fuller','--name-only'],cwd=ROOT,capture_output=True,text=True)
    if history.returncode==0:check(history.stdout,'history','git history')
    result={'passed':not any(counts.values()),'files':len(paths),'text_files':text_count,'subtitle_sources':subtitle_count,'media_files':media_count,
        'checked_terms':len(terms),'search':'case-insensitive whole words plus identifier-token boundaries; term list kept outside repository',
        'counts':counts,'max_file_bytes':max_size,'tracked_payload_bytes':sum((ROOT/n).stat().st_size for n in paths),
        'spoken_scope':'Only approved synthetic reference texts and a newly generated neutral TTS script are included; no original film or personal recording.',
        'hits':hits}
    if a.output:a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result));return 0 if result['passed'] else 1

if __name__=='__main__':sys.exit(main())
