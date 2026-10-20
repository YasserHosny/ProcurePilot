# Remove temporary unmasked source stills after the source audit. Keep only
# final-output proof frames and sheets; reference raw media remains untouched.
from paths import *
import shutil
analysis=ROOT/'analysis'
for name in ('s0-phone-lowstock','s1-rfq','s2-quote-photo','s2b-photo-closeup','s3-guardrail-draft','s3b-compare','s3c-smart-compare','s4-phone-approve','s5-po-savings','s6-savings-close'):
 folder=analysis/name
 if folder.is_dir():shutil.rmtree(folder)
 for p in analysis.glob(name+'*.png'):p.unlink()
 p=analysis/(name+'.jpg')
 if p.exists():p.unlink()
for pattern in ('template-*.png','preview-*.jpg'):
 for p in analysis.glob(pattern):p.unlink()
p=analysis/'raw-email-audit-draft-incorrect-times.json'
if p.exists():p.unlink()
print('temporary raw identity stills removed; final-output proof retained')
