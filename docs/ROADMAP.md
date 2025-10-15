# MVP Roadmap

## Mission
Empower citizens to participate in democracy by writing impactful open letters to the representatives best positioned to act, and by allowing others to rally behind those letters with signatures. Verified identities add credibility; when a letter clears a signature threshold, we commit to printing, signing, and delivering it to the relevant office.

## MVP Feature Set
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
   - Integrate one third-party provider (e.g., Verimi or yes®) via OAuth2/OIDC to pull verified name.
   - Store attestation + expiry; store only constituency foreign keys (addresses never persisted).
   - Users without verification can still sign, flagged as "unverified."
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

## Implementation Phases

### Phase 1: Foundation & Core Letter Flow
**Core functionality for writing, publishing, and signing letters**

- [x] Account Management (Completed: 2024-10-11, pre-roadmap work)
  - Email/password registration & login
  - Password reset functionality
  - Account deletion
  - Double opt-in email verification

- [x] Representative Data Infrastructure (Completed: 2024-10-14, PR #4)
  - Representative metadata sync (photos, committees, focus areas)
  - Parliament/Term/Constituency models
  - Committee-to-topic automatic mapping
  - Abgeordnetenwatch API integration
  - Support for EU, Bundestag, and Landtag levels

- [x] Letter Authoring & Publishing (Completed: 2024-10-11, pre-roadmap work)
  - Draft and publish open letters
  - Auto-sign on publish
  - Letter detail page with full content
  - HTMX-based representative suggestions

- [x] Signature Flow (Completed: 2024-10-11, pre-roadmap work)
  - One-click signing for logged-in users
  - Signature display with verification badges
  - Basic signature counting

- [x] Topic Matching (Completed: 2024-10-11, pre-roadmap work)
  - TopicArea taxonomy with keyword matching
  - Topic analysis for letters
  - Committee-to-topic mapping

- [ ] Draft Management
  - Save unpublished drafts
  - Edit drafts before publishing
  - Draft list in user profile
  - Delete drafts

### Phase 2: Accurate Constituency Matching
**Geographic precision for representative recommendations**

- [x] Geocoding Infrastructure (Completed: 2024-10-15, pre-roadmap work)
  - OSM Nominatim API integration with rate limiting
  - AddressGeocoder service
  - GeocodeCache model for performance
  - Address → lat/lng conversion

- [x] Wahlkreis Boundary Lookup (Completed: 2024-10-15, pre-roadmap work)
  - WahlkreisLocator using Shapely for point-in-polygon
  - GeoJSON boundary data loading and caching
  - Coordinate → Wahlkreis mapping

- [x] Integration & Validation (Completed: 2025-10-15, privacy-profile branch)
  - Integrate geocoding into profile (HTMX address search)
  - Privacy-first: addresses used for geocoding, never persisted
  - Test with real German addresses (Berlin, etc.)
  - Handle edge cases (geocoding failures, invalid addresses)
  - GeocodeCache for performance (rate limit compliance)

### Phase 3: Internationalization
**Multi-language support with German as primary**

- [x] i18n Infrastructure (Completed: 2024-10-14, PR #2)
  - Django i18n configuration (German/English)
  - All templates wrapped with translation tags
  - German and English .po files generated
  - Language switcher component
  - Translation management command

- [ ] Content Refinement
  - Audit all user-facing strings for completeness
  - Review German tone/voice consistency
  - Ensure error messages are clear and helpful
  - Complete any missing translations

### Phase 4: User Experience & Polish
**Visual design and usability improvements**

- [ ] Design System
  - Define color palette (gov.uk-inspired)
  - Typography system
  - CSS design system with variables
  - Simple wordmark/logo

- [ ] Letter Discovery
  - Sorting controls (newest, most signatures, most verified)
  - TopicArea filtering (multi-select)
  - Improved letter card design
  - Empty states with helpful CTAs
  - Mobile responsive improvements

- [ ] Letter Authoring Experience
  - Character counter (500 char minimum)
  - Prominent immutability warning
  - Representative suggestion reasoning display
  - Preview step before publishing
  - Improved auto-signature confirmation

- [ ] Sharing & Engagement
  - Prominent "Copy link" button
  - Social share buttons (Twitter, Bluesky)
  - Improved verified/unverified badges
  - Enhanced report functionality

### Phase 5: Content & Documentation
**Landing pages, legal docs, and transparency**

- [ ] Public-Facing Content
  - Compelling homepage with mission and stats
  - "How It Works" page explaining matching
  - FAQ section
  - Example letters or testimonials

- [ ] Legal & Privacy
  - Privacy Policy (GDPR-compliant)
  - Terms of Service
  - Impressum (German legal requirement)
  - Cookie consent if needed

### Phase 6: Production Deployment
**Infrastructure and monitoring**

- [ ] VPS Infrastructure
  - Provision VPS with cloud-init
  - Configure Gunicorn + Nginx
  - SSL/TLS certificates (Let's Encrypt)
  - Static file serving

- [ ] Production Configuration
  - Environment-based settings (secrets, database)
  - Email backend (SMTP/SendGrid/SES)
  - Error tracking (Sentry/Rollbar)
  - Structured logging

- [ ] Deployment Automation
  - Deployment script (rsync/git-based)
  - Rollback procedure
  - Deployment documentation
  - Health checks and monitoring

### Phase 7: Testing & Launch Readiness
**Comprehensive validation before launch**

- [ ] Automated Testing
  - End-to-end flow tests (Register → Create → Publish → Sign)
  - Geocoding and matching tests with real addresses
  - Email flow tests
  - Edge case testing (border areas, ambiguous data)

- [ ] User Acceptance Testing
  - Manual testing of complete flows
  - Multi-device and browser testing
  - Link and form verification
  - Content proofreading

- [ ] Security & Performance
  - Load testing (concurrent users)
  - Security review (XSS, CSRF, SQL injection)
  - Form validation audit
  - Admin permissions review

- [ ] Launch Preparation
  - Launch checklist creation
  - Demo script preparation
  - Analytics/monitoring dashboards
  - Initial outreach planning

## Future Work
**Features deferred until post-MVP**

- Third-party identity verification (Verimi, yes®)
- Advanced analytics and feedback systems
- Draft auto-save functionality
- Advanced admin moderation tools
- Additional language support beyond German/English

## Out of Scope for MVP
- Local municipality reps, party-wide campaigns.
- In-browser letter editing with collaboration.
- Advanced analytics or CRM tooling.
- Multiple identity providers (beyond initial integration).
- Expert matching based on representative metadata keywords
- Biography providers, display on representative detail view and extract keywords for matching
