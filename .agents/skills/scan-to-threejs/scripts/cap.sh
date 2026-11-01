#!/bin/zsh
# Render one view of the capture page to a PNG with Playwright (capture.mjs).
# usage: cap.sh <name> "<query>"       e.g. cap.sh north "view=n&ppm=180&cut=0.2"
#        cap.sh sofa "src=model&cam=0.8,1.5,-1.2&look=-1.2,0.4,1.6&fov=60&size=1300x850"
# env:   CAP_OUT (output dir, default data/captures in this project, ./captures elsewhere)
#        CAP_URL (viewer server, default http://localhost:5188)
#        CAP_QUERY (extra query appended to every capture, e.g. "parts=desk")
#        CAP_TIMEOUT_MS, CAP_BROWSER_CHANNEL (see capture.mjs)
DIR=${0:A:h}
source "$DIR/capture_env.sh"
Q="$2${CAP_QUERY:+&$CAP_QUERY}"
mkdir -p "$CAP_OUT"
node "$DIR/capture.mjs" "$CAP_URL/tools/capture.html?$Q" "$CAP_OUT/$1.png"
