# yapper_ 4.0

**Yapper: the open-source wrapper you don't need to pay for.**

Because paying a monthly subscription for a wrapper around great open-source
tools felt ridiculous.

yapper_ is a free, open-source, offline-first Windows dictation application
published by Nimbus. It records from a chosen microphone, transcribes locally
with Faster-Whisper, applies optional cleanup, and inserts the result into the
active application.

**Transparency note:** Yapper was vibe-coded with an LLM as a coding
contributor. Nimbus shaped the idea, product direction, personality, and testing.

Version 4.0 is the clean release baseline. Application resources, personal
data, downloaded models, development tools, and generated release artifacts
are deliberately separated.

## Download for Windows

**[Download the Yapper 4.0 Windows installer](https://drive.google.com/drive/folders/1zj7320R444bluO8H1Z6PfbQ57_kKFGqO?usp=sharing)**

For normal Windows installation, download and run `Yapper-4.0.0-Setup.exe`
from the linked folder. Git and Python are not required.

## Why Yapper exists

Yapper began as a personal attempt to build a free, inspectable alternative to
subscription-based voice-dictation tools such as Wispr Flow. The target was the
same simple interaction—press a hotkey, speak naturally, and receive clean text
in the active app—while keeping speech processing, cleanup, history, and model
choice under the user's control.

It is not a wrapper around a paid service. Faster-Whisper performs local speech
recognition, an explicit rules layer protects commands and important literals,
and optional local Gemma cleanup adds punctuation and structure without trying
to rewrite the speaker's voice. Online formatting providers are optional; the
default workflow remains local and has no subscription requirement.

Yapper is an independent project and is not affiliated with Wispr Flow.

## Project layout

```text
aura_flow/          application package
assets/             read-only packaged resources
docs/               privacy, installer, media, and design documentation
packaging/          Windows executable and installer definitions
tests/              automated regression suite
tools/              development and evaluation utilities
main.py             application and packaged-helper entry point
setup_models.py     transactional speech-model installer
setup_semantic.py   gated Gemma installer
```

Personal data and downloaded models are not part of this tree. Installed builds
use `%LOCALAPPDATA%\Nimbus\Yapper`; portable builds use a `portable.flag` beside
the executable.

## Development

Use 64-bit Python 3.11. Python 3.10 is not supported by the pinned NumPy build.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-semantic.txt
.\.venv\Scripts\python.exe main.py
```

Models are optional at installation time and are downloaded into the separate
user model directory. The app runs on CPU and uses compatible NVIDIA hardware
when CTranslate2 reports CUDA support. Do not install GPU drivers as part of
the application installer.

On first launch, Yapper opens its in-app Downloads page with Tiny, Medium, and
Gemma selected. Users can uncheck any model or skip setup entirely. Medium is
the recommended dictation model. Gemma remains gated by Google's license and a
user-supplied Hugging Face read token, which Yapper uses only for that download.

## Tests

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

## Building and releasing

The `packaging` folder contains the reproducible Windows build scaffolding.
Python is bundled into `Yapper.exe`; end users do not need Python installed.
The generated executable and installer must be tested on a clean Windows 10 or
11 x64 system before release.

Setting the publisher metadata to Nimbus is not a digital signature. Trusted
Authenticode signing requires a valid code-signing certificate and protected
private key supplied during the release build. See the
[Windows code-signing guide](docs/CODE_SIGNING.md) for the practical personal,
open-source, and Store options.

## Licensing

The source code is available under the [MIT License](LICENSE). Dependencies,
downloaded models, and optional media remain subject to their own terms. See
[third-party notices](THIRD_PARTY_NOTICES.md), [privacy](docs/PRIVACY.md), and
[media notice](docs/MEDIA_NOTICE.md).
