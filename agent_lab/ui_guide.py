"""A written, student-controlled Learning Guide. No exercise or SDK calls live here."""

import json
from typing import Any

from nicegui import ui

from agent_lab.lesson_guide import LearningGuide, adjacent_lesson, lesson_url
from agent_lab.ui_learning import set_preference, stored

GUIDE_CSS = """
.learning-guide {
    position: fixed; right: 20px; bottom: 20px; z-index: 2500;
    width: 410px; max-width: calc(100vw - 24px); max-height: min(76vh, 740px);
    background: #ffffff; color: #17294a; border: 2px solid #2563eb;
    border-radius: 16px; box-shadow: 0 12px 40px #0003;
    padding: 16px; gap: 12px; font-size: 18px; line-height: 1.5;
}
.learning-guide-heading { font-size: 21px; font-weight: 750; }
.learning-guide-body { overflow-y: auto; min-height: 0; width: 100%; padding: 3px; }
.learning-guide .q-btn { white-space: normal; min-height: 44px; font-size: 16px; }
.learning-guide .q-btn:focus-visible { outline: 3px solid #1d4ed8; outline-offset: 3px; }
.learning-guide .q-field { max-width: 100%; }
.learning-guide .q-field__native, .learning-guide .q-field__label { font-size: 17px; }
.learning-guide .guide-primary { --q-primary: #1d4ed8; }
.learning-guide-step { font-weight: 700; font-size: 20px; }
.learning-guide-action { background: #eff6ff; color: #173b63; padding: 12px; border-radius: 10px; }
.learning-guide-status { font-size: 16px; color: #475569; }
.learning-guide-target { outline: 3px solid #dc2626 !important; outline-offset: 5px; border-radius: 5px; }
.learning-guide-actions { width: 100%; gap: 8px; }
.learning-guide-actions .q-btn { flex: 1 1 130px; }
.guide-lesson-actions { align-items: center; gap: 12px; }
body.body--dark .learning-guide { background: #171e2e; color: #f1f5f9; border-color: #93c5fd; }
body.body--dark .learning-guide-action { background: #203654; color: #e0efff; }
body.body--dark .learning-guide-status { color: #cbd5e1; }
body.body--dark .learning-guide .q-btn:focus-visible { outline-color: #93c5fd; }
body.lab-text-large .learning-guide { font-size: 20px; }
body.lab-text-xlarge .learning-guide { font-size: 22px; }
@media (max-width: 600px) {
    .learning-guide { right: 12px; bottom: 12px; width: calc(100vw - 24px); max-height: 53vh; padding: 12px; }
}
"""

# These functions only scroll, focus the lesson heading and manage an outline.
# They never click a target or change any form value.
CLEAR_TARGET = """
if ((window.__learningGuideRevision || 0) <= REVISION) {
    document.querySelectorAll('.learning-guide-target').forEach(e => e.classList.remove('learning-guide-target'));
    window.__learningGuideRevision = REVISION;
}
"""
LESSON_START = """
const heading = document.querySelector('#lesson-heading');
if (heading) {
    const header = document.querySelector('.q-header');
    const offset = header ? header.getBoundingClientRect().bottom + 16 : 16;
    window.scrollTo({top: Math.max(0, window.scrollY + heading.getBoundingClientRect().top - offset), behavior: 'auto'});
    heading.focus({preventScroll: true});
}
"""


def guide_positions() -> dict[str, str]:
    value = stored("learning_guide_positions", {})
    return dict(value) if isinstance(value, dict) else {}


class LessonGuidePanel:
    def __init__(self, guide: LearningGuide, tabs: Any, path: str = "") -> None:
        self.guide, self.tabs, self.path = guide, tabs, path
        self.index = 0
        self.active = self.paused = self.minimized = False
        self.revision = 0
        self.key = str(guide.lesson)
        self.launch = ui.button("Open Learning Guide", icon="explore", on_click=self.open)
        self.launch.props("outline aria-haspopup='false'")
        ui.add_css(GUIDE_CSS)
        with ui.teleport("body"):
            with ui.column().classes("learning-guide").props(
                f'role="region" aria-label="Lesson {guide.lesson} Learning Guide" tabindex="-1"'
            ) as self.panel:
                with ui.row().classes("w-full items-center justify-between gap-1"):
                    ui.label("Learning Guide").classes("learning-guide-heading")
                    with ui.row().classes("gap-0"):
                        self.minimize = ui.button(icon="minimize", on_click=self.toggle_minimized).props(
                            "flat round aria-label='Minimize Learning Guide'"
                        )
                        ui.button(icon="close", on_click=self.close).props(
                            "flat round aria-label='Close Learning Guide'"
                        )
                self.body = ui.column().classes("learning-guide-body gap-3")
        self.panel.set_visibility(False)
        self.launch.props(f'aria-controls="{self.panel.html_id}" aria-expanded="false"')
        self.minimize.props(f'aria-controls="{self.body.html_id}" aria-expanded="true"')
        self.tabs.on_value_change(self.tab_changed)
        self.panel.on("keydown.escape", self.close)

        @ui.refreshable
        def content() -> None:
            if not self.active:
                ui.label("A written tour of this lesson's real controls and evidence.")
                ui.label("The guide makes no model calls and never runs or completes the lesson.").classes(
                    "learning-guide-status"
                )
                ui.button("Start guided tour", icon="route", on_click=lambda: self.show(0)).classes(
                    "guide-primary"
                )
                saved = guide_positions().get(self.key)
                if saved in [section.id for section in self.guide.sections]:
                    index = next(i for i, section in enumerate(self.guide.sections) if section.id == saved)
                    ui.button(
                        f"Resume: {self.guide.sections[index].title}",
                        icon="play_arrow", on_click=lambda: self.show(index),
                    ).props("outline")
                ui.label("Recorded Python narration is not included in this pilot.").classes(
                    "learning-guide-status"
                )
                return
            section = self.guide.sections[self.index]
            ui.label(f"Section {self.index + 1} of 7 · {section.title}").classes("learning-guide-step").props(
                'role="heading" aria-level="2" tabindex="-1"'
            )
            ui.select(
                {i: s.title for i, s in enumerate(self.guide.sections)},
                value=self.index, label="Jump to guide section",
                on_change=lambda e: self.show(int(e.value)) if e.value != self.index else None,
            ).props("outlined dense").classes("w-full")
            ui.label(section.text)
            with ui.column().classes("learning-guide-action w-full gap-1"):
                ui.label("Your action").classes("font-bold")
                ui.label(section.action)
            if section.student_action:
                ui.label("Pause here and do this yourself. Continue when you are ready.").classes(
                    "learning-guide-status"
                )
            self.status = ui.label(
                "Tour paused after a tab change. Select Show section to continue."
                if self.paused else "The outlined element belongs to this section."
            ).classes("learning-guide-status").props('role="status" aria-live="polite"')
            ui.button("Show section", icon="my_location", on_click=lambda: self.show(self.index)).props("outline")
            with ui.row().classes("learning-guide-actions"):
                previous = ui.button("Previous section", icon="chevron_left", on_click=lambda: self.show(self.index - 1))
                previous.set_enabled(self.index > 0)
                if self.index < len(self.guide.sections) - 1:
                    ui.button("Next section", icon="chevron_right", on_click=lambda: self.show(self.index + 1))
                else:
                    ui.button("Finish tour", icon="done", on_click=self.finish)
                    if adjacent_lesson(self.guide.lesson, 1, self.path) is not None:
                        ui.button("Next lesson →", on_click=self.next_lesson).classes("guide-primary")

        self.content = content
        with self.body:
            content()

    def open(self) -> None:
        self.panel.set_visibility(True)
        self.launch.props('aria-expanded="true"')
        self.minimized = False
        self.body.set_visibility(True)
        self.minimize.props("aria-label='Minimize Learning Guide' aria-expanded='true'")
        self.minimize.set_icon("minimize")
        self.content.refresh()
        ui.run_javascript(
            f"requestAnimationFrame(() => document.getElementById({json.dumps(self.panel.html_id)})?.focus({{preventScroll: true}}))"
        )

    def clear_target(self) -> None:
        self.revision += 1
        ui.run_javascript(CLEAR_TARGET.replace("REVISION", str(self.revision)))

    def close(self) -> None:
        self.clear_target()
        self.panel.set_visibility(False)
        self.launch.props('aria-expanded="false"')
        self.active = False
        ui.run_javascript(f"document.getElementById({json.dumps(self.launch.html_id)})?.focus()")

    def toggle_minimized(self) -> None:
        self.minimized = not self.minimized
        self.body.set_visibility(not self.minimized)
        self.minimize.props(f'aria-expanded="{str(not self.minimized).lower()}"')
        self.minimize.props(
            "aria-label='Expand Learning Guide'" if self.minimized else "aria-label='Minimize Learning Guide'"
        )
        self.minimize.set_icon("expand_less" if self.minimized else "minimize")

    def forget_position(self) -> None:
        positions = guide_positions()
        positions.pop(self.key, None)
        set_preference("learning_guide_positions", positions)

    def finish(self) -> None:
        self.forget_position()
        self.clear_target()
        self.active = False
        self.panel.set_visibility(False)
        self.launch.props('aria-expanded="false"')
        ui.run_javascript(LESSON_START)

    def next_lesson(self) -> None:
        target = adjacent_lesson(self.guide.lesson, 1, self.path)
        if target is not None:
            self.forget_position()
            self.clear_target()
            ui.navigate.to(lesson_url(target, self.path))

    def tab_changed(self, event: Any) -> None:
        if self.active and event.value != self.guide.sections[self.index].tab:
            self.paused = True
            self.clear_target()
            self.content.refresh()

    async def show(self, index: int) -> None:
        if not 0 <= index < len(self.guide.sections):
            return
        self.index, self.active, self.paused = index, True, False
        self.revision += 1
        revision = self.revision
        section = self.guide.sections[index]
        positions = guide_positions()
        positions[self.key] = section.id
        set_preference("learning_guide_positions", positions)
        self.tabs.set_value(section.tab)
        self.content.refresh()
        found = await ui.run_javascript(
            """return await new Promise(resolve => {
                const revision = REVISION;
                if ((window.__learningGuideRevision || 0) > revision) return resolve(false);
                window.__learningGuideRevision = revision;
                document.querySelectorAll('.learning-guide-target').forEach(e => e.classList.remove('learning-guide-target'));
                const visible = selector => [...document.querySelectorAll(selector)]
                    .find(e => e.getClientRects().length && getComputedStyle(e).visibility !== 'hidden');
                let tries = 0;
                function find() {
                    if (window.__learningGuideRevision !== revision) return resolve(false);
                    const step = visible('.learning-guide-step');
                    const target = visible(TARGET);
                    if (!target || !step || !step.textContent.startsWith(STEP_TITLE)) {
                        if (++tries < 35) return setTimeout(find, 50);
                        return resolve(false);
                    }
                    step.focus({preventScroll: true});
                    const context = visible(CONTEXT) || target;
                    const header = document.querySelector('.q-header');
                    const top = header ? header.getBoundingClientRect().bottom + 20 : 20;
                    window.scrollTo({top: Math.max(0, window.scrollY + context.getBoundingClientRect().top - top), behavior: 'auto'});
                    const box = target.getBoundingClientRect();
                    const panel = visible('.learning-guide');
                    const panelBox = panel?.getBoundingClientRect();
                    const overlaps = panelBox && box.right > panelBox.left && box.left < panelBox.right;
                    const bottom = overlaps && panelBox.top > top + 80 ? panelBox.top - 16 : window.innerHeight - 24;
                    if (box.top < top || box.bottom > bottom)
                        window.scrollTo({top: Math.max(0, window.scrollY + box.top - top), behavior: 'auto'});
                    target.classList.add('learning-guide-target');
                    resolve(true);
                }
                requestAnimationFrame(find);
            });""".replace("REVISION", str(revision)).replace("TARGET", json.dumps(section.target)).replace("CONTEXT", json.dumps(section.context))
            .replace("STEP_TITLE", json.dumps(f"Section {index + 1} of 7")),
            timeout=4,
        )
        if self.revision == revision and not found:
            self.status.set_text("This target is unavailable. Read the written action above, or try Show section again.")
