# Third-party test fixtures

## `faces/nasa-s69-31741-portrait.jpg`

The one photo of a person in this repository, there only so the face-blurring test has a
real face to find.

| field | value (from the Wikimedia Commons API `extmetadata`, read 2026-10-21) |
|---|---|
| title | File:Neil Armstrong pose.jpg |
| subject | Neil Armstrong, official NASA astronaut portrait (NASA photo S69-31741) |
| author / credit | NASA (Commons lists "Unknown author"; credit links https://www.nasa.gov/images/content/464436main_S69-31741_full.jpg) |
| licence | **Public domain** (`LicenseShortName: Public domain`, `License: pd`, `Copyrighted: False`, `AttributionRequired: false`, no `Restrictions`) |
| page | https://commons.wikimedia.org/wiki/File:Neil_Armstrong_pose.jpg |
| API query | `https://commons.wikimedia.org/w/api.php?action=query&prop=imageinfo&iiprop=url\|size\|mime\|extmetadata&titles=File:Neil_Armstrong_pose.jpg` |
| downloaded | the 960 px Commons thumbnail (sha256 `7862273d62febf72259b20cf65d192e5a9b6477112cb193b99ea99c6cca35f45`) |
| changes | resized to 640x800 px with OpenCV INTER_AREA, JPEG quality 90 (sha256 `55a34f8d111ce664ec0c7ff0dcbc754c371d4d96a8546a01ab5e3f805857e35b`) |

A work of the US federal government (NASA), in the public domain in the United States.
Attribution is not required; it is given anyway. The photo is used only to test that
faces are found and blurred; it is never shown in the app.

## The YuNet face detector (not in git)

`models/face_detection_yunet_2023mar.onnx` is fetched, never committed — MIT licence,
Copyright (c) 2020 Shiqi Yu, from https://github.com/opencv/opencv_zoo. The notice is
written beside the file when it is fetched (`src/stepspotter/perception/fetch_yunet.py`).
