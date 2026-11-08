from huggingface_hub import login,whoami,hf_hub_download
from getpass import getpass
print("Paste a Hugging Face READ token here. Input is hidden.")
token=getpass("Read token: ")
login(token=token,add_to_git_credential=False)
try:
    hf_hub_download(repo_id="pyannote/speaker-diarization-community-1",filename="config.yaml",token=token)
    print("Model access confirmed. You can close this window.")
except Exception as e:
    print("Login saved, but model access failed. Confirm you accepted access terms using the same account.")
    print(type(e).__name__)
token=None
input("Press Enter to close.")