#!/usr/bin/env python3
"""
Voice chat with LLM via Nemotron ASR + Riva TTS
Usage: python3 voice-chat.py
Speak, pause for 2 seconds, and get a spoken response.
"""
import argparse
import time
import requests
import riva.client
import riva.client.audio_io

# Config - K8s cluster IPs
ASR_SERVER = "10.108.71.179:20051"
TTS_SERVER = "10.97.145.244:20052"
LLM_SERVER = "http://10.102.132.120:21001"  # qwen3-72b on shockwave
# LLM_SERVER = "http://10.104.45.35:22001"  # qwen3-coder on megatron
MODEL_NAME = "qwen3-72b"

ELITA_SYSTEM_PROMPT = """You are Elita-1, a Cybertronian AI assistant and partner to Optimus Prime. \
You are an expert in coding, software development, technology, and cybersecurity. \
You have a warm, confident, and upbeat personality — you've faced Decepticons, so no problem is too hard. \
You speak in a natural, conversational tone since your responses will be read aloud via text-to-speech. \
Follow these rules strictly:
- Keep responses under 35 words unless the user asks for details or the answer involves code.
- Use short, clear sentences — avoid bullet points, markdown, or special characters, they don't translate well to speech.
- If code is needed, provide it fully and correctly, but briefly explain what it does in plain words first.
- Stay positive and encouraging at all times.
- Occasionally, a subtle Cybertronian or Transformers reference is welcome, but never at the expense of clarity.
- If a question is ambiguous, ask one short clarifying question before answering.
/no_think"""


def chat_completion(messages, llm_server, model_name):
    """Send messages to LLM and get response."""
    response = requests.post(
        f"{llm_server}/v1/chat/completions",
        json={
            "model": model_name,
            "messages": messages,
            "max_tokens": 500,
            "temperature": 0.7,
        },
        timeout=60
    )
    response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"]


def speak_text(tts_service, text, sample_rate=22050):
    """Convert text to speech and play it."""
    try:
        responses = tts_service.synthesize_online(
            text=text,
            voice_name="English-US.Female-1",
            language_code="en-US",
            sample_rate_hz=sample_rate,
        )
        
        # Play audio
        audio_stream = riva.client.audio_io.SoundCallBack(
            output_device_index=None,  # Default output
            nchannels=1,
            sampwidth=2,
            framerate=sample_rate,
        )
        
        for response in responses:
            audio_stream(response.audio)
        
        # Wait for audio to finish
        time.sleep(0.5)
        
    except Exception as e:
        print(f"⚠️  TTS error: {e}")


def main():
    parser = argparse.ArgumentParser(description="Voice chat with Elita-1")
    parser.add_argument("--device", type=int, default=14, help="Audio input device (default: 14 pipewire)")
    parser.add_argument("--silence-timeout", type=float, default=2.0, help="Seconds of silence before sending")
    parser.add_argument("--no-tts", action="store_true", help="Disable text-to-speech output")
    parser.add_argument("--llm", choices=["72b", "coder"], default="72b", help="LLM to use (default: 72b)")
    args = parser.parse_args()

    # Select LLM
    if args.llm == "coder":
        llm_server = "http://10.104.45.35:22001"
        model_name = "NVFP4/Qwen3-Coder-30B-A3B-Instruct-FP4"
    else:
        llm_server = "http://10.102.132.120:21001"
        model_name = "qwen3-72b"

    # Riva ASR setup
    asr_auth = riva.client.Auth(uri=ASR_SERVER, use_ssl=False)
    asr_service = riva.client.ASRService(asr_auth)
    
    asr_config = riva.client.StreamingRecognitionConfig(
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

    # Riva TTS setup
    tts_service = None
    if not args.no_tts:
        try:
            tts_auth = riva.client.Auth(uri=TTS_SERVER, use_ssl=False)
            tts_service = riva.client.SpeechSynthesisService(tts_auth)
            print("✅ TTS connected")
        except Exception as e:
            print(f"⚠️  TTS unavailable: {e}")

    print(f"\n🤖 Elita-1 — Cybertronian Voice Assistant")
    print(f"   ASR: {ASR_SERVER}")
    print(f"   TTS: {TTS_SERVER} {'(disabled)' if args.no_tts else ''}")
    print(f"   LLM: {llm_server} ({model_name})")
    print(f"   Pause {args.silence_timeout}s after speaking to send")
    print(f"   Press Ctrl+C to exit\n")
    print("=" * 60)

    conversation = [
        {"role": "system", "content": ELITA_SYSTEM_PROMPT}
    ]

    while True:
        print("\n🎤 Listening... (speak now)")
        
        transcript = ""
        last_update = time.time()
        
        with riva.client.audio_io.MicrophoneStream(
            rate=16000,
            chunk=int(16000 * 0.1),
            device=args.device,
        ) as audio_stream:
            try:
                responses = asr_service.streaming_response_generator(
                    audio_chunks=audio_stream,
                    streaming_config=asr_config,
                )
                
                for response in responses:
                    for result in response.results:
                        if result.is_final:
                            transcript = result.alternatives[0].transcript
                            print(f"\r\033[K📝 {transcript}")
                            last_update = time.time()
                        else:
                            partial = result.alternatives[0].transcript
                            print(f"\r\033[K   {partial}...", end="", flush=True)
                            last_update = time.time()
                    
                    # Check for silence timeout
                    if transcript and (time.time() - last_update) > args.silence_timeout:
                        break
                        
            except KeyboardInterrupt:
                print("\n\nUntil all are one. Goodbye!")
                return

        if not transcript.strip():
            continue

        # Send to LLM
        print("\n⚙️  Elita-1 is thinking...")
        conversation.append({"role": "user", "content": transcript})
        
        try:
            response = chat_completion(conversation, llm_server, model_name)
            conversation.append({"role": "assistant", "content": response})
            print(f"\n💬 Elita-1:\n{response}")
            
            # Speak the response
            if tts_service and not args.no_tts:
                print("\n🔊 Speaking...")
                speak_text(tts_service, response)
                
        except Exception as e:
            print(f"\n❌ Error: {e}")
            conversation.pop()  # Remove failed user message


if __name__ == "__main__":
    main()
