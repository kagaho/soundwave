#!/usr/bin/env python3
"""
Real-time mic transcription with Nemotron ASR using nvidia-riva-client
Usage: python3 riva-mic.py [--server HOST:PORT]

Requirements: pip install nvidia-riva-client sounddevice numpy
"""

import argparse
import riva.client
import riva.client.audio_io

def main():
    parser = argparse.ArgumentParser(description="Streaming ASR with Riva")
    parser.add_argument("--server", default="10.107.122.126:50051", help="Riva gRPC server")
    parser.add_argument("--list-devices", action="store_true", help="List audio devices")
    parser.add_argument("--device", type=int, default=None, help="Audio device index")
    args = parser.parse_args()

    if args.list_devices:
        import sounddevice as sd
        print("\nAudio input devices:")
        for i, dev in enumerate(sd.query_devices()):
            if dev['max_input_channels'] > 0:
                print(f"  [{i}] {dev['name']}")
        return

    # Create Riva ASR client
    auth = riva.client.Auth(uri=args.server, use_ssl=False)
    asr_service = riva.client.ASRService(auth)

    # Streaming config
    config = riva.client.StreamingRecognitionConfig(
        config=riva.client.RecognitionConfig(
            encoding=riva.client.AudioEncoding.LINEAR_PCM,
            language_code="en-US",
            max_alternatives=1,
            enable_automatic_punctuation=True,
            sample_rate_hertz=16000,
            audio_channel_count=1,
        ),
        interim_results=True,
    )

    print(f"\n🎤 Streaming ASR")
    print(f"   Server: {args.server}")
    print(f"   Press Ctrl+C to stop\n")
    print("=" * 60)

    with riva.client.audio_io.MicrophoneStream(
        rate=16000,
        chunk=int(16000 * 0.1),
        device=args.device,
    ) as audio_stream:
        try:
            responses = asr_service.streaming_response_generator(
                audio_chunks=audio_stream,
                streaming_config=config,
            )
            for response in responses:
                for result in response.results:
                    if result.is_final:
                        print(f"\r\033[K✓ {result.alternatives[0].transcript}")
                    else:
                        print(f"\r\033[K  {result.alternatives[0].transcript}...", end="", flush=True)
        except KeyboardInterrupt:
            print("\n\nStopped.")

if __name__ == "__main__":
    main()
