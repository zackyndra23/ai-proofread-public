from contextlib import contextmanager

from services import ner as sn


@contextmanager
def _ctx(flag_dict, name):
    flag_dict[name] = flag_dict.get(name, 0) + 1
    try:
        yield
    finally:
        pass


def test_resolve_device_cpu(monkeypatch):
    monkeypatch.setenv("USE_GPU", "1")
    monkeypatch.setenv("GPU_DEVICE_INDEX", "2")
    monkeypatch.setenv("NER_FP16", "1")
    monkeypatch.setenv("NER_BATCH_SIZE", "4")
    monkeypatch.setattr(sn.torch.cuda, "is_available", lambda: False)

    sn._DEVICE_LOGGED = False
    device_idx, fp16, batch = sn._resolve_device()
    assert device_idx == -1
    assert fp16 is True
    assert batch == 4


def test_resolve_device_gpu(monkeypatch):
    monkeypatch.setenv("USE_GPU", "1")
    monkeypatch.setenv("GPU_DEVICE_INDEX", "1")
    monkeypatch.setattr(sn.torch.cuda, "is_available", lambda: True)

    sn._DEVICE_LOGGED = False
    device_idx, _, _ = sn._resolve_device()
    assert device_idx == 1


def test_infer_spans_uses_inference_and_amp(monkeypatch):
    runner = sn.NerRunner(base_dir=".")
    runner.fp16 = True
    runner.device_idx = 0

    class DummyPipe:
        def __init__(self):
            self.tokenizer = object()

        def __call__(self, text):
            return [{"start": 0, "end": 1, "entity": "PER"}]

    monkeypatch.setattr(runner, "_pipe", lambda model_dir: DummyPipe())
    monkeypatch.setattr(sn, "_iter_token_chunks", lambda text, tokenizer, max_tokens=510, stride=50: [text])

    flags = {}
    monkeypatch.setattr(sn, "_inference_context", lambda: _ctx(flags, "inference"))
    monkeypatch.setattr(sn, "_autocast_context", lambda enabled: _ctx(flags, "autocast"))

    spans = runner.infer_spans_for_model("abc", "model")
    assert spans and spans[0]["label"] == "PER"
    assert flags.get("inference", 0) == 1
    assert flags.get("autocast", 0) == 1


def test_infer_spans_cpu_no_amp(monkeypatch):
    runner = sn.NerRunner(base_dir=".")
    runner.fp16 = True
    runner.device_idx = -1

    class DummyPipe:
        def __init__(self):
            self.tokenizer = object()

        def __call__(self, text):
            return []

    monkeypatch.setattr(runner, "_pipe", lambda model_dir: DummyPipe())
    monkeypatch.setattr(sn, "_iter_token_chunks", lambda text, tokenizer, max_tokens=510, stride=50: [text])

    flags = {}
    monkeypatch.setattr(sn, "_inference_context", lambda: _ctx(flags, "inference"))
    def _auto(enabled):
        if enabled:
            return _ctx(flags, "autocast")
        return _ctx(flags, "no_autocast")
    monkeypatch.setattr(sn, "_autocast_context", _auto)

    runner.infer_spans_for_model("abc", "model")
    assert flags.get("inference", 0) == 1
    assert flags.get("autocast", 0) == 0
