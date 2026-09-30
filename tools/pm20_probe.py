#!/usr/bin/env python3
"""Dreame PM20 (dreame.airp.u2402) salt okunur özellik taraması.

SADECE OKUR. Bu dosyada cihaza yazan ya da action çağıran kod yoktur ve
eklenmemelidir: izin verilen tek RPC yöntemi "get_properties".

Kullanım (kullanıcı kendi terminalinde çalıştırır; e-posta ve parola gizli
istemde sorulur, hiçbir yere yazılmaz):

    python3 tools/pm20_probe.py sweep
    python3 tools/pm20_probe.py snapshot sabah-1
    python3 tools/pm20_probe.py diff sabah-1 sabah-2

Çıktılar: ./pm20-probe/  (parola ve erişim anahtarı yazılmaz; did/sn içerir, paylaşmayın)

Tel protokolü bilgileri (uç noktalar, başlıklar, uygulama tuzu) Dreamehome
uygulamasından çıkarılmış olgulardır; kaynak: KalfDmytro/dreame-pm30-integration
(MIT) api/protocol.py ve tools/_cloud.py. Kod burada yeniden yazılmıştır.
"""
from __future__ import annotations

import argparse
import getpass
import hashlib
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

OUT_DIR = Path.cwd() / "pm20-probe"  # sonuçlar çalıştırılan klasöre yazılır
ALLOWED_METHODS = frozenset({"get_properties"})  # başka hiçbir yöntem gönderilemez

# ── Dreamehome uygulamasından çıkarılmış sabitler (olgu, gizli değil) ──
SALT = "RAylYC%fmSKp7%Tq"
AUTH_BASIC = "Basic ZHJlYW1lX2FwcHYxOkFQXmR2QHpAU1FZVnhOODg="
USER_AGENT = "Dreame_Smarthome/2.1.9 (iPhone; iOS 18.4.1; Scale/3.00)"
DEFAULT_TENANT = "000000"
REGIONS = ("eu", "sg", "ru", "us", "kr", "cn")
PORT = 13267
TIMEOUT = 20

_req_id = int(time.time()) % 100000


def _next_id() -> int:
    global _req_id
    _req_id += 1  # her istekte farklı olmalı; aynı id yanıtların karışmasına yol açıyor
    return _req_id


def _post(url: str, headers: dict, body: bytes) -> tuple[int, object]:
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:  # noqa: S310
            raw = r.read().decode("utf-8", "replace")
            status = r.status
    except urllib.error.HTTPError as ex:
        raw, status = ex.read().decode("utf-8", "replace"), ex.code
    except (urllib.error.URLError, TimeoutError, OSError) as ex:
        return 0, {"_error": str(ex)}
    try:
        return status, json.loads(raw)
    except json.JSONDecodeError:
        return status, {"_raw": raw[:300]}


class Cloud:
    def __init__(self, region: str) -> None:
        self.region = region
        self.base = f"https://{region}.iot.dreame.tech:{PORT}"
        self.token: str | None = None
        self.tenant = DEFAULT_TENANT

    def login(self, username: str, password: str) -> dict:
        pw = hashlib.md5((password + SALT).encode()).hexdigest()  # noqa: S324 (Dreame'in seçimi)
        body = ("platform=IOS&scope=all&grant_type=password&type=account"
                f"&username={urllib.parse.quote(username)}&password={pw}").encode()
        headers = {"User-Agent": USER_AGENT, "Authorization": AUTH_BASIC, "Tenant-Id": DEFAULT_TENANT,
                   "Content-Type": "application/x-www-form-urlencoded", "Accept": "*/*"}
        status, data = _post(f"{self.base}/dreame-auth/oauth/token", headers, body)
        if status == 200 and isinstance(data, dict) and data.get("access_token"):
            self.token = data["access_token"]
            self.tenant = data.get("tenant_id") or DEFAULT_TENANT
            return {"ok": True}
        err = data.get("error") if isinstance(data, dict) else None
        return {"ok": False, "status": status, "error": err}

    def _api(self, path: str, payload: dict) -> tuple[int, object]:
        headers = {"User-Agent": USER_AGENT, "Authorization": AUTH_BASIC, "Tenant-Id": self.tenant,
                   "Dreame-Auth": self.token or "", "Content-Type": "application/json", "Accept": "*/*"}
        return _post(f"{self.base}{path}", headers, json.dumps(payload).encode())

    def devices(self) -> list[dict]:
        status, data = self._api("/dreame-user-iot/iotuserbind/device/listV2", {})
        try:
            return data["data"]["page"]["records"]  # type: ignore[index]
        except (KeyError, TypeError):
            print(f"  cihaz listesi alınamadı: {status} {str(data)[:200]}")
            return []

    def rpc(self, did: str, bind_domain: str | None, method: str, params: list) -> object:
        if method not in ALLOWED_METHODS:
            raise RuntimeError(f"YASAK yöntem: {method} (bu araç sadece okur)")
        rid = _next_id()
        shard = f"-{bind_domain.split('.')[0]}" if bind_domain else ""
        payload = {"did": str(did), "id": rid,
                   "data": {"did": str(did), "id": rid, "method": method, "params": params}}
        for delay in (1, 3, None):  # 80001 (cihaz zaman aşımı) geçicidir: 1 sn ve 3 sn sonra tekrar
            status, data = self._api(f"/dreame-iot-com{shard}/device/sendCommand", payload)
            code = data.get("code") if isinstance(data, dict) else None
            if code == 0:
                inner = data.get("data")
                if isinstance(inner, dict) and "result" in inner:
                    return inner["result"]
            if code != 80001 or delay is None:
                return {"_fail": True, "status": status, "code": code}
            time.sleep(delay)
            rid = _next_id()  # her denemede yeni id
            payload["id"] = payload["data"]["id"] = rid
        return {"_fail": True}

    def read(self, did: str, bind: str | None, props: list[tuple[int, int]], pause: float = 0.35) -> list[dict]:
        """Grup hâlinde okur; grup başarısız olursa tek tek dener (grup bütün olarak düşebiliyor)."""
        out: list[dict] = []
        for i in range(0, len(props), 10):
            batch = props[i:i + 10]
            res = self.rpc(did, bind, "get_properties", [{"did": str(did), "siid": s, "piid": p} for s, p in batch])
            time.sleep(pause)
            if isinstance(res, list):
                out.extend(res)
                continue
            for s, p in batch:
                r1 = self.rpc(did, bind, "get_properties", [{"did": str(did), "siid": s, "piid": p}])
                time.sleep(pause)
                out.extend(r1 if isinstance(r1, list) else [{"siid": s, "piid": p, "code": None, "_batch_failed": True}])
        return out


def connect() -> tuple[Cloud, dict]:
    print("Dreame hesabı (yedek hesap önerilir). Parola ekranda görünmez ve hiçbir yere kaydedilmez.")
    username = input("  E-posta: ").strip()
    password = getpass.getpass("  Parola: ")
    region = input(f"  Bölge {REGIONS} [süpürgede seçtiğin, boş=otomatik]: ").strip().lower()
    for cand in ([region] if region else list(REGIONS)):
        cloud = Cloud(cand)
        r = cloud.login(username, password)
        if r["ok"]:
            print(f"  giriş başarılı, bölge: {cand}")
            devs = cloud.devices()
            airp = [d for d in devs if ".airp." in str(d.get("model", ""))]
            print(f"  hesapta {len(devs)} cihaz; hava temizleyici: {[d.get('model') for d in airp]}")
            if not airp:
                if region:
                    sys.exit("  Bu hesapta/bölgede hava temizleyici yok. PM20 bu hesaba paylaşıldı mı?")
                continue
            del password
            return cloud, airp[0]
        print(f"  bölge {cand}: giriş olmadı ({r.get('error') or r.get('status')})")
        if r.get("error") == "invalid_user":
            sys.exit("  E-posta ya da parola hatalı. (Denemeyi sürdürmüyorum, hesap kilitlenmesin.)")
        time.sleep(1.5)
    sys.exit("  Hiçbir bölgede PM20 bulunamadı.")


def _meta(dev: dict) -> dict:
    return {k: dev.get(k) for k in ("model", "customName", "deviceName", "did", "bindDomain", "online", "ver", "sn")}


def cmd_sweep(args) -> None:
    cloud, dev = connect()
    did, bind = str(dev["did"]), dev.get("bindDomain")
    props = [(s, p) for s in range(1, args.max_siid + 1) for p in range(1, args.max_piid + 1)]
    print(f"  {dev.get('model')} taranıyor: {len(props)} adres (sadece okuma), birkaç dakika sürer...")
    t0 = time.time()
    res = cloud.read(did, bind, props)
    found = [r for r in res if r.get("code") == 0 and r.get("value") is not None]
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M")
    out = OUT_DIR / f"sweep-{stamp}.json"
    out.write_text(json.dumps({"device": _meta(dev), "region": cloud.region, "found": found,
                               "failed_batches": sum(1 for r in res if r.get("_batch_failed")),
                               "seconds": round(time.time() - t0)}, ensure_ascii=False, indent=1))
    print(f"  bitti: {len(found)} okunabilir özellik, {round(time.time() - t0)} sn → {out}")
    for r in found:
        print(f"    {r['siid']:>2},{r['piid']:<2} = {json.dumps(r['value'], ensure_ascii=False)[:60]}")


def _latest_sweep() -> dict:
    files = sorted(OUT_DIR.glob("sweep-*.json"))
    if not files:
        sys.exit("  Önce 'sweep' çalıştır.")
    return json.loads(files[-1].read_text())


def cmd_snapshot(args) -> None:
    sweep = _latest_sweep()
    props = [(r["siid"], r["piid"]) for r in sweep["found"]]
    cloud, dev = connect()
    res = cloud.read(str(dev["did"]), dev.get("bindDomain"), props)
    vals = {f"{r['siid']},{r['piid']}": r.get("value") for r in res if r.get("code") == 0}
    out = OUT_DIR / f"snap-{args.name}.json"
    out.write_text(json.dumps({"time": datetime.now().isoformat(timespec="seconds"), "values": vals},
                              ensure_ascii=False, indent=1))
    print(f"  {len(vals)} değer → {out}")


def cmd_diff(args) -> None:
    a = json.loads((OUT_DIR / f"snap-{args.a}.json").read_text())["values"]
    b = json.loads((OUT_DIR / f"snap-{args.b}.json").read_text())["values"]
    ch = [(k, a.get(k), b.get(k)) for k in sorted(set(a) | set(b), key=lambda x: tuple(map(int, x.split(","))))
          if a.get(k) != b.get(k)]
    print(f"  {len(ch)} değişen adres:")
    for k, x, y in ch:
        print(f"    {k:>6}: {json.dumps(x, ensure_ascii=False)[:40]} → {json.dumps(y, ensure_ascii=False)[:40]}")


def main() -> None:
    ap = argparse.ArgumentParser(description="PM20 salt okunur tarama")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("sweep", help="tüm siid/piid adreslerini oku")
    s.add_argument("--max-siid", type=int, default=40)
    s.add_argument("--max-piid", type=int, default=30)
    s.set_defaults(func=cmd_sweep)
    n = sub.add_parser("snapshot", help="bulunan adreslerin anlık görüntüsü")
    n.add_argument("name")
    n.set_defaults(func=cmd_snapshot)
    d = sub.add_parser("diff", help="iki anlık görüntüyü karşılaştır")
    d.add_argument("a")
    d.add_argument("b")
    d.set_defaults(func=cmd_diff)
    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
