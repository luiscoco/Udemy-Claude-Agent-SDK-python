# Lesson 29: Images and file input

The original offline exercise writes a 68-byte one-pixel PNG and builds a local base64 image block. The enhanced experiment creates a deterministic 256×256 red or blue PNG inside the isolated lesson workspace. The host validates its PNG signature, dimensions and byte limit, hashes it, and sends one typed `image/png` base64 block followed by a text question in an SDK user message. The report records the hash and metadata without including the base64 payload.

The automatic check requires one yielded typed image message, a successful SDK result in the initialized session, an unchanged workspace file hash, and a `RED` or `BLUE` answer matching the selected image. Paired live colors provide behavioral evidence that the image content influenced the response. The provider's internal vision processing is not directly visible. The lesson accepts neither arbitrary upload paths nor external files.

Run the offline exercise with `uv run agent-lab lesson 29`. Run both bounded provider-backed image cases with `uv run python scripts/lesson_live_smoke.py 29 --live` after the live environment is configured. Reports are saved under `.lab-data/lesson-live-smoke/`.
