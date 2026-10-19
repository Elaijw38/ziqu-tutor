import io
p = "web/index.html"
t = io.open(p, encoding="utf-8").read()
old = """  const g = await (await fetch('/api/grade',{method:'POST',
    headers:{'Content-Type':'application/json'},
    body:JSON.stringify({quiz:PAPER, answers})})).json();
  const box = $('#gradeBox'); box.innerHTML = '';"""
new = """  const g = await (await fetch('/api/grade',{method:'POST',
    headers:{'Content-Type':'application/json'},
    body:JSON.stringify({quiz:PAPER, answers})})).json();
  const box = $('#gradeBox'); box.innerHTML = '';
  if (g.error){ box.textContent = '评阅失败：' + g.error; return; }"""
assert t.count(old) == 1
io.open(p, "w", encoding="utf-8", newline="\n").write(t.replace(old, new))
print("  评阅失败时会显示原因")
