#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
CMC COLLECTOR 2 — RANGO 201-300
"""

import csv
import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import requests


# ============================================================
# CONFIGURACIÓN
# ============================================================

CMC_API_URL = (
    "https://pro-api.coinmarketcap.com/v1/"
    "cryptocurrency/listings/latest"
)

TOP_N = 300
TOP100_MAX = 100
TOP200_MAX = 200
TOP300_MAX = 300


# ============================================================
# ARCHIVOS
# ============================================================

DATA_DIR = Path("data") / "cmc"
CSV_201_300 = DATA_DIR / "market_history_201_300.csv"
ROTATION_FILE = DATA_DIR / "last_rotation.txt"
ARCHIVE_DIR = DATA_DIR / "archives"

DIAS_ROTACION = 3
HORAS_RETENCION_CSV = 72

TIMEOUT = 30


# ============================================================
# GITHUB
# ============================================================

GITHUB_USER = "emerging2"
GITHUB_REPO = "inspector2"
GITHUB_BRANCH = "main"


# ============================================================
# TELEGRAM
# ============================================================

def enviar_telegram(msg):

    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")

    if not token or not chat_id:

        print("Telegram no configurado")

        return False

    try:

        url = (
            f"https://api.telegram.org/"
            f"bot{token}/sendMessage"
        )

        data = {
            "chat_id": chat_id,
            "text": msg,
        }

        r = requests.post(
            url,
            data=data,
            timeout=20,
        )

        return (
            r.status_code == 200
            and r.json().get("ok", False)
        )

    except Exception as e:

        print(f"Error Telegram: {e}")

        return False


# ============================================================
# ROTACIÓN
# ============================================================

def leer_ultima_rotacion():

    if not ROTATION_FILE.exists():

        return None

    try:

        return datetime.fromisoformat(
            ROTATION_FILE.read_text().strip()
        )

    except Exception:

        return None


def guardar_ultima_rotacion(dt):

    DATA_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    ROTATION_FILE.write_text(
        dt.isoformat()
    )


def inicializar_rotacion():

    if not ROTATION_FILE.exists():

        guardar_ultima_rotacion(
            datetime.now(timezone.utc)
        )

        print(
            f"Primera ejecución: "
            f"próxima rotación en "
            f"{DIAS_ROTACION} días"
        )

        return True

    return False


def toca_rotar():

    ultima = leer_ultima_rotacion()

    if ultima is None:

        return False

    ahora = datetime.now(
        timezone.utc
    )

    if ultima.tzinfo is None:

        ultima = ultima.replace(
            tzinfo=timezone.utc
        )

    return (
        ahora - ultima
    ) >= timedelta(
        days=DIAS_ROTACION
    )


def rotar_csv():
    """
    Rota el CSV 201-300 conservando 72h en el CSV activo.
    El resto se mueve al archive (que se puede borrar tras descargar).
    """

    if not CSV_201_300.exists():

        print(
            "No hay CSV 201-300 para rotar."
        )

        return None

    ARCHIVE_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    ahora = datetime.now(
        timezone.utc
    )

    sufijo = ahora.strftime(
        "%Y%m%d_%H%M"
    )

    # --------------------------------------------------------
    # LEER CSV ACTUAL
    # --------------------------------------------------------

    try:

        df = pd.read_csv(
            CSV_201_300
        )

    except Exception as e:

        print(
            f"Error leyendo "
            f"{CSV_201_300.name}: {e}"
        )

        return None

    if len(df) == 0:

        print(
            f"{CSV_201_300.name} vacío, "
            f"se omite"
        )

        return None

    # --------------------------------------------------------
    # NORMALIZAR TIMESTAMP (con parche)
    # --------------------------------------------------------

    df["timestamp"] = parsear_timestamps(df["timestamp"])

    df = df.dropna(
        subset=["timestamp"]
    )

    df = df.sort_values(
        "timestamp"
    )

    # --------------------------------------------------------
    # CORTE 72H (desde AHORA, no desde el último dato)
    # --------------------------------------------------------

    ts_max = df["timestamp"].max()

    corte = pd.Timestamp(ahora) - timedelta(hours=HORAS_RETENCION_CSV)

    df_reciente = df[
        df["timestamp"] >= corte
    ].copy()

    df_viejo = df[
        df["timestamp"] < corte
    ].copy()

    # --------------------------------------------------------
    # ARCHIVE: SOLO LO VIEJO
    # --------------------------------------------------------

    tamaño_archive = 0

    destino = None

    if len(df_viejo) > 0:

        destino = (
            ARCHIVE_DIR
            / f"201_300_{sufijo}.csv"
        )

        guardar_csv_normalizado(df_viejo, destino)

        tamaño_archive = (
            destino.stat().st_size
            / (1024 * 1024)
        )

        print(
            f"Archivado 201-300: "
            f"{len(df_viejo):,} filas "
            f"({tamaño_archive:.2f} MB)"
        )

    else:

        print(
            f"201-300: nada que archivar "
            f"(todo dentro de "
            f"{HORAS_RETENCION_CSV}h)"
        )

    # --------------------------------------------------------
    # CSV ACTIVO: SOLO ÚLTIMAS 72H
    # --------------------------------------------------------

    guardar_csv_normalizado(df_reciente, CSV_201_300)

    print(
        f"CSV 201-300 conserva "
        f"{len(df_reciente):,} filas "
        f"(desde "
        f"{df_reciente['timestamp'].min()} "
        f"hasta {ts_max})"
    )

    # --------------------------------------------------------
    # INFO PARA TELEGRAM
    # --------------------------------------------------------

    info = {

        "fecha": ahora,

        "archivos": (
            [
                {
                    "nombre": destino.name,
                    "tipo": "201_300",
                    "tamaño_mb": tamaño_archive,
                }
            ]
            if destino is not None and tamaño_archive > 0
            else []
        ),

        "tamaño_total_mb": tamaño_archive,
    }

    guardar_ultima_rotacion(
        ahora
    )

    return info


def notificar_rotacion(info):

    if not info:

        return

    fecha_lima = (
        info["fecha"]
        - timedelta(hours=5)
    )

    lineas = []

    for archivo in info["archivos"]:

        url_raw = (
            f"https://raw.githubusercontent.com/"
            f"{GITHUB_USER}/"
            f"{GITHUB_REPO}/"
            f"{GITHUB_BRANCH}/"
            f"data/cmc/archives/"
            f"{archivo['nombre']}"
        )

        lineas.append(
            f"📄 {archivo['tipo'].upper()}\n"
            f"{archivo['nombre']}\n"
            f"{url_raw}"
        )

    msg = (
        "📦 CMC CACHE 201-300\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        f"📅 Cierre: "
        f"{fecha_lima.strftime('%Y-%m-%d %H:%M')} Lima\n"
        f"💾 Total: "
        f"{info['tamaño_total_mb']:.2f} MB\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        + "\n\n".join(lineas)
        + "\n━━━━━━━━━━━━━━━━━━━"
    )

    if enviar_telegram(msg):

        print(
            "Telegram enviado."
        )

    else:

        print(
            "Fallo Telegram."
        )


# ============================================================
# UTILIDADES DE TIMESTAMP (PARCHE)
# ============================================================

FORMATO_TS = "%Y-%m-%dT%H:%M:%S+00:00"


def parsear_timestamps(col):
    """ISO8601 -> mixto -> epoch. Lo que no se pueda leer queda NaT."""
    s = col.astype(str).str.strip()
    t = pd.to_datetime(s, utc=True, errors="coerce", format="ISO8601")
    mal = t.isna()
    if mal.any():
        try:
            t2 = pd.to_datetime(s[mal], utc=True, errors="coerce", format="mixed")
        except (ValueError, TypeError):
            t2 = pd.to_datetime(s[mal], utc=True, errors="coerce")
        t = t.fillna(t2)
        mal = t.isna()
    if mal.any():
        n = pd.to_numeric(s[mal], errors="coerce").dropna()
        if len(n):
            ms, sg = n[n > 1e11], n[n <= 1e11]
            if len(ms):
                t.loc[ms.index] = pd.to_datetime(ms, unit="ms", utc=True)
            if len(sg):
                t.loc[sg.index] = pd.to_datetime(sg, unit="s", utc=True)
    return t


def guardar_csv_normalizado(df, ruta):
    """Escribe el CSV con UN solo formato de timestamp (ISO con T, sin fracción, +00:00)."""
    out = df.copy()
    out["timestamp"] = out["timestamp"].dt.tz_convert("UTC").dt.strftime(FORMATO_TS)
    out.to_csv(ruta, index=False)


def limpiar_csv_viejo(csv_path, tipo, ahora=None):
    """
    Deja SOLO las últimas HORAS_RETENCION_CSV horas contadas desde AHORA
    (no desde el último dato del archivo). Reescribe el archivo con un formato
    de timestamp único. Las filas con timestamp ilegible NO se borran en silencio:
    se guardan en archives/ y se avisa por pantalla.
    """
    if not csv_path.exists():
        return

    ahora = pd.Timestamp(ahora or datetime.now(timezone.utc))
    if ahora.tzinfo is None:
        ahora = ahora.tz_localize("UTC")

    try:
        df = pd.read_csv(csv_path, low_memory=False)
        if len(df) == 0:
            return
        n0 = len(df)

        df["timestamp"] = parsear_timestamps(df["timestamp"])
        ilegibles = df[df["timestamp"].isna()]
        df = df.dropna(subset=["timestamp"]).sort_values("timestamp")

        corte = ahora - timedelta(hours=HORAS_RETENCION_CSV)
        reciente = df[df["timestamp"] >= corte]
        n_viejas = int((df["timestamp"] < corte).sum())

        if len(ilegibles) > 0:
            ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
            ruta_ileg = ARCHIVE_DIR / f"{tipo}_ilegibles_{ahora.strftime('%Y%m%d_%H%M')}.csv"
            ilegibles.to_csv(ruta_ileg, index=False)
            print(f"   ⚠️ {len(ilegibles):,} filas con timestamp ilegible -> {ruta_ileg.name}")

        guardar_csv_normalizado(reciente, csv_path)

        ts_min = reciente["timestamp"].min() if len(reciente) else None
        print(f"   🧹 {tipo}: {n0:,} filas -> {len(reciente):,} "
              f"(quitadas {n_viejas:,} de más de {HORAS_RETENCION_CSV}h"
              f"{'; datos desde ' + ts_min.strftime('%d-%b %H:%M') + ' UTC' if ts_min is not None else ''})")

    except Exception as e:
        print(f"Error limpiando {tipo}: {e}")


# ============================================================
# COLUMNAS
# ============================================================

CSV_COLUMNS = [
    "snapshot_id", "timestamp",
    "cmc_id", "name", "symbol", "slug",
    "cmc_rank", "segment",
    "price",
    "percent_change_1h", "percent_change_24h", "percent_change_7d",
    "percent_change_30d", "percent_change_60d", "percent_change_90d",
    "volume_24h", "volume_change_24h",
    "market_cap", "market_cap_dominance",
    "volume_marketcap_ratio", "marketcap_volume_ratio",
    "is_top100", "is_top200", "is_top300",
    "rank_gainer_300", "rank_loser_300", "rank_volume_300",
    "rank_gainer_segment", "rank_volume_segment",
]


# ============================================================
# UTILIDADES GENERALES
# ============================================================

def get_api_key():
    api_key = os.getenv("CMC_API_KEY")
    if not api_key:
        print("ERROR: No existe CMC_API_KEY.")
        sys.exit(1)
    return api_key


def safe_float(value):
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def create_snapshot_id(timestamp):
    return timestamp.strftime("%Y%m%d_%H%M%S")


def segmento(rank):
    if rank <= 100:
        return "top100"
    if rank <= 200:
        return "101_200"
    if rank <= 300:
        return "201_300"
    return "outside"


# ============================================================
# FETCH CMC
# ============================================================

def fetch_monedas(api_key):
    headers = {
        "Accepts": "application/json",
        "X-CMC_PRO_API_KEY": api_key,
    }
    params = {
        "start": 1,
        "limit": TOP_N,
        "convert": "USD",
        "sort": "market_cap",
        "sort_dir": "desc",
        "cryptocurrency_type": "all",
    }

    print(f"Consultando CoinMarketCap (TOP {TOP_N})...")
    r = requests.get(CMC_API_URL, headers=headers, params=params, timeout=TIMEOUT)
    print(f"HTTP: {r.status_code}")

    if r.status_code != 200:
        print(r.text)
        r.raise_for_status()

    payload = r.json()
    status = payload.get("status", {})

    if status.get("error_code", 0) != 0:
        print("ERROR CMC:", status)
        sys.exit(1)

    data = payload.get("data", [])
    if not data:
        print("ERROR: CMC no devolvió monedas.")
        sys.exit(1)

    print(f"Monedas recibidas: {len(data)}")
    print(f"Credits utilizados: {status.get('credit_count')}")
    return data


# ============================================================
# RANKINGS
# ============================================================

def calculate_rankings(coins):
    def change_24h(c):
        q = c.get("quote", {}).get("USD", {})
        return safe_float(q.get("percent_change_24h"))

    def volume(c):
        q = c.get("quote", {}).get("USD", {})
        return safe_float(q.get("volume_24h"))

    losers = sorted(coins, key=lambda c: (change_24h(c) if change_24h(c) is not None else float("inf")))
    gainers = sorted(coins, key=lambda c: (change_24h(c) if change_24h(c) is not None else float("-inf")), reverse=True)
    volumes = sorted(coins, key=lambda c: (volume(c) if volume(c) is not None else float("-inf")), reverse=True)

    return (
        {c["id"]: p for p, c in enumerate(losers, start=1)},
        {c["id"]: p for p, c in enumerate(gainers, start=1)},
        {c["id"]: p for p, c in enumerate(volumes, start=1)},
    )


def calculate_segment_rankings(coins):
    resultado = {}
    segmentos = {"top100": [], "101_200": [], "201_300": []}

    for coin in coins:
        rank = (coin.get("cmc_rank") or 99999)
        seg = segmento(rank)
        if seg in segmentos:
            segmentos[seg].append(coin)

    for seg, lista in segmentos.items():
        if not lista:
            continue

        def ch(c):
            return safe_float(c.get("quote", {}).get("USD", {}).get("percent_change_24h"))

        def vol(c):
            return safe_float(c.get("quote", {}).get("USD", {}).get("volume_24h"))

        gainers = sorted(lista, key=lambda c: ch(c) if ch(c) is not None else float("-inf"), reverse=True)
        volumes = sorted(lista, key=lambda c: vol(c) if vol(c) is not None else float("-inf"), reverse=True)

        resultado[seg] = {
            "gainer": {c["id"]: p for p, c in enumerate(gainers, start=1)},
            "volume": {c["id"]: p for p, c in enumerate(volumes, start=1)},
        }

    return resultado


# ============================================================
# CONSTRUIR REGISTROS
# ============================================================

def build_records(coins, timestamp):
    snapshot_id = create_snapshot_id(timestamp)
    loser_rank, gainer_rank, volume_rank = calculate_rankings(coins)
    segment_rankings = calculate_segment_rankings(coins)

    records = []

    for coin in coins:
        q = coin.get("quote", {}).get("USD", {})
        rank = (coin.get("cmc_rank") or 99999)
        seg = segmento(rank)

        if seg != "201_300":
            continue

        price = safe_float(q.get("price"))
        volume_24h = safe_float(q.get("volume_24h"))
        market_cap = safe_float(q.get("market_cap"))

        if volume_24h is not None and market_cap is not None and market_cap > 0:
            volume_marketcap_ratio = volume_24h / market_cap * 100
            marketcap_volume_ratio = market_cap / volume_24h if volume_24h > 0 else None
        else:
            volume_marketcap_ratio = None
            marketcap_volume_ratio = None

        seg_gainer = None
        seg_volume = None
        if seg in segment_rankings:
            seg_gainer = segment_rankings[seg]["gainer"].get(coin.get("id"))
            seg_volume = segment_rankings[seg]["volume"].get(coin.get("id"))

        records.append({
            "snapshot_id": snapshot_id,
            "timestamp": timestamp.replace(microsecond=0).isoformat(),
            "cmc_id": coin.get("id"),
            "name": coin.get("name"),
            "symbol": coin.get("symbol"),
            "slug": coin.get("slug"),
            "cmc_rank": rank,
            "segment": seg,
            "price": price,
            "percent_change_1h": safe_float(q.get("percent_change_1h")),
            "percent_change_24h": safe_float(q.get("percent_change_24h")),
            "percent_change_7d": safe_float(q.get("percent_change_7d")),
            "percent_change_30d": safe_float(q.get("percent_change_30d")),
            "percent_change_60d": safe_float(q.get("percent_change_60d")),
            "percent_change_90d": safe_float(q.get("percent_change_90d")),
            "volume_24h": volume_24h,
            "volume_change_24h": safe_float(q.get("volume_change_24h")),
            "market_cap": market_cap,
            "market_cap_dominance": safe_float(q.get("market_cap_dominance")),
            "volume_marketcap_ratio": volume_marketcap_ratio,
            "marketcap_volume_ratio": marketcap_volume_ratio,
            "is_top100": 0,
            "is_top200": 0,
            "is_top300": 1,
            "rank_gainer_300": gainer_rank.get(coin.get("id")),
            "rank_loser_300": loser_rank.get(coin.get("id")),
            "rank_volume_300": volume_rank.get(coin.get("id")),
            "rank_gainer_segment": seg_gainer,
            "rank_volume_segment": seg_volume,
        })

    return records


# ============================================================
# GUARDADO
# ============================================================

def save_records(records, archivo):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    file_exists = archivo.exists()

    with archivo.open("a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        if not file_exists:
            writer.writeheader()
        writer.writerows(records)

    print(f"Guardado: {len(records)} registros → {archivo.name}")


# ============================================================
# MAIN
# ============================================================

def main():
    print("\n" + "=" * 100)
    print("🚨 CMC COLLECTOR — RANGO 201-300")
    print("=" * 100)

    inicializar_rotacion()

    if toca_rotar():
        print(f"Han pasado {DIAS_ROTACION}+ días.")
        print("Rotando histórico 201-300...")
        info = rotar_csv()
        if info:
            notificar_rotacion(info)
    else:
        ultima = leer_ultima_rotacion()
        if ultima:
            ahora = datetime.now(timezone.utc)
            if ultima.tzinfo is None:
                ultima = ultima.replace(tzinfo=timezone.utc)
            dias_transcurridos = (ahora - ultima).total_seconds() / 86400
            dias_restantes = max(0, DIAS_ROTACION - dias_transcurridos)
            print(f"Próxima rotación en ~{dias_restantes:.1f} días")

    print()
    print("🧹 Forzando limpieza de CSV 201-300 (últimas 72h)...")
    limpiar_csv_viejo(CSV_201_300, "201_300")

    api_key = get_api_key()
    timestamp = datetime.now(timezone.utc)
    coins = fetch_monedas(api_key)

    top100 = []
    rango101_200 = []
    rango201_300 = []

    for coin in coins:
        rank = (coin.get("cmc_rank") or 99999)
        if rank <= 100:
            top100.append(coin)
        elif rank <= 200:
            rango101_200.append(coin)
        elif rank <= 300:
            rango201_300.append(coin)

    print()
    print("División TOP 300:")
    print(f"  TOP 100:   {len(top100)}")
    print(f"  101-200:   {len(rango101_200)}")
    print(f"  201-300:   {len(rango201_300)}")

    records = build_records(coins, timestamp)
    save_records(records, CSV_201_300)

    print()
    print("=" * 100)
    print("✅ CAPTURA 201-300 FINALIZADA")
    print("=" * 100)
    print(f"Snapshot: {timestamp.isoformat()}")
    print(f"Monedas 201-300 guardadas: {len(records)}")
    print(f"Archivo: {CSV_201_300}")


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
