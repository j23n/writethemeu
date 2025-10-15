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
refactor ConstituencyLocator.locate() should return Constituencies, not reprensentatives. Sometimes Cs don't have Rs! this should be handled when we need representatives
