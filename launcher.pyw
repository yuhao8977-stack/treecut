import os, sys, subprocess
os.environ.update({
    "MPLBACKEND":"Agg","QT_QPA_PLATFORM":"offscreen","SDL_VIDEODRIVER":"dummy",
    "PYTHONIOENCODING":"utf-8","HF_ENDPOINT":"https://hf-mirror.com",
    "HF_HUB_ENABLE_HF_TRANSFER":"0", "NO_PROXY":"huggingface.co,hf-mirror.com",
})
os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.exit(subprocess.call([sys.executable, u"树剪.py"]))
