# Lesson 52 narration status

Three reviewed English scripts in `agent_lab/content/lesson_52_narration.json` match source excerpts for comparison, calibration and baseline promotion. `scripts/lesson52_audio.py plan --lessons=52` reports 1,119 UTF-16 characters for the requested Inworld Yash voice and `inworld-tts-2` model. All three clips were recorded after the workspace credential was refreshed. `agent_lab/lesson52_audio.py` exposes each clip only when source, text, settings, MP3 and timing hashes match the published manifest.

The first recording request received HTTP 403 `SESSION_TOKEN_EXPIRED` and produced no audio. Its private failed response and receipt are retained in `.lab-data/lesson-52-audio/` as a definitively failed authentication attempt. The final source-hash-bound recordings and provider word timing are indexed by `public/audio/code/lesson-52-manifest.json`. Provider billing was not reported; human listening review remains open.
