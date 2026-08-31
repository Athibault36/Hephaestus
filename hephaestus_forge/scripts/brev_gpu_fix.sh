pkill -f "forge.py gpu-dev" 2>/dev/null || true
cd ~/Hephaestus/hephaestus_forge
source .venv/bin/activate
pip install -q nvidia-cuda-runtime-cu12
CUDA_RT=$(python -c "import nvidia.cuda_runtime.lib as l, pathlib; print(pathlib.Path(l.__file__).parent)")
export LD_LIBRARY_PATH="${CUDA_RT}:/usr/local/cuda/lib64"
nohup env LD_LIBRARY_PATH="$LD_LIBRARY_PATH" python forge.py gpu-dev --repo ~/Hephaestus --serve-only --host 0.0.0.0 --port 8080 > ~/gpu_dev.log 2>&1 &
echo "LD_LIBRARY_PATH=$LD_LIBRARY_PATH"
sleep 150
tail -10 ~/gpu_dev.log
curl -sf http://127.0.0.1:8080/v1/models | head -c 200 || echo NOT_READY
nvidia-smi --query-gpu=memory.used,utilization.gpu --format=csv,noheader
