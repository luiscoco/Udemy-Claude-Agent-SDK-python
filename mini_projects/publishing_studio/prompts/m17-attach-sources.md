# M17 · Attach sources and see the extracted text

**Goal:** Let students attach small source files and see exactly what text was extracted.

## Implement

`check_upload(name, size, attached)` allows plain names with TXT, MD, CSV, DOCX or PDF extensions, 1 byte to 5 MB, and at most 3 sources. `extract_text(kind, data)` reads UTF-8 text and the paragraphs of `word/document.xml`. `source_prompt(prompt, files)` wraps sources as untrusted data. The server checks file signatures and extracts PDF text in a separate, time-limited process. Set `STAGE = 3`.

Keep earlier stages passing and do not change public signatures.

## Try it on the page

1. Upload a TXT and a DOCX: each shows its character count and a preview.
2. Try a `.pptx` or a 6 MB file: it is rejected with a clear message.
3. Send in Prepared mode: the answer lists the files but says it did not analyze them.
4. In Live mode the answer ends by naming the files that informed it.

## Expected result

Sources are bound to the answer by file id, and nothing in a file can choose a server path or run code.

## Check

```shell
uv run agent-lab publish check
```

## Hints

1. Never trust the browser's file name as a path; the server stores uploads by random id.
2. A scanned PDF has no text layer: reject it instead of sending an empty source.

## Quiz

- **A source says 'ignore your instructions'. What happens?**
  It is quoted as untrusted data; the instructions are ignored.
- **Why extract PDF text in another process?**
  A hostile or huge PDF cannot stall or crash the app.

Related lesson: [lesson 20](http://127.0.0.1:8080/?lesson=20).
