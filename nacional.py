import json
import os
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

API_KEY = os.environ["API_FOOTBALL_KEY"]
WA_PHONE = os.environ["WA_PHONE"]
WA_KEY = os.environ["WA_APIKEY"]

TZ = "America/Montevideo"
BASE = "https://v3.football.api-sports.io"
HEADERS = {"x-apisports-key": API_KEY}
ESTADO = Path("estado.json")


def cargar_estado():
    if ESTADO.exists():
        return json.loads(ESTADO.read_text())
    return {}


def guardar_estado(estado):
    ESTADO.write_text(json.dumps(estado, indent=2))


def api(endpoint, **params):
    r = requests.get(f"{BASE}/{endpoint}", headers=HEADERS, params=params, timeout=30)
    r.raise_for_status()
    data = r.json()
    if data.get("errors"):
        print("Errores de la API:", data["errors"])
    return data.get("response", [])


def enviar_whatsapp(texto):
    r = requests.get(
        "https://api.callmebot.com/whatsapp.php",
        params={"phone": WA_PHONE, "text": texto, "apikey": WA_KEY},
        timeout=30,
    )
    print("CallMeBot:", r.status_code, r.text[:200])
    r.raise_for_status()


def buscar_id_nacional():
    candidatos = api("teams", search="Nacional")
    for item in candidatos:
        t = item["team"]
        print("Candidato:", t["id"], t["name"], t["country"])
        if t["country"] == "Uruguay" and t["name"] == "Club Nacional":
            return t["id"]
    return None


def main():
    estado = cargar_estado()

    # La primera vez busca el ID de Nacional y lo guarda
    if "team_id" not in estado:
        team_id = buscar_id_nacional()
        if team_id is None:
            print("No encontré a Nacional de Uruguay en la API.")
            sys.exit(1)
        estado["team_id"] = team_id
        guardar_estado(estado)

    hoy = datetime.now(ZoneInfo(TZ)).strftime("%Y-%m-%d")
    partidos = api("fixtures", team=estado["team_id"], date=hoy, timezone=TZ)

    if not partidos:
        print("Hoy no juega Nacional.")
        return

    for p in partidos:
        fid = str(p["fixture"]["id"])
        info = estado.setdefault("partidos", {}).setdefault(
            fid, {"aviso": False, "resultado": False}
        )

        local = p["teams"]["home"]["name"]
        visitante = p["teams"]["away"]["name"]
        hora = datetime.fromisoformat(p["fixture"]["date"]).strftime("%H:%M")
        estadio = p["fixture"]["venue"]["name"] or "a confirmar"
        ciudad = p["fixture"]["venue"]["city"] or ""
        torneo = p["league"]["name"]
        situacion = p["fixture"]["status"]["short"]

        # Mensaje 1: aviso del partido (una sola vez)
        if not info["aviso"]:
            enviar_whatsapp(
                f"⚽ Hoy juega Nacional\n"
                f"{local} vs {visitante}\n"
                f"🕒 {hora} hs\n"
                f"🏟️ {estadio} {ciudad}\n"
                f"🏆 {torneo}"
            )
            info["aviso"] = True
            guardar_estado(estado)

        # Mensaje 2: resultado final (una sola vez)
        if situacion in ("FT", "AET", "PEN") and not info["resultado"]:
            gl = p["goals"]["home"]
            gv = p["goals"]["away"]
            texto = f"🏁 Final: {local} {gl} - {gv} {visitante}\n🏆 {torneo}"
            pen = p["score"]["penalty"]
            if situacion == "PEN" and pen["home"] is not None:
                texto += f"\nPenales: {pen['home']} - {pen['away']}"
            enviar_whatsapp(texto)
            info["resultado"] = True
            guardar_estado(estado)


if __name__ == "__main__":
    main()
