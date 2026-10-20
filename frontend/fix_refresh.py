"""Task 26 - make the detail pane clear after a verdict."""

from pathlib import Path

p = Path("src/CaseQueue.jsx")
t = p.read_text(encoding="utf-8")

old = """  async function verdict(value) {
    setBusy(true)
    try {
      await api.submitVerdict(caseRef, value, notes)
      await load()
      onChanged()
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }"""

new = """  async function verdict(value) {
    setBusy(true)
    try {
      await api.submitVerdict(caseRef, value, notes)
      // Reload THIS case first so the pane shows the closed state,
      // then refresh the queue. Doing it the other way round leaves
      // `selected` pointing at a case that has just left the open
      // list, and the detail never updates.
      await load()
      await onChanged()
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }"""

if old in t:
    t = t.replace(old, new)
    print("verdict handler patched")
else:
    print("WARNING: verdict handler not found as expected")

# The real fix: re-select when the chosen case is gone from the list.
old2 = """      if (data.cases?.length && !data.cases.find((c) => c.case_ref === selected)) {
        setSelected(data.cases[0].case_ref)
      }"""

new2 = """      // If the selected case left this list (a verdict closed it),
      // move to the next one rather than showing a stale pane.
      const stillHere = data.cases?.find((c) => c.case_ref === selected)
      if (!stillHere) {
        setSelected(data.cases?.length ? data.cases[0].case_ref : null)
      }"""

if old2 in t:
    t = t.replace(old2, new2)
    print("re-selection patched")
else:
    print("WARNING: selection block not found as expected")

p.write_text(t, encoding="utf-8")
print("bytes:", p.stat().st_size)