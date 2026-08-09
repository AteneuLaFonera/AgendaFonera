"""
Agenda Fonera — generador del calendari HTML

Llegeix els esdeveniments del calendari "Agenda Fonera" de Google Calendar,
descarrega els cartells adjunts i genera el fitxer HTML públic.

Ús:
    python generar_agenda.py

Sortida:
    sortida/index.html      -> el calendari, llest per obrir o per pujar al hosting
    sortida/imatges/        -> els cartells descarregats
"""

import os
import re
import json
import shutil
import unicodedata
from datetime import datetime

import requests

from config import API_KEY, CALENDAR_ID

# ---------------------------------------------------------------------------
# Configuració
# ---------------------------------------------------------------------------

PLANTILLA = "plantilla.html"
CARPETA_SORTIDA = "sortida"
CARPETA_IMATGES = os.path.join(CARPETA_SORTIDA, "imatges")

# Els esdeveniments amb aquesta marca al títol no es publiquen al web.
# Exemple: un esdeveniment titulat "[intern] Reunió de coordinació" s'ignora.
MARCA_PRIVAT = "[intern]"

MESOS = ["gener", "febrer", "març", "abril", "maig", "juny",
         "juliol", "agost", "setembre", "octubre", "novembre", "desembre"]


# ---------------------------------------------------------------------------
# Lectura del calendari
# ---------------------------------------------------------------------------

def descarrega_esdeveniments():
    """Baixa tots els esdeveniments del calendari, paginant si cal."""
    url = f"https://www.googleapis.com/calendar/v3/calendars/{CALENDAR_ID}/events"
    tots = []
    page_token = None

    while True:
        params = {
            "key": API_KEY,
            "singleEvents": True,
            "orderBy": "startTime",
            "maxResults": 2500,
        }
        if page_token:
            params["pageToken"] = page_token

        r = requests.get(url, params=params, timeout=30)
        if r.status_code != 200:
            raise RuntimeError(f"Error llegint el calendari ({r.status_code}): {r.text}")

        dades = r.json()
        tots.extend(dades.get("items", []))

        page_token = dades.get("nextPageToken")
        if not page_token:
            break

    return tots


# ---------------------------------------------------------------------------
# Imatges
# ---------------------------------------------------------------------------

def id_de_drive(file_url):
    """Extreu l'ID del fitxer a partir de la URL de Drive."""
    if not file_url:
        return None
    m = re.search(r"[?&]id=([a-zA-Z0-9_-]+)", file_url)
    if m:
        return m.group(1)
    m = re.search(r"/d/([a-zA-Z0-9_-]+)", file_url)
    return m.group(1) if m else None


def nom_segur(text):
    """Converteix un text en un nom de fitxer sense accents ni espais."""
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    text = re.sub(r"[^\w\s.-]", "", text).strip().replace(" ", "_")
    return re.sub(r"_+", "_", text)


def baixa_cartell(file_id, nom_base):
    """
    Descarrega el cartell des de Drive.
    Retorna la ruta relativa per a l'HTML, o None si no s'ha pogut.
    """
    desti = os.path.join(CARPETA_IMATGES, f"{nom_base}.jpg")
    relatiu = f"imatges/{nom_base}.jpg"

    # Si ja el tenim d'una execució anterior, no el tornem a baixar
    if os.path.exists(desti):
        return relatiu

    url = f"https://drive.google.com/thumbnail?id={file_id}&sz=w1200"
    try:
        r = requests.get(url, timeout=30)
    except requests.RequestException:
        return None

    if r.status_code == 200 and r.headers.get("content-type", "").startswith("image"):
        os.makedirs(CARPETA_IMATGES, exist_ok=True)
        with open(desti, "wb") as f:
            f.write(r.content)
        return relatiu

    return None


# ---------------------------------------------------------------------------
# Transformació de dades
# ---------------------------------------------------------------------------

def formata_hora(inici, fi):
    """Genera l'etiqueta d'horari que es mostra al web."""
    if "date" in inici:          # esdeveniment de tot el dia
        return "Tot el dia"

    h_inici = datetime.fromisoformat(inici["dateTime"]).strftime("%H:%M")
    if fi and "dateTime" in fi:
        h_fi = datetime.fromisoformat(fi["dateTime"]).strftime("%H:%M")
        if h_fi != h_inici:
            return f"{h_inici} – {h_fi}"
    return h_inici


def neteja_descripcio(text):
    """Google Calendar pot retornar HTML a la descripció; el passem a text pla."""
    if not text:
        return ""
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.I)
    text = re.sub(r"</p>", "\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", "", text)
    text = (text.replace("&nbsp;", " ").replace("&amp;", "&")
                .replace("&lt;", "<").replace("&gt;", ">").replace("&quot;", '"'))
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def prepara(esdeveniments):
    """Converteix els esdeveniments de Google al format que espera l'HTML."""
    resultat = []
    saltats = 0

    for ev in esdeveniments:
        titol = (ev.get("summary") or "").strip()

        if not titol:
            saltats += 1
            continue

        if MARCA_PRIVAT.lower() in titol.lower():
            saltats += 1
            continue

        inici = ev.get("start", {})
        data = inici.get("date") or inici.get("dateTime", "")[:10]
        if not data:
            saltats += 1
            continue

        item = {
            "date": data,
            "time": formata_hora(inici, ev.get("end", {})),
            "title": titol,
            "place": (ev.get("location") or "").strip(),
            "desc": neteja_descripcio(ev.get("description")),
        }

        # Cartell adjunt (agafem el primer que sigui una imatge)
        for adjunt in ev.get("attachments", []):
            if not (adjunt.get("mimeType") or "").startswith("image"):
                continue
            file_id = id_de_drive(adjunt.get("fileUrl"))
            if not file_id:
                continue
            nom = nom_segur(f"{data}_{titol}")[:60]
            ruta = baixa_cartell(file_id, nom)
            if ruta:
                item["poster"] = ruta
                print(f"   cartell: {ruta}")
            else:
                print(f"   !! no s'ha pogut baixar el cartell de «{titol}» "
                      f"(revisa que el fitxer sigui accessible amb l'enllaç)")
            break

        resultat.append(item)

    return resultat, saltats


# ---------------------------------------------------------------------------
# Generació de l'HTML
# ---------------------------------------------------------------------------

def mes_inicial(events):
    """
    El calendari s'obre al mes actual si hi ha activitats;
    si no, al primer mes futur que en tingui; si no, al més recent.
    """
    avui = datetime.now()
    mesos = sorted({e["date"][:7] for e in events})
    if not mesos:
        return avui.year, avui.month

    actual = avui.strftime("%Y-%m")
    if actual in mesos:
        return avui.year, avui.month

    futurs = [m for m in mesos if m > actual]
    triat = futurs[0] if futurs else mesos[-1]
    any_, mes = triat.split("-")
    return int(any_), int(mes)


def genera_html(events):
    with open(PLANTILLA, encoding="utf-8") as f:
        plantilla = f.read()

    dades = json.dumps(events, ensure_ascii=False, indent=1)
    html = plantilla.replace("/*__EVENTS__*/[]", dades)

    any_, mes = mes_inicial(events)
    html = html.replace("/*__START_MONTH__*/new Date()",
                        f"new Date({any_},{mes - 1},1)")

    os.makedirs(CARPETA_SORTIDA, exist_ok=True)
    desti = os.path.join(CARPETA_SORTIDA, "index.html")
    with open(desti, "w", encoding="utf-8") as f:
        f.write(html)

    return desti, any_, mes


# ---------------------------------------------------------------------------

def main():
    print("Llegint el calendari...")
    bruts = descarrega_esdeveniments()
    print(f"   {len(bruts)} esdeveniments trobats\n")

    print("Preparant les dades i descarregant cartells...")
    events, saltats = prepara(bruts)
    amb_cartell = sum(1 for e in events if "poster" in e)
    print(f"   {len(events)} publicats · {amb_cartell} amb cartell · {saltats} omesos\n")

    desti, any_, mes = genera_html(events)

    mesos_coberts = sorted({e["date"][:7] for e in events})
    print("Fet!")
    print(f"   Fitxer generat: {os.path.abspath(desti)}")
    print(f"   S'obre a: {MESOS[mes - 1]} {any_}")
    if mesos_coberts:
        print(f"   Mesos amb activitat: {mesos_coberts[0]} → {mesos_coberts[-1]}")
    print("\n   Per publicar-ho, puja tot el contingut de la carpeta "
          f"'{CARPETA_SORTIDA}' al hosting.")


if __name__ == "__main__":
    main()
