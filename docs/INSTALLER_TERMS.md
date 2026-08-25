# Before installing yapper_

The open-source wrapper you don't need to pay for.

No subscription. No separate Python setup. Just install, speak, and yap.

Yapper was vibe-coded with an LLM as a coding contributor, with product
direction and testing by Nimbus.

yapper_ is free and open-source software published by Nimbus under the MIT
License. The installer should display the complete `LICENSE` file and require
the user to continue before installation.

The software is provided without warranty. The installer includes the Python
runtime required by the application; a separate Python installation is not
required.

NVIDIA CUDA acceleration is optional. yapper_ must not install display or CUDA
drivers silently. Systems without a compatible NVIDIA driver use the CPU
fallback.

Speech and Smart Cleanup models are downloaded separately. Third-party model
terms continue to apply. Gemma requires acceptance of Google's Gemma terms
before download and is not licensed under yapper_'s MIT License.

On first launch, the in-app model setup selects Tiny, Medium (Recommended), and
Gemma by default. The user can opt out of any model or skip the setup. Downloads
begin only after the user confirms them; Gemma also requires a Hugging Face
read token after its license has been accepted.

Installed builds store personal state in `%LOCALAPPDATA%\Nimbus\Yapper`.
See `docs/PRIVACY.md` for details.
