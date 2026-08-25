# Windows code signing

The current Yapper 4.0 installer is intentionally marked **unsigned**. Its
Nimbus file metadata is not a trusted digital signature. Windows may therefore
show an Unknown publisher or SmartScreen warning when the installer is
downloaded from the internet.

Do not use a self-signed certificate for public releases. It is useful only on
computers where that certificate has been manually trusted and does not solve
the warning for ordinary users.

## Practical signing paths

1. **SignPath Foundation for qualifying open-source projects.** This managed
   program is free, but the project must apply and meet its open-source,
   maintenance, privacy, repository, and reproducible-build requirements. The
   displayed certificate publisher is SignPath Foundation. Yapper's separately
   licensed cover media should be disclosed during the application because it
   may affect eligibility. See <https://signpath.org/>.
2. **A paid organization-validated certificate.** A public certificate
   authority verifies the legal person or organization responsible for the
   software. The verified legal name—not an unregistered nickname—is used as
   the trusted publisher. The certificate is normally supplied through a
   hardware token or managed signing service.
3. **Microsoft Store MSIX distribution.** Microsoft signs accepted MSIX
   packages without requiring the developer to buy a certificate, but Yapper
   would need a separate MSIX packaging and Store-submission pass. See
   <https://learn.microsoft.com/windows/apps/package-and-deploy/code-signing-options>.

The reproducible Windows build accepts a certificate thumbprint on a protected
release machine. It signs both `Yapper.exe` and the final installer with SHA-256
and an RFC 3161 time stamp. Private keys and certificate passwords must never be
committed to this repository.
