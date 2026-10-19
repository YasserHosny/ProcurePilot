#!/bin/bash
# Mux body + outro with music: track 0:00–BODY at -6.6 dB (the outro's own music gain), limiter -3 dB before AAC.
set -e; S=/tmp/claude-1000/-media-yasserhosny-My-Passport-Work-Projects-ProcurePilot/1c3520f5-a777-4834-b5ef-0684f2157c72/scratchpad
FF=$S/vid/lib/python3.12/site-packages/imageio_ffmpeg/binaries/ffmpeg-linux-x86_64-v7.0.2
BODY_FILE=$1; OUTRO=$2; MUSIC_START=$3; BODY=$4; OUT=$5; W=${6:-1920}; H=${7:-1080}
MU="/media/yasserhosny/My Passport/Work/Projects/ProcurePilot/docs/gtm/video/music/dayfox-antalya-beaches-119047.mp3"
$FF -y -loglevel error -i "$BODY_FILE" -i "$OUTRO" -ss $MUSIC_START -t $BODY -i "$MU" -filter_complex "[0:v]fps=30,tpad=stop_mode=clone:stop_duration=1,trim=0:$BODY,setpts=PTS-STARTPTS[b];[1:v]fps=30,scale=$W:$H,format=yuv420p,setsar=1,setpts=PTS-STARTPTS[o];[b][o]concat=n=2:v=1:a=0,fps=30[v];[2:a]atrim=0:$BODY,asetpts=PTS-STARTPTS,volume=-6.6dB,afade=t=in:d=0.5,aresample=48000,aformat=channel_layouts=stereo[m];[1:a]aresample=48000,aformat=channel_layouts=stereo[oa];[m][oa]concat=n=2:v=0:a=1,alimiter=limit=0.7079:attack=0.5:release=50:level=false,aresample=48000[a]" -map "[v]" -map "[a]" -r 30 -c:v libx264 -preset slow -crf 17 -pix_fmt yuv420p -c:a aac -b:a 256k -movflags +faststart "$OUT"
$FF -hide_banner -i "$OUT" 2>&1 | grep -E "Duration|Video:" ; $FF -hide_banner -i "$OUT" -vn -af ebur128=peak=true -f null - 2>&1 | grep -A14 Summary | grep -E "I:|Peak:"
