"""Print handoff evidence from completed command reports; refuse incomplete privacy proof."""
import json
from privacy import ROOT

def main():
    before=json.loads((ROOT/'proof/before-native.json').read_text())
    after=json.loads((ROOT/'proof/after-native.json').read_text())
    control=json.loads((ROOT/'proof/control-native.json').read_text())
    assert len(before)==len(after)==16 and before.keys()==after.keys()
    for name,v in before.items():
        a=after[name];assert v['frames']==a['frames'] and a['matches']==0
        print(f"{name} frames={v['frames']} before_matching_frames={v['matching_frames']} before_hits={v['matches']} after_hits={a['matches']}")
    print('TOTAL frames='+str(sum(v['frames'] for v in before.values()))+' before_matching_frames='+str(sum(v['matching_frames'] for v in before.values()))+' after_hits='+str(sum(v['matches'] for v in after.values())))
    for name,v in control.items():
        assert v['matches']>0
        print(f"CONTROL {name} frames={v['frames']} matching_frames={v['matching_frames']} hits={v['matches']}")
    results=json.loads((ROOT/'proof/results-privacy.json').read_text())
    assert len(results)==4
    for name,v in results.items():
        assert v['after']['matches']==0
        print(f"RESULT {name} frames={v['before']['frames']} before_hits={v['before']['matches']} legacy_hits={v['legacy_template_hits']} after_hits={v['after']['matches']} boxes={v['boxes']}")
    audio=json.loads((ROOT/'proof/audio.json').read_text())
    for name,v in audio.items():
        print(f"AUDIO {name} PCM_duration={v['pcm']['duration_seconds']:.6f}s AAC_duration={v['aac']['container_duration']} I={v['aac']['integrated_lufs']:.1f}_LUFS TP={v['aac']['true_peak_dbfs']:.1f}_dBFS")
    print('DELTA_FINAL_VIDEO_PROOF pending orchestrator render; earlier MP4 measurements do not validate this revision')
    print('FILE_LIST proof/results-changed-files.txt')
if __name__=='__main__':main()
