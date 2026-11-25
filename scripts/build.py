#!/usr/bin/env python3
"""ライフ資産ダッシュボード生成（汎用版）
使い方: python3 build.py --data-dir <params.json と events.jsonl のあるフォルダ> [--out <出力HTML>]
台帳の各イベントは {"date","type","account","label","amount","half_life_days"} を持つ。
残存価値 = 取得額 × (1/2)^(経過日数 ÷ 半減期)。損失イベントは永久残存割合まで回復する。
"""
import argparse, json, math
from datetime import date, datetime, timedelta
from pathlib import Path

C = {"F": "#5b8def", "H": "#43b581", "G": "#f2a93b", "E": "#e573b7", "S": "#7a6fd0", "L": "#2f9e6e"}
SYM = "¥"

def residual(ev, on, params):
    d0 = datetime.strptime(ev["date"], "%Y-%m-%d").date()
    if on < d0:
        return 0.0
    days = (on - d0).days
    amt = float(ev["amount"])
    hl = float(ev["half_life_days"])
    if ev["type"] == "loss":
        perm = params.get("loss_permanent_ratio", 0.2)
        return amt * (perm + (1 - perm) * (0.5 ** (days / hl)))
    return amt * (0.5 ** (days / hl))

def yen(v):
    return f"{SYM}{v:,.0f}"

def line_chart(series, labels):
    W, H, PL, PR, PT, PB = 840, 250, 78, 14, 14, 30
    iw, ih = W - PL - PR, H - PT - PB
    allv = [v for s in series.values() for v in s]
    lo, hi = min(allv), max(allv)
    span = (hi - lo) or 1
    lo -= span * 0.15 + 1
    hi += span * 0.15 + 1
    n = len(labels)
    def X(i): return PL + iw * (i / max(n - 1, 1))
    def Y(v): return PT + ih * (1 - (v - lo) / (hi - lo))
    parts = [f'<svg viewBox="0 0 {W} {H}" width="100%" role="img">']
    for g in range(4):
        v = lo + (hi - lo) * g / 3
        y = Y(v)
        parts.append(f'<line x1="{PL}" y1="{y:.1f}" x2="{W-PR}" y2="{y:.1f}" stroke="#e7e2d6" stroke-width="1"/>')
        parts.append(f'<text x="{PL-6}" y="{y+4:.1f}" font-size="11" fill="#999" text-anchor="end">{SYM}{v/1e6:,.0f}M</text>')
    step = max(1, n // 6)
    for i, d in enumerate(labels):
        if i % step == 0 or i == n - 1:
            parts.append(f'<text x="{X(i):.1f}" y="{H-8}" font-size="11" fill="#999" text-anchor="middle">{d.strftime("%m/%d")}</text>')
    for key, vals in series.items():
        pts = " ".join(f"{X(i):.1f},{Y(v):.1f}" for i, v in enumerate(vals))
        parts.append(f'<polyline points="{pts}" fill="none" stroke="{C[key]}" stroke-width="2.5" stroke-linejoin="round"/>')
        parts.append(f'<circle cx="{X(len(vals)-1):.1f}" cy="{Y(vals[-1]):.1f}" r="4" fill="{C[key]}"/>')
    parts.append("</svg>")
    return "".join(parts)

def donut(shares):
    total = sum(v for _, v in shares) or 1
    R, SW, CX, CY = 62, 26, 80, 80
    circ = 2 * math.pi * R
    parts = [f'<svg viewBox="0 0 160 160" width="170" height="170" role="img">']
    parts.append(f'<circle cx="{CX}" cy="{CY}" r="{R}" fill="none" stroke="#f0ead9" stroke-width="{SW}"/>')
    off = 0.0
    for key, v in shares:
        if v <= 0:
            continue
        dash = (v / total) * circ
        parts.append(f'<circle cx="{CX}" cy="{CY}" r="{R}" fill="none" stroke="{C[key]}" stroke-width="{SW}" '
                     f'stroke-dasharray="{dash:.1f} {circ-dash:.1f}" stroke-dashoffset="{-off:.1f}" transform="rotate(-90 {CX} {CY})"/>')
        off += dash
    fshare = dict(shares).get("F", 0) / total * 100
    parts.append(f'<text x="{CX}" y="{CY-2}" font-size="17" font-weight="700" fill="#333" text-anchor="middle">F {fshare:.0f}%</text>')
    parts.append(f'<text x="{CX}" y="{CY+16}" font-size="10" fill="#999" text-anchor="middle">金融資産の割合</text>')
    parts.append("</svg>")
    return "".join(parts)

def main():
    global SYM
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", default=".")
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    base = Path(a.data_dir)
    params = json.loads((base / "params.json").read_text(encoding="utf-8"))
    SYM = params.get("currency_symbol", "¥")
    events = []
    ev_file = base / "events.jsonl"
    if ev_file.exists():
        for line in ev_file.read_text(encoding="utf-8").splitlines():
            if line.strip():
                events.append(json.loads(line))
    today = date.today()
    start = datetime.strptime(params["start_date"], "%Y-%m-%d").date()
    F = params["financial_assets"]["value"]

    accounts = {"H": 0.0, "G": 0.0, "E": 0.0, "S": 0.0}
    rows = []
    for ev in events:
        r = residual(ev, today, params)
        accounts[ev["account"]] += r
        rows.append((ev, r))
    N = sum(accounts.values())
    L = F + N
    month_flow = sum(float(ev["amount"]) for ev in events
                     if ev["date"][:7] == today.strftime("%Y-%m"))
    rows.sort(key=lambda x: x[0]["date"], reverse=True)

    end = max(today, start + timedelta(days=6))
    days = (end - start).days + 1
    labels, sF, sL = [], [], []
    for i in range(days):
        d = start + timedelta(days=i)
        labels.append(d)
        n_d = sum(residual(ev, d, params) for ev in events)
        sF.append(float(F)); sL.append(F + n_d)
    chart = line_chart({"L": sL, "F": sF}, labels)
    legend = (f'<div class="legend"><span><i style="background:{C["L"]}"></i>ライフ資産 L</span>'
              f'<span><i style="background:{C["F"]}"></i>金融資産 F</span>'
              f'<span class="note-inline">非金融 N が小さいうちは L と F がほぼ重なります</span></div>')

    shares = [("F", float(F)), ("H", accounts["H"]), ("G", accounts["G"]), ("E", accounts["E"]), ("S", accounts["S"])]
    dn = donut(shares)
    names = {"F": "金融資産 F", "H": "健康資産 H", "G": "モノ資産 G", "E": "体験・思い出・幸福資産 E", "S": "学び資産 S"}
    vals = {"F": float(F), "H": accounts["H"], "G": accounts["G"], "E": accounts["E"], "S": accounts["S"]}
    bal_rows = ""
    for k in ("F", "H", "G", "E", "S"):
        pct = vals[k] / L * 100 if L else 0
        bal_rows += (f'<div class="bal-row"><span class="bal-name"><i style="background:{C[k]}"></i>{names[k]}</span>'
                     f'<span class="bal-bar"><span style="width:{max(pct,0.4):.1f}%;background:{C[k]}"></span></span>'
                     f'<span class="bal-val">{yen(vals[k])}（{pct:.1f}%）</span></div>')

    descs = {"H": "健康活動。将来の医療費削減見込みを収入化し、継続度で半減期が変わる",
             "G": "管理対象にしたモノのもとの価値。価格そのままを計上し、カテゴリ別の半減期で減る",
             "E": "体験や家族イベントなどの幸福度を換算。モノを利用して得た価値も棚卸しでここに積み上がる。半減期は長め",
             "S": "読書で元本を積み、成長の一言で複利が付く。続けるほど増分が加速する"}
    cards = ""
    for k in ("H", "G", "E", "S"):
        cnt = sum(1 for e in events if e["account"] == k)
        cards += (f'<div class="card"><div class="card-label"><i style="background:{C[k]}"></i>{names[k]}</div>'
                  f'<div class="card-value">{yen(accounts[k])}</div><div class="card-desc">{descs[k]}<br>台帳 {cnt} 件</div></div>')

    if rows:
        trs = "".join(
            f"<tr><td>{ev['date']}</td><td>{ev.get('label','')}</td><td class='num'>{yen(float(ev['amount']))}</td>"
            f"<td class='num'>{yen(r)}</td><td>{ev['half_life_days']}日</td></tr>" for ev, r in rows[:30])
        events_html = f"<table><thead><tr><th>日付</th><th>イベント</th><th>取得額</th><th>現在価値</th><th>半減期</th></tr></thead><tbody>{trs}</tbody></table>"
    else:
        events_html = "<p class='empty'>まだイベントはありません。記録が貯まるとここに並びます。</p>"

    html = f"""<!DOCTYPE html>
<html lang="ja"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>ライフ資産ダッシュボード</title>
<style>
body {{ font-family: -apple-system, "Hiragino Sans", "Noto Sans JP", sans-serif; margin: 0; background: #fdfaf2; color: #2b2b26; }}
.wrap {{ max-width: 900px; margin: 0 auto; padding: 24px 16px 48px; }}
h1 {{ font-size: 21px; margin: 8px 0 2px; }}
.sub {{ color: #8a8578; font-size: 13px; margin-bottom: 18px; }}
.hero {{ background: linear-gradient(120deg, #e9f7ec, #fff6df); border: 1px solid #e7e0c8; border-radius: 16px; padding: 26px 24px; margin-bottom: 14px; }}
.hero .label {{ font-size: 13px; color: #6d7a6a; }}
.hero .value {{ font-size: 42px; font-weight: 700; margin: 6px 0; color: #205c3a; }}
.hero .breakdown {{ font-size: 14px; color: #55534a; line-height: 1.7; }}
.panel {{ background: #fff; border-radius: 14px; padding: 18px; box-shadow: 0 1px 4px rgba(120,110,60,.08); margin-bottom: 14px; }}
.panel h2 {{ font-size: 15px; margin: 0 0 12px; }}
.legend {{ display: flex; gap: 16px; flex-wrap: wrap; font-size: 12px; color: #666; margin-top: 6px; }}
.legend i, .card-label i, .bal-name i {{ display: inline-block; width: 10px; height: 10px; border-radius: 3px; margin-right: 6px; }}
.note-inline {{ color: #aaa; }}
.balance-flex {{ display: flex; gap: 20px; align-items: center; flex-wrap: wrap; }}
.bal-list {{ flex: 1; min-width: 300px; }}
.bal-row {{ display: flex; align-items: center; gap: 10px; font-size: 13px; padding: 5px 0; }}
.bal-name {{ width: 130px; flex-shrink: 0; }}
.bal-bar {{ flex: 1; background: #f3efe2; border-radius: 6px; height: 12px; overflow: hidden; }}
.bal-bar span {{ display: block; height: 100%; border-radius: 6px; }}
.bal-val {{ width: 190px; text-align: right; flex-shrink: 0; }}
.cards {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(230px, 1fr)); gap: 12px; margin-bottom: 14px; }}
.card {{ background: #fff; border-radius: 12px; padding: 16px; box-shadow: 0 1px 4px rgba(120,110,60,.08); }}
.card-label {{ font-size: 13px; color: #555; }}
.card-value {{ font-size: 24px; font-weight: 700; margin: 4px 0; }}
.card-desc {{ font-size: 12px; color: #8a8578; line-height: 1.6; }}
table {{ width: 100%; border-collapse: collapse; background: #fff; border-radius: 12px; overflow: hidden; font-size: 13px; }}
th, td {{ padding: 8px 10px; border-bottom: 1px solid #f0ebdd; text-align: left; }}
td.num {{ text-align: right; }}
.empty {{ background: #fff; border-radius: 12px; padding: 16px; font-size: 13px; color: #8a8578; }}
.note {{ font-size: 12px; color: #8a8578; line-height: 1.8; margin-top: 14px; }}
</style></head><body><div class="wrap">
<h1>ライフ資産ダッシュボード</h1>
<div class="sub">運用開始 {params['start_date']} ／ 最終更新 {today.isoformat()}</div>
<div class="hero"><div class="label">ライフ資産 L</div><div class="value">{yen(L)}</div>
<div class="breakdown">金融資産 F：{yen(F)}（{params['financial_assets']['as_of']} 時点、{params['financial_assets']['source']}）<br>非金融資産 N：{yen(N)}（今月の新規計上 {yen(month_flow)}）</div></div>
<div class="panel"><h2>全体の推移</h2>{chart}{legend}</div>
<div class="panel"><h2>バランス（資産の構成）</h2><div class="balance-flex"><div>{dn}</div><div class="bal-list">{bal_rows}</div></div></div>
<div class="cards">{cards}</div>
<div class="panel"><h2>イベント台帳（新しい順・最大30件）</h2>{events_html}</div>
<div class="panel"><h2>いまの変数（初期値）</h2>
<table><tbody>
<tr><td>体験の換算レート</td><td class="num">{yen(params['r_exp'])}／点（家族は ×{params['family_multiplier']}）</td></tr>
<tr><td>喪失の換算レート</td><td class="num">{yen(params['r_loss'])}／点</td></tr>
<tr><td>ラン収入</td><td class="num">{yen(params['run_base'])}／回 + {yen(params['run_per_km'])}／km</td></tr>
<tr><td>ランの半減期</td><td class="num">継続が少ない {params['run_half_life_days']['low']}日 ／ 中 {params['run_half_life_days']['mid']}日 ／ 習慣化 {params['run_half_life_days']['high']}日</td></tr>
<tr><td>体験の半減期</td><td class="num">{params['experience_half_life_days']}日（記録を残すと {params['experience_half_life_days_with_record']}日）</td></tr>
<tr><td>読書収入</td><td class="num">{yen(params.get('reading_per_min', 10))}／分（完読ボーナス {yen(params.get('reading_complete_bonus', 1000))}／冊）</td></tr>
<tr><td>成長の複利</td><td class="num">学び残高 × {params.get('growth_rate', 0.002) * 100:g}%／日（成長の一言が言えた日）</td></tr>
</tbody></table>
<p class="note">この数字は「幸福への変換効率」を見るための物差しです。金融資産は定期的に最新の値へ更新します。変数の調整は四半期ごとが目安です。</p>
</div>
</div></body></html>"""
    out = Path(a.out) if a.out else base / "dashboard.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    print(f"wrote {out} ({len(html)} bytes) L={L:,.0f} N={N:,.0f}")

if __name__ == "__main__":
    main()
