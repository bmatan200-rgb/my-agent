import importlib.util,json
from pathlib import Path
print(json.dumps({n:bool(importlib.util.find_spec(n)) for n in ['pyannote','speechbrain','transformers','librosa','soundfile']},indent=2))
from huggingface_hub import get_token
print('HF_TOKEN_PRESENT:', bool(get_token()))