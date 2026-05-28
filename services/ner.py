# services/ner.py
import os
import logging
from typing import Dict, List, Optional, Tuple
from pathlib import Path
from services.utils import get_env_path
import torch
from contextlib import nullcontext

logger = logging.getLogger(__name__)

try:
    import transformers
except Exception:
    transformers = None
    logger.warning("transformers not installed; NER will be disabled.")

# Basis folder model dari ENV
NER_BASE = get_env_path("NER_MODEL_DIR", "ner_model")

# --- Performance knobs (safe defaults) ---
try:
    torch.backends.cudnn.benchmark = True
except Exception:
    pass
if hasattr(torch, "set_float32_matmul_precision"):
    try:
        torch.set_float32_matmul_precision("high")
    except Exception:
        pass

# Contoh path submodel (sesuaikan dengan loader yang ada)
PATH_BERT_LARGE_CASED   = NER_BASE / "bert_large_cased"
PATH_INDONLU_NER_GRIT   = NER_BASE / "indonlu_ner_grit"
PATH_MALAY_FINETUNED    = NER_BASE / "malay_ner_finetuned_300725_10h50_set01"
PATH_THAI_NNER          = NER_BASE / "thai_nner"

def _iter_token_chunks(text, tokenizer, max_tokens=510, stride=50):
    """
    Potong teks jadi potongan <=510 token (CLS/SEP akan tambah 2 jadi 512).
    stride: overlap antar-chunk biar entitas di boundary tidak hilang.
    """
    toks = tokenizer(
        text,
        add_special_tokens=False,
        return_offsets_mapping=False,
        return_attention_mask=False,
    )
    ids = toks["input_ids"]
    n = len(ids)
    start = 0
    while start < n:
        end = min(start + max_tokens, n)
        chunk_ids = ids[start:end]
        chunk_text = tokenizer.decode(
            chunk_ids, skip_special_tokens=True, clean_up_tokenization_spaces=False
        )
        yield chunk_text
        if end == n:
            break
        start = max(0, end - stride)

_DEVICE_LOGGED = False

def _inference_context():
    if hasattr(torch, "inference_mode"):
        return torch.inference_mode()
    if hasattr(torch, "no_grad"):
        return torch.no_grad()
    return nullcontext()

def _autocast_context(enabled: bool):
    if not enabled:
        return nullcontext()
    if hasattr(torch, "autocast"):
        return torch.autocast(device_type="cuda", dtype=torch.float16)
    return nullcontext()

def _resolve_device() -> tuple[int, bool, int]:
    """
    Resolve device index + fp16 flag + batch size once.
    Returns: (device_idx, fp16_enabled, batch_size)
    """
    use_gpu_env = os.getenv("USE_GPU", "1")
    want_gpu = (use_gpu_env != "0")

    gpu_index_env = os.getenv("GPU_DEVICE_INDEX", "0")
    fp16 = os.getenv("NER_FP16", "0").lower() in ("1", "true", "yes")
    try:
        batch_size = int(os.getenv("NER_BATCH_SIZE", "0") or "0")
    except Exception:
        batch_size = 0

    if want_gpu and torch.cuda.is_available():
        try:
            device_idx = int(gpu_index_env)
        except Exception:
            device_idx = 0
    else:
        device_idx = -1

    global _DEVICE_LOGGED
    if not _DEVICE_LOGGED:
        if device_idx == -1:
            logger.info("NER device resolved: CPU (cuda_available=%s)", torch.cuda.is_available())
        else:
            logger.info("NER device resolved: CUDA:%d (fp16=%s, batch_size=%s)", device_idx, fp16, batch_size)
        _DEVICE_LOGGED = True

    return device_idx, fp16, batch_size

class NerRunner:
    def __init__(self, base_dir: str):
        self.ok = transformers is not None
        self.base_en = os.path.join(base_dir, "bert_large_cased")
        self.cache = {}
        self.device_idx, self.fp16, self.batch_size = _resolve_device()

    def _device_index(self) -> int:
        # -1 = CPU, >=0 = GPU index
        return self.device_idx

    def _pipe(self, model_dir: str):
        if not self.ok or not os.path.isdir(model_dir):
            return None
        if model_dir in self.cache:
            return self.cache[model_dir]
        try:
            # 1) load tokenizer dulu supaya bisa set model_max_length
            tokenizer = transformers.AutoTokenizer.from_pretrained(model_dir, use_fast=True)
            tokenizer.model_max_length = 512 

            device_idx = self._device_index()
            try:
                kwargs = {
                    "aggregation_strategy": "simple",
                    "device": device_idx,
                }
                if device_idx >= 0 and self.fp16:
                    kwargs["torch_dtype"] = torch.float16
                if self.batch_size and self.batch_size > 0:
                    kwargs["batch_size"] = self.batch_size
                pl = transformers.pipeline(
                    "token-classification",
                    model=model_dir,
                    tokenizer=tokenizer,          # <= pass tokenizer yang sudah di-set
                    **kwargs,
                )
            except TypeError:
                pl = transformers.pipeline(
                    "token-classification",
                    model=model_dir,
                    tokenizer=tokenizer,           # <= pass tokenizer yang sudah di-set
                    device=device_idx,
                )

            # (opsional) jaga-jaga
            if hasattr(pl, "tokenizer"):
                pl.tokenizer.model_max_length = 512

            self.cache[model_dir] = pl
            return pl
        except Exception as e:
            logger.exception("Failed to load NER pipeline for %s: %s", model_dir, e)
            return None

    def _label_of(self, ent: Dict) -> str:
        return (ent.get("entity_group") or ent.get("entity") or "ENT").upper().replace(" ", "_")

    def infer_spans_for_model(self, text: str, model_dir: str) -> List[Dict]:
        """Ambil span dari satu model saja (untuk kontrol urutan: EN lalu TENANT)."""
        pl = self._pipe(model_dir)
        if not pl:
            return []
        spans, seen = [], set()
        try:
            device_idx = self._device_index()
            use_amp = device_idx >= 0 and self.fp16
            amp_ctx = _autocast_context(use_amp)
            # ====== GANTI pemanggilan pl(text, truncation=..., max_length=...) ======
            with _inference_context():
                with amp_ctx:
                    for chunk_text in _iter_token_chunks(text, pl.tokenizer, max_tokens=510, stride=50):
                        ents = pl(chunk_text)  # <= TANPA truncation/max_length (kompatibel versi lama)
                        for ent in ents:
                            st, en = int(ent.get("start", -1)), int(ent.get("end", -1))
                            if st < 0 or en <= st:
                                continue
                            label = self._label_of(ent)
                            key = (st, en, label)
                            if key in seen:
                                continue
                            seen.add(key)
                            spans.append({"label": label, "start": st, "end": en})
        except Exception as e:
            logger.exception("NER inference failed for %s: %s", model_dir, e)
        return spans

def mask_by_ner(text: str, spans: List[Dict]) -> Tuple[str, List[Tuple[str, Dict[str, str]]]]:
    """Kembalikan masked_text + list layer (('PER', {token:ori}), ...). Token: [PER_1], dst."""
    if not spans:
        return text, []
    spans = sorted([s for s in spans if s["start"] >= 0 and s["end"] > s["start"]], key=lambda s: s["start"])
    layers_map: Dict[str, Dict[str, str]] = {}
    counters: Dict[str, int] = {}
    parts, cur = [], 0
    for s in spans:
        st, en = s["start"], s["end"]
        if st < cur:
            continue
        lname = f"{s['label']}"
        if lname not in layers_map:
            layers_map[lname], counters[lname] = {}, 1
        token = f"[{lname.upper()}_{counters[lname]}]"
        layers_map[lname][token] = text[st:en]
        counters[lname] += 1
        parts += [text[cur:st], token]
        cur = en
    parts.append(text[cur:])
    return "".join(parts), [(lname, layers_map[lname]) for lname in layers_map]
