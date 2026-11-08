# My local Windows AI agent — source-code backup

The running **offline local agent** is in `local-agent/` (`agent.py`).
The movie dubbing engine and local voice-processing scripts are in `dubbing/`.
The older repository-root `main.py` and `local_agent.py` are legacy examples, not the latest Windows application.

This is a **source-code snapshot**, not a deployed cloud agent or a backup of model weights, voices, personal conversations or generated videos.

## Restore
Copy `local-agent/` to your agent program folder and `dubbing/` to `%USERPROFILE%\\video-dubbing-local`, install requirements, and restore local models from your *private* offline backup or download their permitted versions. Run `local-agent/agent.py` with local Ollama.
Create your own `config.json` from `local-agent/config.example.json`. The public source deliberately omits user-specific remote domain and email defaults; configure `AGENT_REMOTE_HOST` and `AGENT_REMOTE_USER` securely on your machine if using remote access.

**Never commit** API keys, login information, tokens, voice samples without redistribution rights, local files or conversation history.

## Test
Run `py -3.11 -m unittest discover -s tests -v` from the `local-agent` directory with the dubbing engine present at the local path. Editing approved Hebrew segments changes synthesis text and invalidates the audio cache only for changed segments. Test results do not guarantee end-to-end video quality or stability for every film.
