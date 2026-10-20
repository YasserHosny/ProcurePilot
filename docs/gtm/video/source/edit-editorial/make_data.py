# Writes data.js: the music beat map (for snapping scene changes to beats) and the plate index from extract.py.
import json, os
H=os.path.dirname(os.path.abspath(__file__))
beats=[float(l) for l in open(os.path.join(H,'../../music/antalya-beaches-beats.csv')) if l[0].isdigit()]
meta=json.load(open(os.path.join(H,'plates/meta.json')))
open(os.path.join(H,'data.js'),'w').write('window.BEATS='+json.dumps(beats)+';\nwindow.PLATE_META='+json.dumps(meta)+';\n')
