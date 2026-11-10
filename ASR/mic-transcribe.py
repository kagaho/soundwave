#!/usr/bin/env python3
"""
Real-time microphone transcription with Nemotron ASR Streaming NIM
Usage: python3 mic-transcribe.py [--server HOST:PORT]

Requirements:
  pip install sounddevice numpy websockets

Press Ctrl+C to stop.
"""

import argparse
import asyncio
import base64
import json
import queue
import sys

try:
    import sounddevice as sd
except ImportError:
    print("Install sounddevice: pip install sounddevice")
    sys.exit(1)

try:
    import websockets
except ImportError:
    print("Install websockets: pip install websockets")
    sys.exit(1)

import numpy as np

SAMPLE_RATE = 16000
CHANNELS = 1
CHUNK_DURATION_MS = 100


def list_audio_devices():
    print("\nAvailable audio input devices:")
    print("-" * 50)
    devices = sd.query_devices()
    for i, dev in enumerate(devices):
        if dev['max_input_channels'] > 0:
            marker = " (default)" if i == sd.default.device[0] else ""
            print(f"  [{i}] {dev['name']}{marker}")
    print("-" * 50)


class MicrophoneStream:
    def __init__(self, rate=SAMPLE_RATE, chunk_ms=CHUNK_DURATION_MS, device=None):
        self.rate = rate
        self.chunk_size = int(rate * chunk_ms / 1000)
        self.device = device
        self.audio_queue = queue.Queue()
        self.stream = None
        self.running = True

    def start(self):
        self.stream = sd.InputStream(
            samplerate=self.rate,
            channels=CHANNELS,
            dtype='int16',
            blocksize=self.chunk_size,
            device=self.device,
            callback=self._audio_callback
        )
        self.stream.start()

    def stop(self):
        self.running = False
        if self.stream:
            self.stream.stop()
            self.stream.close()

    def _audio_callback(self, indata, frames, time, status):
        if status:
            print(f"⚠ Audio: {status}", file=sys.stderr)
        self.audio_queue.put(indata.copy())

    def get_chunk(self, timeout=0.5):
        try:
            return self.audio_queue.get(timeout=timeout)
        except queue.Empty:
            return None


async def transcribe_realtime(server_url: str, device=None):
    ws_url = server_url.replace("http://", "ws://").replace("https://", "wss://")
    ws_url = f"{ws_url}/v1/realtime/transcription_sessions"
    
    print(f"\n🎤 Real-time transcription")
    print(f"   Server: {ws_url}")
    print(f"   Sample rate: {SAMPLE_RATE} Hz")
    print(f"   Press Ctrl+C to stop\n")
    print("=" * 60)
    
    mic = MicrophoneStream(device=device)
    
    try:
        async with websockets.connect(ws_url) as ws:
            config = {
                "type": "config",
                "config": {
                    "encoding": "LINEAR16",
                    "sample_rate_hertz": SAMPLE_RATE,
                    "language_code": "en-US",
                    "enable_automatic_punctuation": True,
                    "interim_results": True,
                }
            }
            await ws.send(json.dumps(config))
            print("✓ Connected to ASR server")
            print("=" * 60)
            print()
            
            mic.start()
            
            async def send_audio():
                while mic.running:
                    chunk = mic.get_chunk(timeout=0.1)
                    if chunk is not None:
                        audio_msg = {
                            "type": "audio",
                            "audio": base64.b64encode(chunk.tobytes()).decode('utf-8')
                        }
                        await ws.send(json.dumps(audio_msg))
                    await asyncio.sleep(0.01)
            
            async def receive_transcripts():
                async for message in ws:
                    try:
                        data = json.loads(message)
                        if data.get("type") == "transcript":
                            text = data.get("transcript", "")
                            is_final = data.get("is_final", False)
                            if is_final and text:
                                print(f"\r\033[K✓ {text}")
                            elif text:
                                print(f"\r\033[K  {text}...", end="", flush=True)
                        elif data.get("type") == "error":
                            print(f"\n⚠ Error: {data.get('message')}")
                    except json.JSONDecodeError:
                        pass
            
            send_task = asyncio.create_task(send_audio())
            recv_task = asyncio.create_task(receive_transcripts())
            await asyncio.gather(send_task, recv_task)
            
    except websockets.exceptions.ConnectionClosed as e:
        print(f"\n⚠ Connection closed: {e}")
    except ConnectionRefusedError:
        print(f"\n✗ Cannot connect to {ws_url}")
    finally:
        mic.stop()


def main():
    parser = argparse.ArgumentParser(description="Real-time mic transcription")
    parser.add_argument("--server", default="http://10.107.122.126:8000")
    parser.add_argument("--list-devices", action="store_true")
    parser.add_argument("--device", type=int, default=None)
    args = parser.parse_args()
    
    if args.list_devices:
        list_audio_devices()
        return
    
    try:
        asyncio.run(transcribe_realtime(args.server, device=args.device))
    except KeyboardInterrupt:
        print("\n\nTranscription stopped.")


if __name__ == "__main__":
    main()
