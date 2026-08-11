import argparse
import asyncio
import json
import logging
import soundfile as sf
import websockets

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


async def run_text_client(url: str, question: int, text: str):
    logging.info(f"Connecting to {url}...")
    async with websockets.connect(url) as ws:
        payload = {"question": question, "text": text}
        logging.info(f"Sending text payload: {payload}")
        await ws.send(json.dumps(payload))

        response = await ws.recv()
        logging.info(f"Received response: {response}")


async def run_audio_client(url: str, question: int, file_path: str):
    logging.info(f"Connecting to {url}...")
    async with websockets.connect(url) as ws:
        # Step 1: Send text question signal
        question_payload = {"question": question}
        logging.info(f"Sending question signal: {question_payload}")
        await ws.send(json.dumps(question_payload))

        # Step 2: Read WAV audio and stream PCM chunks
        data, samplerate = sf.read(file_path, dtype="int16")
        pcm_bytes = data.tobytes()

        # Send in 100ms chunks (16kHz 16-bit mono -> 3200 bytes per 100ms)
        chunk_size = 3200
        logging.info(f"Streaming {len(pcm_bytes)} audio bytes in chunks of {chunk_size}...")

        for i in range(0, len(pcm_bytes), chunk_size):
            chunk = pcm_bytes[i : i + chunk_size]
            await ws.send(chunk)
            await asyncio.sleep(0.1)

        logging.info("Audio streaming complete. Waiting for response...")
        response = await asyncio.wait_for(ws.recv(), timeout=10.0)
        logging.info(f"Received response: {response}")


def main():
    parser = argparse.ArgumentParser(description="VoiceSatisfaction Test Client")
    parser.add_argument("--url", default="ws://localhost:8000/ws/test-session-002")
    parser.add_argument("--mode", choices=["text", "audio"], required=True)
    parser.add_argument("--question", type=int, default=1)
    parser.add_argument("--text", default="sangat puas")
    parser.add_argument("--file", help="Path to 16kHz PCM WAV file")

    args = parser.parse_args()

    if args.mode == "text":
        asyncio.run(run_text_client(args.url, args.question, args.text))
    elif args.mode == "audio":
        if not args.file:
            print("Error: --file argument is required for audio mode")
            return
        asyncio.run(run_audio_client(args.url, args.question, args.file))


if __name__ == "__main__":
    main()
