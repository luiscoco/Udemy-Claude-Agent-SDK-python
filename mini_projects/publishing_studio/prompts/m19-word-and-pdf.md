# M19 · Build Word and PDF files

**Goal:** Build readable Word and PDF files from one validated plan.

## Implement

`code_lines(code, language)` highlights code with Pygments into colored segments without losing a character. `document_html(plan)` writes one escaped HTML page; the server prints it to PDF with the network blocked and builds the DOCX with python-docx from the same plan. Set `STAGE = 5`.

Keep earlier stages passing and do not change public signatures.

## Try it on the page

1. Build **Word + PDF document**: the preview shows headings, lists, a table and a dark code panel.
2. Download both. Open them and compare the title and paragraphs with the selected answer.
3. Note the byte size, SHA-256, planning mode and source answer under each download.

## Expected result

Both files are built from the same plan, or neither is saved; raw HTML in an answer appears as text.

## Check

```shell
uv run agent-lab publish check
```

## Hints

1. Escape every source string before it reaches HTML; python-docx escapes Word XML for you.
2. Keep code in a monospace, colored, line-preserving panel in every format.

## Quiz

- **The PDF fails but the DOCX succeeded. What is saved?**
  Nothing: the pair is published together or not at all.
- **How do you identify a download later?**
  By its opaque artifact id and SHA-256, tied to the answer id and hash.

Related lesson: [lesson 72](http://127.0.0.1:8080/?lesson=72).
