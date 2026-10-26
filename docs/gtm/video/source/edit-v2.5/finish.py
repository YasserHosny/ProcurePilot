"""Encode body, append approved outro frames, mux audio, probe and make review sheets."""
from paths import ROOT,FF,jobs
from make_data import MARKETS
import json,subprocess,shutil
from PIL import Image,ImageDraw
from audio import measure

def call(args,log):
    p=subprocess.run([FF,'-hide_banner','-nostdin','-y',*map(str,args)],capture_output=True,text=True)
    (ROOT/'proof'/log).write_text(p.stderr);p.check_returncode()

def main():
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--only');args=parser.parse_args()
    (ROOT/'tmp').mkdir(exist_ok=True);(ROOT/'sheets').mkdir(exist_ok=True)
    report=json.loads((ROOT/'proof/final-audio.json').read_text()) if args.only and (ROOT/'proof/final-audio.json').exists() else {}
    markets=json.loads((ROOT/'timeline.json').read_text())
    for market,lang,fmt in jobs(markets,args.only):
            key=f'{market}-{lang}-{fmt}';_,_,folder,stem,_=MARKETS[market]
            dst=(ROOT/'../../cuts'/folder).resolve();dst.mkdir(parents=True,exist_ok=True)
            body=markets[market][fmt]['body']
            aspect='16x9' if fmt=='h' else '9x16';suffix='' if lang=='ar' else '-en'
            frames=ROOT/f'frames-{key}';count=round(body*30)
            assert len(list(frames.glob('*.jpg')))==count,f'Missing rendered frames: {frames}'
            bodyfile=ROOT/'tmp'/f'body-{key}.mp4'
            call(['-framerate','30','-i',frames/'%05d.jpg','-frames:v',count,'-c:v','libx264','-crf','18','-preset','medium','-threads','4','-pix_fmt','yuv420p','-an',bodyfile],f'encode-{key}.log')
            outro=(ROOT/'../../renders'/f'outro-{aspect}{suffix}.mp4').resolve()
            # Concat demuxer's automatic AVC bitstream conversion preserves approved outro frames.
            # Both inputs are H.264 / yuv420p / 30 fps at the same native output resolution.
            listing=ROOT/'tmp'/f'concat-{key}.txt'
            listing.write_text("file '"+str(bodyfile)+"'\nfile '"+str(outro)+"'\n")
            final=dst/(stem.format(lang=lang)+f'-{aspect}.mp4')
            call(['-f','concat','-safe','0','-i',listing,'-i',ROOT/'audio'/f'{key}.m4a','-map','0:v','-map','1:a','-c:v','copy','-c:a','copy','-movflags','+faststart',final],f'mux-{key}.log')
            # Full final-cut ffprobe proof when ffprobe is installed on the render host.
            probe=shutil.which('ffprobe')
            if probe:
                p=subprocess.run([probe,'-v','error','-show_entries','format=duration:stream=codec_type,codec_name,width,height,r_frame_rate','-of','json',str(final)],capture_output=True,text=True,check=True)
                data=json.loads(p.stdout);video=next(s for s in data['streams'] if s['codec_type']=='video');audio=next(s for s in data['streams'] if s['codec_type']=='audio')
                assert (video['width'],video['height'])==((1920,1080) if fmt=='h' else (1080,1920))
                assert video['r_frame_rate']=='30/1' and video['codec_name']=='h264' and audio['codec_name']=='aac'
                (ROOT/'proof'/f'{key}-ffprobe.json').write_text(p.stdout);print('FFPROBE',final.name,p.stdout,flush=True)
            else:print('FFPROBE_UNAVAILABLE: install-free render host must supply ffprobe for requested proof',flush=True)
            report[key]=measure(final)
            assert report[key]['true_peak_dbfs']<=-2
            assert abs(report[key]['integrated_lufs']+14)<=1
            sheet_frames=ROOT/'sheets'/f'{key}';sheet_frames.mkdir(exist_ok=True)
            call(['-i',final,'-vf',"select='not(mod(n,60))',scale=384:-1",'-fps_mode','vfr','-q:v','3',sheet_frames/'%03d.jpg'],f'sheet-{key}.log')
            thumbs=sorted(sheet_frames.glob('*.jpg'));tw,th=Image.open(thumbs[0]).size
            sheet=Image.new('RGB',(tw*6,(th+30)*((len(thumbs)+5)//6)),'#F4F6F9');draw=ImageDraw.Draw(sheet)
            for i,p in enumerate(thumbs):
                x=(i%6)*tw;y=(i//6)*(th+30);sheet.paste(Image.open(p),(x,y+30));draw.text((x+8,y+8),f'{i*2:03d}s',fill='#0B2545')
            sheet.save(ROOT/'sheets'/f'{key}-every-2s.jpg',quality=92)
    (ROOT/'proof/final-audio.json').write_text(json.dumps(report,indent=2)+'\n')
if __name__=='__main__':main()
