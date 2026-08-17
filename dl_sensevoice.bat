@echo off
cd /d "E:\树剪软件相关文件"
echo === SenseVoiceSmall Download ===
modelscope download --model FunAudioLLM/SenseVoiceSmall --local_dir models/SenseVoiceSmall
echo Done!
pause
