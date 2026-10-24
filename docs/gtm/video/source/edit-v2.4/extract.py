"""Extract only privacy-cleared plates; refuse to proceed without the 16-clip zero-match audit."""
from pathlib import Path
import subprocess,json
from privacy import ROOT,FF

def main():
    proof=json.loads((ROOT/'proof/after-native.json').read_text())
    assert len(proof)==16 and all(v['matches']==0 for v in proof.values()),'Privacy audit required'
    meta={}
    sources=[(p.parent.name+'/'+p.stem,p) for p in sorted((ROOT/'masked').glob('*/*.mp4'))]
    sources += [('opening-'+f,ROOT/'raw/openings'/('opening-anim-'+a+'.mp4')) for f,a in [('h','16x9'),('v','9x16')]]
    for name,p in sources:
        folder=ROOT/'plates'/name;folder.mkdir(parents=True,exist_ok=True)
        subprocess.run([FF,'-v','error','-y','-i',str(p),'-q:v','2','-threads','2',str(folder/'%04d.jpg')],check=True)
        from PIL import Image
        w,h=Image.open(folder/'0001.jpg').size
        meta[name]={'box':[0,0,w,h],'frames':len(list(folder.glob('*.jpg')))}
        print('PLATE',name,meta[name],flush=True)
    (ROOT/'plates/meta.json').write_text(json.dumps(meta,indent=2)+'\n')
if __name__=='__main__':main()
