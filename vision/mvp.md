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

## 1-Month Sprint to 39C3 (December 2024)

### **Week 1-2: Core Functionality** (Days 1-10)

#### Track 1: Accurate Constituency Matching (Days 1-5) ⚠️ CRITICAL
**Day 1: OSM Nominatim Integration**
- [ ] Set up OSM Nominatim API client (requests-based, with rate limiting)
- [ ] Add address geocoding service (`AddressGeocoder`)
- [ ] Cache geocoding results in database to minimize API calls
- [ ] Write tests for address → lat/lng conversion

**Day 2: GeoJSON Point-in-Polygon Lookup**
- [ ] Download full Bundestag Wahlkreis GeoJSON (via existing management command)
- [ ] Build `WahlkreisLocator` using shapely for point-in-polygon
- [ ] Load GeoJSON into memory at startup (or cache in Redis)
- [ ] Test coordinate → Wahlkreis lookup with sample points

**Day 3: Integration & Service Layer**
- [ ] Replace `ConstituencyLocator` with new address-based lookup
- [ ] Update `LocationContext` to accept full addresses
- [ ] Maintain PLZ prefix fallback for partial data
- [ ] Add comprehensive error handling and logging

**Day 4: Representative Matching Validation**
- [ ] Test matching with 20 real German addresses
- [ ] Verify direct representatives are correctly suggested
- [ ] Test topic + geography combined matching
- [ ] Document matching algorithm for transparency

**Day 5: Performance & Edge Cases**
- [ ] Add caching layer for expensive operations
- [ ] Handle border constituencies and ambiguous addresses
- [ ] Performance test with 100+ concurrent requests
- [ ] Add monitoring/logging for matching accuracy

#### Track 2: UX Polish (Days 3-8)

**Day 3-4: Gov.uk-Inspired Branding**
- [ ] Define color palette (inspired by gov.uk: blues, blacks, whites)
- [ ] Choose typography (gov.uk uses: Transport/Arial for headings, system fonts for body)
- [ ] Create CSS design system with variables
- [ ] Update base template with new styles
- [ ] Design simple wordmark/logo

**Day 5-6: Letter List Improvements**
- [ ] Add sorting controls (newest, most signatures, most verified)
- [ ] Add TopicArea filtering (multi-select chips)
- [ ] Improve letter card design (hierarchy, spacing, affordances)
- [ ] Add empty states with helpful CTAs
- [ ] Mobile responsive improvements

**Day 6-7: Letter Authoring Flow**
- [ ] Add character counter (500 char minimum)
- [ ] Add prominent immutability warning before publish
- [ ] Show representative suggestion reasoning
- [ ] Add preview step before publishing
- [ ] Improve auto-signature confirmation messaging

**Day 7-8: Letter Detail & Sharing**
- [ ] Add prominent "Copy link" button with visual feedback
- [ ] Add social share buttons (Twitter, Bluesky with pre-filled text)
- [ ] Clarify signature removal instructions
- [ ] Improve verified/unverified signature badges
- [ ] Polish report button and modal

#### Track 3: Localization Foundation (Days 6-8)

**Day 6-7: Django i18n Setup**
- [ ] Wrap all strings in `gettext()` / `_()` calls
- [ ] Generate German .po files
- [ ] Add language switcher infrastructure (even if only DE works)
- [ ] Document translation workflow

**Day 8: Content Audit**
- [ ] Audit templates for hardcoded strings
- [ ] Review German tone/voice consistency
- [ ] Ensure error messages are clear and helpful
- [ ] Proofread all user-facing content

#### Track 4: Automated Testing (Days 8-10)

**Day 8: Integration Tests**
- [ ] Test full flow: Register → Create Letter → Suggestions → Publish → Sign
- [ ] Test with 10 real German addresses
- [ ] Test with 5 different topics
- [ ] Test email flows (registration, password reset)

**Day 9: Matching Tests**
- [ ] Unit tests for geocoding service
- [ ] Unit tests for GeoJSON lookup
- [ ] Integration tests for address → representative matching
- [ ] Test edge cases (border areas, ambiguous addresses)

**Day 10: System Tests**
- [ ] Browser automation tests (Playwright/Selenium)
- [ ] Mobile responsive tests
- [ ] Performance tests (response times, concurrent users)
- [ ] Create bug fix punch list

### **Week 3-4: Deployment & Polish** (Days 11-20)

#### Track 5: Production Deployment (Days 11-14)

**Day 11-12: VPS Setup**
- [ ] Provision VPS with cloud-init template
- [ ] Configure Gunicorn + Nginx
- [ ] Set up SSL/TLS certificates (Let's Encrypt)
- [ ] Configure static file serving

**Day 13: Production Configuration**
- [ ] Environment-based settings (secrets, database)
- [ ] Configure email backend (SMTP/SendGrid/SES)
- [ ] Set up error tracking (Sentry/Rollbar)
- [ ] Configure logging (structured logs)

**Day 14: Deployment Automation**
- [ ] Create deployment script (simple rsync/git pull based)
- [ ] Test rollback procedure
- [ ] Document deployment process
- [ ] Set up basic monitoring/health checks

#### Track 6: Content & Documentation (Days 15-17)

**Day 15-16: Landing & How It Works**
- [ ] Create compelling homepage (mission, stats, CTA)
- [ ] Write "How It Works" page (transparency about matching)
- [ ] Create FAQ section
- [ ] Add example letters / testimonials

**Day 17: Legal & Privacy**
- [ ] Write basic Privacy Policy (GDPR-compliant)
- [ ] Write Terms of Service
- [ ] Add cookie consent if needed
- [ ] Create Impressum (legal requirement in Germany)

#### Track 7: Final Testing & Launch Prep (Days 18-20)

**Day 18: User Acceptance Testing**
- [ ] Run through entire flow with fresh eyes
- [ ] Test on multiple devices and browsers
- [ ] Verify all links and forms work
- [ ] Check for typos and formatting issues

**Day 19: Performance & Security Audit**
- [ ] Load testing (how many concurrent users can it handle?)
- [ ] Security review (XSS, CSRF, SQL injection protections)
- [ ] Check all forms have proper validation
- [ ] Review admin permissions

**Day 20: Launch Preparation**
- [ ] Create launch checklist
- [ ] Prepare 39C3 demo script
- [ ] Set up analytics/monitoring dashboards
- [ ] Plan initial outreach (Twitter, mailing lists, etc.)

## Completed Features (From Previous Work)
- [x] Account Management (registration, login, password reset, deletion)
- [x] Double opt-in email verification
- [x] TopicArea taxonomy with keyword matching
- [x] Representative metadata sync (photos, committees, focus areas)
- [x] Committee-to-topic automatic mapping
- [x] Self-declared constituency verification
- [x] HTMX-based representative suggestions
- [x] Basic letter authoring and signing flow

## Explicitly Deferred (Post-39C3)
- Third-party identity verification (Verimi, yes®)
- Analytics/feedback systems (basic monitoring only for MVP)
- EU Parliament & Landtag levels (Bundestag only for MVP)
- Draft auto-save functionality
- Advanced admin moderation tools
- Multiple language support (German only for MVP, i18n structure ready)

## Out of Scope for MVP
- Local municipality reps, party-wide campaigns.
- In-browser letter editing with collaboration.
- Advanced analytics or CRM tooling.
- Multiple identity providers (beyond initial integration).
- Expert matching based on representative metadata keywords
- Biography providers, display on representative detail view and extract keywords for matching
