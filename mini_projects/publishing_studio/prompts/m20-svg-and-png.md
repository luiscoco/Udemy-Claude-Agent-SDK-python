# M20 · Build SVG and PNG infographics

**Goal:** Produce a concise, downloadable infographic as SVG and PNG.

## Implement

`infographic_svg(plan, style)` draws the title, 3 to 6 numbered cards, the takeaway and a labeled code excerpt with native `<text>`/`<tspan>` colors. No scripts, `foreignObject` or external links; the server rejects any SVG that has them and rasterizes it to PNG. Set `STAGE = 6`.

Keep earlier stages passing and do not change public signatures.

## Try it on the page

1. Choose **SVG + PNG infographic** and build: the preview is the exact SVG.
2. Download both. The SVG opens in any viewer; the PNG starts with the PNG signature.
3. Try a long title: it wraps to two lines and is cut with an ellipsis, never overflowing.

## Expected result

The infographic is a deterministic diagram built from a validated plan, not free-form model output.

## Check

```shell
uv run agent-lab publish check
```

## Hints

1. Never accept SVG, HTML, CSS or image links from a model; render from data you validated.
2. Keep the complete code in Word/PDF; the infographic shows a bounded excerpt.

## Quiz

- **Why not let Claude write the SVG?**
  Model SVG can carry scripts or remote links; your renderer is reviewable.
- **Where is the full code?**
  In the Word and PDF files; the infographic shows at most 12 lines.

Related lesson: [lesson 72](http://127.0.0.1:8080/?lesson=72).
