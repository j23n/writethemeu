# MVP Vision

## Mission
Empower citizens to participate in democracy by writing impactful open letters to the representatives best positioned to act, and by allowing others to rally behind those letters with signatures. Verified identities add credibility; when a letter clears a signature threshold, we commit to printing, signing, and delivering it to the relevant office.

## Core Feature Set
1. **Accounts & Profiles**
   - Email/password registration & login.
   - Profile page showing authored letters, signed letters, and verification status.
2. **Representative Directory**
   - EU, Bundestag, Landtag members with photo, party, mandate mode, committee roles, Abgeordnetenwatch links.
   - Exposed via detail view and reusable UI card.
3. **Letter Authoring & Publishing**
   - Draft open letters, auto-suggest recipients based on title + PLZ.
   - Auto-sign on publish; allow editing until first signature.
   - Letter detail page shows full content, representative card, signature stats.
4. **Recommendation Engine**
   - PLZ → constituency router (direct/state/federal) using official boundary data.
   - Topic analysis highlighting likely responsible level and committee working areas.
   - Explain why a representative is recommended, surface relevant tags, show similar letters.
5. **Signature Flow**
   - One-click signing for logged in users; prompt login otherwise.
   - Badges for verified vs unverified signatures, count constituents distinctly.
   - Social sharing (link copy, optional Twitter/Bluesky share).
6. **Identity Verification (Optional)**
   - Integrate one third-party provider (e.g., Verimi or yes®) via OAuth2/OIDC to pull verified name/address.
   - Store attestation + expiry; map address to constituency for direct mandates.
   - Users without verification can still sign, flagged as “unverified.”
7. **Signature Threshold & Fulfilment**
   - Configurable threshold per letter or representative type.
   - Admin view showing letters reaching milestones, export letter + supporters for printing/mailing.
8. **Admin & Moderation**
   - Admin dashboard to inspect letters, representatives, signatures, verification status, and signature thresholds.
   - Ability to disable inappropriate letters, resend sync, run exports.
9. **Landing & Discovery**
   - Public homepage summarising mission, stats, featured letters.
   - Browse letters and representatives without login.
10. **Documentation & Transparency**
    - Public “How it works” page, privacy policy, terms.
    - README covering setup, architecture, deployment.

## MVP To-Do List
1. **Constituency & Matching Foundations**
   - [ ] Replace PLZ prefix heuristic with Wahlkreis GeoJSON (Bundestag) + state-level boundaries; build router service.
   - [x] Expand `TopicArea` taxonomy, add NLP/keyword scoring, and present explanations.
   - [x] Enrich representative metadata with committee focus, responsiveness, photos.
   - [x] Scope recommendation engine to relevant parliaments using constituency + topic competence.
2. **Identity Verification Integration**
   - [ ] Build provider abstraction and connect to first reusable ID service.
   - [ ] Persist provider response (hash/ID, address) with expiry handling; skip manual verification path.
   - [x] Support self-declared constituency verification with profile management UI.
3. **Letter Authoring UX**
   - [x] Polish HTMX suggestions and representative cards for consistency.
   - [ ] Allow draft auto-save and clearer edit states pre-signature.
   - [ ] Add share buttons and clearer “copy link” prompt on letter detail.
4. **Signature Threshold Workflow**
   - [ ] Configurable thresholds per representative type, admin notification when reached.
   - [ ] Export letters and supporters as PDF/CSV; mark fulfilment status (printed/sent).
5. **Admin Tooling**
   - [ ] Dedicated dashboard or extended Django admin for analytics, moderation, verification oversight.
   - [ ] Simple stats (letters per day, signatures per letter), filters for unverified vs verified.
6. **Localization & Accessibility**
   - [ ] Complete en/de translation coverage for all templates and forms.
   - [ ] Ensure forms, buttons, and suggestions meet accessibility best practices.
7. **Deployment Readiness**
   - [ ] Production config (secrets, logging, error tracking, email backend).
   - [ ] Static/media hosting (e.g., S3 + CDN), WSGI deployment (Fly.io/Heroku/etc.).
   - [ ] Health checks, Sentry or equivalent for monitoring.
8. **Feedback & Analytics**
   - [ ] Add feedback/contact channel for users.
   - [ ] Track key funnel metrics (letter creation, signature conversion).
9. **Testing & QA**
   - [ ] Expand automated test coverage (matching, verification, export workflow).
   - [ ] QA checklist for matching accuracy, verification flow, admin exports.

## Out of Scope for MVP
- Local municipality reps, party-wide campaigns.
- In-browser letter editing with collaboration.
- Advanced analytics or CRM tooling.
- Multiple identity providers (beyond initial integration).
