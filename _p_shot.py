import io
p = "tests/shot.py"
t = io.open(p, encoding="utf-8").read()
t = t.replace("{width: 1000, height: 900, deviceScaleFactor: 1, mobile: false}",
              "{width: +process.argv[5], height: +process.argv[6], deviceScaleFactor: 1, mobile: +process.argv[5] < 700}")
t = t.replace("r = subprocess.run([NODE, js_path, page[\"webSocketDebuggerUrl\"], OUT, URL],",
              "r = subprocess.run([NODE, js_path, page[\"webSocketDebuggerUrl\"], OUT, URL,\n                    str(W), str(H)],")
t = t.replace('URL = "http://127.0.0.1:8770/"',
              'URL = "http://127.0.0.1:8770/"\nW = int(sys.argv[1]) if len(sys.argv) > 1 else 1000\nH = int(sys.argv[2]) if len(sys.argv) > 2 else 900')
t = t.replace("OUTDIR + '/tutor.png'", "OUTDIR + '/tutor-' + W + 'x' + H + '.png'")
io.open(p, "w", encoding="utf-8", newline="\n").write(t)
print("  shot.py 支持任意尺寸")
