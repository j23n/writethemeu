Letters
- letters should be written in german or english

Overall
- remove admin link
- remove Kompetenzen page

----

important: make sure that the email signup/passwordreset messages are actually sent
remove: custom markdown rendering, use existing packages instead
letter/new/: representative dropdown should have text filtering, similar to the wahlkreis drop down in /profile
api/analyze-title: title 'universitäten' does not match TopicArea 'hochschule'
model Committee.memberships: need mapping of 'role' to human readable string shown e.g. in the recommentations
important: we never want to save a person's address. Hence, the profile page should be changed so that a user can search for their wahlkreise by entering an address. This calls our WahlkreisLocator (with htmx?) and returns the relevant Wahlkreise. THESE are then saved to the profile
important: remove verification from profile html template until it is implemented
