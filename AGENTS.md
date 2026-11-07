# Lesson implementation workflow

- Complete offline regression checks and real provider-backed live scenarios for the current lesson before proceeding to the next lesson.
- Use bounded, isolated live acceptance runs. Recorded fixtures and injected clients do not count as live verification.
- Exercise the passing workflow and relevant supported live control variants. Keep synthetic negative scenarios offline when the API requires it.
- Report observed outcomes, costs when available, and remaining limitations. If authentication, account access or runtime behavior blocks live acceptance, report the blocker and do not advance to the next lesson.
- The user explicitly requested this live-verification requirement on 3 November 2026.
