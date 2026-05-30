import json, csv, os, time

# Quick timestamp check: source vs results
print('='*60)
print('Source vs Result Timestamp Check')
print('='*60)
pairs = [
    ('code/src/q1/run_q1.py', 'code/results/tables/Q1_rul.csv'),
    ('code/src/q2/run_q2.py', 'code/results/tables/Q2_bearing_theta.csv'),
    ('code/src/q3/run_q3.py', 'code/results/tables/Q3_rul.csv'),
    ('code/run_all.py', 'code/results/tables/_paper_numbers.json'),
]
all_ok = True
for s, r in pairs:
    sm = os.path.getmtime(s) if os.path.exists(s) else 0
    rm = os.path.getmtime(r) if os.path.exists(r) else 0
    ok = rm >= sm
    if not ok:
        all_ok = False
    tag = "OK" if ok else "STALE!"
    print("  %-30s src=%s  res=%s  %s" % (
        r.split("/")[-1],
        time.strftime("%H:%M:%S", time.localtime(sm)),
        time.strftime("%H:%M:%S", time.localtime(rm)),
        tag
    ))

print()
if all_ok:
    print("All results are fresh - consistent with latest source code!")
else:
    print("WARNING: Some results are older than source code!")

# Key numbers
print()
print('='*60)
print('Key Results Summary')
print('='*60)
with open('code/results/tables/_paper_numbers.json','r',encoding='utf-8') as f:
    pn = json.load(f)
print("  Q1 RUL_A: %.1f days" % pn["Q1_RUL_A_days"])
print("  Q1 RUL_B: %.1f days" % pn["Q1_RUL_B_days"])
print("  Q3 RUL_TL: %.1f days, CI=[%.1f, %.1f]" % (pn["Q3_RUL_TL_days"], pn["Q3_RUL_TL_CI"][0], pn["Q3_RUL_TL_CI"][1]))
print("  Q3 lambda: (see Q3_summary.json)")
print("  Q2 top features: %s" % pn["Q2_top_features"])
print("  Alert: %s" % pn["Q3_alert_level"])

# exp_r2 check
print()
print('='*60)
print('Q2 exp_r2 column check')
print('='*60)
with open('code/results/tables/Q2_bearing_theta.csv','r',encoding='utf-8') as f:
    reader = csv.DictReader(f)
    rows = list(reader)
    has_exp = 'exp_r2' in (reader.fieldnames or [])
print("  exp_r2 column exists: %s" % has_exp)
print("  Total bearings: %d" % len(rows))
for r in rows[:3]:
    print("  %s: W-R2=%.2f  E-R2=%.2f" % (r["bearing"], float(r["wiener_r2"]), float(r.get("exp_r2",0))))

# Tests
print()
print('='*60)
print('Regression Tests')
print('='*60)
import subprocess
result = subprocess.run([r'D:\新建文件夹\python\python.exe', 'code/tests/test_unit.py'],
                       capture_output=True, text=True, cwd='.')
print(result.stdout.strip() or "(no output = all passed)")
if result.stderr:
    print("STDERR:", result.stderr[:300])
print("Exit code: %d" % result.returncode)
