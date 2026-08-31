cd ~/Hephaestus/hephaestus_forge
source .venv/bin/activate
pip install -q "llama-cpp-python[server]" starlette-context
pkill -f "forge.py gpu-dev" 2>/dev/null || true
nohup python forge.py gpu-dev --repo ~/Hephaestus --serve-only --host 0.0.0.0 --port 8080 > ~/gpu_dev.log 2>&1 &
sleep 180
tail -8 ~/gpu_dev.log
curl -s http://127.0.0.1:8080/v1/models | head -c 250
echo
ps aux | grep "forge.py gpu-dev" | grep -v grep
