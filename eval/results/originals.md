# Quality check on unmodified real photos

Ran 2026-10-21T13:17:17+00:00. Command: `python eval/originals.py`.

| source / label by eye | n | refused by OpenCV | reasons |
|---|---:|---:|---|
| onq / good | 6 | 0 | — |
| commons / good | 40 | 0 | — |
| own-video / good | 10 | 0 | — |
| own-video / blurred | 4 | 1 | {'blurry': 1} |
| own-video / borderline | 2 | 0 | — |

| photo | source | label | OpenCV | reason | sharpness p90 | glare blob | bright frac |
|---|---|---|---|---|---:|---:|---:|
| 01 | onq | good | ok | ok | 292.4 | 0.0021 | 0.0070 |
| 02 | onq | good | ok | ok | 164.6 | 0.0000 | 0.0000 |
| 03 | onq | good | ok | ok | 1072.5 | 0.0001 | 0.0021 |
| 04 | onq | good | ok | ok | 73.7 | 0.0000 | 0.0000 |
| 05 | onq | good | ok | ok | 330.9 | 0.0000 | 0.0000 |
| 06 | onq | good | ok | ok | 318.9 | 0.0000 | 0.0000 |
| c01 | commons | good | ok | ok | 4124.6 | 0.0001 | 0.0013 |
| c02 | commons | good | ok | ok | 8811.2 | 0.0001 | 0.0027 |
| c03 | commons | good | ok | ok | 1061.6 | 0.0027 | 0.0038 |
| c04 | commons | good | ok | ok | 6308.2 | 0.0006 | 0.0070 |
| c05 | commons | good | ok | ok | 3605.2 | 0.0004 | 0.0029 |
| c07 | commons | good | ok | ok | 1582.3 | 0.0023 | 0.0076 |
| c08 | commons | good | ok | ok | 2856.2 | 0.0008 | 0.0095 |
| c09 | commons | good | ok | ok | 803.0 | 0.0000 | 0.0000 |
| c10 | commons | good | ok | ok | 740.9 | 0.0000 | 0.0000 |
| c11 | commons | good | ok | ok | 3268.6 | 0.0000 | 0.0000 |
| c12 | commons | good | ok | ok | 3032.6 | 0.0001 | 0.0001 |
| c13 | commons | good | ok | ok | 1488.1 | 0.0002 | 0.0016 |
| c14 | commons | good | ok | ok | 3739.6 | 0.0001 | 0.0003 |
| c15 | commons | good | ok | ok | 3266.4 | 0.0012 | 0.0086 |
| c16 | commons | good | ok | ok | 248.7 | 0.0000 | 0.0000 |
| c17 | commons | good | ok | ok | 346.6 | 0.0000 | 0.0000 |
| c18 | commons | good | ok | ok | 316.5 | 0.0000 | 0.0000 |
| c19 | commons | good | ok | ok | 549.8 | 0.0048 | 0.0131 |
| c20 | commons | good | ok | ok | 337.1 | 0.2236 | 0.4529 |
| c21 | commons | good | ok | ok | 3457.3 | 0.0008 | 0.0015 |
| c22 | commons | good | ok | ok | 2187.9 | 0.0203 | 0.0597 |
| c23 | commons | good | ok | ok | 2178.9 | 0.0201 | 0.0583 |
| c24 | commons | good | ok | ok | 1680.1 | 0.0769 | 0.1098 |
| c25 | commons | good | ok | ok | 664.3 | 0.0004 | 0.0023 |
| c27 | commons | good | ok | ok | 961.4 | 0.0002 | 0.0011 |
| c28 | commons | good | ok | ok | 1129.3 | 0.0003 | 0.0012 |
| c29 | commons | good | ok | ok | 206.8 | 0.0000 | 0.0000 |
| c30 | commons | good | ok | ok | 59.1 | 0.0000 | 0.0000 |
| c31 | commons | good | ok | ok | 1171.3 | 0.0001 | 0.0032 |
| c32 | commons | good | ok | ok | 455.6 | 0.0000 | 0.0000 |
| c33 | commons | good | ok | ok | 1296.1 | 0.0036 | 0.0094 |
| c34 | commons | good | ok | ok | 1261.6 | 0.0097 | 0.0344 |
| c35 | commons | good | ok | ok | 1792.2 | 0.0060 | 0.0281 |
| c36 | commons | good | ok | ok | 10179.4 | 0.0001 | 0.0096 |
| c37 | commons | good | ok | ok | 2599.7 | 0.0002 | 0.0079 |
| c38 | commons | good | ok | ok | 16418.0 | 0.0015 | 0.0070 |
| c39 | commons | good | ok | ok | 10585.0 | 0.0001 | 0.0023 |
| c40 | commons | good | ok | ok | 1934.7 | 0.0111 | 0.0602 |
| c41 | commons | good | ok | ok | 1443.5 | 0.0001 | 0.0015 |
| c43 | commons | good | ok | ok | 335.2 | 0.0000 | 0.0000 |
| v0030 | own-video | good | ok | ok | 342.4 | 0.0037 | 0.0546 |
| v0042 | own-video | good | ok | ok | 816.1 | 0.0062 | 0.0660 |
| v0180 | own-video | good | ok | ok | 472.1 | 0.0017 | 0.0096 |
| v0195 | own-video | blurred | ok | ok | 55.1 | 0.0027 | 0.0054 |
| v0240 | own-video | blurred | ok | ok | 70.3 | 0.0203 | 0.1219 |
| v0448 | own-video | good | ok | ok | 310.0 | 0.0001 | 0.0285 |
| v0510 | own-video | borderline | ok | ok | 86.3 | 0.0000 | 0.0000 |
| v0557 | own-video | good | ok | ok | 423.6 | 0.0000 | 0.0256 |
| v0570 | own-video | borderline | ok | ok | 48.5 | 0.0000 | 0.0068 |
| v0659 | own-video | good | ok | ok | 624.1 | 0.0000 | 0.0356 |
| v0812 | own-video | good | ok | ok | 1170.0 | 0.0000 | 0.0435 |
| v0870 | own-video | blurred | retake | blurry | 4.9 | 0.0000 | 0.0000 |
| v0900 | own-video | blurred | ok | ok | 91.5 | 0.0185 | 0.0896 |
| v0990 | own-video | good | ok | ok | 645.8 | 0.0000 | 0.0143 |
| v1050 | own-video | good | ok | ok | 408.4 | 0.0000 | 0.0566 |
| v1106 | own-video | good | ok | ok | 1028.1 | 0.0026 | 0.0226 |
