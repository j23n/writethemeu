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
2. **Account Management**
   - [ ] Add account deletion option (removes signatures but keeps letters)
   - [ ] Add double opt-in for account creation
3. **UX**
   - [ ] Add letter list sorting by signatures / verified signatures / age
   - [ ] Add filtering based on TopicArea keywords
   - [ ] Remove Kompetenzen info page
   - [ ] Rudimentary branding - color scheme, bootstrap
3. **Identity Verification Integration**
   - [ ] Build provider abstraction and connect to first reusable ID service.
   - [ ] Persist provider response (hash/ID, address) with expiry handling; skip manual verification path.
   - [ ] Determine if providers exist offering login-provider functionality
   - [x] Support self-declared constituency verification with profile management UI.
3. **Letter Authoring UX**
   - [x] Polish HTMX suggestions and representative cards for consistency.
   - [ ] Allow draft auto-save and clearer edit states pre-signature.
   - [ ] Add share buttons and clearer “copy link” prompt on letter detail.
   - [ ] Add minimum letter length of 500 characters.
   - [ ] Make it very clear that letters cannot be changed after publication
   - [ ] Make it very clear that you can remove your signature from a letter, but not the letter itself
6. **Localization & Accessibility**
   - [ ] Complete en/de translation coverage for all templates and forms.
   - [ ] Ensure forms, buttons, and suggestions meet accessibility best practices.
7. **Deployment Readiness**
   - [ ] Production config (secrets, logging, error tracking, email backend).
   - [ ] Deploy to VPS - static media, unicorn, nginx, docker
   - [ ] Health checks with Tinylytics
   - [ ] Add caching
8. **Feedback & Analytics**
   - [ ] Add feedback/contact channel for users.
   - [ ] Add simple analytics app. Middleware that keeps track of impressions -> build this so it can easily be moved into a separate repo
9. **Testing & QA**
   - [ ] Expand automated test coverage (matching, verification, export workflow).
   - [ ] QA checklist for matching accuracy, verification flow, admin exports.

## Out of Scope for MVP
- Local municipality reps, party-wide campaigns.
- In-browser letter editing with collaboration.
- Advanced analytics or CRM tooling.
- Multiple identity providers (beyond initial integration).
- Expert matching based on representative metadata keywords
- Biography providers, display on representative detail view and extract keywords for matching
