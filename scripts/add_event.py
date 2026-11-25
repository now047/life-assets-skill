#!/usr/bin/env python3
"""ライフ資産の台帳にイベントを1件追加する。
使い方（いずれか1モード）:
  ラン:       --run-km 5.2 [--date YYYY-MM-DD] [--label 任意]
  購入:       --price 30000 --category 道具・機材 --manage --label 品名
              （購入時点で管理対象とするか判断する。--manage なら価格そのままをモノ資産 G に
               計上し購入品レジストリにも登録。--no-manage なら台帳に載せない）
  棚卸し:     --use-value 15000 --label 品名 [--recorded]
              （年1回の棚卸しで「利用して得た価値」を幸福の側 E に計上。半減期は体験と同じ）
  体験:       --points 4 [--family] [--recorded] --label 内容
  喪失:       --severity 3 --label 内容
  読書:       --reading-min 25 [--date YYYY-MM-DD] [--label 本のタイトル等]
  完読:       --book-complete --label 本のタイトル
  成長:       --growth [--label 成長の一言]（その日時点の学び残高 × growth_rate を複利として記録。1日1回）
  汎用:       --type X --account H|G|E --amount 数値 --half-life-days 数値 --label 内容
追加後に台帳へ追記した JSON を1行で表示する。ランの重複（同日・距離±0.1km）はエラーにする。
"""
import argparse, json, sys
from datetime import date, datetime, timedelta
from pathlib import Path

def load(base):
    params = json.loads((base / "params.json").read_text(encoding="utf-8"))
    events = []
    f = base / "events.jsonl"
    if f.exists():
        for line in f.read_text(encoding="utf-8").splitlines():
            if line.strip():
                events.append(json.loads(line))
    return params, events

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", default=".")
    ap.add_argument("--date", default=None)
    ap.add_argument("--label", default="")
    ap.add_argument("--run-km", type=float, default=None)
    ap.add_argument("--price", type=float, default=None)
    ap.add_argument("--category", default="その他")
    ap.add_argument("--manage", action="store_true")
    ap.add_argument("--no-manage", action="store_true")
    ap.add_argument("--use-value", type=float, default=None)
    ap.add_argument("--points", type=float, default=None)
    ap.add_argument("--family", action="store_true")
    ap.add_argument("--recorded", action="store_true")
    ap.add_argument("--severity", type=float, default=None)
    ap.add_argument("--reading-min", type=float, default=None)
    ap.add_argument("--book-complete", action="store_true")
    ap.add_argument("--growth", action="store_true")
    ap.add_argument("--type", default=None)
    ap.add_argument("--account", default=None)
    ap.add_argument("--amount", type=float, default=None)
    ap.add_argument("--half-life-days", type=float, default=None)
    a = ap.parse_args()
    base = Path(a.data_dir)
    params, events = load(base)
    d = a.date or date.today().isoformat()
    ev = None

    if a.run_km is not None:
        for e in events:
            if e["type"] == "run" and e["date"] == d and abs(float(e.get("km", -999)) - a.run_km) <= 0.1:
                print("ERROR: 同日・同距離のランが既に台帳にあります", file=sys.stderr)
                sys.exit(2)
        d0 = datetime.strptime(d, "%Y-%m-%d").date()
        n = 1 + sum(1 for e in events if e["type"] == "run"
                    and d0 - timedelta(days=28) <= datetime.strptime(e["date"], "%Y-%m-%d").date() < d0)
        tiers = params["run_half_life_days"]
        hl = tiers["low"] if n <= 3 else tiers["mid"] if n <= 7 else tiers["high"]
        amount = round(params["run_base"] + params["run_per_km"] * a.run_km)
        ev = {"date": d, "type": "run", "account": "H",
              "label": a.label or f"ラン {a.run_km:.1f}km",
              "amount": amount, "half_life_days": hl, "km": a.run_km}
    elif a.price is not None:
        if a.manage and a.no_manage:
            print("ERROR: --manage と --no-manage は同時に指定できません", file=sys.stderr)
            sys.exit(2)
        if not a.manage and not a.no_manage:
            print("ERROR: 購入時点で管理対象とするか判断し、--manage か --no-manage を指定してください", file=sys.stderr)
            sys.exit(2)
        if a.no_manage:
            print("SKIP: 管理対象外のため台帳に載せませんでした")
            sys.exit(3)
        hl = params["purchase_half_life_days"].get(a.category, params["purchase_half_life_days"]["その他"])
        ev = {"date": d, "type": "purchase", "account": "G", "label": a.label,
              "amount": round(a.price), "half_life_days": hl,
              "price": a.price, "category": a.category, "managed": True}
    elif a.use_value is not None:
        if not a.label:
            print("ERROR: 棚卸しの計上には --label で品名が必要です", file=sys.stderr)
            sys.exit(2)
        hl = params["experience_half_life_days_with_record"] if a.recorded else params["experience_half_life_days"]
        ev = {"date": d, "type": "use_value", "account": "E", "label": a.label,
              "amount": round(a.use_value), "half_life_days": hl, "recorded": a.recorded}
    elif a.points is not None:
        mult = params["family_multiplier"] if a.family else 1.0
        hl = params["experience_half_life_days_with_record"] if a.recorded else params["experience_half_life_days"]
        ev = {"date": d, "type": "experience", "account": "E", "label": a.label,
              "amount": round(a.points * params["r_exp"] * mult), "half_life_days": hl,
              "points": a.points, "family": a.family}
    elif a.severity is not None:
        ev = {"date": d, "type": "loss", "account": "E", "label": a.label,
              "amount": -round(a.severity * params["r_loss"]),
              "half_life_days": params["loss_recovery_half_life_days"], "severity": a.severity}
    elif a.reading_min is not None:
        lbl = a.label or f"読書 {a.reading_min:.0f}分"
        for e in events:
            if e["type"] == "reading" and e["date"] == d and float(e.get("minutes", -999)) == a.reading_min and e.get("label", "") == lbl:
                print("ERROR: 同日・同時間・同ラベルの読書が既に台帳にあります", file=sys.stderr)
                sys.exit(2)
        ev = {"date": d, "type": "reading", "account": "S",
              "label": lbl,
              "amount": round(a.reading_min * params.get("reading_per_min", 10)),
              "half_life_days": params.get("reading_half_life_days", 180),
              "minutes": a.reading_min}
    elif a.book_complete:
        if not a.label:
            print("ERROR: 完読には --label で本のタイトルが必要です", file=sys.stderr)
            sys.exit(2)
        for e in events:
            if e["type"] == "reading_complete" and e["date"] == d and e.get("label", "") == a.label:
                print("ERROR: 同日・同タイトルの完読が既に台帳にあります", file=sys.stderr)
                sys.exit(2)
        ev = {"date": d, "type": "reading_complete", "account": "S", "label": a.label,
              "amount": round(params.get("reading_complete_bonus", 1000)),
              "half_life_days": params.get("reading_complete_half_life_days", 365)}
    elif a.growth:
        for e in events:
            if e["type"] == "growth" and e["date"] == d:
                print("ERROR: その日の成長（複利）は記録済みです", file=sys.stderr)
                sys.exit(2)
        d0 = datetime.strptime(d, "%Y-%m-%d").date()
        bal = 0.0
        for e in events:
            if e.get("account") == "S":
                ed = datetime.strptime(e["date"], "%Y-%m-%d").date()
                if ed <= d0:
                    bal += float(e["amount"]) * (0.5 ** ((d0 - ed).days / float(e["half_life_days"])))
        amount = round(bal * params.get("growth_rate", 0.002))
        if amount <= 0:
            print("SKIP: 学び残高が小さいため複利は付きませんでした", file=sys.stderr)
            sys.exit(3)
        ev = {"date": d, "type": "growth", "account": "S",
              "label": a.label or "成長", "amount": amount,
              "half_life_days": params.get("growth_half_life_days", 365),
              "base": round(bal)}
    elif a.type and a.account and a.amount is not None and a.half_life_days is not None:
        ev = {"date": d, "type": a.type, "account": a.account, "label": a.label,
              "amount": a.amount, "half_life_days": a.half_life_days}
    else:
        print("ERROR: モードを指定してください（--run-km / --price / --points / --severity / 汎用）", file=sys.stderr)
        sys.exit(2)

    with open(base / "events.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(ev, ensure_ascii=False) + "\n")
    if ev.get("type") == "purchase" and ev.get("managed"):
        reg = {"date": ev["date"], "label": ev["label"], "price": ev["price"],
               "category": ev["category"]}
        with open(base / "registry.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(reg, ensure_ascii=False) + "\n")
    print(json.dumps(ev, ensure_ascii=False))

if __name__ == "__main__":
    main()
