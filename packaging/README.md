# Windows release process

`Yapper.spec` builds a 64-bit, folder-based `Yapper.exe` with its private Python
runtime. `installer.iss` wraps that folder in a per-user Inno Setup installer.

Requirements:

- 64-bit Python 3.11 with `requirements-build.txt` installed;
- Inno Setup 6 (`iscc.exe`) for the installer;
- Windows SDK `signtool.exe` and a trusted code-signing certificate for public
  Authenticode signing.

Inno Setup's current license permits non-commercial use without charge, but a
commercial Nimbus release requires an Inno Setup commercial license (or a
different installer tool). This is separate from yapper_'s MIT License.

Run `packaging\build.ps1`. Pass `-CertificateThumbprint` only on the protected
release machine that has access to Nimbus's signing certificate. The script
never creates or embeds a private key.

The installer displays the MIT License and pre-installation information. It
installs per user, so model/data writes under Local AppData do not require
administrator access.

Before publishing, test installation, uninstall, startup registration,
microphone access, CPU fallback, optional CUDA use, every model download, and
upgrade behavior on clean Windows 10 and 11 x64 systems.
