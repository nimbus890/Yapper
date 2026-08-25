# Privacy and local storage

yapper_ is offline-first. By default, recordings, transcripts, settings,
personalization, and usage history remain on the user's computer.

Installed builds store writable state under:

`%LOCALAPPDATA%\Nimbus\Yapper\`

The folders are separated by purpose:

- `data` — settings, encrypted API credentials, history, and local metrics;
- `models` — speech and optional Smart Cleanup model downloads;
- `logs` — release diagnostics that contain no API keys.

A portable build is enabled by placing `portable.flag` beside `Yapper.exe`.
That build stores its data and models beside the executable so the entire
folder can be moved together.

An online cleanup provider is contacted only after a user explicitly enables
and configures it. Model downloads contact the model publisher. Feedback and
testing exports are created or sent only after explicit user action.

The Feedback window's Send data tab creates a readable `.txt` report only after
the user chooses a scope, reviews it, and confirms. Yapper then opens the
published Google Form; the user must sign in and upload the file themselves.
Nothing is uploaded automatically.

API credentials are encrypted with Windows DPAPI for the current Windows user.
They must never be copied into source control, diagnostics, or release files.
