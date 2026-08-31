from pathlib import Path

from hephaestus_forge.gpu_dev.llama_manager import (
    GPUSettings,
    build_llama_server_argv,
    recommend_gpu_settings,
)


def test_l40s_gets_full_offload_big_context_and_flash_attn():
    s = recommend_gpu_settings("NVIDIA L40S", vram_free_mb=46000, requested_ctx=32768)
    assert s.n_gpu_layers == -1  # all layers on GPU
    assert s.n_ctx == 32768
    assert s.n_batch == 512
    assert s.flash_attn is True


def test_cpu_fallback_disables_gpu_features():
    s = recommend_gpu_settings(None, vram_free_mb=0, requested_ctx=32768)
    assert s.n_gpu_layers == 0
    assert s.flash_attn is False
    assert s.n_ctx <= 8192


def test_rtx4090_class_caps_context_but_keeps_flash_attn():
    s = recommend_gpu_settings("NVIDIA GeForce RTX 4090", vram_free_mb=24000)
    assert s.flash_attn is True
    assert s.n_ctx == 16384  # 24 GB class caps context
    assert s.n_gpu_layers == -1


def test_small_gpu_partial_offload():
    s = recommend_gpu_settings("NVIDIA GeForce GTX 1080", vram_free_mb=8000, requested_gpu_layers=-1)
    assert s.n_gpu_layers == 20  # partial offload when caller asked for "all" on a small card
    assert s.flash_attn is False  # pre-Ampere: no flash attention


def test_flash_attn_detection_across_families():
    for name in ["NVIDIA L40S", "NVIDIA A100-SXM4-40GB", "NVIDIA H100 PCIe", "NVIDIA RTX A6000"]:
        assert recommend_gpu_settings(name, 46000).flash_attn is True
    for name in ["Tesla T4", "NVIDIA GeForce GTX 1080 Ti"]:
        assert recommend_gpu_settings(name, 12000).flash_attn is False


def test_build_argv_includes_perf_flags():
    s = GPUSettings(n_gpu_layers=-1, n_ctx=32768, n_batch=512, flash_attn=True, n_threads=16)
    argv = build_llama_server_argv("python", Path("/models/x.gguf"), "0.0.0.0", 8080, s)
    assert argv[:3] == ["python", "-m", "llama_cpp.server"]
    assert "--flash_attn" in argv and argv[argv.index("--flash_attn") + 1] == "true"
    assert argv[argv.index("--n_ctx") + 1] == "32768"
    assert argv[argv.index("--n_gpu_layers") + 1] == "-1"
    assert argv[argv.index("--model") + 1] == "/models/x.gguf"


def test_build_argv_omits_flash_attn_on_cpu():
    s = recommend_gpu_settings(None, 0)
    argv = build_llama_server_argv("python", Path("/m.gguf"), "127.0.0.1", 8080, s)
    assert "--flash_attn" not in argv
