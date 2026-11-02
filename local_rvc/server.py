"""
Autonomous Local RVC Neural Inference Microservice for girlfriend-tamagotchi
Powered by official RVC v2 runtime (Python 3.9 + PyTorch CUDA + fairseq + rmvpe)
Endpoint: http://127.0.0.1:5050/convert
"""

import os
import sys
import io
import time
import logging
import tempfile
import soundfile as sf
import numpy as np

# ── 1. Пути к RVC и окружению ─────────────────────────────────────────────────
RVC_ROOT = os.getenv("RVC_ROOT", r"C:\RVC")
if RVC_ROOT not in sys.path:
    sys.path.insert(0, RVC_ROOT)

os.chdir(RVC_ROOT)

from dotenv import load_dotenv
load_dotenv(os.path.join(RVC_ROOT, ".env"))

# ── 2. Конфигурация логирования ───────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] [LocalRVC] %(message)s"
)
logger = logging.getLogger("LocalRVC")

# ── 3. Загрузка RVC конвейера ─────────────────────────────────────────────────
from configs.config import Config
from infer.modules.vc.modules import VC
from fastapi import FastAPI, UploadFile, File, Form, Request, HTTPException
from fastapi.responses import Response, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

MODEL_NAME = "her_voice_200e_3400s.pth"
INDEX_PATH = os.path.join(RVC_ROOT, "logs", "her_voice.index")

logger.info(f"Инициализация RVC конфигурации (RVC_ROOT: {RVC_ROOT})...")
config = Config()
vc = VC(config)

logger.info(f"Загрузка обученных весов RVC: {MODEL_NAME}...")
vc.get_vc(MODEL_NAME)
logger.info(f"[OK] Модель {MODEL_NAME} успешно загружена на {config.device}! (SR: {vc.tgt_sr} Гц, Версия: {vc.version})")

if os.path.exists(INDEX_PATH):
    logger.info(f"[OK] Найден FAISS индекс тембра: {INDEX_PATH} ({os.path.getsize(INDEX_PATH)} байт)")
else:
    logger.warning(f"[WARN] FAISS индекс не найден по пути: {INDEX_PATH}")

# ── 4. FastAPI приложение ─────────────────────────────────────────────────────
app = FastAPI(title="Local RVC Neural Voice Server", version="3.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
@app.get("/health")
async def health():
    return {
        "status": "online",
        "service": "Local RVC Neural Voice Server",
        "device": str(config.device),
        "cuda_available": config.device != "cpu",
        "model_loaded": vc.net_g is not None,
        "model_name": MODEL_NAME,
        "index_exists": os.path.exists(INDEX_PATH),
        "target_sr": vc.tgt_sr
    }

@app.post("/convert")
async def convert_endpoint(
    request: Request,
    audio: UploadFile = File(None),
    f0_up_key: float = Form(12.0),
    pitch: float = Form(None),
    index_rate: float = Form(0.45),
    protect: float = Form(0.5),
    filter_radius: int = Form(5),
    rms_mix_rate: float = Form(0.0),
    f0_method: str = Form("rmvpe")
):
    t0 = time.time()
    audio_bytes = None
    if audio is not None:
        audio_bytes = await audio.read()
    else:
        audio_bytes = await request.body()

    if not audio_bytes or len(audio_bytes) < 100:
        raise HTTPException(status_code=400, detail="Empty or invalid audio data")

    effective_pitch = int(pitch if pitch is not None else f0_up_key)

    # Нормализация входного аудио (пик не выше -1.0 dB = 0.89125) для исключения клиппинга и артефактов
    try:
        in_buf = io.BytesIO(audio_bytes)
        audio_data, in_sr = sf.read(in_buf, dtype="float32")
        if audio_data.ndim > 1:
            audio_data = np.mean(audio_data, axis=1) # Mono
        max_val = float(np.max(np.abs(audio_data)))
        target_peak = 10.0 ** (-1.0 / 20.0) # ~0.89125 (-1.0 dB)
        if max_val > 1e-4:
            audio_data = audio_data * (target_peak / max_val)
        
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp_in:
            sf.write(tmp_in, audio_data, in_sr, format="WAV", subtype="PCM_16")
            tmp_in_path = tmp_in.name
    except Exception as norm_err:
        logger.warning(f"Audio read/normalization fallback: {norm_err}")
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp_in:
            tmp_in.write(audio_bytes)
            tmp_in_path = tmp_in.name

    logger.info(
        f"🎤 [INCOMING RVC] Получено аудио {len(audio_bytes)} байт (нормализовано к -1.0 dB) | "
        f"pitch: +{effective_pitch} | f0_method: {f0_method} | index_rate: {index_rate} | "
        f"filter_radius: {filter_radius} | protect: {protect} | rms_mix: {rms_mix_rate}"
    )

    try:
        # Честный нейросетевой инференс через родной конвейер RVC
        info, (tgt_sr, audio_opt) = vc.vc_single(
            sid=0,
            input_audio_path=tmp_in_path,
            f0_up_key=effective_pitch,
            f0_file=None,
            f0_method=f0_method,
            file_index=INDEX_PATH if os.path.exists(INDEX_PATH) else "",
            file_index2="",
            index_rate=float(index_rate),
            filter_radius=int(filter_radius),
            resample_sr=0,
            rms_mix_rate=float(rms_mix_rate),
            protect=float(protect)
        )

        elapsed = time.time() - t0
        logger.info(f"✨ [RVC INFER COMPLETE] Время инференса: {elapsed:.2f}с | {info.replace(chr(10), ' ')}")

        # Запись сгенерированных отсчетов в WAV поток
        out_buf = io.BytesIO()
        sf.write(out_buf, audio_opt, tgt_sr, format="WAV", subtype="PCM_16")
        wav_bytes = out_buf.getvalue()

        logger.info(f"📤 [RESPONSE] Отправлено клиенту {len(wav_bytes)} байт WAV ({tgt_sr} Гц).")
        return Response(content=wav_bytes, media_type="audio/wav")

    except Exception as e:
        logger.error(f"❌ [RVC ERROR] Ошибка инференса: {e}", exc_info=True)
        return JSONResponse(status_code=500, content={"error": str(e), "status": "error"})
    finally:
        if os.path.exists(tmp_in_path):
            try:
                os.remove(tmp_in_path)
            except Exception:
                pass

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=5050, log_level="info")
