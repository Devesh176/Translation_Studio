Bodhan Avaliable Models:

Model Name                    |  Input ₹                       |  Output ₹
indic-ocr                     |  ₹0.20 / image	               |  —
indic-speak                   |  ₹6 / 10K characters	       |  —
indic-transcribe              |  ₹0.10 / audio minute	       |  —
indic-translate               |  —	                           |  ₹0.20 / 10K output tokens
indic-transliterate           |  —	                           |  ₹0.20 / 10K output tokens


Bodhan API reference:

Every example below calls one Bodhan model on the gateway's /v1 routes: machine translation (indic-translate), transliteration (indic-transliterate), speech-to-text (indic-transcribe), document OCR (indic-ocr) and text-to-speech (indic-speak). The routes keep the OpenAI request and response shapes, so an SDK you already use works once base_url points here.

1. Translation:
```python
import requests

resp = requests.post(
    "https://api.bodhan.ai/v1/chat/completions",
    headers={"Authorization": "Bearer your_bodhan_key"},
    json={
        "model": "indic-translate",
        "messages": [{"role": "user", "content": "The meeting has been postponed."}],
        "target_language_code": "kn",
        "target_script": "native"
    },
)

print(resp.json()["choices"][0]["message"]["content"])
```

2. Transliteration:
```python
import requests

# same language in, same language out -- only the script changes
resp = requests.post(
    "https://api.bodhan.ai/v1/chat/completions",
    headers={"Authorization": "Bearer your_bodhan_key"},
    json={
        "model": "indic-transliterate",
        "messages": [{"role": "user", "content": "पनडुब्बी के अंदर पहुँच कर"}],
        "target_language_code": "hi",
        "target_script": "roman"
    },
)

print(resp.json()["choices"][0]["message"]["content"])
```

3. Speech-to-text:
```python
import requests

resp = requests.post(
    "https://api.bodhan.ai/v1/audio/transcriptions",
    headers={"Authorization": "Bearer your_bodhan_key"},
    files={"file": open("sample_hindi.wav", "rb")},
    data={"model": "indic-transcribe", "language": "hi", "vad": True},
)

print(resp.json()["text"])
```

4. Document OCR:
```python
import base64, requests

b64 = base64.b64encode(open("block.png", "rb").read()).decode()

resp = requests.post(
    "https://api.bodhan.ai/v1/chat/completions",
    headers={"Authorization": "Bearer your_bodhan_key"},
    json={
        "model": "indic-ocr",
        "messages": [{"role": "user", "content": [
            {"type": "image_url", "image_url": {"url": "data:image/png;base64," + b64}}
        ]}]
    },
)

print(resp.json()["choices"][0]["message"]["content"])
```

5. Text-to-Speech:
```python
import requests

# lang/style ride in the 'instructions' field as a JSON string,
# since OpenAI's audio.speech has no field of its own for them
resp = requests.post(
    "https://api.bodhan.ai/v1/audio/speech",
    headers={"Authorization": "Bearer your_bodhan_key"},
    json={
        "model": "indic-speak",
        "input": "The meeting has been postponed.",
        "voice": "Amit",
        "instructions": '{"lang": "en"}'
    },
)
with open("speech.wav", "wb") as f:
    f.write(resp.content)
```
