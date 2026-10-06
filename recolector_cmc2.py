#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
CMC COLLECTOR 2 — RANGO 201-300

Objetivo:
    Construir un histórico del rango 201-300 de CoinMarketCap
    para estudiar:

    - monedas que empiezan a subir antes del pump
    - acumulación
    - expansión de volumen
    - compresión
    - mejora de ranking
    - fuerza relativa
    - rotación de capital
    - monedas 201-300 que empiezan a entrar hacia Top 200
    - posibles patrones previos a grandes movimientos

IMPORTANTE:
    Se consulta el TOP 300 completo para calcular correctamente
    los rankings y métricas relativas.

    SOLAMENTE se guardan las monedas 201-300.

Uso:

    python recolector_cmc2.py

Requiere:

    pip install requests

Variables:

    CMC_API_KEY
    TELEGRAM_BOT_TOKEN   (opcional)
    TELEGRAM_CHAT_ID     (opcional)
"""

import csv
import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

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

# ESTE RECOLECTOR GUARDA SOLAMENTE 201-300
CSV_201_300 = DATA_DIR / "market_history_201_300.csv"

ROTATION_FILE = DATA_DIR / "last_rotation.txt"
ARCHIVE_DIR = DATA_DIR / "archives"

DIAS_ROTACION = 5

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
        url = f"https://api.telegram.org/bot{token}/sendMessage"

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
            f"próxima rotación en {DIAS_ROTACION} días"
        )

        return True

    return False


def toca_rotar():

    ultima = leer_ultima_rotacion()

    if ultima is None:
        return False

    ahora = datetime.now(timezone.utc)

    if ultima.tzinfo is None:
        ultima = ultima.replace(
            tzinfo=timezone.utc
        )

    return (
        ahora - ultima
    ) >= timedelta(days=DIAS_ROTACION)


def rotar_csv():

    if not CSV_201_300.exists():

        print(
            "No hay CSV 201-300 para rotar."
        )

        return None

    ARCHIVE_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    ahora = datetime.now(timezone.utc)

    sufijo = ahora.strftime(
        "%Y%m%d_%H%M"
    )

    destino = (
        ARCHIVE_DIR
        / f"201_300_{sufijo}.csv"
    )

    CSV_201_300.rename(destino)

    tamaño = (
        destino.stat().st_size
        / (1024 * 1024)
    )

    info = {
        "fecha": ahora,
        "archivos": [
            {
                "nombre": destino.name,
                "tipo": "201_300",
                "tamaño_mb": tamaño,
            }
        ],
        "tamaño_total_mb": tamaño,
    }

    print(
        f"Rotado 201-300: "
        f"{destino.name} "
        f"({tamaño:.2f} MB)"
    )

    guardar_ultima_rotacion(ahora)

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
# COLUMNAS
# ============================================================

CSV_COLUMNS = [

    # Identificación
    "snapshot_id",
    "timestamp",

    "cmc_id",
    "name",
    "symbol",
    "slug",

    # Ranking
    "cmc_rank",
    "segment",

    # Precio
    "price",

    # Momentum
    "percent_change_1h",
    "percent_change_24h",
    "percent_change_7d",
    "percent_change_30d",
    "percent_change_60d",
    "percent_change_90d",

    # Volumen
    "volume_24h",
    "volume_change_24h",

    # Market cap
    "market_cap",
    "market_cap_dominance",

    # Métricas derivadas
    "volume_marketcap_ratio",
    "marketcap_volume_ratio",

    # Flags
    "is_top100",
    "is_top200",
    "is_top300",

    # Rankings del snapshot
    "rank_gainer_300",
    "rank_loser_300",
    "rank_volume_300",

    # Ranking por segmento
    "rank_gainer_segment",
    "rank_volume_segment",

]


# ============================================================
# UTILIDADES
# ============================================================

def get_api_key():

    api_key = os.getenv(
        "CMC_API_KEY"
    )

    if not api_key:

        print(
            "ERROR: No existe "
            "CMC_API_KEY."
        )

        sys.exit(1)

    return api_key


def safe_float(value):

    if value is None:
        return None

    try:
        return float(value)

    except (
        TypeError,
        ValueError
    ):
        return None


def create_snapshot_id(timestamp):

    return timestamp.strftime(
        "%Y%m%d_%H%M%S"
    )


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

    print(
        f"Consultando CoinMarketCap "
        f"(TOP {TOP_N})..."
    )

    r = requests.get(
        CMC_API_URL,
        headers=headers,
        params=params,
        timeout=TIMEOUT,
    )

    print(
        f"HTTP: {r.status_code}"
    )

    if r.status_code != 200:

        print(r.text)

        r.raise_for_status()

    payload = r.json()

    status = payload.get(
        "status",
        {}
    )

    if status.get(
        "error_code",
        0
    ) != 0:

        print(
            "ERROR CMC:",
            status
        )

        sys.exit(1)

    data = payload.get(
        "data",
        []
    )

    if not data:

        print(
            "ERROR: CMC no devolvió "
            "monedas."
        )

        sys.exit(1)

    print(
        f"Monedas recibidas: "
        f"{len(data)}"
    )

    print(
        f"Credits utilizados: "
        f"{status.get('credit_count')}"
    )

    return data


# ============================================================
# RANKINGS
# ============================================================

def calculate_rankings(coins):

    def change_24h(c):

        q = c.get(
            "quote",
            {}
        ).get(
            "USD",
            {}
        )

        return safe_float(
            q.get(
                "percent_change_24h"
            )
        )

    def volume(c):

        q = c.get(
            "quote",
            {}
        ).get(
            "USD",
            {}
        )

        return safe_float(
            q.get(
                "volume_24h"
            )
        )

    losers = sorted(
        coins,
        key=lambda c: (
            change_24h(c)
            if change_24h(c) is not None
            else float("inf")
        )
    )

    gainers = sorted(
        coins,
        key=lambda c: (
            change_24h(c)
            if change_24h(c) is not None
            else float("-inf")
        ),
        reverse=True,
    )

    volumes = sorted(
        coins,
        key=lambda c: (
            volume(c)
            if volume(c) is not None
            else float("-inf")
        ),
        reverse=True,
    )

    return (

        {
            c["id"]: p
            for p, c
            in enumerate(
                losers,
                start=1
            )
        },

        {
            c["id"]: p
            for p, c
            in enumerate(
                gainers,
                start=1
            )
        },

        {
            c["id"]: p
            for p, c
            in enumerate(
                volumes,
                start=1
            )
        },

    )


def calculate_segment_rankings(coins):

    resultado = {}

    segmentos = {
        "top100": [],
        "101_200": [],
        "201_300": [],
    }

    for coin in coins:

        rank = (
            coin.get("cmc_rank")
            or 99999
        )

        seg = segmento(rank)

        if seg in segmentos:

            segmentos[seg].append(
                coin
            )

    for seg, lista in segmentos.items():

        if not lista:
            continue

        def ch(c):

            return safe_float(
                c.get(
                    "quote",
                    {}
                ).get(
                    "USD",
                    {}
                ).get(
                    "percent_change_24h"
                )
            )

        def vol(c):

            return safe_float(
                c.get(
                    "quote",
                    {}
                ).get(
                    "USD",
                    {}
                ).get(
                    "volume_24h"
                )
            )

        gainers = sorted(
            lista,
            key=lambda c:
                ch(c)
                if ch(c) is not None
                else float("-inf"),
            reverse=True,
        )

        volumes = sorted(
            lista,
            key=lambda c:
                vol(c)
                if vol(c) is not None
                else float("-inf"),
            reverse=True,
        )

        resultado[seg] = {

            "gainer": {
                c["id"]: p
                for p, c
                in enumerate(
                    gainers,
                    start=1
                )
            },

            "volume": {
                c["id"]: p
                for p, c
                in enumerate(
                    volumes,
                    start=1
                )
            },

        }

    return resultado


# ============================================================
# CONSTRUIR REGISTROS
# ============================================================

def build_records(
    coins,
    timestamp,
):

    snapshot_id = (
        create_snapshot_id(
            timestamp
        )
    )

    (
        loser_rank,
        gainer_rank,
        volume_rank,
    ) = calculate_rankings(
        coins
    )

    segment_rankings = (
        calculate_segment_rankings(
            coins
        )
    )

    records = []

    for coin in coins:

        q = coin.get(
            "quote",
            {}
        ).get(
            "USD",
            {}
        )

        rank = (
            coin.get("cmc_rank")
            or 99999
        )

        seg = segmento(rank)

        # ====================================================
        # SOLAMENTE 201-300
        # ====================================================

        if seg != "201_300":
            continue

        price = safe_float(
            q.get("price")
        )

        volume_24h = safe_float(
            q.get("volume_24h")
        )

        market_cap = safe_float(
            q.get("market_cap")
        )

        # ====================================================
        # VOLUMEN / MARKET CAP
        # ====================================================

        if (
            volume_24h is not None
            and market_cap is not None
            and market_cap > 0
        ):

            volume_marketcap_ratio = (
                volume_24h
                / market_cap
                * 100
            )

            marketcap_volume_ratio = (
                market_cap
                / volume_24h
                if volume_24h > 0
                else None
            )

        else:

            volume_marketcap_ratio = None
            marketcap_volume_ratio = None

        seg_gainer = None
        seg_volume = None

        if seg in segment_rankings:

            seg_gainer = (
                segment_rankings[seg]
                ["gainer"]
                .get(coin.get("id"))
            )

            seg_volume = (
                segment_rankings[seg]
                ["volume"]
                .get(coin.get("id"))
            )

        records.append({

            "snapshot_id":
                snapshot_id,

            "timestamp":
                timestamp.isoformat(),

            "cmc_id":
                coin.get("id"),

            "name":
                coin.get("name"),

            "symbol":
                coin.get("symbol"),

            "slug":
                coin.get("slug"),

            "cmc_rank":
                rank,

            "segment":
                seg,

            "price":
                price,

            "percent_change_1h":
                safe_float(
                    q.get(
                        "percent_change_1h"
                    )
                ),

            "percent_change_24h":
                safe_float(
                    q.get(
                        "percent_change_24h"
                    )
                ),

            "percent_change_7d":
                safe_float(
                    q.get(
                        "percent_change_7d"
                    )
                ),

            "percent_change_30d":
                safe_float(
                    q.get(
                        "percent_change_30d"
                    )
                ),

            "percent_change_60d":
                safe_float(
                    q.get(
                        "percent_change_60d"
                    )
                ),

            "percent_change_90d":
                safe_float(
                    q.get(
                        "percent_change_90d"
                    )
                ),

            "volume_24h":
                volume_24h,

            "volume_change_24h":
                safe_float(
                    q.get(
                        "volume_change_24h"
                    )
                ),

            "market_cap":
                market_cap,

            "market_cap_dominance":
                safe_float(
                    q.get(
                        "market_cap_dominance"
                    )
                ),

            "volume_marketcap_ratio":
                volume_marketcap_ratio,

            "marketcap_volume_ratio":
                marketcap_volume_ratio,

            "is_top100":
                0,

            "is_top200":
                0,

            "is_top300":
                1,

            "rank_gainer_300":
                gainer_rank.get(
                    coin.get("id")
                ),

            "rank_loser_300":
                loser_rank.get(
                    coin.get("id")
                ),

            "rank_volume_300":
                volume_rank.get(
                    coin.get("id")
                ),

            "rank_gainer_segment":
                seg_gainer,

            "rank_volume_segment":
                seg_volume,

        })

    return records


# ============================================================
# GUARDADO
# ============================================================

def save_records(
    records,
    archivo
):

    DATA_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    file_exists = archivo.exists()

    with archivo.open(
        "a",
        newline="",
        encoding="utf-8"
    ) as f:

        writer = csv.DictWriter(
            f,
            fieldnames=CSV_COLUMNS
        )

        if not file_exists:
            writer.writeheader()

        writer.writerows(
            records
        )

    print(
        f"Guardado: "
        f"{len(records)} registros "
        f"→ {archivo.name}"
    )


# ============================================================
# MAIN
# ============================================================

def main():

    print()

    print("=" * 100)

    print(
        "🚨 CMC COLLECTOR — "
        "RANGO 201-300"
    )

    print("=" * 100)

    # --------------------------------------------------------
    # ROTACIÓN
    # --------------------------------------------------------

    inicializar_rotacion()

    if toca_rotar():

        print(
            f"Han pasado "
            f"{DIAS_ROTACION}+ días."
        )

        print(
            "Rotando histórico 201-300..."
        )

        info = rotar_csv()

        if info:
            notificar_rotacion(
                info
            )

    else:

        ultima = (
            leer_ultima_rotacion()
        )

        if ultima:

            ahora = (
                datetime.now(
                    timezone.utc
                )
            )

            if ultima.tzinfo is None:
                ultima = (
                    ultima.replace(
                        tzinfo=timezone.utc
                    )
                )

            dias_transcurridos = (
                ahora - ultima
            ).total_seconds() / 86400

            dias_restantes = max(
                0,
                DIAS_ROTACION
                - dias_transcurridos
            )

            print(
                f"Próxima rotación "
                f"en ~"
                f"{dias_restantes:.1f} días"
            )

    # --------------------------------------------------------
    # API
    # --------------------------------------------------------

    api_key = get_api_key()

    timestamp = (
        datetime.now(
            timezone.utc
        )
    )

    coins = fetch_monedas(
        api_key
    )

    # --------------------------------------------------------
    # CONTAR SEGMENTOS
    # --------------------------------------------------------

    top100 = []
    rango101_200 = []
    rango201_300 = []

    for coin in coins:

        rank = (
            coin.get(
                "cmc_rank"
            )
            or 99999
        )

        if rank <= 100:

            top100.append(
                coin
            )

        elif rank <= 200:

            rango101_200.append(
                coin
            )

        elif rank <= 300:

            rango201_300.append(
                coin
            )

    print()

    print(
        "División TOP 300:"
    )

    print(
        f"  TOP 100:   "
        f"{len(top100)}"
    )

    print(
        f"  101-200:   "
        f"{len(rango101_200)}"
    )

    print(
        f"  201-300:   "
        f"{len(rango201_300)}"
    )

    # --------------------------------------------------------
    # CONSTRUIR REGISTROS
    # --------------------------------------------------------

    records = build_records(
        coins,
        timestamp
    )

    # --------------------------------------------------------
    # GUARDAR SOLAMENTE 201-300
    # --------------------------------------------------------

    save_records(
        records,
        CSV_201_300
    )

    # --------------------------------------------------------
    # RESUMEN
    # --------------------------------------------------------

    print()

    print("=" * 100)

    print(
        "✅ CAPTURA 201-300 FINALIZADA"
    )

    print("=" * 100)

    print(
        f"Snapshot: "
        f"{timestamp.isoformat()}"
    )

    print(
        f"Monedas 201-300 guardadas: "
        f"{len(records)}"
    )

    print(
        f"Archivo:"
    )

    print(
        f"  → {CSV_201_300}"
    )

    print()

    print(
        "🎯 Objetivo del histórico:"
    )

    print(
        "  Detectar monedas que:"
    )

    print(
        "  1. mejoran ranking"
    )

    print(
        "  2. aumentan volumen"
    )

    print(
        "  3. mantienen precio comprimido"
    )

    print(
        "  4. ganan fuerza relativa"
    )

    print(
        "  5. pasan 201-300 → 101-200"
    )

    print(
        "  6. posteriormente entran al Top 100"
    )

    print(
        "  7. finalmente desarrollan el pump"
    )

    print()

    print(
        "💡 IMPORTANTE:"
    )

    print(
        "El recolector NO intenta decidir "
        "qué comprar."
    )

    print(
        "Su trabajo es guardar suficiente "
        "histórico para que el analizador "
        "descubra qué patrones aparecen "
        "ANTES de los pumps."
    )


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":

    try:

        main()

    except Exception as e:

        print()

        print(
            f"❌ ERROR: {e}"
        )

        import traceback

        traceback.print_exc()

        sys.exit(1)
