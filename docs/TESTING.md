# Testing

## Grailed staging incident smoke checks

Run these checks against the staging bot after a verified staging deployment. Record only the listing ID, outcome state, and duration for each check.

| Case | Listing ID | Expected outcome |
| --- | --- | --- |
| Resolved short link | `100324065` | One successful item calculation and no blocked-page seller advisory. |
| Canonical listing | `87485016` | One successful item calculation and no blocked-page seller advisory. |
| Canonical listing | `99406229` | One successful item calculation and no blocked-page seller advisory. |
| Canonical listing | `102514433` | One successful item calculation and no blocked-page seller advisory. |

Also validate these response states:

- A blocked page produces a `Grailed page blocked` warning, performs no seller extraction, and leaves no secret or raw Telegram update in logs.
- An incomplete page triggers no more than two headless page attempts.

Do not place credentials, user identifiers, or raw Telegram messages in smoke-test notes or logs.
