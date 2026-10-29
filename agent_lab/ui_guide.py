"""A written, student-controlled Learning Guide. No exercise or SDK calls live here."""

import json
from typing import Any

from nicegui import ui

from agent_lab.lesson_guide import LearningGuide, adjacent_lesson, lesson_url
from agent_lab.ui_learning import set_preference, stored

GUIDE_CSS = """
.learning-guide {
    position: fixed; right: 20px; bottom: 20px; z-index: 2500;
    width: 410px; max-width: calc(100vw - 24px); max-height: min(56vh, 680px);
    background: #ffffff; color: #17294a; border: 2px solid #2563eb;
    border-radius: 16px; box-shadow: 0 12px 40px #0003;
    padding: 16px; gap: 12px; font-size: 18px; line-height: 1.5;
}
.learning-guide-heading { font-size: 21px; font-weight: 750; }
.learning-guide-body { overflow-y: auto; overflow-wrap: anywhere; min-height: 0; width: 100%; padding: 3px; }
.learning-guide-footer { flex-shrink: 0; width: 100%; }
.learning-guide > .nicegui-row { flex-shrink: 0; }
.learning-guide .q-btn { white-space: normal; min-height: 44px; font-size: 16px; }
.learning-guide .q-btn:focus-visible { outline: 3px solid #1d4ed8; outline-offset: 3px; }
.learning-guide .q-field { max-width: 100%; }
.learning-guide .q-field__native, .learning-guide .q-field__label { font-size: 17px; }
.learning-guide .guide-primary { --q-primary: #1d4ed8; }
.learning-guide-step { font-weight: 700; font-size: 20px; }
.learning-guide-action { background: #eff6ff; color: #173b63; padding: 12px; border-radius: 10px; }
.learning-guide-status { font-size: 16px; color: #475569; }
/* Layered !important declarations outrank unlayered ones. NiceGUI orders its
   overrides layer before quasar_importants, so this beats Quasar's .no-outline. */
@layer overrides {
    body.learning-guide-active .learning-guide-target {
        outline: 3px solid #dc2626 !important; outline-offset: 5px; border-radius: 5px;
    }
}
.learning-guide-target.nicegui-markdown > :first-child { margin-top: 0; }
.learning-guide-target.nicegui-markdown > :last-child { margin-bottom: 0; }
.learning-guide-target:not(button) {
    max-height: var(--learning-guide-target-height); overflow: auto; overscroll-behavior: contain;
    flex-shrink: 0;
}
.guide-scroll-target .nicegui-code, .guide-scroll-target .tour-code { flex-shrink: 0; }
body.learning-guide-active .q-page { padding-bottom: calc(100vh + 32px); }
.learning-guide-actions { width: 100%; gap: 8px; align-items: stretch; }
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
    window.__learningGuideCleanup?.();
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
INITIAL_LESSON_START = """
if (document.activeElement === document.body &&
    !document.querySelector('.learning-guide')?.getClientRects().length) {
""" + LESSON_START + "\n}"


def guide_positions() -> dict[str, str]:
    value = stored("learning_guide_positions", {})
    return dict(value) if isinstance(value, dict) else {}


async def _locate_target(script: str) -> bool:
    """A busy browser must leave a recoverable guide, not an unhandled UI timeout."""
    try:
        return bool(await ui.run_javascript(script, timeout=8))
    except TimeoutError:
        return False


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
                self.footer = ui.column().classes("learning-guide-footer gap-0")
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
                ui.label("This written guide has no recorded Python narration.").classes(
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
                if self.paused else "Locating this section's highlighted content..."
            ).classes("learning-guide-status").props('role="status" aria-live="polite"')
            ui.button("Show section", icon="my_location", on_click=lambda: self.show(self.index)).props("outline")

        @ui.refreshable
        def navigation() -> None:
            if not self.active:
                return
            with ui.row().classes("learning-guide-actions"):
                previous = ui.button("Previous section", icon="chevron_left", on_click=lambda: self.show(self.index - 1))
                previous.set_enabled(self.index > 0)
                if self.index < len(self.guide.sections) - 1:
                    ui.button("Next section", icon="chevron_right", on_click=lambda: self.show(self.index + 1))
                else:
                    ui.button("Finish tour", icon="done", on_click=self.finish)
                    if adjacent_lesson(self.guide.lesson, 1, self.path) is not None:
                        ui.button("Next lesson →", on_click=self.next_lesson).classes("guide-primary")
        self.navigation = navigation
        with self.footer:
            navigation()

        self.content = content
        with self.body:
            content()

    def open(self) -> None:
        self.panel.set_visibility(True)
        self.launch.props('aria-expanded="true"')
        self.minimized = False
        self.body.set_visibility(True)
        self.footer.set_visibility(True)
        self.minimize.props("aria-label='Minimize Learning Guide' aria-expanded='true'")
        self.minimize.set_icon("minimize")
        self.content.refresh()
        self.navigation.refresh()
        ui.run_javascript(
            "let tries = 0; requestAnimationFrame(function focusGuide() {"
            f"const panel = document.getElementById({json.dumps(self.panel.html_id)});"
            "if (panel?.getClientRects().length) {"
            "panel.focus({preventScroll: true});"
            "} else if (++tries < 30) requestAnimationFrame(focusGuide); });"
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
        self.footer.set_visibility(not self.minimized)
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
        self.navigation.refresh()
        found = await _locate_target(
            """return await new Promise(resolve => {
                const revision = REVISION;
                if ((window.__learningGuideRevision || 0) > revision) return resolve(false);
                window.__learningGuideCleanup?.();
                window.__learningGuideRevision = revision;
                document.querySelectorAll('.learning-guide-target').forEach(e => e.classList.remove('learning-guide-target'));
                const visible = selector => [...document.querySelectorAll(selector)]
                    .find(e => e.getClientRects().length && getComputedStyle(e).visibility !== 'hidden');
                const deadline = performance.now() + 5000;
                function find() {
                    if (window.__learningGuideRevision !== revision) return resolve(false);
                    const step = visible('.learning-guide-step');
                    const target = visible(TARGET);
                    if (!target || !step || !step.textContent.startsWith(STEP_TITLE)
                        || target.closest('[class*="-enter-active"], [class*="-leave-active"]')) {
                        if (performance.now() < deadline) return setTimeout(find, 50);
                        return resolve(false);
                    }
                    const panel = visible('.learning-guide');
                    const header = document.querySelector('.q-header');
                    const body = panel.querySelector('.learning-guide-body');
                    body.scrollTop = 0;
                    step.focus({preventScroll: true});
                    document.body.classList.add('learning-guide-active');
                    target.classList.add('learning-guide-target');
                    let frame = 0;
                    function align() {
                        if (!target.isConnected || window.__learningGuideRevision !== revision) return;
                        const top = (header?.getBoundingClientRect().bottom || 0) + 20;
                        // Reserve the complete target above the panel, including its outline.
                        const bottom = Math.min(panel.getBoundingClientRect().top - 20, innerHeight - 20);
                        const available = Math.max(64, bottom - top);
                        const before = target.getBoundingClientRect();
                        // Width is stable when height is capped. A height-based scale can
                        // oscillate on rounded pixels and repeatedly pull the page back.
                        const scale = target.offsetWidth ? before.width / target.offsetWidth : 1;
                        target.style.setProperty('--learning-guide-target-height', `${available / scale}px`);
                        const box = target.getBoundingClientRect();
                        const context = visible(CONTEXT) || target;
                        const contextBox = context.getBoundingClientRect();
                        const start = contextBox.top <= box.top && box.bottom - contextBox.top <= available
                            ? contextBox.top : box.top;
                        window.scrollTo({top: Math.max(0, scrollY + start - top), behavior: 'instant'});
                    }
                    function schedule() {
                        cancelAnimationFrame(frame);
                        frame = requestAnimationFrame(align);
                    }
                    const observer = new ResizeObserver(schedule);
                    observer.observe(target);
                    observer.observe(panel);
                    if (header) observer.observe(header);
                    // Vue reapplies a button's server-owned classes when Run is disabled
                    // or enabled. Restore only our temporary marker, without scrolling.
                    const classes = new MutationObserver(() => {
                        if (window.__learningGuideRevision === revision && target.isConnected
                            && !target.classList.contains('learning-guide-target'))
                            target.classList.add('learning-guide-target');
                    });
                    classes.observe(target, {attributes: true, attributeFilter: ['class']});
                    window.addEventListener('resize', schedule);
                    window.visualViewport?.addEventListener('resize', schedule);
                    window.__learningGuideCleanup = () => {
                        cancelAnimationFrame(frame);
                        observer.disconnect();
                        classes.disconnect();
                        window.removeEventListener('resize', schedule);
                        window.visualViewport?.removeEventListener('resize', schedule);
                        target.style.removeProperty('--learning-guide-target-height');
                        document.body.classList.remove('learning-guide-active');
                    };
                    align();
                    // Vue tab contents and font metrics can settle on the following frame.
                    schedule();
                    resolve(true);
                }
                requestAnimationFrame(find);
            });""".replace("REVISION", str(revision)).replace("TARGET", json.dumps(section.target)).replace("CONTEXT", json.dumps(section.context))
            .replace("STEP_TITLE", json.dumps(f"Section {index + 1} of 7")),
        )
        if self.revision == revision:
            self.status.set_text(
                "The outlined element belongs to this section." if found else
                "This target is unavailable. Read the written action above, or try Show section again."
            )
