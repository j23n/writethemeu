# WriteThem.eu - Quick Start Guide

## 🚀 Getting Started in 5 Minutes

### 1. Setup Database and Dependencies
```bash
# Already done - migrations have been run!
cd website
```

### 2. Start the Development Server
```bash
uv run python manage.py runserver
```

### 3. Access the Application
- **Main Site**: http://localhost:8000/
- **Admin Panel**: http://localhost:8000/admin/
  - Username: `admin`
  - Password: `admin123`

## 📝 Quick Test Flow

### As a New User:

1. **Register** at http://localhost:8000/register/
   - Create an account with username/email/password

2. **Browse Letters** at http://localhost:8000/
   - View existing open letters (if any)

3. **Write a Letter** at http://localhost:8000/letter/new/
   - Select "Example Representative (STUB)" from the dropdown
   - Write your letter with title and body
   - Add tags (comma-separated): climate, transport, education
   - Click "Publish Letter"

4. **Sign a Letter**
   - Go to any letter detail page
   - Add an optional comment
   - Click "Sign this letter"

5. **Verify Your Identity**
   - Go to http://localhost:8000/profile/
   - Click "Start Verification"
   - Click "Complete Verification (Stub)" to simulate verification
   - Your signatures will now show a "✓ Verified Constituent" badge

6. **Report a Letter**
   - On any letter page, scroll to "Report this letter"
   - Select a reason and add description
   - Submit the report

### As an Admin:

1. **Access Admin Panel** at http://localhost:8000/admin/
   - Login with admin/admin123

2. **Manage Representatives**
   - Add more representatives with different constituencies
   - Set active/inactive status

3. **Review Reports**
   - Check flagged letters in the Reports section
   - Update status and add moderator notes

4. **View All Data**
   - Browse constituencies, letters, signatures, verifications

## 🔧 Management Commands

### Sync Representatives (Stub)
```bash
uv run python manage.py sync_representatives
# Options:
# --level federal|state|local|all
# --dry-run  (preview without saving)
```

## 📊 Key Features Demonstrated

✅ **Letter Creation & Publishing**
- Rich text support
- Tag system
- Representative selection

✅ **Signature System**
- PPI redaction (shows "First L." for verified users)
- Verification badges
- Comment support

✅ **Identity Verification (Stub)**
- Pending → Verified flow
- Constituency mapping
- Verification status display

✅ **Search & Filter**
- Full-text search
- Tag filtering
- Representative filtering

✅ **Moderation**
- Report system
- Status tracking
- Admin review workflow

## 🔍 Project Structure

```
website/
├── manage.py                    # Django management
├── writethem/                   # Project settings
│   ├── settings.py
│   └── urls.py
└── letters/                     # Main app
    ├── models.py               # Data models
    ├── views.py                # Views and logic
    ├── forms.py                # Forms
    ├── services.py             # Business logic
    ├── admin.py                # Admin config
    ├── urls.py                 # URL routing
    ├── templates/letters/      # Templates
    └── management/commands/    # Custom commands
```

## 📚 Next Steps

See `IMPLEMENTATION.md` for:
- Detailed architecture
- API integration research
- Production deployment guide
- How to implement real APIs

## 🎯 What's Stubbed vs. Real

### ✅ Fully Implemented (Production-Ready)
- All data models and database schema
- User authentication and authorization
- Letter CRUD operations
- Signature system with PPI redaction
- Search and filtering
- Report/moderation system
- Admin interface
- Responsive UI

### 🔄 Stubbed (Framework Ready for Integration)
- Representative data syncing from Bundestag/Abgeordnetenwatch APIs
- Address-to-constituency mapping (geocoding + shapefiles)
- Identity verification provider integration

All stubbed components have documented integration points and research findings in the code!
