#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
CMC COLLECTOR 2 — RANGO 201-300  (v4: híbrido 4 días)
"""

import csv
import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

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

# ============================================================
# ARCHIVOS (v4: archivo activo de 4 días)
# ============================================================

DATA_DIR = Path("data") / "cmc"
CSV_201_300 = DATA_DIR / "market_history_201_300.csv"  # Archivo activo

DIAS_VENTANA = 4  # hoy + 3 anteriores

TIMEOUT = 30

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
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        data = {"chat_id": chat_id, "text": msg}
        r = requests.post(url, data=data, timeout=20)
        return r.status_code == 200 and r.json().get("ok", False)
    except Exception as e:
        print(f"Error Telegram: {e}")
        return False


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
# UTILIDADES
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
# GUARDAR (append al archivo activo)
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
# ROTACIÓN INTELIGENTE
# ============================================================

def rotar_archivo_activo(csv_path, tipo):
    if not csv_path.exists():
        return

    print(f"  🔄 Rotando {csv_path.name}...")

    try:
        df = pd.read_csv(csv_path, low_memory=False)
    except Exception as e:
        print(f"  ⚠️ Error leyendo {csv_path.name}: {e}")
        return

    if len(df) == 0:
        return

    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True, errors="coerce", format="mixed")
    df = df.dropna(subset=["timestamp"])
    df = df.sort_values("timestamp")

    hoy = datetime.now(timezone.utc).date()
    fecha_corte = hoy - timedelta(days=DIAS_VENTANA - 1)

    df_viejos = df[df["timestamp"].dt.date < fecha_corte]
    df_recientes = df[df["timestamp"].dt.date >= fecha_corte]

    if len(df_viejos) > 0:
        for fecha, grupo in df_viejos.groupby(df_viejos["timestamp"].dt.date):
            archivo_diario = DATA_DIR / f"market_history_{tipo}_{fecha.isoformat()}.csv"
            grupo.to_csv(archivo_diario, index=False)
            print(f"  📁 Día {fecha} extraído → {archivo_diario.name} ({len(grupo):,} filas)")

    df_recientes.to_csv(csv_path, index=False)
    print(f"  ✅ {csv_path.name} conserva {len(df_recientes):,} filas "
          f"(desde {df_recientes['timestamp'].min()} hasta {df_recientes['timestamp'].max()})")


# ============================================================
# MAIN
# ============================================================

def main():
    print("\n" + "=" * 100)
    print("🚨 CMC COLLECTOR — RANGO 201-300 (v4: híbrido 4 días)")
    print("=" * 100)

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

    print("\n📦 Rotación de archivos activos...")
    rotar_archivo_activo(CSV_201_300, "201_300")

    print()
    print("=" * 100)
    print("✅ CAPTURA 201-300 FINALIZADA")
    print("=" * 100)
    print(f"Snapshot: {timestamp.isoformat()}")
    print(f"Monedas 201-300 guardadas: {len(records)}")
    print(f"Archivo activo: {CSV_201_300}")


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
