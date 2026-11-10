# On soundwave - export (this is ~17GB so will take a minute)
sudo ctr -n k8s.io images export /tmp/riva-tts.tar nvcr.io/nim/nvidia/riva-tts:1.3.0

# Copy to megatron
scp /tmp/riva-tts.tar megatron:~

# On megatron - import
ssh megatron "sudo ctr -n k8s.io images import ~/riva-tts.tar"

# Cleanup
rm /tmp/riva-tts.tar
ssh megatron "rm ~/riva-tts.tar"

