# /// script
# requires-python = ">=3.11"
# dependencies = ["httpx", "nvidia-riva-client", "piper-tts", "yt-dlp", "numpy"]
# ///
"""Buida la cua del traductor de vídeos (taula `fcbillar.video_traduccio`).

Per a cada petició pendent:

1. baixa l'àudio amb yt-dlp i el passa a 16 kHz mono;
2. el talla pels silencis en trossos de com a molt TROS_MAX segons;
3. transcriu cada tros amb el Whisper large-v3 de NVIDIA. Aquest servei no torna
   el temps de cada paraula, i per això es talla abans: el tros ja porta el temps;
4. tradueix els trossos al català amb el Llama de NVIDIA, tots d'una tirada per
   no perdre el context;
5. en fa la veu en off amb Piper (NVIDIA no té veu catalana) i la col·loca al seu
   temps, accelerant-la si no hi cap;
6. penja l'mp3 al release `traduccions` del repositori i deixa la fila 'fet'.

El vídeo no es guarda: la PWA reprodueix l'original silenciat amb la pista a sobre.

Entorn: NEON_DATA_API_URL, NEON_SERVICE_ROLE_TOKEN, NVIDIA_API_KEY, GH_TOKEN.
Executa: `uv run scripts/traductor/tradueix.py [--max 3] [--sense-pujar]`.
"""

from __future__ import annotations

import argparse
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import wave
from pathlib import Path

import httpx
import numpy as np

REPO = "AG-Engineering-Services/FCBillar"
RELEASE = "traduccions"
WHISPER_FUNCTION_ID = "b702f636-f60c-4a3d-a6f4-f3568c13bd7d"  # openai/whisper-large-v3
# El catàleg de NVIDIA canvia sense avisar: el llama-3.3-70b que feien servir els
# scripts de sistemes torna 410 des del setembre de 2026, i la meitat dels models
# que llista /v1/models responen 404. Aquests dos s'han provat amb coreà el
# 24/09/2026: Nemotron respon en segons; GLM tradueix una mica millor però triga
# prop d'un minut, i només entra si el primer falla.
LLMS = [
    os.environ.get("NVIDIA_MODEL", "nvidia/nemotron-3-super-120b-a12b"),
    "z-ai/glm-5.3-flash",
]
VEU = "ca_ES-upc_ona-medium"
VEU_URL = f"https://huggingface.co/rhasspy/piper-voices/resolve/main/ca/ca_ES/upc_ona/medium/{VEU}"

DURADA_MAX = 20 * 60  # s; més llarg no, que una execució d'Actions no s'hi eternitzi
TROS_MAX = 12.0  # s; trossos curts = doblatge més ben sincronitzat
TROS_MIN = 2.0
ACCELERACIO_MAX = 1.6  # més ràpid ja no s'entén
MAX_INTENTS = 3

IDIOMES = {"ko": "coreà", "vi": "vietnamita", "tr": "turc"}

# Whisper, quan només sent música, s'inventa les frases de tancament dels vídeos
# del seu entrenament. Amb el primer vídeo de prova (37 s de música, cap veu) va
# «sentir» dues vegades 감사합니다 («gràcies»). Un fragment que és NOMÉS això és soroll.
AL_LUCINACIONS = {
    "감사합니다",
    "시청해주셔서감사합니다",
    "구독과좋아요부탁드립니다",
    "cảmơncácbạnđãtheodõi",
    "hẹngặplạicácbạn",
    "izlediğiniziçinteşekkürler",
    "teşekkürler",
}

# El mateix vocabulari que fan servir els scripts de sistemes (explora.mjs).
SISTEMA_TRADUCCIO = """Tradueixes al CATALÀ els subtítols d'un vídeo de billar a tres bandes, en {idioma}.
Rebràs un JSON {{"1": "...", "2": "...", ...}} amb els fragments en ordre. Retorna NOMÉS un JSON amb
les MATEIXES claus i la traducció de cada fragment. Regles:
- Fidel i complet: no resumeixis ni ajuntis fragments; cada clau, la seva traducció.
- Català parlat i natural, frases curtes: servirà per a una veu en off que ha de cabre en el temps.
- Terminologia: quantitat de bola (mai "gruix"), efecte, tac, banda, bola 1/2/3, rombe, carambola,
  tacada, retrocés, massé.
- Si un fragment és soroll o no té sentit, retorna'l buit ("").
- Números i xifres de rombes, tal qual.
Glossari obligatori ({idioma} → català):
{glossari}"""

# Sense glossari, el model tradueix els termes tècnics al peu de la lletra: amb el
# vídeo de prova de 54 s, 두께 va sortir «espessura» i no «quantitat de bola». Els
# termes coreans de famílies de tirades són els de scripts/sistemes/explora.mjs.
GLOSSARIS = {
    "ko": """두께 = quantitat de bola · 당점, 팁 = efecte (punt on toca el tac) · 회전 = efecte
수구 = bola jugadora · 제1적구 = segona bola (la primera que es toca) · 제2적구 = tercera bola
쿠션 = banda · 장쿠션 = banda llarga · 단쿠션 = banda curta · 포인트 = rombe
큐 = tac · 스트로크 = tacada · 밀어치기 = seguir (endavant) · 끌어치기 = retrocés
앞돌리기 = endavant · 뒤돌리기 = endarrere · 옆돌리기 = de costat · 대회전 = gran rotació
비껴치기, 빗겨치기, 얇게 = tocar la bola fina · 더블쿠션 = doble banda · 횡단 = travessa
뱅크샷, 뱅크 = bricol · 무회전 = sense efecte · 시스템 = sistema""",
    "vi": """độ dày = quantitat de bola · điểm đánh, phê, xoáy = efecte · bi cái = bola jugadora
bi mục tiêu = bola objectiu · băng = banda · băng dài = banda llarga · băng ngắn = banda curta
điểm, kim cương = rombe · cơ = tac · 3 băng = tres bandes · đánh nảy băng trước = bricol""",
    "tr": """kalınlık = quantitat de bola · falso = efecte · ıstaka = tac · bant = banda
uzun bant = banda llarga · kısa bant = banda curta · elmas = rombe · üç bant = tres bandes
vuruş = tacada · sistem = sistema · önden bant = bricol""",  # noqa: RUF001 (lletres turques)
}


# --- Neon Data API ----------------------------------------------------------


class Cua:
    def __init__(self) -> None:
        base = os.environ["NEON_DATA_API_URL"].rstrip("/")
        if not base.endswith("/rest/v1"):
            base += "/rest/v1"
        self.http = httpx.Client(
            base_url=base,
            timeout=30,
            headers={
                "Authorization": f"Bearer {os.environ['NEON_SERVICE_ROLE_TOKEN']}",
                "Accept-Profile": "fcbillar",
                "Content-Profile": "fcbillar",
                "Content-Type": "application/json",
                "Prefer": "return=representation",
            },
        )

    def reprèn_encallades(self) -> None:
        """Una execució que mor a mitges deixa la fila 'processant' per sempre."""
        fa_dues_hores = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - 7200))
        self.http.patch(
            "/video_traduccio",
            params={"estat": "eq.processant", "processat": f"lt.{fa_dues_hores}"},
            json={"estat": "pendent"},
        ).raise_for_status()

    def agafa(self, excepte: set[int] | None = None) -> dict | None:
        """La pendent més antiga. `excepte` són les que aquesta execució ja ha
        provat: una que falla torna a 'pendent' per a la propera execució, i sense
        això la tornaria a agafar al moment (el primer tret a Actions va provar el
        mateix vídeo tres vegades seguides i el va deixar 'error' en un minut)."""
        params = {"estat": "eq.pendent", "order": "creat.asc", "limit": "1"}
        if excepte:
            params["id"] = f"not.in.({','.join(map(str, excepte))})"
        r = self.http.get("/video_traduccio", params=params)
        r.raise_for_status()
        if not r.json():
            return None
        fila = r.json()[0]
        # Només ens la quedem si encara és pendent: dues execucions no la fan alhora.
        r = self.http.patch(
            "/video_traduccio",
            params={"id": f"eq.{fila['id']}", "estat": "eq.pendent"},
            json={
                "estat": "processant",
                "intents": fila["intents"] + 1,
                "processat": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            },
        )
        r.raise_for_status()
        return r.json()[0] if r.json() else None

    def desa(self, id_: int, **camps) -> None:
        camps["processat"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        self.http.patch(
            "/video_traduccio", params={"id": f"eq.{id_}"}, json=camps
        ).raise_for_status()


# --- àudio ------------------------------------------------------------------


def ffmpeg(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["ffmpeg", "-hide_banner", "-nostdin", "-y", *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=True,
    )


class BaixadaError(Exception):
    """yt-dlp no ha pogut baixar el vídeo: privat, amb login o IP bloquejada."""


def yt_dlp(*args: str) -> str:
    # A les IP de GitHub Actions YouTube hi respon «Sign in to confirm you're not a
    # bot». Provat el 24/09/2026: directe 0/2, amb PO tokens (bgutil) 0/2, sortint
    # per Cloudflare WARP 2/2. El workflow aixeca WARP en mode proxy i el passa
    # aquí; només hi va yt-dlp, NVIDIA i Neon surten directes.
    proxy = ["--proxy", os.environ["YTDLP_PROXY"]] if os.environ.get("YTDLP_PROXY") else []
    r = subprocess.run(
        [sys.executable, "-m", "yt_dlp", "--no-playlist", *proxy, *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if r.returncode:
        detall = (r.stderr.strip().splitlines() or ["?"])[-1]
        raise BaixadaError(f"No s'ha pogut baixar el vídeo: {detall[:300]}")
    return r.stdout


def metadades(url: str) -> dict:
    return json.loads(yt_dlp("-J", url))


def baixa_audio(url: str, dir_: Path) -> Path:
    yt_dlp("-q", "-f", "bestaudio/best", "-o", str(dir_ / "original.%(ext)s"), url)
    original = next(dir_.glob("original.*"))
    wav = dir_ / "audio16k.wav"
    ffmpeg("-i", str(original), "-ac", "1", "-ar", "16000", str(wav))
    return wav


def silencis(wav: Path) -> list[tuple[float, float]]:
    r = ffmpeg("-i", str(wav), "-af", "silencedetect=noise=-35dB:d=0.3", "-f", "null", "-")
    inicis = [float(x) for x in re.findall(r"silence_start: ([\d.]+)", r.stderr)]
    finals = [float(x) for x in re.findall(r"silence_end: ([\d.]+)", r.stderr)]
    # Un silenci que arriba fins al final no té silence_end: el tros ja acaba allà.
    return list(zip(inicis, finals, strict=False))


def trossos(durada: float, sil: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """Talla pel mig dels silencis, tan llarg com es pugui fins a TROS_MAX, i
    després arrossega els extrems fins on comença i acaba la veu."""
    mitjos = [(a + b) / 2 for a, b in sil]
    talls: list[tuple[float, float]] = []
    ini = 0.0
    while durada - ini > TROS_MAX:
        candidats = [c for c in mitjos if ini + TROS_MIN <= c <= ini + TROS_MAX]
        fi = candidats[-1] if candidats else ini + TROS_MAX
        talls.append((ini, fi))
        ini = fi
    talls.append((ini, durada))

    def retalla(t0: float, t1: float) -> tuple[float, float]:
        for a, b in sil:
            if a <= t0 < b:
                t0 = min(b, t1)
            if a < t1 <= b:
                t1 = max(a, t0)
        return t0, t1

    return [r for r in (retalla(a, b) for a, b in talls) if r[1] - r[0] >= 0.4]


def tros_wav(wav: Path, t0: float, t1: float) -> bytes:
    r = subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-nostdin",
            "-v",
            "error",
            "-ss",
            f"{t0:.3f}",
            "-to",
            f"{t1:.3f}",
            "-i",
            str(wav),
            "-ac",
            "1",
            "-ar",
            "16000",
            "-f",
            "wav",
            "-",
        ],
        capture_output=True,
        check=True,
    )
    return r.stdout


# --- NVIDIA -----------------------------------------------------------------


def amb_reintents(f, intents: int = 5):
    for i in range(intents):
        try:
            return f()
        except Exception:
            if i == intents - 1:
                raise
            time.sleep(4 * (i + 1))  # el pla gratuït limita les peticions per minut


class Whisper:
    def __init__(self) -> None:
        import riva.client

        auth = riva.client.Auth(
            uri="grpc.nvcf.nvidia.com:443",
            use_ssl=True,
            metadata_args=[
                ["function-id", WHISPER_FUNCTION_ID],
                ["authorization", f"Bearer {os.environ['NVIDIA_API_KEY']}"],
            ],
        )
        self.riva = riva.client
        self.asr = riva.client.ASRService(auth)

    def transcriu(self, audio: bytes, idioma: str) -> str:
        cfg = self.riva.RecognitionConfig(
            language_code=idioma, max_alternatives=1, enable_automatic_punctuation=True
        )
        r = amb_reintents(lambda: self.asr.offline_recognize(audio, cfg))
        return " ".join(
            res.alternatives[0].transcript.strip() for res in r.results if res.alternatives
        ).strip()


def es_soroll(text: str) -> bool:
    """Al·lucinacions de Whisper: una frase de tancament sola, o una paraula en
    bucle (el mateix vídeo de prova va donar 이십 trenta-dues vegades seguides)."""
    net = re.sub(r"[\s.,!?…·\-]", "", text).lower()
    if net in AL_LUCINACIONS:
        return True
    paraules = text.split()
    return len(paraules) >= 4 and max(map(paraules.count, paraules)) / len(paraules) > 0.5


def llm(sistema: str, usuari: str) -> str:
    for model in LLMS[:-1]:
        try:
            return _llm(model, sistema, usuari)
        except Exception as e:
            print(f"  {model} ha fallat ({e}); provo el següent")
    return _llm(LLMS[-1], sistema, usuari)


def _llm(model: str, sistema: str, usuari: str) -> str:
    def crida() -> str:
        r = httpx.post(
            "https://integrate.api.nvidia.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {os.environ['NVIDIA_API_KEY']}"},
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": sistema},
                    {"role": "user", "content": usuari},
                ],
                "temperature": 0.2,
                "max_tokens": 4000,
            },
            timeout=180,
        )
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]

    return amb_reintents(crida, intents=3)


def tradueix(textos: list[str], idioma: str) -> list[str]:
    sistema = SISTEMA_TRADUCCIO.format(idioma=IDIOMES[idioma], glossari=GLOSSARIS[idioma])
    sortida = [""] * len(textos)
    lot = 25
    for ini in range(0, len(textos), lot):
        entrada = {str(i + 1): t for i, t in enumerate(textos[ini : ini + lot]) if t}
        if not entrada:
            continue
        resposta = llm(sistema, json.dumps(entrada, ensure_ascii=False))
        m = re.search(r"\{.*\}", resposta, re.S)
        traduit = json.loads(m.group(0)) if m else {}
        for clau in entrada:
            valor = traduit.get(clau)
            if not isinstance(valor, str):
                # El model s'ha saltat el fragment: el demanem sol.
                valor = llm(sistema, json.dumps({"1": entrada[clau]}, ensure_ascii=False))
                m = re.search(r"\{.*\}", valor, re.S)
                valor = json.loads(m.group(0)).get("1", "") if m else ""
            sortida[ini + int(clau) - 1] = valor.strip()
    return sortida


# --- veu en off ---------------------------------------------------------------


class Veu:
    def __init__(self, dir_models: Path) -> None:
        from piper import PiperVoice, SynthesisConfig

        dir_models.mkdir(parents=True, exist_ok=True)
        for ext in (".onnx", ".onnx.json"):
            desti = dir_models / f"{VEU}{ext}"
            if not desti.exists():
                with httpx.stream("GET", VEU_URL + ext, follow_redirects=True, timeout=120) as r:
                    r.raise_for_status()
                    with open(desti, "wb") as f:
                        for bloc in r.iter_bytes():
                            f.write(bloc)
        self.veu = PiperVoice.load(str(dir_models / f"{VEU}.onnx"))
        self.config = SynthesisConfig
        self.sr = self.veu.config.sample_rate

    def diu(self, text: str, velocitat: float = 1.0) -> np.ndarray:
        buf = io.BytesIO()
        with wave.open(buf, "wb") as w:
            self.veu.synthesize_wav(text, w, syn_config=self.config(length_scale=1 / velocitat))
        buf.seek(0)
        with wave.open(buf, "rb") as w:
            return np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)


def doblatge(veu: Veu, segments: list[dict], durada: float, desti: Path) -> None:
    """Col·loca cada frase al seu temps. Si no hi cap fins que comença la següent,
    l'accelera (fins a ACCELERACIO_MAX); si tot i així no hi cap, la següent
    s'espera: millor un petit desfasament que dues veus trepitjant-se."""
    sr = veu.sr
    pista = np.zeros(int((durada + 30) * sr), dtype=np.int32)
    cursor = 0.0
    for i, s in enumerate(segments):
        if not s["ca"]:
            continue
        seguent = next((x["t0"] for x in segments[i + 1 :] if x["ca"]), durada)
        inici = max(s["t0"], cursor)
        espai = max(seguent - inici, 0.5)
        audio = veu.diu(s["ca"])
        if len(audio) / sr > espai:
            audio = veu.diu(s["ca"], min(len(audio) / sr / espai, ACCELERACIO_MAX))
        a = int(inici * sr)
        pista[a : a + len(audio)] += audio
        cursor = inici + len(audio) / sr + 0.1
    fi = int(max(cursor, durada) * sr)
    pista = np.clip(pista[:fi], -32768, 32767).astype(np.int16)
    wav = desti.with_suffix(".wav")
    with wave.open(str(wav), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(pista.tobytes())
    ffmpeg("-i", str(wav), "-ac", "1", "-codec:a", "libmp3lame", "-b:a", "64k", str(desti))


# --- una petició ----------------------------------------------------------------


def processa(fila: dict, whisper: Whisper, veu: Veu, pujar: bool) -> dict:
    with tempfile.TemporaryDirectory() as tmp:
        dir_ = Path(tmp)
        meta = metadades(fila["url"])
        durada = float(meta.get("duration") or 0)
        if durada > DURADA_MAX:
            raise ValueError(
                f"El vídeo dura {durada / 60:.0f} min; el màxim són {DURADA_MAX // 60}."
            )
        wav = baixa_audio(fila["url"], dir_)
        if not durada:
            with wave.open(str(wav)) as w:
                durada = w.getnframes() / w.getframerate()

        segments = []
        for t0, t1 in trossos(durada, silencis(wav)):
            text = whisper.transcriu(tros_wav(wav, t0, t1), fila["idioma"])
            if text and not es_soroll(text):
                segments.append({"t0": round(t0, 2), "t1": round(t1, 2), "orig": text})
        if not segments:
            raise ValueError("No s'hi ha entès cap veu.")
        for s, ca in zip(
            segments, tradueix([s["orig"] for s in segments], fila["idioma"]), strict=True
        ):
            s["ca"] = ca

        nom = f"{fila['plataforma']}-{re.sub(r'[^A-Za-z0-9_-]', '_', fila['video_id'])}.mp3"
        mp3 = dir_ / nom
        doblatge(veu, segments, durada, mp3)
        audio_url = None
        if pujar:
            subprocess.run(
                ["gh", "release", "upload", RELEASE, str(mp3), "--clobber", "-R", REPO], check=True
            )
            audio_url = f"https://github.com/{REPO}/releases/download/{RELEASE}/{nom}"
        else:
            desat = Path("traduccions") / nom
            desat.parent.mkdir(exist_ok=True)
            desat.write_bytes(mp3.read_bytes())
            print(f"  àudio a {desat}")

        return {
            "estat": "fet",
            "titol": meta.get("title"),
            "canal": meta.get("channel") or meta.get("uploader"),
            "durada": durada,
            "segments": segments,
            "audio_url": audio_url,
            "missatge": None,
        }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--max", type=int, default=3, help="vídeos com a molt per execució")
    ap.add_argument(
        "--sense-pujar", action="store_true", help="deixa l'mp3 a ./traduccions i no el puja"
    )
    args = ap.parse_args()

    cua = Cua()
    cua.reprèn_encallades()
    fila = cua.agafa()
    if not fila:
        print("Cua buida.")
        return
    whisper = Whisper()
    veu = Veu(Path(os.environ.get("PIPER_MODELS", Path.home() / ".cache" / "piper")))
    provades: set[int] = set()
    while fila:
        provades.add(fila["id"])
        print(f"#{fila['id']} {fila['plataforma']} {fila['video_id']} ({fila['idioma']})")
        try:
            camps = processa(fila, whisper, veu, pujar=not args.sense_pujar)
            cua.desa(fila["id"], **camps)
            print(f"  fet: {len(camps['segments'])} fragments")
        except Exception as e:  # l'error va a la fila, que és on el veu l'usuari
            missatge = str(e)[:500] or type(e).__name__
            definitiu = isinstance(e, ValueError) or fila["intents"] >= MAX_INTENTS
            cua.desa(fila["id"], estat="error" if definitiu else "pendent", missatge=missatge)
            print(f"  error: {missatge}")
        fila = cua.agafa(provades) if len(provades) < args.max else None


if __name__ == "__main__":
    main()
