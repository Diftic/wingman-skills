"""Local human-only update controls. No approval endpoint or AI tool exists."""

from pathlib import Path

from .updates import UpdateManager


def show_review(runtime_directory, url=None):
    # Imported only by the explicitly launched CLI command, never by Wingman.
    import tkinter as tk
    from tkinter import messagebox, scrolledtext, ttk

    manager = UpdateManager(Path(runtime_directory) / "instructions", url)
    window = tk.Tk()
    window.title("Star Citizen Log Reader — instruction updates")
    window.geometry("900x600")
    frame = ttk.Frame(window, padding=18)
    frame.pack(fill="both", expand=True)
    ttk.Label(frame, text="Reading instructions", font=("Segoe UI", 16)).pack(
        anchor="w"
    )
    ttk.Label(frame, text="Updates take effect the next time the skill starts.").pack(
        anchor="w", pady=6
    )
    content = scrolledtext.ScrolledText(frame, height=16, wrap="word")
    content.pack(fill="both", expand=True)
    buttons = ttk.Frame(frame)
    buttons.pack(fill="x", pady=12)
    shown_digest = None
    shown_source = None
    shown_generation = None
    shown_rollback = None

    def refresh():
        nonlocal shown_digest, shown_source, shown_generation, shown_rollback
        status = manager.status()
        shown_digest = status.get("sha256")
        shown_source = status.get("candidate_source_url")
        shown_generation = status.get("source_generation")
        shown_rollback = status.get("rollback_sha256")
        lines = [
            "Runtime folder: " + status["runtime_directory"],
            "Update publisher: " + (status.get("source_url") or "Not configured"),
            "",
            "Active version: " + status.get("active_version", "unknown"),
            "Scheduled version: " + status.get("staged_version", "None"),
            "Rollback target: " + status.get("rollback_version", "unknown"),
        ]
        if status.get("staged_sha256"):
            lines += ["Scheduled change: " + (status.get("staged_kind") or "unknown")]
            if status.get("staged_source_url"):
                lines += ["Scheduled publisher: " + status["staged_source_url"]]
        if status.get("rollback_fallback_reason"):
            lines += [status["rollback_fallback_reason"]]
        if shown_digest:
            lines += [
                "Available version: " + status["candidate_version"],
                "Available publisher: " + (shown_source or "Unknown; download again"),
                "Requires reader: " + status["minimum_reader_version"],
                "Qualified game builds: "
                + (", ".join(status["verified_game_builds"]) or "Not yet qualified"),
                "",
                status["release_notes"],
            ]
        else:
            lines += ["No downloaded update is waiting for review."]
        if status.get("staged_sha256"):
            lines += ["", "An approved change is waiting for the next startup."]
        if status.get("skipped"):
            lines += [
                "",
                "You skipped this version. Newer versions will still be offered.",
            ]
        if status.get("notice"):
            lines += ["", status["notice"]]
        if status.get("error"):
            lines += ["", status["error"]]
        content.configure(state="normal")
        content.delete("1.0", "end")
        content.insert("1.0", "\n".join(lines))
        content.configure(state="disabled")
        update.configure(state="normal" if shown_digest else "disabled")
        skip.configure(state="normal" if shown_digest else "disabled")
        cancel.configure(state="normal" if status.get("staged_sha256") else "disabled")

    def action(which):
        try:
            if which == "approve":
                manager.approve(
                    shown_digest,
                    source_url=shown_source,
                    source_generation=shown_generation,
                )
                messagebox.showinfo(
                    "Update approved",
                    "It will be activated at the next skill startup.",
                    parent=window,
                )
            elif which == "cancel":
                manager.cancel()
            elif which == "skip":
                manager.skip(shown_digest)
            else:
                result = manager.rollback(expected_sha256=shown_rollback)
                messagebox.showinfo(
                    "Rollback scheduled",
                    (
                        result.get("fallback_reason")
                        or "The previous instructions will be restored"
                    )
                    + " at the next skill startup.",
                    parent=window,
                )
            refresh()
        except (OSError, ValueError) as exc:
            refresh()
            messagebox.showerror(
                "Update unavailable",
                str(exc)
                + "\nThe display has been refreshed. Review it before clicking again.",
                parent=window,
            )

    update = ttk.Button(
        buttons, text="Update next startup", command=lambda: action("approve")
    )
    update.pack(side="left")
    ttk.Button(buttons, text="Later", command=window.destroy).pack(side="left", padx=6)
    skip = ttk.Button(buttons, text="Skip this version", command=lambda: action("skip"))
    skip.pack(side="left")
    cancel = ttk.Button(
        buttons, text="Cancel scheduled update", command=lambda: action("cancel")
    )
    cancel.pack(side="left", padx=6)
    ttk.Button(buttons, text="Roll back", command=lambda: action("rollback")).pack(
        side="right"
    )
    refresh()
    window.mainloop()
