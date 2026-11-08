from huggingface_hub import get_token,whoami,hf_hub_download
import json
token=get_token()
print('TOKEN_PRESENT:',bool(token))
if token:
 try:
  info=whoami(token=token)
  print('HF_ACCOUNT:',info.get('name'))
  access=info.get('auth',{}).get('accessToken',{})
  print('TOKEN_ROLE:',access.get('role'))
  hf_hub_download('pyannote/speaker-diarization-community-1','config.yaml',token=token)
  print('MODEL_ACCESS_OK')
 except Exception as e:
  print('ERROR_TYPE:',type(e).__name__)
  response=getattr(e,'response',None)
  if response is not None:
   print('HTTP_STATUS:',response.status_code)
   message=response.text[:1800]
   if token:message=message.replace(token,'[REDACTED]')
   print('DETAIL:',message)
token=None