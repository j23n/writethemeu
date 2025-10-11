# Identity Verification Vision

## Objective
Guarantee that only real, uniquely verified individuals can sign letters and that their constituency is proven—ideally by reusing identities users already hold (e.g., Verimi, BundID, bank login) rather than forcing a new verification flow.

## Core Requirements
- **Proof of personhood:** Ensure each signature is tied to a real individual (no throwaway accounts).
- **Proof of constituency:** Capture verified address (street, PLZ, city) and map it to the correct Wahlkreis / Landtag district.
- **Reusable identity:** Prefer providers where users can consent to sharing existing verified attributes (lower friction than video calls).
- **Evidence retention:** Store cryptographically signed responses or verification references so we can prove the verification later.
- **Expiry / refresh:** Verification should have a validity window (e.g., re-check every 6–12 months or when user updates address).

## Recommended Providers (Germany)

### Identity Wallets (best reuse experience)
- **Verimi** (OAuth2/OIDC)
  - Users already have a Verimi wallet → grant consent → we receive name + address.
  - Supports multiple underlying methods (eID, VideoIdent, bank sources).
- **BundID / BundesIdent** (official government ID)
  - OIDC-based access to Personalausweis attributes via government portal.
  - Gold standard for address proof; onboarding limited to approved use cases.
- **yes® (yes.com)**
  - Bank login to participating institutions; returns bank-verified identity/address via OpenID Connect.
  - No new verification, just consent.
- **Signicat Identity Platform**
  - Aggregator: supports Verimi, yes®, BankID, eIDAS. Useful if expansion beyond Germany is planned.
- **Nect Ident**
  - After an initial automated verification, users can re-share their identity from a wallet.

### Alternative Methods
- **BankIdent / PSD2 providers** (WebID BankIdent, yes®, Deutsche Bank BankIdent)
  - Users log into their bank; returns name/address. High trust, no video.
- **eID solutions (AUTHADA, D-Trust)**
  - NFC-based Personalausweis reading; some provide reusable tokens after first use.
- **VideoIdent (IDnow, WebID VideoIdent, POSTIDENT)**
  - Higher friction; use as fallback when wallet/bank options fail.

## Integration Architecture
1. **Abstraction layer:** Implement a `VerificationProvider` interface with methods like `start_verification(user)` and `handle_callback(payload)`.
2. **Provider adapters:** Build adapters for Verimi, yes®, BundID, etc., each handling OAuth2/OIDC flows, token validation, and attribute extraction.
3. **Verification storage:** Extend `IdentityVerification` to store provider name, verification reference, timestamp, address, and provider response hash/signature.
4. **Constituency mapping:** After receiving address data, run it through the constituency router (GeoJSON-based once available) to attach the exact direct-mandate seat/state.
5. **Expiry handling:** Add `expires_at`—prompt users to re-verify when outdated or on address change.
6. **Audit trail:** Log provider responses; maintain a verification history per user.
7. **Fallback/manual path:** Offer manual verification (moderator-reviewed documents) only if all automated providers fail, clearly flagging such signatures.

## User Flow Blueprint
1. User chooses “Verify identity”.
2. We present available providers (Verimi, yes®, BundID…).
3. User authenticates/consents with chosen provider.
4. Provider redirects back / sends webhook with verification result + attributes.
5. We validate response, persist identity data, and map PLZ → constituency.
6. Signatures now display “Verified constituent” (and reinforce direct mandates with proof).

## Implementation Priorities
- Start with a wallet provider (Verimi or yes®) for minimal friction.
- Add BundID for maximum trust where accessible.
- Abstract architecture so adding Landtag-specific providers later is straightforward.
- Ensure we can reuse the same verification across multiple letters until it expires.

## Outstanding Questions
- Do we need different assurance levels for general signatures vs. direct-mandate proof? (e.g., allow bank login for signing, but require eID for constituency-critical interactions?)
- How to handle users without access to any supported provider? (Manual override / postal verification?)
- Data protection & consent: store only what’s necessary (likely name + address); ensure GDPR-compliant retention policies.

