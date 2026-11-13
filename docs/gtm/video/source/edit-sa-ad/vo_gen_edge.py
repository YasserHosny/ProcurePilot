import asyncio,json,os,sys,subprocess,edge_tts
os.environ['SSL_CERT_FILE']='/root/.ccr/ca-bundle.crt'
PROXY=os.environ['HTTPS_PROXY']
SEG=json.load(open(sys.argv[1]));OUT=sys.argv[2];os.makedirs(OUT,exist_ok=True)
VOICE=sys.argv[3] if len(sys.argv)>3 else 'ar-SA-HamedNeural'
async def one(s):
    c=edge_tts.Communicate(s['text'],VOICE,rate=s.get('rate','+14%'),pitch=s.get('pitch','+0Hz'),proxy=PROXY,boundary='WordBoundary')
    words=[];buf=b''
    async for ch in c.stream():
        if ch['type']=='audio':buf+=ch['data']
        elif ch['type']=='WordBoundary':words.append([ch['offset']/1e7,ch['duration']/1e7,ch['text']])
    open(f"{OUT}/{s['id']}.mp3",'wb').write(buf)
    subprocess.run(['ffmpeg','-v','error','-y','-i',f"{OUT}/{s['id']}.mp3",'-ar','48000','-ac','1',f"{OUT}/{s['id']}.wav"],check=True)
    d=float(subprocess.check_output(['ffprobe','-v','error','-show_entries','format=duration','-of','csv=p=0',f"{OUT}/{s['id']}.wav"]))
    return {'id':s['id'],'dur':d,'words':words}
async def main():
    res=[]
    for s in SEG:
        for k in range(4):
            try:res.append(await one(s));break
            except Exception as e:print('retry',s['id'],e);await asyncio.sleep(2)
        print(res[-1]['id'],round(res[-1]['dur'],2),len(res[-1]['words']))
    json.dump(res,open(f'{OUT}/timing.json','w'),ensure_ascii=False,indent=1)
asyncio.run(main())
