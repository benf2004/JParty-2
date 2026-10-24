# Public Mac signing certificates

These DER X.509 files contain public certificates only. The private signing key
remains in macOS Keychain and the encrypted GitHub Actions `.p12` secret.

- `developer-id-application.cer`: JParty's Developer ID Application certificate,
  matched to the existing signing key using the CSR. Expires February 1, 2027.
- `DeveloperIDCA.cer` and `DeveloperIDG2CA.cer`: Apple Developer ID intermediate
  certificates downloaded from <https://www.apple.com/certificateauthority/>.

The build imports these into its temporary keychain without changing trust
settings, then requires the exact leaf certificate to appear as a valid signing
identity with a matching private key. Existing certificates in a `.p12` are
allowed; only the intended Developer ID certificate is used to sign JParty.

When renewing, replace the public leaf certificate and update the `.p12` secret
if using a new private key. Never put `.p12`, `.p8`, or private-key files here.
