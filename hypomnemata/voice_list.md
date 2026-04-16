# Overview:
I have three voice engines: kokoro, piper, and espeak.
They have only been tested with English.
See logos API docs for more usage details.
Below are voices listed by engine. 

---

## Engine: Kokoro
Kokoro is my highest quality voice engine. This is a great engine to use when clarity and human-like realism or clarity are important, and latency or CPU/battery usage are not a concern.

### Voices:
Kokoro supports percentage based voice mixing using a formula like `0.50*am_onyx + 0.15*if_sara + 0.0125*ff_siwis + 0.0125*bm_george`. The selected voices should add up to 1.00, but if not, it is safely normalized.

American:
af_alloy    af_aoede    af_bella    af  af_heart    af_jessica  af_kore af_nicole   af_nova
af_river    af_sarah    af_sky
am_adam     am_echo     am_eric am_fenrir   am_liam am_michael  am_onyx am_puck am_santa

British:
bf_alice    bf_emma bf_isabella bf_lily
bm_daniel   bm_fable    bm_george   bm_lewis

Spanish:
ef_dora
em_alex em_santa

French:
ff_siwis

Indian:
hf_alpha    hf_beta
hm_omega    hm_psi

Italian:
if_sara
im_nicola

Japanese:
jf_alpha    jf_gongitsune   jf_nezumi   jf_tebukuro
jm_kumo

Brazilian Portugese:
pf_dora
pm_alex pm_santa

Mandarin Chinese:
zf_xiaobei  zf_xiaoni   zf_xiaoxiao zf_xiaoyi
zm_yunjian  zm_yunxia   zm_yunxi    zm_yunyang

---

## Engine: Piper
Piper provides a wide variety of good quality voices
Piper is often preferred when operating on battery or when reduced latency matters.

### Voices:
My immediately accessible voices live in `~/src/logos_tts_server/voices/piper`.
A **complete** library of Piper voices is in `~/src/logos_tts_server/voices/piper-all-voices/`. To add any of these voices, the onnx and json need to be copied to the above dir.

From the standard Piper voice collection:
en_GB-alan-medium
en_GB-alba-medium
en_GB-aru-medium
en_GB-cori-high
en_GB-jenny_dioco-medium
en_GB-northern_english_male-medium
en_GB-semaine-medium
en_GB-southern_english_female-low
en_GB-vctk-medium
en_US-amy-medium
en_US-arctic-medium
en_US-bryce-medium
en_US-danny-low
en_US-hfc_female-medium
en_US-hfc_male-medium
en_US-joe-medium
en_US-john-medium
en_US-kathleen-low
en_US-kristin-medium
en_US-kusal-medium
en_US-l2arctic-medium
en_US-lessac-high
en_US-libritts-high
en_US-libritts_r-medium
en_US-ljspeech-high
en_US-norman-medium
en_US-reza_ibrahim-medium
en_US-ryan-high
en_US-sam-medium

Special voices:
hal
cortana
kronk-medium
vasco
wheatley1
zarvox
en_US-glados-high
en_US-picard_7399-medium
en_US-data_7024-medium
en_US-hal_12894-medium
en_US-hal_6409-medium
en_US-carlin-high
en_US-trump-high
pipe-organ

---

## Engine: espeak
I can use `espeak` for robotic effect, or for when saving CPU/battery/latency is important. The Linux `espeak` binary is used directly. 

### Voices:
Uses standard voice mixing based on typical `/usr/lib/x86_64-linux-gnu/espeak-data/voices`:
'!v'/   asia/   de   default   en   en-us   es-la   europe/   fr   mb/   other/   pt   test/

/usr/lib/x86_64-linux-gnu/espeak-data/voices/!v':
croak  f1  f2  f3  f4  f5  klatt  klatt2  klatt3  klatt4  m1  m2  m3  m4  m5  m6  m7  whisper  whisperf

/usr/lib/x86_64-linux-gnu/espeak-data/voices/asia:
fa  fa-pin  hi  hy  hy-west  id  ka  kn  ku  ml  ms  ne  pa  ta  tr  vi  vi-hue  vi-sgn  zh  zh-yue

/usr/lib/x86_64-linux-gnu/espeak-data/voices/europe:
an  bs  cs  da  es  fi     ga  hu  it  lv  nl  pl     ro  sk  sr
bg  ca  cy  el  et  fr-be  hr  is  lt  mk  no  pt-pt  ru  sq  sv

/usr/lib/x86_64-linux-gnu/espeak-data/voices/mb:
mb-af1     mb-cr1  mb-de4-en   mb-de7  mb-fr1     mb-gr2-en  mb-ir1  mb-mx1     mb-pl1-en  mb-sw1-en  mb-us1
mb-af1-en  mb-cz2  mb-de5      mb-ee1  mb-fr1-en  mb-hu1     mb-ir2  mb-mx2     mb-pt1     mb-sw2     mb-us2
mb-br1     mb-de2  mb-de5-en   mb-en1  mb-fr4     mb-hu1-en  mb-it3  mb-nl2     mb-ro1     mb-sw2-en  mb-us3
mb-br3     mb-de3  mb-de6      mb-es1  mb-fr4-en  mb-ic1     mb-it4  mb-nl2-en  mb-ro1-en  mb-tr1     mb-vz1
mb-br4     mb-de4  mb-de6-grc  mb-es2  mb-gr2     mb-id1     mb-la1  mb-pl1     mb-sw1     mb-tr2

/usr/lib/x86_64-linux-gnu/espeak-data/voices/other:
af  en-n  en-rp  en-sc  en-wi  en-wm  eo  grc  jbo  la  lfn  sw

/usr/lib/x86_64-linux-gnu/espeak-data/voices/test:
am  as  az  bn  eu  gd  gu  kl  ko  nci  or  pap  si  sl  te  ur
