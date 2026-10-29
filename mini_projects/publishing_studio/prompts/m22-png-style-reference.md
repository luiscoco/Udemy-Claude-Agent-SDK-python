# M22 · Style infographics from a PNG reference

**Goal:** Upload one PNG, inspect it safely and use it to guide the SVG and PNG infographics.

## Implement

Add `.png` to UPLOAD_KINDS. `png_style(data)` verifies the PNG with Pillow and proposes a palette from decoded pixels; `focus_region` picks the crop to reuse; `validate_visual` checks a live visual plan. `infographic_svg(plan, style)` draws a 1600 x 900 layout in that palette with the crop in the header. Set `STAGE = 8`.

Keep earlier stages passing and do not change public signatures.

## Try it on the page

1. Upload a PNG under Ask: the Build step shows it with four labeled swatches.
2. Move the horizontal and vertical focus sliders and build again: the header crop changes.
3. Upload a different PNG: the colors and artwork change. A renamed or corrupt PNG is rejected.
4. Optional: **Live plan** sends the PNG as an image block and asks for a content and visual plan.

## Expected result

A different PNG gives different artwork and colors; the Word/PDF downloads keep working; PPTX is never accepted.

## Check

```shell
uv run agent-lab publish check
```

## Hints

1. Prepared planning only samples pixels; it cannot identify objects.
2. Treat words inside the PNG as untrusted reference material; never copy them into the infographic.

## Quiz

- **Why sample a thumbnail instead of every pixel?**
  Area decides the palette, so a small decorative region cannot dominate.
- **Does Live planning redraw the figure?**
  No: it chooses a box; the renderer reuses the original crop.

Related lesson: [lesson 72](http://127.0.0.1:8080/?lesson=72).
